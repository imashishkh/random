"""
API dependency check for the Forex Trading system.

This module provides a dependency check that verifies connectivity and
basic functionality of external API services used by the system.
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Tuple, Optional
import aiohttp
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from core.dependencies.checker import DependencyCheck, CheckResult, CheckStatus
from core.config import ConfigManager


logger = logging.getLogger(__name__)


class APICheck(DependencyCheck):
    """
    Dependency check for external API services.
    
    This check verifies connectivity to all external API endpoints required
    by the Forex Trading system, including market data providers, payment
    gateways, and other third-party services.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the API dependency check with configuration.
        
        Args:
            config_manager: The configuration manager containing API endpoints and credentials.
        """
        super().__init__(
            name="api_services",
            description="Checks connectivity to external API services",
            dependencies=[],
            priority=1  # Priority 1 as most services depend on APIs, but database is more critical
        )
        self.config_manager = config_manager
    
    def _get_api_config(self) -> Dict[str, Any]:
        """
        Extract API configuration from the config manager.
        
        Returns:
            Dictionary containing API endpoints and settings.
        """
        api_config = self.config_manager.get("api_services", {})
        
        # Default API configuration if not specified
        default_config = {
            "timeout": 10,
            "endpoints": [],
            "retry_count": 2,
            "verify_ssl": True
        }
        
        # Merge provided config with defaults
        for key, default_value in default_config.items():
            if key not in api_config:
                api_config[key] = default_value
                
        return api_config
    
    def _get_endpoints(self) -> List[Dict[str, Any]]:
        """
        Get the list of API endpoints to check.
        
        Returns:
            List of API endpoint configurations.
        """
        api_config = self._get_api_config()
        endpoints = api_config.get("endpoints", [])
        
        # Example default endpoints if none are configured
        if not endpoints:
            logger.warning("No API endpoints configured for health checks. Using default endpoints.")
            # Add some minimal default checks for common forex APIs
            endpoints = [
                {
                    "name": "example_market_data",
                    "url": "https://api.example.com/forex/status",
                    "method": "GET",
                    "timeout": 5,
                    "expected_status": 200,
                    "headers": {},
                    "required": False
                }
            ]
            
        return endpoints
    
    def _check_endpoint(self, endpoint: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check a single API endpoint synchronously.
        
        Args:
            endpoint: API endpoint configuration dictionary
            
        Returns:
            Tuple containing success status, message, and detailed results
        """
        name = endpoint.get("name", "unnamed_api")
        url = endpoint.get("url")
        method = endpoint.get("method", "GET").upper()
        timeout = endpoint.get("timeout", self._get_api_config().get("timeout", 10))
        headers = endpoint.get("headers", {})
        expected_status = endpoint.get("expected_status", 200)
        payload = endpoint.get("payload")
        verify_ssl = endpoint.get("verify_ssl", self._get_api_config().get("verify_ssl", True))
        
        if not url:
            return False, f"No URL provided for API endpoint: {name}", {"error": "Missing URL"}
        
        # Prepare request arguments
        request_args = {
            "headers": headers,
            "timeout": timeout,
            "verify": verify_ssl
        }
        
        # Add payload for POST/PUT methods
        if method in ["POST", "PUT"] and payload:
            request_args["json"] = payload
        
        # Initialize result dictionary
        result = {
            "url": url,
            "method": method,
            "timeout": timeout,
            "expected_status": expected_status
        }
        
        try:
            logger.debug(f"Checking API endpoint {name} ({url}) with method {method}")
            
            # Make request based on method
            if method == "GET":
                response = requests.get(url, **request_args)
            elif method == "POST":
                response = requests.post(url, **request_args)
            elif method == "PUT":
                response = requests.put(url, **request_args)
            elif method == "DELETE":
                response = requests.delete(url, **request_args)
            else:
                return False, f"Unsupported HTTP method: {method}", {"error": f"Unsupported method: {method}"}
            
            # Check response status
            status_code = response.status_code
            result["status_code"] = status_code
            
            if status_code == expected_status:
                # Try to parse response as JSON for additional validation
                try:
                    result["response"] = response.json()
                except ValueError:
                    # Not JSON or empty response
                    result["response"] = "Non-JSON response"
                
                return True, f"API endpoint {name} returned expected status: {status_code}", result
            else:
                # Unexpected status code
                try:
                    error_data = response.json()
                    result["error_data"] = error_data
                except ValueError:
                    result["error_data"] = response.text[:200] + "..." if len(response.text) > 200 else response.text
                
                return False, f"API endpoint {name} returned unexpected status: {status_code}, expected: {expected_status}", result
                
        except Timeout:
            return False, f"Timeout connecting to API endpoint {name}", {"error": "Timeout", "url": url}
        except ConnectionError:
            return False, f"Connection error for API endpoint {name}", {"error": "Connection error", "url": url}
        except RequestException as e:
            return False, f"Request error for API endpoint {name}: {str(e)}", {"error": str(e), "url": url}
        except Exception as e:
            return False, f"Unexpected error checking API endpoint {name}: {str(e)}", {"error": str(e), "url": url}
    
    async def _check_endpoint_async(self, endpoint: Dict[str, Any], session: aiohttp.ClientSession) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check a single API endpoint asynchronously.
        
        Args:
            endpoint: API endpoint configuration dictionary
            session: aiohttp client session
            
        Returns:
            Tuple containing success status, message, and detailed results
        """
        name = endpoint.get("name", "unnamed_api")
        url = endpoint.get("url")
        method = endpoint.get("method", "GET").upper()
        timeout = endpoint.get("timeout", self._get_api_config().get("timeout", 10))
        headers = endpoint.get("headers", {})
        expected_status = endpoint.get("expected_status", 200)
        payload = endpoint.get("payload")
        verify_ssl = endpoint.get("verify_ssl", self._get_api_config().get("verify_ssl", True))
        
        if not url:
            return False, f"No URL provided for API endpoint: {name}", {"error": "Missing URL"}
        
        # Initialize result dictionary
        result = {
            "url": url,
            "method": method,
            "timeout": timeout,
            "expected_status": expected_status
        }
        
        try:
            logger.debug(f"Checking API endpoint asynchronously {name} ({url}) with method {method}")
            
            # Make request based on method
            if method == "GET":
                request_method = session.get
            elif method == "POST":
                request_method = session.post
            elif method == "PUT":
                request_method = session.put
            elif method == "DELETE":
                request_method = session.delete
            else:
                return False, f"Unsupported HTTP method: {method}", {"error": f"Unsupported method: {method}"}
            
            # Set up the request arguments
            request_kwargs = {
                "headers": headers,
                "timeout": aiohttp.ClientTimeout(total=timeout),
                "ssl": verify_ssl
            }
            
            # Add payload for POST/PUT methods
            if method in ["POST", "PUT"] and payload:
                request_kwargs["json"] = payload
            
            async with request_method(url, **request_kwargs) as response:
                # Check response status
                status_code = response.status
                result["status_code"] = status_code
                
                if status_code == expected_status:
                    # Try to parse response as JSON for additional validation
                    try:
                        result["response"] = await response.json()
                    except ValueError:
                        # Not JSON or empty response
                        result["response"] = "Non-JSON response"
                    
                    return True, f"API endpoint {name} returned expected status: {status_code}", result
                else:
                    # Unexpected status code
                    try:
                        error_data = await response.json()
                        result["error_data"] = error_data
                    except ValueError:
                        text = await response.text()
                        result["error_data"] = text[:200] + "..." if len(text) > 200 else text
                    
                    return False, f"API endpoint {name} returned unexpected status: {status_code}, expected: {expected_status}", result
                    
        except asyncio.TimeoutError:
            return False, f"Timeout connecting to API endpoint {name}", {"error": "Timeout", "url": url}
        except aiohttp.ClientConnectorError:
            return False, f"Connection error for API endpoint {name}", {"error": "Connection error", "url": url}
        except aiohttp.ClientError as e:
            return False, f"Request error for API endpoint {name}: {str(e)}", {"error": str(e), "url": url}
        except Exception as e:
            return False, f"Unexpected error checking API endpoint {name}: {str(e)}", {"error": str(e), "url": url}
    
    def run(self) -> CheckResult:
        """
        Run the API dependency check synchronously.
        
        Returns:
            CheckResult: The result of the API services check.
        """
        endpoints = self._get_endpoints()
        api_config = self._get_api_config()
        
        if not endpoints:
            logger.warning("No API endpoints to check")
            return CheckResult(
                status=CheckStatus.WARNING,
                message="No API endpoints configured for health checks",
                details={"endpoints_count": 0}
            )
        
        # Track results for all endpoints
        all_results = []
        required_failures = []
        optional_failures = []
        
        # Check each endpoint
        for endpoint in endpoints:
            endpoint_name = endpoint.get("name", "unnamed_api")
            required = endpoint.get("required", True)
            
            # Perform the check with retries
            retry_count = api_config.get("retry_count", 2)
            success = False
            message = ""
            details = {}
            
            for attempt in range(retry_count + 1):
                if attempt > 0:
                    logger.debug(f"Retrying API endpoint {endpoint_name} (attempt {attempt}/{retry_count})")
                
                success, message, details = self._check_endpoint(endpoint)
                
                if success:
                    if attempt > 0:
                        logger.debug(f"API endpoint {endpoint_name} succeeded on retry {attempt}")
                    break
            
            # Store result
            result = {
                "name": endpoint_name,
                "success": success,
                "message": message,
                "required": required,
                "details": details
            }
            all_results.append(result)
            
            # Track failures
            if not success:
                if required:
                    required_failures.append(endpoint_name)
                else:
                    optional_failures.append(endpoint_name)
        
        # Determine overall status
        if required_failures:
            status = CheckStatus.FAILURE
            message = f"Failed to connect to required API services: {', '.join(required_failures)}"
        elif optional_failures:
            status = CheckStatus.WARNING
            message = f"Failed to connect to optional API services: {', '.join(optional_failures)}"
        else:
            status = CheckStatus.SUCCESS
            message = "Successfully connected to all API services"
        
        return CheckResult(
            status=status,
            message=message,
            details={
                "endpoints_checked": len(endpoints),
                "successful_endpoints": len(endpoints) - len(required_failures) - len(optional_failures),
                "required_failures": required_failures,
                "optional_failures": optional_failures,
                "all_results": all_results
            }
        )
    
    async def run_async(self) -> CheckResult:
        """
        Run the API dependency check asynchronously.
        
        Returns:
            CheckResult: The result of the API services check.
        """
        endpoints = self._get_endpoints()
        api_config = self._get_api_config()
        
        if not endpoints:
            logger.warning("No API endpoints to check")
            return CheckResult(
                status=CheckStatus.WARNING,
                message="No API endpoints configured for health checks",
                details={"endpoints_count": 0}
            )
        
        # Track results for all endpoints
        all_results = []
        required_failures = []
        optional_failures = []
        
        # Create aiohttp ClientSession
        timeout = aiohttp.ClientTimeout(total=api_config.get("timeout", 10))
        connector = aiohttp.TCPConnector(ssl=api_config.get("verify_ssl", True))
        
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            # Prepare list of tasks for checking endpoints
            check_tasks = []
            
            for endpoint in endpoints:
                endpoint_name = endpoint.get("name", "unnamed_api")
                required = endpoint.get("required", True)
                retry_count = api_config.get("retry_count", 2)
                
                # Create task that includes retry logic
                check_tasks.append(self._check_endpoint_with_retry(endpoint, session, retry_count))
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*check_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                endpoint = endpoints[i]
                endpoint_name = endpoint.get("name", "unnamed_api")
                required = endpoint.get("required", True)
                
                if isinstance(result, Exception):
                    # Handle exceptions from the task
                    success = False
                    message = f"Error checking API endpoint {endpoint_name}: {str(result)}"
                    details = {"error": str(result), "exception_type": type(result).__name__}
                else:
                    # Unpack normal results
                    success, message, details = result
                
                # Store result
                endpoint_result = {
                    "name": endpoint_name,
                    "success": success,
                    "message": message,
                    "required": required,
                    "details": details
                }
                all_results.append(endpoint_result)
                
                # Track failures
                if not success:
                    if required:
                        required_failures.append(endpoint_name)
                    else:
                        optional_failures.append(endpoint_name)
        
        # Determine overall status
        if required_failures:
            status = CheckStatus.FAILURE
            message = f"Failed to connect to required API services: {', '.join(required_failures)}"
        elif optional_failures:
            status = CheckStatus.WARNING
            message = f"Failed to connect to optional API services: {', '.join(optional_failures)}"
        else:
            status = CheckStatus.SUCCESS
            message = "Successfully connected to all API services"
        
        return CheckResult(
            status=status,
            message=message,
            details={
                "endpoints_checked": len(endpoints),
                "successful_endpoints": len(endpoints) - len(required_failures) - len(optional_failures),
                "required_failures": required_failures,
                "optional_failures": optional_failures,
                "all_results": all_results
            }
        )
    
    async def _check_endpoint_with_retry(self, endpoint: Dict[str, Any], session: aiohttp.ClientSession, retry_count: int) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check an API endpoint with retries.
        
        Args:
            endpoint: API endpoint configuration
            session: aiohttp client session
            retry_count: Number of retry attempts
            
        Returns:
            Result of the endpoint check
        """
        endpoint_name = endpoint.get("name", "unnamed_api")
        success = False
        message = ""
        details = {}
        
        for attempt in range(retry_count + 1):
            if attempt > 0:
                logger.debug(f"Retrying API endpoint {endpoint_name} (attempt {attempt}/{retry_count})")
                # Add exponential backoff
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
            
            success, message, details = await self._check_endpoint_async(endpoint, session)
            
            if success:
                if attempt > 0:
                    logger.debug(f"API endpoint {endpoint_name} succeeded on retry {attempt}")
                break
        
        return success, message, details 