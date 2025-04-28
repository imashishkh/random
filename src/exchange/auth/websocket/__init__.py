"""
WebSocket authentication module for exchange communications.

This package provides authentication for WebSocket connections.
"""

from .auth.websocket.auth_protocol import (
    authenticate_ws_connection,
    authenticate_ws_with_message,
    validate_ws_token_on_connect,
    validate_ws_message_auth,
    refresh_ws_token,
    WebSocketAuthMiddleware,
    WS_CLOSE_NORMAL,
    WS_CLOSE_GOING_AWAY,
    WS_CLOSE_PROTOCOL_ERROR,
    WS_CLOSE_UNSUPPORTED,
    WS_CLOSE_NO_STATUS,
    WS_CLOSE_ABNORMAL,
    WS_CLOSE_INVALID_DATA,
    WS_CLOSE_POLICY_VIOLATION,
    WS_CLOSE_TOO_LARGE,
    WS_CLOSE_EXTENSION_REQUIRED,
    WS_CLOSE_UNEXPECTED_CONDITION,
    WS_CLOSE_AUTH_REQUIRED,
    WS_CLOSE_AUTH_FAILED,
    WS_CLOSE_AUTH_EXPIRED,
    WS_CLOSE_INVALID_AUTH_FORMAT
)

__all__ = [
    "authenticate_ws_connection",
    "authenticate_ws_with_message",
    "validate_ws_token_on_connect",
    "validate_ws_message_auth",
    "refresh_ws_token",
    "WebSocketAuthMiddleware",
    "WS_CLOSE_NORMAL",
    "WS_CLOSE_GOING_AWAY",
    "WS_CLOSE_PROTOCOL_ERROR",
    "WS_CLOSE_UNSUPPORTED",
    "WS_CLOSE_NO_STATUS",
    "WS_CLOSE_ABNORMAL",
    "WS_CLOSE_INVALID_DATA",
    "WS_CLOSE_POLICY_VIOLATION",
    "WS_CLOSE_TOO_LARGE",
    "WS_CLOSE_EXTENSION_REQUIRED",
    "WS_CLOSE_UNEXPECTED_CONDITION",
    "WS_CLOSE_AUTH_REQUIRED",
    "WS_CLOSE_AUTH_FAILED",
    "WS_CLOSE_AUTH_EXPIRED",
    "WS_CLOSE_INVALID_AUTH_FORMAT"
] 