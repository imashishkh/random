#!/usr/bin/env python3
"""
Suspicious Blockchain Activity Detector

This script analyzes blockchain transactions to detect potentially suspicious activities
such as:
- Unusual transaction patterns
- Transactions involving known suspicious addresses
- Large or unusual value transfers
- Multiple rapid transactions
"""

import os
import sys
import json
import argparse
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Any, Set
from collections import defaultdict, Counter

# Add the parent directory to the path so we can import our modules
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
project_root = script_dir.parent
sys.path.append(str(project_root))

# Import our modules
from dotenv import load_dotenv
from src.db import get_db_connection

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
logger = logging.getLogger('suspicious_activity')

# Thresholds for suspicious activity detection
DEFAULT_THRESHOLDS = {
    'large_transaction_value': 100.0,  # BNB value threshold for large transactions
    'transaction_frequency': 10,       # Number of transactions in short period to flag
    'frequency_time_window': 3600,     # Time window in seconds (1 hour)
    'unusual_hour_threshold': 3,       # Transactions outside business hours
    'repeated_address_threshold': 5,   # Transactions with same external address
}

def load_blacklist(blacklist_path: str) -> Set[str]:
    """
    Load blacklisted addresses from a file.
    
    Args:
        blacklist_path: Path to JSON file with blacklisted addresses
        
    Returns:
        Set of blacklisted addresses
    """
    if not os.path.exists(blacklist_path):
        logger.warning(f"Blacklist file not found: {blacklist_path}")
        return set()
        
    try:
        with open(blacklist_path, 'r') as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            if 'addresses' in data and isinstance(data['addresses'], list):
                return set(addr.lower() for addr in data['addresses'])
            logger.error(f"Invalid blacklist format in {blacklist_path}")
            return set()
            
        return set(addr.lower() for addr in data)
        
    except Exception as e:
        logger.error(f"Error loading blacklist: {str(e)}")
        return set()

