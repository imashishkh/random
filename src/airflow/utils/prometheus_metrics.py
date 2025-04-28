"""
Prometheus Metrics for Airflow

This module provides utilities for collecting and exporting Prometheus metrics
from Airflow DAGs and tasks. It integrates with the Prometheus Python client
to expose custom metrics for monitoring task execution, resource usage, and
system health.
"""

import time
import os
import logging
from typing import Dict, List, Any, Optional, Union, Callable
from functools import wraps
from contextlib import contextmanager
from enum import Enum
from prometheus_client import Counter, Gauge, Histogram, Summary, CollectorRegistry, push_to_gateway, generate_latest

# Set up logging
logger = logging.getLogger(__name__)

# Default Prometheus gateway configuration
DEFAULT_PROMETHEUS_GATEWAY = os.environ.get("PROMETHEUS_PUSHGATEWAY", "localhost:9091")

# Registry for metrics
registry = CollectorRegistry()


class MetricType(Enum):
    """Enum for different types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


# Define default metrics
task_execution_time = Histogram(
    'airflow_task_execution_seconds',
    'Time spent executing task',
    ['dag_id', 'task_id', 'task_type'],
    registry=registry
)

task_success_counter = Counter(
    'airflow_task_success_total',
    'Number of successful task executions',
    ['dag_id', 'task_id', 'task_type'],
    registry=registry
)

task_failure_counter = Counter(
    'airflow_task_failure_total',
    'Number of failed task executions',
    ['dag_id', 'task_id', 'task_type'],
    registry=registry
)

task_retry_counter = Counter(
    'airflow_task_retry_total',
    'Number of retried task executions',
    ['dag_id', 'task_id', 'task_type'],
    registry=registry
)

memory_usage_gauge = Gauge(
    'airflow_task_memory_usage_mb',
    'Memory usage of task execution in MB',
    ['dag_id', 'task_id'],
    registry=registry
)

cpu_usage_gauge = Gauge(
    'airflow_task_cpu_usage_percent',
    'CPU usage of task execution as percentage',
    ['dag_id', 'task_id'],
    registry=registry
)

disk_usage_gauge = Gauge(
    'airflow_task_disk_usage_gb',
    'Disk usage of task execution in GB',
    ['dag_id', 'task_id', 'path'],
    registry=registry
)

dag_execution_time = Histogram(
    'airflow_dag_execution_seconds',
    'Time spent executing DAG',
    ['dag_id'],
    registry=registry
)

dag_success_counter = Counter(
    'airflow_dag_success_total',
    'Number of successful DAG executions',
    ['dag_id'],
    registry=registry
)

dag_failure_counter = Counter(
    'airflow_dag_failure_total',
    'Number of failed DAG executions',
    ['dag_id'],
    registry=registry
)

# Model training specific metrics
model_training_time = Histogram(
    'airflow_model_training_seconds',
    'Time spent training model',
    ['dag_id', 'task_id', 'model_type', 'dataset_size'],
    registry=registry
)

model_accuracy_gauge = Gauge(
    'airflow_model_accuracy',
    'Model accuracy metric',
    ['dag_id', 'task_id', 'model_type', 'metric_name'],
    registry=registry
)

model_error_gauge = Gauge(
    'airflow_model_error',
    'Model error metric',
    ['dag_id', 'task_id', 'model_type', 'metric_name'],
    registry=registry
)

# Temporary file metrics
temp_files_created_counter = Counter(
    'airflow_temp_files_created_total',
    'Number of temporary files created',
    ['dag_id', 'task_id'],
    registry=registry
)

temp_files_cleaned_counter = Counter(
    'airflow_temp_files_cleaned_total',
    'Number of temporary files cleaned up',
    ['dag_id', 'task_id'],
    registry=registry
)

temp_files_size_gauge = Gauge(
    'airflow_temp_files_size_mb',
    'Size of temporary files in MB',
    ['dag_id', 'task_id'],
    registry=registry
)


def push_metrics(job_name: str, gateway: Optional[str] = None) -> None:
    """
    Push metrics to Prometheus Pushgateway.
    
    Args:
        job_name: Name of the job pushing metrics
        gateway: Address of the Prometheus Pushgateway
    """
    if gateway is None:
        gateway = DEFAULT_PROMETHEUS_GATEWAY
    
    try:
        push_to_gateway(gateway, job=job_name, registry=registry)
        logger.info(f"Pushed metrics to gateway: {gateway}")
    except Exception as e:
        logger.error(f"Error pushing metrics to gateway: {str(e)}")


def record_custom_metric(
    metric_type: MetricType,
    name: str,
    description: str,
    value: Union[int, float],
    labels: Dict[str, str] = None,
    buckets: Optional[List[float]] = None
) -> None:
    """
    Record a custom metric.
    
    Args:
        metric_type: Type of metric (counter, gauge, histogram, summary)
        name: Name of the metric
        description: Description of the metric
        value: Value to record
        labels: Labels for the metric
        buckets: Buckets for histogram metrics
    """
    if labels is None:
        labels = {}
    
    try:
        metric_name = f"airflow_{name}"
        
        # Create or get the metric
        if metric_type == MetricType.COUNTER:
            metric = Counter(metric_name, description, labels.keys(), registry=registry)
            metric.labels(**labels).inc(value)
        elif metric_type == MetricType.GAUGE:
            metric = Gauge(metric_name, description, labels.keys(), registry=registry)
            metric.labels(**labels).set(value)
        elif metric_type == MetricType.HISTOGRAM:
            if buckets is None:
                buckets = [0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
            metric = Histogram(metric_name, description, labels.keys(), buckets=buckets, registry=registry)
            metric.labels(**labels).observe(value)
        elif metric_type == MetricType.SUMMARY:
            metric = Summary(metric_name, description, labels.keys(), registry=registry)
            metric.labels(**labels).observe(value)
        else:
            logger.error(f"Unknown metric type: {metric_type}")
            return
        
        logger.debug(f"Recorded {metric_type.value} metric: {name}={value}, labels={labels}")
    except Exception as e:
        logger.error(f"Error recording metric {name}: {str(e)}")


@contextmanager
def monitor_task_execution(
    dag_id: str, 
    task_id: str, 
    task_type: str
) -> None:
    """
    Context manager for monitoring task execution and recording metrics.
    
    Args:
        dag_id: ID of the DAG
        task_id: ID of the task
        task_type: Type of the task
        
    Yields:
        None
    """
    start_time = time.time()
    success = False
    
    try:
        yield
        success = True
    except Exception as e:
        task_failure_counter.labels(dag_id=dag_id, task_id=task_id, task_type=task_type).inc()
        raise e
    finally:
        execution_time = time.time() - start_time
        task_execution_time.labels(dag_id=dag_id, task_id=task_id, task_type=task_type).observe(execution_time)
        
        if success:
            task_success_counter.labels(dag_id=dag_id, task_id=task_id, task_type=task_type).inc()


def task_monitor(task_type: Optional[str] = None) -> Callable:
    """
    Decorator for monitoring task execution and recording metrics.
    
    Args:
        task_type: Type of the task
        
    Returns:
        Callable: Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Extract DAG ID and task ID from context
            context = kwargs.get('context', {})
            dag_id = context.get('dag').dag_id if context.get('dag') else 'unknown_dag'
            task_id = context.get('task').task_id if context.get('task') else 'unknown_task'
            task_type_value = task_type or func.__name__
            
            with monitor_task_execution(dag_id, task_id, task_type_value):
                return func(*args, **kwargs)
                
        return wrapper
    return decorator


