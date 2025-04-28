"""
Binance Client Initializer

This module provides the initializer component for the Binance API client.
"""

import os
import time
import asyncio
from typing import Dict, List, Any, Optional, Callable, Awaitable

from ....exchange.binance_api_client import BinanceApiClient
from .boot import CircuitBreaker, RecoveryPolicy
from ....utils.logger import get_logger
from .base import BaseServiceInitializer, ServiceInitializationError, ConfigurationError

# Configure logger
logger = get_logger("binance_initializer")


class BinanceClientInitializer(BaseServiceInitializer):
    """
    Initializes and configures the Binance API client.
    
    This component handles:
    1. Loading API credentials from configuration or environment
    2. Creating and configuring the Binance API client
    3. Setting up rate limiting and circuit breakers
    4. Registering health checks
    5. Configuring graceful shutdown
    """
    
    def __init__(
        self,
        name: str = "binance_client",
        dependencies: List[str] = None,
        config: Dict[str, Any] = None
    ):
        """
        Initialize the Binance client initializer.
        
        Args:
            name: Component name (default: "binance_client")
            dependencies: Components this initializer depends on
            config: Configuration for the Binance client
        """
        super().__init__(name, dependencies, config)
        self.api_check_interval = 60  # seconds
        self.health_check_task = None
    
    async def _resolve_configuration(self) -> None:
        """
        Resolve and validate Binance API configuration.
        
        Resolves API credentials from configuration or environment variables
        and validates that they are present.
        
        Raises:
            ConfigurationError: If API credentials are missing
        """
        # Get API key from config or environment
        self.api_key = self.config.get("api_key") or os.environ.get("BINANCE_API_KEY")
        self.api_secret = self.config.get("api_secret") or os.environ.get("BINANCE_API_SECRET")
        
        # Validate API credentials
        if not self.api_key:
            raise ConfigurationError(self.name, "Binance API key not provided in config or environment")
        
        if not self.api_secret:
            raise ConfigurationError(self.name, "Binance API secret not provided in config or environment")
        
        # Get other configuration parameters with defaults
        self.testnet = self.config.get("testnet", False)
        self.use_ed25519 = self.config.get("use_ed25519", False)
        self.timeout = self.config.get("timeout", 30000)  # milliseconds
        self.enable_rate_limit = self.config.get("enable_rate_limit", True)
        self.max_retries = self.config.get("max_retries", 3)
        
        logger.info(
            f"Resolved Binance API configuration: testnet={self.testnet}, "
            f"ed25519={self.use_ed25519}, timeout={self.timeout}ms"
        )
    
    async def _create_service_instance(self) -> BinanceApiClient:
        """
        Create a new Binance API client instance.
        
        Returns:
            Configured BinanceApiClient instance
        
        Raises:
            ServiceInitializationError: If client creation fails
        """
        try:
            logger.info(f"Creating Binance API client (testnet={self.testnet})")
            
            # Create client instance
            client = BinanceApiClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                use_ed25519=self.use_ed25519,
                testnet=self.testnet,
                timeout=self.timeout,
                enable_rate_limit=self.enable_rate_limit,
                max_retries=self.max_retries
            )
            
            logger.info("Binance API client created successfully")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create Binance API client: {str(e)}")
            raise ServiceInitializationError(self.name, "Failed to create Binance API client", e)
    
    async def _configure_service(self, service: BinanceApiClient) -> None:
        """
        Configure the Binance API client.
        
        Args:
            service: BinanceApiClient instance to configure
            
        Raises:
            ConfigurationError: If client configuration fails
        """
        try:
            # Configure rate limits if provided in config
            rate_limits = self.config.get("rate_limits", {})
            for endpoint, limit_config in rate_limits.items():
                limit = limit_config.get("limit")
                interval = limit_config.get("interval")
                
                if limit and interval:
                    service.rate_limiter.set_limit(endpoint, limit, interval)
                    logger.info(f"Set rate limit for {endpoint}: {limit} requests per {interval}s")
            
            # Configure circuit breakers if provided in config
            circuit_breakers = self.config.get("circuit_breakers", {})
            for endpoint, cb_config in circuit_breakers.items():
                if endpoint in service.circuit_breakers:
                    # Update existing circuit breaker configuration
                    if "failure_threshold" in cb_config:
                        service.circuit_breakers[endpoint].failure_threshold = cb_config["failure_threshold"]
                    
                    if "reset_timeout" in cb_config:
                        service.circuit_breakers[endpoint].reset_timeout = cb_config["reset_timeout"]
                    
                    if "half_open_max_calls" in cb_config:
                        service.circuit_breakers[endpoint].half_open_max_calls = cb_config["half_open_max_calls"]
                    
                    logger.info(f"Configured circuit breaker for {endpoint}")
            
            # Prewarm connections by performing a lightweight API call
            await self._prewarm_connections(service)
            
            logger.info("Binance API client configured successfully")
            
        except Exception as e:
            logger.error(f"Failed to configure Binance API client: {str(e)}")
            raise ConfigurationError(self.name, "Failed to configure Binance API client", e)
    
    async def _register_health_checks(self, service: BinanceApiClient) -> None:
        """
        Register health checks for the Binance API client.
        
        Args:
            service: BinanceApiClient instance to register health checks for
        """
        # Define the main health check function
        async def binance_api_health_check() -> bool:
            try:
                # Use a lightweight ping endpoint to check API connectivity
                await service.public_request("ping", {})
                return True
            except Exception as e:
                logger.warning(f"Binance API health check failed: {str(e)}")
                return False
        
        # Define the market data health check
        async def binance_market_data_health_check() -> bool:
            try:
                # Check if we can fetch basic market data
                market_data = await service.public_request("exchangeInfo", {})
                return "symbols" in market_data and len(market_data["symbols"]) > 0
            except Exception as e:
                logger.warning(f"Binance market data health check failed: {str(e)}")
                return False
        
        # Define the account data health check (if auth credentials provided)
        async def binance_account_health_check() -> bool:
            try:
                # Check if we can fetch account information
                account_data = await service.private_request("account", {})
                return "makerCommission" in account_data
            except Exception as e:
                logger.warning(f"Binance account health check failed: {str(e)}")
                return False
        
        # Register the health checks
        self.register_health_check(binance_api_health_check)
        self.register_health_check(binance_market_data_health_check)
        
        # Only register account check if api credentials are provided
        if self.api_key and self.api_secret:
            self.register_health_check(binance_account_health_check)
        
        logger.info(f"Registered {len(self.health_checks)} health checks for Binance API client")
    
    async def _setup_shutdown_hooks(self, service: BinanceApiClient) -> None:
        """
        Set up graceful shutdown hooks for the Binance API client.
        
        Args:
            service: BinanceApiClient instance to set up shutdown hooks for
        """
        # Define the shutdown hook for the API client
        async def binance_api_shutdown() -> None:
            try:
                logger.info("Shutting down Binance API client...")
                
                # Cancel any periodic health check task
                if self.health_check_task and not self.health_check_task.done():
                    self.health_check_task.cancel()
                    try:
                        await self.health_check_task
                    except asyncio.CancelledError:
                        pass
                
                # Close any open resources
                if hasattr(service, 'close') and callable(service.close):
                    if asyncio.iscoroutinefunction(service.close):
                        await service.close()
                    else:
                        service.close()
                
                # Close the session
                if hasattr(service, 'session') and service.session:
                    await service.session.close()
                
                logger.info("Binance API client shut down successfully")
                
            except Exception as e:
                logger.error(f"Error during Binance API client shutdown: {str(e)}")
        
        # Register the shutdown hook
        self.register_shutdown_hook(binance_api_shutdown)
        
        logger.info("Registered shutdown hook for Binance API client")
    
    async def _prewarm_connections(self, service: BinanceApiClient) -> None:
        """
        Prewarm connections to the Binance API.
        
        Performs a lightweight API call to establish connections and
        cache necessary data for better cold-start performance.
        
        Args:
            service: BinanceApiClient instance to prewarm
        """
        try:
            logger.info("Prewarming Binance API connections...")
            
            # Ping the API to establish connection
            await service.public_request("ping", {})
            
            # Load exchange information to cache symbols and rules
            await service.public_request("exchangeInfo", {})
            
            # Load server time to check time synchronization
            server_time_resp = await service.public_request("time", {})
            server_time = server_time_resp.get("serverTime", 0) / 1000.0  # Convert to seconds
            local_time = time.time()
            time_diff = abs(local_time - server_time)
            
            if time_diff > 1.0:  # More than 1 second difference
                logger.warning(
                    f"Time difference between local and Binance server: {time_diff:.2f}s. "
                    f"This may cause authentication issues."
                )
            
            logger.info("Binance API connections prewarmed successfully")
            
        except Exception as e:
            logger.warning(f"Failed to prewarm Binance API connections: {str(e)}")
            # Don't raise exception, just log warning as this is not critical
    
    async def start(self) -> bool:
        """
        Start the Binance client service.
        
        This implementation starts a periodic health check task in addition
        to the standard startup process.
        
        Returns:
            True if startup was successful, False otherwise
        """
        result = await super().start()
        
        if result and self.config.get("enable_periodic_health_check", True):
            # Start a periodic health check task
            self.health_check_task = asyncio.create_task(self._periodic_health_check())
            logger.info(f"Started periodic health check task (interval: {self.api_check_interval}s)")
        
        return result
    
    async def _periodic_health_check(self) -> None:
        """
        Run periodic health checks for the Binance API client.
        
        This task runs indefinitely until cancelled during shutdown.
        """
        try:
            while True:
                healthy = await self.health_check()
                if not healthy:
                    logger.warning(f"Periodic health check for {self.name} failed")
                
                # Wait for the next check interval
                await asyncio.sleep(self.api_check_interval)
                
        except asyncio.CancelledError:
            logger.info(f"Periodic health check task for {self.name} cancelled")
        except Exception as e:
            logger.error(f"Error in periodic health check for {self.name}: {str(e)}")
    
    async def _default_health_check(self, service: BinanceApiClient) -> bool:
        """
        Default health check implementation for Binance API client.
        
        Args:
            service: BinanceApiClient instance to check
            
        Returns:
            True if the service is healthy, False otherwise
        """
        try:
            # Use a simple ping check if no other health checks registered
            await service.public_request("ping", {})
            return True
        except Exception as e:
            logger.warning(f"Default Binance API health check failed: {str(e)}")
            return False 