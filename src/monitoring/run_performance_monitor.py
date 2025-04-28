#!/usr/bin/env python3
"""
Trade Performance Monitoring System

This script serves as the entry point for the trade performance monitoring system.
It orchestrates the collection, processing, analysis, and reporting of trade metrics.
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
import json
import pandas as pd
from typing import Dict, Any, List, Optional

# Add project root to path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from .collectors.performance_collector import PerformanceCollector
from .analysis.metrics_loader import MetricsLoader
from .analysis.bottleneck_analyzer import BottleneckAnalyzer, PerformanceReport
from .config.config_manager import ConfigManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('performance_monitor.log')
    ]
)

logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Trade Performance Monitoring System")
    
    # General options
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--output-dir', type=str, help='Directory to save reports')
    
    # Time range options
    parser.add_argument('--start-time', type=str, help='Start time for analysis (ISO format)')
    parser.add_argument('--end-time', type=str, help='End time for analysis (ISO format)')
    parser.add_argument('--last-hours', type=int, help='Analyze the last N hours')
    
    # Analysis options
    parser.add_argument('--exchanges', type=str, nargs='+', help='Exchanges to analyze')
    parser.add_argument('--pairs', type=str, nargs='+', help='Trading pairs to analyze')
    parser.add_argument('--report-format', type=str, choices=['html', 'json', 'both'], 
                        help='Output format for the report')
    parser.add_argument('--correlation-threshold', type=float,
                        help='Threshold for considering metrics correlated')
    parser.add_argument('--anomaly-threshold', type=float,
                        help='Z-score threshold for anomaly detection')
    
    # Data source options
    parser.add_argument('--data-source', type=str, choices=['collector', 'prometheus', 'csv'],
                        help='Source of performance data')
    parser.add_argument('--prometheus-url', type=str, help='Prometheus server URL')
    parser.add_argument('--csv-dir', type=str, help='Directory containing CSV metric files')
    
    return parser.parse_args()

def determine_time_range(config_manager, args):
    """Determine the time range for analysis based on arguments."""
    end_time = datetime.now()
    
    if args.end_time:
        try:
            end_time = datetime.fromisoformat(args.end_time)
        except ValueError:
            logger.warning(f"Invalid end time format: {args.end_time}. Using current time.")
    
    if args.start_time:
        try:
            start_time = datetime.fromisoformat(args.start_time)
        except ValueError:
            logger.warning(f"Invalid start time format: {args.start_time}. Using default time window.")
            start_time = end_time - timedelta(seconds=config_manager.get("analysis.time_window", 300))
    elif args.last_hours:
        start_time = end_time - timedelta(hours=args.last_hours)
    else:
        # Default to configured time window
        start_time = end_time - timedelta(seconds=config_manager.get("analysis.time_window", 300))
    
    return start_time, end_time

def get_metrics_from_collector(config_manager) -> Dict[str, pd.DataFrame]:
    """Get metrics from the PerformanceCollector."""
    logger.info("Collecting performance metrics from collector")
    
    # Get configuration values
    exchanges = config_manager.get("exchanges")
    pairs = config_manager.get("pairs")
    collection_interval = config_manager.get("collection.interval", 15)
    max_trade_history = config_manager.get("collection.max_trade_history", 1000)
    latency_buckets = config_manager.get("collection.latency_buckets", 
                                         [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
    slippage_buckets = config_manager.get("collection.slippage_buckets", 
                                          [0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    
    # Initialize collector with configuration
    collector = PerformanceCollector(
        exchanges=exchanges,
        pairs=pairs,
        latency_buckets=latency_buckets,
        slippage_buckets=slippage_buckets,
        collection_interval=collection_interval,
        max_trade_history=max_trade_history
    )
    
    # Collect metrics into dictionary of DataFrames
    metrics = {}
    
    # Loop through exchanges and pairs to get metrics
    for exchange in exchanges:
        for pair in pairs:
            try:
                summary = collector.get_trade_metrics_summary(exchange, pair)
                
                # Convert each metric to a DataFrame with timestamp and value
                timestamp = datetime.now()
                for metric_name, value in summary.items():
                    full_metric_name = f"performance.{exchange}.{pair}.{metric_name}"
                    if full_metric_name not in metrics:
                        metrics[full_metric_name] = pd.DataFrame(columns=["timestamp", "value"])
                    
                    # Add the data point
                    new_row = pd.DataFrame({"timestamp": [timestamp], "value": [value]})
                    metrics[full_metric_name] = pd.concat([metrics[full_metric_name], new_row], ignore_index=True)
            
            except Exception as e:
                logger.error(f"Error collecting metrics for {exchange}/{pair}: {e}")
    
    return metrics

def get_metrics_from_prometheus(config_manager, start_time, end_time) -> Dict[str, pd.DataFrame]:
    """Get metrics from Prometheus."""
    logger.info("Collecting performance metrics from Prometheus")
    
    # Get Prometheus configuration
    prometheus_url = config_manager.get("data_sources.prometheus.url", "http://localhost:9090")
    step = config_manager.get("data_sources.prometheus.step", "15s")
    
    # Initialize metrics loader
    loader = MetricsLoader({"prometheus_url": prometheus_url})
    
    # Get exchanges and pairs for query construction
    exchanges = config_manager.get("exchanges")
    pairs = config_manager.get("pairs")
    
    # Construct queries based on exchanges and pairs
    queries = {}
    
    # Add performance queries for each exchange and pair
    for exchange in exchanges:
        for pair in pairs:
            pair_label = pair.replace("/", "_")
            queries[f"performance.{exchange}.{pair}.latency.total"] = f'avg(trade_execution_time_seconds{{exchange="{exchange}",pair="{pair_label}"}})'
            queries[f"performance.{exchange}.{pair}.slippage.percent"] = f'avg(trade_slippage_percent{{exchange="{exchange}",pair="{pair_label}"}})'
            queries[f"performance.{exchange}.{pair}.fill_rate"] = f'avg(order_fill_rate{{exchange="{exchange}",pair="{pair_label}"}})'
            queries[f"performance.{exchange}.{pair}.rejection_rate"] = f'avg(order_rejection_rate{{exchange="{exchange}",pair="{pair_label}"}})'
    
    # Add system metrics
    queries["system.cpu_usage"] = 'avg(system_cpu_usage)'
    queries["system.memory_usage"] = 'avg(system_memory_usage)'
    queries["system.network_utilization"] = 'avg(system_network_utilization)'
    
    # Load metrics from Prometheus
    return loader.load_from_prometheus(queries, start_time, end_time, step=step)

def get_metrics_from_csv(config_manager) -> Dict[str, pd.DataFrame]:
    """Get metrics from CSV files."""
    logger.info("Loading performance metrics from CSV files")
    
    # Get CSV configuration
    csv_dir = config_manager.get("data_sources.csv.directory", "./data/metrics")
    timestamp_column = config_manager.get("data_sources.csv.timestamp_column", "timestamp")
    value_column = config_manager.get("data_sources.csv.value_column", "value")
    timestamp_format = config_manager.get("data_sources.csv.timestamp_format")
    
    # Ensure directory exists
    if not os.path.exists(csv_dir):
        logger.error(f"CSV directory not found: {csv_dir}")
        return {}
    
    # Map metrics to CSV files
    file_paths = {}
    
    # Get exchanges and pairs for creating file paths
    exchanges = config_manager.get("exchanges")
    pairs = config_manager.get("pairs")
    
    # Create mappings for performance metrics by exchange and pair
    for exchange in exchanges:
        for pair in pairs:
            pair_label = pair.replace("/", "_")
            
            # Map metrics to file paths
            file_paths[f"performance.{exchange}.{pair}.latency.total"] = os.path.join(
                csv_dir, f"latency_{exchange}_{pair_label}.csv")
            file_paths[f"performance.{exchange}.{pair}.slippage.percent"] = os.path.join(
                csv_dir, f"slippage_{exchange}_{pair_label}.csv")
            file_paths[f"performance.{exchange}.{pair}.fill_rate"] = os.path.join(
                csv_dir, f"fill_rate_{exchange}_{pair_label}.csv")
            file_paths[f"performance.{exchange}.{pair}.rejection_rate"] = os.path.join(
                csv_dir, f"rejection_rate_{exchange}_{pair_label}.csv")
    
    # Add system metrics
    file_paths["system.cpu_usage"] = os.path.join(csv_dir, "cpu_usage.csv")
    file_paths["system.memory_usage"] = os.path.join(csv_dir, "memory_usage.csv")
    file_paths["system.network_utilization"] = os.path.join(csv_dir, "network_utilization.csv")
    
    # Filter to include only existing files
    existing_file_paths = {k: v for k, v in file_paths.items() if os.path.exists(v)}
    
    if not existing_file_paths:
        logger.warning(f"No CSV metric files found in directory: {csv_dir}")
        return {}
    
    # Initialize metrics loader
    loader = MetricsLoader()
    
    # Load metrics from CSV files
    return loader.load_from_csv(
        existing_file_paths,
        timestamp_column=timestamp_column,
        value_column=value_column,
        timestamp_format=timestamp_format
    )

def main():
    """Main execution function."""
    args = parse_args()
    
    # Load configuration
    config_manager = ConfigManager(args.config)
    
    # Update config with command-line arguments if provided
    if args.output_dir:
        config_manager.set("reporting.output_directory", args.output_dir)
    if args.exchanges:
        config_manager.set("exchanges", args.exchanges)
    if args.pairs:
        config_manager.set("pairs", args.pairs)
    if args.report_format:
        config_manager.set("reporting.format", args.report_format)
    if args.correlation_threshold:
        config_manager.set("analysis.correlation_threshold", args.correlation_threshold)
    if args.anomaly_threshold:
        config_manager.set("analysis.anomaly_z_threshold", args.anomaly_threshold)
    if args.prometheus_url:
        config_manager.set("data_sources.prometheus.url", args.prometheus_url)
    if args.csv_dir:
        config_manager.set("data_sources.csv.directory", args.csv_dir)
    
    # Set up logging based on configuration
    log_level = config_manager.get("logging.level", "INFO")
    log_file = config_manager.get("logging.file", "performance_monitor.log")
    
    numeric_level = getattr(logging, log_level.upper(), None)
    if isinstance(numeric_level, int):
        logging.getLogger().setLevel(numeric_level)
        # Update file handler
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()
                logging.getLogger().removeHandler(handler)
        
        # Add new file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(file_handler)
    
    # Determine time range for analysis
    start_time, end_time = determine_time_range(config_manager, args)
    logger.info(f"Analyzing data from {start_time} to {end_time}")
    
    # Create output directory if it doesn't exist
    output_dir = config_manager.get("reporting.output_directory", "./reports")
    os.makedirs(output_dir, exist_ok=True)
    
    # Get data source from arguments or configuration
    data_source = args.data_source or config_manager.get("data_source", "collector")
    
    # Get metrics based on specified data source
    if data_source == "collector":
        metrics = get_metrics_from_collector(config_manager)
    elif data_source == "prometheus":
        metrics = get_metrics_from_prometheus(config_manager, start_time, end_time)
    elif data_source == "csv":
        metrics = get_metrics_from_csv(config_manager)
    else:
        logger.error(f"Unsupported data source: {data_source}")
        return 1
    
    # Check if we have any metrics
    if not metrics or all(df.empty for df in metrics.values()):
        logger.error("No metrics data available for analysis")
        return 1
    
    logger.info(f"Loaded {len(metrics)} metrics for analysis")
    
    # Initialize the analyzer with configuration
    analyzer = BottleneckAnalyzer(
        correlation_threshold=config_manager.get("analysis.correlation_threshold", 0.7),
        anomaly_z_threshold=config_manager.get("analysis.anomaly_z_threshold", 3.0),
        time_window=config_manager.get("analysis.time_window", 300),
        min_samples=config_manager.get("analysis.min_samples", 10)
    )
    
    # Perform analysis
    logger.info("Analyzing metrics for bottlenecks and anomalies")
    analysis_results = analyzer.analyze_metrics(metrics)
    
    # Generate test configuration for the report
    test_config = {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "exchanges": config_manager.get("exchanges"),
        "pairs": config_manager.get("pairs"),
        "correlation_threshold": config_manager.get("analysis.correlation_threshold"),
        "anomaly_threshold": config_manager.get("analysis.anomaly_z_threshold"),
        "data_source": data_source
    }
    
    # Determine report format(s)
    report_format = config_manager.get("reporting.format", "html")
    output_formats = []
    
    if report_format == "both":
        output_formats = ["html", "json"]
    else:
        output_formats = [report_format]
    
    # Generate reports in specified formats
    for format_type in output_formats:
        try:
            # Initialize the report generator
            report_generator = PerformanceReport(output_format=format_type)
            
            # Generate the report
            report_content = report_generator.generate_report(
                metrics=metrics,
                analysis_results=analysis_results,
                test_config=test_config,
                time_range=(start_time, end_time)
            )
            
            # Save the report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"performance_report_{timestamp}.{format_type}"
            report_path = os.path.join(output_dir, filename)
            
            with open(report_path, "w") as f:
                f.write(report_content)
            
            logger.info(f"Generated {format_type} report: {report_path}")
            
            # Optionally save metrics data
            if config_manager.get("reporting.save_metrics", False):
                metrics_filename = f"metrics_data_{timestamp}.json"
                metrics_path = os.path.join(output_dir, metrics_filename)
                
                # Convert metrics DataFrames to serializable dictionaries
                serializable_metrics = {}
                for metric_name, df in metrics.items():
                    records = []
                    for _, row in df.iterrows():
                        records.append({
                            "timestamp": row["timestamp"].isoformat() if isinstance(row["timestamp"], datetime) else row["timestamp"],
                            "value": float(row["value"])
                        })
                    serializable_metrics[metric_name] = records
                
                with open(metrics_path, "w") as f:
                    json.dump(serializable_metrics, f, indent=2)
                
                logger.info(f"Saved metrics data: {metrics_path}")
        
        except Exception as e:
            logger.error(f"Error generating {format_type} report: {e}", exc_info=True)
    
    logger.info("Performance monitoring completed successfully")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1) 