#!/usr/bin/env python3
"""
Wallet Report Generator

This script generates reports on wallet balances and transactions for
auditing and reconciliation purposes.
"""

import os
import sys
import csv
import json
import argparse
import logging
import datetime
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.account.wallet import get_all_wallets, get_wallet_transactions, get_wallet_balance
from src.db.database import init_db, close_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/wallet_reports.log')
    ]
)
logger = logging.getLogger('wallet_report')

def generate_balance_report(output_path, format_type='csv'):
    """Generate a report of all wallet balances.
    
    Args:
        output_path (str): Directory where the report will be saved
        format_type (str): Output format ('csv' or 'json')
    
    Returns:
        str: Path to the generated report file
    """
    # Get all wallets
    wallets = get_all_wallets()
    
    # Prepare report data
    report_data = []
    total_balance = 0
    
    for wallet in wallets:
        balance = get_wallet_balance(wallet['address'])
        wallet_data = {
            'user_id': wallet['user_id'],
            'address': wallet['address'],
            'wallet_type': wallet['wallet_type'],
            'balance': balance,
            'last_updated': datetime.datetime.now().isoformat()
        }
        report_data.append(wallet_data)
        total_balance += balance
    
    # Generate filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"wallet_balance_report_{timestamp}.{format_type}"
    file_path = os.path.join(output_path, filename)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)
    
    # Write report to file
    if format_type == 'csv':
        with open(file_path, 'w', newline='') as csvfile:
            fieldnames = ['user_id', 'address', 'wallet_type', 'balance', 'last_updated']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for data in report_data:
                writer.writerow(data)
    else:  # json format
        with open(file_path, 'w') as jsonfile:
            json_data = {
                'report_generated_at': datetime.datetime.now().isoformat(),
                'total_balance': total_balance,
                'wallet_count': len(report_data),
                'wallets': report_data
            }
            json.dump(json_data, jsonfile, indent=2)
    
    logger.info(f"Balance report generated: {file_path}")
    logger.info(f"Total wallets: {len(report_data)}")
    logger.info(f"Total balance: {total_balance}")
    
    return file_path

def generate_transaction_report(output_path, days=7, format_type='csv'):
    """Generate a report of wallet transactions for a specified time period.
    
    Args:
        output_path (str): Directory where the report will be saved
        days (int): Number of days to include in the report
        format_type (str): Output format ('csv' or 'json')
    
    Returns:
        str: Path to the generated report file
    """
    # Calculate start date
    start_date = datetime.datetime.now() - datetime.timedelta(days=days)
    
    # Get all wallets
    wallets = get_all_wallets()
    
    # Prepare report data
    report_data = []
    transaction_count = 0
    
    for wallet in wallets:
        transactions = get_wallet_transactions(wallet['address'], start_date=start_date)
        
        for tx in transactions:
            tx_data = {
                'user_id': wallet['user_id'],
                'wallet_address': wallet['address'],
                'transaction_id': tx['id'],
                'tx_hash': tx['tx_hash'],
                'amount': tx['amount'],
                'timestamp': tx['timestamp'].isoformat(),
                'type': tx['tx_type'],
                'status': tx['status']
            }
            report_data.append(tx_data)
            transaction_count += 1
    
    # Generate filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"wallet_transaction_report_{timestamp}.{format_type}"
    file_path = os.path.join(output_path, filename)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)
    
    # Write report to file
    if format_type == 'csv':
        with open(file_path, 'w', newline='') as csvfile:
            fieldnames = ['user_id', 'wallet_address', 'transaction_id', 'tx_hash', 
                          'amount', 'timestamp', 'type', 'status']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for data in report_data:
                writer.writerow(data)
    else:  # json format
        with open(file_path, 'w') as jsonfile:
            json_data = {
                'report_generated_at': datetime.datetime.now().isoformat(),
                'period_days': days,
                'start_date': start_date.isoformat(),
                'end_date': datetime.datetime.now().isoformat(),
                'transaction_count': transaction_count,
                'transactions': report_data
            }
            json.dump(json_data, jsonfile, indent=2)
    
    logger.info(f"Transaction report generated: {file_path}")
    logger.info(f"Total transactions: {transaction_count}")
    logger.info(f"Period: {days} days ({start_date.strftime('%Y-%m-%d')} to {datetime.datetime.now().strftime('%Y-%m-%d')})")
    
    return file_path

def main():
    """Run the wallet report generator."""
    # Load environment variables
    load_dotenv()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Generate wallet balance and transaction reports')
    parser.add_argument('--report-type', choices=['balance', 'transactions', 'both'], 
                        default='both', help='Type of report to generate')
    parser.add_argument('--format', choices=['csv', 'json'], default='csv',
                        help='Output format for the report')
    parser.add_argument('--output-dir', default='reports',
                        help='Directory where reports will be saved')
    parser.add_argument('--days', type=int, default=7,
                        help='Number of days to include in transaction report')
    args = parser.parse_args()
    
    try:
        # Initialize database connection
        init_db()
        
        # Generate requested reports
        if args.report_type in ['balance', 'both']:
            balance_report = generate_balance_report(
                output_path=args.output_dir,
                format_type=args.format
            )
        
        if args.report_type in ['transactions', 'both']:
            transaction_report = generate_transaction_report(
                output_path=args.output_dir,
                days=args.days,
                format_type=args.format
            )
        
        logger.info("Report generation completed successfully")
        
    except Exception as e:
        logger.exception(f"Error generating wallet reports: {str(e)}")
        sys.exit(1)
    finally:
        # Close database connection
        close_db()

if __name__ == '__main__':
    main() 