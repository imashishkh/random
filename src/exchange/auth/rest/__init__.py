"""
REST authentication module for exchange communications.

This package provides authentication for REST API endpoints.
"""

from .auth.rest.dependencies import (
    get_current_user,
    get_current_active_user,
    require_scopes,
    validate_api_key,
    get_jwt_user,
    validate_jwt,
    validate_api_key_auth
)

__all__ = [
    "get_current_user",
    "get_current_active_user",
    "require_scopes",
    "validate_api_key",
    "get_jwt_user",
    "validate_jwt",
    "validate_api_key_auth"
] 