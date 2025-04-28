"""
Market Condition Analyzer Module

This module implements a market condition analyzer that detects market anomalies,
regime changes, and extreme market conditions.
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from .technical_analysis.agent import TechnicalAnalysisAgent
from .technical_analysis.indicator_factory import TAIndicatorFactory

logger = logging.getLogger(__name__)


class MarketConditionAnalyzer(TechnicalAnalysisAgent):
    """
    Market Condition Analyzer for detecting market anomalies, regime changes,
    and extreme market conditions.
    
    This agent monitors market data for:
    1. Volatility anomalies (excessive or unusually low volatility)
    2. Liquidity changes (unusual volume patterns)
    3. Trend disruptions and regime changes
    4. Correlation breakdowns or anomalies
    5. Market pattern repetitions (fractal patterns)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the market condition analyzer.
        
        Args:
            config: Configuration dictionary with settings
        """
        default_config = {
            # Volatility settings
            'vol_window': 20,
            'vol_threshold_high': 2.5,  # Standard deviations above mean for high volatility
            'vol_threshold_low': 0.5,   # Standard deviations below mean for low volatility
            
            # Liquidity settings
            'volume_window': 20,
            'volume_threshold': 2.0,    # Standard deviations for unusual volume
            
            # Trend settings
            'trend_short_window': 20,
            'trend_long_window': 50,
            'trend_strength_threshold': 0.8,  # Minimum for strong trend
            
            # Regime detection settings
            'regime_window': 50,
            'regime_threshold': 0.5,  # Minimum change to signal regime shift
            
            # Correlation settings
            'correlation_assets': [],  # Additional assets to track correlations with
            'correlation_window': 30,
            'correlation_threshold': 0.3,  # Change threshold for correlation breakdown
            
            # Market anomaly settings
            'anomaly_sensitivity': 3.0,  # Standard deviations for anomaly detection
            'anomaly_lookback': 100,     # Lookback period for anomaly detection
            
            # Pattern recognition settings
            'pattern_sensitivity': 0.85, # Similarity threshold for pattern matching (0-1)
            'pattern_min_length': 5,     # Minimum candles for a pattern
            'pattern_max_length': 20     # Maximum candles for a pattern
        }
        
        # Update with user-provided config
        if config:
            default_config.update(config)
        
        super().__init__(config=default_config)
        self.name = "market_condition_analyzer"
        self.description = "Analyzes market conditions for anomalies and regime changes"
        
        # Initialize result containers
        self.conditions = {
            'volatility_state': 'normal',
            'liquidity_state': 'normal',
            'trend_state': 'neutral',
            'regime_state': 'normal',
            'correlation_state': 'normal',
            'anomalies': []
        }
        
        self.pattern_library = {}  # Storage for detected patterns
        self.last_analysis_time = None
        
    def compute_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Compute indicators related to market conditions.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            Dictionary mapping indicator names to computed values
        """
        # Ensure data is sorted by time
        if not data.index.is_monotonic_increasing:
            data = data.sort_index()
            
        # Calculate volatility indicators
        self.indicators['atr'] = TAIndicatorFactory.create_indicator(
            'ATR', 
            data, 
            {'timeperiod': self.config['vol_window']}
        )
        
        # Calculate returns and realized volatility
        data['returns'] = data['close'].pct_change()
        self.indicators['realized_vol'] = data['returns'].rolling(
            window=self.config['vol_window']
        ).std() * np.sqrt(252)  # Annualized
        
        # Calculate moving averages for trend analysis
        self.indicators['sma_short'] = TAIndicatorFactory.create_indicator(
            'SMA', 
            data, 
            {'timeperiod': self.config['trend_short_window']}
        )
        
        self.indicators['sma_long'] = TAIndicatorFactory.create_indicator(
            'SMA', 
            data, 
            {'timeperiod': self.config['trend_long_window']}
        )
        
        # Calculate volume indicators
        if 'volume' in data.columns:
            self.indicators['volume_ma'] = data['volume'].rolling(
                window=self.config['volume_window']
            ).mean()
            self.indicators['volume_std'] = data['volume'].rolling(
                window=self.config['volume_window']
            ).std()
        
        return self.indicators
        
    def generate_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Generate signals based on market condition analysis.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            List of signal dictionaries with type, timestamp, indicator, and confidence
        """
        # Compute indicators if not already done
        if not self.indicators:
            self.compute_indicators(data)
            
        signals = []
        
        # Analyze market conditions
        self._analyze_volatility(data)
        self._analyze_liquidity(data)
        self._analyze_trend(data)
        self._analyze_regime_changes(data)
        self._detect_anomalies(data)
        
        # Generate signals based on market conditions
        timestamp = data.index[-1]  # Most recent timestamp
        
        # Check for extreme volatility conditions
        if self.conditions['volatility_state'] in ['extremely_high', 'extremely_low']:
            signal_type = 'caution' if self.conditions['volatility_state'] == 'extremely_high' else 'opportunity'
            signal = {
                'type': signal_type,
                'timestamp': timestamp,
                'indicator': 'volatility_anomaly',
                'condition': self.conditions['volatility_state'],
                'value': self.indicators['realized_vol'].iloc[-1]
            }
            signal['confidence'] = self.get_confidence_level(signal, data)
            signals.append(signal)
        
        # Check for liquidity anomalies
        if self.conditions['liquidity_state'] != 'normal':
            signal = {
                'type': 'caution',
                'timestamp': timestamp,
                'indicator': 'liquidity_anomaly',
                'condition': self.conditions['liquidity_state'],
                'value': data['volume'].iloc[-1] if 'volume' in data.columns else None
            }
            signal['confidence'] = self.get_confidence_level(signal, data)
            signals.append(signal)
            
        # Check for regime changes
        if self.conditions['regime_state'] == 'changing':
            signal = {
                'type': 'regime_change',
                'timestamp': timestamp,
                'indicator': 'regime_change',
                'condition': 'transition',
                'value': None
            }
            signal['confidence'] = self.get_confidence_level(signal, data)
            signals.append(signal)
            
        # Add detected anomalies
        for anomaly in self.conditions['anomalies']:
            signal = {
                'type': 'anomaly',
                'timestamp': timestamp,
                'indicator': anomaly['type'],
                'condition': anomaly['severity'],
                'value': anomaly['value']
            }
            signal['confidence'] = self.get_confidence_level(signal, data)
            signals.append(signal)
            
        self.signals = signals
        self.last_analysis_time = datetime.now()
        
        return signals
        
    def get_confidence_level(self, signal: Dict[str, Any], data: pd.DataFrame) -> float:
        """
        Calculate confidence level for market condition signals.
        
        Args:
            signal: Signal dictionary with metadata
            data: Market data as a pandas DataFrame
            
        Returns:
            Confidence level between 0 and 1
        """
        confidence = 0.5  # Base confidence
        
        # Adjust confidence based on signal type
        if signal['indicator'] == 'volatility_anomaly':
            # Higher deviation from normal = higher confidence
            if 'realized_vol' in self.indicators:
                realized_vol = self.indicators['realized_vol'].iloc[-1]
                vol_mean = self.indicators['realized_vol'].mean()
                vol_std = self.indicators['realized_vol'].std()
                
                if vol_std > 0:
                    # Calculate z-score
                    z_score = abs(realized_vol - vol_mean) / vol_std
                    # Convert to confidence (capped at 0.4 addition)
                    confidence += min(0.4, z_score / 10)
        
        elif signal['indicator'] == 'liquidity_anomaly':
            # Volume-based confidence adjustment
            if 'volume' in data.columns and 'volume_ma' in self.indicators and 'volume_std' in self.indicators:
                latest_vol = data['volume'].iloc[-1]
                vol_ma = self.indicators['volume_ma'].iloc[-1]
                vol_std = self.indicators['volume_std'].iloc[-1]
                
                if vol_std > 0:
                    # Calculate z-score
                    z_score = abs(latest_vol - vol_ma) / vol_std
                    # Convert to confidence (capped at 0.3 addition)
                    confidence += min(0.3, z_score / 10)
        
        elif signal['indicator'] == 'regime_change':
            # Regime change confidence based on trend strength
            if 'sma_short' in self.indicators and 'sma_long' in self.indicators:
                # Add confidence based on moving average divergence
                ma_divergence = abs(
                    self.indicators['sma_short'].iloc[-1] / self.indicators['sma_long'].iloc[-1] - 1
                )
                confidence += min(0.35, ma_divergence * 5)
        
        # For anomaly signals, base confidence on the severity
        elif signal['type'] == 'anomaly':
            if signal['condition'] == 'extreme':
                confidence += 0.3
            elif signal['condition'] == 'significant':
                confidence += 0.2
            elif signal['condition'] == 'moderate':
                confidence += 0.1
                
        # Cap confidence between 0-1
        return max(0.0, min(1.0, confidence))
        
    def _analyze_volatility(self, data: pd.DataFrame) -> None:
        """
        Analyze market volatility conditions.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        # Check if we have enough data for volatility analysis
        if 'realized_vol' not in self.indicators or len(self.indicators['realized_vol']) < self.config['vol_window']:
            self.conditions['volatility_state'] = 'unknown'
            return
            
        # Get current volatility
        current_vol = self.indicators['realized_vol'].iloc[-1]
        
        # Calculate volatility statistics from history
        vol_data = self.indicators['realized_vol'].dropna()
        vol_mean = vol_data.mean()
        vol_std = vol_data.std()
        
        # Determine volatility state
        if current_vol > vol_mean + (self.config['vol_threshold_high'] * vol_std):
            if current_vol > vol_mean + (2 * self.config['vol_threshold_high'] * vol_std):
                self.conditions['volatility_state'] = 'extremely_high'
            else:
                self.conditions['volatility_state'] = 'high'
        elif current_vol < vol_mean - (self.config['vol_threshold_low'] * vol_std):
            if current_vol < vol_mean - (2 * self.config['vol_threshold_low'] * vol_std):
                self.conditions['volatility_state'] = 'extremely_low'
            else:
                self.conditions['volatility_state'] = 'low'
        else:
            self.conditions['volatility_state'] = 'normal'
            
    def _analyze_liquidity(self, data: pd.DataFrame) -> None:
        """
        Analyze market liquidity conditions based on volume.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        # Check if we have volume data and enough history
        if 'volume' not in data.columns or 'volume_ma' not in self.indicators or 'volume_std' not in self.indicators:
            self.conditions['liquidity_state'] = 'unknown'
            return
            
        if len(self.indicators['volume_ma']) < self.config['volume_window']:
            self.conditions['liquidity_state'] = 'unknown'
            return
            
        # Get current volume
        current_volume = data['volume'].iloc[-1]
        volume_ma = self.indicators['volume_ma'].iloc[-1]
        volume_std = self.indicators['volume_std'].iloc[-1]
        
        # Check for abnormal volume
        if volume_std > 0:
            z_score = (current_volume - volume_ma) / volume_std
            
            if z_score > self.config['volume_threshold']:
                self.conditions['liquidity_state'] = 'high'
            elif z_score < -self.config['volume_threshold']:
                self.conditions['liquidity_state'] = 'low'
            else:
                self.conditions['liquidity_state'] = 'normal'
        else:
            self.conditions['liquidity_state'] = 'normal'
            
    def _analyze_trend(self, data: pd.DataFrame) -> None:
        """
        Analyze current market trend state.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        # Check if we have necessary indicators
        if 'sma_short' not in self.indicators or 'sma_long' not in self.indicators:
            self.conditions['trend_state'] = 'unknown'
            return
            
        if len(self.indicators['sma_short']) < self.config['trend_short_window'] or \
           len(self.indicators['sma_long']) < self.config['trend_long_window']:
            self.conditions['trend_state'] = 'unknown'
            return
            
        # Get most recent values
        sma_short = self.indicators['sma_short'].iloc[-1]
        sma_long = self.indicators['sma_long'].iloc[-1]
        
        # Determine trend direction
        if sma_short > sma_long:
            # Uptrend - determine strength
            strength = (sma_short / sma_long) - 1
            if strength > self.config['trend_strength_threshold']:
                self.conditions['trend_state'] = 'strong_uptrend'
            else:
                self.conditions['trend_state'] = 'uptrend'
        elif sma_short < sma_long:
            # Downtrend - determine strength
            strength = 1 - (sma_short / sma_long)
            if strength > self.config['trend_strength_threshold']:
                self.conditions['trend_state'] = 'strong_downtrend'
            else:
                self.conditions['trend_state'] = 'downtrend'
        else:
            self.conditions['trend_state'] = 'neutral'
            
    def _analyze_regime_changes(self, data: pd.DataFrame) -> None:
        """
        Detect market regime changes.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        # Check if we have enough data
        if len(data) < self.config['regime_window'] * 2:
            self.conditions['regime_state'] = 'unknown'
            return
            
        # Get recent and previous periods
        recent_period = data.iloc[-self.config['regime_window']:]
        previous_period = data.iloc[-2*self.config['regime_window']:-self.config['regime_window']]
        
        # Calculate metrics for regime detection
        recent_vol = recent_period['returns'].std()
        previous_vol = previous_period['returns'].std()
        
        vol_change = abs(recent_vol / previous_vol - 1) if previous_vol > 0 else 0
        
        # Detect trend changes
        recent_trend = recent_period['close'].iloc[-1] / recent_period['close'].iloc[0] - 1
        previous_trend = previous_period['close'].iloc[-1] / previous_period['close'].iloc[0] - 1
        
        trend_change = (recent_trend * previous_trend < 0)  # True if trend direction changed
        
        # Determine regime state
        if vol_change > self.config['regime_threshold'] or trend_change:
            self.conditions['regime_state'] = 'changing'
        else:
            self.conditions['regime_state'] = 'stable'
            
    def _detect_anomalies(self, data: pd.DataFrame) -> None:
        """
        Detect various market anomalies.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        # Reset anomalies list
        self.conditions['anomalies'] = []
        
        # Check if we have enough data
        if len(data) < self.config['anomaly_lookback']:
            return
            
        # Subset for analysis
        analysis_data = data.iloc[-self.config['anomaly_lookback']:]
        
        # 1. Price gap anomalies
        self._detect_price_gaps(analysis_data)
        
        # 2. Volatility clustering anomalies
        self._detect_volatility_clustering(analysis_data)
        
        # 3. Volume-price divergence anomalies
        self._detect_volume_price_divergence(analysis_data)
        
        # 4. Correlation breakdowns
        self._detect_correlation_breakdowns(data)
        
        # 5. Pattern repetition detection
        self._detect_pattern_repetition(analysis_data)
            
    def _detect_price_gaps(self, data: pd.DataFrame) -> None:
        """
        Detect significant price gaps.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        if len(data) < 2:
            return
            
        # Calculate gaps as percentage of price
        data['gap'] = (data['open'] - data['close'].shift(1)) / data['close'].shift(1)
        
        # Calculate statistical thresholds
        gap_mean = data['gap'].mean()
        gap_std = data['gap'].std()
        
        if gap_std == 0:
            return
            
        # Check most recent gap
        latest_gap = data['gap'].iloc[-1]
        z_score = abs(latest_gap - gap_mean) / gap_std
        
        if z_score > self.config['anomaly_sensitivity']:
            severity = 'extreme' if z_score > 2 * self.config['anomaly_sensitivity'] else 'significant'
            gap_direction = 'up' if latest_gap > 0 else 'down'
            
            self.conditions['anomalies'].append({
                'type': 'price_gap',
                'direction': gap_direction,
                'severity': severity,
                'value': latest_gap,
                'z_score': z_score
            })
            
    def _detect_volatility_clustering(self, data: pd.DataFrame) -> None:
        """
        Detect volatility clustering anomalies.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        if 'returns' not in data.columns or len(data) < self.config['vol_window'] * 2:
            return
            
        # Calculate absolute returns for volatility clustering
        data['abs_returns'] = data['returns'].abs()
        
        # Check for autocorrelation in absolute returns (sign of volatility clustering)
        recent_abs_returns = data['abs_returns'].iloc[-self.config['vol_window']:]
        if len(recent_abs_returns.dropna()) < self.config['vol_window'] / 2:
            return
            
        # Calculate autocorrelation
        try:
            from statsmodels.stats.diagnostic import acorr_ljungbox
            result = acorr_ljungbox(recent_abs_returns.dropna(), lags=[1])
            
            # Check if autocorrelation is significant
            p_value = result[1][0]
            
            if p_value < 0.05:  # Statistically significant
                recent_vol = recent_abs_returns.mean()
                historical_vol = data['abs_returns'].iloc[:-self.config['vol_window']].mean()
                
                if recent_vol > historical_vol * 1.5:
                    self.conditions['anomalies'].append({
                        'type': 'volatility_clustering',
                        'severity': 'significant' if p_value < 0.01 else 'moderate',
                        'value': recent_vol / historical_vol,
                        'p_value': p_value
                    })
        except:
            # Skip if statsmodels is not available or calculation fails
            pass
            
    def _detect_volume_price_divergence(self, data: pd.DataFrame) -> None:
        """
        Detect divergence between price moves and volume.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        if 'volume' not in data.columns or len(data) < self.config['vol_window']:
            return
            
        # Calculate price changes and volume changes
        data['price_change'] = data['close'].pct_change()
        data['volume_change'] = data['volume'].pct_change()
        
        # Get recent data
        recent_data = data.iloc[-self.config['vol_window']:]
        
        # Check for price increase with decreasing volume (potential exhaustion)
        if recent_data['price_change'].iloc[-1] > 0 and recent_data['volume_change'].iloc[-1] < -0.1:
            # Check if this is a pattern over several days
            price_up_days = (recent_data['price_change'] > 0).sum()
            volume_down_days = (recent_data['volume_change'] < 0).sum()
            
            if price_up_days > self.config['vol_window'] * 0.7 and volume_down_days > self.config['vol_window'] * 0.7:
                self.conditions['anomalies'].append({
                    'type': 'volume_price_divergence',
                    'subtype': 'bearish_divergence',
                    'severity': 'significant',
                    'value': recent_data['price_change'].iloc[-1]
                })
                
        # Check for price decrease with decreasing volume (potential bottoming)
        elif recent_data['price_change'].iloc[-1] < 0 and recent_data['volume_change'].iloc[-1] < -0.1:
            # Check if this is a pattern over several days
            price_down_days = (recent_data['price_change'] < 0).sum()
            volume_down_days = (recent_data['volume_change'] < 0).sum()
            
            if price_down_days > self.config['vol_window'] * 0.7 and volume_down_days > self.config['vol_window'] * 0.7:
                self.conditions['anomalies'].append({
                    'type': 'volume_price_divergence',
                    'subtype': 'bullish_divergence',
                    'severity': 'moderate',
                    'value': recent_data['price_change'].iloc[-1]
                })
                
    def _detect_correlation_breakdowns(self, data: pd.DataFrame) -> None:
        """
        Detect breakdowns in typical correlations.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        # Correlation breakdown detection would require data for correlated assets
        # This is a placeholder implementation
        pass
            
    def _detect_pattern_repetition(self, data: pd.DataFrame) -> None:
        """
        Detect repeating price patterns (fractals).
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
        """
        # Pattern repetition detection requires complex time series matching
        # This is a placeholder implementation
        pass
            
    def get_market_conditions(self) -> Dict[str, Any]:
        """
        Get current market conditions analysis.
        
        Returns:
            Dictionary with market conditions analysis
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'last_analysis': self.last_analysis_time.isoformat() if self.last_analysis_time else None,
            'conditions': self.conditions,
            'signals': self.signals
        } 