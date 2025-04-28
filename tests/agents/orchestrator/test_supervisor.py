"""
Unit tests for the Supervisor pattern implementation.
"""

import unittest
import asyncio
import os
import tempfile
import json
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Mock required imports
sys.modules['langchain'] = MagicMock()
sys.modules['langchain.schema'] = MagicMock()
sys.modules['src'] = MagicMock()
sys.modules['src.agents'] = MagicMock()
sys.modules['src.agents.health'] = MagicMock()
sys.modules['src.agents.health'].get_health_monitor = MagicMock(return_value=MagicMock())
sys.modules['networkx'] = MagicMock()
sys.modules['networkx'].DiGraph = MagicMock(return_value=MagicMock())
sys.modules['networkx'].topological_sort = MagicMock(return_value=['agent3', 'agent2', 'agent1'])
sys.modules['networkx'].NetworkXUnfeasible = Exception

# Path the module to force these imports to work
with patch.dict('sys.modules'):
    from src.agents.orchestrator.engine import (
        AgentSwarmOrchestrator, 
        AgentMetadata, 
        AgentStatus
    )
    from src.agents.orchestrator.supervisor import (
        SupervisorManager,
        SupervisionPolicy,
        RestartPolicy,
        ShutdownPhase,
        get_supervisor
    )


