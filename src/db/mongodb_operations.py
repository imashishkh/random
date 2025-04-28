"""
MongoDB CRUD operations for Forex Trading application.

This module provides functions for performing CRUD operations on MongoDB collections
including trades, accounts, strategies, and journal entries.
"""

import logging
import datetime
import uuid
from typing import Dict, List, Any, Optional, Union

from pymongo.errors import DuplicateKeyError, PyMongoError
from bson.objectid import ObjectId

from .mongodb_connection import get_collection

# Set up logging
logger = logging.getLogger(__name__)

# ===================== Trade Operations =====================

def create_trade(trade_data: Dict[str, Any]) -> Optional[str]:
    """
    Create a new trade in the trades collection.
    
    Args:
        trade_data (Dict[str, Any]): Trade data to insert
        
    Returns:
        Optional[str]: ID of the created trade or None if creation failed
    """
    try:
        # Generate trade_id if not provided
        if 'trade_id' not in trade_data:
            trade_data['trade_id'] = str(uuid.uuid4())
            
        # Add timestamps if not present
        current_time = datetime.datetime.utcnow()
        if 'open_time' not in trade_data:
            trade_data['open_time'] = current_time
            
        # Get trades collection
        trades_collection = get_collection('trades')
        
        # Insert trade
        result = trades_collection.insert_one(trade_data)
        
        if result.acknowledged:
            logger.info(f"Created trade with ID: {trade_data['trade_id']}")
            return trade_data['trade_id']
        else:
            logger.error("Failed to create trade: Insert not acknowledged")
            return None
            
    except DuplicateKeyError:
        logger.error(f"Failed to create trade: Duplicate trade_id {trade_data.get('trade_id')}")
        return None
    except PyMongoError as e:
        logger.error(f"Failed to create trade: {str(e)}")
        return None


