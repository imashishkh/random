"""
Dependency checker for boot process.

This module provides health check implementations for different service types,
used to verify service dependencies during system boot.
"""

import socket
import asyncio
import importlib
from typing import Dict, Any, Callable, Optional, Union
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

async def http_health_check(url: str, timeout: int = 5, 
                           expected_status: int = 200,
                           headers: Optional[Dict[str, str]] = None) -> bool:
    """
    Check health of a service via HTTP endpoint.
    
    Args:
        url: The HTTP endpoint URL to check
        timeout: Timeout in seconds
        expected_status: Expected HTTP status code for success
        headers: Optional HTTP headers to include in the request
        
    Returns:
        True if the service is healthy, False otherwise
    """
    headers = headers or {}
    try:
        # Import here to avoid requiring aiohttp for all users
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout, headers=headers) as response:
                return response.status == expected_status
    except ImportError:
        logger.error("aiohttp package is required for HTTP health checks")
        return False
    except Exception as e:
        logger.error(f"HTTP health check failed for {url}: {str(e)}")
        return False

async def tcp_health_check(host: str, port: int, timeout: int = 5) -> bool:
    """
    Check if a TCP port is open and accepting connections.
    
    Args:
        host: The hostname or IP address
        port: The TCP port to check
        timeout: Timeout in seconds
        
    Returns:
        True if the port is open, False otherwise
    """
    try:
        future = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(future, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as e:
        logger.error(f"TCP health check failed for {host}:{port}: {str(e)}")
        return False

def filesystem_health_check(path: Union[str, Path], 
                           check_writable: bool = False) -> bool:
    """
    Check if a filesystem path exists and is accessible.
    
    Args:
        path: Path to check
        check_writable: Whether to verify write access
        
    Returns:
        True if the path is accessible, False otherwise
    """
    path = Path(path)
    try:
        if not path.exists():
            logger.error(f"Path does not exist: {path}")
            return False
            
        if check_writable:
            if path.is_dir():
                # Try to create and remove a temp file
                test_file = path / ".health_check_test"
                test_file.touch()
                test_file.unlink()
            else:
                # Check if parent directory is writable
                if not path.parent.exists():
                    logger.error(f"Parent directory does not exist: {path.parent}")
                    return False
                # Try write access on the file
                with open(path, 'a'):
                    pass
        return True
    except (PermissionError, OSError) as e:
        logger.error(f"Filesystem health check failed for {path}: {str(e)}")
        return False

async def database_health_check(connection_string: str, 
                               driver_type: str = "sqlite",
                               timeout: int = 5) -> bool:
    """
    Check database connectivity.
    
    Args:
        connection_string: Database connection string
        driver_type: Database type (sqlite, postgresql, etc.)
        timeout: Timeout in seconds
        
    Returns:
        True if the database is accessible, False otherwise
    """
    try:
        if driver_type == "sqlite":
            import sqlite3
            conn = sqlite3.connect(connection_string)
            conn.execute("SELECT 1")
            conn.close()
            return True
        elif driver_type == "postgresql":
            # Import here to avoid requiring psycopg2 for all users
            import psycopg2
            conn = psycopg2.connect(connection_string)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            return True
        # Add other database types as needed
        else:
            logger.error(f"Unsupported database type: {driver_type}")
            return False
    except ImportError:
        logger.error(f"Required database driver for {driver_type} is not installed")
        return False
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return False

async def custom_health_check(check_path: str, **kwargs) -> bool:
    """
    Run a custom health check by importing and calling a function.
    
    Args:
        check_path: Import path in form "module.submodule.function"
        **kwargs: Additional arguments to pass to the check function
        
    Returns:
        True if the check passes, False otherwise
    """
    try:
        module_path, function_name = check_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        check_function = getattr(module, function_name)
        
        # Support both async and sync functions
        if asyncio.iscoroutinefunction(check_function):
            return await check_function(**kwargs)
        else:
            return check_function(**kwargs)
    except Exception as e:
        logger.error(f"Custom health check failed: {str(e)}")
        return False 