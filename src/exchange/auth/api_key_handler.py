"""
API key authentication handler for exchange communications.

Provides API key-based authentication including HMAC signing
for both REST and WebSocket connections.
"""
import hmac
import hashlib
import time
import json
import logging
import os
from typing import Dict, Any, Optional, Union, Tuple
from urllib.parse import urlencode

# Configure logger
logger = logging.getLogger(__name__)

# Determine if we should use the secret manager
try:
    from src.security.secrets.factory import get_secret_manager
    HAS_SECRET_MANAGER = True
except ImportError:
    logger.warning("Secret Manager not available, using fallback API key storage")
    HAS_SECRET_MANAGER = False


class ApiKeyError(Exception):
    """Base exception for API key-related errors."""
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(self.message)


class InvalidSignatureError(ApiKeyError):
    """Exception raised when an API signature is invalid."""
    def __init__(self, message: str = "Invalid signature"):
        super().__init__("INVALID_SIGNATURE", message)


class TimestampExpiredError(ApiKeyError):
    """Exception raised when a request timestamp is expired."""
    def __init__(self, message: str = "Request timestamp expired"):
        super().__init__("TIMESTAMP_EXPIRED", message)


class ApiKeyAuthentication:
    """
    API key authentication handler.
    
    This class handles API key authentication including HMAC signing
    for both REST and WebSocket connections.
    """
    
    def __init__(self, 
                 exchange: str,
                 timestamp_window_ms: int = 5000,
                 use_secret_manager: bool = True):
        """
        Initialize the API key authentication handler.
        
        Args:
            exchange: Name of the exchange
            timestamp_window_ms: Window in milliseconds for timestamp validation
            use_secret_manager: Whether to use the Secret Manager
        """
        self.exchange = exchange.lower()
        self.timestamp_window_ms = timestamp_window_ms
        self.use_secret_manager = use_secret_manager and HAS_SECRET_MANAGER
        self._secret_manager = None
        
        if self.use_secret_manager:
            try:
                self._secret_manager = get_secret_manager()
                logger.info(f"Using Secret Manager for {exchange} API key authentication")
            except Exception as e:
                logger.error(f"Failed to initialize Secret Manager: {str(e)}")
                self.use_secret_manager = False
    
    def _get_api_secret(self, api_key: str) -> Optional[str]:
        """
        Get API secret for a given API key.
        
        Args:
            api_key: API key
            
        Returns:
            str: API secret if found, None otherwise
        """
        if not api_key:
            return None
        
        # Get from Secret Manager if available
        if self.use_secret_manager and self._secret_manager:
            try:
                # Format the key identifier for the specific exchange
                secret_id = f"{self.exchange}_api_secret_{api_key}"
                secret = self._secret_manager.retrieve_secret(secret_id)
                return secret
            except Exception as e:
                logger.error(f"Error retrieving API secret from Secret Manager: {str(e)}")
                return None
        
        # Fallback to environment variables 
        # (not recommended for production, just for testing)
        env_var_name = f"{self.exchange.upper()}_API_SECRET"
        return os.getenv(env_var_name)
    
    def validate_timestamp(self, timestamp: Union[int, str]) -> bool:
        """
        Validate request timestamp.
        
        Args:
            timestamp: Request timestamp in milliseconds
            
        Returns:
            bool: True if timestamp is valid, False otherwise
            
        Raises:
            TimestampExpiredError: If timestamp is outside the allowed window
        """
        if not timestamp:
            raise TimestampExpiredError("Missing timestamp")
        
        try:
            # Convert to int if string
            ts = int(timestamp) if isinstance(timestamp, str) else timestamp
            
            # Get current time in milliseconds
            current_time = int(time.time() * 1000)
            
            # Check if timestamp is within allowed window
            if abs(current_time - ts) > self.timestamp_window_ms:
                raise TimestampExpiredError(
                    f"Timestamp outside allowed window ±{self.timestamp_window_ms}ms"
                )
            
            return True
        except ValueError:
            raise TimestampExpiredError("Invalid timestamp format")
    
    def create_signature(self, 
                        api_secret: str, 
                        data: Dict[str, Any], 
                        method: str = "sha256") -> str:
        """
        Create a signature for the given data.
        
        Args:
            api_secret: API secret
            data: Data to sign
            method: Signature method (sha256, sha512)
            
        Returns:
            str: Signature
        """
        # Convert data to a query string
        if isinstance(data, dict):
            payload = urlencode(sorted(data.items()))
        else:
            payload = str(data)
        
        # Create signature
        if method.lower() == "sha512":
            signature = hmac.new(
                api_secret.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha512
            ).hexdigest()
        else:
            # Default to SHA256
            signature = hmac.new(
                api_secret.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
        
        return signature
    
    def validate_signature(self, 
                          api_key: str, 
                          signature: str, 
                          data: Dict[str, Any],
                          method: str = "sha256") -> bool:
        """
        Validate a signature for the given data.
        
        Args:
            api_key: API key
            signature: Signature to validate
            data: Data that was signed
            method: Signature method (sha256, sha512)
            
        Returns:
            bool: True if signature is valid, False otherwise
            
        Raises:
            InvalidSignatureError: If signature is invalid
        """
        if not signature:
            raise InvalidSignatureError("Missing signature")
        
        # Get API secret
        api_secret = self._get_api_secret(api_key)
        if not api_secret:
            raise InvalidSignatureError(f"No API secret found for key {api_key}")
        
        # Create expected signature
        expected_signature = self.create_signature(api_secret, data, method)
        
        # Compare signatures (constant-time comparison to prevent timing attacks)
        if not hmac.compare_digest(signature.lower(), expected_signature.lower()):
            raise InvalidSignatureError("Signature mismatch")
        
        return True
    
    def authenticate_request(self, 
                            api_key: str, 
                            signature: str, 
                            params: Dict[str, Any],
                            method: str = "sha256",
                            check_timestamp: bool = True) -> bool:
        """
        Authenticate a request using API key and signature.
        
        Args:
            api_key: API key
            signature: Request signature
            params: Request parameters (including timestamp)
            method: Signature method (sha256, sha512)
            check_timestamp: Whether to validate timestamp
            
        Returns:
            bool: True if authentication is successful
            
        Raises:
            InvalidSignatureError: If signature is invalid
            TimestampExpiredError: If timestamp is outside the allowed window
        """
        # Validate timestamp if needed
        if check_timestamp and "timestamp" in params:
            self.validate_timestamp(params["timestamp"])
        
        # Validate signature
        return self.validate_signature(api_key, signature, params, method)
    
    def sign_request(self, 
                    api_key: str, 
                    api_secret: str, 
                    params: Dict[str, Any],
                    method: str = "sha256",
                    add_timestamp: bool = True) -> Dict[str, Any]:
        """
        Sign a request with API key and secret.
        
        Args:
            api_key: API key
            api_secret: API secret
            params: Request parameters
            method: Signature method (sha256, sha512)
            add_timestamp: Whether to add timestamp to params
            
        Returns:
            Dict: Signed parameters
        """
        # Clone params to avoid modifying the original
        signed_params = dict(params)
        
        # Add timestamp if needed
        if add_timestamp and "timestamp" not in signed_params:
            signed_params["timestamp"] = int(time.time() * 1000)
        
        # Create signature
        signature = self.create_signature(api_secret, signed_params, method)
        
        # Add signature to params
        signed_params["signature"] = signature
        
        return signed_params
    
    def sign_websocket_auth(self, 
                           api_key: str, 
                           api_secret: str, 
                           params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a signed authentication message for WebSocket.
        
        Args:
            api_key: API key
            api_secret: API secret
            params: Additional parameters for the auth message
            
        Returns:
            Dict: Signed authentication message
        """
        auth_params = params or {}
        
        # Add timestamp if not present
        if "timestamp" not in auth_params:
            auth_params["timestamp"] = int(time.time() * 1000)
        
        # Add API key
        auth_params["api_key"] = api_key
        
        # Sign the message
        signature = self.create_signature(api_secret, auth_params)
        
        # Create the authentication message
        auth_message = {
            "method": "auth",
            "params": auth_params,
            "signature": signature,
            "id": int(time.time() * 1000)  # Request ID
        }
        
        return auth_message
    
    def create_api_key_header(self, api_key: str) -> Dict[str, str]:
        """
        Create HTTP headers for API key authentication.
        
        Args:
            api_key: API key
            
        Returns:
            Dict: HTTP headers
        """
        # Different exchanges use different header formats
        if self.exchange == "binance":
            return {"X-MBX-APIKEY": api_key}
        elif self.exchange == "coinbase":
            return {"CB-ACCESS-KEY": api_key}
        elif self.exchange == "ftx":
            return {"FTX-KEY": api_key}
        else:
            # Default format
            return {"API-Key": api_key}


# Singleton instance dictionary for different exchanges
_api_key_auth_instances: Dict[str, ApiKeyAuthentication] = {}

def get_api_key_auth(exchange: str) -> ApiKeyAuthentication:
    """
    Get API key authentication instance for a specific exchange.
    
    Args:
        exchange: Name of the exchange
        
    Returns:
        ApiKeyAuthentication: Instance for the exchange
    """
    exchange = exchange.lower()
    
    # Create instance if not exists
    if exchange not in _api_key_auth_instances:
        _api_key_auth_instances[exchange] = ApiKeyAuthentication(exchange)
    
    return _api_key_auth_instances[exchange] 