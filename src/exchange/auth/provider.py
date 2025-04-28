"""
Authentication Provider for Exchange Communications

This module provides a unified authentication service that works with
both REST and WebSocket connections and integrates with the Secret Manager.
"""
import abc
import hmac
import hashlib
import logging
import time
import json
from typing import Dict, Any, Optional, Tuple, Union
from urllib.parse import urlencode

from .transport.base import AuthType

# Configure logger
logger = logging.getLogger(__name__)

# Import Secret Manager if available
try:
    from src.security.secret_manager import SecretManager
    HAS_SECRET_MANAGER = True
except ImportError:
    logger.warning("Secret Manager not available, using basic credential storage")
    HAS_SECRET_MANAGER = False
    SecretManager = None

class AuthProvider:
    """
    Authentication provider for exchange communications.
    
    This class handles authentication for both REST and WebSocket
    connections, integrating with the Secret Manager when available.
    """
    
    def __init__(
        self,
        exchange: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        extra_auth: Optional[Dict[str, Any]] = None,
        auth_type: AuthType = AuthType.API_KEY,
        use_secret_manager: bool = True
    ):
        """
        Initialize the authentication provider.
        
        Args:
            exchange: Name of the exchange
            api_key: API key for the exchange
            api_secret: API secret for the exchange
            extra_auth: Extra authentication parameters
            auth_type: Type of authentication to use
            use_secret_manager: Whether to use the Secret Manager
        """
        self.exchange = exchange.lower()
        self.auth_type = auth_type
        self.use_secret_manager = use_secret_manager and HAS_SECRET_MANAGER
        self.extra_auth = extra_auth or {}
        
        # Store credentials directly if Secret Manager not used
        if not self.use_secret_manager:
            self.api_key = api_key
            self.api_secret = api_secret
        else:
            self.api_key = None
            self.api_secret = None
            
            # Store credentials in Secret Manager
            if api_key and api_secret:
                self._store_credentials(api_key, api_secret)
    
    def _store_credentials(self, api_key: str, api_secret: str) -> None:
        """
        Store credentials in the Secret Manager.
        
        Args:
            api_key: API key to store
            api_secret: API secret to store
        """
        if not self.use_secret_manager or not HAS_SECRET_MANAGER:
            return
        
        try:
            # Get the appropriate Secret Manager instance
            secret_manager = SecretManager.get_instance()
            
            # Store credentials
            secret_manager.store_credential(
                f"{self.exchange}_api_key",
                api_key
            )
            
            secret_manager.store_credential(
                f"{self.exchange}_api_secret",
                api_secret
            )
            
            logger.info(f"Stored {self.exchange} credentials in Secret Manager")
            
        except Exception as e:
            logger.error(f"Error storing credentials in Secret Manager: {str(e)}")
            
            # Fall back to direct storage
            self.api_key = api_key
            self.api_secret = api_secret
            self.use_secret_manager = False
    
    def _get_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get credentials from the Secret Manager or direct storage.
        
        Returns:
            Tuple of (api_key, api_secret)
        """
        if not self.use_secret_manager or not HAS_SECRET_MANAGER:
            return self.api_key, self.api_secret
        
        try:
            # Get the appropriate Secret Manager instance
            secret_manager = SecretManager.get_instance()
            
            # Retrieve credentials
            api_key = secret_manager.get_credential(f"{self.exchange}_api_key")
            api_secret = secret_manager.get_credential(f"{self.exchange}_api_secret")
            
            return api_key, api_secret
            
        except Exception as e:
            logger.error(f"Error retrieving credentials from Secret Manager: {str(e)}")
            
            # Fall back to direct storage
            return self.api_key, self.api_secret
    
    def get_auth_headers(self, request_path: str = "") -> Dict[str, str]:
        """
        Get authentication headers for a request.
        
        Args:
            request_path: Path of the request (for path-specific headers)
            
        Returns:
            Dict: Authentication headers
        """
        api_key, api_secret = self._get_credentials()
        
        if not api_key:
            return {}
        
        headers = {}
        
        # Basic API key authentication
        if self.auth_type == AuthType.API_KEY:
            # Binance and many others use X-MBX-APIKEY
            if self.exchange == 'binance':
                headers['X-MBX-APIKEY'] = api_key
            # Coinbase Pro uses CB-ACCESS headers
            elif self.exchange == 'coinbase':
                headers['CB-ACCESS-KEY'] = api_key
            # FTX uses FTX-KEY
            elif self.exchange == 'ftx':
                headers['FTX-KEY'] = api_key
            # Default to generic API-Key header
            else:
                headers['API-Key'] = api_key
        
        # JWT token authentication
        elif self.auth_type == AuthType.JWT:
            if 'jwt_token' in self.extra_auth:
                headers['Authorization'] = f"Bearer {self.extra_auth['jwt_token']}"
        
        # Session-based authentication
        elif self.auth_type == AuthType.SESSION:
            if 'session_token' in self.extra_auth:
                headers['Authorization'] = f"Session {self.extra_auth['session_token']}"
        
        return headers
    
    def sign_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Sign a request with authentication credentials.
        
        Args:
            method: HTTP method
            path: Request path
            params: Query parameters
            data: Request body data
            headers: Request headers
            
        Returns:
            Dict: Updated request data
        """
        api_key, api_secret = self._get_credentials()
        
        if not api_key or not api_secret:
            return {
                'params': params or {},
                'data': data or {},
                'headers': headers or {}
            }
        
        # Create copies to avoid modifying originals
        params = params.copy() if params else {}
        data = data.copy() if data else {}
        headers = headers.copy() if headers else {}
        
        # Handle exchange-specific signing logic
        if self.exchange == 'binance':
            return self._sign_binance_request(
                api_key, api_secret, method, path, params, data, headers
            )
        elif self.exchange == 'coinbase':
            return self._sign_coinbase_request(
                api_key, api_secret, method, path, params, data, headers
            )
        elif self.exchange == 'ftx':
            return self._sign_ftx_request(
                api_key, api_secret, method, path, params, data, headers
            )
        
        # Default to generic signing
        return {
            'params': params,
            'data': data,
            'headers': headers
        }
    
    def _sign_binance_request(
        self,
        api_key: str,
        api_secret: str,
        method: str,
        path: str,
        params: Dict[str, Any],
        data: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Sign a request for Binance.
        
        Args:
            api_key: API key
            api_secret: API secret
            method: HTTP method
            path: Request path
            params: Query parameters
            data: Request body data
            headers: Request headers
            
        Returns:
            Dict: Updated request data
        """
        # Add API key to headers
        headers['X-MBX-APIKEY'] = api_key
        
        # Combine params and data for signing
        payload = params.copy()
        payload.update(data)
        
        # Add timestamp if not present
        if 'timestamp' not in payload:
            payload['timestamp'] = int(time.time() * 1000)
        
        # Convert all values to strings
        payload = {k: str(v) for k, v in payload.items()}
        
        # Create signature
        query_string = urlencode(payload)
        signature = hmac.new(
            api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Add signature to payload
        payload['signature'] = signature
        
        # Update params or data based on HTTP method
        if method.upper() in ['GET', 'DELETE']:
            return {
                'params': payload,
                'data': {},
                'headers': headers
            }
        else:
            return {
                'params': {},
                'data': payload,
                'headers': headers
            }
    
    def _sign_coinbase_request(
        self,
        api_key: str,
        api_secret: str,
        method: str,
        path: str,
        params: Dict[str, Any],
        data: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Sign a request for Coinbase Pro.
        
        Args:
            api_key: API key
            api_secret: API secret
            method: HTTP method
            path: Request path
            params: Query parameters
            data: Request body data
            headers: Request headers
            
        Returns:
            Dict: Updated request data
        """
        # Generate timestamp
        timestamp = str(int(time.time()))
        
        # Create prehash string
        query_string = urlencode(params) if params else ""
        body = json.dumps(data) if data else ""
        prehash = timestamp + method.upper() + path
        
        if query_string:
            prehash += '?' + query_string
        
        if body:
            prehash += body
        
        # Create signature
        signature = hmac.new(
            api_secret.encode('utf-8'),
            prehash.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Add headers
        headers['CB-ACCESS-KEY'] = api_key
        headers['CB-ACCESS-SIGN'] = signature
        headers['CB-ACCESS-TIMESTAMP'] = timestamp
        
        if 'passphrase' in self.extra_auth:
            headers['CB-ACCESS-PASSPHRASE'] = self.extra_auth['passphrase']
        
        return {
            'params': params,
            'data': data,
            'headers': headers
        }
    
    def _sign_ftx_request(
        self,
        api_key: str,
        api_secret: str,
        method: str,
        path: str,
        params: Dict[str, Any],
        data: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Sign a request for FTX.
        
        Args:
            api_key: API key
            api_secret: API secret
            method: HTTP method
            path: Request path
            params: Query parameters
            data: Request body data
            headers: Request headers
            
        Returns:
            Dict: Updated request data
        """
        # Generate timestamp (in milliseconds)
        ts = int(time.time() * 1000)
        
        # Create payload string
        query_string = urlencode(params) if params else ""
        path_with_query = path
        if query_string:
            path_with_query += '?' + query_string
        
        payload = f'{ts}{method.upper()}{path_with_query}'
        
        if data:
            payload += json.dumps(data)
        
        # Create signature
        signature = hmac.new(
            api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Add headers
        headers['FTX-KEY'] = api_key
        headers['FTX-SIGN'] = signature
        headers['FTX-TS'] = str(ts)
        
        if 'subaccount' in self.extra_auth:
            headers['FTX-SUBACCOUNT'] = self.extra_auth['subaccount']
        
        return {
            'params': params,
            'data': data,
            'headers': headers
        }
    
    async def get_listen_key(self, http_client) -> Optional[str]:
        """
        Get a listen key for WebSocket authentication.
        
        Args:
            http_client: HTTP client to use for the request
            
        Returns:
            str: Listen key or None if failed
        """
        api_key, api_secret = self._get_credentials()
        
        if not api_key:
            logger.error("Cannot get listen key without API key")
            return None
        
        # Handle exchange-specific listen key logic
        if self.exchange == 'binance':
            endpoint = '/api/v3/userDataStream'
            headers = {'X-MBX-APIKEY': api_key}
            
            try:
                response = await http_client.post(endpoint, headers=headers)
                if response.status == 200:
                    result = await response.json()
                    listen_key = result.get('listenKey')
                    logger.info(f"Got listen key for {self.exchange}")
                    return listen_key
                else:
                    error = await response.text()
                    logger.error(f"Failed to get listen key: {error}")
                    return None
                    
            except Exception as e:
                logger.error(f"Error getting listen key: {str(e)}")
                return None
        
        return None
    
    async def keep_listen_key_alive(self, http_client, listen_key: str) -> bool:
        """
        Keep a listen key alive.
        
        Args:
            http_client: HTTP client to use for the request
            listen_key: Listen key to keep alive
            
        Returns:
            bool: True if successful, False otherwise
        """
        api_key, api_secret = self._get_credentials()
        
        if not api_key or not listen_key:
            return False
        
        # Handle exchange-specific listen key logic
        if self.exchange == 'binance':
            endpoint = '/api/v3/userDataStream'
            headers = {'X-MBX-APIKEY': api_key}
            params = {'listenKey': listen_key}
            
            try:
                response = await http_client.put(endpoint, headers=headers, params=params)
                if response.status == 200:
                    logger.debug(f"Refreshed listen key for {self.exchange}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"Failed to refresh listen key: {error}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error refreshing listen key: {str(e)}")
                return False
        
        return False 