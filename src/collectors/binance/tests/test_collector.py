"""
Tests for Binance collector.

This module contains tests for the Binance data collectors
using mock API responses.
"""

import asyncio
import json
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from .binance.collector import BinanceCollector
from .binance.constants import TIMEFRAMES


# Mock API responses
MOCK_KLINES_RESPONSE = [
    [1625097600000, "35000.0", "36000.0", "34500.0", "35500.0", "100.0", 
     1625101199999, "3500000.0", 5000, "50.0", "1750000.0", "0"],
    [1625101200000, "35500.0", "36500.0", "35000.0", "36000.0", "120.0", 
     1625104799999, "4300000.0", 6000, "60.0", "2100000.0", "0"],
    [1625104800000, "36000.0", "37000.0", "35500.0", "36500.0", "130.0", 
     1625108399999, "4700000.0", 7000, "70.0", "2500000.0", "0"]
]

MOCK_TRADES_RESPONSE = [
    {
        "id": 1,
        "price": "35500.0",
        "qty": "1.0",
        "quoteQty": "35500.0",
        "time": 1625097600000,
        "isBuyerMaker": False,
        "isBestMatch": True
    },
    {
        "id": 2,
        "price": "35600.0",
        "qty": "0.5",
        "quoteQty": "17800.0",
        "time": 1625097610000,
        "isBuyerMaker": True,
        "isBestMatch": True
    }
]

MOCK_TICKER_RESPONSE = {
    "symbol": "BTCUSDT",
    "priceChange": "1000.0",
    "priceChangePercent": "2.5",
    "weightedAvgPrice": "35750.0",
    "prevClosePrice": "34500.0",
    "lastPrice": "35500.0",
    "lastQty": "0.5",
    "bidPrice": "35450.0",
    "bidQty": "1.0",
    "askPrice": "35550.0",
    "askQty": "1.5",
    "openPrice": "34500.0",
    "highPrice": "36000.0",
    "lowPrice": "34500.0",
    "volume": "1000.0",
    "quoteVolume": "35750000.0",
    "openTime": 1625011200000,
    "closeTime": 1625097600000,
    "firstId": 1,
    "lastId": 1000,
    "count": 1000
}

MOCK_ORDERBOOK_RESPONSE = {
    "lastUpdateId": 12345,
    "bids": [
        ["35450.0", "1.0"],
        ["35400.0", "2.0"],
        ["35350.0", "3.0"]
    ],
    "asks": [
        ["35550.0", "1.5"],
        ["35600.0", "2.5"],
        ["35650.0", "3.5"]
    ]
}


