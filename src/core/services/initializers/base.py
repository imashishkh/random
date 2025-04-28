"""
Service Initializer Base Classes

This module provides base classes for service initializers that follow the Component
architecture pattern while incorporating best practices for initialization, metrics
collection, health checks, and graceful shutdown.
"""

import os
import time
import logging
import asyncio
from abc import abstractmethod
from typing import Dict, List, Any, Optional, Callable, Awaitable, Tuple, Set, Union

from .boot import Component, ComponentState, CircuitBreaker, RecoveryPolicy
from ....utils.logger import get_logger

# Configure logger
logger = get_logger("service_initializers")


class ServiceInitializationError(Exception):
    """Exception raised when a service fails to initialize."""
    
    def __init__(self, service_name: str, reason: str, cause: Optional[Exception] = None):
        """
        Initialize a service initialization error.
        
        Args:
            service_name: Name of the service that failed to initialize
            reason: Reason for the initialization failure
            cause: Optional underlying exception that caused the failure
        """
        self.service_name = service_name
        self.reason = reason
        self.cause = cause
        message = f"Failed to initialize service '{service_name}': {reason}"
        if cause:
            message += f" (Caused by: {str(cause)})"
        super().__init__(message)


class ConfigurationError(ServiceInitializationError):
    """Exception raised when service configuration is invalid or missing."""
    
    def __init__(self, service_name: str, reason: str, cause: Optional[Exception] = None):
        """
        Initialize a configuration error.
        
        Args:
            service_name: Name of the service with invalid configuration
            reason: Details about the configuration issue
            cause: Optional underlying exception that caused the failure
        """
        super().__init__(service_name, f"Configuration error: {reason}", cause)


