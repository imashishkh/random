"""
Specialized Technical Analysis Agents.

This module provides specialized agent implementations for different types of
technical analysis, including momentum, volatility, trend, and pattern recognition.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime

from .technical_analysis.agent import TechnicalAnalysisAgent
from .technical_analysis.indicator_factory import TAIndicatorFactory


class MomentumAnalysisAgent(TechnicalAnalysisAgent):
    """
    Agent specializing in momentum analysis using indicators like RSI and MACD.
    
    This agent identifies overbought and oversold conditions, as well as 
    momentum shifts that could indicate trading opportunities.
    """
    
    def __init__(self, name: str = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the momentum analysis agent.
        
        Args:
            name: Optional name for the agent instance
            config: Configuration dictionary with parameters for indicators and signal generation
        """
        # Set default config values for momentum analysis
        default_config = {
            'rsi_period': 14,
            'rsi_overbought': 70,
            'rsi_oversold': 30,
            'macd_fast_period': 12,
            'macd_slow_period': 26,
            'macd_signal_period': 9,
            'stoch_k_period': 14,
            'stoch_d_period': 3,
            'evaluation_periods': 10,
        }
        
        # Merge with provided config
        if config:
            config = {**default_config, **config}
        else:
            config = default_config
            
        super().__init__(name=name or "MomentumAgent", config=config)
    
    def compute_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Compute momentum indicators.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            Dictionary mapping indicator names to computed values
        """
        # Calculate RSI
        self.indicators['rsi'] = TAIndicatorFactory.create_indicator(
            'RSI', 
            data, 
            {'timeperiod': self.config['rsi_period']}
        )
        
        # Calculate MACD
        macd_result = TAIndicatorFactory.create_indicator(
            'MACD', 
            data, 
            {
                'fastperiod': self.config['macd_fast_period'],
                'slowperiod': self.config['macd_slow_period'],
                'signalperiod': self.config['macd_signal_period']
            }
        )
        
        # TA-Lib's MACD returns three outputs, but our factory simplifies it
        # If we need the other values, we'd need to adjust the factory
        self.indicators['macd'] = macd_result
        
        # Calculate Stochastic
        stoch_result = TAIndicatorFactory.create_indicator(
            'STOCH',
            data,
            {
                'fastk_period': self.config['stoch_k_period'],
                'slowk_period': self.config['stoch_d_period'],
                'slowd_period': self.config['stoch_d_period']
            }
        )
        
        # Again, stochastic returns multiple values
        self.indicators['stoch'] = stoch_result
        
        return self.indicators
    
    def generate_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Generate trading signals based on momentum indicators.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            List of signal dictionaries with type, timestamp, indicator, and confidence
        """
        # Compute indicators if not already done
        if not self.indicators:
            self.compute_indicators(data)
            
        signals = []
        
        # Generate RSI signals
        rsi = self.indicators.get('rsi')
        if rsi is not None:
            for i in range(1, len(rsi)):
                # RSI crosses above oversold level (bullish)
                if rsi.iloc[i-1] < self.config['rsi_oversold'] and rsi.iloc[i] > self.config['rsi_oversold']:
                    signal = {
                        'type': 'buy',
                        'timestamp': data.index[i],
                        'indicator': 'rsi_oversold',
                        'value': rsi.iloc[i],
                        'threshold': self.config['rsi_oversold']
                    }
                    signal['confidence'] = self.get_confidence_level(signal, data)
                    signals.append(signal)
                
                # RSI crosses below overbought level (bearish)
                elif rsi.iloc[i-1] > self.config['rsi_overbought'] and rsi.iloc[i] < self.config['rsi_overbought']:
                    signal = {
                        'type': 'sell',
                        'timestamp': data.index[i],
                        'indicator': 'rsi_overbought',
                        'value': rsi.iloc[i],
                        'threshold': self.config['rsi_overbought']
                    }
                    signal['confidence'] = self.get_confidence_level(signal, data)
                    signals.append(signal)
        
        # Generate MACD signals
        macd = self.indicators.get('macd')
        if macd is not None:
            # In a real implementation, we'd have access to all MACD components
            # For now, let's assume we can calculate a simple MACD crossover
            # In a production system, we would enhance the indicator factory to return all components
            pass
        
        # Generate Stochastic signals
        stoch = self.indicators.get('stoch')
        if stoch is not None:
            # Similar to MACD, we need the components
            pass
        
        self.signals = signals
        return signals
    
    def get_confidence_level(self, signal: Dict[str, Any], data: pd.DataFrame) -> float:
        """
        Calculate confidence level for a momentum signal.
        
        Args:
            signal: Signal dictionary with metadata
            data: Market data as a pandas DataFrame
            
        Returns:
            Confidence level between 0 and 1
        """
        confidence = 0.5  # Base confidence
        
        # Get the index for the signal
        signal_idx = self._get_index_from_timestamp(signal['timestamp'], data)
        
        # Factor 1: Signal strength - how far from the threshold
        if signal['indicator'] == 'rsi_oversold':
            # For RSI oversold (buy signal), lower RSI = stronger signal
            strength = max(0, (self.config['rsi_oversold'] - signal['value']) * 0.02)
            confidence += strength
        elif signal['indicator'] == 'rsi_overbought':
            # For RSI overbought (sell signal), higher RSI = stronger signal
            strength = max(0, (signal['value'] - self.config['rsi_overbought']) * 0.02)
            confidence += strength
        
        # Factor 2: Trend confirmation
        # Check if multiple indicators agree
        confirming_signals = 0
        
        # For example, check if stochastic confirms RSI
        stoch = self.indicators.get('stoch')
        if stoch is not None and signal['indicator'].startswith('rsi'):
            if signal['type'] == 'buy' and stoch.iloc[signal_idx] < 20:
                confirming_signals += 1
            elif signal['type'] == 'sell' and stoch.iloc[signal_idx] > 80:
                confirming_signals += 1
                
        # More confirmation checks would go here
        
        confidence += confirming_signals * 0.1
        
        # Factor 3: Volume confirmation
        if 'volume' in data.columns:
            # Check if volume is above average during signal
            avg_volume = data['volume'].rolling(window=20).mean().iloc[signal_idx]
            if data['volume'].iloc[signal_idx] > avg_volume * 1.5:
                confidence += 0.1
        
        # Cap confidence between 0-1
        return max(0.0, min(1.0, confidence))


