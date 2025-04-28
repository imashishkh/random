"""
Credential management module.

This module provides secure storage and access to API credentials
for various data sources and services.
"""

import os
import json
import logging
import time
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Setup logger
logger = logging.getLogger(__name__)

# Service types
SERVICE_TYPES = [
    "exchange",  # Trading exchanges like Binance, Coinbase
    "news",      # News APIs
    "data",      # Market data providers
    "sentiment", # Sentiment analysis services
    "llm",       # Language models like OpenAI, Perplexity
    "other"      # Other services
]


class CredentialError(Exception):
    """Base exception for credential related errors."""
    pass


class CredentialManager:
    """Secure manager for API credentials."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super(CredentialManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, encryption_key: Optional[str] = None, credentials_file: Optional[str] = None):
        """Initialize the credential manager.
        
        Args:
            encryption_key: Key used for encrypting credentials. If not provided, 
                            will try to read from CREDENTIAL_ENCRYPTION_KEY env var.
            credentials_file: Path to credentials storage file. If not provided,
                              will use default location.
        """
        # Only initialize once due to singleton pattern
        if self._initialized:
            return
        
        # Get encryption key from params or environment
        self._encryption_key = encryption_key or os.getenv("CREDENTIAL_ENCRYPTION_KEY")
        if not self._encryption_key:
            # Generate a random key if none provided
            salt = os.urandom(16)
            fallback_passphrase = f"forex-trading-{salt.hex()}"
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            self._encryption_key = base64.urlsafe_b64encode(
                kdf.derive(fallback_passphrase.encode())
            ).decode()
            
            logger.warning(
                "No encryption key provided. Generated a random key. "
                "This means credentials will be lost if the application restarts. "
                "Set CREDENTIAL_ENCRYPTION_KEY env var for persistent credentials."
            )
        
        # Initialize Fernet cipher
        self._cipher = Fernet(self._encryption_key.encode() if isinstance(self._encryption_key, str) else self._encryption_key)
        
        # Set credentials file path
        if credentials_file:
            self._credentials_file = Path(credentials_file)
        else:
            config_dir = Path(os.getenv("CONFIG_DIR", "./config"))
            config_dir.mkdir(exist_ok=True)
            self._credentials_file = config_dir / "credentials.enc"
        
        # In-memory cache of decrypted credentials with TTL
        self._credentials_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)  # 5 minute TTL by default
        
        # Load credentials if file exists
        self._credentials_loaded = False
        if self._credentials_file.exists():
            try:
                self._load_credentials()
                self._credentials_loaded = True
            except Exception as e:
                logger.error(f"Failed to load credentials: {e}")
        
        # Set initialized flag
        self._initialized = True
        
        logger.info(f"Credential manager initialized with storage at {self._credentials_file}")
    
    def _load_credentials(self):
        """Load and decrypt credentials from file."""
        try:
            with open(self._credentials_file, "rb") as f:
                encrypted_data = f.read()
            
            decrypted_data = self._cipher.decrypt(encrypted_data)
            credentials = json.loads(decrypted_data)
            
            # Update cache with loaded credentials
            now = datetime.utcnow()
            for service_id, creds in credentials.items():
                self._credentials_cache[service_id] = creds
                self._cache_timestamps[service_id] = now
            
            logger.info(f"Loaded credentials for {len(credentials)} services")
        except FileNotFoundError:
            logger.info("No credentials file found, starting with empty credentials")
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            raise CredentialError(f"Failed to load credentials: {e}")
    
    def _save_credentials(self):
        """Encrypt and save credentials to file."""
        try:
            # Create credentials data from cache
            credentials = {}
            for service_id, creds in self._credentials_cache.items():
                credentials[service_id] = creds
            
            # Encrypt and save
            json_data = json.dumps(credentials)
            encrypted_data = self._cipher.encrypt(json_data.encode())
            
            with open(self._credentials_file, "wb") as f:
                f.write(encrypted_data)
            
            logger.info(f"Saved credentials for {len(credentials)} services")
        except Exception as e:
            logger.error(f"Error saving credentials: {e}")
            raise CredentialError(f"Failed to save credentials: {e}")
    
    def set_credential(self, service_type: str, service_id: str, credentials: Dict[str, Any]) -> None:
        """Store credentials for a service.
        
        Args:
            service_type: Type of service (exchange, news, etc.)
            service_id: Unique identifier for the service
            credentials: Dictionary of credential data
            
        Raises:
            CredentialError: If service_type is invalid or there's an error saving
        """
        if service_type not in SERVICE_TYPES:
            raise CredentialError(
                f"Invalid service type: {service_type}. Must be one of {SERVICE_TYPES}"
            )
        
        # Create a credential record with metadata
        cred_record = {
            "type": service_type,
            "id": service_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "data": credentials
        }
        
        # Update cache
        cache_key = f"{service_type}:{service_id}"
        self._credentials_cache[cache_key] = cred_record
        self._cache_timestamps[cache_key] = datetime.utcnow()
        
        # Save to file
        try:
            self._save_credentials()
            logger.info(f"Stored credentials for {service_type}:{service_id}")
        except Exception as e:
            # Remove from cache if save failed
            self._credentials_cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)
            raise CredentialError(f"Failed to save credentials: {e}")
    
    def get_credential(self, service_type: str, service_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve credentials for a service.
        
        Args:
            service_type: Type of service
            service_id: Unique identifier for the service
            
        Returns:
            Dictionary of credential data or None if not found
            
        Raises:
            CredentialError: If there's an error retrieving credentials
        """
        cache_key = f"{service_type}:{service_id}"
        
        # Check cache first
        if cache_key in self._credentials_cache:
            # Check if cache entry is still valid
            cache_time = self._cache_timestamps.get(cache_key)
            if cache_time and datetime.utcnow() - cache_time < self._cache_ttl:
                return self._credentials_cache[cache_key]["data"]
        
        # If not in cache or expired, try to load from file
        if not self._credentials_loaded:
            try:
                self._load_credentials()
                self._credentials_loaded = True
            except Exception as e:
                logger.error(f"Failed to load credentials: {e}")
                raise CredentialError(f"Failed to load credentials: {e}")
        
        # Check if the credentials are now in cache after loading
        if cache_key in self._credentials_cache:
            self._cache_timestamps[cache_key] = datetime.utcnow()
            return self._credentials_cache[cache_key]["data"]
        
        logger.warning(f"No credentials found for {service_type}:{service_id}")
        return None
    
    def delete_credential(self, service_type: str, service_id: str) -> bool:
        """Delete credentials for a service.
        
        Args:
            service_type: Type of service
            service_id: Unique identifier for the service
            
        Returns:
            True if credentials were deleted, False if not found
            
        Raises:
            CredentialError: If there's an error saving after deletion
        """
        cache_key = f"{service_type}:{service_id}"
        
        # Check if exists
        if cache_key not in self._credentials_cache:
            if not self._credentials_loaded:
                try:
                    self._load_credentials()
                    self._credentials_loaded = True
                except Exception:
                    pass
            
            if cache_key not in self._credentials_cache:
                logger.warning(f"No credentials found to delete for {service_type}:{service_id}")
                return False
        
        # Remove from cache
        self._credentials_cache.pop(cache_key, None)
        self._cache_timestamps.pop(cache_key, None)
        
        # Save changes
        try:
            self._save_credentials()
            logger.info(f"Deleted credentials for {service_type}:{service_id}")
            return True
        except Exception as e:
            raise CredentialError(f"Failed to save after deleting credentials: {e}")
    
    def list_credentials(self, service_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all credentials, optionally filtered by service type.
        
        Args:
            service_type: Optional filter for service type
            
        Returns:
            List of credential records (without the actual credential data)
        """
        # Make sure credentials are loaded
        if not self._credentials_loaded:
            try:
                self._load_credentials()
                self._credentials_loaded = True
            except Exception:
                pass
        
        result = []
        for key, cred in self._credentials_cache.items():
            if service_type is None or cred["type"] == service_type:
                # Return metadata but not the actual credentials
                result.append({
                    "type": cred["type"],
                    "id": cred["id"],
                    "created_at": cred["created_at"],
                    "updated_at": cred["updated_at"]
                })
        
        return result
    
    def clear_cache(self):
        """Clear the in-memory credential cache."""
        self._credentials_cache = {}
        self._cache_timestamps = {}
        self._credentials_loaded = False
        logger.info("Credential cache cleared")


# Singleton instance
credential_manager = CredentialManager()


def get_credential(service_type: str, service_id: str) -> Optional[Dict[str, Any]]:
    """Get credentials for a service.
    
    Args:
        service_type: Type of service
        service_id: Unique identifier for the service
        
    Returns:
        Dictionary of credential data or None if not found
    """
    return credential_manager.get_credential(service_type, service_id)


def set_credential(service_type: str, service_id: str, credentials: Dict[str, Any]) -> None:
    """Store credentials for a service.
    
    Args:
        service_type: Type of service
        service_id: Unique identifier for the service
        credentials: Dictionary of credential data
    """
    credential_manager.set_credential(service_type, service_id, credentials)


def delete_credential(service_type: str, service_id: str) -> bool:
    """Delete credentials for a service.
    
    Args:
        service_type: Type of service
        service_id: Unique identifier for the service
        
    Returns:
        True if credentials were deleted, False if not found
    """
    return credential_manager.delete_credential(service_type, service_id)


def list_credentials(service_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all credentials, optionally filtered by service type.
    
    Args:
        service_type: Optional filter for service type
        
    Returns:
        List of credential records (without the actual credential data)
    """
    return credential_manager.list_credentials(service_type) 