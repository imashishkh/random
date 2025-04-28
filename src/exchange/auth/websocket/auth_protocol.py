"""
WebSocket authentication protocol handlers.

This module provides functions for authenticating WebSocket connections
using various authentication methods.
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable, Tuple, Union

from fastapi import WebSocket, WebSocketDisconnect, status

from .auth.jwt_handler import validate_token, is_token_about_to_expire
from .auth.api_key_handler import get_api_key_auth, ApiKeyError

# Configure logger
logger = logging.getLogger(__name__)

# WebSocket close codes
WS_CLOSE_NORMAL = 1000
WS_CLOSE_GOING_AWAY = 1001
WS_CLOSE_PROTOCOL_ERROR = 1002
WS_CLOSE_UNSUPPORTED = 1003
WS_CLOSE_NO_STATUS = 1005
WS_CLOSE_ABNORMAL = 1006
WS_CLOSE_INVALID_DATA = 1007
WS_CLOSE_POLICY_VIOLATION = 1008
WS_CLOSE_TOO_LARGE = 1009
WS_CLOSE_EXTENSION_REQUIRED = 1010
WS_CLOSE_UNEXPECTED_CONDITION = 1011

# Custom close codes (4000-4999 range is for application-specific codes)
WS_CLOSE_AUTH_REQUIRED = 4000
WS_CLOSE_AUTH_FAILED = 4001
WS_CLOSE_AUTH_EXPIRED = 4002
WS_CLOSE_INVALID_AUTH_FORMAT = 4003


async def validate_ws_token_on_connect(
    websocket: WebSocket,
    token_param: str = "token"
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Validate JWT token provided as a query parameter during WebSocket connection.
    
    Args:
        websocket: WebSocket connection
        token_param: Name of the query parameter containing the token
        
    Returns:
        Tuple of (is_valid, payload)
    """
    # Get token from query parameter
    token = websocket.query_params.get(token_param)
    
    if not token:
        logger.warning("WebSocket connection attempt without token")
        return False, None
    
    # Validate token
    is_valid, payload = validate_token(token)
    
    if not is_valid:
        logger.warning("Invalid token in WebSocket connection")
        return False, None
    
    return True, payload


async def authenticate_ws_connection(
    websocket: WebSocket,
    token_param: str = "token",
    on_success: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
) -> bool:
    """
    Authenticate a WebSocket connection using JWT token in query parameter.
    
    Args:
        websocket: WebSocket connection
        token_param: Name of the query parameter containing the token
        on_success: Optional callback function to call on successful authentication
        
    Returns:
        bool: True if authentication was successful, False otherwise
    """
    # Validate token
    is_valid, payload = await validate_ws_token_on_connect(websocket, token_param)
    
    if not is_valid:
        try:
            await websocket.close(code=WS_CLOSE_AUTH_FAILED, reason="Authentication failed")
        except Exception:
            pass
        return False
    
    # Call success callback if provided
    if on_success and payload:
        try:
            await on_success(payload)
        except Exception as e:
            logger.error(f"Error in WebSocket authentication success callback: {str(e)}")
    
    return True


