#!/usr/bin/env python3
"""
Daily Wallet Balance Report Generator

This script generates a report of all wallet balances in the system, 
comparing on-chain balances with database records to identify discrepancies.
"""

import os
import sys
import csv
import json
import argparse
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Add the parent directory to the path so we can import our modules
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
project_root = script_dir.parent
sys.path.append(str(project_root))

# Import our modules
from dotenv import load_dotenv
from src.db import get_db_connection
from src.account.wallet import (
    get_all_wallets, 
    get_wallet_balance, 
    get_on_chain_balance,
    WalletType
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('balance_report')

def get_all_wallet_balances() -> List[Dict[str, Any]]:
    """
    Retrieve all wallets and their balances from both database and blockchain.
    
    Returns:
        List of dictionaries containing wallet information and balances
    """
    conn = get_db_connection()
    try:
        wallets = get_all_wallets(conn)
        logger.info(f"Retrieved {len(wallets)} wallets from database")
        
        wallet_data = []
        for wallet in wallets:
            wallet_id = wallet['id']
            wallet_address = wallet['address']
            user_id = wallet['user_id']
            wallet_type = WalletType(wallet['type'])
            
            # Get database balance
            db_balance = get_wallet_balance(conn, wallet_id)
            
            # Get on-chain balance
            chain_balance = get_on_chain_balance(wallet_address)
            
            # Calculate discrepancy
            discrepancy = chain_balance - db_balance
            
            wallet_data.append({
                'id': wallet_id,
                'address': wallet_address,
                'user_id': user_id,
                'type': wallet_type.name,
                'db_balance': db_balance,
                'chain_balance': chain_balance,
                'discrepancy': discrepancy,
                'has_discrepancy': abs(discrepancy) > 0.00001  # Allow for tiny rounding differences
            })
        
        return wallet_data
        
    except Exception as e:
        logger.error(f"Error retrieving wallet balances: {str(e)}")
        return []
    finally:
        conn.close()

def generate_csv_report(wallet_data: List[Dict[str, Any]], output_path: str) -> bool:
    """
    Generate a CSV report of wallet balances.
    
    Args:
        wallet_data: List of wallet data including balances
        output_path: Path to save the CSV report
    
    Returns:
        True if successful, False otherwise
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', newline='') as csvfile:
            fieldnames = [
                'wallet_id', 'wallet_address', 'user_id', 'wallet_type',
                'db_balance', 'chain_balance', 'discrepancy', 'has_discrepancy'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for wallet in wallet_data:
                writer.writerow({
                    'wallet_id': wallet['id'],
                    'wallet_address': wallet['address'],
                    'user_id': wallet['user_id'],
                    'wallet_type': wallet['type'],
                    'db_balance': wallet['db_balance'],
                    'chain_balance': wallet['chain_balance'],
                    'discrepancy': wallet['discrepancy'],
                    'has_discrepancy': wallet['has_discrepancy']
                })
        
        logger.info(f"CSV report generated: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error generating CSV report: {str(e)}")
        return False

def generate_summary(wallet_data: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Generate a summary of wallet balances including totals and discrepancies.
    
    Args:
        wallet_data: List of wallet data including balances
    
    Returns:
        Tuple containing summary statistics and list of discrepancies
    """
    summary = {
        'total_wallets': len(wallet_data),
        'total_db_balance': sum(w['db_balance'] for w in wallet_data),
        'total_chain_balance': sum(w['chain_balance'] for w in wallet_data),
        'total_discrepancy': sum(w['discrepancy'] for w in wallet_data),
        'wallets_with_discrepancy': sum(1 for w in wallet_data if w['has_discrepancy']),
        'date': datetime.datetime.now().strftime('%Y-%m-%d'),
        'time': datetime.datetime.now().strftime('%H:%M:%S')
    }
    
    # Get wallets with discrepancies
    discrepancies = [w for w in wallet_data if w['has_discrepancy']]
    
    return summary, discrepancies

def main():
    """Main function to generate wallet balance report"""
    parser = argparse.ArgumentParser(description='Generate wallet balance report')
    parser.add_argument('--output', type=str, 
                        default=f"reports/wallet/daily_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                        help='Output CSV file path')
    parser.add_argument('--summary', type=str,
                        default=f"reports/wallet/summary_{datetime.datetime.now().strftime('%Y%m%d')}.json",
                        help='Output summary JSON file path')
    args = parser.parse_args()
    
    logger.info("Starting wallet balance report generation")
    
    # Get wallet balances
    wallet_data = get_all_wallet_balances()
    
    if not wallet_data:
        logger.error("No wallet data found or error occurred")
        return
    
    # Generate CSV report
    generate_csv_report(wallet_data, args.output)
    
    # Generate summary
    summary, discrepancies = generate_summary(wallet_data)
    
    # Output summary
    logger.info(f"Wallet Balance Summary - {summary['date']}:")
    logger.info(f"Total wallets: {summary['total_wallets']}")
    logger.info(f"Total DB balance: {summary['total_db_balance']}")
    logger.info(f"Total on-chain balance: {summary['total_chain_balance']}")
    logger.info(f"Overall discrepancy: {summary['total_discrepancy']}")
    logger.info(f"Wallets with discrepancies: {summary['wallets_with_discrepancy']}")
    
    # Save summary to JSON file
    try:
        os.makedirs(os.path.dirname(args.summary), exist_ok=True)
        with open(args.summary, 'w') as f:
            json.dump({
                'summary': summary,
                'discrepancies': [
                    {
                        'wallet_id': d['id'],
                        'address': d['address'],
                        'user_id': d['user_id'],
                        'db_balance': d['db_balance'],
                        'chain_balance': d['chain_balance'],
                        'discrepancy': d['discrepancy']
                    } for d in discrepancies
                ]
            }, f, indent=2)
        logger.info(f"Summary saved to {args.summary}")
    except Exception as e:
        logger.error(f"Error saving summary: {str(e)}")
    
    # Log warnings for discrepancies
    if discrepancies:
        logger.warning(f"Found {len(discrepancies)} wallets with balance discrepancies:")
        for d in discrepancies:
            logger.warning(f"  Wallet ID: {d['id']}, Address: {d['address']}, "
                         f"DB: {d['db_balance']}, Chain: {d['chain_balance']}, "
                         f"Discrepancy: {d['discrepancy']}")

if __name__ == "__main__":
    main() 