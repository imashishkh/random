"""
Model Registry Module
--------------------
Handles model versioning, registration, and promotion across environments.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

class ModelRegistry:
    """
    Registry for tracking ML model versions, metadata, and performance metrics.
    
    Handles model registration, versioning, promotion, and querying.
    """
    
    def __init__(self, registry_dir: str):
        """
        Initialize the model registry.
        
        Args:
            registry_dir: Directory for storing registry data
        """
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for different environments
        self.env_dirs = {
            env: self.registry_dir / env
            for env in ["dev", "staging", "production"]
        }
        
        for env_dir in self.env_dirs.values():
            env_dir.mkdir(exist_ok=True)
        
        # Path to the registry index file
        self.index_file = self.registry_dir / "registry_index.json"
        
        # Load or initialize registry index
        self.registry_index = self._load_registry_index()
    
    def _load_registry_index(self) -> Dict[str, Any]:
        """Load or initialize the registry index."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading registry index: {str(e)}")
        
        # Initialize empty registry
        return {
            "models": {},
            "last_updated": datetime.now().isoformat()
        }
    
    def _save_registry_index(self) -> None:
        """Save the registry index to disk."""
        try:
            self.registry_index["last_updated"] = datetime.now().isoformat()
            with open(self.index_file, "w") as f:
                json.dump(self.registry_index, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving registry index: {str(e)}")
    
    def register_model(
        self, 
        model_id: str,
        model_path: str,
        metadata: Dict[str, Any],
        metrics: Dict[str, float],
        environment: str = "dev"
    ) -> Dict[str, Any]:
        """
        Register a new model in the registry.
        
        Args:
            model_id: Unique identifier for the model
            model_path: Path to the model file
            metadata: Model metadata
            metrics: Model performance metrics
            environment: Target environment ("dev", "staging", "production")
            
        Returns:
            Dictionary with registration details
        """
        if environment not in self.env_dirs:
            raise ValueError(f"Invalid environment: {environment}")
        
        # Generate version
        existing_versions = []
        if model_id in self.registry_index["models"]:
            existing_versions = [
                v["version"] for v in self.registry_index["models"][model_id]["versions"]
            ]
        
        if not existing_versions:
            version = "1.0.0"
        else:
            # Increment minor version
            latest = sorted(existing_versions, key=lambda v: [int(x) for x in v.split(".")])[-1]
            major, minor, patch = [int(x) for x in latest.split(".")]
            version = f"{major}.{minor+1}.0"
        
        # Create registration timestamp
        timestamp = datetime.now().isoformat()
        
        # Create model directory in registry
        model_dir = self.env_dirs[environment] / f"{model_id}_v{version.replace('.', '_')}"
        model_dir.mkdir(exist_ok=True)
        
        # Copy model file to registry
        dest_path = model_dir / os.path.basename(model_path)
        shutil.copy2(model_path, dest_path)
        
        # Save metadata and metrics
        with open(model_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        
        with open(model_dir / "metrics.json", "w") as f:
            json.dump(metrics, f, indent=2)
        
        # Update registry index
        model_entry = {
            "version": version,
            "path": str(dest_path),
            "timestamp": timestamp,
            "environment": environment,
            "metrics": metrics,
            "metadata": metadata
        }
        
        if model_id not in self.registry_index["models"]:
            self.registry_index["models"][model_id] = {
                "current_versions": {env: None for env in self.env_dirs},
                "versions": []
            }
        
        self.registry_index["models"][model_id]["versions"].append(model_entry)
        self.registry_index["models"][model_id]["current_versions"][environment] = version
        
        # Save updated index
        self._save_registry_index()
        
        return {
            "model_id": model_id,
            "version": version,
            "path": str(dest_path),
            "environment": environment,
            "timestamp": timestamp
        }
    
    def promote_model(
        self,
        model_id: str,
        version: str,
        target_environment: str
    ) -> Dict[str, Any]:
        """
        Promote a model to a different environment.
        
        Args:
            model_id: Model identifier
            version: Model version
            target_environment: Target environment
            
        Returns:
            Promotion details
        """
        if target_environment not in self.env_dirs:
            raise ValueError(f"Invalid target environment: {target_environment}")
        
        if model_id not in self.registry_index["models"]:
            raise ValueError(f"Model not found: {model_id}")
        
        # Find the model version
        model_versions = self.registry_index["models"][model_id]["versions"]
        version_entry = None
        
        for entry in model_versions:
            if entry["version"] == version:
                version_entry = entry
                break
        
        if not version_entry:
            raise ValueError(f"Version not found: {version}")
        
        # Copy model to target environment
        source_path = Path(version_entry["path"])
        target_dir = self.env_dirs[target_environment] / f"{model_id}_v{version.replace('.', '_')}"
        target_dir.mkdir(exist_ok=True)
        
        target_path = target_dir / source_path.name
        shutil.copy2(source_path, target_path)
        
        # Copy metadata and metrics
        source_dir = source_path.parent
        shutil.copy2(source_dir / "metadata.json", target_dir / "metadata.json")
        shutil.copy2(source_dir / "metrics.json", target_dir / "metrics.json")
        
        # Update registry index
        promotion_entry = version_entry.copy()
        promotion_entry["path"] = str(target_path)
        promotion_entry["environment"] = target_environment
        promotion_entry["promotion_timestamp"] = datetime.now().isoformat()
        
        self.registry_index["models"][model_id]["versions"].append(promotion_entry)
        self.registry_index["models"][model_id]["current_versions"][target_environment] = version
        
        # Save updated index
        self._save_registry_index()
        
        return {
            "model_id": model_id,
            "version": version,
            "path": str(target_path),
            "environment": target_environment,
            "promotion_timestamp": promotion_entry["promotion_timestamp"]
        }
    
    def get_model(
        self, 
        model_id: str, 
        version: Optional[str] = None,
        environment: str = "production"
    ) -> Optional[Dict[str, Any]]:
        """
        Get information about a registered model.
        
        Args:
            model_id: Model identifier
            version: Specific version (optional)
            environment: Target environment
            
        Returns:
            Model information or None if not found
        """
        if model_id not in self.registry_index["models"]:
            return None
        
        model_info = self.registry_index["models"][model_id]
        
        # If version not specified, get the current version for the environment
        if not version:
            version = model_info["current_versions"].get(environment)
            if not version:
                return None
        
        # Find the specific version entry
        for entry in model_info["versions"]:
            if entry["version"] == version and entry["environment"] == environment:
                return entry
        
        return None
    
    def get_all_models(self, environment: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all registered models, optionally filtered by environment.
        
        Args:
            environment: Filter by environment
            
        Returns:
            List of model information
        """
        results = []
        
        for model_id, model_info in self.registry_index["models"].items():
            for version_entry in model_info["versions"]:
                if environment and version_entry["environment"] != environment:
                    continue
                
                entry = {
                    "model_id": model_id,
                    "version": version_entry["version"],
                    "environment": version_entry["environment"],
                    "path": version_entry["path"],
                    "timestamp": version_entry["timestamp"],
                    "metrics": version_entry["metrics"]
                }
                
                results.append(entry)
        
        return results
    
    def compare_models(
        self, 
        model_id: str, 
        version1: str, 
        version2: str
    ) -> Dict[str, Any]:
        """
        Compare metrics between two model versions.
        
        Args:
            model_id: Model identifier
            version1: First version
            version2: Second version
            
        Returns:
            Comparison results
        """
        model1 = self.get_model(model_id, version1)
        model2 = self.get_model(model_id, version2)
        
        if not model1 or not model2:
            raise ValueError("One or both model versions not found")
        
        metrics1 = model1["metrics"]
        metrics2 = model2["metrics"]
        
        # Calculate differences
        diff = {}
        for key in set(metrics1.keys()) | set(metrics2.keys()):
            val1 = metrics1.get(key, 0.0)
            val2 = metrics2.get(key, 0.0)
            
            if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                diff[key] = {
                    "v1": val1,
                    "v2": val2,
                    "diff": val2 - val1,
                    "pct_change": ((val2 - val1) / val1 * 100) if val1 != 0 else float('inf')
                }
        
        return {
            "model_id": model_id,
            "version1": version1,
            "version2": version2,
            "comparison": diff
        }

# Factory function to get registry instance
def get_model_registry(registry_dir: Optional[str] = None) -> ModelRegistry:
    """Get or create a model registry instance."""
    if not registry_dir:
        from src.utils.config import get_config
        config = get_config()
        registry_dir = config.get("model_registry_dir", "/opt/airflow/model_registry")
    
    return ModelRegistry(registry_dir) 