"""
Audit logging utility for the Forex Trading AI System.
Records security-related events for compliance and monitoring.
"""
import logging
import datetime
from typing import Dict, Any, Optional, Union

from fastapi import Request
from pydantic import BaseModel

from ..db.connection import insert_with_json

# Configure logging
logger = logging.getLogger(__name__)

# Event types
class EventType:
    LOGIN = "login"
    LOGOUT = "logout"
    ACCESS = "access"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    KEY_ROTATE = "key_rotate"
    KEY_REVOKE = "key_revoke"
    CONFIG_CHANGE = "config_change"

# Statuses
class EventStatus:
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ATTEMPTED = "attempted"

class AuditEvent(BaseModel):
    """Audit event data model"""
    event_type: str
    actor_id: Optional[int] = None
    actor_type: Optional[str] = None
    ip_address: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: str
    status: str
    details: Optional[Dict[str, Any]] = None


async def log_event(
    event_type: str,
    action: str,
    status: str,
    actor_id: Optional[int] = None,
    actor_type: Optional[str] = None,
    ip_address: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[Union[str, int]] = None,
    details: Optional[Dict[str, Any]] = None
) -> int:
    """
    Log a security event to the audit log.
    
    Args:
        event_type: Type of event (see EventType class)
        action: Action being performed
        status: Result status (see EventStatus class)
        actor_id: ID of the user/entity performing the action
        actor_type: Type of actor (e.g., "user", "system")
        ip_address: IP address of the client
        resource_type: Type of resource being acted upon
        resource_id: ID of the resource being acted upon
        details: Additional details about the event
    
    Returns:
        int: ID of the inserted audit log record
    """
    try:
        # Convert resource_id to string if provided
        if resource_id is not None:
            resource_id = str(resource_id)
        
        # Create event data
        event_data = {
            "event_type": event_type,
            "action": action,
            "status": status,
            "event_time": datetime.datetime.utcnow().isoformat(),
        }
        
        # Add optional fields if provided
        if actor_id is not None:
            event_data["actor_id"] = actor_id
        if actor_type is not None:
            event_data["actor_type"] = actor_type
        if ip_address is not None:
            event_data["ip_address"] = ip_address
        if resource_type is not None:
            event_data["resource_type"] = resource_type
        if resource_id is not None:
            event_data["resource_id"] = resource_id
        if details is not None:
            event_data["details"] = details
        
        # Insert the event into the database
        log_id = insert_with_json("security.audit_log", event_data)
        
        # Also log to regular logs for visibility
        log_message = f"AUDIT: {event_type.upper()} {action} {status}"
        if resource_type and resource_id:
            log_message += f" | {resource_type}:{resource_id}"
        if actor_id:
            log_message += f" | actor:{actor_id}"
        
        logger.info(log_message)
        
        return log_id
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")
        # Log to regular logs as a fallback
        logger.warning(
            f"AUDIT-FALLBACK: {event_type}|{action}|{status}|{actor_id}|{resource_type}|{resource_id}"
        )
        return 0


async def log_api_access(
    request: Request,
    actor_id: Optional[int] = None,
    status: str = EventStatus.SUCCESS,
    details: Optional[Dict[str, Any]] = None
) -> int:
    """
    Log an API access event.
    
    Args:
        request: FastAPI request object
        actor_id: ID of the authenticated user
        status: Result status
        details: Additional details
    
    Returns:
        int: ID of the inserted audit log record
    """
    # Extract relevant information from the request
    ip_address = request.client.host if request.client else "unknown"
    method = request.method
    path = request.url.path
    
    # Create basic details if none provided
    if details is None:
        details = {}
    
    # Add request information to details
    request_details = {
        "method": method,
        "path": path,
        "user_agent": request.headers.get("user-agent", "unknown"),
    }
    details["request"] = request_details
    
    return await log_event(
        event_type=EventType.ACCESS,
        action=method,
        status=status,
        actor_id=actor_id,
        actor_type="user" if actor_id else "anonymous",
        ip_address=ip_address,
        resource_type="api_endpoint",
        resource_id=path,
        details=details
    )


async def log_api_key_event(
    event_type: str,
    key_id: int,
    actor_id: Optional[int],
    ip_address: Optional[str],
    status: str = EventStatus.SUCCESS,
    details: Optional[Dict[str, Any]] = None
) -> int:
    """
    Log an API key related event (creation, rotation, revocation).
    
    Args:
        event_type: The type of key event
        key_id: ID of the API key
        actor_id: ID of the user performing the action
        ip_address: IP address of the client
        status: Result status
        details: Additional details
    
    Returns:
        int: ID of the inserted audit log record
    """
    return await log_event(
        event_type=event_type,
        action="api_key_operation",
        status=status,
        actor_id=actor_id,
        actor_type="user" if actor_id else "system",
        ip_address=ip_address,
        resource_type="api_key",
        resource_id=key_id,
        details=details
    ) 