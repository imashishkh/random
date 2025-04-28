"""
Celery worker configuration for the Forex Trading AI System.
"""
import os
import logging
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Create Celery app
celery = Celery(
    "forex_trading",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["src.worker.tasks"]
)

# Configure Celery
celery.conf.update(
    result_expires=3600,  # 1 hour
    worker_concurrency=int(os.getenv("CELERY_WORKERS", "4")),
    worker_prefetch_multiplier=int(os.getenv("CELERY_PREFETCH", "4")),
    task_acks_late=True,
    task_time_limit=int(os.getenv("CELERY_TASK_TIMEOUT", "300")),  # 5 minutes
    task_soft_time_limit=int(os.getenv("CELERY_TASK_SOFT_TIMEOUT", "240")),  # 4 minutes
    worker_max_tasks_per_child=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "100")),
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Scheduled tasks
celery.conf.beat_schedule = {
    "market-data-collection": {
        "task": "src.worker.tasks.collect_market_data",
        "schedule": int(os.getenv("SCHEDULE_MARKET_DATA", "300")),  # 5 minutes
        "args": (),
    },
    "balance-update": {
        "task": "src.worker.tasks.update_account_balances",
        "schedule": int(os.getenv("SCHEDULE_BALANCE_UPDATE", "900")),  # 15 minutes
        "args": (),
    },
    "daily-system-health-check": {
        "task": "src.worker.tasks.system_health_check",
        "schedule": crontab(hour=0, minute=0),  # Daily at midnight
        "args": (),
    },
    "position-update": {
        "task": "src.worker.tasks.update_positions",
        "schedule": int(os.getenv("SCHEDULE_POSITION_UPDATE", "60")),  # 1 minute
        "args": (),
    },
    "trading-signal-generation": {
        "task": "src.worker.tasks.generate_trading_signals",
        "schedule": int(os.getenv("SCHEDULE_SIGNAL_GENERATION", "600")),  # 10 minutes
        "args": (),
    },
}

if __name__ == "__main__":
    celery.start() 