def get_recent_transactions(days: int) -> List[Dict[str, Any]]:
    """
    Retrieve recent blockchain transactions from the database.
    
    Args:
        days: Number of days to look back
        
    Returns:
        List of transaction records
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Calculate cutoff date
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        cutoff_date_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')
        
        query = """
        SELECT 
            id, tx_hash, from_address, to_address, block_number, 
            value, chain_id, status, confirmations, user_id, 
            created_at, updated_at 
        FROM 
            blockchain_transactions 
        WHERE 
            created_at >= %s
        ORDER BY 
            created_at DESC
        """
        
        cursor.execute(query, (cutoff_date_str,))
        columns = [col[0] for col in cursor.description]
        transactions = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        logger.info(f"Retrieved {len(transactions)} transactions from the past {days} days")
        return transactions
        
    except Exception as e:
        logger.error(f"Error retrieving transactions: {str(e)}")
        return []
    finally:
        conn.close()

def detect_blacklisted_addresses(transactions: List[Dict[str, Any]], blacklist: Set[str]) -> List[Dict[str, Any]]:
    """
    Detect transactions involving blacklisted addresses.
    
    Args:
        transactions: List of transaction records
        blacklist: Set of blacklisted addresses
        
    Returns:
        List of suspicious transactions involving blacklisted addresses
    """
    suspicious = []
    
    for tx in transactions:
        from_address = tx.get('from_address', '').lower()
        to_address = tx.get('to_address', '').lower()
        
        if from_address in blacklist or to_address in blacklist:
            suspicious.append({
                'tx_id': tx['id'],
                'tx_hash': tx['tx_hash'],
                'from_address': tx['from_address'],
                'to_address': tx['to_address'],
                'created_at': tx['created_at'].isoformat() if isinstance(tx['created_at'], datetime.datetime) else tx['created_at'],
                'value': tx['value'],
                'reason': 'blacklisted_address',
                'details': f"{'From' if from_address in blacklist else 'To'} address is blacklisted"
            })
    
    return suspicious

def detect_large_transactions(transactions: List[Dict[str, Any]], threshold: float) -> List[Dict[str, Any]]:
    """
    Detect unusually large transactions.
    
    Args:
        transactions: List of transaction records
        threshold: Value threshold for large transactions
        
    Returns:
        List of suspicious large transactions
    """
    suspicious = []
    
    for tx in transactions:
        value = float(tx.get('value', 0))
        
        if value >= threshold:
            suspicious.append({
                'tx_id': tx['id'],
                'tx_hash': tx['tx_hash'],
                'from_address': tx['from_address'],
                'to_address': tx['to_address'],
                'created_at': tx['created_at'].isoformat() if isinstance(tx['created_at'], datetime.datetime) else tx['created_at'],
                'value': value,
                'reason': 'large_transaction',
                'details': f"Transaction value {value} exceeds threshold {threshold}"
            })
    
    return suspicious

def detect_high_frequency(transactions: List[Dict[str, Any]], 
                         count_threshold: int, 
                         time_window: int) -> List[Dict[str, Any]]:
    """
    Detect high frequency of transactions from the same user/address.
    
    Args:
        transactions: List of transaction records
        count_threshold: Number of transactions to consider suspicious
        time_window: Time window in seconds
        
    Returns:
        List of suspicious high frequency transactions
    """
    suspicious = []
    
    # Group transactions by user_id
    user_transactions = defaultdict(list)
    for tx in transactions:
        user_id = tx.get('user_id')
        if user_id:
            user_transactions[user_id].append(tx)
    
    # Check each user's transaction frequency
    for user_id, txs in user_transactions.items():
        # Sort by creation time
        txs.sort(key=lambda x: x['created_at'] if isinstance(x['created_at'], datetime.datetime) 
                                             else datetime.datetime.fromisoformat(x['created_at']))
        
        # Check for windows with high frequency
        for i in range(len(txs)):
            window_txs = [txs[i]]
            start_time = txs[i]['created_at'] if isinstance(txs[i]['created_at'], datetime.datetime) else datetime.datetime.fromisoformat(txs[i]['created_at'])
            
            for j in range(i+1, len(txs)):
                tx_time = txs[j]['created_at'] if isinstance(txs[j]['created_at'], datetime.datetime) else datetime.datetime.fromisoformat(txs[j]['created_at'])
                time_diff = (tx_time - start_time).total_seconds()
                
                if time_diff <= time_window:
                    window_txs.append(txs[j])
                else:
                    break
            
            if len(window_txs) >= count_threshold:
                # Found suspicious cluster
                for tx in window_txs:
                    suspicious.append({
                        'tx_id': tx['id'],
                        'tx_hash': tx['tx_hash'],
                        'from_address': tx['from_address'],
                        'to_address': tx['to_address'],
                        'created_at': tx['created_at'].isoformat() if isinstance(tx['created_at'], datetime.datetime) else tx['created_at'],
                        'value': tx['value'],
                        'reason': 'high_frequency',
                        'details': f"User {user_id} made {len(window_txs)} transactions within {time_window/3600:.1f} hours"
                    })
                
                # Skip ahead to avoid duplicate flagging
                i = j
    
    return suspicious

def detect_unusual_hours(transactions: List[Dict[str, Any]], threshold: int) -> List[Dict[str, Any]]:
    """
    Detect transactions occurring during unusual hours (outside 8 AM - 8 PM).
    
    Args:
        transactions: List of transaction records
        threshold: Minimum number of transactions to consider unusual
        
    Returns:
        List of suspicious transactions during unusual hours
    """
    suspicious = []
    
    # Group transactions by user
    user_unusual_hours = defaultdict(list)
    
    for tx in transactions:
        user_id = tx.get('user_id')
        if not user_id:
            continue
            
        tx_time = tx['created_at'] if isinstance(tx['created_at'], datetime.datetime) else datetime.datetime.fromisoformat(tx['created_at'])
        hour = tx_time.hour
        
        # Define unusual hours (outside 8 AM - 8 PM)
        if hour < 8 or hour >= 20:
            user_unusual_hours[user_id].append(tx)
    
    # Check which users have multiple unusual hour transactions
    for user_id, txs in user_unusual_hours.items():
        if len(txs) >= threshold:
            for tx in txs:
                suspicious.append({
                    'tx_id': tx['id'],
                    'tx_hash': tx['tx_hash'],
                    'from_address': tx['from_address'],
                    'to_address': tx['to_address'],
                    'created_at': tx['created_at'].isoformat() if isinstance(tx['created_at'], datetime.datetime) else tx['created_at'],
                    'value': tx['value'],
                    'reason': 'unusual_hours',
                    'details': f"Transaction at unusual hour: {tx['created_at'] if isinstance(tx['created_at'], str) else tx['created_at'].strftime('%H:%M:%S')}"
                })
    
    return suspicious

def detect_repeated_external_addresses(transactions: List[Dict[str, Any]], threshold: int) -> List[Dict[str, Any]]:
    """
    Detect when a user interacts repeatedly with the same external address.
    
    Args:
        transactions: List of transaction records
        threshold: Number of interactions to consider suspicious
        
    Returns:
        List of suspicious repeated address interactions
    """
    suspicious = []
    
    # Group by user_id
    user_transactions = defaultdict(list)
    for tx in transactions:
        user_id = tx.get('user_id')
        if user_id:
            user_transactions[user_id].append(tx)
    
    # For each user, check for repeated external addresses
    for user_id, txs in user_transactions.items():
        # Count occurrences of external addresses
        external_addresses = []
        for tx in txs:
            if tx['from_address'].lower() != tx['to_address'].lower():  # Skip self-transfers
                if tx.get('direction') == 'outgoing' or 'from_address' in tx:
                    external_addresses.append(tx['to_address'].lower())
                else:
                    external_addresses.append(tx['from_address'].lower())
        
        address_counts = Counter(external_addresses)
        
        # Flag transactions with addresses that appear frequently
        for tx in txs:
            external_addr = None
            if tx['from_address'].lower() != tx['to_address'].lower():
                if tx.get('direction') == 'outgoing' or 'from_address' in tx:
                    external_addr = tx['to_address'].lower()
                else:
                    external_addr = tx['from_address'].lower()
            
            if external_addr and address_counts[external_addr] >= threshold:
                suspicious.append({
                    'tx_id': tx['id'],
                    'tx_hash': tx['tx_hash'],
                    'from_address': tx['from_address'],
                    'to_address': tx['to_address'],
                    'created_at': tx['created_at'].isoformat() if isinstance(tx['created_at'], datetime.datetime) else tx['created_at'],
                    'value': tx['value'],
                    'reason': 'repeated_address',
                    'details': f"User {user_id} interacted with address {external_addr} {address_counts[external_addr]} times"
                })
    
    return suspicious

def save_report(suspicious_activities: List[Dict[str, Any]], output_path: str) -> bool:
    """
    Save suspicious activities to a JSON report file.
    
    Args:
        suspicious_activities: List of suspicious transactions with reasons
        output_path: Path to save the report
        
    Returns:
        True if successful, False otherwise
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        report = {
            'generated_at': datetime.datetime.now().isoformat(),
            'total_suspicious': len(suspicious_activities),
            'activities': suspicious_activities
        }
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Suspicious activity report saved to: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving report: {str(e)}")
        return False

