"""
Service-specific dependency checks.

This module provides concrete implementations of DependencyCheck for
various services and resources that the trading system depends on.
"""
import os
import socket
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import logging
from urllib.parse import urlparse

from .base import DependencyCheck, CheckResult, CheckStatus

logger = logging.getLogger(__name__)


class ServiceCheck(DependencyCheck):
    """
    Base class for checking if a service is available.
    
    This is a common parent class for service-specific checks
    that provides a consistent interface and naming convention.
    """
    def __init__(self, name: str, service_name: str, **kwargs):
        """
        Initialize a service check.
        
        Args:
            name: Unique identifier for the check
            service_name: Human-readable name of the service
            **kwargs: Additional arguments for DependencyCheck
        """
        description = kwargs.pop("description", f"Check if {service_name} is available")
        super().__init__(name, description=description, **kwargs)
        self.service_name = service_name


class RedisCheck(ServiceCheck):
    """Check if Redis is available and responsive."""
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str = None,
        db: int = 0,
        **kwargs
    ):
        """
        Initialize a Redis check.
        
        Args:
            host: Redis host
            port: Redis port
            password: Redis password
            db: Redis database number
            **kwargs: Additional arguments for ServiceCheck
        """
        name = kwargs.pop("name", f"redis-{host}:{port}")
        super().__init__(name, "Redis", **kwargs)
        self.host = host
        self.port = port
        self.password = password
        self.db = db
    
    def _execute_check(self) -> CheckResult:
        """Execute the Redis check."""
        try:
            # Import here to avoid requiring redis for the whole module
            import redis
            
            client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                socket_timeout=5
            )
            # Simple ping to check connection
            response = client.ping()
            if response:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.SUCCESS,
                    message="Redis is available",
                    details={"host": self.host, "port": self.port}
                )
            else:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.FAILURE,
                    message="Redis ping failed",
                    details={"host": self.host, "port": self.port}
                )
        except ImportError:
            logger.exception("Redis package not installed")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message="Redis package not installed. Run 'pip install redis'",
                details={"error": "ImportError: No module named 'redis'"}
            )
        except Exception as e:
            logger.exception(f"Redis check failed: {e}")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"Redis connection failed: {str(e)}",
                details={"host": self.host, "port": self.port, "error": str(e)}
            )


class PostgresCheck(ServiceCheck):
    """Check if PostgreSQL database is available and responsive."""
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = None,
        database: str = "postgres",
        required_tables: List[str] = None,
        **kwargs
    ):
        """
        Initialize a PostgreSQL check.
        
        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            user: PostgreSQL user
            password: PostgreSQL password
            database: PostgreSQL database name
            required_tables: List of tables that must exist
            **kwargs: Additional arguments for ServiceCheck
        """
        name = kwargs.pop("name", f"postgres-{host}:{port}/{database}")
        super().__init__(name, "PostgreSQL", **kwargs)
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.required_tables = required_tables or []
    
    def _execute_check(self) -> CheckResult:
        """Execute the PostgreSQL check."""
        details = {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user
        }
        
        try:
            # Import here to avoid requiring psycopg2 for the whole module
            import psycopg2
            
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=10
            )
            
            # Check server version
            with conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]
                details["version"] = version
            
            # Check required tables if specified
            if self.required_tables:
                missing_tables = []
                with conn.cursor() as cursor:
                    for table in self.required_tables:
                        cursor.execute(
                            "SELECT EXISTS (SELECT FROM information_schema.tables "
                            "WHERE table_schema = 'public' AND table_name = %s);",
                            (table,)
                        )
                        exists = cursor.fetchone()[0]
                        if not exists:
                            missing_tables.append(table)
                
                if missing_tables:
                    details["missing_tables"] = missing_tables
                    return CheckResult(
                        name=self.name,
                        status=CheckStatus.FAILURE,
                        message=f"Missing required tables: {', '.join(missing_tables)}",
                        details=details
                    )
            
            conn.close()
            return CheckResult(
                name=self.name,
                status=CheckStatus.SUCCESS,
                message="PostgreSQL database is available",
                details=details
            )
        except ImportError:
            logger.exception("psycopg2 package not installed")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message="psycopg2 package not installed. Run 'pip install psycopg2-binary'",
                details={"error": "ImportError: No module named 'psycopg2'"}
            )
        except Exception as e:
            logger.exception(f"PostgreSQL check failed: {e}")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"PostgreSQL connection failed: {str(e)}",
                details={**details, "error": str(e)}
            )