@pytest.mark.asyncio
class TestBinanceCollector:
    """Tests for the BinanceCollector class."""
    
    async def setup_method(self):
        """Set up for each test method."""
        # Create a session mock
        self.session_mock = MagicMock()
        self.session_mock.get = AsyncMock()
        self.session_mock.post = AsyncMock()
        self.session_mock.close = AsyncMock()
        
        # Create a response mock
        self.response_mock = AsyncMock()
        self.response_mock.json = AsyncMock()
        self.response_mock.status = 200
        self.response_mock.headers = {}
        
        # Set up context manager for response
        self.session_mock.get.return_value.__aenter__.return_value = self.response_mock
        self.session_mock.post.return_value.__aenter__.return_value = self.response_mock
        
        # Create WebSocket client mock
        self.ws_client_mock = MagicMock()
        self.ws_client_mock.connect = AsyncMock()
        self.ws_client_mock.disconnect = AsyncMock()
        self.ws_client_mock.add_stream = AsyncMock()
        self.ws_client_mock.remove_stream = AsyncMock()
        self.ws_client_mock.add_callback = MagicMock()
        
        # Create collector with mocks
        with patch('aiohttp.ClientSession', return_value=self.session_mock):
            with patch('src.collectors.binance.websocket.BinanceWebSocketClient', return_value=self.ws_client_mock):
                self.collector = BinanceCollector(
                    symbols=["BTCUSDT", "ETHUSDT"],
                    timeframes=["1h", "4h"],
                    api_key="mock_api_key",
                    api_secret="mock_api_secret"
                )
                await self.collector.start()
    
    async def teardown_method(self):
        """Clean up after each test method."""
        await self.collector.stop()
    
    async def test_fetch_klines(self):
        """Test fetching klines (candlestick) data."""
        # Mock the response
        self.response_mock.json.return_value = MOCK_KLINES_RESPONSE
        
        # Fetch klines
        result = await self.collector.collect("kline", "BTCUSDT", timeframe="1h", limit=3)
        
        # Verify the request was made correctly
        self.session_mock.get.assert_called_once()
        args, kwargs = self.session_mock.get.call_args
        assert "klines" in args[0]
        assert kwargs["params"]["symbol"] == "BTCUSDT"
        assert kwargs["params"]["interval"] == "1h"
        assert kwargs["params"]["limit"] == 3
        
        # Verify the result
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert "open" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns
    
    async def test_fetch_trades(self):
        """Test fetching recent trades."""
        # Mock the response
        self.response_mock.json.return_value = MOCK_TRADES_RESPONSE
        
        # Fetch trades
        result = await self.collector.collect("trade", "BTCUSDT", limit=2)
        
        # Verify the request was made correctly
        self.session_mock.get.assert_called_once()
        args, kwargs = self.session_mock.get.call_args
        assert "trades" in args[0]
        assert kwargs["params"]["symbol"] == "BTCUSDT"
        assert kwargs["params"]["limit"] == 2
        
        # Verify the result
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert "price" in result.columns
        assert "qty" in result.columns
    
    async def test_fetch_ticker(self):
        """Test fetching ticker data."""
        # Mock the response
        self.response_mock.json.return_value = MOCK_TICKER_RESPONSE
        
        # Fetch ticker
        result = await self.collector.collect("ticker", "BTCUSDT")
        
        # Verify the request was made correctly
        self.session_mock.get.assert_called_once()
        args, kwargs = self.session_mock.get.call_args
        assert "ticker" in args[0]
        assert kwargs["params"]["symbol"] == "BTCUSDT"
        
        # Verify the result
        assert isinstance(result, dict)
        assert result["symbol"] == "BTCUSDT"
        assert "lastPrice" in result
    
    async def test_fetch_orderbook(self):
        """Test fetching order book data."""
        # Mock the response
        self.response_mock.json.return_value = MOCK_ORDERBOOK_RESPONSE
        
        # Fetch order book
        result = await self.collector.collect("orderbook", "BTCUSDT", limit=5)
        
        # Verify the request was made correctly
        self.session_mock.get.assert_called_once()
        args, kwargs = self.session_mock.get.call_args
        assert "depth" in args[0]
        assert kwargs["params"]["symbol"] == "BTCUSDT"
        assert kwargs["params"]["limit"] == 5
        
        # Verify the result
        assert isinstance(result, dict)
        assert "bids" in result
        assert "asks" in result
        assert len(result["bids"]) == 3
        assert len(result["asks"]) == 3
    
    async def test_websocket_subscription(self):
        """Test WebSocket subscription."""
        # Set up callback
        callback = AsyncMock()
        
        # Subscribe to WebSocket stream
        stream = await self.collector.subscribe_ws("kline", "btcusdt", timeframe="1m", callback=callback)
        
        # Verify the subscription
        self.ws_client_mock.add_callback.assert_called_once()
        self.ws_client_mock.add_stream.assert_called_once_with("btcusdt@kline_1m")
        
        # Verify stream name
        assert stream == "btcusdt@kline_1m"
        
        # Unsubscribe
        await self.collector.unsubscribe_ws(stream)
        
        # Verify unsubscription
        self.ws_client_mock.remove_stream.assert_called_once_with("btcusdt@kline_1m")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__]) 