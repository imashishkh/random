"""
Long-Term Memory Module

This module implements persistent long-term memory for agents
using embedding-based vector storage for semantic retrieval.
"""

import os
import time
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from pathlib import Path

from ...utils.logging.logger import get_logger

logger = get_logger()

try:
    import openai
    from openai.embeddings_utils import get_embedding, cosine_similarity
    HAS_OPENAI = True
except ImportError:
    logger.warning("OpenAI package not found. LongTermMemory will use mock embeddings.")
    HAS_OPENAI = False


class MemoryEntry:
    """Represents a single memory entry in long-term memory."""
    
    def __init__(
        self,
        content: str,
        entry_type: str,
        entry_id: Optional[str] = None,
        importance: float = 0.5,
        timestamp: Optional[float] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a memory entry.
        
        Args:
            content: Text content of the memory.
            entry_type: Type of memory (fact, experience, etc.).
            entry_id: Unique ID for the memory (generates UUID if None).
            importance: Importance score (0.0 to 1.0).
            timestamp: Creation timestamp (uses current time if None).
            embedding: Vector embedding of content.
            metadata: Additional metadata.
        """
        self.content = content
        self.entry_type = entry_type
        self.entry_id = entry_id or str(uuid.uuid4())
        self.importance = max(0.0, min(1.0, importance))  # Clamp between 0 and 1
        self.timestamp = timestamp or time.time()
        self.embedding = embedding
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert memory entry to dictionary format.
        
        Returns:
            Dictionary representation of the memory entry.
        """
        return {
            "entry_id": self.entry_id,
            "content": self.content,
            "entry_type": self.entry_type,
            "importance": self.importance,
            "timestamp": self.timestamp,
            "embedding": self.embedding,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryEntry':
        """
        Create memory entry from dictionary.
        
        Args:
            data: Dictionary representation of memory entry.
            
        Returns:
            New MemoryEntry object.
        """
        return cls(
            content=data.get("content", ""),
            entry_type=data.get("entry_type", "unknown"),
            entry_id=data.get("entry_id"),
            importance=data.get("importance", 0.5),
            timestamp=data.get("timestamp"),
            embedding=data.get("embedding"),
            metadata=data.get("metadata", {})
        )


class LongTermMemory:
    """
    Long-term memory for agents using embedding-based storage.
    
    Stores information persistently and enables semantic search
    using vector embeddings for retrieval by relevance.
    """
    
    def __init__(
        self,
        agent_id: str,
        openai_api_key: Optional[str] = None,
        persistence_dir: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small"
    ):
        """
        Initialize long-term memory.
        
        Args:
            agent_id: Unique identifier for the agent.
            openai_api_key: OpenAI API key for embeddings.
            persistence_dir: Directory for storing memory.
            embedding_model: OpenAI embedding model to use.
        """
        self.agent_id = agent_id
        self.embedding_model = embedding_model
        self.entries: Dict[str, MemoryEntry] = {}
        
        # Set up OpenAI client if API key provided
        if openai_api_key:
            openai.api_key = openai_api_key
        
        # Set up persistence directory
        if persistence_dir:
            self.persistence_dir = Path(persistence_dir)
        else:
            home_dir = Path.home()
            self.persistence_dir = home_dir / ".agent_memory" / agent_id
        
        # Create directory if it doesn't exist
        self.persistence_dir.mkdir(parents=True, exist_ok=True)
        self.persistence_file = self.persistence_dir / "long_term_memory.json"
        
        # Load existing memories if available
        self._load()
        
        logger.info(f"Long-term memory initialized for agent {agent_id}")
    
    def add_entry(
        self,
        content: str,
        entry_type: str,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add new entry to long-term memory.
        
        Args:
            content: Text content of the memory.
            entry_type: Type of memory (fact, experience, etc.).
            importance: Importance score (0.0 to 1.0).
            metadata: Additional metadata.
            
        Returns:
            ID of the created memory entry.
        """
        if not content.strip():
            logger.warning("Attempted to add empty content to long-term memory")
            return ""
        
        # Generate embedding if OpenAI is available
        embedding = None
        if HAS_OPENAI and openai.api_key:
            try:
                embedding = self._get_embedding(content)
            except Exception as e:
                logger.error(f"Error generating embedding: {str(e)}")
        
        # Create new memory entry
        entry = MemoryEntry(
            content=content,
            entry_type=entry_type,
            importance=importance,
            embedding=embedding,
            metadata=metadata
        )
        
        # Store entry
        self.entries[entry.entry_id] = entry
        
        # Auto-save if enabled
        self.save()
        
        logger.debug(f"Added new entry to long-term memory: {entry.entry_id[:8]}")
        return entry.entry_id
    
    def get_entry(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a specific memory entry by ID.
        
        Args:
            entry_id: ID of the entry to retrieve.
            
        Returns:
            Memory entry or None if not found.
        """
        return self.entries.get(entry_id)
    
    def update_entry(
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
        entry = self.entries.get(entry_id)
        if not entry:
            logger.warning(f"Attempted to update non-existent entry: {entry_id}")
            return False
        
        # Update fields if provided
        if content is not None:
            entry.content = content
            
            # Update embedding if content changed
            if HAS_OPENAI and openai.api_key:
                try:
                    entry.embedding = self._get_embedding(content)
                except Exception as e:
                    logger.error(f"Error updating embedding: {str(e)}")
        
        if entry_type is not None:
            entry.entry_type = entry_type
            
        if importance is not None:
            entry.importance = max(0.0, min(1.0, importance))
            
        if metadata is not None:
            # Update metadata (don't replace completely)
            entry.metadata.update(metadata)
        
        # Auto-save
        self.save()
        
        return True
    
    def forget(self, entry_id: str) -> bool:
        """
        Remove entry from long-term memory.
        
        Args:
            entry_id: ID of entry to forget.
            
        Returns:
            Whether the entry was successfully removed.
        """
        if entry_id in self.entries:
            del self.entries[entry_id]
            self.save()
            logger.debug(f"Removed entry from long-term memory: {entry_id[:8]}")
            return True
        return False
    
    def search(
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
        if not self.entries:
            return []
        
        # Generate query embedding
        query_embedding = None
        if HAS_OPENAI and openai.api_key:
            try:
                query_embedding = self._get_embedding(query)
            except Exception as e:
                logger.error(f"Error generating query embedding: {str(e)}")
        
        # Filter entries by type and importance if specified
        filtered_entries = self.entries.values()
        
        if entry_type:
            filtered_entries = [entry for entry in filtered_entries 
                               if entry.entry_type == entry_type]
        
        if min_importance is not None:
            filtered_entries = [entry for entry in filtered_entries 
                               if entry.importance >= min_importance]
        
        # If no query embedding, return most important entries
        if query_embedding is None:
            sorted_entries = sorted(
                filtered_entries, 
                key=lambda entry: entry.importance, 
                reverse=True
            )
            results = [self._format_search_result(entry, 1.0) 
                      for entry in sorted_entries[:limit]]
            return results
        
        # Calculate similarity scores using embeddings
        entries_with_similarity = []
        for entry in filtered_entries:
            # Skip entries without embeddings
            if not entry.embedding:
                continue
                
            # Calculate similarity
            similarity = self._calculate_similarity(query_embedding, entry.embedding)
            
            # Filter by minimum similarity
            if similarity >= min_similarity:
                entries_with_similarity.append((entry, similarity))
        
        # Sort by similarity (descending)
        sorted_entries = sorted(
            entries_with_similarity,
            key=lambda x: x[1],
            reverse=True
        )
        
        # Format results
        results = [self._format_search_result(entry, score) 
                  for entry, score in sorted_entries[:limit]]
        
        return results
    
    def get_all_entries(self) -> List[MemoryEntry]:
        """
        Get all memory entries.
        
        Returns:
            List of all memory entries.
        """
        return list(self.entries.values())
    
    def clear(self) -> None:
        """Clear all memory entries."""
        self.entries = {}
        self.save()
        logger.info("Cleared all long-term memory entries")
    
    def save(self) -> bool:
        """
        Save memory to disk.
        
        Returns:
            Whether the save operation was successful.
        """
        try:
            # Convert entries to dictionaries
            entries_dict = {
                entry_id: entry.to_dict() 
                for entry_id, entry in self.entries.items()
            }
            
            # Save to file
            with open(self.persistence_file, 'w') as f:
                json.dump(entries_dict, f, indent=2)
                
            logger.debug(f"Saved {len(self.entries)} long-term memory entries to disk")
            return True
            
        except Exception as e:
            logger.error(f"Error saving long-term memory: {str(e)}")
            return False
    
    def _load(self) -> None:
        """Load memory from disk."""
        if not self.persistence_file.exists():
            logger.debug("No existing long-term memory file found")
            return
        
        try:
            with open(self.persistence_file, 'r') as f:
                entries_dict = json.load(f)
            
            # Convert dictionaries to MemoryEntry objects
            self.entries = {
                entry_id: MemoryEntry.from_dict(entry_data)
                for entry_id, entry_data in entries_dict.items()
            }
            
            logger.info(f"Loaded {len(self.entries)} long-term memory entries from disk")
            
        except Exception as e:
            logger.error(f"Error loading long-term memory: {str(e)}")
            self.entries = {}
    
    def _get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text using OpenAI API.
        
        Args:
            text: Text to embed.
            
        Returns:
            Vector embedding.
        """
        if not HAS_OPENAI:
            # Return mock embedding if OpenAI not available
            return self._generate_mock_embedding()
        
        try:
            response = openai.Embedding.create(
                input=text,
                model=self.embedding_model
            )
            embedding = response["data"][0]["embedding"]
            return embedding
        except Exception as e:
            logger.error(f"OpenAI embedding error: {str(e)}")
            return self._generate_mock_embedding()
    
    def _generate_mock_embedding(self, dim: int = 1536) -> List[float]:
        """
        Generate a fake embedding for testing without OpenAI.
        
        Args:
            dim: Embedding dimension.
            
        Returns:
            Random embedding vector.
        """
        # Generate random vector and normalize it
        vec = np.random.normal(0, 1, dim)
        norm = np.linalg.norm(vec)
        normalized = vec / norm
        return normalized.tolist()
    
    def _calculate_similarity(
        self, 
        embedding1: List[float], 
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector.
            embedding2: Second embedding vector.
            
        Returns:
            Cosine similarity score.
        """
        # Convert to numpy arrays
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Calculate cosine similarity
        if HAS_OPENAI:
            return cosine_similarity(vec1, vec2)
        else:
            # Manual calculation if openai.embeddings_utils not available
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            return dot_product / (norm1 * norm2)
    
    def _format_search_result(
        self, 
        entry: MemoryEntry, 
        similarity: float
    ) -> Dict[str, Any]:
        """
        Format memory entry for search results.
        
        Args:
            entry: Memory entry.
            similarity: Similarity score.
            
        Returns:
            Formatted result with entry data and similarity.
        """
        result = entry.to_dict()
        result["similarity"] = similarity
        
        # Remove embedding from result to reduce size
        if "embedding" in result:
            del result["embedding"]
            
        return result 