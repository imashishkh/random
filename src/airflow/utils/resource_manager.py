"""
Resource Manager for Airflow DAGs

This module provides utilities for resource tracking, temporary file management,
and resource usage monitoring for Airflow DAGs. It helps ensure proper cleanup
of resources and provides metrics for monitoring resource usage.
"""

import os
import shutil
import logging
import time
import psutil
import gc
from typing import Dict, List, Set, Any, Optional, Union, Callable, ContextManager
from contextlib import contextmanager
import threading
from datetime import datetime, timedelta
import json
import tempfile

# Set up logging
logger = logging.getLogger(__name__)


class TempFileRegistry:
    """
    Registry for tracking temporary files created during DAG execution.
    
    This registry keeps track of all temporary files created during DAG execution
    and provides utilities for cleaning them up, even in case of task failures.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'TempFileRegistry':
        """
        Get singleton instance of TempFileRegistry.
        
        Returns:
            TempFileRegistry: Singleton instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize the registry."""
        self._registry: Dict[str, Set[str]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
    
    def register_file(self, file_path: str, task_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Register a temporary file with the registry.
        
        Args:
            file_path: Path to the temporary file
            task_id: ID of the task that created the file
            metadata: Optional metadata about the file
            
        Returns:
            str: Registered file path
        """
        abs_path = os.path.abspath(file_path)
        
        if task_id not in self._registry:
            self._registry[task_id] = set()
        
        self._registry[task_id].add(abs_path)
        
        if metadata:
            if abs_path not in self._metadata:
                self._metadata[abs_path] = {}
            self._metadata[abs_path].update(metadata)
        
        logger.debug(f"Registered temporary file: {abs_path} for task: {task_id}")
        return abs_path
    
    def get_files_for_task(self, task_id: str) -> List[str]:
        """
        Get all temporary files registered for a task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List[str]: List of file paths
        """
        return list(self._registry.get(task_id, set()))
    
    def get_all_files(self) -> List[str]:
        """
        Get all registered temporary files.
        
        Returns:
            List[str]: List of all registered file paths
        """
        all_files = set()
        for files in self._registry.values():
            all_files.update(files)
        return list(all_files)
    
    def remove_file(self, file_path: str) -> bool:
        """
        Remove a file from the filesystem and registry.
        
        Args:
            file_path: Path to the file to remove
            
        Returns:
            bool: True if the file was successfully removed, False otherwise
        """
        abs_path = os.path.abspath(file_path)
        
        try:
            if os.path.exists(abs_path):
                if os.path.isdir(abs_path):
                    shutil.rmtree(abs_path)
                else:
                    os.remove(abs_path)
                
                # Remove from registry
                for task_id, files in self._registry.items():
                    if abs_path in files:
                        files.remove(abs_path)
                
                # Remove metadata
                if abs_path in self._metadata:
                    del self._metadata[abs_path]
                
                logger.debug(f"Removed temporary file: {abs_path}")
                return True
            else:
                logger.debug(f"File {abs_path} does not exist, skipping removal")
                return True
        except Exception as e:
            logger.error(f"Error removing file {abs_path}: {str(e)}")
            return False
    
    def cleanup_task(self, task_id: str) -> Dict[str, Any]:
        """
        Clean up all temporary files for a specific task.
        
        Args:
            task_id: ID of the task to clean up files for
            
        Returns:
            Dict[str, Any]: Cleanup results
        """
        if task_id not in self._registry:
            return {"cleaned": 0, "failed": 0, "task_id": task_id}
        
        files = self.get_files_for_task(task_id)
        cleaned = 0
        failed = 0
        
        for file_path in files:
            if self.remove_file(file_path):
                cleaned += 1
            else:
                failed += 1
        
        logger.info(f"Cleaned up {cleaned} files for task {task_id} ({failed} failed)")
        return {"cleaned": cleaned, "failed": failed, "task_id": task_id}
    
    def cleanup_all(self) -> Dict[str, Any]:
        """
        Clean up all registered temporary files.
        
        Returns:
            Dict[str, Any]: Cleanup results by task
        """
        results = {}
        
        for task_id in self._registry.keys():
            results[task_id] = self.cleanup_task(task_id)
        
        return results


