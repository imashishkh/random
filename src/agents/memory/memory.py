"""
Agent Memory System

This module integrates short-term and long-term memory for intelligent agents,
providing a complete memory system with conversation history, working memory,
and persistent knowledge storage with semantic retrieval capabilities.
"""

import os
import time
import json
from typing import Any, Dict, List, Optional, Tuple, Union

from .memory.short_term import ShortTermMemory, Message
from .memory.long_term import LongTermMemory, MemoryEntry
from ...utils.logging.logger import get_logger

logger = get_logger()


class AgentMemory:
    """
    Integrated memory system for intelligent agents.
    
    Combines short-term memory (conversation history and working memory) with
    long-term memory (persistent knowledge and experiences) to provide a
    complete memory system for agents.
    """
    
    def __init__(
        self,
        agent_id: str,
        openai_api_key: Optional[str] = None,
        persistence_dir: Optional[str] = None,
        max_conversation_messages: int = 100,
        consolidation_threshold: float = 0.7,
        embedding_model: str = "text-embedding-3-small"
    ):
        """
        Initialize the integrated agent memory system.
        
        Args:
            agent_id: Unique identifier for the agent.
            openai_api_key: OpenAI API key for embeddings.
            persistence_dir: Directory for persisting memory.
            max_conversation_messages: Maximum number of conversation messages to retain.
            consolidation_threshold: Importance threshold for consolidating to long-term memory.
            embedding_model: OpenAI embedding model to use.
        """
        self.agent_id = agent_id
        self.consolidation_threshold = consolidation_threshold
        
        # Set up persistence directory
        if persistence_dir:
            self.persistence_dir = persistence_dir
        else:
            home_dir = os.path.expanduser("~")
            self.persistence_dir = os.path.join(home_dir, ".agent_memory", agent_id)
        
        # Create directory if it doesn't exist
        os.makedirs(self.persistence_dir, exist_ok=True)
        
        # Initialize short-term and long-term memory
        self.short_term = ShortTermMemory(
            agent_id=agent_id,
            max_conversation_messages=max_conversation_messages,
            persistence_dir=self.persistence_dir
        )
        
        self.long_term = LongTermMemory(
            agent_id=agent_id,
            openai_api_key=openai_api_key,
            persistence_dir=self.persistence_dir,
            embedding_model=embedding_model
        )
        
        logger.info(f"Integrated memory system initialized for agent {agent_id}")
    
    def add_message(
        self,
        content: str,
        role: str,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        auto_consolidate: bool = True
    ) -> str:
        """
        Add a message to conversation history.
        
        Args:
            content: Message content.
            role: Message role (user, assistant, system).
            importance: Message importance (0.0 to 1.0).
            metadata: Additional metadata.
            auto_consolidate: Whether to automatically consolidate important messages.
            
        Returns:
            ID of the created message.
        """
        # Add to short-term memory
        metadata = metadata or {}
        metadata["importance"] = importance
        message_id = self.short_term.add_message(content, role, metadata)
        
        # Consolidate to long-term memory if important enough
        if auto_consolidate and importance >= self.consolidation_threshold:
            self._consolidate_memory(content, role, importance, metadata)
        
        return message_id
    
    def set_working_memory(self, key: str, value: Any) -> None:
        """
        Set a value in working memory.
        
        Args:
            key: Memory key.
            value: Memory value.
        """
        self.short_term.set_working_memory(key, value)
    
    def get_working_memory(self, key: str, default: Any = None) -> Any:
        """
        Get a value from working memory.
        
        Args:
            key: Memory key.
            default: Default value if key not found.
            
        Returns:
            Stored value or default.
        """
        return self.short_term.get_working_memory(key, default)
    
    def delete_working_memory(self, key: str) -> bool:
        """
        Delete a value from working memory.
        
        Args:
            key: Memory key to delete.
            
        Returns:
            Whether the key was deleted.
        """
        return self.short_term.delete_working_memory(key)
    
    def clear_working_memory(self) -> None:
        """Clear all working memory."""
        self.short_term.clear_working_memory()
    
    def get_all_working_memory(self) -> Dict[str, Any]:
        """
        Get all working memory.
        
        Returns:
            Dictionary of all working memory.
        """
        return self.short_term.get_all_working_memory()
    
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
        return self.short_term.get_conversation_history(
            max_messages=max_messages,
            roles=roles,
            min_timestamp=min_timestamp,
            reverse=reverse
        )
    
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
        return self.short_term.get_llm_messages(
            max_messages=max_messages,
            include_system=include_system
        )
    
    def clear_conversation(self) -> None:
        """Clear conversation history."""
        self.short_term.clear_conversation()
    
    def add_to_long_term_memory(
        self,
        content: str,
        entry_type: str,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add an entry to long-term memory.
        
        Args:
            content: Text content of the memory.
            entry_type: Type of memory (fact, experience, etc.).
            importance: Importance score (0.0 to 1.0).
            metadata: Additional metadata.
            
        Returns:
            ID of the created memory entry.
        """
        return self.long_term.add_entry(
            content=content,
            entry_type=entry_type,
            importance=importance,
            metadata=metadata
        )
    
    def get_long_term_entry(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a specific memory entry by ID.
        
        Args:
            entry_id: ID of the entry to retrieve.
            
        Returns:
            Memory entry or None if not found.
        """
        return self.long_term.get_entry(entry_id)
    
    def search_long_term_memory(
        self,
        query: str,
        limit: int = 5,
        entry_type: Optional[str] = None,
        min_importance: Optional[float] = None,
        min_similarity: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search long-term memory by semantic similarity.
        
        Args:
            query: Search query.
            limit: Maximum entries to retrieve.
            entry_type: Filter by entry type.
            min_importance: Minimum importance threshold.
            min_similarity: Minimum similarity score threshold.
            
        Returns:
            List of relevant memory entries with similarity scores.
        """
        return self.long_term.search(
            query=query,
            limit=limit,
            entry_type=entry_type,
            min_importance=min_importance,
            min_similarity=min_similarity
        )
    
    def update_long_term_entry(
        self,
        entry_id: str,
        content: Optional[str] = None,
        entry_type: Optional[str] = None,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update an existing memory entry.
        
        Args:
            entry_id: ID of the entry to update.
            content: New content (if None, keeps existing).
            entry_type: New type (if None, keeps existing).
            importance: New importance (if None, keeps existing).
            metadata: New metadata (if None, keeps existing).
            
        Returns:
            Whether the update was successful.
        """
        return self.long_term.update_entry(
            entry_id=entry_id,
            content=content,
            entry_type=entry_type,
            importance=importance,
            metadata=metadata
        )
    
    def forget_long_term_entry(self, entry_id: str) -> bool:
        """
        Remove entry from long-term memory.
        
        Args:
            entry_id: ID of entry to forget.
            
        Returns:
            Whether the entry was successfully removed.
        """
        return self.long_term.forget(entry_id)
    
    def retrieve_relevant_memories(
        self,
        context: str,
        limit: int = 3,
        entry_types: Optional[List[str]] = None,
        min_importance: float = 0.0,
        min_similarity: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories relevant to the current context.
        
        Args:
            context: Current context to find relevant memories for.
            limit: Maximum number of memories to retrieve.
            entry_types: Types of memories to include.
            min_importance: Minimum importance threshold.
            min_similarity: Minimum similarity threshold.
            
        Returns:
            List of relevant memories with similarity scores.
        """
        memories = []
        
        # Search for each type if specified
        if entry_types:
            remaining = limit
            per_type = max(1, limit // len(entry_types))
            
            for entry_type in entry_types:
                type_limit = min(per_type, remaining)
                type_memories = self.long_term.search(
                    query=context,
                    limit=type_limit,
                    entry_type=entry_type,
                    min_importance=min_importance,
                    min_similarity=min_similarity
                )
                
                memories.extend(type_memories)
                remaining -= len(type_memories)
                
                # Stop if we've reached the limit
                if remaining <= 0:
                    break
        else:
            # Search across all types
            memories = self.long_term.search(
                query=context,
                limit=limit,
                min_importance=min_importance,
                min_similarity=min_similarity
            )
        
        return memories
    
    def augment_context_with_memories(
        self,
        context: str,
        limit: int = 3,
        entry_types: Optional[List[str]] = None,
        prefix: str = "Relevant memories:",
        min_similarity: float = 0.6
    ) -> str:
        """
        Augment a context string with relevant memories.
        
        Args:
            context: Current context to augment.
            limit: Maximum number of memories to include.
            entry_types: Types of memories to include.
            prefix: Text to prepend to the memories section.
            min_similarity: Minimum similarity threshold.
            
        Returns:
            Augmented context string.
        """
        # Retrieve relevant memories
        memories = self.retrieve_relevant_memories(
            context=context,
            limit=limit,
            entry_types=entry_types,
            min_similarity=min_similarity
        )
        
        # If no memories found, return original context
        if not memories:
            return context
        
        # Format memories
        memories_text = "\n\n" + prefix + "\n"
        for i, memory in enumerate(memories, 1):
            sim = memory.get("similarity", 0)
            memories_text += f"{i}. [{memory['entry_type']}] {memory['content']} (relevance: {sim:.2f})\n"
        
        # Append to context
        return context + memories_text
    
    def save(self) -> bool:
        """
        Save memory to disk.
        
        Returns:
            Whether both save operations were successful.
        """
        short_term_saved = self.short_term.save()
        long_term_saved = self.long_term.save()
        return short_term_saved and long_term_saved
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get memory statistics.
        
        Returns:
            Dictionary with memory statistics.
        """
        # Get counts from both memory systems
        short_term_msg_count = len(self.short_term.conversation)
        working_memory_count = len(self.short_term.working_memory)
        long_term_entry_count = len(self.long_term.entries)
        
        # Count by entry type
        entry_type_counts = {}
        for entry in self.long_term.entries.values():
            entry_type = entry.entry_type
            entry_type_counts[entry_type] = entry_type_counts.get(entry_type, 0) + 1
        
        return {
            "short_term_messages": short_term_msg_count,
            "working_memory_items": working_memory_count,
            "long_term_entries": long_term_entry_count,
            "long_term_by_type": entry_type_counts,
        }
    
    def _consolidate_memory(
        self,
        content: str,
        role: str,
        importance: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Consolidate an important message to long-term memory.
        
        Args:
            content: Message content.
            role: Message role.
            importance: Message importance.
            metadata: Message metadata.
            
        Returns:
            ID of the created long-term memory entry, or None on failure.
        """
        try:
            # Determine memory entry type based on role
            if role == "system":
                entry_type = "instruction"
            elif role == "user":
                entry_type = "user_input"
            elif role == "assistant":
                entry_type = "response"
            else:
                entry_type = "message"
            
            # Add role to metadata
            metadata = metadata or {}
            metadata["message_role"] = role
            
            # Add to long-term memory
            entry_id = self.long_term.add_entry(
                content=content,
                entry_type=entry_type,
                importance=importance,
                metadata=metadata
            )
            
            logger.debug(f"Consolidated important message to long-term memory: {entry_id[:8]}")
            return entry_id
            
        except Exception as e:
            logger.error(f"Error consolidating memory: {str(e)}")
            return None 