def get_trade_by_id(trade_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a trade by its ID.
    
    Args:
        trade_id (str): ID of the trade to retrieve
        
    Returns:
        Optional[Dict[str, Any]]: Trade data or None if not found
    """
    try:
        trades_collection = get_collection('trades')
        trade = trades_collection.find_one({'trade_id': trade_id})
        
        if trade:
            return trade
        else:
            logger.warning(f"Trade with ID {trade_id} not found")
            return None
            
    except PyMongoError as e:
        logger.error(f"Error retrieving trade {trade_id}: {str(e)}")
        return None


def get_trades(
    account_id: Optional[str] = None,
    strategy_id: Optional[str] = None, 
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = None,
    date_from: Optional[datetime.datetime] = None,
    date_to: Optional[datetime.datetime] = None,
    limit: int = 100,
    skip: int = 0,
    sort_by: str = 'open_time',
    sort_direction: int = -1
) -> List[Dict[str, Any]]:
    """
    Get trades with optional filtering.
    
    Args:
        account_id (Optional[str]): Filter by account ID
        strategy_id (Optional[str]): Filter by strategy ID
        symbol (Optional[str]): Filter by trading symbol
        status (Optional[str]): Filter by trade status
        direction (Optional[str]): Filter by trade direction
        date_from (Optional[datetime.datetime]): Filter trades after this date
        date_to (Optional[datetime.datetime]): Filter trades before this date
        limit (int): Maximum number of trades to return
        skip (int): Number of trades to skip (for pagination)
        sort_by (str): Field to sort by
        sort_direction (int): Sort direction (1 for ascending, -1 for descending)
        
    Returns:
        List[Dict[str, Any]]: List of trades matching the criteria
    """
    try:
        trades_collection = get_collection('trades')
        
        # Build query filter
        query_filter = {}
        
        if account_id:
            query_filter['account_id'] = account_id
            
        if strategy_id:
            query_filter['strategy_id'] = strategy_id
            
        if symbol:
            query_filter['symbol'] = symbol
            
        if status:
            query_filter['status'] = status
            
        if direction:
            query_filter['direction'] = direction
            
        # Handle date range query
        date_query = {}
        if date_from:
            date_query['$gte'] = date_from
        if date_to:
            date_query['$lte'] = date_to
        if date_query:
            query_filter['open_time'] = date_query
            
        # Execute query with pagination and sorting
        cursor = trades_collection.find(query_filter)
        
        # Apply sorting
        cursor = cursor.sort(sort_by, sort_direction)
        
        # Apply pagination
        cursor = cursor.skip(skip).limit(limit)
        
        # Convert cursor to list
        trades = list(cursor)
        
        logger.info(f"Retrieved {len(trades)} trades with filter: {query_filter}")
        return trades
        
    except PyMongoError as e:
        logger.error(f"Error retrieving trades: {str(e)}")
        return []


def update_trade(trade_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Update an existing trade.
    
    Args:
        trade_id (str): ID of the trade to update
        update_data (Dict[str, Any]): New data to update
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Don't allow updating the trade_id
        if 'trade_id' in update_data:
            del update_data['trade_id']
            
        trades_collection = get_collection('trades')
        
        # Update the trade
        result = trades_collection.update_one(
            {'trade_id': trade_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            logger.warning(f"Trade with ID {trade_id} not found for update")
            return False
            
        if result.modified_count > 0:
            logger.info(f"Updated trade {trade_id}")
            return True
        else:
            logger.info(f"No changes made to trade {trade_id}")
            return True
            
    except PyMongoError as e:
        logger.error(f"Error updating trade {trade_id}: {str(e)}")
        return False


def close_trade(
    trade_id: str, 
    close_price: float, 
    close_time: Optional[datetime.datetime] = None,
    pnl: Optional[float] = None,
    notes: Optional[str] = None
) -> bool:
    """
    Close an existing trade.
    
    Args:
        trade_id (str): ID of the trade to close
        close_price (float): Closing price of the trade
        close_time (Optional[datetime.datetime]): Time when the trade was closed
        pnl (Optional[float]): Profit/loss amount
        notes (Optional[str]): Additional notes about the trade closure
        
    Returns:
        bool: True if closure was successful, False otherwise
    """
    try:
        trades_collection = get_collection('trades')
        
        # Get current trade data to calculate PNL if not provided
        if pnl is None:
            trade = trades_collection.find_one({'trade_id': trade_id})
            if not trade:
                logger.warning(f"Trade with ID {trade_id} not found for closure")
                return False
                
            # Calculate PNL based on direction
            direction = trade.get('direction')
            open_price = trade.get('open_price')
            lot_size = trade.get('lot_size', 0)
            
            if direction and open_price and lot_size:
                if direction == 'BUY':
                    pnl = (close_price - open_price) * lot_size
                else:  # SELL
                    pnl = (open_price - close_price) * lot_size
        
        # Prepare update data
        update_data = {
            'close_price': close_price,
            'close_time': close_time or datetime.datetime.utcnow(),
            'status': 'CLOSED',
            'pnl': pnl
        }
        
        if notes:
            update_data['notes'] = notes
            
        # Update the trade
        result = trades_collection.update_one(
            {'trade_id': trade_id, 'status': 'OPEN'},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            logger.warning(f"Trade with ID {trade_id} not found or already closed")
            return False
            
        if result.modified_count > 0:
            logger.info(f"Closed trade {trade_id} with PNL: {pnl}")
            return True
        else:
            logger.warning(f"Failed to close trade {trade_id}")
            return False
            
    except PyMongoError as e:
        logger.error(f"Error closing trade {trade_id}: {str(e)}")
        return False


def delete_trade(trade_id: str) -> bool:
    """
    Delete a trade.
    
    Args:
        trade_id (str): ID of the trade to delete
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        trades_collection = get_collection('trades')
        
        # Delete the trade
        result = trades_collection.delete_one({'trade_id': trade_id})
        
        if result.deleted_count > 0:
            logger.info(f"Deleted trade {trade_id}")
            return True
        else:
            logger.warning(f"Trade with ID {trade_id} not found for deletion")
            return False
            
    except PyMongoError as e:
        logger.error(f"Error deleting trade {trade_id}: {str(e)}")
        return False

# ===================== Account Operations =====================

def create_account(account_data: Dict[str, Any]) -> Optional[str]:
    """
    Create a new account in the accounts collection.
    
    Args:
        account_data (Dict[str, Any]): Account data to insert
        
    Returns:
        Optional[str]: ID of the created account or None if creation failed
    """
    try:
        # Generate account_id if not provided
        if 'account_id' not in account_data:
            account_data['account_id'] = str(uuid.uuid4())
            
        # Add timestamps if not present
        current_time = datetime.datetime.utcnow()
        if 'creation_date' not in account_data:
            account_data['creation_date'] = current_time
        if 'last_updated' not in account_data:
            account_data['last_updated'] = current_time
            
        # Get accounts collection
        accounts_collection = get_collection('accounts')
        
        # Insert account
        result = accounts_collection.insert_one(account_data)
        
        if result.acknowledged:
            logger.info(f"Created account with ID: {account_data['account_id']}")
            return account_data['account_id']
        else:
            logger.error("Failed to create account: Insert not acknowledged")
            return None
            
    except DuplicateKeyError:
        logger.error(f"Failed to create account: Duplicate account_id {account_data.get('account_id')}")
        return None
    except PyMongoError as e:
        logger.error(f"Failed to create account: {str(e)}")
        return None


def get_account_by_id(account_id: str) -> Optional[Dict[str, Any]]:
    """
    Get an account by its ID.
    
    Args:
        account_id (str): ID of the account to retrieve
        
    Returns:
        Optional[Dict[str, Any]]: Account data or None if not found
    """
    try:
        accounts_collection = get_collection('accounts')
        account = accounts_collection.find_one({'account_id': account_id})
        
        if account:
            return account
        else:
            logger.warning(f"Account with ID {account_id} not found")
            return None
            
    except PyMongoError as e:
        logger.error(f"Error retrieving account {account_id}: {str(e)}")
        return None


def get_accounts(
    broker: Optional[str] = None,
    account_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 100,
    skip: int = 0
) -> List[Dict[str, Any]]:
    """
    Get accounts with optional filtering.
    
    Args:
        broker (Optional[str]): Filter by broker name
        account_type (Optional[str]): Filter by account type
        is_active (Optional[bool]): Filter by active status
        limit (int): Maximum number of accounts to return
        skip (int): Number of accounts to skip (for pagination)
        
    Returns:
        List[Dict[str, Any]]: List of accounts matching the criteria
    """
    try:
        accounts_collection = get_collection('accounts')
        
        # Build query filter
        query_filter = {}
        
        if broker:
            query_filter['broker'] = broker
            
        if account_type:
            query_filter['account_type'] = account_type
            
        if is_active is not None:
            query_filter['is_active'] = is_active
            
        # Execute query with pagination
        cursor = accounts_collection.find(query_filter)
        
        # Apply pagination
        cursor = cursor.skip(skip).limit(limit)
        
        # Convert cursor to list
        accounts = list(cursor)
        
        logger.info(f"Retrieved {len(accounts)} accounts with filter: {query_filter}")
        return accounts
        
    except PyMongoError as e:
        logger.error(f"Error retrieving accounts: {str(e)}")
        return []


def update_account(account_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Update an existing account.
    
    Args:
        account_id (str): ID of the account to update
        update_data (Dict[str, Any]): New data to update
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Don't allow updating the account_id
        if 'account_id' in update_data:
            del update_data['account_id']
            
        # Update the last_updated timestamp
        update_data['last_updated'] = datetime.datetime.utcnow()
        
        accounts_collection = get_collection('accounts')
        
        # Update the account
        result = accounts_collection.update_one(
            {'account_id': account_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            logger.warning(f"Account with ID {account_id} not found for update")
            return False
            
        if result.modified_count > 0:
            logger.info(f"Updated account {account_id}")
            return True
        else:
            logger.info(f"No changes made to account {account_id}")
            return True
            
    except PyMongoError as e:
        logger.error(f"Error updating account {account_id}: {str(e)}")
        return False


def delete_account(account_id: str) -> bool:
    """
    Delete an account.
    
    Args:
        account_id (str): ID of the account to delete
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        accounts_collection = get_collection('accounts')
        
        # Delete the account
        result = accounts_collection.delete_one({'account_id': account_id})
        
        if result.deleted_count > 0:
            logger.info(f"Deleted account {account_id}")
            return True
        else:
            logger.warning(f"Account with ID {account_id} not found for deletion")
            return False
            
    except PyMongoError as e:
        logger.error(f"Error deleting account {account_id}: {str(e)}")
        return False

# ===================== Strategy Operations =====================

def create_strategy(strategy_data: Dict[str, Any]) -> Optional[str]:
    """
    Create a new strategy in the strategies collection.
    
    Args:
        strategy_data (Dict[str, Any]): Strategy data to insert
        
    Returns:
        Optional[str]: ID of the created strategy or None if creation failed
    """
    try:
        # Generate strategy_id if not provided
        if 'strategy_id' not in strategy_data:
            strategy_data['strategy_id'] = str(uuid.uuid4())
            
        # Add timestamps if not present
        current_time = datetime.datetime.utcnow()
        if 'created_at' not in strategy_data:
            strategy_data['created_at'] = current_time
        if 'last_updated' not in strategy_data:
            strategy_data['last_updated'] = current_time
            
        # Get strategies collection
        strategies_collection = get_collection('strategies')
        
        # Insert strategy
        result = strategies_collection.insert_one(strategy_data)
        
        if result.acknowledged:
            logger.info(f"Created strategy with ID: {strategy_data['strategy_id']}")
            return strategy_data['strategy_id']
        else:
            logger.error("Failed to create strategy: Insert not acknowledged")
            return None
            
    except DuplicateKeyError:
        logger.error(f"Failed to create strategy: Duplicate strategy_id or name")
        return None
    except PyMongoError as e:
        logger.error(f"Failed to create strategy: {str(e)}")
        return None


def get_strategy_by_id(strategy_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a strategy by its ID.
    
    Args:
        strategy_id (str): ID of the strategy to retrieve
        
    Returns:
        Optional[Dict[str, Any]]: Strategy data or None if not found
    """
    try:
        strategies_collection = get_collection('strategies')
        strategy = strategies_collection.find_one({'strategy_id': strategy_id})
        
        if strategy:
            return strategy
        else:
            logger.warning(f"Strategy with ID {strategy_id} not found")
            return None
            
    except PyMongoError as e:
        logger.error(f"Error retrieving strategy {strategy_id}: {str(e)}")
        return None


def get_strategies(
    is_active: Optional[bool] = None,
    category: Optional[str] = None,
    timeframe: Optional[str] = None,
    instrument: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> List[Dict[str, Any]]:
    """
    Get strategies with optional filtering.
    
    Args:
        is_active (Optional[bool]): Filter by active status
        category (Optional[str]): Filter by strategy category
        timeframe (Optional[str]): Filter by timeframe
        instrument (Optional[str]): Filter by instrument
        limit (int): Maximum number of strategies to return
        skip (int): Number of strategies to skip (for pagination)
        
    Returns:
        List[Dict[str, Any]]: List of strategies matching the criteria
    """
    try:
        strategies_collection = get_collection('strategies')
        
        # Build query filter
        query_filter = {}
        
        if is_active is not None:
            query_filter['is_active'] = is_active
            
        if category:
            query_filter['category'] = category
            
        if timeframe:
            query_filter['timeframes'] = timeframe
            
        if instrument:
            query_filter['instruments'] = instrument
            
        # Execute query with pagination
        cursor = strategies_collection.find(query_filter)
        
        # Apply pagination
        cursor = cursor.skip(skip).limit(limit)
        
        # Convert cursor to list
        strategies = list(cursor)
        
        logger.info(f"Retrieved {len(strategies)} strategies with filter: {query_filter}")
        return strategies
        
    except PyMongoError as e:
        logger.error(f"Error retrieving strategies: {str(e)}")
        return []


def update_strategy(strategy_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Update an existing strategy.
    
    Args:
        strategy_id (str): ID of the strategy to update
        update_data (Dict[str, Any]): New data to update
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Don't allow updating the strategy_id
        if 'strategy_id' in update_data:
            del update_data['strategy_id']
            
        # Update the last_updated timestamp
        update_data['last_updated'] = datetime.datetime.utcnow()
        
        strategies_collection = get_collection('strategies')
        
        # Update the strategy
        result = strategies_collection.update_one(
            {'strategy_id': strategy_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            logger.warning(f"Strategy with ID {strategy_id} not found for update")
            return False
            
        if result.modified_count > 0:
            logger.info(f"Updated strategy {strategy_id}")
            return True
        else:
            logger.info(f"No changes made to strategy {strategy_id}")
            return True
            
    except DuplicateKeyError:
        logger.error(f"Failed to update strategy: Duplicate name")
        return False
    except PyMongoError as e:
        logger.error(f"Error updating strategy {strategy_id}: {str(e)}")
        return False


def delete_strategy(strategy_id: str) -> bool:
    """
    Delete a strategy.
    
    Args:
        strategy_id (str): ID of the strategy to delete
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        strategies_collection = get_collection('strategies')
        
        # Delete the strategy
        result = strategies_collection.delete_one({'strategy_id': strategy_id})
        
        if result.deleted_count > 0:
            logger.info(f"Deleted strategy {strategy_id}")
            return True
        else:
            logger.warning(f"Strategy with ID {strategy_id} not found for deletion")
            return False
            
    except PyMongoError as e:
        logger.error(f"Error deleting strategy {strategy_id}: {str(e)}")
        return False

# ===================== Journal Entry Operations =====================

def create_journal_entry(entry_data: Dict[str, Any]) -> Optional[str]:
    """
    Create a new journal entry in the journal_entries collection.
    
    Args:
        entry_data (Dict[str, Any]): Journal entry data to insert
        
    Returns:
        Optional[str]: ID of the created journal entry or None if creation failed
    """
    try:
        # Generate entry_id if not provided
        if 'entry_id' not in entry_data:
            entry_data['entry_id'] = str(uuid.uuid4())
            
        # Add timestamps if not present
        current_time = datetime.datetime.utcnow()
        if 'created_at' not in entry_data:
            entry_data['created_at'] = current_time
        if 'updated_at' not in entry_data:
            entry_data['updated_at'] = current_time
            
        # Set defaults for optional fields
        if 'is_private' not in entry_data:
            entry_data['is_private'] = True
            
        # Get journal_entries collection
        journal_entries_collection = get_collection('journal_entries')
        
        # Insert journal entry
        result = journal_entries_collection.insert_one(entry_data)
        
        if result.acknowledged:
            logger.info(f"Created journal entry with ID: {entry_data['entry_id']}")
            return entry_data['entry_id']
        else:
            logger.error("Failed to create journal entry: Insert not acknowledged")
            return None
            
    except DuplicateKeyError:
        logger.error(f"Failed to create journal entry: Duplicate entry_id {entry_data.get('entry_id')}")
        return None
    except PyMongoError as e:
        logger.error(f"Failed to create journal entry: {str(e)}")
        return None


def get_journal_entry_by_id(entry_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a journal entry by its ID.
    
    Args:
        entry_id (str): ID of the journal entry to retrieve
        
    Returns:
        Optional[Dict[str, Any]]: Journal entry data or None if not found
    """
    try:
        journal_entries_collection = get_collection('journal_entries')
        entry = journal_entries_collection.find_one({'entry_id': entry_id})
        
        if entry:
            return entry
        else:
            logger.warning(f"Journal entry with ID {entry_id} not found")
            return None
            
    except PyMongoError as e:
        logger.error(f"Error retrieving journal entry {entry_id}: {str(e)}")
        return None


def get_journal_entries(
    account_id: Optional[str] = None,
    trade_id: Optional[str] = None,
    date_from: Optional[datetime.datetime] = None,
    date_to: Optional[datetime.datetime] = None,
    tags: Optional[List[str]] = None,
    mood: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    sort_by: str = 'date',
    sort_direction: int = -1
) -> List[Dict[str, Any]]:
    """
    Get journal entries with optional filtering.
    
    Args:
        account_id (Optional[str]): Filter by account ID
        trade_id (Optional[str]): Filter by trade ID
        date_from (Optional[datetime.datetime]): Filter entries after this date
        date_to (Optional[datetime.datetime]): Filter entries before this date
        tags (Optional[List[str]]): Filter by tags
        mood (Optional[str]): Filter by mood
        limit (int): Maximum number of entries to return
        skip (int): Number of entries to skip (for pagination)
        sort_by (str): Field to sort by
        sort_direction (int): Sort direction (1 for ascending, -1 for descending)
        
    Returns:
        List[Dict[str, Any]]: List of journal entries matching the criteria
    """
    try:
        journal_entries_collection = get_collection('journal_entries')
        
        # Build query filter
        query_filter = {}
        
        if account_id:
            query_filter['account_id'] = account_id
            
        if trade_id:
            query_filter['trade_id'] = trade_id
            
        # Handle date range query
        date_query = {}
        if date_from:
            date_query['$gte'] = date_from
        if date_to:
            date_query['$lte'] = date_to
        if date_query:
            query_filter['date'] = date_query
            
        if tags:
            query_filter['tags'] = {'$in': tags}
            
        if mood:
            query_filter['mood'] = mood
            
        # Execute query with pagination and sorting
        cursor = journal_entries_collection.find(query_filter)
        
        # Apply sorting
        cursor = cursor.sort(sort_by, sort_direction)
        
        # Apply pagination
        cursor = cursor.skip(skip).limit(limit)
        
        # Convert cursor to list
        entries = list(cursor)
        
        logger.info(f"Retrieved {len(entries)} journal entries with filter: {query_filter}")
        return entries
        
    except PyMongoError as e:
        logger.error(f"Error retrieving journal entries: {str(e)}")
        return []


def update_journal_entry(entry_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Update an existing journal entry.
    
    Args:
        entry_id (str): ID of the journal entry to update
        update_data (Dict[str, Any]): New data to update
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Don't allow updating the entry_id
        if 'entry_id' in update_data:
            del update_data['entry_id']
            
        # Update the updated_at timestamp
        update_data['updated_at'] = datetime.datetime.utcnow()
        
        journal_entries_collection = get_collection('journal_entries')
        
        # Update the journal entry
        result = journal_entries_collection.update_one(
            {'entry_id': entry_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            logger.warning(f"Journal entry with ID {entry_id} not found for update")
            return False
            
        if result.modified_count > 0:
            logger.info(f"Updated journal entry {entry_id}")
            return True
        else:
            logger.info(f"No changes made to journal entry {entry_id}")
            return True
            
    except PyMongoError as e:
        logger.error(f"Error updating journal entry {entry_id}: {str(e)}")
        return False


def delete_journal_entry(entry_id: str) -> bool:
    """
    Delete a journal entry.
    
    Args:
        entry_id (str): ID of the journal entry to delete
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        journal_entries_collection = get_collection('journal_entries')
        
        # Delete the journal entry
        result = journal_entries_collection.delete_one({'entry_id': entry_id})
        
        if result.deleted_count > 0:
            logger.info(f"Deleted journal entry {entry_id}")
            return True
        else:
            logger.warning(f"Journal entry with ID {entry_id} not found for deletion")
            return False
            
    except PyMongoError as e:
        logger.error(f"Error deleting journal entry {entry_id}: {str(e)}")
        return False 