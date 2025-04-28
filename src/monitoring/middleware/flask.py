"""
Flask middleware for API monitoring.

This module provides middleware components for integrating API monitoring
with Flask applications.
"""

import logging
import time
from typing import Optional, Callable, Dict, Any, Union

from flask import Flask, request, Response, g

logger = logging.getLogger(__name__)


def init_api_monitoring(
    app: Flask,
    api_collector=None,
    exclude_paths: Optional[list] = None
) -> None:
    """
    Initialize API monitoring for a Flask application.
    
    This function adds before_request and after_request handlers to the Flask
    application to monitor API requests and responses.
    
    Args:
        app: The Flask application
        api_collector: The API collector to use for metrics
        exclude_paths: List of paths to exclude from monitoring
    """
    exclude_paths = exclude_paths or []
    
    @app.before_request
    def before_request() -> None:
        """
        Handle before_request event.
        
        This function is called before each request and starts the request timer.
        """
        # Skip excluded paths
        if any(request.path.startswith(path) for path in exclude_paths):
            return
        
        # Skip the metrics endpoint itself to avoid circular dependencies
        if request.path.endswith('/metrics'):
            return
        
        # Store start time
        g.request_start_time = time.time()
        
        # Record request with collector if available
        if api_collector:
            endpoint = request.endpoint or 'unknown'
            method = request.method
            try:
                api_collector.record_request_start(endpoint, method)
            except Exception as e:
                logger.error(f"Error recording API request start: {e}")
    
    @app.after_request
    def after_request(response: Response) -> Response:
        """
        Handle after_request event.
        
        This function is called after each request and records request metrics.
        
        Args:
            response: The Flask response
            
        Returns:
            The Flask response (unchanged)
        """
        # Skip excluded paths
        if any(request.path.startswith(path) for path in exclude_paths):
            return response
        
        # Skip the metrics endpoint itself to avoid circular dependencies
        if request.path.endswith('/metrics'):
            return response
        
        # Skip if start time not recorded
        if not hasattr(g, 'request_start_time'):
            return response
        
        # Calculate response time
        response_time = time.time() - g.request_start_time
        
        # Record request with collector if available
        if api_collector:
            endpoint = request.endpoint or 'unknown'
            method = request.method
            status_code = str(response.status_code)
            error_type = None
            
            # Determine error type if applicable
            if response.status_code >= 400:
                if response.status_code >= 500:
                    error_type = 'server_error'
                else:
                    error_type = 'client_error'
            
            try:
                api_collector.record_request_end(
                    endpoint=endpoint,
                    start_time=g.request_start_time,
                    status_code=status_code,
                    error_type=error_type,
                    method=method
                )
            except Exception as e:
                logger.error(f"Error recording API request end: {e}")
        
        return response 