"""
Moving Average Crossover Strategy

This strategy generates buy signals when a fast moving average crosses above a slow
moving average, and sell signals when the fast moving average crosses below the slow
moving average.
"""

from typing import Dict, Any, List, Union, Optional
import pandas as pd
import numpy as np
import logging

from .base import Strategy, Signal, SignalType

logger = logging.getLogger(__name__)


class MovingAverageCrossover(Strategy):
    """
    Moving Average Crossover strategy implementation.
    
    This strategy uses two moving averages (fast and slow) and generates:
    - BUY signals when the fast MA crosses above the slow MA
    - SELL signals when the fast MA crosses below the slow MA
    
    Default parameters:
    - fast_period: 10 (period for fast moving average)
    - slow_period: 30 (period for slow moving average)
    - ma_type: 'ema' (type of moving average: 'ema', 'sma', 'wma')
    - signal_threshold: 0.0 (minimum price difference to generate signal)
    """
    
    def __init__(self, name: str, params: Dict[str, Any] = None):
        """Initialize the Moving Average Crossover strategy with parameters."""
        super().__init__(name, params)
        
        # Set default parameters
        self.params.setdefault('fast_period', 10)
        self.params.setdefault('slow_period', 30)
        self.params.setdefault('ma_type', 'ema')  # 'ema', 'sma', 'wma'
        self.params.setdefault('signal_threshold', 0.0)  # Min price difference for signal
        
        # Validate parameters
        if self.params['fast_period'] >= self.params['slow_period']:
            raise ValueError("Fast period must be less than slow period")
            
        self._fast_ma_values = {}
        self._slow_ma_values = {}
        
    def initialize(self) -> None:
        """Initialize the strategy with any necessary setup."""
        logger.info(
            f"Initializing {self.name} with fast_period={self.params['fast_period']}, "
            f"slow_period={self.params['slow_period']}, ma_type={self.params['ma_type']}"
        )
        self.is_initialized = True
    
    def calculate_moving_average(
        self, 
        data: pd.DataFrame, 
        period: int, 
        ma_type: str = 'ema'
    ) -> pd.Series:
        """
        Calculate moving average on the price series.
        
        Args:
            data: DataFrame with price data
            period: Period for the moving average
            ma_type: Type of moving average ('ema', 'sma', 'wma')
            
        Returns:
            Series containing the moving average values
        """
        if 'close' not in data.columns:
            raise ValueError("DataFrame must contain 'close' column")
            
        price = data['close']
        
        if ma_type == 'sma':
            return price.rolling(window=period).mean()
        elif ma_type == 'ema':
            return price.ewm(span=period, adjust=False).mean()
        elif ma_type == 'wma':
            # Weighted moving average with linearly decreasing weights
            weights = np.arange(1, period + 1)
            return price.rolling(window=period).apply(
                lambda x: np.sum(weights * x) / np.sum(weights), raw=True
            )
        else:
            raise ValueError(f"Unsupported MA type: {ma_type}")
    
    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze market data and calculate moving averages.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            Dictionary with analysis results
        """
        if data.empty:
            return {'error': 'Empty data'}
            
        if 'symbol' not in data.columns:
            # Add a default symbol if not present
            symbol = self.params.get('symbol', 'UNKNOWN')
            data = data.copy()
            data['symbol'] = symbol
        
        # Get unique symbols in the data
        symbols = data['symbol'].unique()
        results = {}
        
        for symbol in symbols:
            symbol_data = data[data['symbol'] == symbol]
            
            try:
                # Calculate moving averages
                fast_ma = self.calculate_moving_average(
                    symbol_data, 
                    self.params['fast_period'], 
                    self.params['ma_type']
                )
                
                slow_ma = self.calculate_moving_average(
                    symbol_data, 
                    self.params['slow_period'], 
                    self.params['ma_type']
                )
                
                # Store MA values for this symbol
                self._fast_ma_values[symbol] = fast_ma
                self._slow_ma_values[symbol] = slow_ma
                
                # Calculate crossover points
                crossover = (fast_ma > slow_ma).astype(int)
                signal_line = crossover.diff()
                
                # Store analysis results
                last_fast_ma = fast_ma.iloc[-1]
                last_slow_ma = slow_ma.iloc[-1]
                last_price = symbol_data['close'].iloc[-1]
                
                results[symbol] = {
                    'last_fast_ma': last_fast_ma,
                    'last_slow_ma': last_slow_ma,
                    'last_price': last_price,
                    'ma_diff': last_fast_ma - last_slow_ma,
                    'ma_diff_pct': (last_fast_ma - last_slow_ma) / last_slow_ma * 100,
                    'price_to_fast_ma_pct': (last_price - last_fast_ma) / last_fast_ma * 100,
                    'price_to_slow_ma_pct': (last_price - last_slow_ma) / last_slow_ma * 100,
                    'signal_points': signal_line[signal_line != 0].count(),
                    'current_position': 'long' if fast_ma.iloc[-1] > slow_ma.iloc[-1] else 'short'
                }
                
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
                results[symbol] = {'error': str(e)}
        
        return results
    
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """
        Generate trading signals based on moving average crossovers.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            List of Signal objects
        """
        signals = []
        
        if data.empty:
            logger.warning("Empty data provided, no signals generated")
            return signals
            
        if 'symbol' not in data.columns:
            # Add a default symbol if not present
            symbol = self.params.get('symbol', 'UNKNOWN')
            data = data.copy()
            data['symbol'] = symbol
        
        # Analyze the data if not already analyzed
        analysis_results = self.analyze(data)
        
        # Get unique symbols
        symbols = data['symbol'].unique()
        
        for symbol in symbols:
            symbol_data = data[data['symbol'] == symbol]
            
            if symbol not in self._fast_ma_values or symbol not in self._slow_ma_values:
                logger.warning(f"Missing MA values for {symbol}, skipping signal generation")
                continue
                
            fast_ma = self._fast_ma_values[symbol]
            slow_ma = self._slow_ma_values[symbol]
            
            # Get the current and previous relationship between MAs
            current_fast_above_slow = fast_ma.iloc[-1] > slow_ma.iloc[-1]
            
            # Check if we have enough history to determine previous state
            if len(fast_ma) > 1 and len(slow_ma) > 1:
                previous_fast_above_slow = fast_ma.iloc[-2] > slow_ma.iloc[-2]
                
                # Detect crossover
                if current_fast_above_slow and not previous_fast_above_slow:
                    # Fast MA crossed above slow MA -> BUY signal
                    signal_type = SignalType.BUY
                    # Calculate signal strength based on the difference between MAs
                    signal_strength = min(
                        (fast_ma.iloc[-1] - slow_ma.iloc[-1]) / slow_ma.iloc[-1] * 10, 
                        1.0
                    )
                    
                    # Apply threshold filter
                    if abs(fast_ma.iloc[-1] - slow_ma.iloc[-1]) > self.params['signal_threshold']:
                        signals.append(Signal(
                            signal_type=signal_type,
                            symbol=symbol,
                            price=symbol_data['close'].iloc[-1],
                            timestamp=symbol_data.index[-1] if isinstance(symbol_data.index, pd.DatetimeIndex) else pd.Timestamp.now(),
                            strength=max(0.1, signal_strength),
                            metadata={
                                'fast_ma': float(fast_ma.iloc[-1]),
                                'slow_ma': float(slow_ma.iloc[-1]),
                                'ma_diff': float(fast_ma.iloc[-1] - slow_ma.iloc[-1]),
                                'strategy': self.name
                            }
                        ))
                        
                elif not current_fast_above_slow and previous_fast_above_slow:
                    # Fast MA crossed below slow MA -> SELL signal
                    signal_type = SignalType.SELL
                    # Calculate signal strength based on the difference between MAs
                    signal_strength = min(
                        (slow_ma.iloc[-1] - fast_ma.iloc[-1]) / slow_ma.iloc[-1] * 10, 
                        1.0
                    )
                    
                    # Apply threshold filter
                    if abs(fast_ma.iloc[-1] - slow_ma.iloc[-1]) > self.params['signal_threshold']:
                        signals.append(Signal(
                            signal_type=signal_type,
                            symbol=symbol,
                            price=symbol_data['close'].iloc[-1],
                            timestamp=symbol_data.index[-1] if isinstance(symbol_data.index, pd.DatetimeIndex) else pd.Timestamp.now(),
                            strength=max(0.1, signal_strength),
                            metadata={
                                'fast_ma': float(fast_ma.iloc[-1]),
                                'slow_ma': float(slow_ma.iloc[-1]),
                                'ma_diff': float(fast_ma.iloc[-1] - slow_ma.iloc[-1]),
                                'strategy': self.name
                            }
                        ))
        
        return signals
    
    def get_required_indicators(self) -> List[str]:
        """Return a list of indicator names required by this strategy."""
        return []  # This strategy calculates its own indicators
    
    def get_required_timeframes(self) -> List[str]:
        """Return a list of timeframes required by this strategy."""
        # Return default timeframe from params or a standard one
        return [self.params.get('timeframe', '1h')]
    
    @property
    def description(self) -> str:
        """Return a description of the strategy."""
        return (
            f"Moving Average Crossover Strategy ({self.params['fast_period']}, "
            f"{self.params['slow_period']}, {self.params['ma_type']})"
        ) 