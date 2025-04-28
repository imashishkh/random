"""
File system dependency check for the Forex Trading system.

This module provides a dependency check for verifying the existence and 
permissions of critical directories and files required by the system.
"""

import os
import logging
import stat
import tempfile
from typing import Dict, Any, List, Tuple, Optional
import asyncio

from core.dependencies.checker import DependencyCheck, CheckResult, CheckStatus
from core.config import ConfigManager


logger = logging.getLogger(__name__)


class FileSystemCheck(DependencyCheck):
    """
    Dependency check for the file system.
    
    This check verifies that all required directories exist,
    have proper read/write permissions, and sufficient disk space.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the file system dependency check with configuration.
        
        Args:
            config_manager: The configuration manager containing file system paths and requirements.
        """
        super().__init__(
            name="filesystem",
            description="Checks for required directories and permissions",
            dependencies=[],
            priority=0  # Priority 0 as file system is fundamental
        )
        self.config_manager = config_manager
    
    def _get_fs_config(self) -> Dict[str, Any]:
        """
        Extract file system configuration from the config manager.
        
        Returns:
            Dictionary containing file system paths and requirements.
        """
        fs_config = self.config_manager.get("filesystem", {})
        
        # Default file system configuration if not specified
        default_config = {
            "directories": [
                {
                    "path": "data",
                    "required": True,
                    "permissions": "rw",
                    "check_writeable": True
                },
                {
                    "path": "logs",
                    "required": True,
                    "permissions": "rw",
                    "check_writeable": True
                },
                {
                    "path": "config",
                    "required": True,
                    "permissions": "r",
                    "check_writeable": False
                }
            ],
            "min_free_space_mb": 100,  # Minimum required free space in MB
            "check_disk_space": True
        }
        
        # Merge provided config with defaults
        for key, default_value in default_config.items():
            if key not in fs_config:
                fs_config[key] = default_value
        
        # Ensure paths are using the correct directory separator for the OS
        for dir_config in fs_config.get("directories", []):
            if "path" in dir_config:
                dir_config["path"] = os.path.normpath(dir_config["path"])
                
        return fs_config
    
    def _check_directory(self, dir_config: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check a single directory for existence and permissions.
        
        Args:
            dir_config: Directory configuration dictionary
            
        Returns:
            Tuple containing success status, message, and detailed results
        """
        path = dir_config.get("path")
        required = dir_config.get("required", True)
        permissions = dir_config.get("permissions", "r")
        check_writeable = dir_config.get("check_writeable", False)
        
        # Validate input
        if not path:
            return False, "No path specified for directory check", {"error": "Missing path"}
        
        # Get absolute path
        if not os.path.isabs(path):
            # Convert relative path to absolute based on current working directory
            abs_path = os.path.abspath(path)
        else:
            abs_path = path
        
        result = {
            "path": path,
            "absolute_path": abs_path,
            "required": required,
            "permissions_required": permissions
        }
        
        # Check if directory exists
        if not os.path.exists(abs_path):
            # Try to create directory if it's required and we need write access
            if required and 'w' in permissions:
                try:
                    os.makedirs(abs_path, exist_ok=True)
                    logger.info(f"Created required directory: {abs_path}")
                    result["created"] = True
                except Exception as e:
                    return False, f"Failed to create required directory {path}: {str(e)}", {
                        **result, 
                        "error": f"Creation failed: {str(e)}"
                    }
            else:
                msg = f"Directory does not exist: {path}"
                return (False, msg, {**result, "error": "Directory not found"}) if required else (
                    True, f"Optional directory {path} does not exist", {**result, "warning": "Directory not found"}
                )
        
        # Check if it's actually a directory
        if not os.path.isdir(abs_path):
            return False, f"Path exists but is not a directory: {path}", {
                **result, 
                "error": "Not a directory"
            }
        
        # Check read permissions
        if 'r' in permissions and not os.access(abs_path, os.R_OK):
            return False, f"Directory is not readable: {path}", {
                **result, 
                "error": "No read permission"
            }
        
        # Check write permissions if needed
        if 'w' in permissions and not os.access(abs_path, os.W_OK):
            return False, f"Directory is not writable: {path}", {
                **result, 
                "error": "No write permission"
            }
        
        # Check if it's actually writeable by attempting to create a temp file
        if check_writeable and 'w' in permissions:
            try:
                # Generate a unique filename in the directory
                fd, temp_path = tempfile.mkstemp(dir=abs_path)
                os.close(fd)
                
                # Check if the file was created
                if not os.path.exists(temp_path):
                    return False, f"Failed to create test file in directory: {path}", {
                        **result, 
                        "error": "Write test failed"
                    }
                
                # Clean up the temporary file
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file {temp_path}: {str(e)}")
                    result["warning"] = f"Cleanup failed: {str(e)}"
                
            except Exception as e:
                return False, f"Directory is not writeable (test failed): {path} - {str(e)}", {
                    **result, 
                    "error": f"Write test failed: {str(e)}"
                }
        
        # Check disk space if required
        if dir_config.get("check_disk_space", False):
            fs_config = self._get_fs_config()
            min_free_space_mb = fs_config.get("min_free_space_mb", 100)
            
            try:
                # Get disk usage statistics
                stat_result = os.statvfs(abs_path)
                free_bytes = stat_result.f_frsize * stat_result.f_bavail
                free_mb = free_bytes / (1024 * 1024)
                
                result["free_space_mb"] = round(free_mb, 1)
                
                if free_mb < min_free_space_mb:
                    return False, f"Insufficient disk space in {path}: {free_mb:.1f}MB free, {min_free_space_mb}MB required", {
                        **result, 
                        "error": "Insufficient disk space",
                        "min_required_mb": min_free_space_mb
                    }
                
                result["disk_space_ok"] = True
                
            except Exception as e:
                # Not critical, just log it and continue
                logger.warning(f"Failed to check disk space for {path}: {str(e)}")
                result["warning"] = f"Disk space check failed: {str(e)}"
        
        return True, f"Directory {path} exists with required permissions", result
    
    async def _check_directory_async(self, dir_config: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check a single directory asynchronously.
        
        Args:
            dir_config: Directory configuration dictionary
            
        Returns:
            Tuple containing success status, message, and detailed results
        """
        # For filesystem operations, we'll use the synchronous method
        # but run it in a thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._check_directory, dir_config)
    
    def run(self) -> CheckResult:
        """
        Run the file system dependency check synchronously.
        
        Returns:
            CheckResult: The result of the file system check.
        """
        fs_config = self._get_fs_config()
        directories = fs_config.get("directories", [])
        
        if not directories:
            logger.warning("No directories configured for file system check")
            return CheckResult(
                status=CheckStatus.WARNING,
                message="No directories configured for file system check",
                details={"directories_count": 0}
            )
        
        # Track check results
        all_results = []
        required_failures = []
        optional_failures = []
        warnings = []
        
        # Check each directory
        for dir_config in directories:
            dir_path = dir_config.get("path", "unknown")
            required = dir_config.get("required", True)
            
            success, message, details = self._check_directory(dir_config)
            
            # Store result
            result = {
                "path": dir_path,
                "success": success,
                "message": message,
                "required": required,
                "details": details
            }
            all_results.append(result)
            
            # Track failures and warnings
            if not success:
                if required:
                    required_failures.append(dir_path)
                else:
                    optional_failures.append(dir_path)
            elif "warning" in details:
                warnings.append(f"{dir_path}: {details['warning']}")
        
        # Determine overall status
        if required_failures:
            status = CheckStatus.FAILURE
            message = f"Failed file system checks for required directories: {', '.join(required_failures)}"
        elif optional_failures:
            status = CheckStatus.WARNING
            message = f"Failed file system checks for optional directories: {', '.join(optional_failures)}"
        elif warnings:
            status = CheckStatus.WARNING
            message = f"File system checks completed with warnings: {', '.join(warnings[:3])}" + (
                f" and {len(warnings) - 3} more" if len(warnings) > 3 else ""
            )
        else:
            status = CheckStatus.SUCCESS
            message = "All file system checks passed successfully"
        
        return CheckResult(
            status=status,
            message=message,
            details={
                "directories_checked": len(directories),
                "successful_checks": len(directories) - len(required_failures) - len(optional_failures),
                "required_failures": required_failures,
                "optional_failures": optional_failures,
                "warnings": warnings,
                "all_results": all_results
            }
        )
    
    async def run_async(self) -> CheckResult:
        """
        Run the file system dependency check asynchronously.
        
        Returns:
            CheckResult: The result of the file system check.
        """
        fs_config = self._get_fs_config()
        directories = fs_config.get("directories", [])
        
        if not directories:
            logger.warning("No directories configured for file system check")
            return CheckResult(
                status=CheckStatus.WARNING,
                message="No directories configured for file system check",
                details={"directories_count": 0}
            )
        
        # Track check results
        all_results = []
        required_failures = []
        optional_failures = []
        warnings = []
        
        # Create tasks for checking directories
        tasks = [self._check_directory_async(dir_config) for dir_config in directories]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            dir_config = directories[i]
            dir_path = dir_config.get("path", "unknown")
            required = dir_config.get("required", True)
            
            if isinstance(result, Exception):
                # Handle exceptions from the task
                success = False
                message = f"Error checking directory {dir_path}: {str(result)}"
                details = {"error": str(result), "exception_type": type(result).__name__}
            else:
                # Unpack normal results
                success, message, details = result
            
            # Store result
            dir_result = {
                "path": dir_path,
                "success": success,
                "message": message,
                "required": required,
                "details": details
            }
            all_results.append(dir_result)
            
            # Track failures and warnings
            if not success:
                if required:
                    required_failures.append(dir_path)
                else:
                    optional_failures.append(dir_path)
            elif "warning" in details:
                warnings.append(f"{dir_path}: {details['warning']}")
        
        # Determine overall status
        if required_failures:
            status = CheckStatus.FAILURE
            message = f"Failed file system checks for required directories: {', '.join(required_failures)}"
        elif optional_failures:
            status = CheckStatus.WARNING
            message = f"Failed file system checks for optional directories: {', '.join(optional_failures)}"
        elif warnings:
            status = CheckStatus.WARNING
            message = f"File system checks completed with warnings: {', '.join(warnings[:3])}" + (
                f" and {len(warnings) - 3} more" if len(warnings) > 3 else ""
            )
        else:
            status = CheckStatus.SUCCESS
            message = "All file system checks passed successfully"
        
        return CheckResult(
            status=status,
            message=message,
            details={
                "directories_checked": len(directories),
                "successful_checks": len(directories) - len(required_failures) - len(optional_failures),
                "required_failures": required_failures,
                "optional_failures": optional_failures,
                "warnings": warnings,
                "all_results": all_results
            }
        ) 