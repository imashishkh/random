"""
API Key management module for the Forex Trading AI System.
Provides functionality for creating, validating, and rotating API keys.
"""
import os
import uuid
import time
import logging
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery
from pydantic import BaseModel

from ..db.connection import execute_query, insert_with_json

# Configure logging
logger = logging.getLogger(__name__)

# Constants
API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_QUERY_NAME = "api_key"
API_KEY_EXPIRY_DAYS = 90  # Default expiry for API keys
MASTER_KEY_ENV_VAR = "API_MASTER_KEY"  # Environment variable for master encryption key
DEFAULT_SALT = os.getenv("API_KEY_SALT", "forex_trading_salt").encode()

# Security mechanisms
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)
api_key_query = APIKeyQuery(name=API_KEY_QUERY_NAME, auto_error=False)

# Models
class ApiKey(BaseModel):
    """API Key data model"""
    id: int
    name: str
    key_prefix: str
    hashed_key: str
    encrypted_key: Optional[str] = None
    owner_id: int
    created_at: datetime
    expires_at: datetime
    last_used_at: Optional[datetime] = None
    is_active: bool = True
    scopes: List[str] = []
    metadata: Dict = {}


def get_encryption_key() -> bytes:
    """
    Get or generate the master encryption key for API keys.
    
    Returns:
        bytes: Encryption key
    
    Raises:
        RuntimeError: If master key is not available and cannot be generated
    """
    # Try to get the master key from environment
    master_key = os.getenv(MASTER_KEY_ENV_VAR)
    
    if not master_key:
        # Generate a key for development (not recommended for production)
        if os.getenv("ENVIRONMENT", "development") == "development":
            logger.warning("Generating temporary master key - NOT SECURE FOR PRODUCTION")
            master_key = Fernet.generate_key().decode()
            os.environ[MASTER_KEY_ENV_VAR] = master_key
        else:
            raise RuntimeError(f"Missing required environment variable: {MASTER_KEY_ENV_VAR}")
    
    # Convert string key to bytes if needed
    if isinstance(master_key, str):
        return master_key.encode()
    
    return master_key


def encrypt_api_key(api_key: str) -> str:
    """
    Encrypt an API key using the master encryption key.
    
    Args:
        api_key: The API key to encrypt
    
    Returns:
        str: Base64-encoded encrypted API key
    """
    key = get_encryption_key()
    f = Fernet(key)
    encrypted_data = f.encrypt(api_key.encode())
    return base64.b64encode(encrypted_data).decode()


def decrypt_api_key(encrypted_api_key: str) -> str:
    """
    Decrypt an encrypted API key.
    
    Args:
        encrypted_api_key: Base64-encoded encrypted API key
    
    Returns:
        str: Decrypted API key
    
    Raises:
        ValueError: If decryption fails
    """
    try:
        key = get_encryption_key()
        f = Fernet(key)
        encrypted_data = base64.b64decode(encrypted_api_key)
        return f.decrypt(encrypted_data).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt API key: {e}")
        raise ValueError("Invalid encrypted API key")


def hash_api_key(api_key: str) -> str:
    """
    Create a secure hash of an API key for storage.
    
    Args:
        api_key: The API key to hash
    
    Returns:
        str: Base64-encoded hash of the API key
    """
    # Use PBKDF2 with a salt for secure hashing
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=DEFAULT_SALT,
        iterations=100000,
    )
    key_hash = kdf.derive(api_key.encode())
    return base64.b64encode(key_hash).decode()


def generate_api_key(name: str, owner_id: int, expires_days: int = API_KEY_EXPIRY_DAYS, 
                     scopes: List[str] = None) -> Tuple[str, ApiKey]:
    """
    Generate a new API key and store it in the database.
    
    Args:
        name: Name/description for the API key
        owner_id: ID of the user/entity this key belongs to
        expires_days: Number of days until this key expires
        scopes: List of permission scopes for this key
    
    Returns:
        Tuple containing the raw API key (only shown once) and the ApiKey object
    
    Raises:
        Exception: If key creation fails
    """
    if scopes is None:
        scopes = ["read"]
    
    try:
        # Generate a secure random API key
        raw_key = f"ft_{uuid.uuid4().hex}_{uuid.uuid4().hex}"
        key_prefix = raw_key.split("_")[0:2]
        key_prefix = "_".join(key_prefix)
        
        # Hash the key for storage
        hashed_key = hash_api_key(raw_key)
        
        # Encrypt the full key for potential recovery
        encrypted_key = encrypt_api_key(raw_key)
        
        # Prepare expiration date
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(days=expires_days)
        
        # Create database record
        api_key_data = {
            "name": name,
            "key_prefix": key_prefix,
            "hashed_key": hashed_key,
            "encrypted_key": encrypted_key,
            "owner_id": owner_id,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "is_active": True,
            "scopes": scopes,
            "metadata": {}
        }
        
        # Insert into database
        key_id = insert_with_json("security.api_keys", api_key_data)
        
        # Create ApiKey object (with ID from database)
        api_key_record = ApiKey(
            id=key_id,
            name=name,
            key_prefix=key_prefix,
            hashed_key=hashed_key,
            encrypted_key=encrypted_key,
            owner_id=owner_id,
            created_at=created_at,
            expires_at=expires_at,
            is_active=True,
            scopes=scopes,
            metadata={}
        )
        
        logger.info(f"Created new API key: {key_prefix}... for owner ID {owner_id}")
        return raw_key, api_key_record
        
    except Exception as e:
        logger.error(f"Failed to generate API key: {e}")
        raise