class ApiCheck(DependencyCheck):
    """Check if an API endpoint is available and responding correctly."""
    def __init__(
        self,
        url: str,
        method: str = "GET",
        headers: dict = None,
        params: dict = None,
        data: dict = None,
        expected_status: int = 200,
        timeout: int = 10,
        **kwargs
    ):
        """
        Initialize an API check.
        
        Args:
            url: API endpoint URL
            method: HTTP method
            headers: HTTP headers
            params: Query parameters
            data: Request body data
            expected_status: Expected HTTP status code
            timeout: Request timeout in seconds
            **kwargs: Additional arguments for DependencyCheck
        """
        parsed_url = urlparse(url)
        name = kwargs.pop("name", f"api-{parsed_url.netloc}")
        description = kwargs.pop("description", f"Check if API at {parsed_url.netloc} is available")
        super().__init__(name, description=description, **kwargs)
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.params = params or {}
        self.data = data or {}
        self.expected_status = expected_status
        self.timeout = timeout
    
    def _execute_check(self) -> CheckResult:
        """Execute the API check."""
        try:
            # Import here to avoid requiring requests for the whole module
            import requests
            
            response = requests.request(
                self.method,
                self.url,
                headers=self.headers,
                params=self.params,
                json=self.data if self.method in ["POST", "PUT", "PATCH"] else None,
                timeout=self.timeout
            )
            
            if response.status_code == self.expected_status:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.SUCCESS,
                    message=f"API responded with status {response.status_code}",
                    details={
                        "url": self.url,
                        "method": self.method,
                        "status_code": response.status_code,
                        "response_time_ms": response.elapsed.total_seconds() * 1000
                    }
                )
            else:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.FAILURE,
                    message=f"API responded with unexpected status {response.status_code}, expected {self.expected_status}",
                    details={
                        "url": self.url,
                        "method": self.method,
                        "status_code": response.status_code,
                        "expected_status": self.expected_status,
                        "response_body": response.text[:1000] if response.text else None
                    }
                )
        except ImportError:
            logger.exception("requests package not installed")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message="requests package not installed. Run 'pip install requests'",
                details={"error": "ImportError: No module named 'requests'"}
            )
        except Exception as e:
            logger.exception(f"API check failed: {e}")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"API request failed: {str(e)}",
                details={
                    "url": self.url,
                    "method": self.method,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
    
    async def execute_async(self) -> CheckResult:
        """
        Native async implementation for API checks.
        
        This overrides the default thread pool implementation with
        a native async implementation using aiohttp.
        """
        try:
            # Import here to avoid requiring aiohttp for the whole module
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                method = getattr(session, self.method.lower())
                async with method(
                    self.url,
                    headers=self.headers,
                    params=self.params,
                    json=self.data if self.method in ["POST", "PUT", "PATCH"] else None,
                    timeout=self.timeout
                ) as response:
                    if response.status == self.expected_status:
                        return CheckResult(
                            name=self.name,
                            status=CheckStatus.SUCCESS,
                            message=f"API responded with status {response.status}",
                            details={
                                "url": self.url,
                                "method": self.method,
                                "status_code": response.status
                            }
                        )
                    else:
                        body = await response.text()
                        return CheckResult(
                            name=self.name,
                            status=CheckStatus.FAILURE,
                            message=f"API responded with unexpected status {response.status}, expected {self.expected_status}",
                            details={
                                "url": self.url,
                                "method": self.method,
                                "status_code": response.status,
                                "expected_status": self.expected_status,
                                "response_body": body[:1000] if body else None
                            }
                        )
        except ImportError:
            logger.exception("aiohttp package not installed")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message="aiohttp package not installed. Run 'pip install aiohttp'",
                details={"error": "ImportError: No module named 'aiohttp'"}
            )
        except Exception as e:
            logger.exception(f"Async API check failed: {e}")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"Async API request failed: {str(e)}",
                details={
                    "url": self.url,
                    "method": self.method,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )


