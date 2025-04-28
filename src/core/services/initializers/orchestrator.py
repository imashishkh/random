"""
Orchestrator Service Initializer

This module provides the initializer component for the agent orchestration service
that manages agent lifecycle and coordination in the Forex Trading system.
"""

import os
import time
import asyncio
from typing import Dict, List, Any, Optional, Callable, Awaitable

from ....agents.orchestration import AgentOrchestrator
from ....utils.logger import get_logger
from .base import BaseServiceInitializer, ServiceInitializationError, ConfigurationError

# Configure logger
logger = get_logger("orchestrator_initializer")


class OrchestratorInitializer(BaseServiceInitializer):
    """
    Initializes and configures the agent orchestration service.
    
    This component handles:
    1. Loading orchestration configuration
    2. Initializing the agent orchestrator
    3. Configuring communication channels
    4. Setting up health monitoring
    5. Preparing metrics collection
    6. Configuring graceful shutdown
    """
    
    def __init__(
        self,
        name: str = "orchestrator",
        dependencies: List[str] = None,
        config: Dict[str, Any] = None
    ):
        """
        Initialize the orchestrator initializer.
        
        Args:
            name: Component name (default: "orchestrator")
            dependencies: Component dependencies (Redis is typically required)
            config: Configuration for the orchestrator
        """
        # Ensure orchestrator depends on redis by default
        dependencies = dependencies or ["redis"]
        super().__init__(name, dependencies, config)
        self.health_check_interval = 30  # seconds
        self.health_check_task = None
    
    async def _resolve_configuration(self) -> None:
        """
        Resolve and validate orchestrator configuration.
        
        Raises:
            ConfigurationError: If required configuration is missing
        """
        # Get base configuration
        self.max_agents = self.config.get("max_agents", 10)
        self.agent_spawn_delay = self.config.get("agent_spawn_delay", 2.0)  # seconds
        self.agent_shutdown_timeout = self.config.get("agent_shutdown_timeout", 30.0)  # seconds
        self.communication_namespace = self.config.get("communication_namespace", "forex")
        
        # Get command-line overrides if available
        cli_args = self.config.get("cli_args", {})
        if cli_args and "agent_count" in cli_args:
            try:
                agent_count = int(cli_args["agent_count"])
                logger.info(f"Overriding max_agents from command line: {agent_count}")
                self.max_agents = agent_count
            except (ValueError, TypeError):
                logger.warning(f"Invalid agent_count value: {cli_args['agent_count']}, using default: {self.max_agents}")
        
        # Validate configuration
        if self.max_agents <= 0:
            raise ConfigurationError(self.name, f"Invalid max_agents value: {self.max_agents}")
        
        if self.agent_spawn_delay <= 0:
            raise ConfigurationError(self.name, f"Invalid agent_spawn_delay value: {self.agent_spawn_delay}")
        
        if self.agent_shutdown_timeout <= 0:
            raise ConfigurationError(self.name, f"Invalid agent_shutdown_timeout value: {self.agent_shutdown_timeout}")
        
        logger.info(
            f"Resolved orchestrator configuration: max_agents={self.max_agents}, "
            f"spawn_delay={self.agent_spawn_delay}s, shutdown_timeout={self.agent_shutdown_timeout}s"
        )
    
    async def _create_service_instance(self) -> AgentOrchestrator:
        """
        Create a new orchestrator instance.
        
        Returns:
            Configured AgentOrchestrator instance
        
        Raises:
            ServiceInitializationError: If orchestrator creation fails
        """
        try:
            logger.info("Creating orchestrator instance")
            
            # Create orchestrator with base configuration
            orchestrator = AgentOrchestrator(
                max_agents=self.max_agents,
                namespace=self.communication_namespace,
                spawn_delay=self.agent_spawn_delay,
                shutdown_timeout=self.agent_shutdown_timeout
            )
            
            logger.info("Orchestrator instance created successfully")
            return orchestrator
            
        except Exception as e:
            logger.error(f"Failed to create orchestrator instance: {str(e)}")
            raise ServiceInitializationError(self.name, "Failed to create orchestrator instance", e)
    
    async def _configure_service(self, service: AgentOrchestrator) -> None:
        """
        Configure the orchestrator service.
        
        Args:
            service: AgentOrchestrator instance to configure
            
        Raises:
            ConfigurationError: If orchestrator configuration fails
        """
        try:
            # Configure standard agent types
            agent_types = self.config.get("agent_types", {})
            for agent_type, type_config in agent_types.items():
                if type_config.get("enabled", True):
                    # Register agent type with orchestrator
                    service.register_agent_type(
                        agent_type=agent_type,
                        config=type_config
                    )
                    logger.info(f"Registered agent type: {agent_type}")
            
            # Configure communication channels
            channels_config = self.config.get("communication_channels", {})
            for channel, channel_config in channels_config.items():
                service.register_communication_channel(
                    channel=channel,
                    config=channel_config
                )
                logger.info(f"Registered communication channel: {channel}")
            
            # Configure agent recovery strategies
            recovery_config = self.config.get("recovery_strategies", {})
            for strategy, strategy_config in recovery_config.items():
                service.register_recovery_strategy(
                    strategy=strategy,
                    config=strategy_config
                )
                logger.info(f"Registered recovery strategy: {strategy}")
            
            logger.info("Orchestrator configured successfully")
            
        except Exception as e:
            logger.error(f"Failed to configure orchestrator: {str(e)}")
            raise ConfigurationError(self.name, "Failed to configure orchestrator", e)
    
    async def _register_health_checks(self, service: AgentOrchestrator) -> None:
        """
        Register health checks for the orchestrator service.
        
        Args:
            service: AgentOrchestrator instance to register health checks for
        """
        # Define the main orchestrator health check
        async def orchestrator_health_check() -> bool:
            try:
                # Check orchestrator main subsystems
                if not service.is_ready():
                    logger.warning("Orchestrator not in ready state")
                    return False
                
                # Check if orchestrator can communicate properly
                if not await service.check_communication():
                    logger.warning("Orchestrator communication check failed")
                    return False
                
                return True
            except Exception as e:
                logger.warning(f"Orchestrator health check failed: {str(e)}")
                return False
        
        # Define agent state health check
        async def agent_state_health_check() -> bool:
            try:
                # Check health of managed agents
                agent_health = await service.check_agent_health()
                if not agent_health.get("overall_healthy", False):
                    unhealthy_count = agent_health.get("unhealthy_count", 0)
                    total_count = agent_health.get("total_count", 0)
                    logger.warning(f"Agent health check failed: {unhealthy_count}/{total_count} agents unhealthy")
                    
                    # We still return True if fewer than 25% of agents are unhealthy
                    # as the orchestrator itself is still functioning
                    if total_count > 0 and (unhealthy_count / total_count) < 0.25:
                        logger.info("Fewer than 25% agents unhealthy, orchestrator still considered healthy")
                        return True
                    return False
                
                return True
            except Exception as e:
                logger.warning(f"Agent state health check failed: {str(e)}")
                return False
        
        # Define resource usage health check
        async def resource_usage_health_check() -> bool:
            try:
                # Check resource usage of orchestrator and agents
                resource_state = await service.check_resource_usage()
                
                # If memory/CPU usage is too high, consider unhealthy
                if resource_state.get("memory_percent", 0) > 90:
                    logger.warning(f"Memory usage too high: {resource_state.get('memory_percent')}%")
                    return False
                
                if resource_state.get("cpu_percent", 0) > 90:
                    logger.warning(f"CPU usage too high: {resource_state.get('cpu_percent')}%")
                    return False
                
                return True
            except Exception as e:
                logger.warning(f"Resource usage health check failed: {str(e)}")
                return False
        
        # Register all health checks
        self.register_health_check(orchestrator_health_check)
        self.register_health_check(agent_state_health_check)
        self.register_health_check(resource_usage_health_check)
        
        logger.info(f"Registered {len(self.health_checks)} health checks for orchestrator")
    
    async def _setup_shutdown_hooks(self, service: AgentOrchestrator) -> None:
        """
        Set up graceful shutdown hooks for the orchestrator service.
        
        Args:
            service: AgentOrchestrator instance to set up shutdown hooks for
        """
        # Define the shutdown hook for the orchestrator
        async def orchestrator_shutdown() -> None:
            try:
                logger.info("Orchestrator graceful shutdown initiated")
                
                # Cancel health check task if running
                if self.health_check_task and not self.health_check_task.done():
                    self.health_check_task.cancel()
                    try:
                        await self.health_check_task
                    except asyncio.CancelledError:
                        pass
                
                # First, initiate agent shutdown sequence
                logger.info("Stopping managed agents...")
                await service.stop_all_agents(timeout=self.agent_shutdown_timeout)
                
                # Then, stop the orchestrator itself
                logger.info("Stopping orchestrator service...")
                await service.shutdown()
                
                logger.info("Orchestrator shutdown complete")
                
            except Exception as e:
                logger.error(f"Error during orchestrator shutdown: {str(e)}")
        
        # Register the shutdown hook
        self.register_shutdown_hook(orchestrator_shutdown)
        
        logger.info("Registered shutdown hook for orchestrator")
    
    async def start(self) -> bool:
        """
        Start the orchestrator service.
        
        This implementation starts a periodic health check task in addition
        to the standard startup process, and initiates agent startup if configured.
        
        Returns:
            True if startup was successful, False otherwise
        """
        result = await super().start()
        
        if not result:
            return False
        
        try:
            # Start periodic health check
            if self.config.get("enable_periodic_health_check", True):
                self.health_check_task = asyncio.create_task(self._periodic_health_check())
                logger.info(f"Started periodic health check task (interval: {self.health_check_interval}s)")
            
            # Start initial agents if configured
            if self.config.get("auto_start_agents", True):
                auto_start_count = min(self.config.get("auto_start_count", 3), self.max_agents)
                if auto_start_count > 0:
                    logger.info(f"Auto-starting {auto_start_count} agents")
                    # Get auto-start agent types from config, or use default
                    agent_types = self.config.get("auto_start_types", ["trader", "analyzer", "monitor"])
                    
                    # Start agents asynchronously
                    asyncio.create_task(self._start_initial_agents(auto_start_count, agent_types))
            
            return True
            
        except Exception as e:
            logger.error(f"Error during orchestrator startup: {str(e)}")
            return False
    
    async def _start_initial_agents(self, count: int, agent_types: List[str]) -> None:
        """
        Start initial agents.
        
        Args:
            count: Number of agents to start
            agent_types: Types of agents to start
        """
        try:
            if not self.service:
                logger.error("Cannot start agents: Orchestrator not initialized")
                return
            
            # Distribute agent types evenly
            agents_to_start = []
            while len(agents_to_start) < count:
                for agent_type in agent_types:
                    if len(agents_to_start) < count:
                        agents_to_start.append(agent_type)
            
            # Start each agent with a delay to avoid overwhelming the system
            for i, agent_type in enumerate(agents_to_start):
                logger.info(f"Starting agent {i+1}/{count}: {agent_type}")
                await self.service.start_agent(agent_type)
                
                # Sleep between agent starts to allow resources to stabilize
                await asyncio.sleep(self.agent_spawn_delay)
            
            logger.info(f"Successfully started {count} initial agents")
            
        except Exception as e:
            logger.error(f"Error starting initial agents: {str(e)}")
    
    async def _periodic_health_check(self) -> None:
        """
        Run periodic health checks for the orchestrator.
        
        This task runs indefinitely until cancelled during shutdown.
        """
        try:
            while True:
                healthy = await self.health_check()
                if not healthy:
                    logger.warning(f"Periodic health check for {self.name} failed")
                    
                    # Attempt self-recovery if configured
                    if self.config.get("enable_self_recovery", True):
                        await self._attempt_self_recovery()
                
                # Wait for the next check interval
                await asyncio.sleep(self.health_check_interval)
                
        except asyncio.CancelledError:
            logger.info(f"Periodic health check task for {self.name} cancelled")
        except Exception as e:
            logger.error(f"Error in periodic health check for {self.name}: {str(e)}")
    
    async def _attempt_self_recovery(self) -> None:
        """Attempt to recover orchestrator from unhealthy state."""
        if not self.service:
            return
            
        try:
            logger.info("Attempting orchestrator self-recovery")
            
            # Check and restart communication if needed
            if not await self.service.check_communication():
                logger.info("Restarting communication channels")
                await self.service.restart_communication()
            
            # Check and recover unhealthy agents
            agent_health = await self.service.check_agent_health()
            unhealthy_agents = agent_health.get("unhealthy_agents", [])
            
            if unhealthy_agents:
                logger.info(f"Attempting to recover {len(unhealthy_agents)} unhealthy agents")
                for agent_id in unhealthy_agents:
                    logger.info(f"Restarting agent {agent_id}")
                    await self.service.restart_agent(agent_id)
                    # Short delay between restarts
                    await asyncio.sleep(1.0)
            
            logger.info("Self-recovery attempt completed")
            
        except Exception as e:
            logger.error(f"Error during self-recovery: {str(e)}")
    
    async def _default_health_check(self, service: AgentOrchestrator) -> bool:
        """
        Default health check implementation for orchestrator.
        
        Args:
            service: AgentOrchestrator instance to check
            
        Returns:
            True if the service is healthy, False otherwise
        """
        try:
            # Basic health check just verifies the orchestrator is running
            return service is not None and service.is_running()
        except Exception as e:
            logger.warning(f"Default orchestrator health check failed: {str(e)}")
            return False 