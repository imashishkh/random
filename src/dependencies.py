"""
Application dependency providers.

This module provides dependency injection functions for FastAPI to use in routes.
"""
import logging
from functools import lru_cache
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import database connection at module level since it's needed by multiple functions
from .database import SessionLocal

logger = logging.getLogger(__name__)

security = HTTPBearer()

@lru_cache()
def get_auth_service():
    """Returns a cached instance of the auth service."""
    from .services.auth_service import AuthService
    return AuthService()

def get_db_session():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db():
    """Get a database connection."""
    from .database import get_db
    return get_db()

def get_trade_service():
    """Returns an instance of the trade service."""
    from .services.trade_service import TradeService
    db = next(get_db())
    return TradeService(db)

def get_agent_service():
    """Returns an instance of the agent service."""
    from .services.agent_service import AgentService
    db = next(get_db())
    return AgentService(db)

def get_user_service():
    """Returns an instance of the user service."""
    from .services.user_service import UserService
    db = next(get_db())
    return UserService(db)

def get_analytics_service():
    """Returns an instance of the analytics service.
    
    The analytics service provides access to trading performance metrics,
    profit/loss analysis, trade distribution, and risk metrics.
    """
    from .services.analytics_service import AnalyticsService
    trade_service = get_trade_service()
    return AnalyticsService(trade_service)

def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)]
):
    """
    Dependency for getting the current authenticated user.
    
    Validates the bearer token and returns the user information.
    
    Args:
        credentials: The HTTP Bearer credentials
        auth_service: The auth service instance
        
    Returns:
        The authenticated user object
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        return auth_service.get_current_user(credentials.credentials)
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) 