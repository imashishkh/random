"""
Model Server module for loading and serving machine learning models.

This module provides a class for managing models in memory and serving 
predictions. It handles model loading, activation, and provides
a simple interface for model inference.
"""

import os
import json
import shutil
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import importlib
import traceback

# Configure logger
logger = logging.getLogger(__name__)

class ModelServer:
    """
    ModelServer manages the lifecycle of machine learning models.
    
    This class handles loading models into memory, setting active models,
    and providing a unified interface for model inference.
    """
    
    def __init__(self, model_dir: str):
        """
        Initialize the ModelServer with a directory for models.
        
        Args:
            model_dir: Directory where models are stored
        """
        self.model_dir = model_dir
        self._ensure_model_dir()
        
        # Dictionary to store loaded models
        self.loaded_models: Dict[str, Any] = {}
        
        # Dictionary to store active model for each agent type
        self.active_models: Dict[str, str] = {}
        
        # Track model metadata
        self.model_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Load active model configuration if exists
        self._load_config()
        
        logger.info(f"ModelServer initialized with model directory: {model_dir}")
    
    def _ensure_model_dir(self) -> None:
        """Ensure the model directory exists."""
        os.makedirs(self.model_dir, exist_ok=True)
    
    def _get_config_path(self) -> str:
        """Get the path to the server configuration file."""
        return os.path.join(self.model_dir, "server_config.json")
    
    def _load_config(self) -> None:
        """Load the server configuration from file."""
        config_path = self._get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.active_models = config.get("active_models", {})
                    logger.info(f"Loaded server configuration with {len(self.active_models)} active models")
            except Exception as e:
                logger.error(f"Error loading server configuration: {str(e)}")
        else:
            logger.info("No server configuration found, creating new one")
            self._save_config()
    
    def _save_config(self) -> None:
        """Save the server configuration to file."""
        config_path = self._get_config_path()
        try:
            config = {
                "active_models": self.active_models,
                "updated_at": datetime.now().isoformat()
            }
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info("Saved server configuration")
        except Exception as e:
            logger.error(f"Error saving server configuration: {str(e)}")
    
    def load_model(self, model_id: str, model_path: str) -> bool:
        """
        Load a model into memory.
        
        Args:
            model_id: Unique identifier for the model
            model_path: Path to the model file or directory
            
        Returns:
            True if model loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(model_path):
                logger.error(f"Model path does not exist: {model_path}")
                return False
            
            # Extract agent type from model_id (e.g., "trend_following_1.0.0" -> "trend_following")
            agent_type = model_id.split('_')[0] if '_' in model_id else model_id
            
            # Load model metadata if available
            metadata_path = os.path.join(os.path.dirname(model_path), "metadata.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                self.model_metadata[model_id] = metadata
            
            # For demonstration purposes, we're just setting a placeholder
            # In a real implementation, this would use the appropriate loading
            # mechanism based on the model type (e.g., joblib, tensorflow, etc.)
            self.loaded_models[model_id] = {
                "model_path": model_path,
                "agent_type": agent_type,
                "loaded_at": datetime.now().isoformat()
            }
            
            logger.info(f"Successfully loaded model: {model_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading model {model_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def unload_model(self, model_id: str) -> bool:
        """
        Unload a model from memory.
        
        Args:
            model_id: Unique identifier for the model
            
        Returns:
            True if model unloaded successfully, False otherwise
        """
        if model_id not in self.loaded_models:
            logger.warning(f"Model {model_id} not loaded, cannot unload")
            return False
        
        try:
            # Remove active model reference if this model is active
            for agent_type, active_id in list(self.active_models.items()):
                if active_id == model_id:
                    del self.active_models[agent_type]
            
            # Remove from loaded models
            del self.loaded_models[model_id]
            if model_id in self.model_metadata:
                del self.model_metadata[model_id]
            
            # Update configuration
            self._save_config()
            
            logger.info(f"Successfully unloaded model: {model_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error unloading model {model_id}: {str(e)}")
            return False
    
    def set_active_model(self, model_id: str) -> bool:
        """
        Set a loaded model as the active model for its agent type.
        
        Args:
            model_id: Unique identifier for the model
            
        Returns:
            True if model set as active successfully, False otherwise
        """
        if model_id not in self.loaded_models:
            logger.error(f"Cannot set active model: {model_id} is not loaded")
            return False
        
        try:
            # Get agent type
            agent_type = self.loaded_models[model_id]["agent_type"]
            
            # Set as active model for this agent type
            self.active_models[agent_type] = model_id
            
            # Save configuration
            self._save_config()
            
            logger.info(f"Set {model_id} as active model for {agent_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting active model {model_id}: {str(e)}")
            return False
    
    def get_active_model(self, agent_type: str) -> Optional[str]:
        """
        Get the active model for an agent type.
        
        Args:
            agent_type: Type of agent
            
        Returns:
            Model ID if an active model exists, None otherwise
        """
        return self.active_models.get(agent_type)
    
    def predict(
        self, 
        agent_type: str, 
        input_data: Any,
        model_id: Optional[str] = None
    ) -> Optional[Any]:
        """
        Make a prediction using a model.
        
        Uses the active model for the agent type if model_id is not specified.
        
        Args:
            agent_type: Type of agent
            input_data: Input data for prediction
            model_id: Optional specific model ID to use
            
        Returns:
            Prediction result or None if an error occurs
        """
        # Determine which model to use
        if model_id is None:
            model_id = self.get_active_model(agent_type)
            if not model_id:
                logger.error(f"No active model set for agent type: {agent_type}")
                return None
        
        # Check if model is loaded
        if model_id not in self.loaded_models:
            logger.error(f"Model {model_id} is not loaded")
            return None
        
        try:
            # In a real implementation, this would call the model's predict method
            # For demonstration purposes, we return a placeholder prediction
            logger.info(f"Making prediction using model {model_id}")
            
            # Placeholder for prediction logic
            # In a real implementation, this would use the loaded model
            prediction_result = {
                "model_id": model_id,
                "timestamp": datetime.now().isoformat(),
                "prediction": "placeholder",  # This would be the actual prediction
                "input_shape": str(type(input_data))
            }
            
            return prediction_result
            
        except Exception as e:
            logger.error(f"Error making prediction with model {model_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a loaded model.
        
        Args:
            model_id: Unique identifier for the model
            
        Returns:
            Dictionary with model information or None if not found
        """
        if model_id not in self.loaded_models:
            return None
        
        info = self.loaded_models[model_id].copy()
        
        # Add metadata if available
        if model_id in self.model_metadata:
            info["metadata"] = self.model_metadata[model_id]
        
        # Add active status
        agent_type = info.get("agent_type")
        if agent_type:
            info["is_active"] = self.get_active_model(agent_type) == model_id
        
        return info
    
    def list_models(self, agent_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all loaded models, optionally filtered by agent type.
        
        Args:
            agent_type: Optional agent type to filter by
            
        Returns:
            List of model information dictionaries
        """
        result = []
        
        for model_id, model_info in self.loaded_models.items():
            if agent_type is None or model_info.get("agent_type") == agent_type:
                info = self.get_model_info(model_id)
                if info:
                    result.append(info)
        
        return result
    
    def get_model_metadata(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific model.
        
        Args:
            model_id: Unique identifier for the model
            
        Returns:
            Dictionary with model metadata or None if not found
        """
        return self.model_metadata.get(model_id) 