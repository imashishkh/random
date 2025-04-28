"""
Airflow DAG for calculating and updating technical indicators.
"""

import os
import json
import logging
from datetime import datetime, timedelta

# Airflow imports
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.utils.dates import days_ago
from airflow.models import Variable

# Project imports
import pandas as pd
import numpy as np
from ...indicators.calculator import IndicatorCalculator
from ...cache.redis_client import RedisClient
from ...db.mongo_connection import get_mongo_client

# Set up logging
logger = logging.getLogger(__name__)

# Default arguments for the DAG
default_args = {
    'owner': 'forex_trading',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=30),
    'start_date': days_ago(1),
}

# Helper functions for tasks
def fetch_market_data(symbol, timeframe, lookback_periods, **kwargs):
    """
    Fetch market data for indicator calculation.
    
    Args:
        symbol: Market symbol
        timeframe: Timeframe
        lookback_periods: Number of periods to fetch
        
    Returns:
        Path to a temporary CSV file with the data
    """
    try:
        logger.info(f"Fetching market data for {symbol} {timeframe} (lookback: {lookback_periods})")
        
        # Connect to MongoDB
        mongo_client = get_mongo_client()
        db = mongo_client.forex
        market_data_collection = db.market_data
        
        # Calculate lookback timestamp based on timeframe
        multiplier = 1
        unit = timeframe[-1].lower()
        value = int(timeframe[:-1])
        
        if unit == 'm':
            lookback_minutes = value * lookback_periods
            lookback_time = datetime.now() - timedelta(minutes=lookback_minutes)
        elif unit == 'h':
            lookback_hours = value * lookback_periods
            lookback_time = datetime.now() - timedelta(hours=lookback_hours)
        elif unit == 'd':
            lookback_days = value * lookback_periods
            lookback_time = datetime.now() - timedelta(days=lookback_days)
        else:
            raise ValueError(f"Unsupported timeframe unit: {unit}")
        
        # Query MongoDB for market data
        query = {
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': {'$gte': lookback_time}
        }
        
        projection = {
            '_id': 0,
            'timestamp': 1,
            'open': 1,
            'high': 1,
            'low': 1,
            'close': 1,
            'volume': 1
        }
        
        cursor = market_data_collection.find(query, projection).sort('timestamp', 1)
        market_data = list(cursor)
        
        if not market_data:
            logger.warning(f"No market data found for {symbol} {timeframe}")
            kwargs['ti'].xcom_push(key=f'market_data_{symbol}_{timeframe}', value={'error': 'No data found'})
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(market_data)
        df.set_index('timestamp', inplace=True)
        
        # Save to temporary file for passing between tasks
        tmp_file = f"/tmp/market_data_{symbol}_{timeframe}.csv"
        df.to_csv(tmp_file)
        
        # Push metadata to XCom
        metadata = {
            'symbol': symbol,
            'timeframe': timeframe,
            'data_points': len(df),
            'start_date': df.index[0].isoformat() if len(df) > 0 else None,
            'end_date': df.index[-1].isoformat() if len(df) > 0 else None,
            'file_path': tmp_file
        }
        
        kwargs['ti'].xcom_push(key=f'market_data_{symbol}_{timeframe}', value=metadata)
        logger.info(f"Fetched {len(df)} data points for {symbol} {timeframe}")
        
        return tmp_file
        
    except Exception as e:
        logger.exception(f"Error fetching market data for {symbol} {timeframe}: {e}")
        kwargs['ti'].xcom_push(key=f'market_data_{symbol}_{timeframe}', value={'error': str(e)})
        raise

def calculate_indicators(symbol, timeframe, indicators, **kwargs):
    """
    Calculate technical indicators for market data.
    
    Args:
        symbol: Market symbol
        timeframe: Timeframe
        indicators: List of indicators to calculate
        
    Returns:
        Dictionary of calculated indicators
    """
    try:
        logger.info(f"Calculating indicators for {symbol} {timeframe}")
        
        # Get market data file path from XCom
        ti = kwargs['ti']
        market_data_info = ti.xcom_pull(task_ids=f'fetch_market_data_{symbol}_{timeframe}', 
                                       key=f'market_data_{symbol}_{timeframe}')
        
        if not market_data_info or 'error' in market_data_info:
            logger.error(f"No market data available for {symbol} {timeframe}")
            return {'error': 'No market data available'}
        
        file_path = market_data_info['file_path']
        if not os.path.exists(file_path):
            logger.error(f"Market data file not found: {file_path}")
            return {'error': 'Market data file not found'}
        
        # Load market data from CSV
        market_data = pd.read_csv(file_path, index_col=0, parse_dates=True)
        
        # Initialize calculator
        redis_client = RedisClient()
        calculator = IndicatorCalculator(redis_client=redis_client)
        
        # Calculate indicators
        results = {}
        for indicator_config in indicators:
            name = indicator_config['name']
            params = indicator_config.get('params', {})
            
            logger.info(f"Calculating {name} for {symbol} {timeframe} with params {params}")
            
            result = calculator.calculate(
                name,
                market_data,
                params=params,
                use_cache=True,
                refresh_cache=True,
                metadata={'symbol': symbol, 'timeframe': timeframe}
            )
            
            if result is not None:
                results[name] = {
                    'success': True,
                    'latest_value': result.iloc[-1] if isinstance(result, pd.Series) else {k: v.iloc[-1] for k, v in result.items()},
                    'metadata': {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'indicator': name,
                        'params': params,
                        'calculated_at': datetime.now().isoformat()
                    }
                }
            else:
                results[name] = {
                    'success': False,
                    'error': 'Calculation failed'
                }
        
        # Save results to XCom
        ti.xcom_push(key=f'indicators_{symbol}_{timeframe}', value=results)
        
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
        
        logger.info(f"Calculated {len(results)} indicators for {symbol} {timeframe}")
        return results
        
    except Exception as e:
        logger.exception(f"Error calculating indicators for {symbol} {timeframe}: {e}")
        return {'error': str(e)}

