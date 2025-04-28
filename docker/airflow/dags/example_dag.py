"""
Example DAG for FX-Swarm
This DAG demonstrates basic Airflow functionality and connectivity to other services.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.redis.operators.redis_publish import RedisPublishOperator

# Default arguments for DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=10),
}

# Instantiate the DAG
dag = DAG(
    'fx_swarm_health_check',
    default_args=default_args,
    description='A DAG to verify connectivity to FX-Swarm services',
    schedule_interval=timedelta(hours=1),
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['example', 'health_check'],
)

# Function to check Redis connectivity
def check_redis_connection(**kwargs):
    """Check Redis connectivity by importing the Redis client and connecting"""
    import redis
    from airflow.models import Variable
    
    redis_url = Variable.get('REDIS_URL', 'redis://redis:6379/0')
    
    r = redis.from_url(redis_url)
    ping_result = r.ping()
    
    if not ping_result:
        raise Exception("Failed to connect to Redis")
    
    return "Redis connection successful"

# Function to log a message
def log_task_completion(**kwargs):
    """Log a simple message to verify task execution"""
    return "Task completed successfully at {}".format(datetime.now())

# Define DAG tasks

# Task to check PostgreSQL connectivity
postgres_check = PostgresOperator(
    task_id='check_postgres',
    postgres_conn_id='postgres_default',
    sql="SELECT 1 AS health_check;",
    dag=dag,
)

# Task to check Redis connectivity
redis_check = PythonOperator(
    task_id='check_redis',
    python_callable=check_redis_connection,
    dag=dag,
)

# Task to publish a test message to Redis
redis_publish = RedisPublishOperator(
    task_id='publish_to_redis',
    redis_conn_id='redis_default',
    channel='fx_swarm_health',
    message='Airflow health check: {{ ts }}',
    dag=dag,
)

# Final task to log completion
completion_task = PythonOperator(
    task_id='log_completion',
    python_callable=log_task_completion,
    dag=dag,
)

# Define the task dependencies
postgres_check >> redis_check >> redis_publish >> completion_task 