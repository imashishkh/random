"""
Data Preprocessing Module

This module contains classes for preprocessing market data,
including technical indicators, data cleaning, and normalization.
"""

import abc
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler, StandardScaler

# Configure logger
logger = logging.getLogger(__name__)


class DataPreprocessor(abc.ABC):
    """
    Abstract base class for data preprocessors.
    
    Defines the common interface for all preprocessor types.
    """
    
    @abc.abstractmethod
    def process(self, data: Any) -> Any:
        """
        Process the input data.
        
        Args:
            data: Input data to preprocess
            
        Returns:
            Preprocessed data
        """
        pass


class TechnicalPreprocessor(DataPreprocessor):
    """
    Preprocessor for technical market data.
    
    Handles cleaning, normalization, and feature engineering for OHLCV data.
    """
    
    def __init__(
        self,
        indicators: Optional[List[str]] = None,
        fill_method: str = 'ffill',
        normalize: bool = True,
        normalization_method: str = 'minmax',
        scaling_window: Optional[int] = None,
        outlier_std_threshold: float = 3.0
    ):
        """
        Initialize the technical preprocessor.
        
        Args:
            indicators: List of technical indicators to calculate
            fill_method: Method for handling missing values ('ffill', 'bfill', 'interpolate')
            normalize: Whether to normalize data
            normalization_method: Method for normalization ('minmax', 'standard', 'log')
            scaling_window: Window size for rolling normalization (None for global)
            outlier_std_threshold: Standard deviation threshold for outlier detection
        """
        self.indicators = indicators or []
        self.fill_method = fill_method
        self.normalize = normalize
        self.normalization_method = normalization_method
        self.scaling_window = scaling_window
        self.outlier_std_threshold = outlier_std_threshold
        self.scalers = {}
    
    def process(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Process OHLCV data by cleaning, calculating indicators, and normalizing.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            Processed DataFrame with additional features
        """
        if data.empty:
            return data
        
        # Work with a copy to avoid modifying the original
        df = data.copy()
        
        # Clean the data
        df = self._clean_data(df)
        
        # Calculate technical indicators
        df = self._calculate_indicators(df)
        
        # Normalize data if requested
        if self.normalize:
            df = self._normalize_data(df)
        
        return df
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean the data by handling missing values and outliers.
        
        Args:
            df: Input DataFrame
            
        Returns:
            Cleaned DataFrame
        """
        # Handle duplicate indices
        df = df[~df.index.duplicated(keep='first')]
        
        # Sort by index (timestamp)
        df = df.sort_index()
        
        # Handle missing values based on specified method
        if self.fill_method == 'ffill':
            df = df.fillna(method='ffill')
        elif self.fill_method == 'bfill':
            df = df.fillna(method='bfill')
        elif self.fill_method == 'interpolate':
            df = df.interpolate(method='time')
        else:
            # Default to forward fill
            df = df.fillna(method='ffill')
        
        # Handle any remaining NaNs (e.g., at the edges)
        df = df.fillna(method='bfill').fillna(method='ffill')
        
        # Detect and handle outliers
        if self.outlier_std_threshold > 0:
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    mean = df[col].mean()
                    std = df[col].std()
                    
                    # Identify outliers
                    outliers = (df[col] - mean).abs() > (self.outlier_std_threshold * std)
                    
                    if outliers.any():
                        logger.warning(f"Found {outliers.sum()} outliers in {col}")
                        
                        # For volume, replace outliers with the mean
                        if col == 'volume':
                            df.loc[outliers, col] = mean
                        # For price columns, use the previous value
                        else:
                            df.loc[outliers, col] = df[col].shift(1).loc[outliers]
        
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators based on the configured list.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with additional indicator columns
        """
        try:
            # Use pandas_ta or TA-Lib if available
            import pandas_ta as ta
        except ImportError:
            logger.warning("pandas_ta not found, using basic indicator calculations")
            ta = None
        
        # Standard indicators regardless of configuration
        if 'open' in df.columns and 'close' in df.columns:
            # Calculate returns
            df['returns'] = df['close'].pct_change()
            df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        
        if 'high' in df.columns and 'low' in df.columns:
            # Calculate range
            df['range'] = df['high'] - df['low']
        
        # Process requested indicators
        if 'sma' in self.indicators or 'all' in self.indicators:
            for period in [5, 10, 20, 50, 200]:
                if ta:
                    df[f'sma_{period}'] = ta.sma(df['close'], length=period)
                else:
                    df[f'sma_{period}'] = df['close'].rolling(window=period).mean()
        
        if 'ema' in self.indicators or 'all' in self.indicators:
            for period in [5, 10, 20, 50, 200]:
                if ta:
                    df[f'ema_{period}'] = ta.ema(df['close'], length=period)
                else:
                    df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        
        if 'rsi' in self.indicators or 'all' in self.indicators:
            for period in [7, 14, 21]:
                if ta:
                    df[f'rsi_{period}'] = ta.rsi(df['close'], length=period)
                else:
                    # Basic RSI calculation
                    delta = df['close'].diff()
                    gain = delta.where(delta > 0, 0)
                    loss = -delta.where(delta < 0, 0)
                    avg_gain = gain.rolling(window=period).mean()
                    avg_loss = loss.rolling(window=period).mean()
                    rs = avg_gain / avg_loss
                    df[f'rsi_{period}'] = 100 - (100 / (1 + rs))
        
        if 'macd' in self.indicators or 'all' in self.indicators:
            if ta:
                macd = ta.macd(df['close'])
                df = pd.concat([df, macd], axis=1)
            else:
                # Basic MACD calculation
                ema12 = df['close'].ewm(span=12, adjust=False).mean()
                ema26 = df['close'].ewm(span=26, adjust=False).mean()
                df['macd_line'] = ema12 - ema26
                df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
                df['macd_histogram'] = df['macd_line'] - df['macd_signal']
        
        if 'bbands' in self.indicators or 'all' in self.indicators:
            if ta:
                bbands = ta.bbands(df['close'])
                df = pd.concat([df, bbands], axis=1)
            else:
                # Basic Bollinger Bands calculation
                period = 20
                sma = df['close'].rolling(window=period).mean()
                std = df['close'].rolling(window=period).std()
                df['bb_upper'] = sma + (std * 2)
                df['bb_middle'] = sma
                df['bb_lower'] = sma - (std * 2)
                df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        if 'atr' in self.indicators or 'all' in self.indicators:
            if ta:
                atr = ta.atr(df['high'], df['low'], df['close'])
                df = pd.concat([df, atr], axis=1)
            else:
                # Basic ATR calculation
                period = 14
                high_low = df['high'] - df['low']
                high_close = (df['high'] - df['close'].shift()).abs()
                low_close = (df['low'] - df['close'].shift()).abs()
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                df['atr'] = tr.rolling(window=period).mean()
        
        # Remove NaN values that might have been introduced
        df = df.fillna(method='bfill').fillna(method='ffill')
        
        return df
    
    def _normalize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize data using the specified method.
        
        Args:
            df: DataFrame to normalize
            
        Returns:
            Normalized DataFrame
        """
        # Create a copy to avoid unexpected changes
        normalized_df = df.copy()
        
        # Columns to normalize
        price_cols = [col for col in df.columns if col in ['open', 'high', 'low', 'close'] 
                     or col.startswith('sma_') or col.startswith('ema_')]
        
        volume_cols = [col for col in df.columns if col in ['volume']]
        
        other_cols = [col for col in df.columns if col not in price_cols + volume_cols 
                     and col not in ['returns', 'log_returns'] 
                     and df[col].dtype in [np.float64, np.int64]]
        
        # Handle global normalization
        if self.scaling_window is None:
            # Apply normalization based on selected method
            if self.normalization_method == 'minmax':
                for cols in [price_cols, volume_cols, other_cols]:
                    if cols:
                        scaler = MinMaxScaler()
                        normalized_df[cols] = scaler.fit_transform(df[cols])
            
            elif self.normalization_method == 'standard':
                for cols in [price_cols, volume_cols, other_cols]:
                    if cols:
                        scaler = StandardScaler()
                        normalized_df[cols] = scaler.fit_transform(df[cols])
            
            elif self.normalization_method == 'log':
                # For log normalization, only apply to positive values
                for col in price_cols + volume_cols + other_cols:
                    if (df[col] > 0).all():
                        normalized_df[col] = np.log(df[col])
        
        # Handle rolling window normalization
        else:
            for i in range(self.scaling_window, len(df) + 1):
                window = df.iloc[i - self.scaling_window:i]
                
                # Apply normalization on each window
                if self.normalization_method == 'minmax':
                    for cols in [price_cols, volume_cols, other_cols]:
                        if cols:
                            scaler = MinMaxScaler()
                            scaler.fit(window[cols])
                            normalized_df.iloc[i-1][cols] = scaler.transform(df.iloc[i-1:i][cols])[0]
                
                elif self.normalization_method == 'standard':
                    for cols in [price_cols, volume_cols, other_cols]:
                        if cols:
                            scaler = StandardScaler()
                            scaler.fit(window[cols])
                            normalized_df.iloc[i-1][cols] = scaler.transform(df.iloc[i-1:i][cols])[0]
        
        return normalized_df


class FundamentalPreprocessor(DataPreprocessor):
    """
    Preprocessor for fundamental data.
    
    Handles cleaning, normalization, and feature engineering for fundamental data.
    """
    
    def __init__(
        self,
        fill_method: str = 'ffill',
        normalize: bool = True,
        calculate_ratios: bool = True
    ):
        """
        Initialize the fundamental preprocessor.
        
        Args:
            fill_method: Method for handling missing values ('ffill', 'bfill', 'interpolate')
            normalize: Whether to normalize data
            calculate_ratios: Whether to calculate financial ratios
        """
        self.fill_method = fill_method
        self.normalize = normalize
        self.calculate_ratios = calculate_ratios
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process fundamental data.
        
        Args:
            data: Dictionary with fundamental data
            
        Returns:
            Processed fundamental data
        """
        # Process different types of fundamental data
        if 'financials' in data:
            return self._process_financials(data)
        elif 'info' in data:
            return self._process_company_info(data)
        else:
            # Just clean basic dictionary data
            return self._clean_dict_data(data)
    
    def _process_financials(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process financial statements data.
        
        Args:
            data: Dictionary with financial data
            
        Returns:
            Processed financial data
        """
        result = data.copy()
        
        # Convert DataFrames to more processable format
        for key in ['financials', 'balance_sheet', 'cashflow']:
            if key in result and not isinstance(result[key], dict):
                try:
                    # Convert to dict format
                    result[key] = result[key].to_dict()
                except:
                    logger.warning(f"Failed to convert {key} to dictionary")
        
        # Calculate financial ratios if requested
        if self.calculate_ratios and 'financials' in result and 'balance_sheet' in result:
            result['ratios'] = self._calculate_financial_ratios(result)
        
        return result
    
    def _process_company_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process company information data.
        
        Args:
            data: Dictionary with company info
            
        Returns:
            Processed company info
        """
        return self._clean_dict_data(data)
    
    def _clean_dict_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean dictionary data by handling missing values.
        
        Args:
            data: Dictionary with data
            
        Returns:
            Cleaned dictionary
        """
        result = {}
        
        for key, value in data.items():
            # Skip None values
            if value is None:
                continue
            
            # Handle nested dictionaries
            if isinstance(value, dict):
                result[key] = self._clean_dict_data(value)
            # Handle lists
            elif isinstance(value, list):
                # Skip empty lists
                if not value:
                    continue
                # Process list items if they're dictionaries
                if all(isinstance(item, dict) for item in value):
                    result[key] = [self._clean_dict_data(item) for item in value]
                else:
                    result[key] = value
            # Handle other values
            else:
                result[key] = value
        
        return result
    
    def _calculate_financial_ratios(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate financial ratios from financial statements.
        
        Args:
            data: Dictionary with financial statements
            
        Returns:
            Dictionary with calculated ratios
        """
        ratios = {}
        
        # Extract relevant data
        try:
            financials = data.get('financials', {})
            balance_sheet = data.get('balance_sheet', {})
            
            # Get the most recent data
            if financials and balance_sheet:
                # Calculate profitability ratios
                total_revenue = financials.get('Total Revenue', {})
                net_income = financials.get('Net Income', {})
                total_assets = balance_sheet.get('Total Assets', {})
                shareholders_equity = balance_sheet.get('Total Stockholder Equity', {})
                
                # Calculate ROA (Return on Assets)
                if net_income and total_assets:
                    dates = set(net_income.keys()) & set(total_assets.keys())
                    ratios['roa'] = {
                        date: net_income[date] / total_assets[date] 
                        for date in dates 
                        if total_assets[date] != 0
                    }
                
                # Calculate ROE (Return on Equity)
                if net_income and shareholders_equity:
                    dates = set(net_income.keys()) & set(shareholders_equity.keys())
                    ratios['roe'] = {
                        date: net_income[date] / shareholders_equity[date] 
                        for date in dates 
                        if shareholders_equity[date] != 0
                    }
                
                # Calculate Profit Margin
                if net_income and total_revenue:
                    dates = set(net_income.keys()) & set(total_revenue.keys())
                    ratios['profit_margin'] = {
                        date: net_income[date] / total_revenue[date] 
                        for date in dates 
                        if total_revenue[date] != 0
                    }
        
        except Exception as e:
            logger.error(f"Error calculating financial ratios: {str(e)}")
        
        return ratios


class NewsPreprocessor(DataPreprocessor):
    """
    Preprocessor for news data.
    
    Handles cleaning and sentiment analysis for news articles.
    """
    
    def __init__(
        self,
        perform_sentiment: bool = True,
        summarize: bool = False,
        extract_entities: bool = False
    ):
        """
        Initialize the news preprocessor.
        
        Args:
            perform_sentiment: Whether to perform sentiment analysis
            summarize: Whether to generate article summaries
            extract_entities: Whether to extract named entities
        """
        self.perform_sentiment = perform_sentiment
        self.summarize = summarize
        self.extract_entities = extract_entities
        
        # Initialize NLP components if needed
        if perform_sentiment or summarize or extract_entities:
            try:
                import nltk
                # Download necessary NLTK packages
                try:
                    nltk.data.find('vader_lexicon')
                except LookupError:
                    nltk.download('vader_lexicon')
                
                try:
                    nltk.data.find('punkt')
                except LookupError:
                    nltk.download('punkt')
                
                if extract_entities:
                    try:
                        nltk.data.find('maxent_ne_chunker')
                    except LookupError:
                        nltk.download('maxent_ne_chunker')
                    
                    try:
                        nltk.data.find('words')
                    except LookupError:
                        nltk.download('words')
            except ImportError:
                logger.warning("NLTK not available, some news preprocessing features will be disabled")
    
    def process(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process news data.
        
        Args:
            data: List of news articles
            
        Returns:
            Processed news data
        """
        if not data:
            return []
        
        processed_news = []
        
        for article in data:
            processed_article = article.copy()
            
            # Clean the article content
            content = article.get('content', article.get('description', ''))
            processed_article['clean_content'] = self._clean_text(content)
            
            # Perform sentiment analysis if requested
            if self.perform_sentiment and processed_article['clean_content']:
                processed_article['sentiment'] = self._analyze_sentiment(processed_article['clean_content'])
            
            # Generate summary if requested
            if self.summarize and processed_article['clean_content']:
                processed_article['summary'] = self._generate_summary(processed_article['clean_content'])
            
            # Extract entities if requested
            if self.extract_entities and processed_article['clean_content']:
                processed_article['entities'] = self._extract_named_entities(processed_article['clean_content'])
            
            processed_news.append(processed_article)
        
        return processed_news
    
    def _clean_text(self, text: str) -> str:
        """
        Clean text by removing special characters and unnecessary whitespace.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Remove HTML tags
        import re
        text = re.sub('<.*?>', ' ', text)
        
        # Replace newlines and tabs with spaces
        text = text.replace('\n', ' ').replace('\t', ' ')
        
        # Remove multiple spaces
        text = re.sub(' +', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def _analyze_sentiment(self, text: str) -> Dict[str, float]:
        """
        Perform sentiment analysis on text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with sentiment scores
        """
        try:
            from nltk.sentiment.vader import SentimentIntensityAnalyzer
            
            sia = SentimentIntensityAnalyzer()
            sentiment = sia.polarity_scores(text)
            
            return sentiment
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {str(e)}")
            return {
                'neg': 0.0,
                'neu': 0.0,
                'pos': 0.0,
                'compound': 0.0
            }
    
    def _generate_summary(self, text: str, sentences: int = 3) -> str:
        """
        Generate a summary of the text.
        
        Args:
            text: Text to summarize
            sentences: Number of sentences in the summary
            
        Returns:
            Summary text
        """
        try:
            from nltk.tokenize import sent_tokenize
            from nltk.corpus import stopwords
            from nltk.tokenize import word_tokenize
            
            # Tokenize text into sentences
            sent_tokens = sent_tokenize(text)
            
            # If there are fewer sentences than requested, return the original text
            if len(sent_tokens) <= sentences:
                return text
            
            # Calculate word frequency
            word_freq = {}
            stop_words = set(stopwords.words('english'))
            
            for sentence in sent_tokens:
                for word in word_tokenize(sentence.lower()):
                    if word not in stop_words and word.isalnum():
                        if word not in word_freq:
                            word_freq[word] = 1
                        else:
                            word_freq[word] += 1
            
            # Calculate sentence scores based on word frequency
            sent_scores = {}
            for idx, sentence in enumerate(sent_tokens):
                for word in word_tokenize(sentence.lower()):
                    if word in word_freq:
                        if idx not in sent_scores:
                            sent_scores[idx] = word_freq[word]
                        else:
                            sent_scores[idx] += word_freq[word]
            
            # Get top sentences
            top_sents = sorted(sent_scores.items(), key=lambda x: x[1], reverse=True)[:sentences]
            top_sents = sorted(top_sents, key=lambda x: x[0])
            
            # Assemble summary
            summary = ' '.join([sent_tokens[idx] for idx, _ in top_sents])
            
            return summary
        
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            
            # If we can't generate a proper summary, return the first few sentences
            try:
                from nltk.tokenize import sent_tokenize
                sent_tokens = sent_tokenize(text)
                return ' '.join(sent_tokens[:sentences])
            except:
                # Last resort: simple string-based approach
                ending_marks = ['. ', '! ', '? ']
                for mark in ending_marks:
                    text = text.replace(mark, mark + '|||')
                sent_tokens = text.split('|||')
                return ' '.join(sent_tokens[:sentences])
    
    def _extract_named_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Extract named entities from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with entity types and values
        """
        try:
            import nltk
            from nltk import ne_chunk, pos_tag, word_tokenize
            
            # Tokenize and tag text
            tokens = word_tokenize(text)
            tagged = pos_tag(tokens)
            
            # Extract named entities
            named_entities = ne_chunk(tagged)
            
            # Process named entities into a dictionary
            entities = {
                'PERSON': [],
                'ORGANIZATION': [],
                'GPE': [],  # Geo-Political Entity
                'LOCATION': [],
                'DATE': [],
                'MONEY': [],
                'PERCENT': [],
                'OTHER': []
            }
            
            for chunk in named_entities:
                if hasattr(chunk, 'label'):
                    entity_type = chunk.label()
                    entity_text = ' '.join(word for word, tag in chunk.leaves())
                    
                    if entity_type in entities:
                        if entity_text not in entities[entity_type]:
                            entities[entity_type].append(entity_text)
                    else:
                        if entity_text not in entities['OTHER']:
                            entities['OTHER'].append(entity_text)
            
            # Remove empty categories
            entities = {k: v for k, v in entities.items() if v}
            
            return entities
        
        except Exception as e:
            logger.error(f"Error extracting named entities: {str(e)}")
            return {}


class EconomicIndicatorPreprocessor(DataPreprocessor):
    """
    Preprocessor for economic indicator data.
    
    Handles cleaning, normalization, and seasonality analysis.
    """
    
    def __init__(
        self,
        fill_method: str = 'ffill',
        normalize: bool = True,
        handle_seasonality: bool = True
    ):
        """
        Initialize the economic indicator preprocessor.
        
        Args:
            fill_method: Method for handling missing values ('ffill', 'bfill', 'interpolate')
            normalize: Whether to normalize data
            handle_seasonality: Whether to handle seasonality in the data
        """
        self.fill_method = fill_method
        self.normalize = normalize
        self.handle_seasonality = handle_seasonality
    
    def process(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Process economic indicator data.
        
        Args:
            data: DataFrame with economic indicator data
            
        Returns:
            Processed DataFrame
        """
        if data.empty:
            return data
        
        # Work with a copy to avoid modifying the original
        df = data.copy()
        
        # Clean the data
        df = self._clean_data(df)
        
        # Handle seasonality if requested
        if self.handle_seasonality:
            df = self._handle_seasonality(df)
        
        # Normalize if requested
        if self.normalize:
            df = self._normalize_data(df)
        
        return df
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean economic indicator data.
        
        Args:
            df: DataFrame to clean
            
        Returns:
            Cleaned DataFrame
        """
        # Handle duplicate indices
        df = df[~df.index.duplicated(keep='first')]
        
        # Sort by index (timestamp)
        df = df.sort_index()
        
        # Handle missing values based on specified method
        if self.fill_method == 'ffill':
            df = df.fillna(method='ffill')
        elif self.fill_method == 'bfill':
            df = df.fillna(method='bfill')
        elif self.fill_method == 'interpolate':
            df = df.interpolate(method='time')
        else:
            # Default to forward fill
            df = df.fillna(method='ffill')
        
        # Handle any remaining NaNs (e.g., at the edges)
        df = df.fillna(method='bfill').fillna(method='ffill')
        
        return df
    
    def _handle_seasonality(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Handle seasonality in economic indicator data.
        
        Args:
            df: DataFrame to process
            
        Returns:
            DataFrame with seasonality features
        """
        # Add basic time features
        df['month'] = df.index.month
        df['quarter'] = df.index.quarter
        df['year'] = df.index.year
        
        # For numerical columns, calculate seasonal components
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        numeric_cols = [col for col in numeric_cols if col not in ['month', 'quarter', 'year']]
        
        # Add year-over-year change for each numeric column
        for col in numeric_cols:
            # Calculate year-over-year percent change
            df[f'{col}_yoy'] = df.groupby('month')[col].pct_change(12)
            
            # Calculate quarterly change
            df[f'{col}_qoq'] = df.groupby('quarter')[col].pct_change()
        
        return df
    
    def _normalize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize economic indicator data.
        
        Args:
            df: DataFrame to normalize
            
        Returns:
            Normalized DataFrame
        """
        # Identify numeric columns except time features
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        numeric_cols = [col for col in numeric_cols if col not in ['month', 'quarter', 'year']]
        
        # Apply min-max scaling to numeric columns
        if numeric_cols:
            scaler = MinMaxScaler()
            df[numeric_cols] = scaler.fit_transform(df[numeric_cols])
        
        return df


class PreprocessorFactory:
    """
    Factory for creating data preprocessors.
    
    Provides a centralized way to create preprocessor instances.
    """
    
    def __init__(self):
        """Initialize the factory."""
        self.preprocessor_classes = {
            'technical': TechnicalPreprocessor,
            'fundamental': FundamentalPreprocessor,
            'news': NewsPreprocessor,
            'economic': EconomicIndicatorPreprocessor
        }
    
    def get_preprocessor(
        self, 
        preprocessor_type: str,
        **kwargs
    ) -> DataPreprocessor:
        """
        Get a preprocessor instance.
        
        Args:
            preprocessor_type: Type of preprocessor
            **kwargs: Additional arguments for the preprocessor
            
        Returns:
            Preprocessor instance
            
        Raises:
            ValueError: If the preprocessor type is not supported
        """
        if preprocessor_type not in self.preprocessor_classes:
            raise ValueError(f"Unsupported preprocessor type: {preprocessor_type}")
        
        # Create new instance
        preprocessor_class = self.preprocessor_classes[preprocessor_type]
        preprocessor = preprocessor_class(**kwargs)
        
        return preprocessor 