def store_indicator_results(symbol, timeframe, **kwargs):
    """
    Store calculated indicator results in MongoDB.
    
    Args:
        symbol: Market symbol
        timeframe: Timeframe
    """
    try:
        logger.info(f"Storing indicator results for {symbol} {timeframe}")
        
        # Get indicator results from XCom
        ti = kwargs['ti']
        results = ti.xcom_pull(task_ids=f'calculate_indicators_{symbol}_{timeframe}', 
                               key=f'indicators_{symbol}_{timeframe}')
        
        if not results or 'error' in results:
            logger.error(f"No indicator results available for {symbol} {timeframe}")
            return False
        
        # Connect to MongoDB
        mongo_client = get_mongo_client()
        db = mongo_client.forex
        indicators_collection = db.technical_indicators
        
        # Store results
        for indicator_name, result in results.items():
            if result['success']:
                # Prepare document
                document = {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'indicator': indicator_name,
                    'latest_value': result['latest_value'] if isinstance(result['latest_value'], (int, float)) 
                                  else result['latest_value'].to_dict() if hasattr(result['latest_value'], 'to_dict') 
                                  else result['latest_value'],
                    'metadata': result['metadata'],
                    'updated_at': datetime.now()
                }
                
                # Upsert to MongoDB
                indicators_collection.update_one(
                    {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'indicator': indicator_name
                    },
                    {'$set': document},
                    upsert=True
                )
                
                logger.info(f"Stored {indicator_name} result for {symbol} {timeframe}")
        
        return True
        
    except Exception as e:
        logger.exception(f"Error storing indicator results for {symbol} {timeframe}: {e}")
        return False

# Define the DAG
with DAG(
    'technical_indicators_calculation',
    default_args=default_args,
    description='Calculate and update technical indicators from market data',
    schedule_interval='*/5 * * * *',  # Every 5 minutes
    catchup=False,
    tags=['forex', 'indicators'],
) as dag:
    
    # Start task
    start = DummyOperator(
        task_id='start',
        dag=dag,
    )
    
    # End task
    end = DummyOperator(
        task_id='end',
        dag=dag,
    )
    
    # Define symbols and timeframes to process
    symbols = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD']
    timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
    
    # Define indicators to calculate
    indicators_to_calculate = [
        {'name': 'SMA', 'params': {'period': 14}},
        {'name': 'SMA', 'params': {'period': 50}},
        {'name': 'SMA', 'params': {'period': 200}},
        {'name': 'EMA', 'params': {'period': 14}},
        {'name': 'RSI', 'params': {'period': 14}},
        {'name': 'MACD', 'params': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}},
        {'name': 'BBANDS', 'params': {'period': 20, 'std_dev': 2}},
        {'name': 'ATR', 'params': {'period': 14}},
    ]
    
    # Create tasks dynamically for each symbol and timeframe
    for symbol in symbols:
        for timeframe in timeframes:
            # Define lookback periods based on timeframe
            if timeframe in ['1m', '5m']:
                lookback_periods = 1000  # For short timeframes
            elif timeframe in ['15m', '1h']:
                lookback_periods = 500   # For medium timeframes
            else:
                lookback_periods = 300   # For long timeframes
            
            # Task to fetch market data
            fetch_data_task = PythonOperator(
                task_id=f'fetch_market_data_{symbol}_{timeframe}',
                python_callable=fetch_market_data,
                op_kwargs={
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'lookback_periods': lookback_periods
                },
                dag=dag,
            )
            
            # Task to calculate indicators
            calculate_indicators_task = PythonOperator(
                task_id=f'calculate_indicators_{symbol}_{timeframe}',
                python_callable=calculate_indicators,
                op_kwargs={
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'indicators': indicators_to_calculate
                },
                dag=dag,
            )
            
            # Task to store indicator results
            store_results_task = PythonOperator(
                task_id=f'store_indicator_results_{symbol}_{timeframe}',
                python_callable=store_indicator_results,
                op_kwargs={
                    'symbol': symbol,
                    'timeframe': timeframe
                },
                dag=dag,
            )
            
            # Define task dependencies
            start >> fetch_data_task >> calculate_indicators_task >> store_results_task >> end 