"""
Metrics Loader for performance analysis.

This module provides utilities for loading metrics data from various sources
like Prometheus, CSV files, or direct inputs and preparing them for analysis.
"""

import logging
import pandas as pd
import numpy as np
import requests
import json
import os
from typing import Dict, List, Optional, Union, Tuple, Any
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)


class MetricsLoader:
    """
    Loads and prepares metrics data for performance analysis.
    
    This class provides methods to load metrics from various sources,
    including Prometheus, CSV files, or in-memory data structures,
    and prepare them for analysis by the BottleneckAnalyzer.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the metrics loader with optional configuration.
        
        Args:
            config: Configuration dictionary with settings for various data sources
        """
        self.config = config or {}
        self.prometheus_url = self.config.get("prometheus_url", "http://localhost:9090")
        self.cache_dir = self.config.get("cache_dir", "/tmp/metrics_cache")
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception as e:
                logger.warning(f"Could not create cache directory: {e}")
    
    def load_from_prometheus(
        self,
        queries: Dict[str, str],
        start_time: Union[datetime, str],
        end_time: Union[datetime, str],
        step: str = "15s"
    ) -> Dict[str, pd.DataFrame]:
        """
        Load metrics from Prometheus using PromQL queries.
        
        Args:
            queries: Dictionary mapping metric names to PromQL queries
            start_time: Start time for the query range
            end_time: End time for the query range
            step: Step interval for the query (e.g., "15s", "1m", "1h")
            
        Returns:
            Dictionary mapping metric names to DataFrames with timestamps and values
        """
        # Convert datetime objects to ISO 8601 strings if needed
        if isinstance(start_time, datetime):
            start_time = start_time.astimezone(pytz.UTC).isoformat()
        if isinstance(end_time, datetime):
            end_time = end_time.astimezone(pytz.UTC).isoformat()
        
        metrics = {}
        
        for metric_name, query in queries.items():
            logger.info(f"Fetching Prometheus metric: {metric_name} with query: {query}")
            
            try:
                # Construct the Prometheus API query URL
                url = f"{self.prometheus_url}/api/v1/query_range"
                params = {
                    "query": query,
                    "start": start_time,
                    "end": end_time,
                    "step": step
                }
                
                # Make the request to Prometheus
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Check if the response was successful
                if data["status"] != "success":
                    logger.error(f"Error querying Prometheus: {data.get('error', 'Unknown error')}")
                    continue
                
                # Process the results into a DataFrame
                result_data = data["data"]["result"]
                if not result_data:
                    logger.warning(f"No data returned for metric: {metric_name}")
                    metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
                    continue
                
                # For simplicity, we'll use the first result if there are multiple results
                # In a real implementation, you might want to handle multiple results differently
                first_result = result_data[0]
                
                # Extract values
                values = []
                for point in first_result["values"]:
                    timestamp, value = point
                    # Convert timestamp to datetime and value to float
                    dt = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
                    try:
                        val = float(value)
                        values.append({"timestamp": dt, "value": val})
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert value to float: {value}")
                
                # Create DataFrame
                if values:
                    df = pd.DataFrame(values)
                    metrics[metric_name] = df
                else:
                    metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
            
            except Exception as e:
                logger.error(f"Error fetching metric {metric_name} from Prometheus: {str(e)}", exc_info=True)
                metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
        
        return metrics
    
    def load_from_csv(
        self,
        file_paths: Dict[str, str],
        timestamp_column: str = "timestamp",
        value_column: str = "value",
        timestamp_format: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Load metrics from CSV files.
        
        Args:
            file_paths: Dictionary mapping metric names to CSV file paths
            timestamp_column: Name of the column containing timestamps
            value_column: Name of the column containing values
            timestamp_format: Optional datetime format string for parsing timestamps
            
        Returns:
            Dictionary mapping metric names to DataFrames with timestamps and values
        """
        metrics = {}
        
        for metric_name, file_path in file_paths.items():
            logger.info(f"Loading metric {metric_name} from CSV file: {file_path}")
            
            try:
                df = pd.read_csv(file_path)
                
                # Check if required columns exist
                if timestamp_column not in df.columns:
                    logger.error(f"Timestamp column '{timestamp_column}' not found in file: {file_path}")
                    metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
                    continue
                
                if value_column not in df.columns:
                    logger.error(f"Value column '{value_column}' not found in file: {file_path}")
                    metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
                    continue
                
                # Parse timestamps if needed
                if timestamp_format:
                    df["timestamp"] = pd.to_datetime(df[timestamp_column], format=timestamp_format)
                else:
                    df["timestamp"] = pd.to_datetime(df[timestamp_column])
                
                # Rename value column if needed
                if value_column != "value":
                    df["value"] = df[value_column]
                
                # Select only the required columns
                df = df[["timestamp", "value"]]
                
                metrics[metric_name] = df
            
            except Exception as e:
                logger.error(f"Error loading metric {metric_name} from CSV: {str(e)}", exc_info=True)
                metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
        
        return metrics
    
    def load_from_dict(
        self,
        metrics_data: Dict[str, List[Dict[str, Union[datetime, float]]]],
        timestamp_key: str = "timestamp",
        value_key: str = "value"
    ) -> Dict[str, pd.DataFrame]:
        """
        Load metrics from dictionary data.
        
        Args:
            metrics_data: Dictionary mapping metric names to lists of data points
            timestamp_key: Key for timestamp values in data point dictionaries
            value_key: Key for metric values in data point dictionaries
            
        Returns:
            Dictionary mapping metric names to DataFrames with timestamps and values
        """
        metrics = {}
        
        for metric_name, data_points in metrics_data.items():
            logger.info(f"Loading metric {metric_name} from dictionary data")
            
            try:
                # Convert data points to DataFrame
                df = pd.DataFrame(data_points)
                
                # Check if required columns exist
                if timestamp_key not in df.columns:
                    logger.error(f"Timestamp key '{timestamp_key}' not found in data for metric: {metric_name}")
                    metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
                    continue
                
                if value_key not in df.columns:
                    logger.error(f"Value key '{value_key}' not found in data for metric: {metric_name}")
                    metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
                    continue
                
                # Ensure timestamp is datetime
                if not pd.api.types.is_datetime64_any_dtype(df[timestamp_key]):
                    df["timestamp"] = pd.to_datetime(df[timestamp_key])
                else:
                    df["timestamp"] = df[timestamp_key]
                
                # Rename value column if needed
                if value_key != "value":
                    df["value"] = df[value_key]
                
                # Select only the required columns
                df = df[["timestamp", "value"]]
                
                metrics[metric_name] = df
            
            except Exception as e:
                logger.error(f"Error loading metric {metric_name} from dictionary: {str(e)}", exc_info=True)
                metrics[metric_name] = pd.DataFrame(columns=["timestamp", "value"])
        
        return metrics
    
    def get_baseline_metrics(
        self,
        metrics: Dict[str, pd.DataFrame],
        baseline_window: Tuple[datetime, datetime]
    ) -> Dict[str, pd.DataFrame]:
        """
        Extract baseline metrics from a given time window.
        
        Args:
            metrics: Dictionary mapping metric names to DataFrames
            baseline_window: Time window (start, end) to use as baseline
            
        Returns:
            Dictionary mapping metric names to baseline DataFrames
        """
        baseline_metrics = {}
        start_time, end_time = baseline_window
        
        for metric_name, df in metrics.items():
            try:
                # Extract data points within the baseline window
                mask = (df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)
                baseline_df = df[mask].copy()
                
                if not baseline_df.empty:
                    baseline_metrics[metric_name] = baseline_df
                else:
                    logger.warning(f"No baseline data available for metric: {metric_name}")
            
            except Exception as e:
                logger.error(f"Error creating baseline for metric {metric_name}: {str(e)}", exc_info=True)
        
        return baseline_metrics
    
    def resample_metrics(
        self,
        metrics: Dict[str, pd.DataFrame],
        interval: str = "1min",
        aggregation: str = "mean"
    ) -> Dict[str, pd.DataFrame]:
        """
        Resample metrics to a common time interval.
        
        Args:
            metrics: Dictionary mapping metric names to DataFrames
            interval: Resampling interval (e.g., "1min", "5min", "1h")
            aggregation: Aggregation method ("mean", "max", "min", "sum", etc.)
            
        Returns:
            Dictionary mapping metric names to resampled DataFrames
        """
        resampled_metrics = {}
        
        for metric_name, df in metrics.items():
            try:
                if df.empty:
                    resampled_metrics[metric_name] = df
                    continue
                
                # Set timestamp as index for resampling
                df = df.set_index("timestamp")
                
                # Resample based on the specified aggregation method
                if aggregation == "mean":
                    resampled = df.resample(interval).mean()
                elif aggregation == "max":
                    resampled = df.resample(interval).max()
                elif aggregation == "min":
                    resampled = df.resample(interval).min()
                elif aggregation == "sum":
                    resampled = df.resample(interval).sum()
                else:
                    logger.warning(f"Unsupported aggregation method: {aggregation}, using mean")
                    resampled = df.resample(interval).mean()
                
                # Reset index to have timestamp as a column again
                resampled = resampled.reset_index()
                
                resampled_metrics[metric_name] = resampled
            
            except Exception as e:
                logger.error(f"Error resampling metric {metric_name}: {str(e)}", exc_info=True)
                resampled_metrics[metric_name] = metrics[metric_name]
        
        return resampled_metrics
    
    def calculate_derived_metrics(
        self,
        metrics: Dict[str, pd.DataFrame],
        derived_metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, pd.DataFrame]:
        """
        Calculate derived metrics from existing metrics.
        
        Args:
            metrics: Dictionary mapping metric names to DataFrames
            derived_metrics: Dictionary defining derived metrics and their calculations
            
        Returns:
            Dictionary with all metrics including new derived ones
        """
        result_metrics = metrics.copy()
        
        for metric_name, config in derived_metrics.items():
            try:
                metric_type = config.get("type", "ratio")
                source_metrics = config.get("source_metrics", [])
                
                if len(source_metrics) < 1:
                    logger.warning(f"Insufficient source metrics for derived metric: {metric_name}")
                    continue
                
                # Check if all source metrics exist
                missing_metrics = [m for m in source_metrics if m not in metrics]
                if missing_metrics:
                    logger.warning(f"Missing source metrics for {metric_name}: {missing_metrics}")
                    continue
                
                # Calculate derived metric based on type
                if metric_type == "ratio" and len(source_metrics) >= 2:
                    # For ratio, we need exactly two metrics (numerator and denominator)
                    numerator = metrics[source_metrics[0]]
                    denominator = metrics[source_metrics[1]]
                    
                    # Merge the two DataFrames on timestamp
                    merged = pd.merge_asof(
                        numerator.sort_values("timestamp"),
                        denominator.sort_values("timestamp"),
                        on="timestamp",
                        suffixes=("_num", "_denom")
                    )
                    
                    # Calculate ratio, avoiding division by zero
                    merged["value"] = np.where(
                        merged["value_denom"] != 0,
                        merged["value_num"] / merged["value_denom"],
                        np.nan
                    )
                    
                    # Select only timestamp and value columns
                    result = merged[["timestamp", "value"]].copy()
                    result_metrics[metric_name] = result
                
                elif metric_type == "sum":
                    # For sum, we add multiple metrics together
                    # First, resample all metrics to a common time basis
                    resampled = self.resample_metrics(
                        {name: metrics[name] for name in source_metrics},
                        interval=config.get("interval", "1min")
                    )
                    
                    # Start with first metric
                    result = resampled[source_metrics[0]].copy()
                    
                    # Add other metrics
                    for metric in source_metrics[1:]:
                        # Merge with next metric
                        temp = pd.merge_asof(
                            result.sort_values("timestamp"),
                            resampled[metric].sort_values("timestamp"),
                            on="timestamp",
                            suffixes=("", f"_{metric}")
                        )
                        
                        # Sum the values
                        temp["value"] = temp["value"] + temp[f"value_{metric}"]
                        
                        # Select only timestamp and value
                        result = temp[["timestamp", "value"]].copy()
                    
                    result_metrics[metric_name] = result
                
                elif metric_type == "difference":
                    # For difference, we calculate metric1 - metric2
                    if len(source_metrics) >= 2:
                        metric1 = metrics[source_metrics[0]]
                        metric2 = metrics[source_metrics[1]]
                        
                        # Merge the two DataFrames on timestamp
                        merged = pd.merge_asof(
                            metric1.sort_values("timestamp"),
                            metric2.sort_values("timestamp"),
                            on="timestamp",
                            suffixes=("_1", "_2")
                        )
                        
                        # Calculate difference
                        merged["value"] = merged["value_1"] - merged["value_2"]
                        
                        # Select only timestamp and value columns
                        result = merged[["timestamp", "value"]].copy()
                        result_metrics[metric_name] = result
                
                elif metric_type == "rate":
                    # For rate, we calculate the rate of change of a metric
                    metric_df = metrics[source_metrics[0]]
                    
                    if len(metric_df) > 1:
                        # Calculate differences between consecutive values
                        metric_df = metric_df.sort_values("timestamp")
                        metric_df["prev_timestamp"] = metric_df["timestamp"].shift(1)
                        metric_df["prev_value"] = metric_df["value"].shift(1)
                        
                        # Calculate time differences in seconds
                        metric_df["time_diff"] = (metric_df["timestamp"] - metric_df["prev_timestamp"]).dt.total_seconds()
                        
                        # Calculate value differences
                        metric_df["value_diff"] = metric_df["value"] - metric_df["prev_value"]
                        
                        # Calculate rate (change per second)
                        metric_df["value"] = np.where(
                            metric_df["time_diff"] > 0,
                            metric_df["value_diff"] / metric_df["time_diff"],
                            np.nan
                        )
                        
                        # Select only timestamp and value
                        result = metric_df[["timestamp", "value"]].dropna().copy()
                        result_metrics[metric_name] = result
            
            except Exception as e:
                logger.error(f"Error calculating derived metric {metric_name}: {str(e)}", exc_info=True)
        
        return result_metrics
    
    def preprocess_metrics(
        self,
        metrics: Dict[str, pd.DataFrame],
        operations: List[Dict[str, Any]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Apply preprocessing operations to metrics data.
        
        Args:
            metrics: Dictionary mapping metric names to DataFrames
            operations: List of preprocessing operations to apply
            
        Returns:
            Dictionary with preprocessed metrics
        """
        if not operations:
            operations = [
                {"type": "remove_outliers", "method": "zscore", "threshold": 3.0},
                {"type": "interpolate_missing", "method": "linear"},
                {"type": "smooth", "window": 3, "method": "rolling_mean"}
            ]
        
        result_metrics = metrics.copy()
        
        for operation in operations:
            op_type = operation.get("type")
            
            if op_type == "remove_outliers":
                method = operation.get("method", "zscore")
                threshold = operation.get("threshold", 3.0)
                
                for metric_name, df in result_metrics.items():
                    if df.empty or len(df) < 3:
                        continue
                    
                    try:
                        if method == "zscore":
                            # Calculate z-scores
                            mean_val = df["value"].mean()
                            std_val = df["value"].std()
                            if std_val > 0:
                                z_scores = np.abs((df["value"] - mean_val) / std_val)
                                # Filter out values with high z-scores
                                df = df[z_scores <= threshold].copy()
                        
                        elif method == "iqr":
                            # Calculate IQR
                            q1 = df["value"].quantile(0.25)
                            q3 = df["value"].quantile(0.75)
                            iqr = q3 - q1
                            # Filter out values outside the range [q1-k*iqr, q3+k*iqr]
                            lower_bound = q1 - threshold * iqr
                            upper_bound = q3 + threshold * iqr
                            df = df[(df["value"] >= lower_bound) & (df["value"] <= upper_bound)].copy()
                        
                        result_metrics[metric_name] = df
                    
                    except Exception as e:
                        logger.warning(f"Error removing outliers for {metric_name}: {e}")
            
            elif op_type == "interpolate_missing":
                method = operation.get("method", "linear")
                
                for metric_name, df in result_metrics.items():
                    if df.empty or len(df) < 2:
                        continue
                    
                    try:
                        # Set timestamp as index for interpolation
                        df = df.sort_values("timestamp").set_index("timestamp")
                        # Interpolate missing values
                        df["value"] = df["value"].interpolate(method=method)
                        # Reset index
                        df = df.reset_index()
                        result_metrics[metric_name] = df
                    
                    except Exception as e:
                        logger.warning(f"Error interpolating missing values for {metric_name}: {e}")
            
            elif op_type == "smooth":
                window = operation.get("window", 3)
                method = operation.get("method", "rolling_mean")
                
                for metric_name, df in result_metrics.items():
                    if df.empty or len(df) < window:
                        continue
                    
                    try:
                        if method == "rolling_mean":
                            # Apply rolling mean
                            df = df.sort_values("timestamp")
                            rolling = df["value"].rolling(window=window, center=True).mean()
                            df["value"] = rolling.fillna(df["value"])
                        
                        elif method == "exponential":
                            # Apply exponential smoothing
                            alpha = operation.get("alpha", 0.3)
                            df = df.sort_values("timestamp")
                            df["value"] = df["value"].ewm(alpha=alpha).mean()
                        
                        result_metrics[metric_name] = df
                    
                    except Exception as e:
                        logger.warning(f"Error smoothing values for {metric_name}: {e}")
        
        return result_metrics
    
    def cache_metrics(self, metrics: Dict[str, pd.DataFrame], cache_id: str) -> bool:
        """
        Cache metrics data to disk for later use.
        
        Args:
            metrics: Dictionary mapping metric names to DataFrames
            cache_id: Unique identifier for the cache
            
        Returns:
            True if caching was successful, False otherwise
        """
        try:
            cache_path = os.path.join(self.cache_dir, f"{cache_id}.h5")
            store = pd.HDFStore(cache_path, mode="w")
            
            for metric_name, df in metrics.items():
                # Use a sanitized metric name as the key
                key = f"metrics/{metric_name.replace('.', '_')}"
                store.put(key, df)
            
            store.close()
            return True
        
        except Exception as e:
            logger.error(f"Error caching metrics: {e}", exc_info=True)
            return False
    
    def load_cached_metrics(self, cache_id: str) -> Dict[str, pd.DataFrame]:
        """
        Load metrics data from cache.
        
        Args:
            cache_id: Unique identifier for the cache
            
        Returns:
            Dictionary mapping metric names to DataFrames
        """
        metrics = {}
        
        try:
            cache_path = os.path.join(self.cache_dir, f"{cache_id}.h5")
            
            if not os.path.exists(cache_path):
                logger.warning(f"Cache file not found: {cache_path}")
                return metrics
            
            store = pd.HDFStore(cache_path, mode="r")
            
            # Get all keys in the store
            keys = store.keys()
            
            for key in keys:
                # Extract metric name from key
                metric_name = key.split("/")[-1].replace("_", ".", 1)
                
                # Load DataFrame
                df = store.get(key)
                metrics[metric_name] = df
            
            store.close()
            return metrics
        
        except Exception as e:
            logger.error(f"Error loading cached metrics: {e}", exc_info=True)
            return metrics 