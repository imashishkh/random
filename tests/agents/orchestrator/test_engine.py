"""
Unit tests for the Agent Swarm Orchestrator engine.
"""

import unittest
import asyncio
import os
import tempfile
import json
import sys
from unittest.mock import patch, MagicMock

# Mock required imports
sys.modules['langchain'] = MagicMock()
sys.modules['langchain.schema'] = MagicMock()
sys.modules['src'] = MagicMock()
sys.modules['src.agents'] = MagicMock()
sys.modules['src.agents.health'] = MagicMock()
sys.modules['src.agents.health'].get_health_monitor = MagicMock(return_value=MagicMock())

# Path the module to force these imports to work
with patch.dict('sys.modules'):
    from src.agents.orchestrator.engine import (
        AgentSwarmOrchestrator, 
        AgentMetadata, 
        AgentStatus,
        get_orchestrator
    )


class TestAgentSwarmOrchestrator(unittest.IsolatedAsyncioTestCase):
    """Test cases for the AgentSwarmOrchestrator class."""
    
    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Create a temporary config file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, 'test_config.json')
        
        # Simple test configuration
        test_config = {
            "log_level": "DEBUG",
            "agent_types": {
                "test_agent": {"schema": {}},
                "technical_analysis": {"schema": {}}
            },
            "health_check": {
                "interval": 5,
                "heartbeat_timeout": 10,
                "max_restart_attempts": 2
            }
        }
        
        # Write config to temp file
        with open(self.config_path, 'w') as f:
            json.dump(test_config, f)
        
        # Create orchestrator with test config
        with patch('src.agents.health.get_health_monitor') as mock_get_health_monitor:
            mock_health_monitor = MagicMock()
            mock_get_health_monitor.return_value = mock_health_monitor
            self.orchestrator = AgentSwarmOrchestrator(config_path=self.config_path)
    
    async def asyncTearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()
    
    async def test_initialize_orchestrator(self):
        """Test orchestrator initialization."""
        # Verify config was loaded
        self.assertEqual(self.orchestrator._config['log_level'], 'DEBUG')
        self.assertIn('test_agent', self.orchestrator._config['agent_types'])
        self.assertEqual(self.orchestrator._config['health_check']['interval'], 5)
        
        # Verify registry is empty
        self.assertEqual(len(self.orchestrator._registry), 0)
        
        # Verify event callbacks are initialized
        self.assertIn('agent_registered', self.orchestrator._event_callbacks)
        self.assertIn('agent_status_changed', self.orchestrator._event_callbacks)
    
    async def test_register_agent(self):
        """Test agent registration."""
        # Register a test agent
        agent_id = 'test-agent-1'
        agent_type = 'test_agent'
        agent_name = 'Test Agent 1'
        agent_config = {'param1': 'value1', 'param2': 'value2'}
        
        metadata = await self.orchestrator.register_agent(
            agent_id=agent_id,
            agent_type=agent_type,
            name=agent_name,
            config=agent_config
        )
        
        # Verify agent was registered
        self.assertIn(agent_id, self.orchestrator._registry)
        self.assertEqual(metadata.id, agent_id)
        self.assertEqual(metadata.name, agent_name)
        self.assertEqual(metadata.agent_type, agent_type)
        self.assertEqual(metadata.status, AgentStatus.PENDING)
        self.assertEqual(metadata.config, agent_config)
        
        # Verify agent is retrievable
        retrieved = await self.orchestrator.get_agent_metadata(agent_id)
        self.assertEqual(retrieved, metadata)
        
        # Verify duplicate registration fails
        with self.assertRaises(ValueError):
            await self.orchestrator.register_agent(
                agent_id=agent_id,
                agent_type=agent_type,
                name=agent_name,
                config=agent_config
            )
    
    async def test_update_agent_status(self):
        """Test updating agent status."""
        # Register a test agent
        agent_id = 'test-agent-2'
        metadata = await self.orchestrator.register_agent(
            agent_id=agent_id,
            agent_type='test_agent',
            name='Test Agent 2',
            config={}
        )
        
        # Update status
        updated = await self.orchestrator.update_agent_status(
            agent_id=agent_id,
            status=AgentStatus.RUNNING
        )
        
        # Verify status was updated
        self.assertEqual(updated.status, AgentStatus.RUNNING)
        self.assertNotEqual(updated.updated_at, metadata.updated_at)
        
        # Verify unknown agent fails
        with self.assertRaises(KeyError):
            await self.orchestrator.update_agent_status(
                agent_id='unknown-agent',
                status=AgentStatus.RUNNING
            )
    
    async def test_deregister_agent(self):
        """Test agent deregistration."""
        # Register a test agent
        agent_id = 'test-agent-3'
        await self.orchestrator.register_agent(
            agent_id=agent_id,
            agent_type='test_agent',
            name='Test Agent 3',
            config={}
        )
        
        # Deregister agent
        await self.orchestrator.deregister_agent(agent_id)
        
        # Verify agent was deregistered
        self.assertNotIn(agent_id, self.orchestrator._registry)
        
        # Verify unknown agent fails
        with self.assertRaises(KeyError):
            await self.orchestrator.deregister_agent('unknown-agent')
    
    async def test_record_heartbeat(self):
        """Test recording agent heartbeats."""
        # Register a test agent
        agent_id = 'test-agent-4'
        metadata = await self.orchestrator.register_agent(
            agent_id=agent_id,
            agent_type='test_agent',
            name='Test Agent 4',
            config={}
        )
        
        # Record heartbeat
        updated = await self.orchestrator.record_agent_heartbeat(agent_id)
        
        # Verify heartbeat was recorded
        self.assertIsNotNone(updated.last_heartbeat)
        self.assertNotEqual(updated.updated_at, metadata.updated_at)
        
        # Verify unknown agent returns None
        result = await self.orchestrator.record_agent_heartbeat('unknown-agent')
        self.assertIsNone(result)
    
    async def test_query_agents(self):
        """Test querying agents by status and type."""
        # Register multiple agents
        await self.orchestrator.register_agent(
            agent_id='test-agent-5',
            agent_type='test_agent',
            name='Test Agent 5',
            config={}
        )
        
        await self.orchestrator.register_agent(
            agent_id='test-agent-6',
            agent_type='technical_analysis',
            name='Test Agent 6',
            config={}
        )
        
        await self.orchestrator.update_agent_status(
            agent_id='test-agent-5',
            status=AgentStatus.RUNNING
        )
        
        # Query by status
        running_agents = await self.orchestrator.get_agents_by_status(AgentStatus.RUNNING)
        pending_agents = await self.orchestrator.get_agents_by_status(AgentStatus.PENDING)
        
        self.assertEqual(len(running_agents), 1)
        self.assertEqual(running_agents[0].id, 'test-agent-5')
        self.assertEqual(len(pending_agents), 1)
        self.assertEqual(pending_agents[0].id, 'test-agent-6')
        
        # Query by type
        test_agents = await self.orchestrator.get_agents_by_type('test_agent')
        tech_agents = await self.orchestrator.get_agents_by_type('technical_analysis')
        
        self.assertEqual(len(test_agents), 1)
        self.assertEqual(test_agents[0].id, 'test-agent-5')
        self.assertEqual(len(tech_agents), 1)
        self.assertEqual(tech_agents[0].id, 'test-agent-6')
        
        # Get all agents
        all_agents = await self.orchestrator.get_all_agents()
        self.assertEqual(len(all_agents), 2)
    
    async def test_event_callbacks(self):
        """Test event callback registration and notification."""
        # Create a mock callback
        callback_results = []
        
        async def test_callback(agent_id, data):
            callback_results.append((agent_id, data))
        
        # Register callback
        await self.orchestrator.on_event('agent_registered', test_callback)
        
        # Trigger event
        agent_id = 'test-agent-7'
        await self.orchestrator.register_agent(
            agent_id=agent_id,
            agent_type='test_agent',
            name='Test Agent 7',
            config={}
        )
        
        # Verify callback was invoked
        self.assertEqual(len(callback_results), 1)
        self.assertEqual(callback_results[0][0], agent_id)
        self.assertEqual(callback_results[0][1].id, agent_id)
    
    async def test_state_serialization(self):
        """Test serializing and deserializing orchestrator state."""
        # Register an agent
        agent_id = 'test-agent-8'
        await self.orchestrator.register_agent(
            agent_id=agent_id,
            agent_type='test_agent',
            name='Test Agent 8',
            config={'param': 'value'}
        )
        
        # Update status
        await self.orchestrator.update_agent_status(
            agent_id=agent_id,
            status=AgentStatus.RUNNING
        )
        
        # Save state
        state_file = os.path.join(self.temp_dir.name, 'test_state.json')
        await self.orchestrator.save_state(state_file)
        
        # Verify state file exists
        self.assertTrue(os.path.exists(state_file))
        
        # Create a new orchestrator
        with patch('src.agents.health.get_health_monitor') as mock_get_health_monitor:
            mock_health_monitor = MagicMock()
            mock_get_health_monitor.return_value = mock_health_monitor
            new_orchestrator = AgentSwarmOrchestrator(config_path=self.config_path)
        
        # Load state
        await new_orchestrator.load_state(state_file)
        
        # Verify agent was loaded
        self.assertIn(agent_id, new_orchestrator._registry)
        loaded_agent = await new_orchestrator.get_agent_metadata(agent_id)
        self.assertEqual(loaded_agent.id, agent_id)
        self.assertEqual(loaded_agent.status, AgentStatus.RUNNING)
        self.assertEqual(loaded_agent.config, {'param': 'value'})
    
    @patch('src.agents.orchestrator.engine.AgentSwarmOrchestrator')
    def test_singleton_get_orchestrator(self, mock_class):
        """Test the singleton get_orchestrator function."""
        # Setup mock
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        
        # Reset singleton for testing
        import src.agents.orchestrator.engine
        src.agents.orchestrator.engine._orchestrator_instance = None
        
        # Get orchestrator instances
        instance1 = get_orchestrator()
        instance2 = get_orchestrator()
        
        # Verify same instance was returned
        self.assertEqual(instance1, instance2)
        
        # Verify constructor was called once
        mock_class.assert_called_once()


if __name__ == '__main__':
    unittest.main() 