@contextmanager
def monitor_dag_execution(dag_id: str) -> None:
    """
    Context manager for monitoring DAG execution and recording metrics.
    
    Args:
        dag_id: ID of the DAG
        
    Yields:
        None
    """
    start_time = time.time()
    success = False
    
    try:
        yield
        success = True
    except Exception as e:
        dag_failure_counter.labels(dag_id=dag_id).inc()
        raise e
    finally:
        execution_time = time.time() - start_time
        dag_execution_time.labels(dag_id=dag_id).observe(execution_time)
        
        if success:
            dag_success_counter.labels(dag_id=dag_id).inc()


def record_resource_usage(
    dag_id: str, 
    task_id: str, 
    memory_mb: float, 
    cpu_percent: float, 
    disk_usage: Dict[str, Dict[str, float]] = None
) -> None:
    """
    Record resource usage metrics.
    
    Args:
        dag_id: ID of the DAG
        task_id: ID of the task
        memory_mb: Memory usage in MB
        cpu_percent: CPU usage as percentage
        disk_usage: Disk usage by path
    """
    try:
        memory_usage_gauge.labels(dag_id=dag_id, task_id=task_id).set(memory_mb)
        cpu_usage_gauge.labels(dag_id=dag_id, task_id=task_id).set(cpu_percent)
        
        if disk_usage:
            for path, usage in disk_usage.items():
                disk_usage_gauge.labels(dag_id=dag_id, task_id=task_id, path=path).set(usage.get('used_gb', 0))
                
        logger.debug(f"Recorded resource usage for {dag_id}/{task_id}: memory={memory_mb}MB, cpu={cpu_percent}%")
    except Exception as e:
        logger.error(f"Error recording resource usage: {str(e)}")


