"""
Message Schema Definitions

This module defines the schema for all messages exchanged between
the orchestrator and agents using Pydantic models.
"""

from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List, Union
from enum import Enum
from datetime import datetime
import uuid
import json

class MessageType(str, Enum):
    """Types of messages exchanged between orchestrator and agents."""
    COMMAND = "command"         # Orchestrator -> Agent: execute a command
    STATUS = "status"           # Agent -> Orchestrator: report status
    RESULT = "result"           # Agent -> Orchestrator: command execution result
    HEARTBEAT = "heartbeat"     # Bidirectional: health check
    NOTIFICATION = "notification"  # Bidirectional: informational updates
    ERROR = "error"             # Bidirectional: error reporting
    
class MessagePriority(str, Enum):
    """Priority levels for messages."""
    LOW = "low"           # Non-urgent information
    NORMAL = "normal"     # Default priority
    HIGH = "high"         # Important, process soon
    CRITICAL = "critical" # Urgent, process immediately

class Message(BaseModel):
    """
    Base message schema for all communication messages.
    
    This model defines the structure of all messages exchanged between
    the orchestrator and agents, ensuring consistent formatting and validation.
    """
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sender_id: str
    recipient_id: Optional[str] = None  # None for broadcast messages
    message_type: MessageType
    priority: MessagePriority = MessagePriority.NORMAL
    payload: Dict[str, Any]
    requires_ack: bool = False
    expires_at: Optional[datetime] = None
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }
    
    def to_json(self) -> str:
        """
        Serialize the message to JSON.
        
        Returns:
            JSON string representation of the message
        """
        return self.json()
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """
        Deserialize a message from JSON.
        
        Args:
            json_str: JSON string to parse
            
        Returns:
            Message object
        """
        return cls.parse_raw(json_str)
    
    @validator('expires_at')
    def validate_expiry(cls, expires_at, values):
        """
        Validate that expiry time is in the future.
        
        Args:
            expires_at: Expiry datetime
            values: Other field values
            
        Returns:
            Validated expiry datetime
            
        Raises:
            ValueError: If expiry time is not in the future
        """
        if expires_at and expires_at <= values.get('timestamp', datetime.utcnow()):
            raise ValueError("Expiry time must be in the future")
        return expires_at

# Command-specific message schemas
class CommandPayload(BaseModel):
    """Base payload for command messages."""
    command_type: str
    args: Dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0
    timeout_seconds: Optional[int] = None

class CommandMessage(Message):
    """Message for sending commands to agents."""
    message_type: MessageType = MessageType.COMMAND
    payload: CommandPayload
    requires_ack: bool = True

# Status-specific message schemas
class StatusLevel(str, Enum):
    """Status levels for status messages."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class StatusPayload(BaseModel):
    """Payload for status update messages."""
    status_level: StatusLevel
    status_code: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None

class StatusMessage(Message):
    """Message for agent status updates."""
    message_type: MessageType = MessageType.STATUS
    payload: StatusPayload

# Result-specific message schemas
class ResultStatus(str, Enum):
    """Status of command execution."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    IN_PROGRESS = "in_progress"

class ResultPayload(BaseModel):
    """Payload for command execution results."""
    command_id: str
    status: ResultStatus
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None  # seconds

class ResultMessage(Message):
    """Message for command execution results."""
    message_type: MessageType = MessageType.RESULT
    payload: ResultPayload
    requires_ack: bool = True

# Heartbeat-specific message schemas
class HeartbeatPayload(BaseModel):
    """Payload for heartbeat messages."""
    status: str = "alive"
    uptime: float  # seconds
    load: Optional[float] = None
    memory_usage: Optional[float] = None  # percentage

class HeartbeatMessage(Message):
    """Message for agent/orchestrator heartbeats."""
    message_type: MessageType = MessageType.HEARTBEAT
    payload: HeartbeatPayload 