@contextmanager
def temp_file_manager(prefix: str, suffix: str = "", task_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Context manager for creating and tracking temporary files.
    
    Args:
        prefix: Prefix for the temporary file name
        suffix: Suffix for the temporary file name
        task_id: ID of the task creating the file
        metadata: Optional metadata about the file
        
    Yields:
        str: Path to the temporary file
    """
    fd, file_path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
    os.close(fd)
    
    registry = TempFileRegistry.get_instance()
    
    try:
        if task_id:
            registry.register_file(file_path, task_id, metadata)
        
        yield file_path
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Removed temporary file: {file_path}")
            except Exception as e:
                logger.error(f"Error removing temporary file {file_path}: {str(e)}")


class ResourceMonitor:
    """
    Monitor resource usage for tasks and DAGs.
    
    This class provides utilities for tracking resource usage (CPU, memory, disk)
    during task execution and reporting metrics.
    """
    
    def __init__(self):
        """Initialize the resource monitor."""
        self.start_time = None
        self.end_time = None
        self.metrics = {}
    
    def start_monitoring(self):
        """Start monitoring resources."""
        self.start_time = time.time()
        self.metrics = {
            "start_time": self.start_time,
            "start_memory": self._get_memory_usage(),
            "start_cpu": self._get_cpu_usage()
        }
    
    def end_monitoring(self) -> Dict[str, Any]:
        """
        End monitoring and return metrics.
        
        Returns:
            Dict[str, Any]: Resource usage metrics
        """
        self.end_time = time.time()
        self.metrics.update({
            "end_time": self.end_time,
            "end_memory": self._get_memory_usage(),
            "end_cpu": self._get_cpu_usage(),
            "duration": self.end_time - self.start_time,
            "memory_diff": self._get_memory_usage() - self.metrics.get("start_memory", 0)
        })
        return self.metrics
    
    def _get_memory_usage(self) -> float:
        """
        Get current memory usage in MB.
        
        Returns:
            float: Memory usage in MB
        """
        try:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            return mem_info.rss / (1024 * 1024)  # Convert to MB
        except Exception as e:
            logger.error(f"Error getting memory usage: {str(e)}")
            return 0.0
    
    def _get_cpu_usage(self) -> float:
        """
        Get current CPU usage as a percentage.
        
        Returns:
            float: CPU usage as a percentage
        """
        try:
            process = psutil.Process(os.getpid())
            return process.cpu_percent(interval=0.1)
        except Exception as e:
            logger.error(f"Error getting CPU usage: {str(e)}")
            return 0.0
    
    def get_disk_usage(self, path: str = "/tmp") -> Dict[str, float]:
        """
        Get disk usage for a specific path.
        
        Args:
            path: Path to check disk usage for
            
        Returns:
            Dict[str, float]: Disk usage statistics
        """
        try:
            disk_usage = shutil.disk_usage(path)
            return {
                "total_gb": disk_usage.total / (1024 * 1024 * 1024),
                "used_gb": disk_usage.used / (1024 * 1024 * 1024),
                "free_gb": disk_usage.free / (1024 * 1024 * 1024),
                "percent_used": disk_usage.used / disk_usage.total * 100
            }
        except Exception as e:
            logger.error(f"Error getting disk usage for {path}: {str(e)}")
            return {
                "total_gb": 0.0,
                "used_gb": 0.0,
                "free_gb": 0.0,
                "percent_used": 0.0,
                "error": str(e)
            }


@contextmanager
def monitored_execution(task_id: str, **kwargs) -> Dict[str, Any]:
    """
    Context manager for monitoring resource usage during task execution.
    
    Args:
        task_id: ID of the task to monitor
        **kwargs: Additional metadata
        
    Yields:
        Dict[str, Any]: Resource monitor metrics dictionary
    """
    monitor = ResourceMonitor()
    metrics = {"task_id": task_id}
    metrics.update(kwargs)
    
    try:
        monitor.start_monitoring()
        metrics.update({"start_time": datetime.now().isoformat()})
        
        # Create a metrics dictionary that the task can update
        yield metrics
        
    finally:
        end_metrics = monitor.end_monitoring()
        metrics.update(end_metrics)
        metrics.update({"end_time": datetime.now().isoformat()})
        
        # Log detailed metrics
        logger.info(f"Task {task_id} resource usage: "
                    f"Duration={metrics.get('duration', 0):.2f}s, "
                    f"Memory={metrics.get('memory_diff', 0):.2f}MB, "
                    f"CPU={metrics.get('end_cpu', 0):.2f}%")


def cleanup_temporary_files(task_outputs: Dict[str, Any], task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Clean up temporary files from task outputs.
    
    Args:
        task_outputs: Dictionary of task outputs that may contain file paths
        task_id: Specific task ID to clean up files for
        
    Returns:
        Dict[str, Any]: Cleanup results
    """
    registry = TempFileRegistry.get_instance()
    
    if task_id:
        return registry.cleanup_task(task_id)
    else:
        return registry.cleanup_all()


def collect_temp_paths(outputs: Dict[str, Any]) -> List[str]:
    """
    Collect temporary file paths from task outputs recursively.
    
    Args:
        outputs: Dictionary of task outputs
        
    Returns:
        List[str]: List of temporary file paths
    """
    temp_paths = []
    
    def extract_paths(obj):
        if isinstance(obj, dict):
            # Check if dict has a file_path key
            if 'file_path' in obj and isinstance(obj['file_path'], str):
                temp_paths.append(obj['file_path'])
            
            # Process all values recursively
            for value in obj.values():
                extract_paths(value)
        elif isinstance(obj, list):
            # Process all items in the list
            for item in obj:
                extract_paths(item)
    
    extract_paths(outputs)
    return temp_paths


def log_dag_metrics(metrics: Dict[str, Any], dag_id: str) -> None:
    """
    Log DAG execution metrics to a file for later analysis.
    
    Args:
        metrics: Dictionary of metrics to log
        dag_id: ID of the DAG
    """
    log_dir = f"/opt/airflow/logs/metrics/{dag_id}"
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{log_dir}/metrics_{timestamp}.json"
    
    # Add timestamp to metrics
    metrics['timestamp'] = timestamp
    metrics['dag_id'] = dag_id
    
    try:
        with open(log_file, 'w') as f:
            json.dump(metrics, f, indent=2)
        logger.info(f"Logged DAG metrics to {log_file}")
    except Exception as e:
        logger.error(f"Error logging DAG metrics: {str(e)}")


def get_threshold(metric_name: str, default_value: Optional[float] = None) -> float:
    """
    Get threshold value for a metric from Airflow variables.
    
    Args:
        metric_name: Name of the metric to get threshold for
        default_value: Default value if threshold is not defined
        
    Returns:
        float: Threshold value
    """
    try:
        from airflow.models import Variable
        
        # Try to get thresholds from Airflow variables
        threshold_key = f"threshold_{metric_name}"
        threshold = Variable.get(threshold_key, default_value=default_value)
        
        if threshold is not None and not isinstance(threshold, (int, float)):
            try:
                threshold = float(threshold)
            except (ValueError, TypeError):
                logger.warning(f"Invalid threshold value for {metric_name}: {threshold}")
                threshold = default_value
        
        return threshold
    except Exception as e:
        logger.error(f"Error getting threshold for {metric_name}: {str(e)}")
        return default_value if default_value is not None else 0.0


def get_memory_usage() -> float:
    """
    Get current memory usage in MB.
    
    Returns:
        float: Memory usage in MB
    """
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        return mem_info.rss / (1024 * 1024)  # Convert to MB
    except Exception as e:
        logger.error(f"Error getting memory usage: {str(e)}")
        return 0.0


def collect_resource_stats() -> Dict[str, Any]:
    """
    Collect system resource statistics.
    
    Returns:
        Dict[str, Any]: Resource statistics
    """
    try:
        stats = {
            "memory": {
                "total_mb": psutil.virtual_memory().total / (1024 * 1024),
                "available_mb": psutil.virtual_memory().available / (1024 * 1024),
                "used_mb": psutil.virtual_memory().used / (1024 * 1024),
                "percent": psutil.virtual_memory().percent
            },
            "cpu": {
                "percent": psutil.cpu_percent(interval=0.5),
                "count": psutil.cpu_count()
            },
            "disk": {}
        }
        
        # Add disk usage for common paths
        for path in ["/", "/tmp", "/opt/airflow"]:
            if os.path.exists(path):
                usage = shutil.disk_usage(path)
                stats["disk"][path] = {
                    "total_gb": usage.total / (1024 * 1024 * 1024),
                    "used_gb": usage.used / (1024 * 1024 * 1024),
                    "free_gb": usage.free / (1024 * 1024 * 1024),
                    "percent": usage.used / usage.total * 100
                }
        
        return stats
    except Exception as e:
        logger.error(f"Error collecting resource stats: {str(e)}")
        return {"error": str(e)}


def force_garbage_collection() -> int:
    """
    Force garbage collection to free memory.
    
    Returns:
        int: Number of objects collected
    """
    try:
        gc.collect()
        return gc.collect()  # Run twice to ensure collection of newly freed objects
    except Exception as e:
        logger.error(f"Error during garbage collection: {str(e)}")
        return 0 