def record_model_metrics(
    dag_id: str,
    task_id: str,
    model_type: str,
    dataset_size: Union[int, str],
    metrics: Dict[str, float],
    training_time: float
) -> None:
    """
    Record model training and evaluation metrics.
    
    Args:
        dag_id: ID of the DAG
        task_id: ID of the task
        model_type: Type of the model
        dataset_size: Size of the training dataset
        metrics: Dictionary of metric name to value
        training_time: Time spent training the model
    """
    try:
        # Convert dataset_size to string if it's an integer
        dataset_size_str = str(dataset_size)
        
        # Record training time
        model_training_time.labels(
            dag_id=dag_id,
            task_id=task_id,
            model_type=model_type,
            dataset_size=dataset_size_str
        ).observe(training_time)
        
        # Record metrics
        for metric_name, value in metrics.items():
            if 'error' in metric_name.lower() or 'loss' in metric_name.lower():
                model_error_gauge.labels(
                    dag_id=dag_id,
                    task_id=task_id,
                    model_type=model_type,
                    metric_name=metric_name
                ).set(value)
            else:
                model_accuracy_gauge.labels(
                    dag_id=dag_id,
                    task_id=task_id,
                    model_type=model_type,
                    metric_name=metric_name
                ).set(value)
        
        logger.debug(f"Recorded model metrics for {model_type} model in {dag_id}/{task_id}")
    except Exception as e:
        logger.error(f"Error recording model metrics: {str(e)}")


def record_temp_file_metrics(
    dag_id: str,
    task_id: str,
    files_created: int,
    files_cleaned: int,
    files_size_mb: float
) -> None:
    """
    Record temporary file metrics.
    
    Args:
        dag_id: ID of the DAG
        task_id: ID of the task
        files_created: Number of temporary files created
        files_cleaned: Number of temporary files cleaned up
        files_size_mb: Size of temporary files in MB
    """
    try:
        temp_files_created_counter.labels(dag_id=dag_id, task_id=task_id).inc(files_created)
        temp_files_cleaned_counter.labels(dag_id=dag_id, task_id=task_id).inc(files_cleaned)
        temp_files_size_gauge.labels(dag_id=dag_id, task_id=task_id).set(files_size_mb)
        
        logger.debug(f"Recorded temp file metrics for {dag_id}/{task_id}: created={files_created}, cleaned={files_cleaned}, size={files_size_mb}MB")
    except Exception as e:
        logger.error(f"Error recording temp file metrics: {str(e)}")


def check_metric_thresholds(
    dag_id: str,
    task_id: str,
    metrics: Dict[str, float],
    thresholds: Dict[str, float]
) -> Dict[str, Any]:
    """
    Check if metrics exceed thresholds.
    
    Args:
        dag_id: ID of the DAG
        task_id: ID of the task
        metrics: Dictionary of metric name to value
        thresholds: Dictionary of metric name to threshold value
        
    Returns:
        Dict[str, Any]: Dictionary of threshold violations
    """
    violations = {}
    
    try:
        for metric_name, value in metrics.items():
            if metric_name in thresholds and value > thresholds[metric_name]:
                violations[metric_name] = {
                    "value": value,
                    "threshold": thresholds[metric_name],
                    "exceeded_by": value - thresholds[metric_name]
                }
                
                # Record as a metric
                record_custom_metric(
                    MetricType.GAUGE,
                    f"threshold_violation_{metric_name}",
                    f"Threshold violation for {metric_name}",
                    value,
                    labels={
                        "dag_id": dag_id,
                        "task_id": task_id,
                        "threshold": str(thresholds[metric_name])
                    }
                )
        
        if violations:
            logger.warning(f"Threshold violations for {dag_id}/{task_id}: {violations}")
        
        return violations
    except Exception as e:
        logger.error(f"Error checking metric thresholds: {str(e)}")
        return {"error": str(e)}


def retry_with_exponential_backoff(
    func: Callable,
    retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    dag_id: str = "unknown_dag",
    task_id: str = "unknown_task"
) -> Callable:
    """
    Decorator for retrying a function with exponential backoff.
    
    Args:
        func: Function to retry
        retries: Maximum number of retries
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        dag_id: ID of the DAG
        task_id: ID of the task
        
    Returns:
        Callable: Decorated function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extract DAG ID and task ID from context if available
        context = kwargs.get('context', {})
        dag_id_value = context.get('dag').dag_id if context.get('dag') else dag_id
        task_id_value = context.get('task').task_id if context.get('task') else task_id
        
        attempt = 0
        last_exception = None
        
        while attempt <= retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                attempt += 1
                last_exception = e
                
                if attempt <= retries:
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    
                    # Record retry metric
                    task_retry_counter.labels(
                        dag_id=dag_id_value,
                        task_id=task_id_value,
                        task_type=func.__name__
                    ).inc()
                    
                    logger.warning(
                        f"Retry {attempt}/{retries} for {dag_id_value}/{task_id_value} "
                        f"after error: {str(e)}. Retrying in {delay:.2f}s."
                    )
                    
                    time.sleep(delay)
                else:
                    # Record failure metric
                    task_failure_counter.labels(
                        dag_id=dag_id_value,
                        task_id=task_id_value,
                        task_type=func.__name__
                    ).inc()
                    
                    logger.error(
                        f"Failed after {retries} retries for {dag_id_value}/{task_id_value}: {str(e)}"
                    )
                    
                    raise last_exception
        
        # Should never reach here, but just in case
        raise last_exception if last_exception else RuntimeError("Unknown error in retry logic")
    
    return wrapper 