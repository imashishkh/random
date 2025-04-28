#!/usr/bin/env python3
"""
Withdrawal Processing Script

This script processes approved withdrawal requests that have met the
required number of approvals. It's designed to be run as a scheduled
task (e.g., via cron).
"""

import os
import sys
import argparse
import logging
import getpass
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.account.withdrawal import process_approved_withdrawals, get_pending_withdrawal_requests
from src.db.database import init_db, close_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/withdrawals.log')
    ]
)
logger = logging.getLogger('withdrawal_processor')

def main():
    """Run the withdrawal processor."""
    # Load environment variables
    load_dotenv()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process approved withdrawal requests')
    parser.add_argument('--batch-size', type=int, default=5, 
                        help='Number of withdrawals to process in one batch')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show withdrawals that would be processed without executing them')
    parser.add_argument('--check', action='store_true',
                        help='Check pending withdrawals and exit')
    args = parser.parse_args()
    
    try:
        # Initialize database connection
        init_db()
        
        if args.check:
            # Just check and report pending withdrawals
            pending = get_pending_withdrawal_requests(limit=100)
            if not pending:
                logger.info("No pending withdrawal requests found.")
                return
                
            logger.info(f"Found {len(pending)} pending withdrawal requests:")
            for req in pending:
                logger.info(f"  ID: {req['id']} - User: {req['user_id']} - "
                           f"Amount: {req['amount']} - "
                           f"Approvals: {req['approval_count']}/{req['required_approvals']}")
            return
            
        if args.dry_run:
            # Show what would be processed without executing
            pending = get_pending_withdrawal_requests(limit=args.batch_size)
            if not pending:
                logger.info("No withdrawal requests ready to process.")
                return
                
            logger.info(f"Would process {len(pending)} withdrawal requests (dry run):")
            for req in pending:
                logger.info(f"  ID: {req['id']} - User: {req['user_id']} - "
                           f"Amount: {req['amount']} - To: {req['to_address']}")
            return
        
        # Get number of withdrawals ready to process
        ready_withdrawals = get_pending_withdrawal_requests(limit=1)
        if not ready_withdrawals:
            logger.info("No withdrawal requests ready to process.")
            return
            
        logger.info("Processing approved withdrawal requests...")
        
        # Prompt for password to decrypt private keys
        password = getpass.getpass("Enter password to decrypt wallet keys: ")
        
        # Process withdrawals
        results = process_approved_withdrawals(
            password=password,
            batch_size=args.batch_size
        )
        
        # Log results
        if results:
            logger.info(f"Successfully processed {len(results)} withdrawal requests.")
            for result in results:
                if result.get('success'):
                    logger.info(f"  ✓ ID: {result['id']} - Tx Hash: {result['tx_hash']}")
                else:
                    logger.error(f"  ✗ ID: {result['id']} - Error: {result.get('error', 'Unknown error')}")
        else:
            logger.info("No withdrawal requests were processed.")
            
    except Exception as e:
        logger.exception(f"Error processing withdrawals: {str(e)}")
        sys.exit(1)
    finally:
        # Close database connection
        close_db()

if __name__ == '__main__':
    main() 