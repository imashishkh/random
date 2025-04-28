"""
Signal generators for fundamental analysis.

This module contains classes for generating trading signals from fundamental data.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import numpy as np

from ...utils.logging.logger import get_logger

logger = get_logger()


class FundamentalSignalGenerator:
    """
    Generates trading signals based on fundamental data analysis.
    
    This class combines financial metrics, economic indicators, and news sentiment
    to generate trading signals for forex markets.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the signal generator.
        
        Args:
            config: Configuration dictionary with parameters for signal generation
        """
        self.config = config or {}
        
        # Default weights for different data types
        self.weights = self.config.get('weights', {
            'financial': 0.3,
            'economic': 0.4,
            'news': 0.3
        })
        
        # Signal thresholds
        self.thresholds = self.config.get('thresholds', {
            'buy': 0.6,  # Strong positive signal
            'sell': -0.6,  # Strong negative signal
            'neutral': 0.2  # Neutral zone threshold
        })
        
        # Currency pair to major economy mapping
        self.currency_economies = {
            'EUR/USD': {'base': 'EUR', 'quote': 'USD'},
            'USD/JPY': {'base': 'USD', 'quote': 'JP'},
            'GBP/USD': {'base': 'GBP', 'quote': 'USD'},
            'AUD/USD': {'base': 'AUD', 'quote': 'USD'},
            'USD/CAD': {'base': 'USD', 'quote': 'CAD'},
            'NZD/USD': {'base': 'NZD', 'quote': 'USD'},
            'USD/CHF': {'base': 'USD', 'quote': 'CHF'}
        }
        
        # Major economies to relevant company tickers
        self.economy_tickers = {
            'USD': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'JPM', 'BRK-A', 'JNJ', 'WMT', 'PG', 'XOM'],
            'EUR': ['SAP.DE', 'SIE.DE', 'LVMH.PA', 'ASML.AS', 'BAYN.DE', 'BNP.PA', 'DTE.DE', 'SAN.MC', 'ABI.BR', 'OR.PA'],
            'GBP': ['HSBA.L', 'BP.L', 'GSK.L', 'ULVR.L', 'RIO.L', 'BATS.L', 'AZN.L', 'RDSB.L', 'DGE.L', 'LLOY.L'],
            'JP': ['7203.T', '6758.T', '9984.T', '8306.T', '6861.T', '9433.T', '6501.T', '7267.T', '8316.T', '9432.T'],
            'AUD': ['BHP.AX', 'CBA.AX', 'CSL.AX', 'NAB.AX', 'WBC.AX', 'ANZ.AX', 'MQG.AX', 'WES.AX', 'RIO.AX', 'TLS.AX'],
            'CAD': ['RY.TO', 'TD.TO', 'ENB.TO', 'BAM-A.TO', 'CNR.TO', 'BMO.TO', 'CP.TO', 'BNS.TO', 'SU.TO', 'CM.TO'],
            'NZD': ['AIR.NZ', 'FPH.NZ', 'SPK.NZ', 'MEL.NZ', 'CEN.NZ', 'MCY.NZ', 'MFT.NZ', 'ATM.NZ', 'FBU.NZ', 'ZEL.NZ'],
            'CHF': ['NESN.SW', 'ROG.SW', 'NOVN.SW', 'UHR.SW', 'ZURN.SW', 'SREN.SW', 'ABBN.SW', 'CSGN.SW', 'GIVN.SW', 'LONN.SW']
        }
        
    def generate_signal(self, 
                        currency_pair: str,
                        financial_data: Dict[str, Any],
                        economic_data: Dict[str, Any],
                        news_data: Dict[str, Any],
                        timeframe: str = 'medium') -> Dict[str, Any]:
        """
        Generate a trading signal based on fundamental data.
        
        Args:
            currency_pair: Currency pair (e.g., 'EUR/USD')
            financial_data: Financial metrics data
            economic_data: Economic indicators data
            news_data: News sentiment data
            timeframe: Signal timeframe ('short', 'medium', 'long')
            
        Returns:
            Dictionary with signal details
        """
        logger.info(f"Generating fundamental signal for {currency_pair}")
        
        # Check if we have data for this currency pair
        if currency_pair not in self.currency_economies:
            logger.warning(f"No economy mapping available for {currency_pair}")
            return self._generate_empty_signal(currency_pair)
        
        # Get the economies for this currency pair
        economies = self.currency_economies[currency_pair]
        base_economy = economies['base']
        quote_economy = economies['quote']
        
        # Analyze each data type
        financial_score = self._analyze_financial_data(financial_data, base_economy, quote_economy)
        economic_score = self._analyze_economic_data(economic_data, base_economy, quote_economy)
        news_score = self._analyze_news_data(news_data, currency_pair)
        
        # Calculate weighted average score
        weighted_score = (
            self.weights['financial'] * financial_score +
            self.weights['economic'] * economic_score +
            self.weights['news'] * news_score
        )
        
        # Determine signal type
        signal_type = self._determine_signal_type(weighted_score)
        
        # Calculate confidence based on signal strength and data quality
        confidence = min(abs(weighted_score), 1.0)
        
        # Determine timeframe impact
        if timeframe == 'short':
            # News has more impact on short-term
            adjusted_score = 0.5 * weighted_score + 0.5 * news_score
        elif timeframe == 'long':
            # Economic indicators have more impact on long-term
            adjusted_score = 0.4 * weighted_score + 0.6 * economic_score
        else:  # medium
            adjusted_score = weighted_score
        
        # Adjust confidence based on data quality and completeness
        confidence = self._adjust_confidence(confidence, financial_data, economic_data, news_data)
        
        # Create signal
        signal = {
            'type': signal_type,
            'currency_pair': currency_pair,
            'timeframe': timeframe,
            'score': weighted_score,
            'adjusted_score': adjusted_score,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'components': {
                'financial': financial_score,
                'economic': economic_score,
                'news': news_score
            },
            'details': {
                'base_economy': base_economy,
                'quote_economy': quote_economy
            }
        }
        
        logger.info(f"Generated {signal_type} signal for {currency_pair} with confidence {confidence:.2f}")
        return signal
    
    def _generate_empty_signal(self, currency_pair: str) -> Dict[str, Any]:
        """
        Generate an empty signal when data is not available.
        
        Args:
            currency_pair: Currency pair
            
        Returns:
            Empty signal dictionary
        """
        return {
            'type': 'neutral',
            'currency_pair': currency_pair,
            'timeframe': 'medium',
            'score': 0,
            'adjusted_score': 0,
            'confidence': 0,
            'timestamp': datetime.now().isoformat(),
            'components': {
                'financial': 0,
                'economic': 0,
                'news': 0
            },
            'error': 'Insufficient data for signal generation'
        }
    
    def _analyze_financial_data(self, financial_data: Dict[str, Any], base_economy: str, quote_economy: str) -> float:
        """
        Analyze financial data to determine relative economic strength.
        
        Args:
            financial_data: Financial metrics data
            base_economy: Base currency economy (e.g., 'EUR')
            quote_economy: Quote currency economy (e.g., 'USD')
            
        Returns:
            Score between -1 and 1 indicating relative strength (positive = base stronger)
        """
        # Check if we have data
        if not financial_data or 'error' in financial_data:
            logger.warning("Insufficient financial data for analysis")
            return 0
        
        # Get relevant tickers for both economies
        base_tickers = self.economy_tickers.get(base_economy, [])
        quote_tickers = self.economy_tickers.get(quote_economy, [])
        
        if not base_tickers or not quote_tickers:
            logger.warning(f"No ticker mapping for {base_economy} or {quote_economy}")
            return 0
        
        # Extract metrics for each economy
        base_metrics = []
        quote_metrics = []
        
        for ticker, data in financial_data.items():
            if 'metrics' not in data:
                continue
                
            metrics = data['metrics']
            
            # Create a score for this company based on various metrics
            company_score = 0
            
            # Revenue growth (higher is better)
            if 'revenue_growth' in metrics and metrics['revenue_growth'] is not None:
                company_score += min(max(metrics['revenue_growth'] * 2, -1), 1)
            
            # Profit margin (higher is better)
            if 'profit_margin' in metrics and metrics['profit_margin'] is not None:
                company_score += min(metrics['profit_margin'] * 5, 1)
            
            # ROE (higher is better)
            if 'roe' in metrics and metrics['roe'] is not None:
                company_score += min(metrics['roe'] * 2, 1)
            
            # Debt-to-equity (lower is better)
            if 'debt_to_equity' in metrics and metrics['debt_to_equity'] is not None:
                if metrics['debt_to_equity'] > 2:
                    company_score -= 0.5
                elif metrics['debt_to_equity'] < 1:
                    company_score += 0.5
            
            # Normalize score
            company_score = company_score / 3  # normalize to -1 to 1 range
            
            # Add to appropriate economy
            if ticker in base_tickers:
                base_metrics.append(company_score)
            elif ticker in quote_tickers:
                quote_metrics.append(company_score)
        
        # Calculate average scores for each economy
        if base_metrics:
            base_score = sum(base_metrics) / len(base_metrics)
        else:
            base_score = 0
            
        if quote_metrics:
            quote_score = sum(quote_metrics) / len(quote_metrics)
        else:
            quote_score = 0
        
        # Calculate relative strength (base vs quote)
        relative_score = base_score - quote_score
        
        # Limit to -1 to 1 range
        relative_score = max(min(relative_score, 1), -1)
        
        logger.debug(f"Financial analysis score: {relative_score:.2f} (base: {base_score:.2f}, quote: {quote_score:.2f})")
        return relative_score
    
    def _analyze_economic_data(self, economic_data: Dict[str, Any], base_economy: str, quote_economy: str) -> float:
        """
        Analyze economic indicators to determine relative economic strength.
        
        Args:
            economic_data: Economic indicators data
            base_economy: Base currency economy (e.g., 'EUR')
            quote_economy: Quote currency economy (e.g., 'USD')
            
        Returns:
            Score between -1 and 1 indicating relative strength (positive = base stronger)
        """
        # Check if we have data
        if not economic_data or '_metadata' not in economic_data or 'error' in economic_data.get('_metadata', {}):
            logger.warning("Insufficient economic data for analysis")
            return 0
        
        # Map economies to indicator prefixes
        economy_indicator_map = {
            'USD': 'US',
            'EUR': 'EUR',
            'GBP': 'UK',
            'JP': 'JP'
        }
        
        base_prefix = economy_indicator_map.get(base_economy)
        quote_prefix = economy_indicator_map.get(quote_economy)
        
        if not base_prefix or not quote_prefix:
            logger.warning(f"No indicator mapping for {base_economy} or {quote_economy}")
            return 0
        
        # Initialize scores
        base_scores = []
        quote_scores = []
        
        # Analyze GDP growth
        if f'{base_prefix}GDP' in economic_data and f'{quote_prefix}GDP' in economic_data:
            base_gdp = economic_data[f'{base_prefix}GDP']
            quote_gdp = economic_data[f'{quote_prefix}GDP']
            
            if not base_gdp.empty and not quote_gdp.empty:
                # Calculate annual growth rates
                base_gdp_growth = base_gdp.pct_change(periods=4).iloc[-1]  # annual growth
                quote_gdp_growth = quote_gdp.pct_change(periods=4).iloc[-1]  # annual growth
                
                # Stronger GDP growth is positive
                gdp_diff = base_gdp_growth - quote_gdp_growth
                base_scores.append(min(max(gdp_diff * 5, -1), 1))  # Scale and limit
        
        # Analyze unemployment (lower is better)
        if f'{base_prefix}UNRATE' in economic_data and f'{quote_prefix}UNRATE' in economic_data:
            base_unrate = economic_data[f'{base_prefix}UNRATE']
            quote_unrate = economic_data[f'{quote_prefix}UNRATE']
            
            if not base_unrate.empty and not quote_unrate.empty:
                base_unemp = base_unrate.iloc[-1].values[0] if len(base_unrate) > 0 else None
                quote_unemp = quote_unrate.iloc[-1].values[0] if len(quote_unrate) > 0 else None
                
                if base_unemp is not None and quote_unemp is not None:
                    # Lower unemployment is better
                    unemp_diff = quote_unemp - base_unemp
                    base_scores.append(min(max(unemp_diff * 0.2, -1), 1))  # Scale and limit
        
        # Analyze inflation (moderate is best)
        if f'{base_prefix}CPIAUCSL' in economic_data and f'{quote_prefix}CPIAUCSL' in economic_data:
            base_cpi = economic_data[f'{base_prefix}CPIAUCSL']
            quote_cpi = economic_data[f'{quote_prefix}CPIAUCSL']
            
            if not base_cpi.empty and not quote_cpi.empty:
                # Calculate annual inflation
                base_inflation = base_cpi.pct_change(periods=12).iloc[-1]  # annual inflation
                quote_inflation = quote_cpi.pct_change(periods=12).iloc[-1]  # annual inflation
                
                # Target inflation around 2%
                base_inflation_score = -abs(base_inflation - 0.02) * 10  # Penalize deviation from target
                quote_inflation_score = -abs(quote_inflation - 0.02) * 10
                
                inflation_diff = base_inflation_score - quote_inflation_score
                base_scores.append(min(max(inflation_diff, -1), 1))
        
        # Analyze interest rates (higher can be positive short-term, negative long-term)
        if f'{base_prefix}FEDFUNDS' in economic_data and f'{quote_prefix}FEDFUNDS' in economic_data:
            base_rates = economic_data[f'{base_prefix}FEDFUNDS']
            quote_rates = economic_data[f'{quote_prefix}FEDFUNDS']
            
            if not base_rates.empty and not quote_rates.empty:
                base_rate = base_rates.iloc[-1].values[0] if len(base_rates) > 0 else None
                quote_rate = quote_rates.iloc[-1].values[0] if len(quote_rates) > 0 else None
                
                if base_rate is not None and quote_rate is not None:
                    # Higher interest rates attract capital flows
                    rate_diff = base_rate - quote_rate
                    base_scores.append(min(max(rate_diff * 0.25, -1), 1))
        
        # Calculate final score
        if base_scores:
            final_score = sum(base_scores) / len(base_scores)
        else:
            final_score = 0
        
        logger.debug(f"Economic analysis score: {final_score:.2f}")
        return final_score
    
    def _analyze_news_data(self, news_data: Dict[str, Any], currency_pair: str) -> float:
        """
        Analyze news data to determine sentiment impact on currency pair.
        
        Args:
            news_data: News sentiment data
            currency_pair: Currency pair (e.g., 'EUR/USD')
            
        Returns:
            Score between -1 and 1 indicating sentiment impact
        """
        # Check if we have data
        if not news_data or 'error' in news_data or not news_data.get('articles'):
            logger.warning("Insufficient news data for analysis")
            return 0
        
        # Extract sentiment scores from news articles
        sentiment_scores = []
        for article in news_data.get('articles', []):
            # Check if we have sentiment data
            if 'sentiment' not in article:
                continue
                
            sentiment = article['sentiment']
            
            # Get sentiment score
            if 'score' in sentiment:
                # Apply relevance weighting
                relevance = article.get('relevance', 0.5)
                sentiment_scores.append(sentiment['score'] * relevance)
        
        # Calculate average sentiment
        if sentiment_scores:
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
        else:
            avg_sentiment = 0
        
        logger.debug(f"News sentiment score: {avg_sentiment:.2f}")
        return avg_sentiment
    
    def _determine_signal_type(self, score: float) -> str:
        """
        Determine signal type based on score.
        
        Args:
            score: Signal score between -1 and 1
            
        Returns:
            Signal type ('buy', 'sell', or 'neutral')
        """
        if score >= self.thresholds['buy']:
            return 'buy'
        elif score <= -self.thresholds['sell']:
            return 'sell'
        else:
            if score > self.thresholds['neutral']:
                return 'weak_buy'
            elif score < -self.thresholds['neutral']:
                return 'weak_sell'
            else:
                return 'neutral'
    
    def _adjust_confidence(self, base_confidence: float, financial_data: Dict[str, Any], 
                          economic_data: Dict[str, Any], news_data: Dict[str, Any]) -> float:
        """
        Adjust confidence based on data quality and completeness.
        
        Args:
            base_confidence: Base confidence value
            financial_data: Financial metrics data
            economic_data: Economic indicators data
            news_data: News sentiment data
            
        Returns:
            Adjusted confidence value
        """
        # Start with base confidence
        confidence = base_confidence
        
        # Check for missing data
        data_quality = 1.0
        
        # Financial data quality
        if not financial_data or 'error' in financial_data:
            data_quality *= 0.7
        
        # Economic data quality
        if not economic_data or '_metadata' not in economic_data or 'error' in economic_data.get('_metadata', {}):
            data_quality *= 0.7
        
        # News data quality
        if not news_data or 'error' in news_data or not news_data.get('articles'):
            data_quality *= 0.8
        elif len(news_data.get('articles', [])) < 10:
            # Few articles means less reliable sentiment
            data_quality *= 0.9
        
        # Adjust confidence
        confidence *= data_quality
        
        return confidence 