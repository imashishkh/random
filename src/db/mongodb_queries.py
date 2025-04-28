"""
MongoDB business-level queries for the Forex Trading application.

This module provides higher-level query functions that abstract the business
logic from the raw MongoDB operations. These queries combine and transform data
from multiple collections to provide the information needed by the application.
"""

import logging
import datetime
from typing import Dict, List, Any, Optional, Tuple

from .mongodb_operations import (
    get_trades, get_account_by_id, get_strategy_by_id,
    get_journal_entries
)

# Set up logging
logger = logging.getLogger(__name__)

def get_account_performance(
    account_id: str, 
    start_date: Optional[datetime.datetime] = None, 
    end_date: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Get performance metrics for an account over a specified time period.
    
    Args:
        account_id (str): ID of the account to analyze
        start_date (Optional[datetime.datetime]): Start date for analysis
        end_date (Optional[datetime.datetime]): End date for analysis
        
    Returns:
        Dict[str, Any]: Performance metrics for the account
    """
    # Get account details
    account = get_account_by_id(account_id)
    if not account:
        logger.warning(f"Account {account_id} not found for performance analysis")
        return {
            'account_id': account_id,
            'error': 'Account not found'
        }
    
    # Get trades for the account in the specified time period
    trades = get_trades(
        account_id=account_id,
        date_from=start_date,
        date_to=end_date,
        status='CLOSED'
    )
    
    # Calculate performance metrics
    total_trades = len(trades)
    
    if total_trades == 0:
        return {
            'account_id': account_id,
            'account_name': account.get('name', 'Unknown'),
            'period_start': start_date,
            'period_end': end_date,
            'total_trades': 0,
            'message': 'No closed trades in the specified period'
        }
    
    # Extract trade data for calculations
    pnl_values = [trade.get('pnl', 0) for trade in trades if trade.get('pnl') is not None]
    winning_trades = [pnl for pnl in pnl_values if pnl > 0]
    losing_trades = [pnl for pnl in pnl_values if pnl < 0]
    
    # Calculate metrics
    total_pnl = sum(pnl_values)
    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
    
    avg_win = sum(winning_trades) / win_count if win_count > 0 else 0
    avg_loss = sum(losing_trades) / loss_count if loss_count > 0 else 0
    
    # Calculate profit factor (gross profit / gross loss)
    gross_profit = sum(winning_trades)
    gross_loss = abs(sum(losing_trades)) if losing_trades else 1  # Avoid division by zero
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit
    
    # Find largest win and loss
    largest_win = max(winning_trades) if winning_trades else 0
    largest_loss = min(losing_trades) if losing_trades else 0
    
    # Calculate consecutive wins/losses
    consecutive_wins, consecutive_losses = _calculate_consecutive_trades(trades)
    
    # Return performance data
    return {
        'account_id': account_id,
        'account_name': account.get('name', 'Unknown'),
        'period_start': start_date,
        'period_end': end_date,
        'total_trades': total_trades,
        'win_count': win_count,
        'loss_count': loss_count,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'largest_win': largest_win,
        'largest_loss': largest_loss,
        'max_consecutive_wins': consecutive_wins,
        'max_consecutive_losses': consecutive_losses
    }

def _calculate_consecutive_trades(trades: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Calculate the maximum number of consecutive winning and losing trades.
    
    Args:
        trades (List[Dict[str, Any]]): List of trade data
        
    Returns:
        Tuple[int, int]: Maximum consecutive wins and losses
    """
    # Sort trades by close time
    sorted_trades = sorted(trades, key=lambda x: x.get('close_time', datetime.datetime.min))
    
    current_wins = 0
    current_losses = 0
    max_wins = 0
    max_losses = 0
    
    for trade in sorted_trades:
        pnl = trade.get('pnl', 0)
        
        if pnl > 0:  # Winning trade
            current_wins += 1
            current_losses = 0
        elif pnl < 0:  # Losing trade
            current_losses += 1
            current_wins = 0
        
        # Update max values
        max_wins = max(max_wins, current_wins)
        max_losses = max(max_losses, current_losses)
    
    return max_wins, max_losses

def get_strategy_performance(
    strategy_id: str,
    start_date: Optional[datetime.datetime] = None,
    end_date: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Get performance metrics for a strategy over a specified time period.
    
    Args:
        strategy_id (str): ID of the strategy to analyze
        start_date (Optional[datetime.datetime]): Start date for analysis
        end_date (Optional[datetime.datetime]): End date for analysis
        
    Returns:
        Dict[str, Any]: Performance metrics for the strategy
    """
    # Get strategy details
    strategy = get_strategy_by_id(strategy_id)
    if not strategy:
        logger.warning(f"Strategy {strategy_id} not found for performance analysis")
        return {
            'strategy_id': strategy_id,
            'error': 'Strategy not found'
        }
    
    # Get trades for the strategy in the specified time period
    trades = get_trades(
        strategy_id=strategy_id,
        date_from=start_date,
        date_to=end_date,
        status='CLOSED'
    )
    
    # Calculate performance metrics using the same logic as account performance
    total_trades = len(trades)
    
    if total_trades == 0:
        return {
            'strategy_id': strategy_id,
            'strategy_name': strategy.get('name', 'Unknown'),
            'period_start': start_date,
            'period_end': end_date,
            'total_trades': 0,
            'message': 'No closed trades in the specified period'
        }
    
    # Extract trade data for calculations
    pnl_values = [trade.get('pnl', 0) for trade in trades if trade.get('pnl') is not None]
    winning_trades = [pnl for pnl in pnl_values if pnl > 0]
    losing_trades = [pnl for pnl in pnl_values if pnl < 0]
    
    # Calculate metrics
    total_pnl = sum(pnl_values)
    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
    
    avg_win = sum(winning_trades) / win_count if win_count > 0 else 0
    avg_loss = sum(losing_trades) / loss_count if loss_count > 0 else 0
    
    # Calculate profit factor (gross profit / gross loss)
    gross_profit = sum(winning_trades)
    gross_loss = abs(sum(losing_trades)) if losing_trades else 1  # Avoid division by zero
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit
    
    # Group trades by symbols to see which instruments work best with this strategy
    symbols = {}
    for trade in trades:
        symbol = trade.get('symbol', 'Unknown')
        if symbol not in symbols:
            symbols[symbol] = {
                'count': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0
            }
        
        symbols[symbol]['count'] += 1
        pnl = trade.get('pnl', 0)
        symbols[symbol]['total_pnl'] += pnl
        
        if pnl > 0:
            symbols[symbol]['wins'] += 1
        elif pnl < 0:
            symbols[symbol]['losses'] += 1
    
    # Calculate win rate for each symbol
    for symbol in symbols:
        total = symbols[symbol]['count']
        wins = symbols[symbol]['wins']
        symbols[symbol]['win_rate'] = (wins / total) * 100 if total > 0 else 0
    
    return {
        'strategy_id': strategy_id,
        'strategy_name': strategy.get('name', 'Unknown'),
        'strategy_description': strategy.get('description', ''),
        'period_start': start_date,
        'period_end': end_date,
        'total_trades': total_trades,
        'win_count': win_count,
        'loss_count': loss_count,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'symbols_performance': symbols
    }

def get_trade_with_context(trade_id: str) -> Dict[str, Any]:
    """
    Get a trade with its context: account details, strategy details, and related journal entries.
    
    Args:
        trade_id (str): ID of the trade to retrieve with context
        
    Returns:
        Dict[str, Any]: Trade data with context
    """
    # Get the trade
    trades = get_trades(limit=1)
    if not trades:
        logger.warning(f"Trade {trade_id} not found")
        return {
            'trade_id': trade_id,
            'error': 'Trade not found'
        }
    
    trade = trades[0]
    
    # Get related account
    account = None
    account_id = trade.get('account_id')
    if account_id:
        account = get_account_by_id(account_id)
    
    # Get related strategy
    strategy = None
    strategy_id = trade.get('strategy_id')
    if strategy_id:
        strategy = get_strategy_by_id(strategy_id)
    
    # Get related journal entries
    journal_entries = get_journal_entries(trade_id=trade_id)
    
    # Return combined data
    return {
        'trade': trade,
        'account': account,
        'strategy': strategy,
        'journal_entries': journal_entries
    }

def get_trade_statistics_by_symbol(
    account_id: Optional[str] = None,
    start_date: Optional[datetime.datetime] = None,
    end_date: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Get statistics grouped by trading symbol.
    
    Args:
        account_id (Optional[str]): Filter by account
        start_date (Optional[datetime.datetime]): Start date for analysis
        end_date (Optional[datetime.datetime]): End date for analysis
        
    Returns:
        Dict[str, Any]: Statistics per symbol
    """
    # Get closed trades for the specified period
    trades = get_trades(
        account_id=account_id,
        date_from=start_date,
        date_to=end_date,
        status='CLOSED'
    )
    
    # Group by symbol
    symbols = {}
    
    for trade in trades:
        symbol = trade.get('symbol', 'Unknown')
        if symbol not in symbols:
            symbols[symbol] = {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'buy_trades': 0,
                'sell_trades': 0,
                'avg_holding_time': datetime.timedelta(0)
            }
        
        symbols[symbol]['total_trades'] += 1
        
        # Count wins/losses
        pnl = trade.get('pnl', 0)
        if pnl > 0:
            symbols[symbol]['winning_trades'] += 1
        elif pnl < 0:
            symbols[symbol]['losing_trades'] += 1
        
        symbols[symbol]['total_pnl'] += pnl
        
        # Count directions
        direction = trade.get('direction')
        if direction == 'BUY':
            symbols[symbol]['buy_trades'] += 1
        elif direction == 'SELL':
            symbols[symbol]['sell_trades'] += 1
        
        # Calculate holding time
        open_time = trade.get('open_time')
        close_time = trade.get('close_time')
        if open_time and close_time:
            holding_time = close_time - open_time
            symbols[symbol]['avg_holding_time'] += holding_time
    
    # Calculate averages and percentages
    for symbol in symbols:
        total = symbols[symbol]['total_trades']
        if total > 0:
            symbols[symbol]['win_rate'] = (symbols[symbol]['winning_trades'] / total) * 100
            symbols[symbol]['avg_holding_time'] = symbols[symbol]['avg_holding_time'] / total
            
            # Convert timedelta to hours for easier interpretation
            symbols[symbol]['avg_holding_time_hours'] = symbols[symbol]['avg_holding_time'].total_seconds() / 3600
    
    return {
        'account_id': account_id,
        'period_start': start_date,
        'period_end': end_date,
        'total_symbols': len(symbols),
        'symbols': symbols
    }

def get_daily_performance(
    account_id: Optional[str] = None,
    start_date: Optional[datetime.datetime] = None,
    end_date: Optional[datetime.datetime] = None
) -> List[Dict[str, Any]]:
    """
    Get daily performance for an account.
    
    Args:
        account_id (Optional[str]): Filter by account
        start_date (Optional[datetime.datetime]): Start date
        end_date (Optional[datetime.datetime]): End date
        
    Returns:
        List[Dict[str, Any]]: Daily performance data
    """
    # Get closed trades for the specified period
    trades = get_trades(
        account_id=account_id,
        date_from=start_date,
        date_to=end_date,
        status='CLOSED'
    )
    
    # Group trades by day
    daily_data = {}
    
    for trade in trades:
        close_time = trade.get('close_time')
        if not close_time:
            continue
        
        # Extract date part only
        date_key = close_time.date()
        
        if date_key not in daily_data:
            daily_data[date_key] = {
                'date': datetime.datetime.combine(date_key, datetime.time.min),
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0
            }
        
        daily_data[date_key]['total_trades'] += 1
        
        pnl = trade.get('pnl', 0)
        daily_data[date_key]['total_pnl'] += pnl
        
        if pnl > 0:
            daily_data[date_key]['winning_trades'] += 1
        elif pnl < 0:
            daily_data[date_key]['losing_trades'] += 1
    
    # Convert to list and sort by date
    result = list(daily_data.values())
    result.sort(key=lambda x: x['date'])
    
    # Calculate running balance if account_id is provided
    if account_id and result:
        account = get_account_by_id(account_id)
        if account:
            # Start with the initial balance (or calculate from trades)
            initial_balance = account.get('initial_deposit', account.get('balance', 0))
            running_balance = initial_balance
            
            for day in result:
                day['balance_before'] = running_balance
                running_balance += day['total_pnl']
                day['balance_after'] = running_balance
                day['daily_return_percent'] = (day['total_pnl'] / day['balance_before']) * 100 if day['balance_before'] > 0 else 0
    
    return result 