"""
Memory Manager Module

This module provides a unified memory management system for agents,
integrating both short-term and long-term memory capabilities.
"""

from typing import Any, Dict, List, Optional, Union, Tuple
import os
import json
import time

from .memory.short_term import ShortTermMemory, Message
from .memory.long_term import LongTermMemory, MemoryEntry
from ...utils.logging.logger import get_logger

# Get logger
logger = get_logger()


class MemoryManager:
    """
    Unified memory management system for agents.
    
    Integrates short-term memory (conversation history and working memory)
    with long-term memory (persistent knowledge and experiences).
    """
    
    def __init__(
        self,
        agent_id: str,
        memory_dir: str = "memory",
        max_conversation_messages: int = 100,
        max_working_variables: int = 50,
        system_prompt: Optional[str] = None,
        enable_vector_store: bool = True,
        openai_api_key: Optional[str] = None,
        vector_collection_name: Optional[str] = None,
        memory_saving_interval: int = 600  # 10 minutes
    ):
        """
        Initialize the memory manager.
        
        Args:
            agent_id: Unique identifier for the agent.
            memory_dir: Directory to store memory files.
            max_conversation_messages: Maximum number of messages in conversation history.
            max_working_variables: Maximum number of variables in working memory.
            system_prompt: Optional system prompt for the agent.
            enable_vector_store: Whether to enable the vector store for long-term memory.
            openai_api_key: OpenAI API key for embeddings (if vector store is enabled).
            vector_collection_name: Name of the vector collection (defaults to agent_id).
            memory_saving_interval: Time interval (in seconds) for auto-saving memory.
        """
        self.agent_id = agent_id
        self.memory_dir = memory_dir
        
        # Create memory directory if it doesn't exist
        os.makedirs(memory_dir, exist_ok=True)
        
        # Ensure agent-specific directory exists
        self.agent_memory_dir = os.path.join(memory_dir, agent_id)
        os.makedirs(self.agent_memory_dir, exist_ok=True)
        
        # Initialize short-term memory
        self.short_term = ShortTermMemory(
            agent_id=agent_id,
            max_conversation_messages=max_conversation_messages,
            max_working_variables=max_working_variables,
            system_prompt=system_prompt
        )
        
        # Initialize long-term memory
        vector_collection_name = vector_collection_name or f"{agent_id}_memory"
        self.long_term = LongTermMemory(
            agent_id=agent_id,
            enable_vector_store=enable_vector_store,
            openai_api_key=openai_api_key,
            vector_collection_name=vector_collection_name,
            persistence_directory=self.agent_memory_dir
        )
        
        # Memory saving settings
        self.memory_saving_interval = memory_saving_interval
        self.last_save_time = time.time()
        
        logger.info(f"Memory manager initialized for agent {agent_id}")
    
    def add_message(
        self,
        content: str,
        role: str,
        add_to_long_term: bool = True,
        message_id: Optional[str] = None,
        timestamp: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        Add a message to memory.
        
        Args:
            content: The content of the message.
            role: The role of the sender (e.g., "user", "assistant", "system").
            add_to_long_term: Whether to add the message to long-term memory.
            message_id: Optional ID for the message.
            timestamp: Optional timestamp for the message.
            metadata: Optional metadata for the message.
            
        Returns:
            The added message.
        """
        # Add to short-term memory
        message = self.short_term.conversation.add_message(
            content=content,
            role=role,
            message_id=message_id,
            timestamp=timestamp,
            metadata=metadata
        )
        
        # Add to long-term memory if requested
        if add_to_long_term and role != "system":
            self.long_term.add_conversation_message(
                content=content,
                role=role,
                metadata=metadata
            )
        
        # Check if we should auto-save
        self._check_auto_save()
        
        return message
    
    def add_fact(
        self,
        content: str,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a fact to long-term memory.
        
        Args:
            content: The factual information to store.
            importance: Importance score (0.0 to 1.0).
            metadata: Optional metadata about the fact.
            
        Returns:
            ID of the created memory entry.
        """
        entry_id = self.long_term.add_fact(
            content=content,
            importance=importance,
            metadata=metadata
        )
        
        # Check if we should auto-save
        self._check_auto_save()
        
        return entry_id
    
    def add_decision(
        self,
        content: str,
        reasoning: str,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a decision to long-term memory.
        
        Args:
            content: The decision that was made.
            reasoning: The reasoning behind the decision.
            importance: Importance score (0.0 to 1.0).
            metadata: Optional metadata about the decision.
            
        Returns:
            ID of the created memory entry.
        """
        # Add metadata about reasoning if not present
        metadata = metadata or {}
        if "reasoning" not in metadata:
            metadata["reasoning"] = reasoning
        
        entry_id = self.long_term.add_decision(
            content=content,
            importance=importance,
            metadata=metadata
        )
        
        # Check if we should auto-save
        self._check_auto_save()
        
        return entry_id
    
    def search_long_term_memory(
        self,
        query: str,
        limit: int = 5,
        entry_types: Optional[List[str]] = None,
        min_relevance: float = 0.0
    ) -> List[MemoryEntry]:
        """
        Search long-term memory for relevant information.
        
        Args:
            query: The search query.
            limit: Maximum number of results to return.
            entry_types: Filter by entry types (e.g., ["fact", "decision"]).
            min_relevance: Minimum relevance score (0.0 to 1.0).
            
        Returns:
            List of relevant memory entries.
        """
        return self.long_term.search_by_content(
            query=query,
            limit=limit,
            entry_types=entry_types,
            min_relevance=min_relevance
        )
    
    def get_conversation_context(
        self,
        query: Optional[str] = None,
        limit: int = 10,
        include_roles: Optional[List[str]] = None,
        exclude_roles: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get a context object containing relevant information for the agent.
        
        Args:
            query: Optional query to search long-term memory.
            limit: Maximum number of long-term memory entries to include.
            include_roles: Only include messages from these roles.
            exclude_roles: Exclude messages from these roles.
            
        Returns:
            A context object with short-term and optionally long-term memory.
        """
        # Get recent messages
        recent_messages = self.short_term.conversation.get_messages(
            include_roles=include_roles,
            exclude_roles=exclude_roles
        )
        
        # Convert to dictionary format
        recent_messages_dict = [msg.to_dict() for msg in recent_messages]
        
        # Initialize context
        context = {
            "conversation_history": recent_messages_dict,
            "working_memory": self.short_term.working.get_all()
        }
        
        # Search long-term memory if query provided
        if query:
            relevant_memories = self.search_long_term_memory(
                query=query,
                limit=limit
            )
            context["relevant_memories"] = [mem.to_dict() for mem in relevant_memories]
        
        return context
    
    def get_relevant_context(
        self,
        query: str,
        conversation_limit: int = 10,
        memory_limit: int = 5
    ) -> str:
        """
        Get a formatted string of relevant context for the agent.
        
        Args:
            query: Query to search for relevant memories.
            conversation_limit: Maximum number of conversation messages to include.
            memory_limit: Maximum number of long-term memory entries to include.
            
        Returns:
            Formatted context string.
        """
        # Get recent conversation
        recent_messages = self.short_term.conversation.get_messages(
            limit=conversation_limit
        )
        
        # Get relevant memories
        relevant_memories = self.search_long_term_memory(
            query=query,
            limit=memory_limit
        )
        
        # Format the context
        context_parts = ["# Agent Context"]
        
        # Add working memory section
        working_memory = self.short_term.working.get_all()
        if working_memory:
            context_parts.append("\n## Working Memory")
            for key, value in working_memory.items():
                context_parts.append(f"- {key}: {value}")
        
        # Add relevant memories section
        if relevant_memories:
            context_parts.append("\n## Relevant Memories")
            for i, memory in enumerate(relevant_memories, 1):
                context_parts.append(f"{i}. [{memory.entry_type.upper()}] {memory.content}")
                
                # Add additional details if available
                if memory.metadata and len(memory.metadata) > 0:
                    for k, v in memory.metadata.items():
                        if k not in ["embedding"]:  # Skip embedding data
                            context_parts.append(f"   - {k}: {v}")
        
        # Add recent conversation section
        if recent_messages:
            context_parts.append("\n## Recent Conversation")
            conversation_str = self.short_term.conversation.get_formatted_history(
                limit=conversation_limit
            )
            context_parts.append(conversation_str)
        
        return "\n".join(context_parts)
    
    def set_working_memory(self, key: str, value: Any) -> None:
        """
        Set a variable in working memory.
        
        Args:
            key: Variable key.
            value: Variable value.
        """
        self.short_term.working.set(key, value)
        
        # Check if we should auto-save
        self._check_auto_save()
    
    def get_working_memory(self, key: str, default: Any = None) -> Any:
        """
        Get a variable from working memory.
        
        Args:
            key: Variable key.
            default: Default value if the key doesn't exist.
            
        Returns:
            Variable value or default.
        """
        return self.short_term.working.get(key, default)
    
    def clear_conversation_history(self, keep_system: bool = True) -> None:
        """
        Clear conversation history.
        
        Args:
            keep_system: Whether to keep system messages.
        """
        self.short_term.conversation.clear_history(keep_system=keep_system)
        logger.info("Conversation history cleared")
    
    def clear_working_memory(self) -> None:
        """Clear working memory."""
        self.short_term.working.clear()
        logger.info("Working memory cleared")
    
    def forget_memory(self, entry_id: str) -> bool:
        """
        Forget a specific memory entry.
        
        Args:
            entry_id: ID of the memory entry to forget.
            
        Returns:
            Whether the operation was successful.
        """
        result = self.long_term.forget_entry(entry_id)
        
        if result:
            logger.info(f"Forgot memory entry: {entry_id}")
        else:
            logger.warning(f"Failed to forget memory entry: {entry_id}")
        
        return result
    
    def save_memory(self) -> bool:
        """
        Save memory to disk.
        
        Returns:
            Whether the operation was successful.
        """
        try:
            # Save short-term memory
            short_term_path = os.path.join(self.agent_memory_dir, "short_term.json")
            self.short_term.save_to_file(short_term_path)
            
            # Long-term memory is automatically persisted via the vector store
            # but we can trigger an explicit save
            self.long_term.save_to_disk()
            
            # Update last save time
            self.last_save_time = time.time()
            
            logger.info(f"Memory saved for agent {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving memory: {str(e)}")
            return False
    
    def load_memory(self) -> bool:
        """
        Load memory from disk.
        
        Returns:
            Whether the operation was successful.
        """
        try:
            # Load short-term memory
            short_term_path = os.path.join(self.agent_memory_dir, "short_term.json")
            if os.path.exists(short_term_path):
                loaded_short_term = ShortTermMemory.load_from_file(short_term_path)
                if loaded_short_term:
                    self.short_term = loaded_short_term
            
            # Long-term memory is loaded on initialization
            # No additional loading needed
            
            logger.info(f"Memory loaded for agent {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"Error loading memory: {str(e)}")
            return False
    
    def _check_auto_save(self) -> None:
        """Check if it's time to auto-save memory and save if needed."""
        current_time = time.time()
        elapsed = current_time - self.last_save_time
        
        if elapsed >= self.memory_saving_interval:
            self.save_memory()
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the agent's memory.
        
        Returns:
            Dictionary with memory statistics.
        """
        # Count conversation messages by role
        conversation_messages = self.short_term.conversation.messages
        message_counts = {}
        for message in conversation_messages:
            role = message.role
            message_counts[role] = message_counts.get(role, 0) + 1
        
        # Get working memory stats
        working_memory_count = len(self.short_term.working.keys())
        
        # Get long-term memory stats
        long_term_count = len(self.long_term.entries)
        entry_type_counts = {}
        for entry in self.long_term.entries.values():
            entry_type = entry.entry_type
            entry_type_counts[entry_type] = entry_type_counts.get(entry_type, 0) + 1
        
        return {
            "agent_id": self.agent_id,
            "short_term": {
                "conversation": {
                    "total_messages": len(conversation_messages),
                    "by_role": message_counts
                },
                "working_memory": {
                    "total_variables": working_memory_count
                }
            },
            "long_term": {
                "total_entries": long_term_count,
                "by_type": entry_type_counts
            },
            "last_save_time": self.last_save_time,
            "memory_saving_interval": self.memory_saving_interval
        } 