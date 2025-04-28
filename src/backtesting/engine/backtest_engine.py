"""
Backtesting Engine Module

This module contains the event-driven backtesting engine that simulates
trading strategies on historical data.
"""

import logging
import queue
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Any, Optional, Union, Tuple, Set, Callable

import pandas as pd
import numpy as np
from dataclasses import dataclass, field

from ...strategies.base import Strategy, Signal, SignalType
from .data.data_manager import BacktestDataManager
from .models.portfolio import Portfolio, Position

# Configure logger
logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events in the backtesting engine."""
    MARKET_DATA = "MARKET_DATA"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"
    EOD = "END_OF_DAY"
    METRICS = "METRICS"


@dataclass
class Event:
    """Base class for all events."""
    event_type: EventType
    timestamp: pd.Timestamp
    
    def __post_init__(self):
        """Ensure timestamp is a pandas Timestamp."""
        if not isinstance(self.timestamp, pd.Timestamp):
            self.timestamp = pd.Timestamp(self.timestamp)


@dataclass
class MarketDataEvent(Event):
    """Event containing market data."""
    event_type: EventType = field(default=EventType.MARKET_DATA)
    symbol: str = None
    timeframe: str = None
    data: pd.DataFrame = None
    current_bar: dict = None
    

@dataclass
class SignalEvent(Event):
    """Event containing a trading signal."""
    event_type: EventType = field(default=EventType.SIGNAL)
    signal: Signal = None


@dataclass
class OrderEvent(Event):
    """Event containing an order."""
    event_type: EventType = field(default=EventType.ORDER)
    symbol: str = None
    order_type: str = "MARKET"  # MARKET, LIMIT, STOP
    direction: str = None  # BUY, SELL
    quantity: float = None
    price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    trailing_stop: Optional[bool] = None
    trailing_amount: Optional[float] = None
    order_id: Optional[str] = None


@dataclass
class FillEvent(Event):
    """Event containing an order fill."""
    event_type: EventType = field(default=EventType.FILL)
    symbol: str = None
    direction: str = None
    quantity: float = None
    price: float = None
    commission: float = None
    slippage: float = None
    order_id: Optional[str] = None


@dataclass
class EODEvent(Event):
    """Event signaling the end of a trading day."""
    event_type: EventType = field(default=EventType.EOD)
    date: datetime = None


@dataclass
class MetricsEvent(Event):
    """Event containing performance metrics."""
    event_type: EventType = field(default=EventType.METRICS)
    metrics: Dict[str, Any] = None


class BacktestEngine:
    """
    Event-driven backtesting engine.
    
    This class simulates trading strategies on historical data using
    an event-driven architecture.
    """
    
    def __init__(
        self,
        data_manager: Optional[BacktestDataManager] = None,
        initial_capital: float = 100000.0,
        commission_model: Callable = None,
        slippage_model: Callable = None
    ):
        """
        Initialize the backtesting engine.
        
        Args:
            data_manager: Optional data manager for fetching historical data
            initial_capital: Initial capital for the portfolio
            commission_model: Function for calculating commissions
            slippage_model: Function for calculating slippage
        """
        self.data_manager = data_manager or BacktestDataManager()
        self.initial_capital = initial_capital
        self.commission_model = commission_model or self._default_commission
        self.slippage_model = slippage_model or self._default_slippage
        
        # Initialize event queue and portfolio
        self.events = queue.Queue()
        self.portfolio = Portfolio(initial_capital)
        
        # Trading universe and data
        self.symbols = []
        self.timeframes = []
        self.data = {}
        self.current_timestamp = None
        
        # Strategy management
        self.strategies = {}
        
        # Performance tracking
        self.performance_df = None
        self.trade_history = []
        
        # Settings
        self.verbose = False
    
    def _default_commission(self, order_price: float, quantity: float) -> float:
        """
        Default commission model (0.1% of trade value).
        
        Args:
            order_price: Execution price
            quantity: Order quantity
            
        Returns:
            Commission amount
        """
        return order_price * quantity * 0.001
    
    def _default_slippage(self, order_price: float, direction: str, market_data: pd.DataFrame) -> float:
        """
        Default slippage model (0.05% of price in direction of trade).
        
        Args:
            order_price: Order price
            direction: Trade direction ('BUY' or 'SELL')
            market_data: Current market data
            
        Returns:
            Price after slippage
        """
        # Apply 0.05% slippage in the direction of the trade
        slippage_factor = 0.0005
        if direction == "BUY":
            return order_price * (1 + slippage_factor)
        else:
            return order_price * (1 - slippage_factor)
    
    def add_strategy(
        self,
        strategy: Strategy,
        symbols: List[str],
        timeframes: List[str]
    ) -> None:
        """
        Add a strategy to the backtest.
        
        Args:
            strategy: Strategy instance
            symbols: List of symbols to trade
            timeframes: List of timeframes to use
        """
        self.strategies[strategy.name] = {
            "strategy": strategy,
            "symbols": symbols,
            "timeframes": timeframes
        }
        
        # Add symbols and timeframes to global lists
        for symbol in symbols:
            if symbol not in self.symbols:
                self.symbols.append(symbol)
        
        for timeframe in timeframes:
            if timeframe not in self.timeframes:
                self.timeframes.append(timeframe)
        
        logger.info(
            f"Added strategy {strategy.name} for {len(symbols)} symbols "
            f"and {len(timeframes)} timeframes"
        )
    
    async def load_data(
        self,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str]
    ) -> None:
        """
        Load historical data for all symbols and timeframes.
        
        Args:
            start_date: Start date for historical data
            end_date: End date for historical data
        """
        if not self.symbols or not self.timeframes:
            raise ValueError("No symbols or timeframes specified")
        
        for timeframe in self.timeframes:
            self.data[timeframe] = {}
            
            # Load data for each symbol
            symbol_data = await self.data_manager.get_multiple_symbols_data(
                symbols=self.symbols,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                include_indicators=None
            )
            
            for symbol, data in symbol_data.items():
                if data.empty:
                    logger.warning(f"No data for {symbol} ({timeframe})")
                    continue
                
                # Store data
                self.data[timeframe][symbol] = data
                logger.debug(
                    f"Loaded {len(data)} bars for {symbol} ({timeframe}) "
                    f"from {data.index[0]} to {data.index[-1]}"
                )
        
        # Create event timeline
        self._create_event_timeline()
        
        logger.info("Data loading complete")
    
    def _create_event_timeline(self) -> None:
        """
        Create a timeline of market data events from the loaded data.
        """
        # Get all unique timestamps across all data
        all_timestamps = set()
        
        for timeframe in self.data:
            for symbol in self.data[timeframe]:
                all_timestamps.update(self.data[timeframe][symbol].index)
        
        # Sort timestamps
        self.timeline = sorted(all_timestamps)
        
        if not self.timeline:
            raise ValueError("No data available for backtesting")
        
        logger.info(
            f"Created event timeline with {len(self.timeline)} points "
            f"from {self.timeline[0]} to {self.timeline[-1]}"
        )
    
    def _get_data_at_time(
        self,
        symbol: str,
        timeframe: str,
        timestamp: pd.Timestamp
    ) -> Optional[Dict[str, Any]]:
        """
        Get market data for a specific symbol, timeframe, and timestamp.
        
        Args:
            symbol: Symbol string
            timeframe: Timeframe string
            timestamp: Timestamp
            
        Returns:
            Dictionary with market data or None if not available
        """
        if timeframe not in self.data or symbol not in self.data[timeframe]:
            return None
        
        # Get data for this symbol and timeframe
        data = self.data[timeframe][symbol]
        
        # Find the row for this timestamp
        try:
            if timestamp in data.index:
                row = data.loc[timestamp]
                return row.to_dict()
            
            # If exact timestamp not found, get the previous bar
            previous_bars = data[data.index <= timestamp]
            if not previous_bars.empty:
                row = previous_bars.iloc[-1]
                return row.to_dict()
            
            return None
        except Exception as e:
            logger.error(f"Error getting data at time {timestamp}: {e}")
            return None
    
    def run(
        self,
        start_date: Optional[Union[datetime, str]] = None,
        end_date: Optional[Union[datetime, str]] = None
    ) -> Dict[str, Any]:
        """
        Run the backtest.
        
        Args:
            start_date: Optional start date to override loaded data range
            end_date: Optional end date to override loaded data range
            
        Returns:
            Dictionary with backtest results
        """
        # Initialize portfolio
        self.portfolio = Portfolio(self.initial_capital)
        self.performance_df = None
        self.trade_history = []
        
        # Clear event queue
        while not self.events.empty():
            self.events.get()
        
        # Filter timeline if start_date or end_date provided
        if start_date or end_date:
            filtered_timeline = self.timeline
            
            if start_date:
                if isinstance(start_date, str):
                    start_date = pd.Timestamp(start_date)
                filtered_timeline = [t for t in filtered_timeline if t >= start_date]
            
            if end_date:
                if isinstance(end_date, str):
                    end_date = pd.Timestamp(end_date)
                filtered_timeline = [t for t in filtered_timeline if t <= end_date]
                
            if not filtered_timeline:
                raise ValueError("No data available in specified date range")
                
            timeline = filtered_timeline
        else:
            timeline = self.timeline
            
        # Initialize strategies
        for strategy_config in self.strategies.values():
            strategy = strategy_config["strategy"]
            if not strategy.is_initialized:
                strategy.initialize()
                strategy.is_initialized = True
        
        # Performance tracking
        performance_records = []
        
        # Run event loop
        for timestamp in timeline:
            self.current_timestamp = timestamp
            
            # Process market data events
            self._process_market_data(timestamp)
            
            # Process events until queue is empty
            while not self.events.empty():
                event = self.events.get()
                
                if event.event_type == EventType.MARKET_DATA:
                    self._process_market_data_event(event)
                elif event.event_type == EventType.SIGNAL:
                    self._process_signal_event(event)
                elif event.event_type == EventType.ORDER:
                    self._process_order_event(event)
                elif event.event_type == EventType.FILL:
                    self._process_fill_event(event)
            
            # Record daily performance
            daily_performance = self._record_performance(timestamp)
            if daily_performance:
                performance_records.append(daily_performance)
            
            # Handle end-of-day processing
            self._process_eod(timestamp)
        
        # Create performance DataFrame
        if performance_records:
            self.performance_df = pd.DataFrame(performance_records)
            self.performance_df.set_index('timestamp', inplace=True)
        
        # Calculate performance metrics
        results = self._calculate_results()
        
        logger.info(
            f"Backtest completed: {results['total_return']:.2%} return, "
            f"Sharpe: {results['sharpe_ratio']:.2f}, "
            f"Drawdown: {results['max_drawdown']:.2%}"
        )
        
        return results
    
    def _process_market_data(self, timestamp: pd.Timestamp) -> None:
        """
        Process market data at a specific timestamp.
        
        Args:
            timestamp: Current timestamp
        """
        # Create market data events for each strategy's symbols and timeframes
        for strategy_name, strategy_config in self.strategies.items():
            strategy = strategy_config["strategy"]
            symbols = strategy_config["symbols"]
            timeframes = strategy_config["timeframes"]
            
            for symbol in symbols:
                for timeframe in timeframes:
                    # Get data at this time
                    bar_data = self._get_data_at_time(symbol, timeframe, timestamp)
                    
                    if bar_data:
                        # Create a market data event
                        event = MarketDataEvent(
                            timestamp=timestamp,
                            symbol=symbol,
                            timeframe=timeframe,
                            current_bar=bar_data
                        )
                        
                        # Add to event queue
                        self.events.put(event)
    
    def _process_market_data_event(self, event: MarketDataEvent) -> None:
        """
        Process a market data event.
        
        Args:
            event: MarketDataEvent
        """
        # Update portfolio with latest prices
        if 'close' in event.current_bar:
            self.portfolio.update_price(
                event.symbol, 
                event.current_bar['close'], 
                event.timestamp
            )
        
        # Generate signals from strategies
        for strategy_name, strategy_config in self.strategies.items():
            strategy = strategy_config["strategy"]
            symbols = strategy_config["symbols"]
            timeframes = strategy_config["timeframes"]
            
            # Check if this event is relevant for this strategy
            if event.symbol in symbols and event.timeframe in timeframes:
                # Get recent data for analysis
                lookback_data = self._get_lookback_data(
                    event.symbol, 
                    event.timeframe, 
                    event.timestamp
                )
                
                if lookback_data is not None:
                    # Generate signals
                    try:
                        analysis_results = strategy.analyze(lookback_data)
                        signals = strategy.generate_signals(lookback_data)
                        
                        # Create signal events
                        for signal in signals:
                            if signal.timestamp == event.timestamp:
                                signal_event = SignalEvent(
                                    timestamp=event.timestamp,
                                    signal=signal
                                )
                                self.events.put(signal_event)
                    except Exception as e:
                        logger.error(
                            f"Error generating signals for {strategy_name}: {e}"
                        )
    
    def _get_lookback_data(
        self,
        symbol: str,
        timeframe: str,
        timestamp: pd.Timestamp,
        lookback_bars: int = 100
    ) -> Optional[pd.DataFrame]:
        """
        Get historical data up to the current timestamp for analysis.
        
        Args:
            symbol: Symbol string
            timeframe: Timeframe string
            timestamp: Current timestamp
            lookback_bars: Number of bars to look back
            
        Returns:
            DataFrame with lookback data or None if not available
        """
        if timeframe not in self.data or symbol not in self.data[timeframe]:
            return None
            
        # Get data for this symbol and timeframe
        all_data = self.data[timeframe][symbol]
        
        # Get data up to this timestamp
        data = all_data[all_data.index <= timestamp]
        
        # Return the last N bars
        if len(data) > lookback_bars:
            return data.iloc[-lookback_bars:]
        
        return data
    
    def _process_signal_event(self, event: SignalEvent) -> None:
        """
        Process a signal event.
        
        Args:
            event: SignalEvent
        """
        signal = event.signal
        
        # Get current price
        current_price = self._get_current_price(signal.symbol)
        if current_price is None:
            logger.warning(f"No price available for {signal.symbol}, skipping signal")
            return
        
        # Determine order direction
        if signal.signal_type == SignalType.BUY:
            direction = "BUY"
        elif signal.signal_type == SignalType.SELL:
            direction = "SELL"
        else:
            # Ignore HOLD or other signals
            return
        
        # Calculate position size based on signal strength and available capital
        position_size = self._calculate_position_size(
            signal.symbol, 
            direction, 
            signal.strength,
            current_price
        )
        
        if position_size <= 0:
            logger.debug(f"Position size for {signal.symbol} is {position_size}, skipping order")
            return
        
        # Create order event
        order = OrderEvent(
            timestamp=event.timestamp,
            symbol=signal.symbol,
            order_type="MARKET",
            direction=direction,
            quantity=position_size,
            price=current_price
        )
        
        # Add to event queue
        self.events.put(order)
    
    def _calculate_position_size(
        self,
        symbol: str,
        direction: str,
        signal_strength: float,
        current_price: float
    ) -> float:
        """
        Calculate position size for an order.
        
        Args:
            symbol: Symbol string
            direction: Order direction ('BUY' or 'SELL')
            signal_strength: Signal strength (0.0 to 1.0)
            current_price: Current price
            
        Returns:
            Position size
        """
        # Get current portfolio value and risk settings
        portfolio_value = self.portfolio.current_value
        
        # Base risk per trade (1% of portfolio)
        base_risk = portfolio_value * 0.01
        
        # Adjust risk based on signal strength
        adjusted_risk = base_risk * signal_strength
        
        # Check existing position
        existing_position = self.portfolio.get_position(symbol)
        
        if existing_position:
            # If already have a position in the same direction, don't add
            if (direction == "BUY" and existing_position.quantity > 0) or \
               (direction == "SELL" and existing_position.quantity < 0):
                return 0
            
            # If opposite direction, close the existing position
            if (direction == "BUY" and existing_position.quantity < 0) or \
               (direction == "SELL" and existing_position.quantity > 0):
                return abs(existing_position.quantity)
        
        # Calculate position size based on adjusted risk
        # For a simple implementation, use a fixed percentage of portfolio
        position_value = adjusted_risk * 10  # 10x the risk
        position_size = position_value / current_price
        
        # Round to appropriate precision
        position_size = round(position_size, 8)
        
        return position_size
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get the most recent price for a symbol.
        
        Args:
            symbol: Symbol string
            
        Returns:
            Current price or None if not available
        """
        # Use the shortest timeframe for the most recent price
        # Sort timeframes by length to prefer shorter timeframes
        sorted_timeframes = sorted(self.timeframes, key=lambda x: x)
        
        for timeframe in sorted_timeframes:
            if timeframe in self.data and symbol in self.data[timeframe]:
                # Get data up to current timestamp
                data = self.data[timeframe][symbol]
                data = data[data.index <= self.current_timestamp]
                
                if not data.empty:
                    return data.iloc[-1]['close']
        
        return None
    
    def _process_order_event(self, event: OrderEvent) -> None:
        """
        Process an order event.
        
        Args:
            event: OrderEvent
        """
        # Check if order can be executed
        if not self._validate_order(event):
            logger.warning(f"Order validation failed for {event.symbol}")
            return
        
        # Simulate execution
        fill_price = self._calculate_fill_price(event)
        commission = self.commission_model(fill_price, event.quantity)
        
        # Create fill event
        fill = FillEvent(
            timestamp=event.timestamp,
            symbol=event.symbol,
            direction=event.direction,
            quantity=event.quantity,
            price=fill_price,
            commission=commission,
            slippage=abs(fill_price - event.price) / event.price if event.price else 0,
            order_id=event.order_id
        )
        
        # Add to event queue
        self.events.put(fill)
    
    def _validate_order(self, order: OrderEvent) -> bool:
        """
        Validate an order before execution.
        
        Args:
            order: OrderEvent
            
        Returns:
            True if order is valid, False otherwise
        """
        # Check if order has quantity
        if not order.quantity or order.quantity <= 0:
            logger.warning(f"Invalid order quantity: {order.quantity}")
            return False
        
        # Check if we have enough cash for a BUY order
        if order.direction == "BUY":
            # Estimate order cost
            est_price = order.price or self._get_current_price(order.symbol)
            if est_price is None:
                logger.warning(f"No price available for {order.symbol}")
                return False
                
            est_commission = self.commission_model(est_price, order.quantity)
            est_cost = (est_price * order.quantity) + est_commission
            
            if est_cost > self.portfolio.cash:
                logger.warning(
                    f"Insufficient cash for order: {est_cost:.2f} > {self.portfolio.cash:.2f}"
                )
                return False
        
        # All checks passed
        return True
    
    def _calculate_fill_price(self, order: OrderEvent) -> float:
        """
        Calculate the fill price for an order, including slippage.
        
        Args:
            order: OrderEvent
            
        Returns:
            Fill price
        """
        # Get current market data
        market_price = order.price
        if market_price is None:
            market_price = self._get_current_price(order.symbol)
            if market_price is None:
                logger.warning(f"No price available for {order.symbol}, using last known price")
                return order.price
        
        # Apply slippage model
        fill_price = self.slippage_model(
            market_price, 
            order.direction,
            None  # Should be market data, but we're using a simple model
        )
        
        return fill_price
    
    def _process_fill_event(self, event: FillEvent) -> None:
        """
        Process a fill event.
        
        Args:
            event: FillEvent
        """
        # Determine quantity (positive for BUY, negative for SELL)
        if event.direction == "BUY":
            quantity = event.quantity
        else:
            quantity = -event.quantity
        
        # Update portfolio
        self.portfolio.execute_trade(
            symbol=event.symbol,
            quantity=quantity,
            price=event.price,
            timestamp=event.timestamp,
            commission=event.commission
        )
        
        # Record trade
        self.trade_history.append({
            'timestamp': event.timestamp,
            'symbol': event.symbol,
            'direction': event.direction,
            'quantity': event.quantity,
            'price': event.price,
            'commission': event.commission,
            'slippage': event.slippage,
            'value': event.price * event.quantity,
            'portfolio_value': self.portfolio.current_value
        })
        
        if self.verbose:
            logger.info(
                f"Executed {event.direction} {event.quantity} {event.symbol} @ "
                f"{event.price:.4f} (commission: {event.commission:.2f})"
            )
    
    def _process_eod(self, timestamp: pd.Timestamp) -> None:
        """
        Process end-of-day activities.
        
        Args:
            timestamp: Current timestamp
        """
        # Check if this is the end of a day
        is_eod = False
        
        # Simple way to check for EOD: if timestamp.hour is near end of trading day
        if timestamp.hour >= 23:
            is_eod = True
        
        if is_eod:
            # Create EOD event
            eod_event = EODEvent(
                timestamp=timestamp,
                date=timestamp.date()
            )
            
            # Handle EOD activities
            self._update_portfolio_eod()
            
            if self.verbose:
                logger.info(
                    f"EOD {timestamp.date()}: "
                    f"Portfolio value: {self.portfolio.current_value:.2f}, "
                    f"Cash: {self.portfolio.cash:.2f}"
                )
    
    def _update_portfolio_eod(self) -> None:
        """Update portfolio at end of day."""
        # Update portfolio values
        self.portfolio.update_value(self.current_timestamp)
    
    def _record_performance(self, timestamp: pd.Timestamp) -> Dict[str, Any]:
        """
        Record daily performance metrics.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            Dictionary with performance metrics
        """
        # Update portfolio value
        self.portfolio.update_value(timestamp)
        
        # Record metrics
        return {
            'timestamp': timestamp,
            'portfolio_value': self.portfolio.current_value,
            'cash': self.portfolio.cash,
            'daily_return': self.portfolio.get_daily_return(),
            'equity': self.portfolio.get_equity_value(),
            'positions': len(self.portfolio.positions)
        }
    
    def _calculate_results(self) -> Dict[str, Any]:
        """
        Calculate final backtest results.
        
        Returns:
            Dictionary with performance metrics
        """
        if self.performance_df is None or self.performance_df.empty:
            logger.warning("No performance data available")
            return {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'win_rate': 0.0,
                'profit_factor': 0.0
            }
        
        # Calculate returns from portfolio value
        df = self.performance_df.copy()
        
        # Calculate daily returns if not already present
        if 'daily_return' not in df.columns:
            df['daily_return'] = df['portfolio_value'].pct_change()
        
        # Calculate cumulative returns
        df['cumulative_return'] = (1 + df['daily_return']).cumprod() - 1
        
        # Calculate drawdown
        df['high_value'] = df['portfolio_value'].cummax()
        df['drawdown'] = (df['portfolio_value'] / df['high_value']) - 1
        
        # Calculate various metrics
        total_return = df['cumulative_return'].iloc[-1]
        daily_returns = df['daily_return'].dropna()
        
        # Annualized return and volatility
        days = (df.index[-1] - df.index[0]).days
        ann_factor = 252 / max(1, days) * len(daily_returns)
        ann_return = (1 + total_return) ** ann_factor - 1
        ann_volatility = daily_returns.std() * np.sqrt(252)
        
        # Sharpe ratio
        risk_free_rate = 0.0  # Can be customized
        sharpe_ratio = (ann_return - risk_free_rate) / ann_volatility if ann_volatility > 0 else 0
        
        # Maximum drawdown
        max_drawdown = df['drawdown'].min()
        
        # Calculate win rate from trade history
        if self.trade_history:
            trade_df = pd.DataFrame(self.trade_history)
            trade_df['profit'] = trade_df['value'] * trade_df['direction'].map({'BUY': -1, 'SELL': 1})
            
            # Group by symbol to match BUY/SELL pairs
            trades_by_symbol = trade_df.groupby('symbol')
            
            # Calculate profit/loss for each symbol
            wins = 0
            losses = 0
            total_profit = 0
            total_loss = 0
            
            for symbol, trades in trades_by_symbol:
                # This is a simplistic approach; a more sophisticated implementation
                # would match specific buy and sell transactions.
                buy_value = trades[trades['direction'] == 'BUY']['value'].sum()
                sell_value = trades[trades['direction'] == 'SELL']['value'].sum()
                commission = trades['commission'].sum()
                
                pnl = sell_value - buy_value - commission
                
                if pnl > 0:
                    wins += 1
                    total_profit += pnl
                else:
                    losses += 1
                    total_loss += abs(pnl)
            
            win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
            profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        else:
            win_rate = 0
            profit_factor = 0
        
        # Create complete results dictionary
        results = {
            'start_date': df.index[0],
            'end_date': df.index[-1],
            'total_days': days,
            'initial_capital': self.initial_capital,
            'final_value': df['portfolio_value'].iloc[-1],
            'total_return': total_return,
            'annualized_return': ann_return,
            'annualized_volatility': ann_volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': len(self.trade_history),
            'performance_df': df
        }
        
        return results 