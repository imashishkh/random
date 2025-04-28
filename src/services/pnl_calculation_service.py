import logging
import datetime
from typing import Dict, List, Optional, Tuple, Union, Any
from decimal import Decimal
from enum import Enum
import time
from functools import lru_cache
import threading

from ..analytics.data_models import Trade, TradeDirection, PerformanceTimePeriod
from ..exchange.binance_api_client import BinanceAPIClient
from ..db.repositories import TradeRepository, PositionRepository

logger = logging.getLogger(__name__)

class CalculationMethod(str, Enum):
    """Enum for PnL calculation methods"""
    FIFO = "fifo"  # First-In-First-Out
    LIFO = "lifo"  # Last-In-First-Out
    AVERAGE_COST = "average_cost"  # Average cost basis


class PnLCalculationService:
    """Service for calculating profit/loss metrics from trading activity"""
    
    def __init__(
        self, 
        trade_repository: Optional[TradeRepository] = None,
        position_repository: Optional[PositionRepository] = None,
        binance_client: Optional[BinanceAPIClient] = None,
        default_calculation_method: CalculationMethod = CalculationMethod.FIFO,
        cache_ttl: int = 300  # Cache time-to-live in seconds
    ):
        """Initialize the PnL calculation service
        
        Args:
            trade_repository: Repository for accessing trade data from local database
            position_repository: Repository for accessing position data from local database
            binance_client: Client for accessing Binance API data
            default_calculation_method: Default method for calculating PnL
            cache_ttl: Time-to-live for cached data in seconds
        """
        self.trade_repository = trade_repository
        self.position_repository = position_repository
        self.binance_client = binance_client
        self.default_calculation_method = default_calculation_method
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_lock = threading.RLock()
        
        # Initialize calculation strategy factories
        self._strategies = {
            CalculationMethod.FIFO: self._calculate_fifo,
            CalculationMethod.LIFO: self._calculate_lifo,
            CalculationMethod.AVERAGE_COST: self._calculate_average_cost
        }
        
        logger.info("PnL calculation service initialized")
    
    def get_trade_data(
        self, 
        symbol: Optional[str] = None, 
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        limit: int = 1000,
        force_refresh: bool = False
    ) -> List[Trade]:
        """Fetch combined trade data from database and Binance API
        
        Args:
            symbol: Filter by trading symbol (e.g., 'BTCUSDT')
            start_time: Filter by trade start time
            end_time: Filter by trade end time
            limit: Maximum number of trades to return
            force_refresh: Force refreshing the cache
            
        Returns:
            List of Trade objects representing combined and deduplicated trade data
        """
        cache_key = f"trades_{symbol}_{start_time}_{end_time}_{limit}"
        
        # Check cache if not forcing refresh
        if not force_refresh:
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                return cached_data
        
        # Fetch data from local database
        db_trades = []
        if self.trade_repository:
            db_trades = self.trade_repository.get_trades(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
        
        # Fetch data from Binance API
        api_trades = []
        if self.binance_client:
            try:
                api_trades = self.binance_client.get_my_trades(
                    symbol=symbol,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit
                )
            except Exception as e:
                logger.error(f"Error fetching trades from Binance API: {e}")
        
        # Merge and deduplicate trades
        combined_trades = self._merge_and_deduplicate_trades(db_trades, api_trades)
        
        # Cache the results
        self._add_to_cache(cache_key, combined_trades)
        
        return combined_trades
    
    def calculate_realized_pnl(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        calculation_method: Optional[CalculationMethod] = None,
        include_fees: bool = True
    ) -> Decimal:
        """Calculate realized profit/loss for closed positions
        
        Args:
            symbol: Filter by trading symbol
            start_time: Filter by trade start time
            end_time: Filter by trade end time
            calculation_method: Method to use for PnL calculation
            include_fees: Whether to include fees in the calculation
            
        Returns:
            Decimal value representing realized PnL
        """
        method = calculation_method or self.default_calculation_method
        trades = self.get_trade_data(symbol, start_time, end_time)
        
        # Use the appropriate strategy for calculations
        calculation_func = self._strategies.get(method, self._calculate_fifo)
        return calculation_func(trades, include_fees=include_fees, unrealized=False)
    
    def calculate_unrealized_pnl(
        self,
        symbol: Optional[str] = None,
        calculation_method: Optional[CalculationMethod] = None,
        include_fees: bool = True
    ) -> Decimal:
        """Calculate unrealized profit/loss for open positions
        
        Args:
            symbol: Filter by trading symbol
            calculation_method: Method to use for PnL calculation
            include_fees: Whether to include fees in the calculation
            
        Returns:
            Decimal value representing unrealized PnL
        """
        method = calculation_method or self.default_calculation_method
        
        # For unrealized PnL, we need current positions and market prices
        open_positions = self._get_open_positions(symbol)
        if not open_positions:
            return Decimal('0')
        
        # Get current market prices
        market_prices = self._get_current_market_prices([pos['symbol'] for pos in open_positions])
        
        # Use the appropriate strategy for calculations
        calculation_func = self._strategies.get(method, self._calculate_fifo)
        
        # Get all trades for the positions
        all_trades = []
        for pos in open_positions:
            symbol_trades = self.get_trade_data(symbol=pos['symbol'])
            all_trades.extend(symbol_trades)
        
        return calculation_func(all_trades, include_fees=include_fees, unrealized=True, 
                              market_prices=market_prices)
    
    def calculate_total_pnl(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        calculation_method: Optional[CalculationMethod] = None,
        include_fees: bool = True
    ) -> Decimal:
        """Calculate total profit/loss (realized + unrealized)
        
        Args:
            symbol: Filter by trading symbol
            start_time: Filter by trade start time
            end_time: Filter by trade end time
            calculation_method: Method to use for PnL calculation
            include_fees: Whether to include fees in the calculation
            
        Returns:
            Decimal value representing total PnL
        """
        realized = self.calculate_realized_pnl(
            symbol, start_time, end_time, calculation_method, include_fees
        )
        unrealized = self.calculate_unrealized_pnl(
            symbol, calculation_method, include_fees
        )
        return realized + unrealized
    
    def calculate_pnl_metrics(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        calculation_method: Optional[CalculationMethod] = None
    ) -> Dict[str, Any]:
        """Calculate comprehensive PnL metrics
        
        Args:
            symbol: Filter by trading symbol
            start_time: Filter by trade start time
            end_time: Filter by trade end time
            calculation_method: Method to use for PnL calculation
            
        Returns:
            Dictionary containing various PnL metrics
        """
        trades = self.get_trade_data(symbol, start_time, end_time)
        
        # Calculate basic metrics
        realized_pnl = self.calculate_realized_pnl(symbol, start_time, end_time, calculation_method)
        unrealized_pnl = self.calculate_unrealized_pnl(symbol, calculation_method)
        total_pnl = realized_pnl + unrealized_pnl
        
        # Calculate win rate
        winning_trades = [t for t in trades if t.is_winning]
        win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
        
        # Calculate average win/loss
        avg_win = sum([t.net_pnl for t in winning_trades]) / len(winning_trades) if winning_trades else 0
        losing_trades = [t for t in trades if not t.is_winning]
        avg_loss = sum([t.net_pnl for t in losing_trades]) / len(losing_trades) if losing_trades else 0
        
        # Calculate maximum drawdown
        max_drawdown, drawdown_start, drawdown_end = self._calculate_max_drawdown(trades)
        
        # Calculate profit factor
        gross_profit = sum([t.net_pnl for t in winning_trades]) if winning_trades else 0
        gross_loss = abs(sum([t.net_pnl for t in losing_trades])) if losing_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        return {
            'realized_pnl': float(realized_pnl),
            'unrealized_pnl': float(unrealized_pnl),
            'total_pnl': float(total_pnl),
            'win_rate': win_rate,
            'average_win': float(avg_win),
            'average_loss': float(avg_loss),
            'max_drawdown': float(max_drawdown),
            'drawdown_start': drawdown_start,
            'drawdown_end': drawdown_end,
            'profit_factor': profit_factor,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'total_trades': len(trades),
            'calculation_method': calculation_method.value if calculation_method else self.default_calculation_method.value,
            'timestamp': datetime.datetime.now()
        }
    
    def schedule_recalculation(self, interval_seconds: int = 300) -> None:
        """Schedule periodic recalculation of unrealized PnL
        
        Args:
            interval_seconds: Time interval between recalculations in seconds
        """
        def recalculation_job():
            while True:
                try:
                    logger.info("Running scheduled PnL recalculation")
                    # Force refresh trade data
                    self.get_trade_data(force_refresh=True)
                    # Recalculate unrealized PnL for open positions
                    self.calculate_unrealized_pnl()
                    logger.info("Scheduled PnL recalculation completed")
                except Exception as e:
                    logger.error(f"Error in scheduled PnL recalculation: {e}")
                
                time.sleep(interval_seconds)
        
        # Start recalculation thread
        thread = threading.Thread(target=recalculation_job, daemon=True)
        thread.start()
        logger.info(f"PnL recalculation scheduled every {interval_seconds} seconds")
    
    def _merge_and_deduplicate_trades(self, db_trades: List[Trade], api_trades: List[Trade]) -> List[Trade]:
        """Merge and deduplicate trades from different sources
        
        Args:
            db_trades: Trades from local database
            api_trades: Trades from API
            
        Returns:
            Deduplicated and merged list of trades
        """
        # Create a lookup for trades by ID to detect duplicates
        trade_lookup = {}
        
        # Add database trades to lookup
        for trade in db_trades:
            trade_lookup[trade.id] = trade
        
        # Add API trades, ignoring duplicates
        for trade in api_trades:
            if trade.id not in trade_lookup:
                trade_lookup[trade.id] = trade
        
        # Return deduplicated trades, sorted by close time
        return sorted(trade_lookup.values(), key=lambda t: t.close_time)
    
    def _get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get current open positions
        
        Args:
            symbol: Filter by trading symbol
            
        Returns:
            List of open position data
        """
        positions = []
        
        # Try to get positions from database
        if self.position_repository:
            positions = self.position_repository.get_open_positions(symbol=symbol)
        
        # If no positions from database, try to get from Binance API
        if not positions and self.binance_client:
            try:
                api_positions = self.binance_client.get_positions(symbol=symbol)
                positions = [
                    {
                        'symbol': pos['symbol'],
                        'size': Decimal(str(pos['positionAmt'])),
                        'entry_price': Decimal(str(pos['entryPrice'])),
                        'mark_price': Decimal(str(pos['markPrice'])),
                        'unrealized_pnl': Decimal(str(pos['unrealizedProfit'])),
                        'leverage': int(pos['leverage'])
                    }
                    for pos in api_positions if float(pos['positionAmt']) != 0
                ]
            except Exception as e:
                logger.error(f"Error fetching positions from Binance API: {e}")
        
        return positions
    
    def _get_current_market_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """Get current market prices for symbols
        
        Args:
            symbols: List of symbols to get prices for
            
        Returns:
            Dictionary mapping symbols to current prices
        """
        prices = {}
        
        if self.binance_client:
            try:
                api_prices = self.binance_client.get_ticker(symbols=symbols)
                prices = {
                    price['symbol']: Decimal(str(price['lastPrice']))
                    for price in api_prices
                }
            except Exception as e:
                logger.error(f"Error fetching prices from Binance API: {e}")
        
        return prices
    
    def _calculate_fifo(
        self, 
        trades: List[Trade], 
        include_fees: bool = True, 
        unrealized: bool = False,
        market_prices: Optional[Dict[str, Decimal]] = None
    ) -> Decimal:
        """Calculate PnL using First-In-First-Out method
        
        Args:
            trades: List of trades to calculate PnL for
            include_fees: Whether to include fees in the calculation
            unrealized: Whether to include unrealized PnL
            market_prices: Current market prices for symbols (required for unrealized PnL)
            
        Returns:
            Decimal value representing PnL
        """
        # Group trades by symbol
        trades_by_symbol = {}
        for trade in trades:
            if trade.symbol not in trades_by_symbol:
                trades_by_symbol[trade.symbol] = []
            trades_by_symbol[trade.symbol].append(trade)
        
        total_pnl = Decimal('0')
        
        # Calculate PnL for each symbol separately
        for symbol, symbol_trades in trades_by_symbol.items():
            # Sort trades by open time (chronological order)
            sorted_trades = sorted(symbol_trades, key=lambda t: t.open_time)
            
            # Use position tracking to implement FIFO
            open_positions = []
            symbol_pnl = Decimal('0')
            
            for trade in sorted_trades:
                trade_direction = trade.direction
                trade_size = Decimal(str(trade.size))
                trade_price = Decimal(str(trade.open_price))
                
                # For buy trades, add to open positions
                if trade_direction == TradeDirection.BUY:
                    open_positions.append({
                        'price': trade_price,
                        'size': trade_size,
                        'open_time': trade.open_time
                    })
                # For sell trades, match against oldest open positions (FIFO)
                elif trade_direction == TradeDirection.SELL:
                    remaining_size = trade_size
                    sell_price = Decimal(str(trade.close_price))
                    
                    while remaining_size > 0 and open_positions:
                        oldest_position = open_positions[0]
                        
                        # Determine how much of this position to close
                        close_size = min(remaining_size, oldest_position['size'])
                        
                        # Calculate PnL for the closed portion
                        position_pnl = (sell_price - oldest_position['price']) * close_size
                        
                        # Add fees if needed
                        if include_fees:
                            # Estimate the proportional fee for this partial close
                            position_fee = Decimal(str(trade.fees)) * (close_size / trade_size)
                            position_pnl -= position_fee
                        
                        symbol_pnl += position_pnl
                        
                        # Update or remove the position
                        if close_size == oldest_position['size']:
                            open_positions.pop(0)
                        else:
                            oldest_position['size'] -= close_size
                        
                        remaining_size -= close_size
            
            # Add unrealized PnL if requested
            if unrealized and market_prices and symbol in market_prices:
                current_price = market_prices[symbol]
                
                for position in open_positions:
                    unrealized_pnl = (current_price - position['price']) * position['size']
                    symbol_pnl += unrealized_pnl
            
            total_pnl += symbol_pnl
        
        return total_pnl
    
    def _calculate_lifo(
        self, 
        trades: List[Trade], 
        include_fees: bool = True, 
        unrealized: bool = False,
        market_prices: Optional[Dict[str, Decimal]] = None
    ) -> Decimal:
        """Calculate PnL using Last-In-First-Out method
        
        Args:
            trades: List of trades to calculate PnL for
            include_fees: Whether to include fees in the calculation
            unrealized: Whether to include unrealized PnL
            market_prices: Current market prices for symbols (required for unrealized PnL)
            
        Returns:
            Decimal value representing PnL
        """
        # Group trades by symbol
        trades_by_symbol = {}
        for trade in trades:
            if trade.symbol not in trades_by_symbol:
                trades_by_symbol[trade.symbol] = []
            trades_by_symbol[trade.symbol].append(trade)
        
        total_pnl = Decimal('0')
        
        # Calculate PnL for each symbol separately
        for symbol, symbol_trades in trades_by_symbol.items():
            # Sort trades by open time (chronological order)
            sorted_trades = sorted(symbol_trades, key=lambda t: t.open_time)
            
            # Use position tracking to implement LIFO
            open_positions = []
            symbol_pnl = Decimal('0')
            
            for trade in sorted_trades:
                trade_direction = trade.direction
                trade_size = Decimal(str(trade.size))
                trade_price = Decimal(str(trade.open_price))
                
                # For buy trades, add to open positions
                if trade_direction == TradeDirection.BUY:
                    open_positions.append({
                        'price': trade_price,
                        'size': trade_size,
                        'open_time': trade.open_time
                    })
                # For sell trades, match against newest open positions (LIFO)
                elif trade_direction == TradeDirection.SELL:
                    remaining_size = trade_size
                    sell_price = Decimal(str(trade.close_price))
                    
                    while remaining_size > 0 and open_positions:
                        # LIFO: take the most recent position (last in the list)
                        newest_position = open_positions[-1]
                        
                        # Determine how much of this position to close
                        close_size = min(remaining_size, newest_position['size'])
                        
                        # Calculate PnL for the closed portion
                        position_pnl = (sell_price - newest_position['price']) * close_size
                        
                        # Add fees if needed
                        if include_fees:
                            # Estimate the proportional fee for this partial close
                            position_fee = Decimal(str(trade.fees)) * (close_size / trade_size)
                            position_pnl -= position_fee
                        
                        symbol_pnl += position_pnl
                        
                        # Update or remove the position
                        if close_size == newest_position['size']:
                            open_positions.pop()
                        else:
                            newest_position['size'] -= close_size
                        
                        remaining_size -= close_size
            
            # Add unrealized PnL if requested
            if unrealized and market_prices and symbol in market_prices:
                current_price = market_prices[symbol]
                
                for position in open_positions:
                    unrealized_pnl = (current_price - position['price']) * position['size']
                    symbol_pnl += unrealized_pnl
            
            total_pnl += symbol_pnl
        
        return total_pnl
    
    def _calculate_average_cost(
        self, 
        trades: List[Trade], 
        include_fees: bool = True, 
        unrealized: bool = False,
        market_prices: Optional[Dict[str, Decimal]] = None
    ) -> Decimal:
        """Calculate PnL using Average Cost method
        
        Args:
            trades: List of trades to calculate PnL for
            include_fees: Whether to include fees in the calculation
            unrealized: Whether to include unrealized PnL
            market_prices: Current market prices for symbols (required for unrealized PnL)
            
        Returns:
            Decimal value representing PnL
        """
        # Group trades by symbol
        trades_by_symbol = {}
        for trade in trades:
            if trade.symbol not in trades_by_symbol:
                trades_by_symbol[trade.symbol] = []
            trades_by_symbol[trade.symbol].append(trade)
        
        total_pnl = Decimal('0')
        
        # Calculate PnL for each symbol separately
        for symbol, symbol_trades in trades_by_symbol.items():
            # Sort trades by open time (chronological order)
            sorted_trades = sorted(symbol_trades, key=lambda t: t.open_time)
            
            # Track average cost for the symbol
            avg_cost = Decimal('0')
            total_size = Decimal('0')
            symbol_pnl = Decimal('0')
            
            for trade in sorted_trades:
                trade_direction = trade.direction
                trade_size = Decimal(str(trade.size))
                
                # For buy trades, update average cost
                if trade_direction == TradeDirection.BUY:
                    trade_price = Decimal(str(trade.open_price))
                    
                    if total_size + trade_size > 0:
                        # Update average cost
                        avg_cost = ((avg_cost * total_size) + (trade_price * trade_size)) / (total_size + trade_size)
                    else:
                        avg_cost = trade_price
                    
                    total_size += trade_size
                    
                # For sell trades, calculate PnL based on current average cost
                elif trade_direction == TradeDirection.SELL:
                    if total_size >= trade_size:
                        sell_price = Decimal(str(trade.close_price))
                        
                        # Calculate PnL
                        trade_pnl = (sell_price - avg_cost) * trade_size
                        
                        # Add fees if needed
                        if include_fees:
                            trade_pnl -= Decimal(str(trade.fees))
                        
                        symbol_pnl += trade_pnl
                        total_size -= trade_size
            
            # Add unrealized PnL if requested
            if unrealized and market_prices and symbol in market_prices and total_size > 0:
                current_price = market_prices[symbol]
                unrealized_pnl = (current_price - avg_cost) * total_size
                symbol_pnl += unrealized_pnl
            
            total_pnl += symbol_pnl
        
        return total_pnl
    
    def _calculate_max_drawdown(self, trades: List[Trade]) -> Tuple[Decimal, Optional[datetime.datetime], Optional[datetime.datetime]]:
        """Calculate maximum drawdown and its period
        
        Args:
            trades: List of trades to calculate drawdown for
            
        Returns:
            Tuple containing maximum drawdown amount and the start/end dates
        """
        if not trades:
            return Decimal('0'), None, None
        
        # Sort trades by close time
        sorted_trades = sorted(trades, key=lambda t: t.close_time)
        
        # Calculate cumulative PnL
        cumulative_pnl = []
        running_total = Decimal('0')
        timestamps = []
        
        for trade in sorted_trades:
            running_total += Decimal(str(trade.net_pnl))
            cumulative_pnl.append(running_total)
            timestamps.append(trade.close_time)
        
        # Find max drawdown
        max_drawdown = Decimal('0')
        peak_idx = 0
        trough_idx = 0
        current_peak_idx = 0
        
        for i, pnl in enumerate(cumulative_pnl):
            if pnl > cumulative_pnl[current_peak_idx]:
                current_peak_idx = i
            else:
                current_drawdown = cumulative_pnl[current_peak_idx] - pnl
                if current_drawdown > max_drawdown:
                    max_drawdown = current_drawdown
                    peak_idx = current_peak_idx
                    trough_idx = i
        
        if max_drawdown == 0:
            return Decimal('0'), None, None
        
        return max_drawdown, timestamps[peak_idx], timestamps[trough_idx]
    
    def _add_to_cache(self, key: str, value: Any) -> None:
        """Add item to cache with current timestamp"""
        with self._cache_lock:
            self._cache[key] = value
            self._cache_timestamps[key] = time.time()
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get item from cache if it exists and hasn't expired"""
        with self._cache_lock:
            if key in self._cache and key in self._cache_timestamps:
                if time.time() - self._cache_timestamps[key] < self.cache_ttl:
                    return self._cache[key]
                # Remove expired item
                del self._cache[key]
                del self._cache_timestamps[key]
        return None 