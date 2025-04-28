"""
Unit tests for the Boot Configuration Manager.
"""

import os
import sys
import json
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from src.utils.boot_config_manager import (
    BootConfigManager,
    BootConfig,
    ServiceConfig,
    HealthCheckConfig,
    HealthCheckType
)

# Sample configuration for testing
SAMPLE_CONFIG = {
    "boot": {
        "startup_sequence": ["database", "api", "trading_engine"],
        "dependency_timeout": 15,
        "retry_attempts": 2,
        "retry_backoff": 1.5,
        "initial_retry_delay": 0.5,
        "force_boot": False,
        "health_check_timeout": 5,
        "services": {
            "database": {
                "enabled": True,
                "critical": True,
                "health_check": {
                    "type": "database",
                    "endpoint": "sqlite://test.db",
                    "timeout": 5
                },
                "dependencies": []
            },
            "api": {
                "enabled": True,
                "critical": True,
                "health_check": {
                    "type": "http",
                    "endpoint": "http://localhost:5000/health",
                    "expected_status": 200
                },
                "dependencies": ["database"]
            },
            "trading_engine": {
                "enabled": True,
                "critical": False,
                "health_check": {
                    "type": "custom",
                    "custom_check": "tests.utils.test_boot_config_manager.mock_health_check",
                    "timeout": 5
                },
                "dependencies": ["database", "api"]
            }
        }
    }
}

# Mock functions for testing
async def mock_health_check(**kwargs):
    """Mock health check that always returns True."""
    return True

async def mock_failing_health_check(**kwargs):
    """Mock health check that always returns False."""
    return False

class MockConfigManager:
    """Mock ConfigManager for testing."""
    
    def __init__(self, config=None):
        self.config = config or {}
    
    def get_config(self, section, default=None):
        """Get a section from the configuration."""
        return self.config.get(section, default)

@pytest.fixture
def boot_manager():
    """Create a BootConfigManager with sample configuration."""
    config_manager = MockConfigManager(SAMPLE_CONFIG)
    return BootConfigManager(config_manager)

