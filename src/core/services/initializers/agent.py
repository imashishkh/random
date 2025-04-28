"""
Agent Service Initializer

This module provides the initializer component for agent services in the
Forex Trading system, handling their lifecycle, health checks, and 
inter-agent communication setup.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Type

from ...agents.base import Agent, AgentRegistry
from ...common.metrics import Metrics, MetricsRegistry
from ...config import ConfigResolver
from .base import BaseServiceInitializer, ConfigurationError

logger = logging.getLogger(__name__)

class AgentInitializer(BaseServiceInitializer):
    """
    Initializer for agent services in the Forex Trading system.
    
    Handles the creation, configuration, health checks, and inter-agent
    communication setup for trading agents.
    """
    
    def __init__(
        self, 
        agent_type: Type[Agent],
        name: Optional[str] = None,
        config_namespace: str = "agents",
        dependent_services: Optional[List[str]] = None,
        metrics_registry: Optional[MetricsRegistry] = None
    ):
        """
        Initialize a new agent service initializer.
        
        Args:
            agent_type: The specific type of agent to initialize
            name: Optional name for this initializer component
            config_namespace: Configuration namespace for agent settings
            dependent_services: Names of services this agent depends on
            metrics_registry: Registry for collecting metrics
        """
        super().__init__(
            name=name or f"{agent_type.__name__}Initializer",
            config_namespace=config_namespace,
            dependent_services=dependent_services,
            metrics_registry=metrics_registry
        )
        self._agent_type = agent_type
        self._agent_instance = None
        
        # Add agent-specific metrics
        self.metrics.add_metric("agent_messages_processed", "counter", 
                               description=f"Number of messages processed by {self._agent_type.__name__}")
        self.metrics.add_metric("agent_decisions_made", "counter",
                               description=f"Number of trading decisions made by {self._agent_type.__name__}")
        self.metrics.add_metric("agent_processing_time", "histogram",
                               description=f"Time taken to process messages by {self._agent_type.__name__}")
    
    def _resolve_configuration(self) -> Dict[str, Any]:
        """
        Resolve configuration for the agent from the configuration system.
        
        Returns:
            Dict containing configuration parameters for the agent
        
        Raises:
            ConfigurationError: If required configuration is missing
        """
        logger.debug(f"Resolving configuration for {self._agent_type.__name__}")
        
        # Get agent-specific configuration from config namespace
        agent_name = self._agent_type.__name__.lower()
        agent_config = ConfigResolver.get_config(f"{self.config_namespace}.{agent_name}")
        
        if not agent_config:
            raise ConfigurationError(
                service_name=self.name,
                reason=f"Missing configuration for agent {agent_name}",
            )
        
        # Ensure required fields are present
        required_fields = ["enabled", "communication_channels"]
        for field in required_fields:
            if field not in agent_config:
                raise ConfigurationError(
                    service_name=self.name,
                    reason=f"Missing required configuration field '{field}' for agent {agent_name}"
                )
        
        # Verify agent is enabled
        if not agent_config.get("enabled", False):
            logger.info(f"Agent {agent_name} is disabled in configuration. Skipping initialization.")
            return {}
            
        return agent_config
    
    def _create_service_instance(self, config: Dict[str, Any]) -> Agent:
        """
        Create an instance of the agent service.
        
        Args:
            config: Configuration for the agent
            
        Returns:
            Initialized agent instance
            
        Raises:
            ServiceInitializationError: If agent creation fails
        """
        try:
            logger.info(f"Creating instance of {self._agent_type.__name__}")
            
            # Create agent instance with configuration
            agent_instance = self._agent_type(config=config)
            
            # Register with agent registry for service discovery
            AgentRegistry.register(agent_instance)
            
            self._agent_instance = agent_instance
            return agent_instance
        except Exception as e:
            logger.exception(f"Failed to create {self._agent_type.__name__} instance")
            raise ServiceInitializationError(
                service_name=self.name,
                reason=f"Failed to create agent instance: {str(e)}",
                cause=e
            )
    
    def _configure_service(self, service: Agent, config: Dict[str, Any]) -> None:
        """
        Configure the agent service with the resolved configuration.
        
        Args:
            service: Agent instance to configure
            config: Configuration parameters
            
        Raises:
            ServiceInitializationError: If configuration fails
        """
        try:
            logger.debug(f"Configuring {self._agent_type.__name__}")
            
            # Configure communication channels
            comm_channels = config.get("communication_channels", [])
            for channel in comm_channels:
                service.subscribe_to_channel(channel)
                logger.debug(f"Agent {service.name} subscribed to channel: {channel}")
            
            # Configure agent-specific settings
            service.configure(config)
            
            # Attach metrics collectors to agent
            service.set_metrics_collector(self.metrics)
            
            logger.info(f"Successfully configured {self._agent_type.__name__}")
        except Exception as e:
            logger.exception(f"Failed to configure {self._agent_type.__name__}")
            raise ServiceInitializationError(
                service_name=self.name,
                reason=f"Failed to configure agent: {str(e)}",
                cause=e
            )
    
    def _register_health_checks(self, service: Agent) -> None:
        """
        Register health check callbacks for the agent service.
        
        Args:
            service: Agent instance to register health checks for
        """
        logger.debug(f"Registering health checks for {self._agent_type.__name__}")
        
        # Register basic agent health check
        self.register_health_check(
            "agent_alive", 
            lambda: self._agent_health_check(service)
        )
        
        # Register communication channels health check
        self.register_health_check(
            "communication_channels",
            lambda: self._check_communication_channels(service)
        )
    
    def _setup_shutdown_hooks(self, service: Agent) -> None:
        """
        Set up graceful shutdown hooks for the agent service.
        
        Args:
            service: Agent instance to set up shutdown hooks for
        """
        logger.debug(f"Setting up shutdown hooks for {self._agent_type.__name__}")
        
        def graceful_shutdown():
            logger.info(f"Gracefully shutting down {service.name}")
            
            # Unsubscribe from all channels
            service.unsubscribe_from_all_channels()
            
            # Allow agent to complete any pending work
            service.finalize()
            
            # Unregister from agent registry
            AgentRegistry.unregister(service.name)
            
            logger.info(f"Agent {service.name} shutdown complete")
        
        # Register the shutdown hook
        self.register_shutdown_hook(graceful_shutdown)
    
    def _agent_health_check(self, agent: Agent) -> bool:
        """
        Perform a health check on the agent.
        
        Args:
            agent: Agent instance to check
            
        Returns:
            True if agent is healthy, False otherwise
        """
        # Check if agent is initialized and ready
        if not agent or not agent.is_ready():
            logger.warning(f"Agent {agent.name if agent else 'unknown'} health check failed: Not ready")
            return False
        
        # Check if agent has been inactive too long
        if agent.get_inactivity_time() > agent.max_inactivity_time:
            logger.warning(f"Agent {agent.name} health check failed: Inactive for too long")
            return False
            
        return True
    
    def _check_communication_channels(self, agent: Agent) -> bool:
        """
        Check the health of agent's communication channels.
        
        Args:
            agent: Agent instance to check
            
        Returns:
            True if communication channels are healthy, False otherwise
        """
        # Verify each channel the agent is subscribed to
        for channel in agent.subscribed_channels:
            if not agent.is_channel_active(channel):
                logger.warning(f"Agent {agent.name} health check failed: Channel {channel} inactive")
                return False
                
        return True
        
    def start(self) -> bool:
        """
        Start the agent service.
        
        Returns:
            True if started successfully, False otherwise
        """
        if not super().start():
            return False
            
        if not self.service or not isinstance(self.service, Agent):
            logger.error(f"Cannot start agent: Service not initialized correctly")
            return False
            
        try:
            # Activate the agent
            self.service.activate()
            
            logger.info(f"Agent {self.service.name} started successfully")
            return True
        except Exception as e:
            logger.exception(f"Failed to start agent {self.service.name}")
            self.metrics.record_event("agent_start_failure", {"error": str(e)})
            return False
    
    def stop(self) -> bool:
        """
        Stop the agent service.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.service:
            return True
            
        try:
            # Deactivate the agent
            self.service.deactivate()
            
            logger.info(f"Agent {self.service.name} stopped successfully")
            return super().stop()
        except Exception as e:
            logger.exception(f"Failed to stop agent {self.service.name}")
            self.metrics.record_event("agent_stop_failure", {"error": str(e)})
            return False 