class BinanceApiCheck(ApiCheck):
    """Check if Binance API is available and responding correctly."""
    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        base_url: str = "https://api.binance.com",
        futures_url: str = "https://fapi.binance.com",
        **kwargs
    ):
        """
        Initialize a Binance API check.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            base_url: Binance API base URL
            futures_url: Binance Futures API base URL
            **kwargs: Additional arguments for ApiCheck
        """
        name = kwargs.pop("name", "binance-api")
        description = kwargs.pop("description", "Check if Binance API is available")
        # Start with a simple ping endpoint for basic check
        super().__init__(
            url=f"{base_url}/api/v3/ping",
            name=name,
            description=description,
            **kwargs
        )
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.futures_url = futures_url
        self.endpoints = [
            {"url": f"{base_url}/api/v3/ping", "name": "spot_ping"},
            {"url": f"{futures_url}/fapi/v1/ping", "name": "futures_ping"}
        ]
        # Add authenticated endpoint if credentials provided
        if api_key:
            self.endpoints.append({
                "url": f"{base_url}/api/v3/account",
                "name": "spot_account",
                "auth": True
            })
            self.endpoints.append({
                "url": f"{futures_url}/fapi/v2/account",
                "name": "futures_account",
                "auth": True
            })
    
    def _execute_check(self) -> CheckResult:
        """Execute checks for all Binance endpoints."""
        try:
            import requests
            import hmac
            import hashlib
            import time
            
            errors = []
            details = {"endpoints_checked": len(self.endpoints), "failures": 0}
            
            for endpoint in self.endpoints:
                url = endpoint["url"]
                try:
                    headers = {}
                    params = {}
                    
                    # Add authentication if needed
                    if endpoint.get("auth") and self.api_key and self.api_secret:
                        headers["X-MBX-APIKEY"] = self.api_key
                        
                        # Add timestamp and signature for auth endpoints
                        timestamp = int(time.time() * 1000)
                        params["timestamp"] = timestamp
                        
                        # Create signature
                        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
                        signature = hmac.new(
                            self.api_secret.encode("utf-8"),
                            query_string.encode("utf-8"),
                            hashlib.sha256
                        ).hexdigest()
                        params["signature"] = signature
                    
                    response = requests.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        details[endpoint["name"]] = "Success"
                    else:
                        errors.append(f"Endpoint {endpoint['name']} returned status {response.status_code}")
                        details[endpoint["name"]] = f"Failed with status {response.status_code}"
                        details["failures"] += 1
                except Exception as e:
                    errors.append(f"Failed to connect to {endpoint['name']}: {str(e)}")
                    details[endpoint["name"]] = f"Exception: {str(e)}"
                    details["failures"] += 1
            
            if errors:
                status = CheckStatus.FAILURE if details["failures"] == len(self.endpoints) else CheckStatus.WARNING
                message = f"Binance API check issues: {'; '.join(errors[:2])}"
                if len(errors) > 2:
                    message += f"... and {len(errors) - 2} more issues"
                return CheckResult(
                    name=self.name,
                    status=status,
                    message=message,
                    details=details
                )
            else:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.SUCCESS,
                    message="All Binance API endpoints are available",
                    details=details
                )
        except ImportError:
            logger.exception("Required packages not installed")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message="Required packages not installed. Run 'pip install requests'",
                details={"error": "ImportError: Missing required packages"}
            )
        except Exception as e:
            logger.exception(f"Binance API check failed: {e}")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"Binance API check failed: {str(e)}",
                details={"error": str(e)}
            )