class TestBootConfigManager:
    """Test the BootConfigManager class."""
    
    def test_initialization(self, boot_manager):
        """Test that the BootConfigManager initializes correctly."""
        assert boot_manager is not None
        assert isinstance(boot_manager.boot_config, BootConfig)
        assert len(boot_manager.boot_config.startup_sequence) == 3
        assert len(boot_manager.boot_config.services) == 3
        assert boot_manager.boot_config.retry_attempts == 2
    
    def test_load_boot_config(self, boot_manager):
        """Test loading boot configuration."""
        # Already loaded in fixture, but we can test the result
        assert "database" in boot_manager.boot_config.services
        assert "api" in boot_manager.boot_config.services
        assert "trading_engine" in boot_manager.boot_config.services
        
        # Test specific config values
        assert boot_manager.boot_config.services["database"].critical == True
        assert boot_manager.boot_config.services["trading_engine"].critical == False
        assert boot_manager.boot_config.services["api"].health_check.type == HealthCheckType.HTTP
    
    def test_validate_boot_readiness_valid(self, boot_manager):
        """Test validation of valid boot configuration."""
        is_valid, missing = boot_manager.validate_boot_readiness()
        assert is_valid == True
        assert len(missing) == 0
    
    def test_validate_boot_readiness_missing_service(self, boot_manager):
        """Test validation when a service in startup_sequence is missing."""
        # Add a non-existent service to startup_sequence
        boot_manager.boot_config.startup_sequence.append("non_existent")
        
        is_valid, missing = boot_manager.validate_boot_readiness()
        assert is_valid == False
        assert len(missing) == 1
        assert missing[0].startswith("Service 'non_existent'")
    
    def test_validate_boot_readiness_missing_dependency(self, boot_manager):
        """Test validation when a dependency doesn't exist."""
        # Add a non-existent dependency
        boot_manager.boot_config.services["api"].dependencies.append("non_existent")
        
        is_valid, missing = boot_manager.validate_boot_readiness()
        assert is_valid == False
        assert len(missing) == 1
        assert missing[0].startswith("Service 'api' depends on")
    
    def test_check_circular_dependencies_none(self, boot_manager):
        """Test checking for circular dependencies when none exist."""
        assert boot_manager._check_circular_dependencies() == True
    
    def test_check_circular_dependencies_exists(self, boot_manager):
        """Test checking for circular dependencies when one exists."""
        # Create a circular dependency: api -> database -> trading_engine -> api
        boot_manager.boot_config.services["database"].dependencies.append("trading_engine")
        boot_manager.boot_config.services["trading_engine"].dependencies.append("api")
        
        assert boot_manager._check_circular_dependencies() == False
    
    def test_mask_sensitive_data(self, boot_manager):
        """Test masking of sensitive data."""
        test_data = {
            "api_key": "secret-key-value",
            "normal_value": "not-sensitive",
            "nested": {
                "password": "secret-password",
                "normal": "not-sensitive"
            },
            "list_of_dicts": [
                {"token": "secret-token", "name": "item1"},
                {"token": "another-token", "name": "item2"}
            ]
        }
        
        masked = boot_manager._mask_sensitive_data(test_data)
        
        # Check that sensitive values are masked
        assert masked["api_key"] == "***MASKED***"
        assert masked["normal_value"] == "not-sensitive"
        assert masked["nested"]["password"] == "***MASKED***"
        assert masked["nested"]["normal"] == "not-sensitive"
        assert masked["list_of_dicts"][0]["token"] == "***MASKED***"
        assert masked["list_of_dicts"][0]["name"] == "item1"
    
    def test_get_service_boot_order(self, boot_manager):
        """Test getting the correct boot order based on dependencies."""
        order = boot_manager.get_service_boot_order()
        
        # The order should respect dependencies:
        # database (no deps) -> api (depends on database) -> trading_engine (depends on both)
        assert order[0] == "database"
        assert order[1] == "api"
        assert order[2] == "trading_engine"
    
    def test_get_service_boot_order_different_sequence(self, boot_manager):
        """Test boot order with a different startup sequence."""
        # Change the sequence but keep dependencies the same
        boot_manager.boot_config.startup_sequence = ["trading_engine", "api", "database"]
        
        order = boot_manager.get_service_boot_order()
        
        # The order should still respect dependencies regardless of sequence
        assert order[0] == "database"
        # Next could be api, as it only depends on database
        assert order[1] == "api"
        # trading_engine should be last as it depends on both
        assert order[2] == "trading_engine"

    @pytest.mark.asyncio
    async def test_check_service_dependencies_all_healthy(self, boot_manager):
        """Test checking service dependencies when all are healthy."""
        # Mock the health checks to always succeed
        with patch('src.utils.boot_config_manager.http_health_check', 
                  new=AsyncMock(return_value=True)), \
             patch('src.utils.boot_config_manager.database_health_check', 
                  new=AsyncMock(return_value=True)), \
             patch('src.utils.boot_config_manager.custom_health_check', 
                  new=AsyncMock(return_value=True)):
            
            results = await boot_manager.check_service_dependencies()
            
            assert results["database"] == True
            assert results["api"] == True
            assert results["trading_engine"] == True
    
    @pytest.mark.asyncio
    async def test_check_service_dependencies_some_unhealthy(self, boot_manager):
        """Test checking service dependencies when some are unhealthy."""
        # Mock the health checks with different results
        with patch('src.utils.boot_config_manager.http_health_check', 
                  new=AsyncMock(return_value=False)), \
             patch('src.utils.boot_config_manager.database_health_check', 
                  new=AsyncMock(return_value=True)), \
             patch('src.utils.boot_config_manager.custom_health_check', 
                  new=AsyncMock(return_value=True)):
            
            results = await boot_manager.check_service_dependencies()
            
            assert results["database"] == True
            assert results["api"] == False  # This should be unhealthy
            assert results["trading_engine"] == True
    
    @pytest.mark.asyncio
    async def test_check_service_health_http(self, boot_manager):
        """Test checking health of an HTTP service."""
        service_config = boot_manager.boot_config.services["api"]
        
        with patch('src.utils.boot_config_manager.http_health_check', 
                  new=AsyncMock(return_value=True)) as mock_http:
            
            result = await boot_manager._check_service_health("api", service_config)
            
            assert result == True
            mock_http.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_service_health_database(self, boot_manager):
        """Test checking health of a database service."""
        service_config = boot_manager.boot_config.services["database"]
        
        with patch('src.utils.boot_config_manager.database_health_check', 
                  new=AsyncMock(return_value=True)) as mock_db:
            
            result = await boot_manager._check_service_health("database", service_config)
            
            assert result == True
            mock_db.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_service_health_custom(self, boot_manager):
        """Test checking health with a custom function."""
        service_config = boot_manager.boot_config.services["trading_engine"]
        
        with patch('src.utils.boot_config_manager.custom_health_check', 
                  new=AsyncMock(return_value=True)) as mock_custom:
            
            result = await boot_manager._check_service_health("trading_engine", service_config)
            
            assert result == True
            mock_custom.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_service_health_with_retries(self, boot_manager):
        """Test health check with retries on failure."""
        service_config = boot_manager.boot_config.services["api"]
        
        # Mock http_health_check to fail twice then succeed
        side_effects = [False, False, True]
        with patch('src.utils.boot_config_manager.http_health_check', 
                  new=AsyncMock(side_effect=side_effects)) as mock_http, \
             patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            
            result = await boot_manager._check_service_health("api", service_config)
            
            assert result == True
            assert mock_http.call_count == 3  # Called for each retry + initial attempt
            assert mock_sleep.call_count == 2  # Called for each retry
    
    @pytest.mark.asyncio
    async def test_check_service_health_all_retries_fail(self, boot_manager):
        """Test health check when all retries fail."""
        service_config = boot_manager.boot_config.services["api"]
        
        # Mock http_health_check to always fail
        with patch('src.utils.boot_config_manager.http_health_check', 
                  new=AsyncMock(return_value=False)) as mock_http, \
             patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            
            result = await boot_manager._check_service_health("api", service_config)
            
            assert result == False
            assert mock_http.call_count == 3  # Initial + 2 retries
            assert mock_sleep.call_count == 2  # Called for each retry 