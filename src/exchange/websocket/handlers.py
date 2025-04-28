"""
WebSocket message handlers for cryptocurrency exchange data.

This module provides handler functions for different types of WebSocket messages
received from cryptocurrency exchanges. Each handler processes raw message data
and transforms it into a standardized format.
"""
import json
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime
import time

from .websocket.models import (
    WebSocketMessage,
    WebSocketMessageType,
    TradeModel,
    KlineModel,
    TickerModel,
    DepthModel,
    BookTickerModel,
    OrderModel,
    BalanceModel,
    AccountUpdateModel,
    OrderUpdateModel,
    WebSocketError
)

# Configure logger
logger = logging.getLogger(__name__)

async def default_handler(message: WebSocketMessage) -> None:
    """
    Default handler for WebSocket messages.
    
    Args:
        message: The WebSocket message to handle
    """
    logger.debug(f"Received {message.msg_type} message: {message.message_data}")

# Binance message handlers

async def handle_binance_trade(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle a Binance trade message.
    
    Args:
        data: Raw trade data from Binance
        
    Returns:
        Processed WebSocketMessage with trade data
    """
    try:
        # Extract stream name if present (for combined streams)
        stream = data.get("stream", "")
        
        # Get the actual trade data
        trade_data = data.get("data", data)
        
        # Create trade model
        trade = TradeModel(
            symbol=trade_data.get("s"),
            price=float(trade_data.get("p")),
            quantity=float(trade_data.get("q")),
            timestamp=int(trade_data.get("T")),
            event_datetime=datetime.fromtimestamp(int(trade_data.get("T")) / 1000),
            is_buyer_maker=trade_data.get("m", False),
            trade_id=str(trade_data.get("t")),
            exchange="binance"
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.TRADE,
            message_data=trade.dict(),
            raw_data=trade_data,
            timestamp=int(trade_data.get("E", trade_data.get("T"))),
            event_datetime=datetime.fromtimestamp(int(trade_data.get("E", trade_data.get("T"))) / 1000),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling Binance trade: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_binance_kline(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle a Binance kline/candlestick message.
    
    Args:
        data: Raw kline data from Binance
        
    Returns:
        Processed WebSocketMessage with kline data
    """
    try:
        # Extract stream name if present (for combined streams)
        stream = data.get("stream", "")
        
        # Get the actual kline data
        kline_data = data.get("data", data)
        k = kline_data.get("k", {})
        
        # Create kline model
        kline = KlineModel(
            symbol=k.get("s"),
            interval=k.get("i"),
            open_time=int(k.get("t")),
            close_time=int(k.get("T")),
            open_price=float(k.get("o")),
            high_price=float(k.get("h")),
            low_price=float(k.get("l")),
            close_price=float(k.get("c")),
            volume=float(k.get("v")),
            quote_volume=float(k.get("q")),
            trades_count=int(k.get("n")),
            is_closed=k.get("x", False),
            event_datetime=datetime.fromtimestamp(int(k.get("t")) / 1000),
            exchange="binance"
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.KLINE,
            message_data=kline.dict(),
            raw_data=kline_data,
            timestamp=int(kline_data.get("E", k.get("t"))),
            event_datetime=datetime.fromtimestamp(int(kline_data.get("E", k.get("t"))) / 1000),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling Binance kline: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_binance_ticker(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle a Binance ticker message.
    
    Args:
        data: Raw ticker data from Binance
        
    Returns:
        Processed WebSocketMessage with ticker data
    """
    try:
        # Extract stream name if present (for combined streams)
        stream = data.get("stream", "")
        
        # Get the actual ticker data
        ticker_data = data.get("data", data)
        
        # Create ticker model
        ticker = TickerModel(
            symbol=ticker_data.get("s"),
            price=float(ticker_data.get("c")),
            price_change=float(ticker_data.get("p", 0.0)),
            price_change_percent=float(ticker_data.get("P", "0").rstrip("%")),
            volume=float(ticker_data.get("v", 0.0)),
            quote_volume=float(ticker_data.get("q", 0.0)),
            high_price=float(ticker_data.get("h", 0.0)),
            low_price=float(ticker_data.get("l", 0.0)),
            open_price=float(ticker_data.get("o", 0.0)),
            timestamp=int(ticker_data.get("E", 0)),
            event_datetime=datetime.fromtimestamp(int(ticker_data.get("E", 0)) / 1000 if ticker_data.get("E", 0) > 0 else 0),
            exchange="binance"
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.TICKER,
            message_data=ticker.dict(),
            raw_data=ticker_data,
            timestamp=int(ticker_data.get("E", 0)),
            event_datetime=datetime.fromtimestamp(int(ticker_data.get("E", 0)) / 1000 if ticker_data.get("E", 0) > 0 else datetime.now().timestamp()),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling Binance ticker: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_binance_depth(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle a Binance depth (order book) message.
    
    Args:
        data: Raw depth data from Binance
        
    Returns:
        Processed WebSocketMessage with depth data
    """
    try:
        # Extract stream name if present (for combined streams)
        stream = data.get("stream", "")
        
        # Get the actual depth data
        depth_data = data.get("data", data)
        
        # Create depth model
        depth = DepthModel(
            symbol=depth_data.get("s", ""),
            timestamp=int(depth_data.get("E", 0)),
            event_datetime=datetime.fromtimestamp(int(depth_data.get("E", 0)) / 1000 if depth_data.get("E", 0) > 0 else 0),
            bids=[[float(price), float(qty)] for price, qty in depth_data.get("b", [])],
            asks=[[float(price), float(qty)] for price, qty in depth_data.get("a", [])],
            last_update_id=int(depth_data.get("u", 0)),
            exchange="binance"
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.DEPTH,
            message_data=depth.dict(),
            raw_data=depth_data,
            timestamp=int(depth_data.get("E", 0)),
            event_datetime=datetime.fromtimestamp(int(depth_data.get("E", 0)) / 1000 if depth_data.get("E", 0) > 0 else datetime.now().timestamp()),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling Binance depth: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_binance_book_ticker(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle a Binance book ticker message.
    
    Args:
        data: Raw book ticker data from Binance
        
    Returns:
        Processed WebSocketMessage with book ticker data
    """
    try:
        # Extract stream name if present (for combined streams)
        stream = data.get("stream", "")
        
        # Get the actual book ticker data
        book_data = data.get("data", data)
        
        # Create book ticker model
        book_ticker = BookTickerModel(
            symbol=book_data.get("s", ""),
            bid_price=float(book_data.get("b", 0.0)),
            bid_qty=float(book_data.get("B", 0.0)),
            ask_price=float(book_data.get("a", 0.0)),
            ask_qty=float(book_data.get("A", 0.0)),
            timestamp=int(book_data.get("E", 0)),
            event_datetime=datetime.fromtimestamp(int(book_data.get("E", 0)) / 1000 if book_data.get("E", 0) > 0 else 0),
            exchange="binance"
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.BOOK_TICKER,
            message_data=book_ticker.dict(),
            raw_data=book_data,
            timestamp=int(book_data.get("E", 0)),
            event_datetime=datetime.fromtimestamp(int(book_data.get("E", 0)) / 1000 if book_data.get("E", 0) > 0 else datetime.now().timestamp()),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling Binance book ticker: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_binance_account_update(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle a Binance account update message.
    
    Args:
        data: Raw account update data from Binance
        
    Returns:
        Processed WebSocketMessage with account update data
    """
    try:
        # Extract stream name if present (for combined streams)
        stream = data.get("stream", "")
        
        # Get the actual account update data
        update_data = data.get("data", data)
        
        # Process balances
        balances = []
        for b in update_data.get("B", []):
            balances.append(BalanceModel(
                asset=b.get("a", ""),
                free=float(b.get("f", 0.0)),
                locked=float(b.get("l", 0.0)),
                exchange="binance"
            ))
        
        # Create account update model
        account_update = AccountUpdateModel(
            event_type=update_data.get("e", ""),
            event_time=int(update_data.get("E", 0)),
            transaction_time=int(update_data.get("T", 0)),
            account_update_time=int(update_data.get("u", 0)),
            balances=balances,
            event_datetime=datetime.fromtimestamp(int(update_data.get("E", 0)) / 1000 if update_data.get("E", 0) > 0 else 0),
            exchange="binance"
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.ACCOUNT_UPDATE,
            message_data=account_update.dict(),
            raw_data=update_data,
            timestamp=int(update_data.get("E", 0)),
            event_datetime=datetime.fromtimestamp(int(update_data.get("E", 0)) / 1000 if update_data.get("E", 0) > 0 else datetime.now().timestamp()),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling Binance account update: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_binance_order_update(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle a Binance order update message.
    
    Args:
        data: Raw order update data from Binance
        
    Returns:
        Processed WebSocketMessage with order update data
    """
    try:
        # Extract stream name if present (for combined streams)
        stream = data.get("stream", "")
        
        # Get the actual order update data
        update_data = data.get("data", data)
        o = update_data.get("o", update_data)
        
        # Create order model
        order = OrderModel(
            symbol=o.get("s", ""),
            order_id=str(o.get("i", "")),
            client_order_id=o.get("c", ""),
            price=float(o.get("p", 0.0)),
            original_quantity=float(o.get("q", 0.0)),
            executed_quantity=float(o.get("z", 0.0)),
            status=o.get("X", ""),
            type=o.get("o", ""),
            side=o.get("S", ""),
            stop_price=float(o.get("P", 0.0)),
            time=int(o.get("T", 0)),
            is_maker=o.get("m", False),
            exchange="binance"
        )
        
        # Create order update model
        order_update = OrderUpdateModel(
            event_type=update_data.get("e", ""),
            event_time=int(update_data.get("E", 0)),
            transaction_time=int(update_data.get("T", 0)),
            order=order,
            event_datetime=datetime.fromtimestamp(int(update_data.get("E", 0)) / 1000 if update_data.get("E", 0) > 0 else 0),
            exchange="binance"
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.ORDER_UPDATE,
            message_data=order_update.dict(),
            raw_data=update_data,
            timestamp=int(update_data.get("E", 0)),
            event_datetime=datetime.fromtimestamp(int(update_data.get("E", 0)) / 1000 if update_data.get("E", 0) > 0 else datetime.now().timestamp()),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling Binance order update: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

# Helper functions

def get_binance_handler_for_stream(stream: str) -> Callable[[Dict[str, Any]], Awaitable[WebSocketMessage]]:
    """
    Get the appropriate handler function for a Binance stream.
    
    Args:
        stream: Stream name or identifier
        
    Returns:
        Handler function for the stream
    """
    if "@trade" in stream:
        return handle_binance_trade
    elif "@kline" in stream:
        return handle_binance_kline
    elif "@ticker" in stream:
        return handle_binance_ticker
    elif "@depth" in stream:
        return handle_binance_depth
    elif "@bookTicker" in stream:
        return handle_binance_book_ticker
    elif "userData" in stream:
        # For user data streams, need to check the event type in the message
        return _handle_binance_user_data
    else:
        logger.warning(f"No specific handler for stream: {stream}, using default handler")
        return lambda data: WebSocketMessage(
            msg_type=WebSocketMessageType.UNKNOWN,
            message_data=data,
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream
        )

async def _handle_binance_user_data(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle Binance user data stream messages based on event type.
    
    Args:
        data: Raw user data from Binance
        
    Returns:
        Processed WebSocketMessage
    """
    try:
        # Extract stream name if present (for combined streams)
        stream = data.get("stream", "userData")
        
        # Get the actual data
        event_data = data.get("data", data)
        
        # Route to appropriate handler based on event type
        event_type = event_data.get("e", "")
        
        if event_type == "outboundAccountPosition":
            return await handle_binance_account_update(data)
        elif event_type in ["executionReport", "ORDER_TRADE_UPDATE"]:
            return await handle_binance_order_update(data)
        else:
            logger.warning(f"Unknown user data event type: {event_type}")
            return WebSocketMessage(
                msg_type=WebSocketMessageType.UNKNOWN,
                message_data=event_data,
                raw_data=event_data,
                timestamp=int(event_data.get("E", 0) or datetime.now().timestamp() * 1000),
                event_datetime=datetime.fromtimestamp(int(event_data.get("E", 0) or datetime.now().timestamp() * 1000) / 1000),
                stream=stream
            )
    except Exception as e:
        logger.error(f"Error handling Binance user data: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else "userData"
        )

# FTX message handlers

async def handle_ftx_trade(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle an FTX trade message.
    
    Args:
        data: Raw trade data from FTX
        
    Returns:
        Processed WebSocketMessage with trade data
    """
    try:
        # Extract stream and market
        channel = data.get("channel", "")
        market = data.get("market", "")
        stream = f"{channel}/{market}"
        
        # Get the actual trade data
        trades_data = data.get("data", [])
        
        # If no trades, return early
        if not trades_data:
            logger.warning(f"Received empty FTX trade data for {market}")
            return WebSocketMessage(
                msg_type=WebSocketMessageType.UNKNOWN,
                message_data={},
                raw_data=data,
                timestamp=int(time.time() * 1000),
                event_datetime=datetime.now(),
                stream=stream
            )
        
        # Process all trades
        all_trades = []
        for trade_data in trades_data:
            # Create trade model
            timestamp = int(datetime.fromisoformat(trade_data.get("time").replace('Z', '+00:00')).timestamp() * 1000)
            trade = TradeModel(
                symbol=market,
                id=trade_data.get("id", 0),
                price=float(trade_data.get("price")),
                quantity=float(trade_data.get("size")),
                timestamp=timestamp,
                is_buyer_maker=not trade_data.get("side") == "buy",  # FTX uses 'buy' or 'sell'
                event_datetime=datetime.fromtimestamp(timestamp / 1000),
                exchange="ftx"
            )
            all_trades.append(trade.dict())
        
        # Create WebSocket message with the list of trades
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.TRADE,
            message_data={"trades": all_trades},
            raw_data=data,
            timestamp=int(time.time() * 1000),
            event_datetime=datetime.now(),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling FTX trade: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_ftx_ticker(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle an FTX ticker message.
    
    Args:
        data: Raw ticker data from FTX
        
    Returns:
        Processed WebSocketMessage with ticker data
    """
    try:
        # Extract stream and market
        channel = data.get("channel", "")
        market = data.get("market", "")
        stream = f"{channel}/{market}"
        
        # Get the actual ticker data
        ticker_data = data.get("data", {})
        
        # If no ticker data, return early
        if not ticker_data:
            logger.warning(f"Received empty FTX ticker data for {market}")
            return WebSocketMessage(
                msg_type=WebSocketMessageType.UNKNOWN,
                message_data={},
                raw_data=data,
                timestamp=int(time.time() * 1000),
                event_datetime=datetime.now(),
                stream=stream
            )
        
        # Current time
        current_time = int(time.time() * 1000)
        
        # Create ticker model
        ticker = TickerModel(
            symbol=market,
            last_price=float(ticker_data.get("last", 0.0)),
            bid_price=float(ticker_data.get("bid", 0.0)),
            ask_price=float(ticker_data.get("ask", 0.0)),
            volume=float(ticker_data.get("volume", 0.0)),
            quote_volume=float(ticker_data.get("quoteVolume", 0.0)) if "quoteVolume" in ticker_data else 0.0,
            timestamp=current_time,
            event_datetime=datetime.now(),
            exchange="ftx",
            # FTX doesn't provide all these fields, so set defaults
            price_change=0.0,
            price_change_percent=0.0,
            weighted_avg_price=0.0,
            prev_close_price=0.0,
            last_qty=0.0,
            bid_qty=0.0,
            ask_qty=0.0,
            open_price=0.0,
            high_price=0.0,
            low_price=0.0,
            open_time=0,
            close_time=current_time,
            first_id=0,
            last_id=0,
            count=0
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.TICKER,
            message_data=ticker.dict(),
            raw_data=data,
            timestamp=current_time,
            event_datetime=datetime.now(),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling FTX ticker: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_ftx_orderbook(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle an FTX orderbook message.
    
    Args:
        data: Raw orderbook data from FTX
        
    Returns:
        Processed WebSocketMessage with orderbook data
    """
    try:
        # Extract stream and market
        channel = data.get("channel", "")
        market = data.get("market", "")
        stream = f"{channel}/{market}"
        
        # Get the actual orderbook data
        orderbook_data = data.get("data", {})
        
        # If no orderbook data, return early
        if not orderbook_data:
            logger.warning(f"Received empty FTX orderbook data for {market}")
            return WebSocketMessage(
                msg_type=WebSocketMessageType.UNKNOWN,
                message_data={},
                raw_data=data,
                timestamp=int(time.time() * 1000),
                event_datetime=datetime.now(),
                stream=stream
            )
        
        # Current time
        current_time = int(time.time() * 1000)
        
        # Process bids and asks
        bids = []
        asks = []
        
        for bid in orderbook_data.get("bids", []):
            bids.append(DepthLevel(price=float(bid[0]), quantity=float(bid[1])))
        
        for ask in orderbook_data.get("asks", []):
            asks.append(DepthLevel(price=float(ask[0]), quantity=float(ask[1])))
        
        # Create depth model
        depth = DepthModel(
            symbol=market,
            update_id=int(time.time() * 1000),  # FTX doesn't provide an update ID, use timestamp
            timestamp=current_time,
            event_datetime=datetime.now(),
            bids=bids,
            asks=asks
        )
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.DEPTH,
            message_data=depth.dict(),
            raw_data=data,
            timestamp=current_time,
            event_datetime=datetime.now(),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling FTX orderbook: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_ftx_fills(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle an FTX fills message (user trades).
    
    Args:
        data: Raw fills data from FTX
        
    Returns:
        Processed WebSocketMessage with fills data
    """
    try:
        # Extract stream and market
        channel = data.get("channel", "")
        stream = f"{channel}/"
        
        # Get the actual fills data
        fills_data = data.get("data", [])
        
        # If no fills data, return early
        if not fills_data:
            logger.debug("Received empty FTX fills data")
            return WebSocketMessage(
                msg_type=WebSocketMessageType.UNKNOWN,
                message_data={},
                raw_data=data,
                timestamp=int(time.time() * 1000),
                event_datetime=datetime.now(),
                stream=stream
            )
        
        # Process fills
        all_fills = []
        
        for fill in fills_data:
            # Create order model for the fill
            market = fill.get("market", "")
            timestamp = int(datetime.fromisoformat(fill.get("time").replace('Z', '+00:00')).timestamp() * 1000)
            
            order = OrderModel(
                symbol=market,
                order_id=fill.get("orderId"),
                price=float(fill.get("price")),
                orig_qty=float(fill.get("size")),
                executed_qty=float(fill.get("size")),
                status="FILLED",
                time_in_force="GTC",
                type=fill.get("orderType", "").upper(),
                side=fill.get("side", "").upper(),
                time=timestamp,
                update_time=timestamp,
                is_working=False,
                event_datetime=datetime.fromtimestamp(timestamp / 1000)
            )
            
            all_fills.append(order.dict())
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.USER_DATA,
            message_data={"fills": all_fills},
            raw_data=data,
            timestamp=int(time.time() * 1000),
            event_datetime=datetime.now(),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling FTX fills: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

async def handle_ftx_orders(data: Dict[str, Any]) -> WebSocketMessage:
    """
    Handle an FTX orders message (user orders).
    
    Args:
        data: Raw orders data from FTX
        
    Returns:
        Processed WebSocketMessage with orders data
    """
    try:
        # Extract stream and market
        channel = data.get("channel", "")
        stream = f"{channel}/"
        
        # Get the actual orders data
        orders_data = data.get("data", [])
        
        # If no orders data, return early
        if not orders_data:
            logger.debug("Received empty FTX orders data")
            return WebSocketMessage(
                msg_type=WebSocketMessageType.UNKNOWN,
                message_data={},
                raw_data=data,
                timestamp=int(time.time() * 1000),
                event_datetime=datetime.now(),
                stream=stream
            )
        
        # Process orders
        all_orders = []
        
        for order in orders_data:
            # Create order model
            market = order.get("market", "")
            timestamp = int(datetime.fromisoformat(order.get("createdAt").replace('Z', '+00:00')).timestamp() * 1000)
            
            order_model = OrderModel(
                symbol=market,
                order_id=order.get("id"),
                price=float(order.get("price", 0.0)),
                orig_qty=float(order.get("size")),
                executed_qty=float(order.get("filledSize", 0.0)),
                status=order.get("status", "").upper(),
                time_in_force="GTC",
                type=order.get("type", "").upper(),
                side=order.get("side", "").upper(),
                time=timestamp,
                update_time=int(time.time() * 1000),
                is_working=order.get("status") == "open",
                event_datetime=datetime.fromtimestamp(timestamp / 1000)
            )
            
            all_orders.append(order_model.dict())
        
        # Create WebSocket message
        message = WebSocketMessage(
            msg_type=WebSocketMessageType.ORDER_UPDATE,
            message_data={"orders": all_orders},
            raw_data=data,
            timestamp=int(time.time() * 1000),
            event_datetime=datetime.now(),
            stream=stream
        )
        
        return message
    except Exception as e:
        logger.error(f"Error handling FTX orders: {str(e)}")
        return WebSocketMessage(
            msg_type=WebSocketMessageType.ERROR,
            message_data={"error": str(e)},
            raw_data=data,
            timestamp=int(datetime.now().timestamp() * 1000),
            event_datetime=datetime.now(),
            stream=stream if "stream" in locals() else ""
        )

def get_ftx_handler_for_stream(stream: str) -> Callable[[Dict[str, Any]], Awaitable[WebSocketMessage]]:
    """
    Get the appropriate handler function for an FTX stream.
    
    Args:
        stream: Stream name in format 'channel/market'
        
    Returns:
        Handler function for the stream
    """
    parts = stream.split('/')
    if len(parts) < 1:
        return default_handler
    
    channel = parts[0]
    
    if channel == 'trades':
        return handle_ftx_trade
    elif channel == 'ticker':
        return handle_ftx_ticker
    elif channel == 'orderbook':
        return handle_ftx_orderbook
    elif channel == 'fills':
        return handle_ftx_fills
    elif channel == 'orders':
        return handle_ftx_orders
    else:
        return default_handler 