async def validate_ws_message_auth(
    websocket: WebSocket,
    auth_timeout: float = 5.0
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Wait for and validate authentication message from WebSocket.
    
    Args:
        websocket: WebSocket connection
        auth_timeout: Timeout in seconds to wait for auth message
        
    Returns:
        Tuple of (is_valid, payload)
    """
    try:
        # Wait for authentication message with timeout
        auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=auth_timeout)
        
        # Validate message format
        if not isinstance(auth_message, dict):
            logger.warning("Invalid WebSocket auth message format (not a dict)")
            return False, None
        
        # Handle JWT token authentication
        if "auth" in auth_message and "token" in auth_message["auth"]:
            token = auth_message["auth"]["token"]
            is_valid, payload = validate_token(token)
            
            if not is_valid:
                logger.warning("Invalid token in WebSocket auth message")
                return False, None
            
            return True, payload
        
        # Handle API key authentication
        elif "auth" in auth_message and "api_key" in auth_message["auth"]:
            api_key = auth_message["auth"]["api_key"]
            signature = auth_message["auth"].get("signature")
            exchange = auth_message["auth"].get("exchange", "generic")
            
            if not signature:
                logger.warning("Missing signature in WebSocket API key auth")
                return False, None
            
            # Get parameters for validation
            params = {k: v for k, v in auth_message["auth"].items() 
                     if k not in ["signature", "method", "id"]}
            
            try:
                # Validate API key auth
                api_auth = get_api_key_auth(exchange)
                api_auth.authenticate_request(
                    api_key=api_key,
                    signature=signature,
                    params=params,
                    check_timestamp=True
                )
                
                # Return successful auth info
                return True, {
                    "api_key": api_key,
                    "exchange": exchange,
                    "auth_type": "api_key"
                }
            except ApiKeyError as e:
                logger.warning(f"API key WebSocket auth failed: {str(e)}")
                return False, None
        
        # Invalid auth message format
        logger.warning("Invalid WebSocket auth message format (missing auth details)")
        return False, None
    
    except asyncio.TimeoutError:
        logger.warning("WebSocket authentication timeout")
        return False, None
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during authentication")
        return False, None
    except Exception as e:
        logger.error(f"Error in WebSocket authentication: {str(e)}")
        return False, None


async def authenticate_ws_with_message(
    websocket: WebSocket,
    auth_timeout: float = 5.0,
    on_success: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
) -> bool:
    """
    Authenticate a WebSocket connection using message-based authentication.
    
    Args:
        websocket: WebSocket connection
        auth_timeout: Timeout in seconds to wait for auth message
        on_success: Optional callback function to call on successful authentication
        
    Returns:
        bool: True if authentication was successful, False otherwise
    """
    # Send authentication required message
    try:
        await websocket.send_json({
            "event": "auth_required",
            "data": {
                "message": "Authentication required to access this WebSocket"
            }
        })
    except Exception as e:
        logger.error(f"Error sending auth required message: {str(e)}")
        return False
    
    # Validate authentication message
    is_valid, payload = await validate_ws_message_auth(websocket, auth_timeout)
    
    if not is_valid:
        try:
            await websocket.close(code=WS_CLOSE_AUTH_FAILED, reason="Authentication failed")
        except Exception:
            pass
        return False
    
    # Send success message
    try:
        await websocket.send_json({
            "event": "auth_success",
            "data": {
                "message": "Authentication successful"
            }
        })
    except Exception as e:
        logger.error(f"Error sending auth success message: {str(e)}")
    
    # Call success callback if provided
    if on_success and payload:
        try:
            await on_success(payload)
        except Exception as e:
            logger.error(f"Error in WebSocket authentication success callback: {str(e)}")
    
    return True


async def refresh_ws_token(
    websocket: WebSocket,
    current_token: str
) -> Optional[str]:
    """
    Refresh a JWT token over WebSocket if it's about to expire.
    
    Args:
        websocket: WebSocket connection
        current_token: Current JWT token
        
    Returns:
        str: New token if refresh was successful, None otherwise
    """
    # Check if token is about to expire
    if not is_token_about_to_expire(current_token, 300):  # 5 minutes threshold
        return current_token
    
    try:
        # Send token refresh request
        await websocket.send_json({
            "event": "token_refresh",
            "data": {
                "token": current_token
            }
        })
        
        # Wait for refresh response
        response = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        
        # Validate response
        if isinstance(response, dict) and response.get("event") == "token_refresh":
            new_token = response.get("data", {}).get("token")
            
            if new_token:
                # Validate new token
                is_valid, _ = validate_token(new_token)
                
                if is_valid:
                    return new_token
        
        # Return original token if refresh failed
        return current_token
    except Exception as e:
        logger.error(f"Error refreshing WebSocket token: {str(e)}")
        return current_token


class WebSocketAuthMiddleware:
    """
    Middleware for WebSocket authentication.
    
    This class provides authentication for WebSocket connections
    with support for multiple authentication methods.
    """
    
    def __init__(
        self,
        app,
        auth_required: bool = True,
        token_param: str = "token",
        message_based_auth: bool = True,
        auth_timeout: float = 5.0
    ):
        """
        Initialize the WebSocket authentication middleware.
        
        Args:
            app: FastAPI application
            auth_required: Whether authentication is required
            token_param: Query parameter for token-based auth
            message_based_auth: Whether to use message-based auth
            auth_timeout: Timeout for message-based auth
        """
        self.app = app
        self.auth_required = auth_required
        self.token_param = token_param
        self.message_based_auth = message_based_auth
        self.auth_timeout = auth_timeout
    
    async def __call__(self, scope, receive, send):
        """
        Process the WebSocket connection.
        
        Args:
            scope: ASGI connection scope
            receive: ASGI receive function
            send: ASGI send function
        """
        if scope["type"] != "websocket":
            # Pass through non-WebSocket requests
            return await self.app(scope, receive, send)
        
        # Create WebSocket instance
        websocket = WebSocket(scope=scope, receive=receive, send=send)
        
        # Accept the connection
        await websocket.accept()
        
        # Skip auth if not required
        if not self.auth_required:
            return await self.app(scope, receive, send)
        
        # Try authenticating with token parameter
        if self.token_param in websocket.query_params:
            is_valid, _ = await validate_ws_token_on_connect(websocket, self.token_param)
            
            if is_valid:
                # Token is valid, proceed to app
                return await self.app(scope, receive, send)
        
        # If message-based auth is enabled, try it
        if self.message_based_auth:
            is_valid, _ = await validate_ws_message_auth(websocket, self.auth_timeout)
            
            if is_valid:
                # Auth message is valid, proceed to app
                return await self.app(scope, receive, send)
        
        # Authentication failed, close connection
        await websocket.close(code=WS_CLOSE_AUTH_REQUIRED, reason="Authentication required")
        return 