def get_api_key_by_prefix(key_prefix: str) -> Optional[ApiKey]:
    """
    Retrieve an API key record by its prefix.
    
    Args:
        key_prefix: The prefix of the API key to find
    
    Returns:
        ApiKey object if found, None otherwise
    """
    try:
        query = """
            SELECT * FROM security.api_keys 
            WHERE key_prefix = %s AND is_active = TRUE
            LIMIT 1
        """
        results = execute_query(query, (key_prefix,))
        
        if not results:
            return None
        
        # Convert the result to an ApiKey object
        api_key_data = results[0]
        return ApiKey(**api_key_data)
        
    except Exception as e:
        logger.error(f"Error retrieving API key by prefix: {e}")
        return None


def validate_api_key(api_key: str) -> Optional[ApiKey]:
    """
    Validate an API key and return the corresponding record.
    
    Args:
        api_key: The API key to validate
    
    Returns:
        ApiKey object if valid, None otherwise
    """
    try:
        # Extract the prefix from the key
        key_parts = api_key.split("_")
        if len(key_parts) < 3:
            logger.warning("Invalid API key format")
            return None
        
        key_prefix = f"{key_parts[0]}_{key_parts[1]}"
        
        # Retrieve the key record by prefix
        api_key_record = get_api_key_by_prefix(key_prefix)
        if not api_key_record:
            logger.warning(f"API key with prefix {key_prefix} not found")
            return None
        
        # Check if the key is expired
        if api_key_record.expires_at < datetime.utcnow():
            logger.warning(f"API key with prefix {key_prefix} is expired")
            return None
        
        # Hash the provided key and compare with stored hash
        hashed_key = hash_api_key(api_key)
        if hashed_key != api_key_record.hashed_key:
            logger.warning(f"Invalid API key hash for prefix {key_prefix}")
            return None
        
        # Update last used timestamp
        update_api_key_usage(api_key_record.id)
        
        return api_key_record
        
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        return None


def update_api_key_usage(key_id: int) -> bool:
    """
    Update the last used timestamp for an API key.
    
    Args:
        key_id: Database ID of the API key
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        query = """
            UPDATE security.api_keys
            SET last_used_at = %s
            WHERE id = %s
        """
        execute_query(query, (datetime.utcnow().isoformat(), key_id))
        return True
    except Exception as e:
        logger.error(f"Error updating API key usage: {e}")
        return False


def revoke_api_key(key_id: int) -> bool:
    """
    Revoke an API key by setting it as inactive.
    
    Args:
        key_id: Database ID of the API key to revoke
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        query = """
            UPDATE security.api_keys
            SET is_active = FALSE
            WHERE id = %s
        """
        execute_query(query, (key_id,))
        logger.info(f"Revoked API key ID: {key_id}")
        return True
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")
        return False


def rotate_api_key(key_id: int) -> Optional[Tuple[str, ApiKey]]:
    """
    Rotate an API key by generating a new one with the same settings.
    
    Args:
        key_id: Database ID of the API key to rotate
    
    Returns:
        Tuple containing the new raw API key and ApiKey object if successful, None otherwise
    """
    try:
        # Get the existing key
        query = "SELECT * FROM security.api_keys WHERE id = %s"
        results = execute_query(query, (key_id,))
        
        if not results:
            logger.warning(f"API key with ID {key_id} not found")
            return None
        
        old_key = results[0]
        
        # Revoke the old key
        revoke_api_key(key_id)
        
        # Generate a new key with the same settings
        return generate_api_key(
            name=f"{old_key['name']} (rotated)",
            owner_id=old_key['owner_id'],
            expires_days=API_KEY_EXPIRY_DAYS,
            scopes=old_key['scopes']
        )
    except Exception as e:
        logger.error(f"Error rotating API key: {e}")
        return None


async def get_api_key(
    api_key_header: str = Security(api_key_header),
    api_key_query: str = Security(api_key_query),
) -> ApiKey:
    """
    FastAPI dependency for API key authentication.
    
    Args:
        api_key_header: API key from request header
        api_key_query: API key from query parameter
    
    Returns:
        ApiKey: Validated API key record
    
    Raises:
        HTTPException: If API key is missing or invalid
    """
    api_key = api_key_header or api_key_query
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    api_key_record = validate_api_key(api_key)
    
    if not api_key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return api_key_record


def require_scopes(required_scopes: List[str]):
    """
    Create a dependency that requires specific API key scopes.
    
    Args:
        required_scopes: List of required scope strings
    
    Returns:
        Function that can be used as a FastAPI dependency
    """
    
    async def validate_scopes(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
        """
        Validate that the API key has the required scopes.
        
        Args:
            api_key: Validated API key from previous dependency
        
        Returns:
            ApiKey: The same API key if validation passes
        
        Raises:
            HTTPException: If API key lacks required scopes
        """
        # Check if the API key has all required scopes
        has_required_scopes = all(scope in api_key.scopes for scope in required_scopes)
        
        if not has_required_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks required scopes: {', '.join(required_scopes)}",
            )
        
        return api_key
    
    return validate_scopes