import json
import csv
import os
from typing import List, Dict, Optional, Any, Callable, Union
from datetime import datetime, timedelta
import logging
from abc import ABC, abstractmethod

from .data_models import Trade, TradeDirection

logger = logging.getLogger(__name__)


class DataFetcherBase(ABC):
    """Abstract base class for data fetchers"""
    
    @abstractmethod
    def fetch_trades(self, start_date: Optional[datetime] = None, 
                    end_date: Optional[datetime] = None) -> List[Trade]:
        """Fetch trades from the data source"""
        pass
    
    @abstractmethod
    def update_trades(self) -> List[Trade]:
        """Update trades data from source"""
        pass


class FileDataFetcher(DataFetcherBase):
    """Fetches trade data from files (JSON or CSV)"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.last_modified = None
        self.cache = []
        
    def fetch_trades(self, start_date: Optional[datetime] = None, 
                    end_date: Optional[datetime] = None) -> List[Trade]:
        """Fetch trades from file, with optional date filtering"""
        # Check if we need to reload the file
        if not self.cache or self._file_modified():
            self._load_file()
        
        # Filter by date if provided
        filtered_trades = self.cache
        if start_date:
            filtered_trades = [t for t in filtered_trades if t.close_time >= start_date]
        if end_date:
            filtered_trades = [t for t in filtered_trades if t.close_time <= end_date]
            
        return filtered_trades
    
    def update_trades(self) -> List[Trade]:
        """Check for file updates and reload if necessary"""
        if self._file_modified():
            old_trade_ids = {t.id for t in self.cache}
            self._load_file()
            new_trades = [t for t in self.cache if t.id not in old_trade_ids]
            return new_trades
        return []
    
    def _file_modified(self) -> bool:
        """Check if the file has been modified since last load"""
        if not os.path.exists(self.file_path):
            return False
            
        current_mtime = os.path.getmtime(self.file_path)
        if self.last_modified is None or current_mtime > self.last_modified:
            self.last_modified = current_mtime
            return True
            
        return False
    
    def _load_file(self) -> None:
        """Load trade data from file"""
        if not os.path.exists(self.file_path):
            logger.warning(f"File {self.file_path} does not exist")
            return
        
        try:
            # Determine file type from extension
            ext = os.path.splitext(self.file_path)[1].lower()
            
            if ext == '.json':
                self._load_json_file()
            elif ext == '.csv':
                self._load_csv_file()
            else:
                logger.error(f"Unsupported file type: {ext}")
                self.cache = []
                
        except Exception as e:
            logger.error(f"Error loading file {self.file_path}: {str(e)}")
            self.cache = []
    
    def _load_json_file(self) -> None:
        """Load trades from JSON file"""
        with open(self.file_path, 'r') as f:
            data = json.load(f)
            
        # Handle different possible JSON structures
        trades_data = data
        if isinstance(data, dict):
            # Look for a trades array in the data
            if 'trades' in data:
                trades_data = data['trades']
            elif 'results' in data:
                trades_data = data['results']
                
        if not isinstance(trades_data, list):
            logger.error(f"Invalid JSON structure in {self.file_path}")
            self.cache = []
            return
            
        # Parse trades
        trades = []
        for item in trades_data:
            try:
                trade = self._parse_json_trade(item)
                if trade:
                    trades.append(trade)
            except Exception as e:
                logger.warning(f"Error parsing trade: {str(e)}")
                
        self.cache = trades
    
    def _parse_json_trade(self, data: Dict[str, Any]) -> Optional[Trade]:
        """Parse a single trade from JSON data"""
        # Map JSON fields to Trade fields, with flexible field name matching
        field_mappings = {
            'id': ['id', 'trade_id', 'tradeId', 'order_id', 'orderId'],
            'symbol': ['symbol', 'pair', 'instrument', 'market', 'ticker'],
            'open_time': ['open_time', 'openTime', 'open_date', 'openDate', 'entry_time', 'entryTime'],
            'close_time': ['close_time', 'closeTime', 'close_date', 'closeDate', 'exit_time', 'exitTime'],
            'direction': ['direction', 'side', 'type', 'position_type', 'positionType'],
            'open_price': ['open_price', 'openPrice', 'entry_price', 'entryPrice', 'entry'],
            'close_price': ['close_price', 'closePrice', 'exit_price', 'exitPrice', 'exit'],
            'size': ['size', 'amount', 'quantity', 'volume', 'position_size', 'positionSize'],
            'pnl': ['pnl', 'profit', 'profit_loss', 'profitLoss', 'realized_pnl', 'realizedPnl'],
            'fees': ['fees', 'fee', 'commission', 'commissions'],
            'strategy': ['strategy', 'strat', 'strategy_name', 'strategyName'],
            'tags': ['tags', 'labels']
        }
        
        # Extract values using field mappings
        extracted = {}
        for field, possible_keys in field_mappings.items():
            for key in possible_keys:
                if key in data:
                    extracted[field] = data[key]
                    break
        
        # Check required fields
        required_fields = ['id', 'symbol', 'open_price', 'close_price', 'size', 'pnl']
        for field in required_fields:
            if field not in extracted:
                logger.warning(f"Missing required field: {field}")
                return None
        
        # Parse direction
        direction = TradeDirection.BUY
        if 'direction' in extracted:
            direction_val = str(extracted['direction']).upper()
            if direction_val in ('SELL', 'SHORT', 'S'):
                direction = TradeDirection.SELL
        
        # Parse dates
        open_time = datetime.now()
        if 'open_time' in extracted:
            open_time = self._parse_datetime(extracted['open_time'])
        
        close_time = datetime.now()
        if 'close_time' in extracted:
            close_time = self._parse_datetime(extracted['close_time'])
        
        # Create Trade object
        trade = Trade(
            id=str(extracted['id']),
            symbol=str(extracted['symbol']),
            open_time=open_time,
            close_time=close_time,
            direction=direction,
            open_price=float(extracted['open_price']),
            close_price=float(extracted['close_price']),
            size=float(extracted['size']),
            pnl=float(extracted['pnl']),
            fees=float(extracted.get('fees', 0.0)),
            strategy=str(extracted.get('strategy', 'default')),
            tags=extracted.get('tags', [])
        )
        
        return trade
    
    def _load_csv_file(self) -> None:
        """Load trades from CSV file"""
        trades = []
        
        with open(self.file_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    trade = self._parse_csv_trade(row)
                    if trade:
                        trades.append(trade)
                except Exception as e:
                    logger.warning(f"Error parsing CSV row: {str(e)}")
        
        self.cache = trades
    
    def _parse_csv_trade(self, row: Dict[str, str]) -> Optional[Trade]:
        """Parse a single trade from CSV row"""
        # Similar approach to the JSON parser, but with CSV specifics
        # Clean up field names - remove spaces, lowercase
        cleaned_row = {k.lower().replace(' ', '_'): v for k, v in row.items()}
        
        # Try to map CSV fields to Trade fields
        field_mappings = {
            'id': ['id', 'trade_id', 'order_id'],
            'symbol': ['symbol', 'pair', 'instrument', 'market', 'ticker'],
            'open_time': ['open_time', 'open_date', 'entry_time', 'entry_date'],
            'close_time': ['close_time', 'close_date', 'exit_time', 'exit_date'],
            'direction': ['direction', 'side', 'type', 'position_type'],
            'open_price': ['open_price', 'entry_price', 'entry'],
            'close_price': ['close_price', 'exit_price', 'exit'],
            'size': ['size', 'amount', 'quantity', 'volume', 'position_size'],
            'pnl': ['pnl', 'profit', 'profit_loss', 'realized_pnl'],
            'fees': ['fees', 'fee', 'commission'],
            'strategy': ['strategy', 'strategy_name'],
            'tags': ['tags', 'labels']
        }
        
        # Extract values using field mappings
        extracted = {}
        for field, possible_keys in field_mappings.items():
            for key in possible_keys:
                if key in cleaned_row:
                    extracted[field] = cleaned_row[key]
                    break
        
        # Check required fields
        required_fields = ['id', 'symbol', 'open_price', 'close_price', 'size', 'pnl']
        for field in required_fields:
            if field not in extracted:
                logger.warning(f"Missing required field in CSV: {field}")
                return None
        
        # Parse direction
        direction = TradeDirection.BUY
        if 'direction' in extracted:
            direction_val = str(extracted['direction']).upper()
            if direction_val in ('SELL', 'SHORT', 'S'):
                direction = TradeDirection.SELL
        
        # Parse dates
        open_time = datetime.now()
        if 'open_time' in extracted:
            open_time = self._parse_datetime(extracted['open_time'])
        
        close_time = datetime.now()
        if 'close_time' in extracted:
            close_time = self._parse_datetime(extracted['close_time'])
        
        # Parse tags (comma-separated in CSV)
        tags = []
        if 'tags' in extracted and extracted['tags']:
            tags = [tag.strip() for tag in str(extracted['tags']).split(',')]
        
        # Create Trade object
        trade = Trade(
            id=str(extracted['id']),
            symbol=str(extracted['symbol']),
            open_time=open_time,
            close_time=close_time,
            direction=direction,
            open_price=float(extracted['open_price']),
            close_price=float(extracted['close_price']),
            size=float(extracted['size']),
            pnl=float(extracted['pnl']),
            fees=float(extracted.get('fees', 0.0)),
            strategy=str(extracted.get('strategy', 'default')),
            tags=tags
        )
        
        return trade
    
    def _parse_datetime(self, value: Any) -> datetime:
        """Parse a datetime from various formats"""
        if isinstance(value, datetime):
            return value
            
        if isinstance(value, (int, float)):
            # Assume unix timestamp
            # If it's in milliseconds (length > 10), convert to seconds
            timestamp = value
            if timestamp > 1e10:  # Likely milliseconds
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp)
        
        # Try various string formats
        if isinstance(value, str):
            formats = [
                '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO format with milliseconds
                '%Y-%m-%dT%H:%M:%SZ',      # ISO format
                '%Y-%m-%d %H:%M:%S',       # Common datetime format
                '%Y-%m-%d',                # Date only
                '%m/%d/%Y %H:%M:%S',       # US format with time
                '%m/%d/%Y',                # US date format
                '%d/%m/%Y %H:%M:%S',       # European format with time
                '%d/%m/%Y',                # European date format
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        
        # If all parsing attempts fail, default to now
        logger.warning(f"Could not parse datetime: {value}, using current time")
        return datetime.now()


class APIDataFetcher(DataFetcherBase):
    """Fetches trade data from an API endpoint"""
    
    def __init__(self, api_url: str, auth_token: Optional[str] = None):
        self.api_url = api_url
        self.auth_token = auth_token
        self.cache = []
        self.last_updated = None
        
    def fetch_trades(self, start_date: Optional[datetime] = None, 
                    end_date: Optional[datetime] = None) -> List[Trade]:
        """Fetch trades from API, with optional date filtering"""
        # This is a placeholder implementation
        # In a real implementation, this would make HTTP requests to the API
        logger.warning("APIDataFetcher is not fully implemented")
        
        # Apply date filtering to cached trades
        filtered_trades = self.cache
        if start_date:
            filtered_trades = [t for t in filtered_trades if t.close_time >= start_date]
        if end_date:
            filtered_trades = [t for t in filtered_trades if t.close_time <= end_date]
            
        return filtered_trades
    
    def update_trades(self) -> List[Trade]:
        """Update trades from API"""
        # Placeholder implementation
        logger.warning("APIDataFetcher.update_trades is not fully implemented")
        return []


class MockDataFetcher(DataFetcherBase):
    """Generates mock trade data for testing"""
    
    def __init__(self, num_trades: int = 100, symbols: Optional[List[str]] = None):
        import random
        self.random = random
        self.random.seed(42)  # For reproducibility
        
        self.num_trades = num_trades
        self.symbols = symbols or ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
        self.strategies = ["trend_following", "mean_reversion", "breakout", "scalping"]
        self.cache = self._generate_mock_trades()
        
    def fetch_trades(self, start_date: Optional[datetime] = None, 
                    end_date: Optional[datetime] = None) -> List[Trade]:
        """Return mock trades with optional date filtering"""
        filtered_trades = self.cache
        if start_date:
            filtered_trades = [t for t in filtered_trades if t.close_time >= start_date]
        if end_date:
            filtered_trades = [t for t in filtered_trades if t.close_time <= end_date]
            
        return filtered_trades
    
    def update_trades(self) -> List[Trade]:
        """Generate a few new mock trades"""
        if not self.cache:
            self.cache = self._generate_mock_trades()
            return self.cache
            
        # Generate a few new trades
        num_new = self.random.randint(1, 5)
        new_trades = self._generate_mock_trades(num_new, start_id=len(self.cache))
        
        # Add them to the cache
        self.cache.extend(new_trades)
        
        return new_trades
    
    def _generate_mock_trades(self, num_trades: Optional[int] = None, start_id: int = 0) -> List[Trade]:
        """Generate mock trade data"""
        num = num_trades or self.num_trades
        trades = []
        
        # Start time: 60 days ago
        end_time = datetime.now()
        start_time = end_time - timedelta(days=60)
        time_range = (end_time - start_time).total_seconds()
        
        for i in range(num):
            # Random trade properties
            symbol = self.random.choice(self.symbols)
            direction = self.random.choice([TradeDirection.BUY, TradeDirection.SELL])
            strategy = self.random.choice(self.strategies)
            
            # Random times within the range
            open_seconds = self.random.uniform(0, time_range * 0.9)
            open_time = start_time + timedelta(seconds=open_seconds)
            
            # Trade duration: 1 minute to 2 days
            duration_seconds = self.random.uniform(60, 60 * 60 * 48)
            close_time = open_time + timedelta(seconds=duration_seconds)
            
            # Prices based on symbol
            base_price = self._get_base_price(symbol)
            price_volatility = base_price * 0.002  # 0.2% volatility
            
            open_price = base_price + self.random.uniform(-price_volatility, price_volatility)
            price_change = self.random.uniform(-price_volatility * 2, price_volatility * 2)
            close_price = open_price + price_change
            
            # Size and P&L
            size = self.random.uniform(0.1, 10.0)
            
            if direction == TradeDirection.BUY:
                pnl = (close_price - open_price) * size * self._get_multiplier(symbol)
            else:
                pnl = (open_price - close_price) * size * self._get_multiplier(symbol)
            
            # Add some randomness to P&L to simulate spread, commission, etc.
            pnl *= self.random.uniform(0.95, 1.05)
            
            # Fees: 0.1% to 0.3% of position size
            fee_rate = self.random.uniform(0.001, 0.003)
            fees = base_price * size * fee_rate
            
            # Trade object
            trade = Trade(
                id=str(start_id + i),
                symbol=symbol,
                open_time=open_time,
                close_time=close_time,
                direction=direction,
                open_price=round(open_price, 5),
                close_price=round(close_price, 5),
                size=round(size, 2),
                pnl=round(pnl, 2),
                fees=round(fees, 2),
                strategy=strategy,
                tags=self._generate_random_tags()
            )
            
            trades.append(trade)
        
        # Sort by close_time
        trades.sort(key=lambda t: t.close_time)
        
        return trades
    
    def _get_base_price(self, symbol: str) -> float:
        """Get a realistic base price for a symbol"""
        prices = {
            "EURUSD": 1.08,
            "GBPUSD": 1.25,
            "USDJPY": 150.0,
            "AUDUSD": 0.65,
            "USDCAD": 1.35,
            "NZDUSD": 0.60,
            "USDCHF": 0.90,
            "EURGBP": 0.85,
            "EURJPY": 160.0,
            "GBPJPY": 190.0
        }
        
        return prices.get(symbol, 1.0)
    
    def _get_multiplier(self, symbol: str) -> float:
        """Get a realistic P&L multiplier for a symbol"""
        # This represents the standard lot size value
        # For most forex pairs, 1 pip on 1 standard lot = $10
        # But for pairs like USDJPY, it's different
        multipliers = {
            "USDJPY": 1000,    # Yen pairs have different pip values
            "EURJPY": 1000,
            "GBPJPY": 1000
        }
        
        return multipliers.get(symbol, 100000)
    
    def _generate_random_tags(self) -> List[str]:
        """Generate random tags for a trade"""
        all_tags = [
            "news", "manual", "automated", "high_volatility", 
            "low_volatility", "trend", "reversal", "breakout",
            "support", "resistance", "pivot", "overnight",
            "scalp", "swing", "position"
        ]
        
        num_tags = self.random.randint(0, 3)
        if num_tags == 0:
            return []
            
        return self.random.sample(all_tags, num_tags)


def create_data_fetcher(source_type: str, **kwargs) -> DataFetcherBase:
    """Factory function to create the appropriate data fetcher"""
    if source_type == 'file':
        if 'file_path' not in kwargs:
            raise ValueError("file_path is required for FileDataFetcher")
        return FileDataFetcher(kwargs['file_path'])
    elif source_type == 'api':
        if 'api_url' not in kwargs:
            raise ValueError("api_url is required for APIDataFetcher")
        return APIDataFetcher(kwargs['api_url'], kwargs.get('auth_token'))
    elif source_type == 'mock':
        return MockDataFetcher(
            num_trades=kwargs.get('num_trades', 100),
            symbols=kwargs.get('symbols')
        )
    else:
        raise ValueError(f"Unknown data source type: {source_type}") 