class FileSystemCheck(DependencyCheck):
    """Check if filesystem resources are available and accessible."""
    def __init__(
        self,
        path: str,
        check_type: str = "exists",
        check_permissions: str = None,
        min_free_space_mb: int = None,
        create_if_missing: bool = False,
        **kwargs
    ):
        """
        Initialize a filesystem check.
        
        Args:
            path: Path to check
            check_type: One of "exists", "file", "directory"
            check_permissions: String containing "r", "w", "x" for read/write/execute
            min_free_space_mb: Minimum required free space in MB
            create_if_missing: Whether to create the path if it doesn't exist
            **kwargs: Additional arguments for DependencyCheck
        """
        name = kwargs.pop("name", f"fs-{os.path.basename(path)}")
        description = kwargs.pop("description", f"Check if {path} exists and is accessible")
        super().__init__(name, description=description, **kwargs)
        self.path = Path(path)
        self.check_type = check_type
        self.check_permissions = check_permissions
        self.min_free_space_mb = min_free_space_mb
        self.create_if_missing = create_if_missing
    
    def _execute_check(self) -> CheckResult:
        """Execute the filesystem check."""
        details = {"path": str(self.path.absolute())}
        
        # Check if path exists
        if not self.path.exists():
            if self.create_if_missing:
                try:
                    if self.check_type == "directory":
                        self.path.mkdir(parents=True, exist_ok=True)
                        details["created"] = True
                    elif self.check_type == "file":
                        self.path.parent.mkdir(parents=True, exist_ok=True)
                        self.path.touch(exist_ok=True)
                        details["created"] = True
                    else:
                        return CheckResult(
                            name=self.name,
                            status=CheckStatus.FAILURE,
                            message=f"Cannot create path of unknown type: {self.check_type}",
                            details=details
                        )
                except Exception as e:
                    logger.exception(f"Failed to create {self.path}: {e}")
                    return CheckResult(
                        name=self.name,
                        status=CheckStatus.FAILURE,
                        message=f"Failed to create {self.path}: {str(e)}",
                        details=details
                    )
            else:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.FAILURE,
                    message=f"Path does not exist: {self.path}",
                    details=details
                )
        
        # Check type
        if self.check_type == "file" and not self.path.is_file():
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"Path is not a file: {self.path}",
                details=details
            )
        elif self.check_type == "directory" and not self.path.is_dir():
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"Path is not a directory: {self.path}",
                details=details
            )
        
        # Check permissions
        if self.check_permissions:
            details["permissions"] = {}
            
            try:
                if "r" in self.check_permissions:
                    readable = os.access(self.path, os.R_OK)
                    details["permissions"]["read"] = readable
                    if not readable:
                        return CheckResult(
                            name=self.name,
                            status=CheckStatus.FAILURE,
                            message=f"No read permission for {self.path}",
                            details=details
                        )
                
                if "w" in self.check_permissions:
                    writable = os.access(self.path, os.W_OK)
                    details["permissions"]["write"] = writable
                    if not writable:
                        return CheckResult(
                            name=self.name,
                            status=CheckStatus.FAILURE,
                            message=f"No write permission for {self.path}",
                            details=details
                        )
                
                if "x" in self.check_permissions:
                    executable = os.access(self.path, os.X_OK)
                    details["permissions"]["execute"] = executable
                    if not executable:
                        return CheckResult(
                            name=self.name,
                            status=CheckStatus.FAILURE,
                            message=f"No execute permission for {self.path}",
                            details=details
                        )
            except Exception as e:
                logger.exception(f"Permission check failed: {e}")
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.FAILURE,
                    message=f"Permission check failed: {str(e)}",
                    details=details
                )
        
        # Check free space if requested
        if self.min_free_space_mb is not None:
            try:
                free_bytes = shutil.disk_usage(self.path).free
                free_mb = free_bytes / (1024 * 1024)
                details["free_space_mb"] = free_mb
                
                if free_mb < self.min_free_space_mb:
                    return CheckResult(
                        name=self.name,
                        status=CheckStatus.WARNING,
                        message=f"Low disk space: {free_mb:.1f}MB free, {self.min_free_space_mb}MB required",
                        details=details
                    )
            except Exception as e:
                logger.exception(f"Disk space check failed: {e}")
                details["free_space_error"] = str(e)
        
        return CheckResult(
            name=self.name,
            status=CheckStatus.SUCCESS,
            message=f"Filesystem check passed for {self.path}",
            details=details
        )


class PortCheck(DependencyCheck):
    """Check if a network port is available or in use."""
    def __init__(
        self,
        host: str,
        port: int,
        expect_available: bool = False,
        **kwargs
    ):
        """
        Initialize a port check.
        
        Args:
            host: Hostname or IP address
            port: Port number
            expect_available: If True, expect the port to be available (not in use)
                             If False, expect the port to be in use
            **kwargs: Additional arguments for DependencyCheck
        """
        name = kwargs.pop("name", f"port-{host}:{port}")
        status = "available" if expect_available else "in use"
        description = kwargs.pop("description", f"Check if port {port} on {host} is {status}")
        super().__init__(name, description=description, **kwargs)
        self.host = host
        self.port = port
        self.expect_available = expect_available
    
    def _execute_check(self) -> CheckResult:
        """Execute the port check."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            
            port_in_use = (result == 0)
            
            if port_in_use and not self.expect_available:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.SUCCESS,
                    message=f"Port {self.port} is in use as expected",
                    details={"host": self.host, "port": self.port, "in_use": True}
                )
            elif not port_in_use and self.expect_available:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.SUCCESS,
                    message=f"Port {self.port} is available as expected",
                    details={"host": self.host, "port": self.port, "in_use": False}
                )
            elif port_in_use and self.expect_available:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.FAILURE,
                    message=f"Port {self.port} is in use but should be available",
                    details={"host": self.host, "port": self.port, "in_use": True}
                )
            else:  # not port_in_use and not self.expect_available
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.FAILURE,
                    message=f"Port {self.port} is not in use but should be",
                    details={"host": self.host, "port": self.port, "in_use": False}
                )
        except Exception as e:
            logger.exception(f"Port check failed: {e}")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"Port check failed: {str(e)}",
                details={
                    "host": self.host,
                    "port": self.port,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            ) 