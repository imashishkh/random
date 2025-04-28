"""
Tests for the AgentInitializer class.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.core.services.initializers import AgentInitializer, ConfigurationError
from src.agents.registry import AgentRegistry
from src.metrics import Metrics


class TestAgentInitializer:
    """Test suite for the AgentInitializer class."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        agent = MagicMock()
        agent.name = "test_agent"
        agent.agent_type = "test_type"
        return agent

    @pytest.fixture
    def mock_config_resolver(self):
        """Create a mock config resolver for testing."""
        resolver = MagicMock()
        resolver.get_config.return_value = {
            "name": "test_agent",
            "enabled": True,
            "communication": {
                "channels": ["channel1", "channel2"]
            },
            "parameters": {
                "param1": "value1",
                "param2": "value2"
            }
        }
        return resolver

    @pytest.fixture
    def mock_metrics_registry(self):
        """Create a mock metrics registry for testing."""
        metrics = MagicMock(spec=Metrics)
        return metrics

    @pytest.fixture
    def initializer(self, mock_config_resolver, mock_metrics_registry):
        """Create an instance of AgentInitializer for testing."""
        with patch("src.core.services.initializers.agent.ConfigResolver", 
                  return_value=mock_config_resolver):
            return AgentInitializer(
                agent_type="test_type",
                name="test_agent",
                config_namespace="agents.test_type",
                dependent_services=[],
                metrics_registry=mock_metrics_registry
            )

    def test_init(self, initializer, mock_metrics_registry):
        """Test initializer instantiation."""
        assert initializer.agent_type == "test_type"
        assert initializer.name == "test_agent"
        assert initializer.config_namespace == "agents.test_type"
        assert initializer.dependent_services == []
        assert initializer.metrics_registry == mock_metrics_registry
        assert initializer.agent is None

    def test_resolve_configuration_success(self, initializer, mock_config_resolver):
        """Test configuration resolution with valid config."""
        config = initializer._resolve_configuration()
        assert mock_config_resolver.get_config.called
        assert config["name"] == "test_agent"
        assert config["enabled"] is True
        assert "communication" in config
        assert "parameters" in config

    def test_resolve_configuration_missing_fields(self, initializer, mock_config_resolver):
        """Test configuration resolution with missing required fields."""
        # Remove required fields
        mock_config_resolver.get_config.return_value = {
            "name": "test_agent",
            # missing "enabled" field
            "parameters": {}
        }
        
        with pytest.raises(ConfigurationError):
            initializer._resolve_configuration()

    @patch("src.core.services.initializers.agent.Agent")
    def test_create_service_instance(self, mock_agent_class, initializer, mock_config_resolver):
        """Test creation of agent service instance."""
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance
        
        config = initializer._resolve_configuration()
        initializer._create_service_instance(config)
        
        # Verify agent was created with correct parameters
        mock_agent_class.assert_called_once()
        assert initializer.agent == mock_agent_instance
        
        # Verify agent was registered with AgentRegistry
        with patch("src.core.services.initializers.agent.AgentRegistry") as mock_registry:
            registry_instance = MagicMock()
            mock_registry.return_value = registry_instance
            
            initializer._create_service_instance(config)
            registry_instance.register_agent.assert_called_once_with(initializer.agent)

    def test_configure_service(self, initializer, mock_agent):
        """Test agent service configuration."""
        initializer.agent = mock_agent
        config = {
            "communication": {
                "channels": ["channel1", "channel2"]
            },
            "parameters": {
                "param1": "value1",
                "param2": "value2"
            }
        }
        
        initializer._configure_service(config)
        
        # Verify communication channels were configured
        mock_agent.setup_communication_channels.assert_called_once_with(["channel1", "channel2"])
        
        # Verify parameters were configured
        mock_agent.configure.assert_called_once_with({"param1": "value1", "param2": "value2"})
        
        # Verify metrics were attached
        mock_agent.attach_metrics_collector.assert_called_once_with(initializer.metrics_registry)

    def test_register_health_checks(self, initializer, mock_agent):
        """Test health check registration."""
        initializer.agent = mock_agent
        
        initializer._register_health_checks()
        
        # Verify health check callbacks were registered
        mock_agent.register_health_check.assert_called()

    def test_agent_health_check(self, initializer, mock_agent):
        """Test agent health check function."""
        initializer.agent = mock_agent
        mock_agent.is_healthy.return_value = True
        
        result = initializer._agent_health_check()
        
        assert result.status == "pass"
        mock_agent.is_healthy.assert_called_once()
        
        # Test failing health check
        mock_agent.is_healthy.return_value = False
        result = initializer._agent_health_check()
        
        assert result.status == "fail"

    def test_check_communication_channels(self, initializer, mock_agent):
        """Test communication channels health check function."""
        initializer.agent = mock_agent
        mock_agent.check_communication_channels.return_value = True
        
        result = initializer._check_communication_channels()
        
        assert result.status == "pass"
        mock_agent.check_communication_channels.assert_called_once()
        
        # Test failing health check
        mock_agent.check_communication_channels.return_value = False
        result = initializer._check_communication_channels()
        
        assert result.status == "fail"

    def test_setup_shutdown_hooks(self, initializer, mock_agent):
        """Test shutdown hooks setup."""
        initializer.agent = mock_agent
        
        initializer._setup_shutdown_hooks()
        
        # Verify shutdown hook was registered
        mock_agent.register_shutdown_hook.assert_called_once()

    @patch("src.core.services.initializers.agent.logging")
    def test_start(self, mock_logging, initializer, mock_agent, mock_config_resolver):
        """Test agent service start."""
        initializer.agent = mock_agent
        
        with patch.object(initializer, '_resolve_configuration', return_value={"enabled": True}), \
             patch.object(initializer, '_create_service_instance'), \
             patch.object(initializer, '_configure_service'), \
             patch.object(initializer, '_register_health_checks'), \
             patch.object(initializer, '_setup_shutdown_hooks'):
            
            initializer.start()
            
            # Verify all methods were called
            initializer._resolve_configuration.assert_called_once()
            initializer._create_service_instance.assert_called_once()
            initializer._configure_service.assert_called_once()
            initializer._register_health_checks.assert_called_once()
            initializer._setup_shutdown_hooks.assert_called_once()
            
            # Verify agent was started
            mock_agent.start.assert_called_once()
            mock_logging.info.assert_called()

    def test_start_disabled_agent(self, initializer, mock_logging):
        """Test agent service start when agent is disabled in config."""
        with patch.object(initializer, '_resolve_configuration', return_value={"enabled": False}), \
             patch("src.core.services.initializers.agent.logging.info") as mock_log:
            
            initializer.start()
            
            # Verify only configuration was resolved but agent not started
            initializer._resolve_configuration.assert_called_once()
            mock_log.assert_called_with(f"Agent {initializer.name} is disabled in configuration, not starting")

    @patch("src.core.services.initializers.agent.logging")
    def test_stop(self, mock_logging, initializer, mock_agent):
        """Test agent service stop."""
        initializer.agent = mock_agent
        
        initializer.stop()
        
        # Verify agent was stopped
        mock_agent.stop.assert_called_once()
        mock_logging.info.assert_called()

    def test_stop_no_agent(self, initializer, mock_logging):
        """Test agent service stop when no agent is initialized."""
        initializer.agent = None
        
        with patch("src.core.services.initializers.agent.logging.info") as mock_log:
            initializer.stop()
            
            # Verify appropriate log message
            mock_log.assert_called_with(f"Agent {initializer.name} was not started, nothing to stop") 