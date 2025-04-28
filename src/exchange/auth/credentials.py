from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List, Any, Union


class AuthType(Enum):
    """Types of authentication methods supported by exchanges."""
    API_KEY_SECRET = "API_KEY_SECRET"  # Standard API key + secret
    JWT = "JWT"                        # JSON Web Token
    OAUTH = "OAUTH"                    # OAuth authentication
    HMAC = "HMAC"                      # HMAC-based authentication
    SESSION = "SESSION"                # Session-based (cookie)
    NONE = "NONE"                      # No authentication required


class SignatureMethod(Enum):
    """Methods for signing requests."""
    HMAC_SHA256 = "HMAC_SHA256"
    HMAC_SHA512 = "HMAC_SHA512"
    RSA = "RSA"
    ED25519 = "ED25519"
    NONE = "NONE"


@dataclass
class BaseCredentials:
    """Base class for all credential types."""
    exchange_id: str
    auth_type: AuthType
    label: str = "default"  # For multiple credentials for same exchange
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    @property
    def is_expired(self) -> bool:
        """Check if credentials have expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def seconds_until_expiry(self) -> Optional[int]:
        """Get seconds until credentials expire."""
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now()
        return max(0, int(delta.total_seconds()))


@dataclass
class ApiKeyCredentials(BaseCredentials):
    """API key based credentials."""
    api_key: str
    api_secret: str
    signature_method: SignatureMethod = SignatureMethod.HMAC_SHA256
    passphrase: Optional[str] = None  # Some exchanges require a passphrase
    key_permissions: List[str] = field(default_factory=list)  # e.g., ["trade", "withdraw"]


@dataclass
class JwtCredentials(BaseCredentials):
    """JWT token based credentials."""
    token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"


@dataclass
class OAuthCredentials(BaseCredentials):
    """OAuth based credentials."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    scope: List[str] = field(default_factory=list)


@dataclass
class SessionCredentials(BaseCredentials):
    """Session based credentials (typically cookie-based)."""
    session_id: str
    cookies: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class SignedRequest:
    """A request with authentication information added."""
    original_params: Dict[str, Any]
    signed_params: Dict[str, Any]
    headers: Dict[str, str]
    signature: Optional[str] = None
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


class CredentialStorage(Enum):
    """Storage methods for credentials."""
    ENV_VARS = "ENV_VARS"
    FILE = "FILE"
    SECRET_MANAGER = "SECRET_MANAGER"
    DATABASE = "DATABASE"


@dataclass
class CredentialConfig:
    """Configuration for credential management."""
    storage_type: CredentialStorage
    auto_refresh: bool = True
    refresh_threshold_seconds: int = 300  # Refresh when <5 min to expiry
    rotation_enabled: bool = False
    rotation_interval_days: int = 30
    storage_options: Dict[str, Any] = field(default_factory=dict)  # Options specific to storage type


# Type for any credential type
AnyCredential = Union[ApiKeyCredentials, JwtCredentials, OAuthCredentials, SessionCredentials] 