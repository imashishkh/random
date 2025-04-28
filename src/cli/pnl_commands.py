"""
Profit/Loss and Wallet CLI Commands

This module implements the 'botctl pnl' command group for displaying trading profit/loss
and wallet information in a user-friendly CLI format.
"""

import os
import csv
import sys
import click
import logging
import random
import tempfile
import asyncio
import signal
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timedelta
from decimal import Decimal
import io

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich import box

from ..utils.logger import get_logger
from ..db.trade_analytics import AnalyticsService, PositionRepository
from ..services.pnl_calculation_service import CalculationMethod
from ..exchange.binance_api_client import BinanceAPIClient
from ..exchange.websocket.binance import BinanceWebSocketClient
from ..database.wallet import get_wallet_balances, get_historical_wallet_balances

# Initialize logger
logger = get_logger("cli.pnl")

# Initialize rich console for pretty output
console = Console()

@click.group(name="pnl")
def pnl_group():
    """
    Profit/loss analytics and wallet information.
    
    Commands for viewing trading profit/loss metrics and wallet balances.
    """
    pass

def display_wallet_table(balances: List[Dict[str, Any]], console: Console = None, title: str = "") -> Table:
    """
    Create and display a pretty table with wallet balances.
    
    Args:
        balances: List of dictionaries with balance information
        console: Optional Rich console instance
        title: Optional title for the table
        
    Returns:
        Rich Table object
    """
    # Initialize console if not provided
    if console is None:
        console = Console()
    
    # Create table
    table = Table(show_header=True, header_style="bold white", title=title or "Current Wallet Balances")
    
    # Determine if this is historical data by looking for timestamp field
    is_historical = any('timestamp' in balance for balance in balances)
    
    # Add columns based on data type
    if is_historical:
        # Historical data includes timestamps
        table.add_column("Date", style="cyan")
        table.add_column("Agent", style="green")
        table.add_column("Symbol", style="magenta")
        table.add_column("Amount", justify="right")
        table.add_column("Value (USD)", justify="right", style="green")
    else:
        # Standard wallet display
        table.add_column("Symbol", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("Free", justify="right")
        table.add_column("Locked", justify="right")
        table.add_column("Price (USD)", justify="right")
        table.add_column("Value (USD)", justify="right", style="green")
        table.add_column("Allocation", justify="right")
        table.add_column("24h Change", justify="right")
    
    # Add rows based on data type
    if is_historical:
        # Sort balances by date (newest first), then by agent, then by symbol
        sorted_balances = sorted(
            balances, 
            key=lambda x: (
                -datetime.timestamp(x.get('timestamp', datetime.now())), 
                x.get('agent_name', ''), 
                x.get('symbol', '')
            )
        )
        
        for balance in sorted_balances:
            timestamp = balance.get('timestamp')
            date_str = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "N/A"
            
            table.add_row(
                date_str,
                balance.get('agent_name', 'N/A'),
                balance.get('symbol', 'N/A'),
                f"{float(balance.get('amount', 0)):.8f}",
                f"${float(balance.get('usd_value', 0)):.2f}" if balance.get('usd_value') else "N/A"
            )
    else:
        # Standard wallet display
        for balance in balances:
            # Format values
            symbol = balance.get('symbol', '')
            total = f"{balance.get('total', 0):.8f}".rstrip('0').rstrip('.')
            free = f"{balance.get('free', 0):.8f}".rstrip('0').rstrip('.')
            locked = f"{balance.get('locked', 0):.8f}".rstrip('0').rstrip('.')
            price = f"${balance.get('price_usd', 0):.8f}".rstrip('0').rstrip('.')
            value = f"${balance.get('value_usd', 0):.2f}"
            allocation = f"{balance.get('allocation', 0):.2f}%"
            
            # Format 24h change with color
            change_24h = balance.get('change_24h', 0)
            if change_24h > 0:
                change_str = f"[green]+{change_24h:.2f}%[/green]"
            elif change_24h < 0:
                change_str = f"[red]{change_24h:.2f}%[/red]"
            else:
                change_str = f"{change_24h:.2f}%"
                
            # Add row to table
            table.add_row(
                symbol,
                total,
                free,
                locked,
                price,
                value,
                allocation,
                change_str
            )
        
        # Add a total row for standard display
        if balances:
            total_value = sum(b.get('value_usd', 0) for b in balances)
            table.add_row(
                "[bold]TOTAL[/bold]",
                "",
                "",
                "",
                "",
                f"[bold]${total_value:.2f}[/bold]",
                "[bold]100.00%[/bold]",
                "",
                style="bold white"
            )
    
    return table

def get_wallet_balances(agent: Optional[str] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve wallet balances with current market values from Binance API.
    
    Args:
        agent: Optional agent name to filter by
        symbol: Optional symbol to filter by
        
    Returns:
        List of dictionaries with balance information
    """
    # Initialize Binance client
    binance_client = BinanceAPIClient()
    
    # Get balances from Binance
    try:
        balance_data = binance_client.get_balance()
        
        # Format balance data with additional information
        formatted_balances = []
        
        # Get current prices for value calculation
        prices = binance_client.get_ticker_prices()
        price_dict = {ticker['symbol']: float(ticker['price']) for ticker in prices}
        
        # Build list of asset symbols for 24h ticker info
        asset_symbols = []
        for asset in balance_data.get('balances', []):
            symbol_name = asset.get('asset')
            if symbol_name:
                asset_symbols.append(f"{symbol_name}USDT")
        
        # Get 24h ticker info for all relevant assets
        ticker_24h_data = {}
        try:
            # Only get 24h data for assets that have a balance
            ticker_24h_list = binance_client.get_24h_ticker_info(asset_symbols)
            ticker_24h_data = {item['symbol']: item for item in ticker_24h_list}
            logger.debug(f"Retrieved 24h data for {len(ticker_24h_data)} symbols")
        except Exception as e:
            logger.warning(f"Could not retrieve 24h ticker data: {e}. Using estimates.")
        
        # Calculate total portfolio value for allocation percentage
        total_value_usd = 0
        
        # First pass to calculate total value
        for asset in balance_data.get('balances', []):
            symbol_name = asset.get('asset')
            free = float(asset.get('free', 0))
            locked = float(asset.get('locked', 0))
            total = free + locked
            
            # Skip zero balances
            if total <= 0:
                continue
                
            # Calculate USD value
            price_key = f"{symbol_name}USDT"
            price = price_dict.get(price_key, 0)
            value_usd = total * price
            
            total_value_usd += value_usd
        
        # Second pass to create formatted balance records
        for asset in balance_data.get('balances', []):
            symbol_name = asset.get('asset')
            free = float(asset.get('free', 0))
            locked = float(asset.get('locked', 0))
            total = free + locked
            
            # Skip zero balances
            if total <= 0:
                continue
            
            # Calculate USD value
            price_key = f"{symbol_name}USDT"
            price = price_dict.get(price_key, 0)
            value_usd = total * price
            
            # Calculate allocation percentage
            allocation = (value_usd / total_value_usd * 100) if total_value_usd > 0 else 0
            
            # Get 24h change data
            change_24h = 0
            ticker_symbol = f"{symbol_name}USDT"
            if ticker_symbol in ticker_24h_data:
                try:
                    # Use actual 24h change data
                    change_str = ticker_24h_data[ticker_symbol].get('priceChangePercent', '0')
                    change_24h = float(change_str)
                except (ValueError, TypeError):
                    # Default to 0 if can't parse
                    change_24h = 0
            
            balance_info = {
                'symbol': symbol_name,
                'free': free,
                'locked': locked,
                'total': total,
                'price_usd': price,
                'value_usd': value_usd,
                'allocation': allocation,
                'change_24h': change_24h
            }
            
            formatted_balances.append(balance_info)
        
        # Apply filters if provided
        if agent:
            # Implementation would filter by agent from database
            pass
            
        if symbol:
            formatted_balances = [b for b in formatted_balances if b['symbol'].lower() == symbol.lower()]
            
        # Sort by value (descending)
        formatted_balances.sort(key=lambda x: x['value_usd'], reverse=True)
        
        return formatted_balances
        
    except Exception as e:
        logger.error(f"Error fetching wallet balances: {str(e)}")
        return []

def get_historical_wallet_balances(
    agent: Optional[str] = None, 
    symbol: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve historical wallet balances from the database.
    
    Args:
        agent: Optional agent name to filter by
        symbol: Optional symbol to filter by
        start_date: Start date for filtering
        end_date: End date for filtering
        
    Returns:
        List of dictionaries with historical balance information
    """
    try:
        # Initialize the position repository
        from ..db.repositories import PositionRepository
        position_repository = PositionRepository()
        
        # Get positions within date range
        positions = position_repository.get_closed_positions(
            agent_id=agent,
            from_date=start_date,
            to_date=end_date,
            limit=1000  # Use a large limit to get comprehensive data
        )
        
        # Format data to match the wallet balance format
        formatted_balances = []
        
        # Process positions to extract balances by symbol
        symbol_balances = {}
        total_value_usd = 0
        
        # First pass - collect data by symbol and calculate totals
        for position in positions:
            position_symbol = position.symbol if hasattr(position, 'symbol') else position.get('symbol')
            
            # Skip if symbol filter is applied and doesn't match
            if symbol and symbol.lower() != position_symbol.lower():
                continue
            
            # Get position details
            quantity = float(position.quantity if hasattr(position, 'quantity') else position.get('quantity', 0))
            close_price = float(position.close_price if hasattr(position, 'close_price') else position.get('close_price', 0))
            
            # Initialize symbol data if not exists
            if position_symbol not in symbol_balances:
                symbol_balances[position_symbol] = {
                    'total': 0,
                    'free': 0,
                    'locked': 0,
                    'price': close_price,
                    'value': 0,
                    'change_24h': 0  # No change data for historical view
                }
            
            # Update totals
            symbol_balances[position_symbol]['total'] += quantity
            symbol_balances[position_symbol]['free'] += quantity  # Assume all balance is free for historical
            symbol_balances[position_symbol]['price'] = close_price  # Use last close price
            
            # Calculate value
            value = quantity * close_price
            symbol_balances[position_symbol]['value'] += value
            
            # Add to total portfolio value
            total_value_usd += value
        
        # Second pass - calculate allocations and format
        for symbol_name, data in symbol_balances.items():
            # Calculate allocation
            allocation = (data['value'] / total_value_usd * 100) if total_value_usd > 0 else 0
            
            # Create balance record
            balance_info = {
                'symbol': symbol_name,
                'free': data['free'],
                'locked': data['locked'],
                'total': data['total'],
                'price_usd': data['price'],
                'value_usd': data['value'],
                'allocation': allocation,
                'change_24h': data['change_24h'],
                'historical': True  # Flag to indicate historical data
            }
            
            formatted_balances.append(balance_info)
        
        # Sort by value (descending)
        formatted_balances.sort(key=lambda x: x['value_usd'], reverse=True)
        
        return formatted_balances
        
    except Exception as e:
        logger.error(f"Error fetching historical wallet balances: {str(e)}")
        return []

def export_wallet_to_csv(balances: List[Dict[str, Any]], output_path: Optional[str] = None) -> str:
    """
    Export wallet balances to CSV.
    
    Args:
        balances: List of balance dictionaries from get_wallet_balances()
        output_path: Optional path to save CSV file (if None, uses temp file)
                    Use "-" for stdout
        
    Returns:
        Path to the created CSV file or "stdout" if printed to console
    """
    # Create CSV data
    headers = ['Asset', 'Available', 'Locked', 'Total', 'Price (USD)', 
               'Value (USD)', '24h Change (%)', 'Allocation (%)']
    
    rows = []
    for balance in balances:
        rows.append([
            balance.get('symbol', ''),
            balance.get('free', 0),
            balance.get('locked', 0),
            balance.get('total', 0),
            balance.get('price_usd', 0),
            balance.get('value_usd', 0),
            balance.get('change_24h', 0),
            balance.get('allocation', 0)
        ])
    
    # Handle stdout output
    if output_path == "-":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        console.print(output.getvalue())
        return "stdout"
    
    # Determine output path for file
    if output_path is None:
        # Use temporary file if not specified
        output_file = tempfile.NamedTemporaryFile(
            mode='w+', 
            suffix='.csv', 
            delete=False,
            prefix='wallet_balance_'
        )
        output_path = output_file.name
    
    # Write data to CSV file
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            writer.writerows(rows)
        
        return output_path
    except Exception as e:
        logger.error(f"Error writing wallet data to CSV: {e}")
        raise

def export_wallet_history_to_csv(balances: List[Dict[str, Any]], output_path: Optional[str] = None) -> str:
    """
    Export historical wallet balances to CSV.
    
    Args:
        balances: List of historical balance dictionaries
        output_path: Optional path to save CSV file (if None, uses temp file)
                     Use "-" for stdout
        
    Returns:
        Path to the created CSV file or "stdout" if printed to console
    """
    # Create CSV data
    headers = ['Date', 'Agent', 'Symbol', 'Amount', 'Value (USD)']
    
    rows = []
    for balance in balances:
        # Format the timestamp
        timestamp = balance.get('timestamp')
        date_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "N/A"
        
        rows.append([
            date_str,
            balance.get('agent_name', 'N/A'),
            balance.get('symbol', 'N/A'),
            balance.get('amount', 0),
            balance.get('usd_value', 0)
        ])
    
    # Handle stdout output
    if output_path == "-":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        console.print(output.getvalue())
        return "stdout"
    
    # Determine output path for file
    if output_path is None:
        # Use temporary file if not specified
        output_file = tempfile.NamedTemporaryFile(
            mode='w+', 
            suffix='.csv', 
            delete=False,
            prefix='wallet_history_'
        )
        output_path = output_file.name
    
    # Write data to CSV file
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            writer.writerows(rows)
        
        return output_path
    except Exception as e:
        logger.error(f"Error writing historical wallet data to CSV: {e}")
        raise

async def wallet_real_time_updates(
    agent: Optional[str] = None, 
    symbol: Optional[str] = None,
    refresh_interval: int = 5,
    timeout: Optional[int] = None
) -> None:
    """
    Display real-time wallet balances with WebSocket updates.
    
    Args:
        agent: Optional agent to filter by
        symbol: Optional symbol to filter by
        refresh_interval: How often to refresh the display (seconds)
        timeout: Optional timeout to automatically exit after X seconds
    """
    stop_event = asyncio.Event()
    
    # Set up signal handlers to exit gracefully
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    
    def signal_handler(*args):
        logger.info("Received termination signal, shutting down...")
        stop_event.set()
        # Restore original handlers
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize Binance API client
    binance_client = BinanceAPIClient()
    
    # Initialize WebSocket client
    ws_client = BinanceWebSocketClient()
    account_update_received = asyncio.Event()
    
    # This will store the latest balance data
    latest_balances = []
    latest_prices = {}
    latest_ticker_24h = {}
    
    # Function to fetch initial data and set up WebSocket
    async def initialize_data():
        nonlocal latest_balances, latest_prices, latest_ticker_24h
        
        # Get initial balances
        balance_data = binance_client.get_balance()
        
        # Get initial price data
        price_data = binance_client.get_ticker_prices()
        latest_prices = {ticker['symbol']: float(ticker['price']) for ticker in price_data}
        
        # Extract assets with non-zero balances
        assets = []
        for asset in balance_data.get('balances', []):
            asset_symbol = asset.get('asset')
            free = float(asset.get('free', 0))
            locked = float(asset.get('locked', 0))
            total = free + locked
            
            if total > 0:
                assets.append(asset_symbol)
                
        # Get 24h ticker info for these assets
        asset_usdt_pairs = [f"{asset}USDT" for asset in assets if asset != "USDT"]
        ticker_24h_data = binance_client.get_24h_ticker_info(asset_usdt_pairs)
        latest_ticker_24h = {item['symbol']: item for item in ticker_24h_data}
        
        # Format the initial balances
        latest_balances = format_wallet_balances(balance_data, latest_prices, latest_ticker_24h)
        
        # Filter if required
        if symbol:
            latest_balances = [b for b in latest_balances if b['symbol'].lower() == symbol.lower()]
        
        # Connect to WebSocket for real-time updates
        # Subscribe to account update streams to get balance changes
        if binance_client.api_key and binance_client.api_secret:
            # Register event handler for account updates
            async def on_account_update(msg):
                nonlocal latest_balances, latest_prices, latest_ticker_24h
                logger.debug(f"Received account update: {msg}")
                
                # Extract updated balance
                if 'data' in msg and 'B' in msg['data']:
                    balances = msg['data']['B']
                    for balance in balances:
                        asset = balance.get('a')  # Asset name
                        free = float(balance.get('f', 0))  # Free amount
                        locked = float(balance.get('l', 0))  # Locked amount
                        
                        # Find and update this asset in latest_balances
                        for idx, bal in enumerate(latest_balances):
                            if bal['symbol'] == asset:
                                # Update the balance
                                latest_balances[idx]['free'] = free
                                latest_balances[idx]['locked'] = locked
                                latest_balances[idx]['total'] = free + locked
                                
                                # Update the value based on the latest price
                                price_key = f"{asset}USDT"
                                if price_key in latest_prices:
                                    latest_balances[idx]['value_usd'] = (free + locked) * latest_prices[price_key]
                                
                                # Recalculate allocations
                                total_value = sum(b['value_usd'] for b in latest_balances)
                                for b in latest_balances:
                                    b['allocation'] = (b['value_usd'] / total_value * 100) if total_value > 0 else 0
                    
                    # Sort by value
                    latest_balances.sort(key=lambda x: x['value_usd'], reverse=True)
                    account_update_received.set()
            
            # Register event handler for ticker updates (to update prices)
            async def on_ticker_update(msg):
                nonlocal latest_balances, latest_prices
                logger.debug(f"Received ticker update: {msg}")
                
                if 'data' in msg:
                    symbol = msg['data'].get('s')  # Symbol
                    price = float(msg['data'].get('c', 0))  # Close price
                    
                    if symbol:
                        # Update latest price
                        latest_prices[symbol] = price
                        
                        # Update value for any balances in this symbol
                        base_asset = symbol.replace('USDT', '')
                        for idx, bal in enumerate(latest_balances):
                            if bal['symbol'] == base_asset:
                                # Update price and value
                                latest_balances[idx]['price_usd'] = price
                                latest_balances[idx]['value_usd'] = bal['total'] * price
                                
                                # Recalculate allocations for all assets
                                total_value = sum(b['value_usd'] for b in latest_balances)
                                for b in latest_balances:
                                    b['allocation'] = (b['value_usd'] / total_value * 100) if total_value > 0 else 0
                                
                                break
            
            # Connect to WebSocket and subscribe to relevant streams
            await ws_client.connect()
            
            # Subscribe to user data stream for account updates
            await ws_client.subscribe("$userDataStream")
            
            # Subscribe to ticker streams for price updates for each asset
            ticker_streams = []
            for asset in assets:
                if asset != "USDT":  # Skip USDT as it's the quote currency
                    ticker_streams.append(f"{asset.lower()}usdt@ticker")
            
            # Subscribe to ticker streams in batches to avoid rate limits
            for i in range(0, len(ticker_streams), 10):
                batch = ticker_streams[i:i+10]
                for stream in batch:
                    await ws_client.subscribe(stream)
                await asyncio.sleep(1)  # Slight delay between batches
    
    # Function to format wallet balances from raw data
    def format_wallet_balances(
        balance_data: Dict[str, Any], 
        prices: Dict[str, float], 
        ticker_24h: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        formatted_balances = []
        
        # Calculate total value for allocation percentages
        total_value_usd = 0
        for asset in balance_data.get('balances', []):
            symbol_name = asset.get('asset')
            free = float(asset.get('free', 0))
            locked = float(asset.get('locked', 0))
            total = free + locked
            
            if total <= 0:
                continue
                
            price_key = f"{symbol_name}USDT"
            price = prices.get(price_key, 0)
            value_usd = total * price
            total_value_usd += value_usd
        
        # Create formatted balance records
        for asset in balance_data.get('balances', []):
            symbol_name = asset.get('asset')
            free = float(asset.get('free', 0))
            locked = float(asset.get('locked', 0))
            total = free + locked
            
            if total <= 0:
                continue
            
            price_key = f"{symbol_name}USDT"
            price = prices.get(price_key, 0)
            value_usd = total * price
            
            allocation = (value_usd / total_value_usd * 100) if total_value_usd > 0 else 0
            
            # Get 24h change
            change_24h = 0
            if price_key in ticker_24h:
                change_24h = float(ticker_24h[price_key].get('priceChangePercent', 0))
            
            balance_info = {
                'symbol': symbol_name,
                'free': free,
                'locked': locked,
                'total': total,
                'price_usd': price,
                'value_usd': value_usd,
                'allocation': allocation,
                'change_24h': change_24h
            }
            
            formatted_balances.append(balance_info)
        
        # Sort by value (descending)
        formatted_balances.sort(key=lambda x: x['value_usd'], reverse=True)
        
        return formatted_balances
    
    # Task to periodically update 24h ticker data
    async def update_ticker_24h():
        nonlocal latest_balances, latest_ticker_24h
        while not stop_event.is_set():
            try:
                # Get symbols from current balances
                symbols = [f"{b['symbol']}USDT" for b in latest_balances if b['symbol'] != "USDT"]
                
                # Update ticker data
                if symbols:
                    ticker_24h_data = binance_client.get_24h_ticker_info(symbols)
                    latest_ticker_24h = {item['symbol']: item for item in ticker_24h_data}
                    
                    # Update 24h change in balances
                    for idx, bal in enumerate(latest_balances):
                        price_key = f"{bal['symbol']}USDT"
                        if price_key in latest_ticker_24h:
                            latest_balances[idx]['change_24h'] = float(
                                latest_ticker_24h[price_key].get('priceChangePercent', 0)
                            )
            except Exception as e:
                logger.error(f"Error updating 24h ticker data: {e}")
            
            # Wait for next update (every 5 minutes)
            await asyncio.sleep(300)  # 5 minutes
    
    # Main display loop
    async def display_loop():
        # Initialize data and WebSocket connections
        await initialize_data()
        
        # Start ticker update task
        ticker_update_task = asyncio.create_task(update_ticker_24h())
        
        # Set timeout if specified
        if timeout:
            asyncio.create_task(
                asyncio.sleep(timeout).then(lambda: stop_event.set())
            )
        
        # Initial table creation
        table = display_wallet_table(latest_balances)
        
        # Create a Live context for updating the display
        with Live(table, refresh_per_second=4, console=console) as live:
            start_time = asyncio.get_event_loop().time()
            
            while not stop_event.is_set():
                # Check for account updates
                if account_update_received.is_set():
                    account_update_received.clear()
                
                # Regular refresh of the table
                current_time = asyncio.get_event_loop().time()
                elapsed = current_time - start_time
                
                # Update the table with latest data
                table = display_wallet_table(latest_balances)
                live.update(table)
                
                # Wait for the next refresh or an account update
                try:
                    # Wait for either the refresh interval or an account update
                    refresh_future = asyncio.create_task(asyncio.sleep(refresh_interval))
                    update_future = asyncio.create_task(account_update_received.wait())
                    
                    done, pending = await asyncio.wait(
                        [refresh_future, update_future],
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=refresh_interval
                    )
                    
                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in display loop: {e}")
                    await asyncio.sleep(refresh_interval)
        
        # Clean up
        ticker_update_task.cancel()
        await ws_client.disconnect()
    
    # Run the main display loop
    try:
        await display_loop()
    except Exception as e:
        logger.error(f"Error in wallet real-time updates: {e}")
    finally:
        # Make sure WebSocket is disconnected
        await ws_client.disconnect()

@pnl_group.command(name="wallet")
@click.option("--agent", "-a", default=None, help="Filter by agent name")
@click.option("--symbol", "-s", default=None, help="Filter by asset symbol")
@click.option("--csv", is_flag=True, help="Export results to CSV file")
@click.option("--output", "-o", type=click.Path(), help="Output file for CSV export (default: stdout)")
def wallet_command(agent, symbol, csv, output):
    """
    Display current wallet balances and asset information.
    
    Shows the current balances of all assets in your wallet with current market values.
    Colors indicate positive (green) or negative (red) 24h changes.
    
    Examples:
        botctl pnl wallet
        botctl pnl wallet --agent=trader1
        botctl pnl wallet --symbol=BTC
        botctl pnl wallet --csv --output=wallet.csv
        botctl pnl wallet --csv --output=-
    """
    try:
        balances = get_wallet_balances(agent=agent, symbol=symbol)
        if not balances:
            console.print("[yellow]No balances found with the specified filters.[/yellow]")
            return
        
        # Handle CSV export if requested
        if csv:
            try:
                csv_path = export_wallet_to_csv(balances, output)
                if csv_path != "stdout":
                    console.print(f"[green]Wallet balances exported to:[/green] {csv_path}")
            except Exception as e:
                logger.error(f"Error exporting wallet balances to CSV: {e}")
                console.print(f"[red]Error exporting wallet balances to CSV: {e}[/red]")
            return
        
        # Display the wallet table
        table = display_wallet_table(balances, console)
        console.print(table)
        
    except Exception as e:
        logger.error(f"Error displaying wallet: {e}")
        console.print(f"[red]Error displaying wallet: {e}[/red]")

@pnl_group.command(name="wallet-history")
@click.option('--agent', '-a', default=None, help='Filter by agent name')
@click.option('--symbol', '-s', default=None, help='Filter by asset symbol')
@click.option('--start-date', '-sd', default=None, help='Start date (YYYY-MM-DD)')
@click.option('--end-date', '-ed', default=None, help='End date (YYYY-MM-DD)')
@click.option("--csv", is_flag=True, help="Export results to CSV file")
@click.option("--output", "-o", type=click.Path(), help="Output file for CSV export (default: stdout)")
def wallet_history_command(agent, symbol, start_date, end_date, csv, output):
    """
    Display historical wallet balances.
    
    Shows wallet balance history over time with timestamps, allowing you to track
    changes in asset holdings and USD values.
    
    Examples:
        botctl pnl wallet-history
        botctl pnl wallet-history --start-date=2023-01-01 --end-date=2023-01-31
        botctl pnl wallet-history --agent=trader1 --symbol=BTC
        botctl pnl wallet-history --csv --output=wallet_history.csv
        botctl pnl wallet-history --csv --output=-
    """
    try:
        # Parse dates if provided
        start_date_obj = None
        end_date_obj = None
        
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                console.print("[red]Invalid start date format. Use YYYY-MM-DD.[/red]")
                return
                
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
                # Set to end of day
                end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
            except ValueError:
                console.print("[red]Invalid end date format. Use YYYY-MM-DD.[/red]")
                return
        
        # Get historical balances
        balances = get_historical_wallet_balances(
            agent=agent, 
            symbol=symbol,
            start_date=start_date_obj,
            end_date=end_date_obj
        )
        
        if not balances:
            console.print("[yellow]No historical balances found with the specified filters.[/yellow]")
            return
        
        # Handle CSV export if requested
        if csv:
            try:
                csv_path = export_wallet_history_to_csv(balances, output)
                if csv_path != "stdout":
                    console.print(f"[green]Historical wallet balances exported to:[/green] {csv_path}")
            except Exception as e:
                logger.error(f"Error exporting historical wallet balances to CSV: {e}")
                console.print(f"[red]Error exporting historical wallet balances to CSV: {e}[/red]")
            return
        
        # Create title based on date range
        title = "Historical Wallet Balances"
        if start_date and end_date:
            title = f"Wallet Balances ({start_date} to {end_date})"
        elif start_date:
            title = f"Wallet Balances (from {start_date})"
        elif end_date:
            title = f"Wallet Balances (until {end_date})"
            
        # Display the wallet table
        table = display_wallet_table(balances, console, title=title)
        console.print(table)
        
    except Exception as e:
        logger.error(f"Error displaying historical wallet: {e}")
        console.print(f"[red]Error displaying historical wallet: {e}[/red]")

@pnl_group.command(name="profit")
@click.option("--start-date", "-s", type=click.DateTime(formats=["%Y-%m-%d"]), 
              help="Start date for filtering (format: YYYY-MM-DD)")
@click.option("--end-date", "-e", type=click.DateTime(formats=["%Y-%m-%d"]), 
              help="End date for filtering (format: YYYY-MM-DD)")
@click.option("--agent", "-a", help="Filter by specific agent")
@click.option("--symbol", "-m", help="Filter by specific trading symbol")
@click.option("--period", "-p", type=click.Choice(["day", "week", "month", "all"]), 
              default="all", help="Time period aggregation (default: all)")
@click.option("--csv", is_flag=True, help="Export results to CSV file")
@click.option("--output", "-o", type=click.Path(), help="Output file for CSV export (default: stdout)")
def profit_command(start_date: Optional[datetime], end_date: Optional[datetime], 
                  agent: Optional[str], symbol: Optional[str], period: str,
                  csv: bool, output: Optional[str]):
    """
    Display profit metrics and statistics.
    
    Shows detailed profit information including total profit,
    win rate, average win/loss, and profit distribution over time.
    
    Examples:
        botctl pnl profit
        botctl pnl profit --start-date=2023-01-01 --end-date=2023-12-31
        botctl pnl profit --agent=trader1 --period=month
        botctl pnl profit --csv --output=profit_report.csv
    """
    try:
        # Initialize the PnL calculation service
        from ..services.pnl_calculation_service import PnLCalculationService, CalculationMethod
        from ..db.repositories import TradeRepository, PositionRepository
        from ..exchange.binance_api_client import BinanceAPIClient
        
        # Create repositories and clients
        trade_repository = TradeRepository()
        position_repository = PositionRepository()
        binance_client = BinanceAPIClient()
        
        # Create PnL calculation service
        pnl_service = PnLCalculationService(
            trade_repository=trade_repository,
            position_repository=position_repository,
            binance_client=binance_client,
            default_calculation_method=CalculationMethod.FIFO
        )
        
        # Set default date range if not provided
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            # Default to last 30 days if not specified
            start_date = end_date - timedelta(days=30)
        
        # Format dates for display
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        # Calculate PnL metrics
        pnl_metrics = pnl_service.calculate_pnl_metrics(
            symbol=symbol,
            start_time=start_date,
            end_time=end_date,
            calculation_method=CalculationMethod.FIFO
        )
        
        # Get time series data for the period
        time_series_data = get_time_series_data(
            pnl_service=pnl_service,
            start_date=start_date,
            end_date=end_date,
            period=period,
            symbol=symbol,
            agent=agent
        )
        
        # Display results in CSV format if requested
        if csv:
            export_pnl_to_csv(pnl_metrics, time_series_data, output)
            return
        
        # Display PnL Summary Panel
        display_pnl_summary(pnl_metrics, start_date_str, end_date_str, symbol, agent)
        
        # Display Trade Performance Table
        display_trade_performance(pnl_metrics)
        
        # Display Time Series Data
        if time_series_data:
            display_time_series(time_series_data, period)
        
        # Display PnL Distribution
        display_pnl_distribution(pnl_metrics)
        
    except Exception as e:
        logger.error(f"Error in profit command: {str(e)}", exc_info=True)
        console.print(f"[bold red]Error:[/bold red] {str(e)}", style="bold red")
        sys.exit(1)

def get_time_series_data(
    pnl_service: Any,
    start_date: datetime,
    end_date: datetime,
    period: str,
    symbol: Optional[str] = None,
    agent: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get time series data for PnL over time.
    
    Args:
        pnl_service: PnL calculation service instance
        start_date: Start date for filtering
        end_date: End date for filtering
        period: Time period aggregation (day, week, month, all)
        symbol: Filter by trading symbol
        agent: Filter by agent
        
    Returns:
        List of time series data points
    """
    # Set the time delta based on the period
    if period == "day":
        delta = timedelta(days=1)
        format_str = "%Y-%m-%d"
    elif period == "week":
        delta = timedelta(weeks=1)
        format_str = "%Y-%m-%d"
    elif period == "month":
        delta = timedelta(days=30)  # Approximate month
        format_str = "%Y-%m"
    else:  # all
        return []  # No time series for 'all' period
    
    # Generate time series dates
    time_series = []
    current_date = start_date
    cumulative_pnl = Decimal('0')
    
    while current_date <= end_date:
        next_date = current_date + delta
        
        # Calculate PnL for this period
        period_pnl = pnl_service.calculate_realized_pnl(
            symbol=symbol,
            start_time=current_date,
            end_time=next_date
        )
        
        # Add to cumulative PnL
        cumulative_pnl += period_pnl
        
        # Format date for period
        if period == "month":
            period_label = current_date.strftime("%b %Y")
        else:
            period_label = current_date.strftime(format_str)
        
        # Add data point
        time_series.append({
            "period": period_label,
            "pnl": float(period_pnl),
            "cumulative_pnl": float(cumulative_pnl)
        })
        
        # Move to next period
        current_date = next_date
    
    return time_series

def display_pnl_summary(
    pnl_metrics: Dict[str, Any],
    start_date: str,
    end_date: str,
    symbol: Optional[str] = None,
    agent: Optional[str] = None
) -> None:
    """
    Display a summary panel of PnL information.
    
    Args:
        pnl_metrics: Dictionary of PnL metrics
        start_date: Start date string
        end_date: End date string
        symbol: Symbol filter (if any)
        agent: Agent filter (if any)
    """
    # Create rich text for panel content
    summary_text = Text()
    
    # Date range
    summary_text.append("Period: ", style="dim")
    summary_text.append(f"{start_date} to {end_date}\n", style="bold")
    
    # Filters applied
    if symbol or agent:
        summary_text.append("Filters: ", style="dim")
        filters = []
        if symbol:
            filters.append(f"Symbol: {symbol}")
        if agent:
            filters.append(f"Agent: {agent}")
        summary_text.append(", ".join(filters) + "\n", style="bold")
    
    summary_text.append("\n")
    
    # Profit/Loss summary
    realized_pnl = pnl_metrics.get("realized_pnl", 0)
    unrealized_pnl = pnl_metrics.get("unrealized_pnl", 0)
    total_pnl = pnl_metrics.get("total_pnl", 0)
    
    pnl_style = "green" if total_pnl >= 0 else "red"
    
    summary_text.append("Realized P/L: ", style="dim")
    summary_text.append(f"${realized_pnl:,.2f}\n", 
                      style="green" if realized_pnl >= 0 else "red")
    
    summary_text.append("Unrealized P/L: ", style="dim")
    summary_text.append(f"${unrealized_pnl:,.2f}\n", 
                      style="green" if unrealized_pnl >= 0 else "red")
    
    summary_text.append("Total P/L: ", style="bold")
    summary_text.append(f"${total_pnl:,.2f}\n\n", style=f"bold {pnl_style}")
    
    # Create panel
    panel = Panel(
        summary_text,
        title="[bold]Profit/Loss Summary[/bold]",
        border_style="blue",
        padding=(1, 2)
    )
    
    # Display panel
    console.print(panel)

def display_trade_performance(pnl_metrics: Dict[str, Any]) -> None:
    """
    Display trade performance metrics in a table.
    
    Args:
        pnl_metrics: Dictionary of PnL metrics
    """
    # Create table with appropriate columns
    table = Table(
        title="Trade Performance Metrics",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold magenta"
    )
    
    # Add columns
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    # Extract metrics
    total_trades = pnl_metrics.get("total_trades", 0)
    winning_trades = pnl_metrics.get("winning_trades", 0)
    losing_trades = pnl_metrics.get("losing_trades", 0)
    win_rate = pnl_metrics.get("win_rate", 0)
    profit_factor = pnl_metrics.get("profit_factor", 0)
    avg_win = pnl_metrics.get("average_win", 0)
    avg_loss = pnl_metrics.get("average_loss", 0)
    max_drawdown = pnl_metrics.get("max_drawdown", 0)
    
    # Format profit factor (handle infinite case)
    if profit_factor == float('inf'):
        profit_factor_str = "∞"
    else:
        profit_factor_str = f"{profit_factor:.2f}"
    
    # Add rows
    table.add_row("Total Trades", str(total_trades))
    table.add_row("Winning Trades", f"{winning_trades} ({win_rate:.1f}%)")
    table.add_row("Losing Trades", str(losing_trades))
    table.add_row("Win Rate", f"{win_rate:.1f}%")
    table.add_row("Profit Factor", profit_factor_str)
    table.add_row(
        "Average Win", 
        f"${avg_win:,.2f}" if avg_win else "N/A",
        style="green" if avg_win > 0 else None
    )
    table.add_row(
        "Average Loss", 
        f"${avg_loss:,.2f}" if avg_loss else "N/A",
        style="red" if avg_loss < 0 else None
    )
    table.add_row(
        "Max Drawdown", 
        f"${max_drawdown:,.2f}" if max_drawdown else "N/A",
        style="red" if max_drawdown < 0 else None
    )
    
    # Display table
    console.print(table)

def display_time_series(time_series: List[Dict[str, Any]], period: str) -> None:
    """
    Display time series data as a table with sparklines.
    
    Args:
        time_series: List of time series data points
        period: Time period (day, week, month)
    """
    # Create table with appropriate columns
    period_label = "Day" if period == "day" else "Week" if period == "week" else "Month"
    
    table = Table(
        title=f"P/L by {period_label}",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold magenta"
    )
    
    # Add columns
    table.add_column(period_label, style="cyan")
    table.add_column("P/L", justify="right")
    table.add_column("Cumulative P/L", justify="right")
    table.add_column("Trend", justify="center")
    
    # Add rows for each time period
    pnl_values = [entry["pnl"] for entry in time_series]
    min_pnl = min(pnl_values) if pnl_values else 0
    max_pnl = max(pnl_values) if pnl_values else 0
    range_pnl = max(abs(min_pnl), abs(max_pnl))
    
    # For sparkline calculation
    cumulative_values = []
    
    for entry in time_series:
        period_label = entry["period"]
        pnl = entry["pnl"]
        cumulative_pnl = entry["cumulative_pnl"]
        
        # Add to cumulative values for sparkline
        cumulative_values.append(cumulative_pnl)
        
        # Determine color based on PnL
        pnl_color = "green" if pnl >= 0 else "red"
        cumulative_color = "green" if cumulative_pnl >= 0 else "red"
        
        # Create sparkline for current point
        if len(cumulative_values) > 1:
            # Normalize values for sparkline (between 0 and 1)
            spark_values = []
            min_val = min(cumulative_values)
            max_val = max(cumulative_values)
            range_val = max_val - min_val if max_val > min_val else 1
            
            for val in cumulative_values:
                normalized = (val - min_val) / range_val
                spark_values.append(normalized)
            
            # Create sparkline using rich's Sparkline
            sparkline = Text("".join("█" for _ in spark_values[-10:]))
        else:
            sparkline = Text("▁")
        
        # Add row
        table.add_row(
            period_label,
            f"[{pnl_color}]${pnl:,.2f}[/{pnl_color}]",
            f"[{cumulative_color}]${cumulative_pnl:,.2f}[/{cumulative_color}]",
            sparkline
        )
    
    # Display table
    console.print(table)

def display_pnl_distribution(pnl_metrics: Dict[str, Any]) -> None:
    """
    Display a visual representation of PnL distribution.
    
    Args:
        pnl_metrics: Dictionary of PnL metrics
    """
    # Extract distribution data if available
    if "pnl_distribution" not in pnl_metrics:
        return
    
    distribution = pnl_metrics.get("pnl_distribution", {})
    if not distribution:
        return
    
    # Create table
    table = Table(
        title="P/L Distribution",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold magenta"
    )
    
    # Add columns
    table.add_column("Range", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Distribution", justify="left")
    
    # Add rows for each distribution range
    max_count = max(distribution.values()) if distribution else 0
    
    for range_key, count in sorted(distribution.items()):
        if max_count > 0:
            bar_width = int((count / max_count) * 20)
            bar = "█" * bar_width
            bar_color = "green" if "-" not in range_key else "red"
        else:
            bar = ""
            bar_color = "white"
        
        table.add_row(
            range_key,
            str(count),
            f"[{bar_color}]{bar}[/{bar_color}]"
        )
    
    # Display table
    console.print(table)

def export_pnl_to_csv(
    pnl_metrics: Dict[str, Any],
    time_series: List[Dict[str, Any]],
    output_path: Optional[str]
) -> None:
    """
    Export PnL metrics to CSV file.
    
    Args:
        pnl_metrics: PnL metrics dictionary
        time_series: Time series data
        output_path: Output file path (or None for stdout)
    """
    # Create CSV content
    csv_data = []
    
    # Add summary metrics
    csv_data.append(["Profit/Loss Summary"])
    csv_data.append(["Metric", "Value"])
    csv_data.append(["Realized P/L", f"{pnl_metrics.get('realized_pnl', 0):.2f}"])
    csv_data.append(["Unrealized P/L", f"{pnl_metrics.get('unrealized_pnl', 0):.2f}"])
    csv_data.append(["Total P/L", f"{pnl_metrics.get('total_pnl', 0):.2f}"])
    csv_data.append([""])
    
    # Add performance metrics
    csv_data.append(["Trade Performance Metrics"])
    csv_data.append(["Metric", "Value"])
    csv_data.append(["Total Trades", pnl_metrics.get("total_trades", 0)])
    csv_data.append(["Winning Trades", pnl_metrics.get("winning_trades", 0)])
    csv_data.append(["Losing Trades", pnl_metrics.get("losing_trades", 0)])
    csv_data.append(["Win Rate", f"{pnl_metrics.get('win_rate', 0):.2f}%"])
    
    # Handle possible infinity for profit factor
    profit_factor = pnl_metrics.get("profit_factor", 0)
    profit_factor_str = "∞" if profit_factor == float('inf') else f"{profit_factor:.2f}"
    csv_data.append(["Profit Factor", profit_factor_str])
    
    csv_data.append(["Average Win", f"{pnl_metrics.get('average_win', 0):.2f}"])
    csv_data.append(["Average Loss", f"{pnl_metrics.get('average_loss', 0):.2f}"])
    csv_data.append(["Max Drawdown", f"{pnl_metrics.get('max_drawdown', 0):.2f}"])
    csv_data.append([""])
    
    # Add time series data if available
    if time_series:
        csv_data.append(["Time Series Data"])
        csv_data.append(["Period", "P/L", "Cumulative P/L"])
        for entry in time_series:
            csv_data.append([
                entry["period"],
                f"{entry['pnl']:.2f}",
                f"{entry['cumulative_pnl']:.2f}"
            ])
    
    # Write to file or stdout
    if output_path:
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)
        console.print(f"[green]Export complete:[/green] PnL data saved to {output_path}")
    else:
        # Write to stdout
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        console.print(output.getvalue())

@pnl_group.command(name="loss")
@click.option("--start-date", "-s", type=click.DateTime(formats=["%Y-%m-%d"]), 
              help="Start date for filtering (format: YYYY-MM-DD)")
@click.option("--end-date", "-e", type=click.DateTime(formats=["%Y-%m-%d"]), 
              help="End date for filtering (format: YYYY-MM-DD)")
@click.option("--agent", "-a", help="Filter by specific agent")
@click.option("--symbol", "-m", help="Filter by specific trading symbol")
@click.option("--limit", "-l", type=int, default=10,
              help="Limit number of results (default: 10)")
@click.option("--csv", is_flag=True, help="Export results to CSV file")
@click.option("--output", "-o", type=click.Path(), help="Output file for CSV export (default: stdout)")
def loss_command(start_date: Optional[datetime], end_date: Optional[datetime], 
                agent: Optional[str], symbol: Optional[str], limit: int,
                csv: bool, output: Optional[str]):
    """
    Display loss information and worst trades.
    
    Shows detailed information about losing trades, including largest losses,
    loss statistics, and worst performing symbols/strategies.
    
    Examples:
        botctl pnl loss
        botctl pnl loss --limit=20
        botctl pnl loss --agent=trader1 --symbol=BTCUSDT
        botctl pnl loss --csv --output=loss_report.csv
    """
    try:
        # Initialize the PnL calculation service
        from ..services.pnl_calculation_service import PnLCalculationService, CalculationMethod
        from ..db.repositories import TradeRepository, PositionRepository
        from ..exchange.binance_api_client import BinanceAPIClient
        
        # Create repositories and clients
        trade_repository = TradeRepository()
        position_repository = PositionRepository()
        binance_client = BinanceAPIClient()
        
        # Create PnL calculation service
        pnl_service = PnLCalculationService(
            trade_repository=trade_repository,
            position_repository=position_repository,
            binance_client=binance_client,
            default_calculation_method=CalculationMethod.FIFO
        )
        
        # Set default date range if not provided
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            # Default to last 30 days if not specified
            start_date = end_date - timedelta(days=30)
        
        # Format dates for display
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        # Fetch losing trades for the specified period
        losing_trades = get_losing_trades(
            pnl_service=pnl_service,
            start_date=start_date,
            end_date=end_date,
            symbol=symbol,
            agent=agent,
            limit=limit
        )
        
        # Get loss statistics
        loss_stats = calculate_loss_statistics(losing_trades)
        
        # Get worst performing symbols
        symbol_performance = get_symbol_performance(
            pnl_service=pnl_service,
            start_date=start_date,
            end_date=end_date,
            agent=agent,
            limit=5  # Show top 5 worst performing symbols
        )
        
        # Display results in CSV format if requested
        if csv:
            export_loss_to_csv(loss_stats, losing_trades, symbol_performance, output)
            return
        
        # Display Loss Summary Panel
        display_loss_summary(loss_stats, start_date_str, end_date_str, symbol, agent)
        
        # Display Worst Trades Table
        if losing_trades:
            display_worst_trades(losing_trades, limit)
        else:
            console.print("[yellow]No losing trades found for the specified period.[/yellow]")
        
        # Display Symbol Performance
        if symbol_performance:
            display_symbol_performance(symbol_performance)
        
    except Exception as e:
        logger.error(f"Error in loss command: {str(e)}", exc_info=True)
        console.print(f"[bold red]Error:[/bold red] {str(e)}", style="bold red")
        sys.exit(1)

def get_losing_trades(
    pnl_service: Any,
    start_date: datetime,
    end_date: datetime,
    symbol: Optional[str] = None,
    agent: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get worst losing trades for the specified period.
    
    Args:
        pnl_service: PnL calculation service instance
        start_date: Start date for filtering
        end_date: End date for filtering
        symbol: Filter by trading symbol
        agent: Filter by agent
        limit: Maximum number of trades to return
        
    Returns:
        List of losing trades sorted by PnL (worst first)
    """
    # Get all trades for the period
    trades = pnl_service.get_trade_data(symbol, start_date, end_date)
    
    # Filter for losing trades
    losing_trades = []
    for trade in trades:
        # Check if agent filter applies
        if agent and trade.agent_id != agent:
            continue
            
        # Check if it's a losing trade
        if hasattr(trade, 'net_pnl') and trade.net_pnl < 0:
            losing_trade = {
                'id': trade.id,
                'symbol': trade.symbol,
                'open_time': trade.open_time,
                'close_time': trade.close_time,
                'direction': trade.direction,
                'size': float(trade.size) if hasattr(trade, 'size') else 0,
                'entry_price': float(trade.open_price) if hasattr(trade, 'open_price') else 0,
                'exit_price': float(trade.close_price) if hasattr(trade, 'close_price') else 0,
                'pnl': float(trade.net_pnl),
                'fees': float(trade.fees) if hasattr(trade, 'fees') else 0,
                'agent_id': trade.agent_id if hasattr(trade, 'agent_id') else None
            }
            losing_trades.append(losing_trade)
    
    # Sort by PnL (worst first)
    losing_trades.sort(key=lambda x: x['pnl'])
    
    # Limit the number of results
    return losing_trades[:limit]

def calculate_loss_statistics(losing_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate loss statistics from losing trades.
    
    Args:
        losing_trades: List of losing trades
        
    Returns:
        Dictionary with loss statistics
    """
    if not losing_trades:
        return {
            'total_losses': 0,
            'total_loss_amount': 0,
            'average_loss': 0,
            'max_loss': 0,
            'losing_streaks': {
                'current': 0,
                'longest': 0,
                'average': 0
            },
            'total_fees': 0
        }
    
    # Calculate basic statistics
    total_loss_amount = sum(trade['pnl'] for trade in losing_trades)
    average_loss = total_loss_amount / len(losing_trades)
    max_loss = min(trade['pnl'] for trade in losing_trades)
    total_fees = sum(trade['fees'] for trade in losing_trades)
    
    # Sort trades by time to calculate streaks
    sorted_trades = sorted(losing_trades, key=lambda x: x['open_time'])
    
    # Calculate losing streaks
    streaks = []
    current_streak = 1
    
    for i in range(1, len(sorted_trades)):
        # If consecutive trades, increment streak
        if sorted_trades[i]['open_time'] - sorted_trades[i-1]['close_time'] < timedelta(days=1):
            current_streak += 1
        else:
            streaks.append(current_streak)
            current_streak = 1
    
    # Add the last streak
    streaks.append(current_streak)
    
    # Calculate streak statistics
    longest_streak = max(streaks) if streaks else 0
    average_streak = sum(streaks) / len(streaks) if streaks else 0
    
    return {
        'total_losses': len(losing_trades),
        'total_loss_amount': total_loss_amount,
        'average_loss': average_loss,
        'max_loss': max_loss,
        'losing_streaks': {
            'current': current_streak,
            'longest': longest_streak,
            'average': average_streak
        },
        'total_fees': total_fees
    }

def get_symbol_performance(
    pnl_service: Any,
    start_date: datetime,
    end_date: datetime,
    agent: Optional[str] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Get worst performing symbols for the specified period.
    
    Args:
        pnl_service: PnL calculation service instance
        start_date: Start date for filtering
        end_date: End date for filtering
        agent: Filter by agent
        limit: Maximum number of symbols to return
        
    Returns:
        List of symbol performance data sorted by PnL (worst first)
    """
    # Get all trades for the period
    trades = pnl_service.get_trade_data(None, start_date, end_date)
    
    # Calculate PnL by symbol
    symbol_pnl = {}
    for trade in trades:
        # Check if agent filter applies
        if agent and trade.agent_id != agent:
            continue
            
        # Add trade PnL to symbol total
        symbol = trade.symbol
        if symbol not in symbol_pnl:
            symbol_pnl[symbol] = {
                'symbol': symbol,
                'total_pnl': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_trades': 0
            }
        
        symbol_pnl[symbol]['total_pnl'] += float(trade.net_pnl) if hasattr(trade, 'net_pnl') else 0
        symbol_pnl[symbol]['total_trades'] += 1
        
        # Count winning/losing trades
        if hasattr(trade, 'net_pnl'):
            if trade.net_pnl >= 0:
                symbol_pnl[symbol]['winning_trades'] += 1
            else:
                symbol_pnl[symbol]['losing_trades'] += 1
    
    # Convert to list and calculate win rate
    symbol_performance = []
    for symbol, data in symbol_pnl.items():
        if data['total_trades'] > 0:
            data['win_rate'] = (data['winning_trades'] / data['total_trades']) * 100
        else:
            data['win_rate'] = 0
        symbol_performance.append(data)
    
    # Sort by PnL (worst first)
    symbol_performance.sort(key=lambda x: x['total_pnl'])
    
    # Limit the number of results
    return symbol_performance[:limit]

def display_loss_summary(
    loss_stats: Dict[str, Any],
    start_date: str,
    end_date: str,
    symbol: Optional[str] = None,
    agent: Optional[str] = None
) -> None:
    """
    Display a summary panel of loss information.
    
    Args:
        loss_stats: Dictionary of loss statistics
        start_date: Start date string
        end_date: End date string
        symbol: Symbol filter (if any)
        agent: Agent filter (if any)
    """
    # Create rich text for panel content
    summary_text = Text()
    
    # Date range
    summary_text.append("Period: ", style="dim")
    summary_text.append(f"{start_date} to {end_date}\n", style="bold")
    
    # Filters applied
    if symbol or agent:
        summary_text.append("Filters: ", style="dim")
        filters = []
        if symbol:
            filters.append(f"Symbol: {symbol}")
        if agent:
            filters.append(f"Agent: {agent}")
        summary_text.append(", ".join(filters) + "\n", style="bold")
    
    summary_text.append("\n")
    
    # Loss summary
    total_losses = loss_stats.get('total_losses', 0)
    total_loss_amount = loss_stats.get('total_loss_amount', 0)
    average_loss = loss_stats.get('average_loss', 0)
    max_loss = loss_stats.get('max_loss', 0)
    
    summary_text.append("Total Losing Trades: ", style="dim")
    summary_text.append(f"{total_losses}\n", style="bold")
    
    summary_text.append("Total Loss Amount: ", style="dim")
    summary_text.append(f"${total_loss_amount:,.2f}\n", style="bold red")
    
    summary_text.append("Average Loss: ", style="dim")
    summary_text.append(f"${average_loss:,.2f}\n", style="bold red")
    
    summary_text.append("Maximum Single Loss: ", style="dim")
    summary_text.append(f"${max_loss:,.2f}\n", style="bold red")
    
    # Losing streak information
    streak_data = loss_stats.get('losing_streaks', {})
    current_streak = streak_data.get('current', 0)
    longest_streak = streak_data.get('longest', 0)
    
    summary_text.append("\nLosing Streaks:\n", style="dim")
    summary_text.append(f"Current: {current_streak} trades\n", style="bold")
    summary_text.append(f"Longest: {longest_streak} trades\n", style="bold")
    
    # Create panel
    panel = Panel(
        summary_text,
        title="[bold]Loss Analysis Summary[/bold]",
        border_style="red",
        padding=(1, 2)
    )
    
    # Display panel
    console.print(panel)

def display_worst_trades(losing_trades: List[Dict[str, Any]], limit: int) -> None:
    """
    Display worst trades in a table.
    
    Args:
        losing_trades: List of losing trades
        limit: Maximum number of trades to display
    """
    # Create table with appropriate columns
    table = Table(
        title=f"Worst {limit} Trades",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold magenta"
    )
    
    # Add columns
    table.add_column("ID", style="dim")
    table.add_column("Symbol", style="cyan")
    table.add_column("Direction", style="cyan")
    table.add_column("Entry", justify="right")
    table.add_column("Exit", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("P/L", justify="right", style="red")
    table.add_column("Date", justify="right")
    
    # Add rows for each trade
    for trade in losing_trades:
        # Format trade data
        trade_id = str(trade['id'])
        symbol = trade['symbol']
        direction = trade['direction'].upper()
        entry_price = f"${trade['entry_price']:,.2f}"
        exit_price = f"${trade['exit_price']:,.2f}"
        size = f"{trade['size']:.4f}"
        pnl = f"${trade['pnl']:,.2f}"
        
        # Format date
        if trade['close_time']:
            date_str = trade['close_time'].strftime("%Y-%m-%d")
        else:
            date_str = trade['open_time'].strftime("%Y-%m-%d")
        
        # Style for direction
        direction_style = "green" if direction == "BUY" else "red"
        
        # Add row
        table.add_row(
            trade_id,
            symbol,
            f"[{direction_style}]{direction}[/{direction_style}]",
            entry_price,
            exit_price,
            size,
            pnl,
            date_str
        )
    
    # Display table
    console.print(table)

def display_symbol_performance(symbol_performance: List[Dict[str, Any]]) -> None:
    """
    Display symbol performance in a table.
    
    Args:
        symbol_performance: List of symbol performance data
    """
    # Create table with appropriate columns
    table = Table(
        title="Worst Performing Symbols",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold magenta"
    )
    
    # Add columns
    table.add_column("Symbol", style="cyan")
    table.add_column("Total P/L", justify="right", style="red")
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Performance", justify="left")
    
    # Add rows for each symbol
    for symbol_data in symbol_performance:
        # Format symbol data
        symbol = symbol_data['symbol']
        total_pnl = symbol_data['total_pnl']
        total_trades = symbol_data['total_trades']
        win_rate = symbol_data['win_rate']
        
        # Create visual performance bar
        if total_pnl < 0:
            # Scale for visualization (max bar width of 20 chars)
            worst_pnl = min(s['total_pnl'] for s in symbol_performance)
            if worst_pnl < 0:
                bar_width = int(abs(total_pnl / worst_pnl) * 20)
                performance_bar = "█" * bar_width
            else:
                performance_bar = ""
        else:
            performance_bar = ""
        
        # Add row
        table.add_row(
            symbol,
            f"${total_pnl:,.2f}",
            str(total_trades),
            f"{win_rate:.1f}%",
            f"[red]{performance_bar}[/red]"
        )
    
    # Display table
    console.print(table)

def export_loss_to_csv(
    loss_stats: Dict[str, Any],
    losing_trades: List[Dict[str, Any]],
    symbol_performance: List[Dict[str, Any]],
    output_path: Optional[str]
) -> None:
    """
    Export loss data to CSV file.
    
    Args:
        loss_stats: Dictionary of loss statistics
        losing_trades: List of losing trades
        symbol_performance: List of symbol performance data
        output_path: Output file path (or None for stdout)
    """
    # Create CSV content
    csv_data = []
    
    # Add loss summary
    csv_data.append(["Loss Analysis Summary"])
    csv_data.append(["Metric", "Value"])
    csv_data.append(["Total Losing Trades", loss_stats.get('total_losses', 0)])
    csv_data.append(["Total Loss Amount", f"{loss_stats.get('total_loss_amount', 0):.2f}"])
    csv_data.append(["Average Loss", f"{loss_stats.get('average_loss', 0):.2f}"])
    csv_data.append(["Maximum Single Loss", f"{loss_stats.get('max_loss', 0):.2f}"])
    csv_data.append(["Current Losing Streak", loss_stats.get('losing_streaks', {}).get('current', 0)])
    csv_data.append(["Longest Losing Streak", loss_stats.get('losing_streaks', {}).get('longest', 0)])
    csv_data.append([""])
    
    # Add worst trades
    if losing_trades:
        csv_data.append(["Worst Trades"])
        csv_data.append(["ID", "Symbol", "Direction", "Entry Price", "Exit Price", "Size", "P/L", "Date"])
        
        for trade in losing_trades:
            # Format date
            if trade['close_time']:
                date_str = trade['close_time'].strftime("%Y-%m-%d")
            else:
                date_str = trade['open_time'].strftime("%Y-%m-%d")
                
            csv_data.append([
                trade['id'],
                trade['symbol'],
                trade['direction'],
                f"{trade['entry_price']:.2f}",
                f"{trade['exit_price']:.2f}",
                f"{trade['size']:.4f}",
                f"{trade['pnl']:.2f}",
                date_str
            ])
        
        csv_data.append([""])
    
    # Add symbol performance
    if symbol_performance:
        csv_data.append(["Worst Performing Symbols"])
        csv_data.append(["Symbol", "Total P/L", "Total Trades", "Win Rate"])
        
        for symbol_data in symbol_performance:
            csv_data.append([
                symbol_data['symbol'],
                f"{symbol_data['total_pnl']:.2f}",
                symbol_data['total_trades'],
                f"{symbol_data['win_rate']:.1f}%"
            ])
    
    # Write to file or stdout
    if output_path:
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)
        console.print(f"[green]Export complete:[/green] Loss data saved to {output_path}")
    else:
        # Write to stdout
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        console.print(output.getvalue())

def register_commands(cli_group):
    """Register all PNL commands with the main CLI."""
    cli_group.add_command(pnl_group) 