class BaseServiceInitializer(Component):
    """
    Abstract base class for all service initializers.
    
    This class provides common functionality for initializing services,
    collecting metrics, registering health checks, and configuring
    graceful shutdown.
    """
    
    def __init__(self, name: str, dependencies: List[str] = None, config: Dict[str, Any] = None):
        """
        Initialize a service initializer.
        
        Args:
            name: Unique name of the service initializer
            dependencies: List of component names this initializer depends on
            config: Configuration for the service
        """
        super().__init__(name, dependencies or [])
        self.config = config or {}
        self.service = None
        self.metrics = {}
        self.start_time = None
        self.health_checks = []
        self.shutdown_hooks = []
    
    async def initialize(self) -> bool:
        """
        Initialize the service with metrics collection.
        
        This template method implements the standard initialization sequence with
        metrics collection and error handling.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            self.start_time = time.time()
            
            # Resolve configuration
            await self._resolve_configuration()
            
            # Create and configure service
            self.service = await self._create_service_instance()
            await self._configure_service(self.service)
            
            # Register health checks
            await self._register_health_checks(self.service)
            
            # Set up graceful shutdown
            await self._setup_shutdown_hooks(self.service)
            
            # Record metrics
            initialization_time = time.time() - self.start_time
            self.metrics["initialization_time"] = initialization_time
            self.metrics["initialization_success"] = True
            
            logger.info(f"Service {self.name} initialized successfully in {initialization_time:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize service {self.name}: {str(e)}")
            self.metrics["initialization_error"] = str(e)
            self.metrics["initialization_time"] = time.time() - self.start_time
            self.metrics["initialization_success"] = False
            
            # Propagate the exception after recording metrics
            raise
    
    async def start(self) -> bool:
        """
        Start the service.
        
        Returns:
            True if startup was successful, False otherwise
        """
        try:
            if not self.service:
                raise ServiceInitializationError(self.name, "Service not initialized")
                
            start_time = time.time()
            
            # Start the service using the service-specific start logic
            await self._start_service(self.service)
            
            # Record metrics
            start_time_elapsed = time.time() - start_time
            self.metrics["start_time"] = start_time_elapsed
            self.metrics["start_success"] = True
            
            logger.info(f"Service {self.name} started successfully in {start_time_elapsed:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start service {self.name}: {str(e)}")
            self.metrics["start_error"] = str(e)
            self.metrics["start_time"] = time.time() - start_time
            self.metrics["start_success"] = False
            
            # Propagate the exception after recording metrics
            raise
    
    async def stop(self) -> bool:
        """
        Stop the service gracefully.
        
        Returns:
            True if shutdown was successful, False otherwise
        """
        try:
            if not self.service:
                logger.warning(f"Service {self.name} not initialized, nothing to stop")
                return True
                
            stop_time = time.time()
            
            # Execute all registered shutdown hooks
            for hook in self.shutdown_hooks:
                try:
                    await hook()
                except Exception as e:
                    logger.warning(f"Error in shutdown hook for {self.name}: {str(e)}")
            
            # Stop the service using the service-specific stop logic
            await self._stop_service(self.service)
            
            # Record metrics
            stop_time_elapsed = time.time() - stop_time
            self.metrics["stop_time"] = stop_time_elapsed
            self.metrics["stop_success"] = True
            
            logger.info(f"Service {self.name} stopped successfully in {stop_time_elapsed:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop service {self.name}: {str(e)}")
            self.metrics["stop_error"] = str(e)
            self.metrics["stop_time"] = time.time() - stop_time
            self.metrics["stop_success"] = False
            return False
    
    async def health_check(self) -> bool:
        """
        Check if the service is operating correctly.
        
        Returns:
            True if the service is healthy, False otherwise
        """
        if not self.service:
            logger.warning(f"Service {self.name} not initialized, health check failed")
            return False
            
        try:
            # Run all registered health checks
            for check in self.health_checks:
                if not await check():
                    logger.warning(f"Health check failed for service {self.name}")
                    return False
            
            # If there are no health checks, run the default health check
            if not self.health_checks:
                return await self._default_health_check(self.service)
                
            return True
            
        except Exception as e:
            logger.error(f"Error during health check for {self.name}: {str(e)}")
            return False
    
    async def cleanup(self) -> bool:
        """
        Clean up resources used by the service.
        
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            if not self.service:
                logger.warning(f"Service {self.name} not initialized, nothing to clean up")
                return True
                
            # Clean up the service using the service-specific cleanup logic
            await self._cleanup_service(self.service)
            
            # Clear references and state
            self.service = None
            self.health_checks = []
            self.shutdown_hooks = []
            
            logger.info(f"Service {self.name} cleaned up successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clean up service {self.name}: {str(e)}")
            return False
    
    async def _resolve_configuration(self) -> None:
        """
        Resolve and validate configuration for the service.
        
        This method should be overridden to implement service-specific
        configuration resolution and validation.
        
        Raises:
            ConfigurationError: If configuration is invalid or missing
        """
        # Base implementation does nothing, override in subclasses
        pass
    
    @abstractmethod
    async def _create_service_instance(self) -> Any:
        """
        Create the service instance.
        
        Returns:
            Service instance
        
        Raises:
            ServiceInitializationError: If service instance creation fails
        """
        pass
    
    @abstractmethod
    async def _configure_service(self, service: Any) -> None:
        """
        Configure the service with appropriate parameters.
        
        Args:
            service: Service instance to configure
            
        Raises:
            ConfigurationError: If service configuration fails
        """
        pass
    
    @abstractmethod
    async def _register_health_checks(self, service: Any) -> None:
        """
        Register health checks for the service.
        
        Args:
            service: Service instance to register health checks for
        """
        pass
    
    @abstractmethod
    async def _setup_shutdown_hooks(self, service: Any) -> None:
        """
        Set up graceful shutdown hooks for the service.
        
        Args:
            service: Service instance to set up shutdown hooks for
        """
        pass
    
    async def _start_service(self, service: Any) -> None:
        """
        Start the service.
        
        Override this method to implement service-specific startup logic.
        
        Args:
            service: Service instance to start
        """
        # Default implementation assumes the service has a start() method
        if hasattr(service, 'start') and callable(service.start):
            if asyncio.iscoroutinefunction(service.start):
                await service.start()
            else:
                service.start()
        else:
            logger.info(f"Service {self.name} does not have a start method, assuming auto-start")
    
    async def _stop_service(self, service: Any) -> None:
        """
        Stop the service.
        
        Override this method to implement service-specific shutdown logic.
        
        Args:
            service: Service instance to stop
        """
        # Default implementation assumes the service has a stop() method
        if hasattr(service, 'stop') and callable(service.stop):
            if asyncio.iscoroutinefunction(service.stop):
                await service.stop()
            else:
                service.stop()
        else:
            logger.info(f"Service {self.name} does not have a stop method, assuming auto-stop")
    
    async def _cleanup_service(self, service: Any) -> None:
        """
        Clean up the service resources.
        
        Override this method to implement service-specific cleanup logic.
        
        Args:
            service: Service instance to clean up
        """
        # Default implementation assumes the service has a cleanup() method
        if hasattr(service, 'cleanup') and callable(service.cleanup):
            if asyncio.iscoroutinefunction(service.cleanup):
                await service.cleanup()
            else:
                service.cleanup()
        else:
            logger.info(f"Service {self.name} does not have a cleanup method, no additional cleanup needed")
    
    async def _default_health_check(self, service: Any) -> bool:
        """
        Default health check implementation.
        
        Override this method to implement service-specific health check logic.
        
        Args:
            service: Service instance to check
            
        Returns:
            True if the service is healthy, False otherwise
        """
        # Default implementation assumes the service exists
        return service is not None
    
    def register_health_check(self, health_check: Callable[[], Awaitable[bool]]) -> None:
        """
        Register a health check function for the service.
        
        Args:
            health_check: Async function that returns True if service is healthy
        """
        self.health_checks.append(health_check)
    
    def register_shutdown_hook(self, shutdown_hook: Callable[[], Awaitable[None]]) -> None:
        """
        Register a shutdown hook function for the service.
        
        Args:
            shutdown_hook: Async function to execute during service shutdown
        """
        self.shutdown_hooks.append(shutdown_hook) 