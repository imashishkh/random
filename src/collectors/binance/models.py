"""
Binance data models.

This module contains Pydantic models for Binance API responses.
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, validator


class OHLCV(BaseModel):
    """Open-High-Low-Close-Volume data model."""
    
    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    quote_volume: float
    trades: int
    taker_buy_volume: float
    taker_buy_quote_volume: float
    
    @validator('open_time', 'close_time', pre=True)
    def convert_timestamp(cls, v):
        """Convert timestamp to datetime."""
        if isinstance(v, int):
            return datetime.fromtimestamp(v / 1000)  # Convert ms to seconds
        return v


class OrderBookEntry(BaseModel):
    """Order book entry model."""
    
    price: float
    quantity: float
    
    @validator('price', 'quantity', pre=True)
    def convert_str_to_float(cls, v):
        """Convert string to float."""
        if isinstance(v, str):
            return float(v)
        return v


class OrderBook(BaseModel):
    """Order book model."""
    
    symbol: str
    last_update_id: int
    event_time: datetime = None
    bids: List[OrderBookEntry]
    asks: List[OrderBookEntry]
    
    @validator('event_time', pre=True)
    def convert_timestamp(cls, v):
        """Convert timestamp to datetime."""
        if isinstance(v, int):
            return datetime.fromtimestamp(v / 1000)  # Convert ms to seconds
        return v


class Trade(BaseModel):
    """Trade model."""
    
    symbol: str
    id: int
    price: float
    quantity: float
    quote_quantity: float = None
    time: datetime
    is_buyer_maker: bool
    is_best_match: bool = None
    
    @validator('price', 'quantity', 'quote_quantity', pre=True)
    def convert_str_to_float(cls, v):
        """Convert string to float."""
        if isinstance(v, str):
            return float(v)
        return v
    
    @validator('time', pre=True)
    def convert_timestamp(cls, v):
        """Convert timestamp to datetime."""
        if isinstance(v, int):
            return datetime.fromtimestamp(v / 1000)  # Convert ms to seconds
        return v
    
    @validator('is_buyer_maker', 'is_best_match', pre=True)
    def convert_str_to_bool(cls, v):
        """Convert string to bool."""
        if isinstance(v, str):
            return v.lower() == 'true'
        return v


class Ticker(BaseModel):
    """24hr price ticker model."""
    
    symbol: str
    price_change: float
    price_change_percent: float
    weighted_avg_price: float
    prev_close_price: float
    last_price: float
    last_qty: float
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    open_price: float
    high_price: float
    low_price: float
    volume: float
    quote_volume: float
    open_time: datetime
    close_time: datetime
    first_id: int
    last_id: int
    count: int
    
    @validator('price_change', 'price_change_percent', 'weighted_avg_price', 
              'prev_close_price', 'last_price', 'last_qty', 'bid_price', 
              'bid_qty', 'ask_price', 'ask_qty', 'open_price', 'high_price', 
              'low_price', 'volume', 'quote_volume', pre=True)
    def convert_str_to_float(cls, v):
        """Convert string to float."""
        if isinstance(v, str):
            return float(v)
        return v
    
    @validator('open_time', 'close_time', pre=True)
    def convert_timestamp(cls, v):
        """Convert timestamp to datetime."""
        if isinstance(v, int):
            return datetime.fromtimestamp(v / 1000)  # Convert ms to seconds
        return v


class BookTicker(BaseModel):
    """Book ticker model."""
    
    symbol: str
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    
    @validator('bid_price', 'bid_qty', 'ask_price', 'ask_qty', pre=True)
    def convert_str_to_float(cls, v):
        """Convert string to float."""
        if isinstance(v, str):
            return float(v)
        return v


def normalize_kline(raw_kline: List, symbol: str, interval: str) -> OHLCV:
    """
    Normalize raw kline data from Binance API.
    
    Args:
        raw_kline: Raw kline data from Binance API.
        symbol: Trading pair symbol.
        interval: Timeframe interval.
        
    Returns:
        Normalized OHLCV data.
    """
    return OHLCV(
        symbol=symbol,
        interval=interval,
        open_time=raw_kline[0],
        open_price=float(raw_kline[1]),
        high_price=float(raw_kline[2]),
        low_price=float(raw_kline[3]),
        close_price=float(raw_kline[4]),
        volume=float(raw_kline[5]),
        close_time=raw_kline[6],
        quote_volume=float(raw_kline[7]),
        trades=raw_kline[8],
        taker_buy_volume=float(raw_kline[9]),
        taker_buy_quote_volume=float(raw_kline[10])
    )


def normalize_order_book(raw_book: Dict, symbol: str) -> OrderBook:
    """
    Normalize raw order book data from Binance API.
    
    Args:
        raw_book: Raw order book data from Binance API.
        symbol: Trading pair symbol.
        
    Returns:
        Normalized OrderBook data.
    """
    bids = [OrderBookEntry(price=bid[0], quantity=bid[1]) for bid in raw_book['bids']]
    asks = [OrderBookEntry(price=ask[0], quantity=ask[1]) for ask in raw_book['asks']]
    
    event_time = raw_book.get('E')
    
    return OrderBook(
        symbol=symbol,
        last_update_id=raw_book['lastUpdateId'],
        event_time=event_time,
        bids=bids,
        asks=asks
    )


def normalize_trade(raw_trade: Dict) -> Trade:
    """
    Normalize raw trade data from Binance API.
    
    Args:
        raw_trade: Raw trade data from Binance API.
        
    Returns:
        Normalized Trade data.
    """
    # Check if it's a normal trade or websocket trade format
    if 's' in raw_trade:  # WebSocket format
        return Trade(
            symbol=raw_trade['s'],
            id=raw_trade['t'],
            price=raw_trade['p'],
            quantity=raw_trade['q'],
            time=raw_trade['T'],
            is_buyer_maker=raw_trade['m'],
            is_best_match=raw_trade.get('M')
        )
    else:  # REST API format
        quote_qty = raw_trade.get('quoteQty', None)
        if quote_qty is None:
            quote_qty = float(raw_trade['price']) * float(raw_trade['qty'])
            
        return Trade(
            symbol=raw_trade['symbol'],
            id=raw_trade['id'],
            price=raw_trade['price'],
            quantity=raw_trade['qty'],
            quote_quantity=quote_qty,
            time=raw_trade['time'],
            is_buyer_maker=raw_trade['isBuyerMaker'],
            is_best_match=raw_trade.get('isBestMatch')
        )


def normalize_ticker(raw_ticker: Dict) -> Ticker:
    """
    Normalize raw ticker data from Binance API.
    
    Args:
        raw_ticker: Raw ticker data from Binance API.
        
    Returns:
        Normalized Ticker data.
    """
    # Check if it's a WebSocket format
    if 's' in raw_ticker:  # WebSocket format
        return Ticker(
            symbol=raw_ticker['s'],
            price_change=raw_ticker['p'],
            price_change_percent=raw_ticker['P'],
            weighted_avg_price=raw_ticker['w'],
            prev_close_price=raw_ticker['x'],
            last_price=raw_ticker['c'],
            last_qty=raw_ticker['Q'],
            bid_price=raw_ticker['b'],
            bid_qty=raw_ticker['B'],
            ask_price=raw_ticker['a'],
            ask_qty=raw_ticker['A'],
            open_price=raw_ticker['o'],
            high_price=raw_ticker['h'],
            low_price=raw_ticker['l'],
            volume=raw_ticker['v'],
            quote_volume=raw_ticker['q'],
            open_time=raw_ticker['O'],
            close_time=raw_ticker['C'],
            first_id=raw_ticker['F'],
            last_id=raw_ticker['L'],
            count=raw_ticker['n']
        )
    else:  # REST API format
        return Ticker(
            symbol=raw_ticker['symbol'],
            price_change=raw_ticker['priceChange'],
            price_change_percent=raw_ticker['priceChangePercent'],
            weighted_avg_price=raw_ticker['weightedAvgPrice'],
            prev_close_price=raw_ticker['prevClosePrice'],
            last_price=raw_ticker['lastPrice'],
            last_qty=raw_ticker['lastQty'],
            bid_price=raw_ticker['bidPrice'],
            bid_qty=raw_ticker['bidQty'],
            ask_price=raw_ticker['askPrice'],
            ask_qty=raw_ticker['askQty'],
            open_price=raw_ticker['openPrice'],
            high_price=raw_ticker['highPrice'],
            low_price=raw_ticker['lowPrice'],
            volume=raw_ticker['volume'],
            quote_volume=raw_ticker['quoteVolume'],
            open_time=raw_ticker['openTime'],
            close_time=raw_ticker['closeTime'],
            first_id=raw_ticker['firstId'],
            last_id=raw_ticker['lastId'],
            count=raw_ticker['count']
        )


def normalize_book_ticker(raw_book_ticker: Dict) -> BookTicker:
    """
    Normalize raw book ticker data from Binance API.
    
    Args:
        raw_book_ticker: Raw book ticker data from Binance API.
        
    Returns:
        Normalized BookTicker data.
    """
    # Check if it's a WebSocket format
    if 's' in raw_book_ticker:  # WebSocket format
        return BookTicker(
            symbol=raw_book_ticker['s'],
            bid_price=raw_book_ticker['b'],
            bid_qty=raw_book_ticker['B'],
            ask_price=raw_book_ticker['a'],
            ask_qty=raw_book_ticker['A']
        )
    else:  # REST API format
        return BookTicker(
            symbol=raw_book_ticker['symbol'],
            bid_price=raw_book_ticker['bidPrice'],
            bid_qty=raw_book_ticker['bidQty'],
            ask_price=raw_book_ticker['askPrice'],
            ask_qty=raw_book_ticker['askQty']
        ) 