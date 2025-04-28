"""
Tests for the DAG integration with agent orchestration.

This module contains unit tests for integrating the DAG model with the agent orchestrator,
including event handling, relationship discovery, and message monitoring.
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from src.visualization.dag.model import DAGModel, NodeData, EdgeData, AgentStatus
from src.visualization.dag.integration import AgentDAGIntegration


class TestAgentDAGIntegration(unittest.TestCase):
    """Tests for the AgentDAGIntegration class."""
    
    def setUp(self):
        """Set up the test environment."""
        self.dag_model = DAGModel()
        self.integration = AgentDAGIntegration(self.dag_model)
        
        # Mock the orchestrator module
        self.orchestrator_patcher = patch('src.visualization.dag.integration.AgentSwarmOrchestrator')
        self.mock_orchestrator_cls = self.orchestrator_patcher.start()
        self.mock_orchestrator = self.mock_orchestrator_cls.return_value
        
        # Mock Redis
        self.redis_patcher = patch('src.visualization.dag.integration.redis')
        self.mock_redis = self.redis_patcher.start()
        self.mock_redis_client = MagicMock()
        self.mock_redis.Redis.return_value = self.mock_redis_client
        
        # Create a mock pubsub
        self.mock_pubsub = MagicMock()
        self.mock_redis_client.pubsub.return_value = self.mock_pubsub
        
        # Setup method mocks
        self.mock_orchestrator.get_registered_agents = AsyncMock(return_value=[])
        self.mock_orchestrator.event_bus = MagicMock()
        self.mock_orchestrator.event_bus.subscribe = AsyncMock()
    
    def tearDown(self):
        """Clean up after the test."""
        self.orchestrator_patcher.stop()
        self.redis_patcher.stop()
    
    def test_init(self):
        """Test initialization of the integration."""
        self.assertEqual(self.integration.dag_model, self.dag_model)
        self.assertIsNone(self.integration.orchestrator)
    
    @patch('asyncio.create_task')
    async def test_connect_to_orchestrator(self, mock_create_task):
        """Test connecting to the orchestrator."""
        # Configure mock
        mock_agents = [
            {
                'id': 'agent1',
                'name': 'Agent 1',
                'agent_type': 'worker',
                'status': 'running',
                'config': {}
            },
            {
                'id': 'agent2',
                'name': 'Agent 2',
                'agent_type': 'analyzer',
                'status': 'pending',
                'config': {'dependencies': ['agent1']}
            }
        ]
        self.mock_orchestrator.get_registered_agents.return_value = mock_agents
        
        # Call the method
        await self.integration.connect_to_orchestrator()
        
        # Check that the orchestrator was accessed
        self.assertEqual(self.integration.orchestrator, self.mock_orchestrator)
        
        # Check that event subscriptions were set up
        self.assertEqual(self.mock_orchestrator.event_bus.subscribe.call_count, 5)
        
        # Check that the existing agents were loaded
        self.assertEqual(len(self.dag_model.nodes), 2)
        self.assertIn('agent1', self.dag_model.nodes)
        self.assertIn('agent2', self.dag_model.nodes)
        
        # Check that relationships were discovered (agent2 depends on agent1)
        self.assertIn(('agent1', 'agent2'), self.dag_model.edges)
        
        # Check that message monitoring was started
        mock_create_task.assert_called()
    
    async def test_on_agent_registered(self):
        """Test handling agent registration events."""
        # Create a mock agent
        agent_data = {
            'id': 'new_agent',
            'name': 'New Agent',
            'agent_type': 'processor',
            'status': 'initializing',
            'config': {}
        }
        
        # Call the method
        await self.integration._on_agent_registered(agent_data)
        
        # Check that the agent was added to the model
        self.assertIn('new_agent', self.dag_model.nodes)
        node = self.dag_model.nodes['new_agent']
        self.assertEqual(node.id, 'new_agent')
        self.assertEqual(node.name, 'New Agent')
        self.assertEqual(node.node_type, 'processor')
        self.assertEqual(node.status, AgentStatus.INITIALIZING)
    
    async def test_on_agent_deregistered(self):
        """Test handling agent deregistration events."""
        # Add a mock agent to the model
        node = NodeData(
            id='agent_to_remove',
            name='Agent To Remove',
            node_type='processor',
            status=AgentStatus.RUNNING
        )
        self.dag_model.add_node(node)
        
        # Call the method
        await self.integration._on_agent_deregistered({'id': 'agent_to_remove'})
        
        # Check that the agent was removed from the model
        self.assertNotIn('agent_to_remove', self.dag_model.nodes)
    
    async def test_on_agent_status_changed(self):
        """Test handling agent status change events."""
        # Add a mock agent to the model
        node = NodeData(
            id='status_agent',
            name='Status Agent',
            node_type='processor',
            status=AgentStatus.RUNNING
        )
        self.dag_model.add_node(node)
        
        # Call the method
        await self.integration._on_agent_status_changed({
            'id': 'status_agent',
            'status': 'paused'
        })
        
        # Check that the agent status was updated
        self.assertEqual(self.dag_model.nodes['status_agent'].status, AgentStatus.PAUSED)
    
    async def test_on_agent_heartbeat(self):
        """Test handling agent heartbeat events."""
        # Add a mock agent to the model
        node = NodeData(
            id='heartbeat_agent',
            name='Heartbeat Agent',
            node_type='processor',
            status=AgentStatus.RUNNING
        )
        self.dag_model.add_node(node)
        
        # Call the method
        await self.integration._on_agent_heartbeat({
            'id': 'heartbeat_agent',
            'timestamp': 123456789
        })
        
        # Check that the agent was updated (heartbeat doesn't change visible properties)
        self.assertIn('heartbeat_agent', self.dag_model.nodes)
        # In a real implementation, this might update lastHeartbeat in metadata
    
    async def test_on_agent_error(self):
        """Test handling agent error events."""
        # Add a mock agent to the model
        node = NodeData(
            id='error_agent',
            name='Error Agent',
            node_type='processor',
            status=AgentStatus.RUNNING
        )
        self.dag_model.add_node(node)
        
        # Call the method
        await self.integration._on_agent_error({
            'id': 'error_agent',
            'error': 'Test error message',
            'timestamp': 123456789
        })
        
        # Check that the agent status was updated
        self.assertEqual(self.dag_model.nodes['error_agent'].status, AgentStatus.FAILED)
    
    async def test_discover_relationships(self):
        """Test discovering relationships between agents."""
        # Set up some mock agents with dependencies
        agents = [
            {
                'id': 'agent1',
                'config': {}
            },
            {
                'id': 'agent2',
                'config': {'dependencies': ['agent1']}
            },
            {
                'id': 'agent3',
                'config': {'dependencies': ['agent1', 'agent2']}
            }
        ]
        
        # Add the agents to the model
        for agent in agents:
            node = NodeData(
                id=agent['id'],
                name=f"Agent {agent['id']}",
                node_type='test',
                status=AgentStatus.PENDING
            )
            self.dag_model.add_node(node)
        
        # Call the method
        self.integration._discover_relationships(agents)
        
        # Check that the relationships were discovered
        self.assertIn(('agent1', 'agent2'), self.dag_model.edges)
        self.assertIn(('agent1', 'agent3'), self.dag_model.edges)
        self.assertIn(('agent2', 'agent3'), self.dag_model.edges)
    
    @patch('src.visualization.dag.integration.json')
    async def test_simulate_message_passing(self, mock_json):
        """Test simulating message passing between agents."""
        # Add some nodes to the model
        node1 = NodeData(
            id='sender',
            name='Sender Agent',
            node_type='sender',
            status=AgentStatus.RUNNING
        )
        node2 = NodeData(
            id='receiver',
            name='Receiver Agent',
            node_type='receiver',
            status=AgentStatus.RUNNING
        )
        self.dag_model.add_node(node1)
        self.dag_model.add_node(node2)
        
        # Add an edge
        edge = EdgeData(
            source_id='sender',
            target_id='receiver',
            edge_type='message'
        )
        self.dag_model.add_edge(edge)
        
        # Define a message
        message = {
            'sender': 'sender',
            'receiver': 'receiver',
            'content': 'Test message',
            'timestamp': 123456789
        }
        mock_json.loads.return_value = message
        
        # Call the method
        await self.integration._simulate_message_passing('channel', message)
        
        # Check that a log was added to the edge
        logs = self.dag_model.get_logs_for_edge('sender', 'receiver')
        self.assertEqual(len(logs), 1)
        self.assertIn('Test message', logs[0].message)
    
    @patch('src.visualization.dag.integration.asyncio.sleep')
    async def test_monitor_redis_for_messages(self, mock_sleep):
        """Test monitoring Redis for messages."""
        # Configure the mock
        mock_sleep.side_effect = [None, Exception("Stop the loop")]  # Run once then raise to exit loop
        
        # Set up the pubsub mock
        self.mock_pubsub.listen.return_value = [
            {'type': 'message', 'channel': b'agent:messages', 'data': b'{"sender": "a", "receiver": "b", "content": "test"}'}
        ]
        
        # Create the integration with a real Redis client
        with patch.object(self.integration, '_simulate_message_passing') as mock_simulate:
            # Call the method and handle the exception to break the loop
            try:
                await self.integration._monitor_redis_for_messages('localhost', 6379, 'agent:messages')
            except Exception as e:
                self.assertEqual(str(e), "Stop the loop")
            
            # Check that Redis was connected to
            self.mock_redis.Redis.assert_called_with(host='localhost', port=6379)
            
            # Check that we subscribed to the channel
            self.mock_pubsub.subscribe.assert_called_with('agent:messages')
            
            # Check that the listener loop processed the message
            mock_simulate.assert_called()


if __name__ == '__main__':
    unittest.main() 