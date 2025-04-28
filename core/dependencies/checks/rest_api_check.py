"""
REST API dependency check for the Forex Trading system.

This module provides a dependency check that verifies connectivity to essential
external REST APIs used by the trading system.
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

from core.dependencies.checker import DependencyCheck, CheckResult, CheckStatus
from core.config import ConfigManager


logger = logging.getLogger(__name__)


class RestApiCheck(DependencyCheck):
    """
    Dependency check for external REST API endpoints.
    
    This check verifies connectivity and basic functionality of configured
    external REST APIs that are essential for the trading system.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the REST API check with configuration.
        
        Args:
            config_manager: The configuration manager containing API endpoints and settings.
        """
        super().__init__(
            name="rest_api",
            description="Checks connectivity to essential external REST APIs",
            dependencies=[],  # External REST APIs don't depend on other services
            priority=2  # Medium-high priority as trading features depend on APIs
        )
        self.config_manager = config_manager
        
    def _get_api_endpoints(self) -> List[Dict[str, Any]]:
        """
        Extract API endpoint configurations from the config manager.
        
        Returns:
            List of dictionaries containing API endpoint configurations.
        """
        api_config = self.config_manager.get("api", {})
        endpoints = api_config.get("endpoints", [])
        
        # If no endpoints are configured, add default forex price API endpoint
        if not endpoints:
            logger.warning("No API endpoints configured for checking, using default")
            endpoints = [{
                "name": "forex_data_provider",
                "url": "https://api.example.com/forex/prices",  # Placeholder URL
                "method": "GET",
                "timeout": 10,
                "expected_status": 200,
                "headers": {}
            }]
            
        return endpoints
    
    def run(self) -> CheckResult:
        """
        Run the REST API check synchronously. This uses asyncio.run to call
        the async implementation.
        
        Returns:
            CheckResult: The result of the REST API connectivity check.
        """
        try:
            return asyncio.run(self.run_async())
        except Exception as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"REST API check failed with error: {str(e)}",
                details={"error": str(e)}
            )
    
    async def run_async(self) -> CheckResult:
        """
        Run the REST API dependency check asynchronously.
        
        Checks each configured API endpoint for:
        1. Network connectivity
        2. Expected HTTP status codes
        3. Response within timeout period
        
        Returns:
            CheckResult: The result of the REST API connectivity check.
        """
        endpoints = self._get_api_endpoints()
        
        # If no endpoints to check, return a warning
        if not endpoints:
            return CheckResult(
                status=CheckStatus.WARNING,
                message="No REST API endpoints configured for checking.",
                details={"warning": "Configure API endpoints in the config file."}
            )
        
        # Execute all endpoint checks concurrently
        tasks = [self._check_endpoint(endpoint) for endpoint in endpoints]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process the results
        success_count = 0
        failed_endpoints = []
        details = {}
        
        for endpoint, result in zip(endpoints, results):
            endpoint_name = endpoint.get("name", "unknown")
            details[endpoint_name] = {}
            
            if isinstance(result, Exception):
                failed_endpoints.append({
                    "name": endpoint_name,
                    "url": endpoint.get("url", ""),
                    "error": str(result)
                })
                details[endpoint_name]["status"] = "error"
                details[endpoint_name]["error"] = str(result)
            elif isinstance(result, Tuple) and len(result) == 3:
                success, message, result_details = result
                details[endpoint_name].update(result_details)
                
                if success:
                    success_count += 1
                    details[endpoint_name]["status"] = "success"
                else:
                    failed_endpoints.append({
                        "name": endpoint_name,
                        "url": endpoint.get("url", ""),
                        "error": message
                    })
                    details[endpoint_name]["status"] = "failed"
                    details[endpoint_name]["error"] = message
            else:
                failed_endpoints.append({
                    "name": endpoint_name,
                    "url": endpoint.get("url", ""),
                    "error": "Unknown result format"
                })
                details[endpoint_name]["status"] = "error"
                details[endpoint_name]["error"] = "Unknown result format"
        
        # Determine the overall check status
        if len(failed_endpoints) == 0:
            status = CheckStatus.SUCCESS
            message = f"All {len(endpoints)} REST API endpoints are accessible."
        elif success_count > 0:
            status = CheckStatus.WARNING
            message = f"{len(failed_endpoints)} out of {len(endpoints)} REST API endpoints failed."
        else:
            status = CheckStatus.FAILURE
            message = f"All {len(endpoints)} REST API endpoints failed."
        
        return CheckResult(
            status=status,
            message=message,
            details={
                "success_count": success_count,
                "failure_count": len(failed_endpoints),
                "failed_endpoints": failed_endpoints,
                "endpoints": details
            }
        )
    
    async def _check_endpoint(self, endpoint: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check a single REST API endpoint.
        
        Args:
            endpoint: Dictionary containing endpoint configuration.
            
        Returns:
            Tuple containing success flag, message, and detailed results.
        """
        name = endpoint.get("name", "unnamed_endpoint")
        url = endpoint.get("url", "")
        method = endpoint.get("method", "GET").upper()
        timeout = endpoint.get("timeout", 10)
        expected_status = endpoint.get("expected_status", 200)
        headers = endpoint.get("headers", {})
        
        if not url:
            return (False, "Missing URL configuration", {"url": url})
        
        # Basic validation of URL format
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return (False, f"Invalid URL format: {url}", {"url": url})
        
        # Prepare request options
        options = {
            "headers": headers,
            "timeout": aiohttp.ClientTimeout(total=timeout)
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                request_method = getattr(session, method.lower(), session.get)
                
                start_time = asyncio.get_event_loop().time()
                async with request_method(url, **options) as response:
                    response_time = asyncio.get_event_loop().time() - start_time
                    
                    # Check status code
                    if response.status != expected_status:
                        return (
                            False,
                            f"Unexpected status code: {response.status}, expected: {expected_status}",
                            {
                                "url": url,
                                "method": method,
                                "status_code": response.status,
                                "expected_status": expected_status,
                                "response_time_ms": round(response_time * 1000, 2)
                            }
                        )
                    
                    # Success case
                    return (
                        True,
                        f"API endpoint {name} is accessible",
                        {
                            "url": url,
                            "method": method,
                            "status_code": response.status,
                            "response_time_ms": round(response_time * 1000, 2)
                        }
                    )
                    
        except asyncio.TimeoutError:
            return (
                False,
                f"Request timed out after {timeout} seconds",
                {"url": url, "method": method, "timeout": timeout}
            )
        except aiohttp.ClientError as e:
            return (
                False,
                f"HTTP client error: {str(e)}",
                {"url": url, "method": method, "error": str(e)}
            )
        except Exception as e:
            return (
                False,
                f"Unexpected error: {str(e)}",
                {"url": url, "method": method, "error": str(e)}
            ) 