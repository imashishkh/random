"""
Redis Communication Module

This module provides Redis-based communication capabilities for the Forex Trading platform,
including both PubSub for real-time messaging and Streams for reliable message delivery.
"""

from .redis.connection_manager import RedisConnectionManager
from .redis.message_schema import (
    Message, MessageType, MessagePriority,
    CommandMessage, StatusMessage, ResultMessage, HeartbeatMessage
)
from .redis.pubsub_messenger import PubSubMessenger
from .redis.stream_messenger import StreamMessenger
from .redis.facade import CommunicationFacade

# Convenience factory function to create a properly configured facade
def create_communication_facade(
    component_id: str,
    component_type: str,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_password: str = None
) -> CommunicationFacade:
    """
    Create a CommunicationFacade with standard configuration.
    
    Args:
        component_id: Unique ID for this component
        component_type: Type of component (e.g., 'orchestrator', 'agent')
        redis_host: Redis server hostname
        redis_port: Redis server port
        redis_password: Redis password (optional)
        
    Returns:
        Configured CommunicationFacade instance
    """
    # Create connection manager
    connection_manager = RedisConnectionManager(
        host=redis_host,
        port=redis_port,
        password=redis_password
    )
    
    # Create facade with standard channel/stream naming
    facade = CommunicationFacade(
        connection_manager=connection_manager,
        component_id=component_id,
        component_type=component_type,
        pub_channels=[
            f"{component_type}.{component_id}.out",
            f"{component_type}.broadcast"
        ],
        sub_channels=[
            f"{component_type}.{component_id}.in",
            f"*.broadcast"  # Subscribe to all broadcast channels
        ],
        stream_names=[
            f"stream.{component_type}.{component_id}.in",
            f"stream.{component_type}.{component_id}.out"
        ]
    )
    
    return facade

__all__ = [
    'RedisConnectionManager',
    'Message',
    'MessageType',
    'MessagePriority',
    'CommandMessage',
    'StatusMessage',
    'ResultMessage',
    'HeartbeatMessage',
    'PubSubMessenger',
    'StreamMessenger',
    'CommunicationFacade',
    'create_communication_facade'
]