class VolatilityAnalysisAgent(TechnicalAnalysisAgent):
    """
    Agent specializing in volatility analysis using indicators like Bollinger Bands and ATR.
    
    This agent identifies periods of high and low volatility, price breakouts, and
    potential mean reversion opportunities.
    """
    
    def __init__(self, name: str = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the volatility analysis agent.
        
        Args:
            name: Optional name for the agent instance
            config: Configuration dictionary with parameters for indicators and signal generation
        """
        # Set default config values for volatility analysis
        default_config = {
            'bb_period': 20,
            'bb_std_dev': 2,
            'atr_period': 14,
            'atr_multiplier': 2.0,
            'evaluation_periods': 10,
        }
        
        # Merge with provided config
        if config:
            config = {**default_config, **config}
        else:
            config = default_config
            
        super().__init__(name=name or "VolatilityAgent", config=config)
    
    def compute_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Compute volatility indicators.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            Dictionary mapping indicator names to computed values
        """
        # Calculate Bollinger Bands
        self.indicators['bbands'] = TAIndicatorFactory.create_indicator(
            'BBANDS', 
            data, 
            {
                'timeperiod': self.config['bb_period'],
                'nbdevup': self.config['bb_std_dev'],
                'nbdevdn': self.config['bb_std_dev']
            }
        )
        
        # Calculate ATR
        self.indicators['atr'] = TAIndicatorFactory.create_indicator(
            'ATR', 
            data, 
            {'timeperiod': self.config['atr_period']}
        )
        
        return self.indicators
    
    def generate_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Generate trading signals based on volatility indicators.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            List of signal dictionaries with type, timestamp, indicator, and confidence
        """
        # Compute indicators if not already done
        if not self.indicators:
            self.compute_indicators(data)
            
        signals = []
        
        # Generate Bollinger Band signals
        bbands = self.indicators.get('bbands')
        if bbands is not None:
            # In a real implementation, we'd have upper, middle, and lower bands
            # For now, let's assume a simplified approach
            pass
        
        # Generate ATR-based signals
        atr = self.indicators.get('atr')
        if atr is not None:
            # ATR can be used for volatility breakout systems
            # This is a simplified example
            for i in range(20, len(data)):
                # Calculate the price change
                price_change = abs(data['close'].iloc[i] - data['close'].iloc[i-1])
                
                # If price change is greater than ATR * multiplier, it's a volatility breakout
                if price_change > atr.iloc[i-1] * self.config['atr_multiplier']:
                    # Determine direction
                    if data['close'].iloc[i] > data['close'].iloc[i-1]:
                        signal_type = 'buy'
                    else:
                        signal_type = 'sell'
                        
                    signal = {
                        'type': signal_type,
                        'timestamp': data.index[i],
                        'indicator': 'atr_breakout',
                        'value': price_change,
                        'threshold': atr.iloc[i-1] * self.config['atr_multiplier']
                    }
                    signal['confidence'] = self.get_confidence_level(signal, data)
                    signals.append(signal)
        
        self.signals = signals
        return signals
    
    def get_confidence_level(self, signal: Dict[str, Any], data: pd.DataFrame) -> float:
        """
        Calculate confidence level for a volatility signal.
        
        Args:
            signal: Signal dictionary with metadata
            data: Market data as a pandas DataFrame
            
        Returns:
            Confidence level between 0 and 1
        """
        confidence = 0.5  # Base confidence
        
        # Get the index for the signal
        signal_idx = self._get_index_from_timestamp(signal['timestamp'], data)
        
        # Factor 1: Signal strength - how much above the threshold
        if signal['indicator'] == 'atr_breakout':
            # The more the price change exceeds the threshold, the stronger the signal
            strength = min(0.3, (signal['value'] / signal['threshold'] - 1) * 0.5)
            confidence += strength
        
        # Factor 2: Volume confirmation
        if 'volume' in data.columns:
            # Check if volume is above average during signal
            avg_volume = data['volume'].rolling(window=20).mean().iloc[signal_idx]
            if data['volume'].iloc[signal_idx] > avg_volume * 1.5:
                confidence += 0.1
        
        # Factor 3: Trend confirmation
        # For a volatility breakout, check if it's in the direction of the trend
        if signal_idx >= 50:  # Make sure we have enough data
            short_ma = data['close'].rolling(window=20).mean().iloc[signal_idx]
            long_ma = data['close'].rolling(window=50).mean().iloc[signal_idx]
            
            # If short MA > long MA, uptrend
            trend_up = short_ma > long_ma
            
            # If signal aligns with trend, increase confidence
            if (signal['type'] == 'buy' and trend_up) or (signal['type'] == 'sell' and not trend_up):
                confidence += 0.15
        
        # Cap confidence between 0-1
        return max(0.0, min(1.0, confidence))


class TrendAnalysisAgent(TechnicalAnalysisAgent):
    """
    Agent specializing in trend analysis using moving averages and other trend indicators.
    
    This agent identifies trends, trend changes, and continuation patterns.
    """
    
    def __init__(self, name: str = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the trend analysis agent.
        
        Args:
            name: Optional name for the agent instance
            config: Configuration dictionary with parameters for indicators and signal generation
        """
        # Set default config values for trend analysis
        default_config = {
            'short_period': 20,
            'medium_period': 50,
            'long_period': 200,
            'ema_period': 20,
            'evaluation_periods': 10,
        }
        
        # Merge with provided config
        if config:
            config = {**default_config, **config}
        else:
            config = default_config
            
        super().__init__(name=name or "TrendAgent", config=config)
    
    def compute_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Compute trend indicators.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            Dictionary mapping indicator names to computed values
        """
        # Calculate Simple Moving Averages
        self.indicators['sma_short'] = TAIndicatorFactory.create_indicator(
            'SMA', 
            data, 
            {'timeperiod': self.config['short_period']}
        )
        
        self.indicators['sma_medium'] = TAIndicatorFactory.create_indicator(
            'SMA', 
            data, 
            {'timeperiod': self.config['medium_period']}
        )
        
        self.indicators['sma_long'] = TAIndicatorFactory.create_indicator(
            'SMA', 
            data, 
            {'timeperiod': self.config['long_period']}
        )
        
        # Calculate Exponential Moving Average
        self.indicators['ema'] = TAIndicatorFactory.create_indicator(
            'EMA', 
            data, 
            {'timeperiod': self.config['ema_period']}
        )
        
        return self.indicators
    
    def generate_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Generate trading signals based on trend indicators.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            List of signal dictionaries with type, timestamp, indicator, and confidence
        """
        # Compute indicators if not already done
        if not self.indicators:
            self.compute_indicators(data)
            
        signals = []
        
        # Generate moving average crossover signals
        if 'sma_short' in self.indicators and 'sma_medium' in self.indicators:
            sma_short = self.indicators['sma_short']
            sma_medium = self.indicators['sma_medium']
            
            for i in range(1, len(sma_short)):
                # Skip if we don't have valid data
                if pd.isna(sma_short.iloc[i-1]) or pd.isna(sma_short.iloc[i]) or \
                   pd.isna(sma_medium.iloc[i-1]) or pd.isna(sma_medium.iloc[i]):
                    continue
                
                # Golden Cross: Short MA crosses above Medium MA (bullish)
                if sma_short.iloc[i-1] < sma_medium.iloc[i-1] and sma_short.iloc[i] > sma_medium.iloc[i]:
                    signal = {
                        'type': 'buy',
                        'timestamp': data.index[i],
                        'indicator': 'golden_cross',
                        'short_ma': sma_short.iloc[i],
                        'medium_ma': sma_medium.iloc[i]
                    }
                    signal['confidence'] = self.get_confidence_level(signal, data)
                    signals.append(signal)
                
                # Death Cross: Short MA crosses below Medium MA (bearish)
                elif sma_short.iloc[i-1] > sma_medium.iloc[i-1] and sma_short.iloc[i] < sma_medium.iloc[i]:
                    signal = {
                        'type': 'sell',
                        'timestamp': data.index[i],
                        'indicator': 'death_cross',
                        'short_ma': sma_short.iloc[i],
                        'medium_ma': sma_medium.iloc[i]
                    }
                    signal['confidence'] = self.get_confidence_level(signal, data)
                    signals.append(signal)
        
        # Generate price crossing EMA signals
        if 'ema' in self.indicators:
            ema = self.indicators['ema']
            
            for i in range(1, len(data)):
                # Skip if we don't have valid data
                if pd.isna(ema.iloc[i]):
                    continue
                
                # Price crosses above EMA (bullish)
                if data['close'].iloc[i-1] < ema.iloc[i-1] and data['close'].iloc[i] > ema.iloc[i]:
                    signal = {
                        'type': 'buy',
                        'timestamp': data.index[i],
                        'indicator': 'price_cross_ema',
                        'price': data['close'].iloc[i],
                        'ema': ema.iloc[i]
                    }
                    signal['confidence'] = self.get_confidence_level(signal, data)
                    signals.append(signal)
                
                # Price crosses below EMA (bearish)
                elif data['close'].iloc[i-1] > ema.iloc[i-1] and data['close'].iloc[i] < ema.iloc[i]:
                    signal = {
                        'type': 'sell',
                        'timestamp': data.index[i],
                        'indicator': 'price_cross_ema',
                        'price': data['close'].iloc[i],
                        'ema': ema.iloc[i]
                    }
                    signal['confidence'] = self.get_confidence_level(signal, data)
                    signals.append(signal)
        
        self.signals = signals
        return signals
    
    def get_confidence_level(self, signal: Dict[str, Any], data: pd.DataFrame) -> float:
        """
        Calculate confidence level for a trend signal.
        
        Args:
            signal: Signal dictionary with metadata
            data: Market data as a pandas DataFrame
            
        Returns:
            Confidence level between 0 and 1
        """
        confidence = 0.5  # Base confidence
        
        # Get the index for the signal
        signal_idx = self._get_index_from_timestamp(signal['timestamp'], data)
        
        # Factor 1: Long-term trend alignment
        if 'sma_long' in self.indicators and signal_idx < len(self.indicators['sma_long']):
            long_ma = self.indicators['sma_long'].iloc[signal_idx]
            if not pd.isna(long_ma):
                # If signal aligns with long-term trend, increase confidence
                if (signal['type'] == 'buy' and data['close'].iloc[signal_idx] > long_ma) or \
                   (signal['type'] == 'sell' and data['close'].iloc[signal_idx] < long_ma):
                    confidence += 0.15
        
        # Factor 2: Signal strength
        if signal['indicator'] == 'golden_cross' or signal['indicator'] == 'death_cross':
            # The larger the gap between MAs, the stronger the signal
            ma_diff_pct = abs(signal['short_ma'] - signal['medium_ma']) / signal['medium_ma']
            confidence += min(0.2, ma_diff_pct * 20)
        
        # Factor 3: Volume confirmation
        if 'volume' in data.columns:
            # Check if volume is above average during signal
            avg_volume = data['volume'].rolling(window=20).mean().iloc[signal_idx]
            if data['volume'].iloc[signal_idx] > avg_volume * 1.5:
                confidence += 0.1
        
        # Cap confidence between 0-1
        return max(0.0, min(1.0, confidence))


class PatternRecognitionAgent(TechnicalAnalysisAgent):
    """
    Agent specializing in chart pattern recognition.
    
    This agent uses TA-Lib's pattern recognition capabilities to identify
    common chart patterns like head and shoulders, double tops, etc.
    """
    
    def __init__(self, name: str = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the pattern recognition agent.
        
        Args:
            name: Optional name for the agent instance
            config: Configuration dictionary with parameters for indicators and signal generation
        """
        # Set default config values for pattern recognition
        default_config = {
            'patterns': [
                'CDLENGULFING',        # Engulfing pattern
                'CDLHAMMER',           # Hammer
                'CDLMORNINGSTAR',      # Morning Star
                'CDLEVENINGSTAR',      # Evening Star
                'CDLDOJI',             # Doji
                'CDLHARAMI',           # Harami pattern
                'CDLPIERCING',         # Piercing pattern
                'CDLDARKCLOUDCOVER',   # Dark Cloud Cover
                'CDLMARUBOZU',         # Marubozu
                'CDLSHOOTINGSTAR',     # Shooting Star
            ],
            'evaluation_periods': 10,
        }
        
        # Merge with provided config
        if config:
            config = {**default_config, **config}
        else:
            config = default_config
            
        super().__init__(name=name or "PatternAgent", config=config)
        
        # Verify TA-Lib is available as it's required for pattern recognition
        if not self.talib_available:
            raise ImportError("TA-Lib is required for pattern recognition but is not available.")
    
    def compute_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Compute pattern recognition indicators.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            Dictionary mapping indicator names to computed values
        """
        # For pattern recognition, we don't compute traditional indicators
        # Instead, we'll be using TA-Lib's pattern recognition functions directly
        # in the generate_signals method
        return self.indicators
    
    def generate_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Generate trading signals based on chart patterns.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            List of signal dictionaries with type, timestamp, indicator, and confidence
        """
        import talib
        
        signals = []
        
        # Check for each configured pattern
        for pattern_name in self.config['patterns']:
            # Get the pattern function
            if hasattr(talib, pattern_name):
                pattern_func = getattr(talib, pattern_name)
                
                # Calculate the pattern
                pattern_result = pattern_func(
                    data['open'].values,
                    data['high'].values,
                    data['low'].values,
                    data['close'].values
                )
                
                # Convert to Series
                pattern_series = pd.Series(pattern_result, index=data.index)
                
                # Find where patterns are detected
                for i in range(len(pattern_series)):
                    value = pattern_series.iloc[i]
                    
                    # Non-zero values indicate pattern detection
                    if value != 0:
                        # Determine signal type based on the pattern value
                        # Positive values are bullish, negative are bearish
                        signal_type = 'buy' if value > 0 else 'sell'
                        
                        signal = {
                            'type': signal_type,
                            'timestamp': data.index[i],
                            'indicator': pattern_name,
                            'value': abs(value),
                            'raw_value': value
                        }
                        signal['confidence'] = self.get_confidence_level(signal, data)
                        signals.append(signal)
        
        self.signals = signals
        return signals
    
    def get_confidence_level(self, signal: Dict[str, Any], data: pd.DataFrame) -> float:
        """
        Calculate confidence level for a pattern signal.
        
        Args:
            signal: Signal dictionary with metadata
            data: Market data as a pandas DataFrame
            
        Returns:
            Confidence level between 0 and 1
        """
        confidence = 0.5  # Base confidence
        
        # Get the index for the signal
        signal_idx = self._get_index_from_timestamp(signal['timestamp'], data)
        
        # Factor 1: Pattern strength
        # For TA-Lib patterns, higher absolute values sometimes indicate stronger patterns
        # (This varies by pattern type)
        confidence += min(0.2, signal['value'] * 0.1)
        
        # Factor 2: Volume confirmation
        if 'volume' in data.columns:
            # Check if volume is above average during pattern formation
            avg_volume = data['volume'].rolling(window=20).mean().iloc[signal_idx]
            if data['volume'].iloc[signal_idx] > avg_volume * 1.5:
                confidence += 0.15
        
        # Factor 3: Trend context
        # Patterns are more reliable when they align with the broader trend
        if signal_idx >= 50:  # Make sure we have enough data
            short_ma = data['close'].rolling(window=20).mean().iloc[signal_idx]
            long_ma = data['close'].rolling(window=50).mean().iloc[signal_idx]
            
            # If short MA > long MA, uptrend
            trend_up = short_ma > long_ma
            
            # If pattern aligns with trend, increase confidence
            if (signal['type'] == 'buy' and trend_up) or (signal['type'] == 'sell' and not trend_up):
                confidence += 0.1
        
        # Cap confidence between 0-1
        return max(0.0, min(1.0, confidence))


class CombinedAnalysisAgent(TechnicalAnalysisAgent):
    """
    Agent combining multiple analysis types for comprehensive market analysis.
    
    This agent integrates signals from momentum, volatility, trend, and pattern
    recognition to provide a more robust trading strategy.
    """
    
    def __init__(self, name: str = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the combined analysis agent.
        
        Args:
            name: Optional name for the agent instance
            config: Configuration dictionary with parameters for indicators and signal generation
        """
        # Set default config values
        default_config = {
            'agent_weights': {
                'momentum': 0.25,
                'volatility': 0.25,
                'trend': 0.25,
                'pattern': 0.25
            },
            'confidence_threshold': 0.6,
            'evaluation_periods': 10,
        }
        
        # Merge with provided config
        if config:
            config = {**default_config, **config}
        else:
            config = default_config
            
        super().__init__(name=name or "CombinedAgent", config=config)
        
        # Create sub-agents
        self.momentum_agent = MomentumAnalysisAgent(config=config.get('momentum_config'))
        self.volatility_agent = VolatilityAnalysisAgent(config=config.get('volatility_config'))
        self.trend_agent = TrendAnalysisAgent(config=config.get('trend_config'))
        
        # Pattern agent requires TA-Lib
        if self.talib_available:
            self.pattern_agent = PatternRecognitionAgent(config=config.get('pattern_config'))
        else:
            self.pattern_agent = None
    
    def compute_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Compute indicators from all sub-agents.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            Dictionary mapping indicator names to computed values
        """
        # Delegate to sub-agents
        momentum_indicators = self.momentum_agent.compute_indicators(data)
        volatility_indicators = self.volatility_agent.compute_indicators(data)
        trend_indicators = self.trend_agent.compute_indicators(data)
        
        # Combine all indicators
        self.indicators = {}
        self.indicators.update(momentum_indicators)
        self.indicators.update(volatility_indicators)
        self.indicators.update(trend_indicators)
        
        # Add pattern indicators if available
        if self.pattern_agent:
            pattern_indicators = self.pattern_agent.compute_indicators(data)
            self.indicators.update(pattern_indicators)
        
        return self.indicators
    
    def generate_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Generate trading signals from all sub-agents and combine them.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            List of signal dictionaries with type, timestamp, indicator, and confidence
        """
        # Get signals from each agent
        momentum_signals = self.momentum_agent.generate_signals(data)
        volatility_signals = self.volatility_agent.generate_signals(data)
        trend_signals = self.trend_agent.generate_signals(data)
        pattern_signals = self.pattern_agent.generate_signals(data) if self.pattern_agent else []
        
        # Combine all signals
        all_signals = []
        all_signals.extend(self._tag_signals(momentum_signals, 'momentum'))
        all_signals.extend(self._tag_signals(volatility_signals, 'volatility'))
        all_signals.extend(self._tag_signals(trend_signals, 'trend'))
        all_signals.extend(self._tag_signals(pattern_signals, 'pattern'))
        
        # Apply weights to adjust confidence
        for signal in all_signals:
            agent_type = signal['agent_type']
            weight = self.config['agent_weights'].get(agent_type, 0.25)
            signal['confidence'] = signal['confidence'] * weight
        
        # Sort by timestamp
        all_signals.sort(key=lambda x: x['timestamp'])
        
        # Aggregate signals for the same time periods
        aggregated_signals = self._aggregate_signals(all_signals)
        
        # Filter by confidence threshold
        filtered_signals = [s for s in aggregated_signals 
                           if s['confidence'] >= self.config['confidence_threshold']]
        
        self.signals = filtered_signals
        return filtered_signals
    
    def _tag_signals(self, signals: List[Dict[str, Any]], agent_type: str) -> List[Dict[str, Any]]:
        """
        Tag signals with their source agent type.
        
        Args:
            signals: List of signals to tag
            agent_type: Type of agent that generated the signals
            
        Returns:
            Tagged signals
        """
        for signal in signals:
            signal['agent_type'] = agent_type
        return signals
    
    def _aggregate_signals(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Aggregate signals for the same time periods, combining confidences.
        
        Args:
            signals: List of signals to aggregate
            
        Returns:
            Aggregated signals
        """
        # Group signals by timestamp and type
        signal_groups = {}
        for signal in signals:
            key = (signal['timestamp'], signal['type'])
            if key not in signal_groups:
                signal_groups[key] = []
            signal_groups[key].append(signal)
        
        # Aggregate each group
        aggregated = []
        for (timestamp, signal_type), group in signal_groups.items():
            # Calculate combined confidence
            # More sophisticated combination could be implemented
            combined_confidence = sum(s['confidence'] for s in group)
            if len(group) > 1:
                # Apply a bonus for multiple signals
                combined_confidence += 0.1
            
            # Cap at 1.0
            combined_confidence = min(1.0, combined_confidence)
            
            # Create aggregated signal
            aggregated_signal = {
                'type': signal_type,
                'timestamp': timestamp,
                'indicator': 'combined',
                'confidence': combined_confidence,
                'contributing_signals': len(group),
                'agent_types': list(set(s['agent_type'] for s in group)),
                'indicators': list(set(s['indicator'] for s in group))
            }
            aggregated.append(aggregated_signal)
        
        # Sort by timestamp
        aggregated.sort(key=lambda x: x['timestamp'])
        
        return aggregated
    
    def get_confidence_level(self, signal: Dict[str, Any], data: pd.DataFrame) -> float:
        """
        This method is not used directly in CombinedAnalysisAgent.
        Confidence is handled in the _aggregate_signals method.
        """
        # This should never be called directly
        raise NotImplementedError(
            "CombinedAnalysisAgent calculates confidence through aggregation, not this method."
        ) 