"""
Celery tasks for the deposit monitoring system.

This module defines Celery tasks for monitoring deposits on the BSC blockchain
and processing transaction confirmations.
"""
import os
import time
import logging
from datetime import timedelta
from typing import Dict, List, Optional

from celery import shared_task, Task
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from dotenv import load_dotenv

from ..account.deposit_monitor import (
    monitor_blockchain, 
    process_transaction_confirmations,
    reconcile_balances,
    load_deposit_addresses
)
from ..account.wallet import (
    BSC_MAINNET_CHAIN_ID, 
    BSC_TESTNET_CHAIN_ID
)

# Load environment variables
load_dotenv()

# Configure logging
logger = get_task_logger(__name__)

# Constants
POLLING_INTERVAL = int(os.getenv("BSC_POLLING_INTERVAL", "15"))
USE_TESTNET = os.getenv("USE_TESTNET", "false").lower() == "true"
CHAIN_ID = BSC_TESTNET_CHAIN_ID if USE_TESTNET else BSC_MAINNET_CHAIN_ID

# Store the last processed block
last_processed_block = None

# Setup Celery beat schedule
beat_schedule = {
    'monitor-deposits': {
        'task': 'src.worker.celery_tasks.monitor_deposits',
        'schedule': timedelta(seconds=POLLING_INTERVAL),
        'args': (CHAIN_ID,),
    },
    'process-confirmations': {
        'task': 'src.worker.celery_tasks.process_confirmations',
        'schedule': timedelta(seconds=POLLING_INTERVAL),
        'args': (CHAIN_ID,),
    },
    'reconcile-balances': {
        'task': 'src.worker.celery_tasks.reconcile_balances',
        'schedule': crontab(minute='0', hour='*/6'),  # Every 6 hours
        'args': (CHAIN_ID,),
    },
    'refresh-address-cache': {
        'task': 'src.worker.celery_tasks.refresh_address_cache',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
}


class MonitoringTask(Task):
    """Base task class for monitoring tasks."""
    
    _deposit_addresses = None
    
    @property
    def deposit_addresses(self) -> Dict[str, int]:
        """
        Lazy-loaded deposit addresses cache.
        
        Returns:
            Dictionary mapping addresses to wallet IDs
        """
        if self._deposit_addresses is None:
            self._deposit_addresses = load_deposit_addresses()
        return self._deposit_addresses
    
    def refresh_addresses(self) -> None:
        """Refresh the deposit addresses cache."""
        self._deposit_addresses = load_deposit_addresses()


@shared_task(base=MonitoringTask, bind=True)
def monitor_deposits(self, chain_id: int = CHAIN_ID) -> Dict[str, int]:
    """
    Task to monitor blockchain for new deposits.
    
    Args:
        chain_id: The blockchain chain ID
        
    Returns:
        Dictionary with last_block and tx_count
    """
    global last_processed_block
    
    try:
        logger.info(f"Running deposit monitor for chain ID {chain_id}")
        
        # Monitor blockchain for new transactions
        last_block, tx_count = monitor_blockchain(chain_id, last_processed_block)
        
        # Update the global variable
        last_processed_block = last_block
        
        if tx_count > 0:
            logger.info(f"Detected {tx_count} new deposits")
        
        return {'last_block': last_block, 'tx_count': tx_count}
    
    except Exception as e:
        logger.error(f"Error in monitor_deposits task: {e}")
        raise


@shared_task(base=MonitoringTask, bind=True)
def process_confirmations(self, chain_id: int = CHAIN_ID) -> int:
    """
    Task to process transaction confirmations.
    
    Args:
        chain_id: The blockchain chain ID
        
    Returns:
        Number of confirmed transactions
    """
    try:
        logger.info(f"Processing transaction confirmations for chain ID {chain_id}")
        
        # Process transaction confirmations
        confirmed_count = process_transaction_confirmations(chain_id)
        
        if confirmed_count > 0:
            logger.info(f"Confirmed {confirmed_count} deposits")
        
        return confirmed_count
    
    except Exception as e:
        logger.error(f"Error in process_confirmations task: {e}")
        raise


@shared_task(base=MonitoringTask, bind=True)
def reconcile_balances_task(self, chain_id: int = CHAIN_ID) -> int:
    """
    Task to reconcile on-chain balances with database balances.
    
    Args:
        chain_id: The blockchain chain ID
        
    Returns:
        Number of wallets reconciled
    """
    try:
        logger.info(f"Reconciling balances for chain ID {chain_id}")
        
        # Reconcile balances
        reconciled_count = reconcile_balances(chain_id)
        
        logger.info(f"Reconciled {reconciled_count} token balances")
        
        return reconciled_count
    
    except Exception as e:
        logger.error(f"Error in reconcile_balances task: {e}")
        raise


@shared_task(base=MonitoringTask, bind=True)
def refresh_address_cache(self) -> int:
    """
    Task to refresh the deposit addresses cache.
    
    Returns:
        Number of addresses loaded
    """
    try:
        # Refresh the deposit addresses
        self.refresh_addresses()
        
        # Return the number of addresses
        count = len(self.deposit_addresses)
        logger.info(f"Refreshed deposit addresses cache: {count} addresses loaded")
        
        return count
    
    except Exception as e:
        logger.error(f"Error in refresh_address_cache task: {e}")
        raise


# For manual testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test monitor_deposits task
    result = monitor_deposits(CHAIN_ID)
    print(f"Monitor result: {result}")
    
    # Test process_confirmations task
    confirmed = process_confirmations(CHAIN_ID)
    print(f"Confirmed transactions: {confirmed}")
    
    # Test reconcile_balances task
    reconciled = reconcile_balances_task(CHAIN_ID)
    print(f"Reconciled balances: {reconciled}") 