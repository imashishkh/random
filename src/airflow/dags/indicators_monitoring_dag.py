"""
Airflow DAG for monitoring the technical indicator calculation system.
"""

import os
import json
import logging
from datetime import datetime, timedelta

# Airflow imports
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
from airflow.models import Variable
from airflow.hooks.base_hook import BaseHook
from airflow.contrib.operators.slack_webhook_operator import SlackWebhookOperator

# Project imports
import pandas as pd
import numpy as np
from ...db.mongo_connection import get_mongo_client
from ...cache.redis_client import RedisClient

# Set up logging
logger = logging.getLogger(__name__)

# Default arguments for the DAG
default_args = {
    'owner': 'forex_trading',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=10),
    'start_date': days_ago(1),
}

# Helper functions for tasks
def check_market_data_freshness(**kwargs):
    """
    Check that market data is being updated regularly.
    
    Returns:
        Dictionary with market data freshness metrics
    """
    try:
        logger.info("Checking market data freshness")
        
        # Connect to MongoDB
        mongo_client = get_mongo_client()
        db = mongo_client.forex
        market_data_collection = db.market_data
        
        # Define symbols and timeframes to check
        symbols = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD']
        timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        
        results = {
            'freshness_checks': [],
            'overall_status': 'green',
            'total_checks': len(symbols) * len(timeframes),
            'passed_checks': 0,
            'warning_checks': 0,
            'failed_checks': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        # Define freshness thresholds (in seconds)
        freshness_thresholds = {
            '1m': {'warning': 120, 'critical': 300},    # 2min/5min
            '5m': {'warning': 300, 'critical': 900},    # 5min/15min
            '15m': {'warning': 900, 'critical': 1800},  # 15min/30min
            '1h': {'warning': 3600, 'critical': 7200},  # 1hr/2hr
            '4h': {'warning': 14400, 'critical': 28800},# 4hr/8hr
            '1d': {'warning': 86400, 'critical': 172800}# 1day/2day
        }
        
        for symbol in symbols:
            for timeframe in timeframes:
                # Get the most recent data point
                latest_data = market_data_collection.find_one(
                    {'symbol': symbol, 'timeframe': timeframe},
                    sort=[('timestamp', -1)]
                )
                
                if not latest_data:
                    # No data found
                    check_result = {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'status': 'red',
                        'message': 'No data found',
                        'timestamp': None,
                        'age_seconds': None
                    }
                    results['failed_checks'] += 1
                    if results['overall_status'] != 'red':
                        results['overall_status'] = 'red'
                else:
                    # Calculate data age
                    latest_timestamp = latest_data.get('timestamp')
                    if latest_timestamp:
                        now = datetime.now()
                        age_seconds = (now - latest_timestamp).total_seconds()
                        
                        # Check against thresholds
                        thresholds = freshness_thresholds.get(timeframe, {'warning': 3600, 'critical': 7200})
                        
                        if age_seconds < thresholds['warning']:
                            status = 'green'
                            message = 'Data is fresh'
                            results['passed_checks'] += 1
                        elif age_seconds < thresholds['critical']:
                            status = 'yellow'
                            message = f'Data is stale: {int(age_seconds)}s old'
                            results['warning_checks'] += 1
                            if results['overall_status'] == 'green':
                                results['overall_status'] = 'yellow'
                        else:
                            status = 'red'
                            message = f'Data is critically outdated: {int(age_seconds)}s old'
                            results['failed_checks'] += 1
                            results['overall_status'] = 'red'
                        
                        check_result = {
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'status': status,
                            'message': message,
                            'timestamp': latest_timestamp.isoformat(),
                            'age_seconds': age_seconds
                        }
                    else:
                        check_result = {
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'status': 'red',
                            'message': 'Invalid timestamp in data',
                            'timestamp': None,
                            'age_seconds': None
                        }
                        results['failed_checks'] += 1
                        results['overall_status'] = 'red'
                
                results['freshness_checks'].append(check_result)
        
        # Save results to XCom
        kwargs['ti'].xcom_push(key='market_data_freshness', value=results)
        
        logger.info(f"Market data freshness check complete. Status: {results['overall_status']}")
        return results
        
    except Exception as e:
        logger.exception(f"Error checking market data freshness: {e}")
        return {
            'overall_status': 'red',
            'message': f"Error checking data freshness: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }

def check_indicator_calculation_status(**kwargs):
    """
    Check that technical indicators are being calculated successfully.
    
    Returns:
        Dictionary with indicator calculation metrics
    """
    try:
        logger.info("Checking indicator calculation status")
        
        # Connect to MongoDB
        mongo_client = get_mongo_client()
        db = mongo_client.forex
        indicators_collection = db.technical_indicators
        
        # Define symbols and timeframes to check
        symbols = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD']
        timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        
        # Define indicators to check
        indicators = ['SMA', 'EMA', 'RSI', 'MACD', 'BBANDS', 'ATR']
        
        results = {
            'indicator_checks': [],
            'overall_status': 'green',
            'total_checks': len(symbols) * len(timeframes) * len(indicators),
            'passed_checks': 0,
            'warning_checks': 0,
            'failed_checks': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        # Define freshness thresholds (in seconds)
        freshness_thresholds = {
            '1m': {'warning': 300, 'critical': 600},    # 5min/10min
            '5m': {'warning': 600, 'critical': 1200},   # 10min/20min
            '15m': {'warning': 1200, 'critical': 2400}, # 20min/40min
            '1h': {'warning': 3600, 'critical': 7200},  # 1hr/2hr
            '4h': {'warning': 14400, 'critical': 28800},# 4hr/8hr
            '1d': {'warning': 86400, 'critical': 172800}# 1day/2day
        }
        
        for symbol in symbols:
            for timeframe in timeframes:
                for indicator in indicators:
                    # Get the most recent indicator calculation
                    latest_indicator = indicators_collection.find_one(
                        {
                            'symbol': symbol, 
                            'timeframe': timeframe,
                            'indicator': indicator
                        }
                    )
                    
                    if not latest_indicator:
                        # No indicator found
                        check_result = {
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'indicator': indicator,
                            'status': 'red',
                            'message': 'No indicator data found',
                            'timestamp': None,
                            'age_seconds': None
                        }
                        results['failed_checks'] += 1
                        if results['overall_status'] != 'red':
                            results['overall_status'] = 'red'
                    else:
                        # Calculate indicator age
                        updated_at = latest_indicator.get('updated_at')
                        if updated_at:
                            now = datetime.now()
                            age_seconds = (now - updated_at).total_seconds()
                            
                            # Check against thresholds
                            thresholds = freshness_thresholds.get(timeframe, {'warning': 3600, 'critical': 7200})
                            
                            if age_seconds < thresholds['warning']:
                                status = 'green'
                                message = 'Indicator is up to date'
                                results['passed_checks'] += 1
                            elif age_seconds < thresholds['critical']:
                                status = 'yellow'
                                message = f'Indicator is stale: {int(age_seconds)}s old'
                                results['warning_checks'] += 1
                                if results['overall_status'] == 'green':
                                    results['overall_status'] = 'yellow'
                            else:
                                status = 'red'
                                message = f'Indicator is critically outdated: {int(age_seconds)}s old'
                                results['failed_checks'] += 1
                                results['overall_status'] = 'red'
                            
                            # Also check if the calculation has a valid value
                            latest_value = latest_indicator.get('latest_value')
                            if latest_value is None:
                                status = 'red'
                                message = 'Indicator has null value'
                                results['failed_checks'] += 1
                                results['overall_status'] = 'red'
                            
                            check_result = {
                                'symbol': symbol,
                                'timeframe': timeframe,
                                'indicator': indicator,
                                'status': status,
                                'message': message,
                                'timestamp': updated_at.isoformat(),
                                'age_seconds': age_seconds
                            }
                        else:
                            check_result = {
                                'symbol': symbol,
                                'timeframe': timeframe,
                                'indicator': indicator,
                                'status': 'red',
                                'message': 'Invalid timestamp in indicator data',
                                'timestamp': None,
                                'age_seconds': None
                            }
                            results['failed_checks'] += 1
                            results['overall_status'] = 'red'
                    
                    results['indicator_checks'].append(check_result)
        
        # Save results to XCom
        kwargs['ti'].xcom_push(key='indicator_calculation_status', value=results)
        
        logger.info(f"Indicator calculation check complete. Status: {results['overall_status']}")
        return results
        
    except Exception as e:
        logger.exception(f"Error checking indicator calculation status: {e}")
        return {
            'overall_status': 'red',
            'message': f"Error checking indicator status: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }

def check_cache_health(**kwargs):
    """
    Check Redis cache health and performance.
    
    Returns:
        Dictionary with cache health metrics
    """
    try:
        logger.info("Checking Redis cache health")
        
        # Initialize Redis client
        redis_client = RedisClient()
        
        # Get cache info
        info = redis_client.info()
        
        # Calculate key metrics
        used_memory = info.get('used_memory_human', 'N/A')
        used_memory_peak = info.get('used_memory_peak_human', 'N/A')
        memory_fragmentation_ratio = info.get('mem_fragmentation_ratio', 0)
        connected_clients = info.get('connected_clients', 0)
        uptime_days = info.get('uptime_in_days', 0)
        total_keys = sum(info.get(f'db{i}', {}).get('keys', 0) for i in range(16))
        
        # Get indicator-specific keys
        indicator_keys = redis_client.keys('indicator:*')
        num_indicator_keys = len(indicator_keys)
        
        # Check for issues
        issues = []
        
        if memory_fragmentation_ratio > 1.5:
            issues.append(f'High memory fragmentation ratio: {memory_fragmentation_ratio}')
        
        if connected_clients > 100:
            issues.append(f'Large number of connected clients: {connected_clients}')
        
        # Create health status
        if issues:
            status = 'yellow'
        else:
            status = 'green'
        
        results = {
            'overall_status': status,
            'used_memory': used_memory,
            'used_memory_peak': used_memory_peak,
            'memory_fragmentation_ratio': memory_fragmentation_ratio,
            'connected_clients': connected_clients,
            'uptime_days': uptime_days,
            'total_keys': total_keys,
            'indicator_keys': num_indicator_keys,
            'issues': issues,
            'timestamp': datetime.now().isoformat()
        }
        
        # Save results to XCom
        kwargs['ti'].xcom_push(key='cache_health', value=results)
        
        logger.info(f"Cache health check complete. Status: {results['overall_status']}")
        return results
        
    except Exception as e:
        logger.exception(f"Error checking cache health: {e}")
        return {
            'overall_status': 'red',
            'message': f"Error checking cache health: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }

def generate_system_health_report(**kwargs):
    """
    Generate a comprehensive health report for the indicator system.
    
    Combines results from all health checks into a single report.
    """
    try:
        logger.info("Generating system health report")
        
        # Get task instance
        ti = kwargs['ti']
        
        # Get results from previous tasks
        market_data_freshness = ti.xcom_pull(task_ids='check_market_data_freshness', 
                                            key='market_data_freshness')
        indicator_status = ti.xcom_pull(task_ids='check_indicator_calculation_status', 
                                      key='indicator_calculation_status')
        cache_health = ti.xcom_pull(task_ids='check_cache_health', 
                                   key='cache_health')
        
        # Determine overall system status
        status_priority = {'red': 3, 'yellow': 2, 'green': 1}
        
        statuses = [
            market_data_freshness.get('overall_status', 'red'),
            indicator_status.get('overall_status', 'red'),
            cache_health.get('overall_status', 'red')
        ]
        
        # Get highest priority status (red > yellow > green)
        overall_status = max(statuses, key=lambda s: status_priority.get(s, 0))
        
        # Generate report
        report = {
            'overall_status': overall_status,
            'timestamp': datetime.now().isoformat(),
            'market_data_freshness': market_data_freshness,
            'indicator_status': indicator_status,
            'cache_health': cache_health,
            'summary': {
                'total_checks': (
                    market_data_freshness.get('total_checks', 0) +
                    indicator_status.get('total_checks', 0) +
                    1  # Cache health
                ),
                'passed_checks': (
                    market_data_freshness.get('passed_checks', 0) +
                    indicator_status.get('passed_checks', 0) +
                    (1 if cache_health.get('overall_status') == 'green' else 0)
                ),
                'warning_checks': (
                    market_data_freshness.get('warning_checks', 0) +
                    indicator_status.get('warning_checks', 0) +
                    (1 if cache_health.get('overall_status') == 'yellow' else 0)
                ),
                'failed_checks': (
                    market_data_freshness.get('failed_checks', 0) +
                    indicator_status.get('failed_checks', 0) +
                    (1 if cache_health.get('overall_status') == 'red' else 0)
                )
            }
        }
        
        # Add action items if issues exist
        action_items = []
        
        if market_data_freshness.get('failed_checks', 0) > 0:
            action_items.append("Check market data collection services")
        
        if indicator_status.get('failed_checks', 0) > 0:
            action_items.append("Investigate indicator calculation pipeline")
        
        if cache_health.get('overall_status') == 'red':
            action_items.append("Address Redis cache issues")
        
        report['action_items'] = action_items
        
        # Save report to MongoDB
        mongo_client = get_mongo_client()
        db = mongo_client.forex
        health_reports_collection = db.system_health_reports
        
        health_reports_collection.insert_one(report)
        
        # Save results to XCom
        ti.xcom_push(key='system_health_report', value=report)
        
        logger.info(f"System health report generated. Overall status: {overall_status}")
        return report
        
    except Exception as e:
        logger.exception(f"Error generating system health report: {e}")
        return {
            'overall_status': 'red',
            'message': f"Error generating health report: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }

def send_alerts(**kwargs):
    """
    Send alerts if system health issues are detected.
    
    Currently supports Slack notifications.
    """
    try:
        logger.info("Checking if alerts need to be sent")
        
        # Get task instance
        ti = kwargs['ti']
        
        # Get system health report
        report = ti.xcom_pull(task_ids='generate_system_health_report', 
                             key='system_health_report')
        
        if not report:
            logger.error("No health report found")
            return False
        
        # Check if alerts are needed
        overall_status = report.get('overall_status')
        
        if overall_status == 'green':
            logger.info("System health is good, no alerts needed")
            return True
        
        # Format alert message
        summary = report.get('summary', {})
        
        alert_message = {
            'blocks': [
                {
                    'type': 'header',
                    'text': {
                        'type': 'plain_text',
                        'text': f"🚨 System Health Alert: {overall_status.upper()}"
                    }
                },
                {
                    'type': 'section',
                    'text': {
                        'type': 'mrkdwn',
                        'text': f"*System Health Report*\n"
                               f"Status: {overall_status.upper()}\n"
                               f"Time: {report.get('timestamp')}\n"
                               f"Checks: {summary.get('passed_checks', 0)} passed, "
                               f"{summary.get('warning_checks', 0)} warnings, "
                               f"{summary.get('failed_checks', 0)} failed"
                    }
                }
            ]
        }
        
        # Add action items
        action_items = report.get('action_items', [])
        if action_items:
            action_text = "*Action Items:*\n" + "\n".join(f"• {item}" for item in action_items)
            alert_message['blocks'].append({
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': action_text
                }
            })
        
        # Send to Slack
        # In a real implementation, this would use SlackWebhookOperator
        # but for this example, we'll just log the message
        logger.info(f"Would send alert: {json.dumps(alert_message)}")
        
        return True
        
    except Exception as e:
        logger.exception(f"Error sending alerts: {e}")
        return False

# Define the DAG
with DAG(
    'indicators_monitoring',
    default_args=default_args,
    description='Monitor the technical indicator calculation system',
    schedule_interval='*/15 * * * *',  # Every 15 minutes
    catchup=False,
    tags=['forex', 'indicators', 'monitoring'],
) as dag:
    
    # Start task
    start = DummyOperator(
        task_id='start',
        dag=dag,
    )
    
    # Check market data freshness
    check_market_data = PythonOperator(
        task_id='check_market_data_freshness',
        python_callable=check_market_data_freshness,
        dag=dag,
    )
    
    # Check indicator calculation status
    check_indicators = PythonOperator(
        task_id='check_indicator_calculation_status',
        python_callable=check_indicator_calculation_status,
        dag=dag,
    )
    
    # Check cache health
    check_cache = PythonOperator(
        task_id='check_cache_health',
        python_callable=check_cache_health,
        dag=dag,
    )
    
    # Generate system health report
    generate_report = PythonOperator(
        task_id='generate_system_health_report',
        python_callable=generate_system_health_report,
        dag=dag,
    )
    
    # Send alerts if needed
    send_alerts_task = PythonOperator(
        task_id='send_alerts',
        python_callable=send_alerts,
        dag=dag,
    )
    
    # End task
    end = DummyOperator(
        task_id='end',
        dag=dag,
    )
    
    # Define task dependencies
    start >> [check_market_data, check_indicators, check_cache] >> generate_report >> send_alerts_task >> end 