class TestSupervisorManager(unittest.IsolatedAsyncioTestCase):
    """Test cases for the SupervisorManager class."""
    
    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Create mock orchestrator
        self.mock_orchestrator = AsyncMock(spec=AgentSwarmOrchestrator)
        
        # Setup mock agent metadata
        agent1 = MagicMock(spec=AgentMetadata)
        agent1.id = "agent1"
        agent1.name = "Test Agent 1"
        agent1.agent_type = "test_agent"
        agent1.status = AgentStatus.RUNNING
        agent1.config = {"param1": "value1"}
        
        agent2 = MagicMock(spec=AgentMetadata)
        agent2.id = "agent2"
        agent2.name = "Test Agent 2"
        agent2.agent_type = "test_agent"
        agent2.status = AgentStatus.RUNNING
        agent2.config = {"param1": "value2"}
        
        # Configure mock orchestrator
        self.mock_orchestrator.get_all_agents.return_value = [agent1, agent2]
        self.mock_orchestrator.get_agent_metadata.side_effect = lambda agent_id: {
            "agent1": agent1,
            "agent2": agent2
        }.get(agent_id)
        
        # Configure dependency graph methods
        sys.modules['networkx'].DiGraph().has_node.return_value = True
        sys.modules['networkx'].DiGraph().successors.return_value = []
        
        # Create supervisor
        self.supervisor = SupervisorManager(orchestrator=self.mock_orchestrator)
        
        # Register test agents
        await self.supervisor.register_agent("agent1")
        await self.supervisor.register_agent("agent2", dependencies=["agent1"])
    
    async def test_register_agent(self):
        """Test agent registration with supervision policy."""
        policy = SupervisionPolicy(
            restart_policy=RestartPolicy.ALWAYS,
            max_restarts=5,
            shutdown_priority=2
        )
        
        await self.supervisor.register_agent("agent3", dependencies=["agent2"], policy=policy)
        
        # Check policy was stored
        self.assertIn("agent3", self.supervisor.policies)
        self.assertEqual(self.supervisor.policies["agent3"].restart_policy, RestartPolicy.ALWAYS)
        self.assertEqual(self.supervisor.policies["agent3"].max_restarts, 5)
    
    async def test_agent_failure_with_restart(self):
        """Test handling of agent failure with restart policy."""
        # Set up restart policy
        self.supervisor.policies["agent1"] = SupervisionPolicy(
            restart_policy=RestartPolicy.ON_FAILURE,
            max_restarts=3,
            backoff_factor=1.0,  # No backoff for testing
        )
        
        # Configure successful restart
        self.mock_orchestrator.spawn_agent.return_value = asyncio.Future()
        self.mock_orchestrator.spawn_agent.return_value.set_result(asyncio.Task(asyncio.sleep(0)))
        
        # Handle failure
        await self.supervisor.handle_agent_failure("agent1", Exception("Test failure"))
        
        # Verify restart behavior
        self.assertEqual(self.supervisor.restart_counts["agent1"], 1)
        self.assertIn("agent1", self.supervisor.recovery_tasks)
        
        # Fast-forward through the restart
        await asyncio.sleep(0.1)
        
        # Verify agent was restarted
        self.mock_orchestrator.update_agent_status.assert_any_call("agent1", AgentStatus.RESTARTING)
        self.mock_orchestrator.spawn_agent.assert_called_once_with(
            "agent1", "test_agent", "Test Agent 1", {"param1": "value1"}
        )
    
    async def test_agent_failure_with_never_restart(self):
        """Test handling of agent failure with NEVER restart policy."""
        # Set up restart policy
        self.supervisor.policies["agent1"] = SupervisionPolicy(
            restart_policy=RestartPolicy.NEVER,
            escalate_on_failure=True
        )
        
        # Handle failure
        await self.supervisor.handle_agent_failure("agent1", Exception("Test failure"))
        
        # Verify no restart occurred
        self.assertEqual(self.supervisor.restart_counts.get("agent1", 0), 0)
        self.assertNotIn("agent1", self.supervisor.recovery_tasks)
        
        # Verify no spawn call
        self.mock_orchestrator.spawn_agent.assert_not_called()
    
    async def test_shutdown_sequence(self):
        """Test the two-phase shutdown sequence."""
        # Configure position check
        self.supervisor.policies["agent1"] = SupervisionPolicy(position_check_required=True)
        
        # Configure termination response
        self.mock_orchestrator.terminate_agent.return_value = True
        
        # Start shutdown
        shutdown_task = asyncio.create_task(
            self.supervisor.initiate_shutdown(timeout=1.0)
        )
        
        # Allow shutdown to begin
        await asyncio.sleep(0.1)
        
        # Check initial shutdown state
        self.assertEqual(self.supervisor.shutdown_phase, ShutdownPhase.PREPARE)
        self.assertTrue(self.supervisor.shutdown_event.is_set())
        
        # Wait for shutdown to complete
        await self.supervisor.wait_for_shutdown(timeout=1.0)
        
        # Verify final state
        self.assertEqual(self.supervisor.shutdown_phase, ShutdownPhase.COMPLETE)
        self.assertTrue(self.supervisor.shutdown_complete.is_set())
        
        # Verify agent termination sequence
        # In reversed topological order of dependencies
        expected_termination_calls = [
            unittest.mock.call("agent1", timeout=10.0, force=True),
            unittest.mock.call("agent2", timeout=10.0, force=True)
        ]
        
        self.assertEqual(
            self.mock_orchestrator.terminate_agent.call_count, 
            len(expected_termination_calls)
        )
    
    async def test_agent_failure_during_shutdown(self):
        """Test agent failure handling during shutdown."""
        # Start shutdown
        shutdown_task = asyncio.create_task(
            self.supervisor.initiate_shutdown(timeout=1.0)
        )
        
        # Allow shutdown to begin
        await asyncio.sleep(0.1)
        
        # Try to handle failure during shutdown
        await self.supervisor.handle_agent_failure("agent1", Exception("Failure during shutdown"))
        
        # Verify no restart attempted during shutdown
        self.mock_orchestrator.spawn_agent.assert_not_called()
    
    @patch('src.agents.orchestrator.supervisor.signal')
    def test_signal_handler(self, mock_signal):
        """Test signal handler registration."""
        # Create new supervisor to test signal handling
        supervisor = SupervisorManager(orchestrator=self.mock_orchestrator)
        
        # Verify signal handlers were set up
        mock_signal.signal.assert_any_call(mock_signal.SIGINT, supervisor._signal_handler)
        mock_signal.signal.assert_any_call(mock_signal.SIGTERM, supervisor._signal_handler)
    
    @patch('src.agents.orchestrator.supervisor.get_orchestrator')
    def test_singleton_get_supervisor(self, mock_get_orchestrator):
        """Test the singleton get_supervisor function."""
        # Reset singleton for testing
        import src.agents.orchestrator.supervisor
        src.agents.orchestrator.supervisor._supervisor_instance = None
        
        # Get supervisor instances
        instance1 = get_supervisor()
        instance2 = get_supervisor()
        
        # Verify same instance was returned
        self.assertIs(instance1, instance2)
        
        # Verify orchestrator was obtained once
        mock_get_orchestrator.assert_called_once()


if __name__ == '__main__':
    unittest.main() 