"""
State Persistence Module

This module provides mechanisms for persisting agent state to various storage backends,
enabling state to be saved and restored across sessions.
"""

import os
import json
import time
import pickle
from typing import Any, Dict, List, Optional, Union, cast
from abc import ABC, abstractmethod
import threading
from uuid import uuid4
import base64

from .state.base import BaseState, StateType
from ...utils.logging.logger import get_logger

# Get logger
logger = get_logger()


class StatePersistence(ABC):
    """
    Abstract base class for state persistence mechanisms.
    
    Implementations of this class provide storage backends for saving
    and loading agent states.
    """
    
    @abstractmethod
    def save_state(self, state: StateType, state_id: Optional[str] = None) -> str:
        """
        Save a state to storage.
        
        Args:
            state: The state to save.
            state_id: Optional ID for the state. If None, use thread_id or generate one.
            
        Returns:
            The ID used to save the state.
        """
        pass
    
    @abstractmethod
    def load_state(self, state_id: str) -> Optional[StateType]:
        """
        Load a state from storage.
        
        Args:
            state_id: The ID of the state to load.
            
        Returns:
            The loaded state, or None if not found.
        """
        pass
    
    @abstractmethod
    def delete_state(self, state_id: str) -> bool:
        """
        Delete a state from storage.
        
        Args:
            state_id: The ID of the state to delete.
            
        Returns:
            Whether the deletion was successful.
        """
        pass
    
    @abstractmethod
    def list_states(self, filter_params: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        List available state IDs.
        
        Args:
            filter_params: Optional parameters to filter the states.
            
        Returns:
            List of state IDs.
        """
        pass
    
    def _get_state_id(self, state: StateType, state_id: Optional[str] = None) -> str:
        """
        Get a state ID from the state or generate a new one.
        
        Args:
            state: The state.
            state_id: Optional explicit state ID.
            
        Returns:
            A state ID.
        """
        if state_id:
            return state_id
        elif "thread_id" in state and state["thread_id"]:
            return state["thread_id"]
        else:
            return str(uuid4())


class FileStatePersistence(StatePersistence):
    """
    File-based state persistence.
    
    This class provides a file-based storage backend for saving and loading
    agent states, useful for development, testing, and simple deployments.
    """
    
    def __init__(self, directory: str = "states", format: str = "json"):
        """
        Initialize file persistence.
        
        Args:
            directory: Directory to store state files.
            format: File format ("json" or "pickle").
        """
        self.directory = directory
        self.format = format
        
        # Ensure directory exists
        os.makedirs(directory, exist_ok=True)
        
        # Lock for thread-safe file operations
        self.file_lock = threading.Lock()
    
    def save_state(self, state: StateType, state_id: Optional[str] = None) -> str:
        """
        Save a state to a file.
        
        Args:
            state: The state to save.
            state_id: Optional ID for the state.
            
        Returns:
            The ID used to save the state.
        """
        state_id = self._get_state_id(state, state_id)
        
        # Add the ID to the state for reference
        if "thread_id" not in state or not state["thread_id"]:
            state["thread_id"] = state_id
        
        # Get filepath
        filepath = self._get_filepath(state_id)
        
        # Save to file with lock for thread safety
        with self.file_lock:
            try:
                if self.format == "json":
                    with open(filepath, "w") as f:
                        json.dump(state, f, indent=2)
                else:  # pickle
                    with open(filepath, "wb") as f:
                        pickle.dump(state, f)
                
                logger.info(f"State saved to {filepath}")
                return state_id
            except Exception as e:
                logger.error(f"Failed to save state: {str(e)}")
                raise
    
    def load_state(self, state_id: str) -> Optional[StateType]:
        """
        Load a state from a file.
        
        Args:
            state_id: The ID of the state to load.
            
        Returns:
            The loaded state, or None if not found.
        """
        filepath = self._get_filepath(state_id)
        
        # Check if file exists
        if not os.path.exists(filepath):
            logger.warning(f"State file not found: {filepath}")
            return None
        
        # Load from file with lock for thread safety
        with self.file_lock:
            try:
                if self.format == "json":
                    with open(filepath, "r") as f:
                        state = json.load(f)
                else:  # pickle
                    with open(filepath, "rb") as f:
                        state = pickle.load(f)
                
                logger.info(f"State loaded from {filepath}")
                return state
            except Exception as e:
                logger.error(f"Failed to load state: {str(e)}")
                return None
    
    def delete_state(self, state_id: str) -> bool:
        """
        Delete a state file.
        
        Args:
            state_id: The ID of the state to delete.
            
        Returns:
            Whether the deletion was successful.
        """
        filepath = self._get_filepath(state_id)
        
        # Check if file exists
        if not os.path.exists(filepath):
            logger.warning(f"State file not found for deletion: {filepath}")
            return False
        
        # Delete file with lock for thread safety
        with self.file_lock:
            try:
                os.remove(filepath)
                logger.info(f"State deleted: {filepath}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete state: {str(e)}")
                return False
    
    def list_states(self, filter_params: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        List available state IDs.
        
        Args:
            filter_params: Optional parameters to filter the states.
            
        Returns:
            List of state IDs.
        """
        try:
            # Get all files with the correct extension
            extension = ".json" if self.format == "json" else ".pickle"
            all_files = [f for f in os.listdir(self.directory) if f.endswith(extension)]
            
            # Extract state IDs from filenames
            state_ids = [f.replace(extension, "") for f in all_files]
            
            # Apply filters if provided
            if filter_params and state_ids:
                filtered_ids = []
                for state_id in state_ids:
                    state = self.load_state(state_id)
                    if state and self._matches_filters(state, filter_params):
                        filtered_ids.append(state_id)
                return filtered_ids
            else:
                return state_ids
        except Exception as e:
            logger.error(f"Failed to list states: {str(e)}")
            return []
    
    def _get_filepath(self, state_id: str) -> str:
        """
        Get the filepath for a state ID.
        
        Args:
            state_id: The state ID.
            
        Returns:
            The filepath.
        """
        # Clean the state ID to ensure it's a valid filename
        safe_id = "".join(c if c.isalnum() or c in "._-" else "_" for c in state_id)
        extension = ".json" if self.format == "json" else ".pickle"
        return os.path.join(self.directory, f"{safe_id}{extension}")
    
    def _matches_filters(self, state: StateType, filter_params: Dict[str, Any]) -> bool:
        """
        Check if a state matches filter parameters.
        
        Args:
            state: The state to check.
            filter_params: Filter parameters.
            
        Returns:
            Whether the state matches the filters.
        """
        for key, value in filter_params.items():
            if key == "agent_type" and "agent_type" in state:
                if state["agent_type"] != value:
                    return False
            elif key == "created_after" and "created_at" in state:
                if state["created_at"] < value:
                    return False
            elif key == "updated_after" and "updated_at" in state:
                if state["updated_at"] < value:
                    return False
            elif key == "metadata" and "metadata" in state:
                for mk, mv in value.items():
                    if mk not in state["metadata"] or state["metadata"][mk] != mv:
                        return False
        return True


class InMemoryStatePersistence(StatePersistence):
    """
    In-memory state persistence.
    
    This class provides an in-memory storage backend for saving and loading
    agent states, useful for testing and ephemeral use cases.
    """
    
    def __init__(self):
        """Initialize in-memory persistence."""
        self.states: Dict[str, BaseState] = {}
        self.memory_lock = threading.Lock()
    
    def save_state(self, state: StateType, state_id: Optional[str] = None) -> str:
        """
        Save a state to memory.
        
        Args:
            state: The state to save.
            state_id: Optional ID for the state.
            
        Returns:
            The ID used to save the state.
        """
        state_id = self._get_state_id(state, state_id)
        
        # Add the ID to the state for reference
        if "thread_id" not in state or not state["thread_id"]:
            state["thread_id"] = state_id
        
        # Save to memory with lock for thread safety
        with self.memory_lock:
            self.states[state_id] = state.copy()
        
        logger.info(f"State saved to memory with ID: {state_id}")
        return state_id
    
    def load_state(self, state_id: str) -> Optional[StateType]:
        """
        Load a state from memory.
        
        Args:
            state_id: The ID of the state to load.
            
        Returns:
            The loaded state, or None if not found.
        """
        # Load from memory with lock for thread safety
        with self.memory_lock:
            if state_id in self.states:
                state = self.states[state_id].copy()
                logger.info(f"State loaded from memory with ID: {state_id}")
                return state
            else:
                logger.warning(f"State not found in memory: {state_id}")
                return None
    
    def delete_state(self, state_id: str) -> bool:
        """
        Delete a state from memory.
        
        Args:
            state_id: The ID of the state to delete.
            
        Returns:
            Whether the deletion was successful.
        """
        # Delete from memory with lock for thread safety
        with self.memory_lock:
            if state_id in self.states:
                del self.states[state_id]
                logger.info(f"State deleted from memory: {state_id}")
                return True
            else:
                logger.warning(f"State not found for deletion: {state_id}")
                return False
    
    def list_states(self, filter_params: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        List available state IDs.
        
        Args:
            filter_params: Optional parameters to filter the states.
            
        Returns:
            List of state IDs.
        """
        # Get all state IDs with lock for thread safety
        with self.memory_lock:
            all_ids = list(self.states.keys())
            
            # Apply filters if provided
            if filter_params:
                return [
                    state_id for state_id in all_ids
                    if self._matches_filters(self.states[state_id], filter_params)
                ]
            else:
                return all_ids
    
    def _matches_filters(self, state: StateType, filter_params: Dict[str, Any]) -> bool:
        """
        Check if a state matches filter parameters.
        
        Args:
            state: The state to check.
            filter_params: Filter parameters.
            
        Returns:
            Whether the state matches the filters.
        """
        for key, value in filter_params.items():
            if key == "agent_type" and "agent_type" in state:
                if state["agent_type"] != value:
                    return False
            elif key == "created_after" and "created_at" in state:
                if state["created_at"] < value:
                    return False
            elif key == "updated_after" and "updated_at" in state:
                if state["updated_at"] < value:
                    return False
            elif key == "metadata" and "metadata" in state:
                for mk, mv in value.items():
                    if mk not in state["metadata"] or state["metadata"][mk] != mv:
                        return False
        return True


class StatePersistenceManager:
    """
    Manager for state persistence.
    
    This class provides a unified interface for saving and loading agent states
    using different storage backends.
    """
    
    def __init__(
        self,
        persistence: Optional[StatePersistence] = None,
        auto_save_enabled: bool = True,
        auto_save_interval: int = 60  # seconds
    ):
        """
        Initialize the persistence manager.
        
        Args:
            persistence: The persistence backend to use.
            auto_save_enabled: Whether to enable automatic saving.
            auto_save_interval: Interval for automatic saving in seconds.
        """
        # Use in-memory persistence by default
        self.persistence = persistence or InMemoryStatePersistence()
        
        # Auto-save settings
        self.auto_save_enabled = auto_save_enabled
        self.auto_save_interval = auto_save_interval
        
        # Auto-save tracking
        self.last_saved: Dict[str, float] = {}
        
        # Thread safety
        self.manager_lock = threading.Lock()
    
    def save_state(self, state: StateType, state_id: Optional[str] = None, force: bool = False) -> str:
        """
        Save a state using the configured persistence backend.
        
        Args:
            state: The state to save.
            state_id: Optional ID for the state.
            force: Whether to force saving even if not due.
            
        Returns:
            The ID used to save the state.
        """
        # Determine the state ID
        if state_id is None and "thread_id" in state and state["thread_id"]:
            state_id = state["thread_id"]
        
        # Check if auto-save is due or forced
        if not force and self.auto_save_enabled and state_id:
            # Check if we've saved this state before
            with self.manager_lock:
                last_save_time = self.last_saved.get(state_id, 0)
            
            # Check if it's time to save
            current_time = time.time()
            if current_time - last_save_time < self.auto_save_interval:
                logger.debug(f"Auto-save not due for state: {state_id}")
                return state_id
        
        # Save the state
        try:
            saved_id = self.persistence.save_state(state, state_id)
            
            # Update last saved time
            with self.manager_lock:
                self.last_saved[saved_id] = time.time()
            
            return saved_id
        except Exception as e:
            logger.error(f"Failed to save state: {str(e)}")
            raise
    
    def load_state(self, state_id: str) -> Optional[StateType]:
        """
        Load a state using the configured persistence backend.
        
        Args:
            state_id: The ID of the state to load.
            
        Returns:
            The loaded state, or None if not found.
        """
        try:
            return self.persistence.load_state(state_id)
        except Exception as e:
            logger.error(f"Failed to load state: {str(e)}")
            return None
    
    def delete_state(self, state_id: str) -> bool:
        """
        Delete a state using the configured persistence backend.
        
        Args:
            state_id: The ID of the state to delete.
            
        Returns:
            Whether the deletion was successful.
        """
        try:
            result = self.persistence.delete_state(state_id)
            
            # Remove from last saved tracking if successful
            if result:
                with self.manager_lock:
                    if state_id in self.last_saved:
                        del self.last_saved[state_id]
            
            return result
        except Exception as e:
            logger.error(f"Failed to delete state: {str(e)}")
            return False
    
    def list_states(self, filter_params: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        List available state IDs using the configured persistence backend.
        
        Args:
            filter_params: Optional parameters to filter the states.
            
        Returns:
            List of state IDs.
        """
        try:
            return self.persistence.list_states(filter_params)
        except Exception as e:
            logger.error(f"Failed to list states: {str(e)}")
            return []
    
    def set_auto_save(self, enabled: bool, interval: Optional[int] = None) -> None:
        """
        Configure auto-save behavior.
        
        Args:
            enabled: Whether to enable automatic saving.
            interval: Optional new interval for automatic saving in seconds.
        """
        self.auto_save_enabled = enabled
        if interval is not None:
            self.auto_save_interval = interval 