def main():
    """Main function to detect suspicious blockchain activities"""
    parser = argparse.ArgumentParser(description='Detect suspicious blockchain activities')
    parser.add_argument('--days', type=int, default=7,
                        help='Number of days to analyze (default: 7)')
    parser.add_argument('--blacklist', type=str, default='config/blacklisted_addresses.json',
                        help='Path to JSON file with blacklisted addresses')
    parser.add_argument('--thresholds', type=str, default='config/suspicious_thresholds.json',
                        help='Path to JSON file with detection thresholds')
    parser.add_argument('--output', type=str, 
                        default=f"reports/security/suspicious_{datetime.datetime.now().strftime('%Y%m%d')}.json",
                        help='Output report file path')
    args = parser.parse_args()
    
    logger.info("Starting suspicious activity detection")
    
    # Load blacklist
    blacklist = load_blacklist(args.blacklist)
    logger.info(f"Loaded {len(blacklist)} blacklisted addresses")
    
    # Load thresholds
    thresholds = DEFAULT_THRESHOLDS
    if os.path.exists(args.thresholds):
        try:
            with open(args.thresholds, 'r') as f:
                custom_thresholds = json.load(f)
                thresholds.update(custom_thresholds)
            logger.info(f"Loaded custom detection thresholds from {args.thresholds}")
        except Exception as e:
            logger.warning(f"Error loading custom thresholds, using defaults: {str(e)}")
    
    # Get recent transactions
    transactions = get_recent_transactions(args.days)
    
    if not transactions:
        logger.error("No transactions found or error occurred")
        return
    
    # Detect suspicious activities
    suspicious = []
    
    # Check for blacklisted addresses
    blacklist_suspicious = detect_blacklisted_addresses(transactions, blacklist)
    suspicious.extend(blacklist_suspicious)
    logger.info(f"Detected {len(blacklist_suspicious)} transactions with blacklisted addresses")
    
    # Check for large transactions
    large_suspicious = detect_large_transactions(transactions, thresholds['large_transaction_value'])
    suspicious.extend(large_suspicious)
    logger.info(f"Detected {len(large_suspicious)} unusually large transactions")
    
    # Check for high frequency
    freq_suspicious = detect_high_frequency(
        transactions, 
        thresholds['transaction_frequency'],
        thresholds['frequency_time_window']
    )
    suspicious.extend(freq_suspicious)
    logger.info(f"Detected {len(freq_suspicious)} high-frequency transaction patterns")
    
    # Check for unusual hours
    hours_suspicious = detect_unusual_hours(transactions, thresholds['unusual_hour_threshold'])
    suspicious.extend(hours_suspicious)
    logger.info(f"Detected {len(hours_suspicious)} transactions at unusual hours")
    
    # Check for repeated external addresses
    repeated_suspicious = detect_repeated_external_addresses(transactions, thresholds['repeated_address_threshold'])
    suspicious.extend(repeated_suspicious)
    logger.info(f"Detected {len(repeated_suspicious)} patterns of repeated address interactions")
    
    # Deduplicate suspicious activities
    unique_tx_ids = set()
    unique_suspicious = []
    
    for activity in suspicious:
        tx_id = activity['tx_id']
        if tx_id not in unique_tx_ids:
            unique_tx_ids.add(tx_id)
            unique_suspicious.append(activity)
    
    logger.info(f"Found {len(unique_suspicious)} unique suspicious transactions")
    
    # Save report
    if unique_suspicious:
        save_report(unique_suspicious, args.output)
    else:
        logger.info("No suspicious activities detected")

if __name__ == "__main__":
    main() 