"""
Short-Term Memory Module

This module implements short-term memory for agents,
including conversation history and working memory.
"""

import time
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from collections import deque

from ...utils.logging.logger import get_logger

logger = get_logger()


class Message:
    """Represents a message in the conversation history."""
    
    def __init__(
        self,
        content: str,
        role: str,
        message_id: Optional[str] = None,
        timestamp: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a message.
        
        Args:
            content: Message content.
            role: Message role (user, assistant, system, etc.).
            message_id: Unique ID for the message (generates UUID if None).
            timestamp: Creation timestamp (uses current time if None).
            metadata: Additional metadata.
        """
        self.content = content
        self.role = role
        self.message_id = message_id or str(uuid.uuid4())
        self.timestamp = timestamp or time.time()
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert message to dictionary format.
        
        Returns:
            Dictionary representation of the message.
        """
        return {
            "message_id": self.message_id,
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """
        Create message from dictionary.
        
        Args:
            data: Dictionary representation of message.
            
        Returns:
            New Message object.
        """
        return cls(
            content=data.get("content", ""),
            role=data.get("role", "unknown"),
            message_id=data.get("message_id"),
            timestamp=data.get("timestamp"),
            metadata=data.get("metadata", {})
        )
    
    def to_llm_format(self) -> Dict[str, str]:
        """
        Convert to format suitable for LLM API calls.
        
        Returns:
            Dictionary with role and content keys.
        """
        return {
            "role": self.role,
            "content": self.content
        }


class ShortTermMemory:
    """
    Short-term memory for agents, including conversation history and working memory.
    
    Maintains recent conversation messages and a working memory
    store for temporary information the agent needs to reference.
    """
    
    def __init__(
        self,
        agent_id: str,
        max_conversation_messages: int = 100,
        persistence_dir: Optional[str] = None
    ):
        """
        Initialize short-term memory.
        
        Args:
            agent_id: Unique identifier for the agent.
            max_conversation_messages: Maximum number of messages to keep in history.
            persistence_dir: Directory for storing memory.
        """
        self.agent_id = agent_id
        self.max_conversation_messages = max_conversation_messages
        
        # Initialize conversation history
        self.conversation: deque[Message] = deque(maxlen=max_conversation_messages)
        
        # Initialize working memory
        self.working_memory: Dict[str, Any] = {}
        
        # Set up persistence directory
        if persistence_dir:
            self.persistence_dir = Path(persistence_dir)
        else:
            home_dir = Path.home()
            self.persistence_dir = home_dir / ".agent_memory" / agent_id
        
        # Create directory if it doesn't exist
        self.persistence_dir.mkdir(parents=True, exist_ok=True)
        self.conversation_file = self.persistence_dir / "short_term_conversation.json"
        self.working_memory_file = self.persistence_dir / "short_term_working_memory.json"
        
        # Load existing memory if available
        self._load()
        
        logger.info(f"Short-term memory initialized for agent {agent_id}")
    
    def add_message(
        self,
        content: str,
        role: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add message to conversation history.
        
        Args:
            content: Message content.
            role: Message role (user, assistant, system, etc.).
            metadata: Additional metadata.
            
        Returns:
            ID of the created message.
        """
        # Create new message
        message = Message(
            content=content,
            role=role,
            metadata=metadata
        )
        
        # Add to conversation history
        self.conversation.append(message)
        
        # Auto-save
        self.save_conversation()
        
        logger.debug(f"Added {role} message to conversation history")
        return message.message_id
    
    def get_message(self, message_id: str) -> Optional[Message]:
        """
        Get message by ID.
        
        Args:
            message_id: ID of the message to retrieve.
            
        Returns:
            Message or None if not found.
        """
        for message in self.conversation:
            if message.message_id == message_id:
                return message
        return None
    
    def get_conversation_history(
        self,
        max_messages: Optional[int] = None,
        roles: Optional[List[str]] = None,
        min_timestamp: Optional[float] = None,
        reverse: bool = False
    ) -> List[Message]:
        """
        Get conversation history with optional filtering.
        
        Args:
            max_messages: Maximum number of messages to return.
            roles: Filter by roles.
            min_timestamp: Minimum timestamp.
            reverse: Return in reverse chronological order.
            
        Returns:
            List of messages.
        """
        # Convert deque to list for easier manipulation
        messages = list(self.conversation)
        
        # Apply filters
        if roles:
            messages = [m for m in messages if m.role in roles]
        
        if min_timestamp:
            messages = [m for m in messages if m.timestamp >= min_timestamp]
        
        # Apply order
        if reverse:
            messages.reverse()
        
        # Apply limit
        if max_messages:
            messages = messages[-max_messages:]
        
        return messages
    
    def get_llm_messages(
        self,
        max_messages: Optional[int] = None,
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        Get messages formatted for LLM API calls.
        
        Args:
            max_messages: Maximum number of messages to return.
            include_system: Whether to include system messages.
            
        Returns:
            List of message dictionaries with role and content.
        """
        # Get messages
        roles = None if include_system else ["user", "assistant"]
        messages = self.get_conversation_history(max_messages=max_messages, roles=roles)
        
        # Convert to LLM format
        return [message.to_llm_format() for message in messages]
    
    def clear_conversation(self) -> None:
        """Clear conversation history."""
        self.conversation.clear()
        self.save_conversation()
        logger.info("Cleared conversation history")
    
    def set_working_memory(self, key: str, value: Any) -> None:
        """
        Set a value in working memory.
        
        Args:
            key: Memory key.
            value: Memory value.
        """
        self.working_memory[key] = value
        self.save_working_memory()
        logger.debug(f"Set working memory '{key}'")
    
    def get_working_memory(self, key: str, default: Any = None) -> Any:
        """
        Get a value from working memory.
        
        Args:
            key: Memory key.
            default: Default value if key not found.
            
        Returns:
            Stored value or default.
        """
        return self.working_memory.get(key, default)
    
    def delete_working_memory(self, key: str) -> bool:
        """
        Delete a value from working memory.
        
        Args:
            key: Memory key to delete.
            
        Returns:
            Whether the key was deleted.
        """
        if key in self.working_memory:
            del self.working_memory[key]
            self.save_working_memory()
            logger.debug(f"Deleted working memory '{key}'")
            return True
        return False
    
    def clear_working_memory(self) -> None:
        """Clear all working memory."""
        self.working_memory.clear()
        self.save_working_memory()
        logger.info("Cleared working memory")
    
    def get_all_working_memory(self) -> Dict[str, Any]:
        """
        Get all working memory.
        
        Returns:
            Dictionary of all working memory.
        """
        return self.working_memory.copy()
    
    def save_conversation(self) -> bool:
        """
        Save conversation to disk.
        
        Returns:
            Whether the save operation was successful.
        """
        try:
            # Convert messages to dictionaries
            messages_dict = [
                message.to_dict() for message in self.conversation
            ]
            
            # Save to file
            with open(self.conversation_file, 'w') as f:
                json.dump(messages_dict, f, indent=2)
                
            logger.debug(f"Saved {len(self.conversation)} conversation messages to disk")
            return True
            
        except Exception as e:
            logger.error(f"Error saving conversation history: {str(e)}")
            return False
    
    def save_working_memory(self) -> bool:
        """
        Save working memory to disk.
        
        Returns:
            Whether the save operation was successful.
        """
        try:
            # Save to file
            with open(self.working_memory_file, 'w') as f:
                json.dump(self.working_memory, f, indent=2)
                
            logger.debug("Saved working memory to disk")
            return True
            
        except Exception as e:
            logger.error(f"Error saving working memory: {str(e)}")
            return False
    
    def save(self) -> bool:
        """
        Save all short-term memory to disk.
        
        Returns:
            Whether both save operations were successful.
        """
        return self.save_conversation() and self.save_working_memory()
    
    def _load(self) -> None:
        """Load memory from disk."""
        self._load_conversation()
        self._load_working_memory()
    
    def _load_conversation(self) -> None:
        """Load conversation history from disk."""
        if not self.conversation_file.exists():
            logger.debug("No existing conversation history file found")
            return
        
        try:
            with open(self.conversation_file, 'r') as f:
                messages_dict = json.load(f)
            
            # Convert dictionaries to Message objects and add to conversation
            for message_data in messages_dict:
                message = Message.from_dict(message_data)
                self.conversation.append(message)
            
            logger.info(f"Loaded {len(self.conversation)} conversation messages from disk")
            
        except Exception as e:
            logger.error(f"Error loading conversation history: {str(e)}")
            self.conversation.clear()
    
    def _load_working_memory(self) -> None:
        """Load working memory from disk."""
        if not self.working_memory_file.exists():
            logger.debug("No existing working memory file found")
            return
        
        try:
            with open(self.working_memory_file, 'r') as f:
                self.working_memory = json.load(f)
            
            logger.info(f"Loaded {len(self.working_memory)} working memory items from disk")
            
        except Exception as e:
            logger.error(f"Error loading working memory: {str(e)}")
            self.working_memory.clear() 