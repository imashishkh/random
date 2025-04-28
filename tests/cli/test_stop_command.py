"""
Test module for the `stop` command in the Forex Trading Bot CLI.

This module contains unit tests for the StopCommand class and integration tests
for the `stop` command and its aliases.
"""

import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import click
from click.testing import CliRunner
import time
import pytest

from src.cli.stop_command import StopCommand, register_commands
from src.core.shutdown import ShutdownPhase

# Skip real asyncio functions in tests
pytestmark = pytest.mark.asyncio


class TestStopCommandUnit(unittest.TestCase):
    """Unit tests for the StopCommand class."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock dependencies
        self.shutdown_coordinator_mock = MagicMock()
        self.position_closer_mock = MagicMock()
        self.agent_terminator_mock = MagicMock()
        self.resource_cleaner_mock = MagicMock()
        
        # Create stop command instance
        self.cmd = StopCommand()
        self.cmd.shutdown_coordinator = self.shutdown_coordinator_mock
        self.cmd.position_closer = self.position_closer_mock
        self.cmd.agent_terminator = self.agent_terminator_mock
        self.cmd.resource_cleaner = self.resource_cleaner_mock
        self.cmd.start_time = time.time()
    
    @patch('asyncio.run')
    def test_initialize_components(self, asyncio_run_mock):
        """Test the component initialization."""
        # Configure mocks
        get_position_closer_mock = MagicMock(return_value=self.position_closer_mock)
        get_orchestrator_mock = MagicMock()
        get_agent_terminator_mock = MagicMock(return_value=self.agent_terminator_mock)
        get_resource_cleaner_mock = MagicMock(return_value=self.resource_cleaner_mock)
        
        # Create a new command instance for this test
        cmd = StopCommand()
        
        # Run initialization with patched dependencies
        with patch('src.cli.stop_command.get_position_closer', get_position_closer_mock), \
             patch('src.cli.stop_command.get_orchestrator', get_orchestrator_mock), \
             patch('src.cli.stop_command.get_agent_terminator', get_agent_terminator_mock), \
             patch('src.cli.stop_command.get_resource_cleaner', get_resource_cleaner_mock):
            # Execute the async function
            asyncio_run_mock.side_effect = lambda coroutine: asyncio.get_event_loop().run_until_complete(coroutine)
            asyncio.run(cmd.initialize_components())
            
            # Assert dependencies were retrieved
            self.assertEqual(cmd.position_closer, self.position_closer_mock)
            self.assertEqual(cmd.agent_terminator, self.agent_terminator_mock)
            self.assertEqual(cmd.resource_cleaner, self.resource_cleaner_mock)
    
    async def test_execute_shutdown_default(self):
        """Test execute_shutdown with default parameters."""
        # Mock methods
        self.cmd.initialize_components = AsyncMock()
        self.cmd.monitor_shutdown_progress = AsyncMock(return_value=0)
        
        # Configure mocks
        self.shutdown_coordinator_mock.initiate_shutdown = AsyncMock()
        
        # Execute with default parameters
        result = await self.cmd.execute_shutdown()
        
        # Verify
        self.cmd.initialize_components.assert_called_once()
        self.shutdown_coordinator_mock.initiate_shutdown.assert_called_once_with(
            reason="cli_command",
            force=False,
            position_strategy='gradual'
        )
        self.cmd.monitor_shutdown_progress.assert_called_once_with(
            timeout=60.0,
            verbose=False
        )
        self.assertEqual(result, 0)
    
    async def test_execute_shutdown_with_options(self):
        """Test execute_shutdown with custom parameters."""
        # Mock methods
        self.cmd.initialize_components = AsyncMock()
        self.cmd.monitor_shutdown_progress = AsyncMock(return_value=0)
        
        # Configure mocks
        self.shutdown_coordinator_mock.initiate_shutdown = AsyncMock()
        
        # Execute with custom parameters
        result = await self.cmd.execute_shutdown(
            force=True,
            immediate=True,
            timeout=30.0,
            verbose=True
        )
        
        # Verify
        self.cmd.initialize_components.assert_called_once()
        self.shutdown_coordinator_mock.initiate_shutdown.assert_called_once_with(
            reason="cli_command",
            force=True,
            position_strategy='immediate'
        )
        self.cmd.monitor_shutdown_progress.assert_called_once_with(
            timeout=30.0,
            verbose=True
        )
        self.assertEqual(result, 0)
    
    async def test_monitor_shutdown_progress_success(self):
        """Test monitor_shutdown_progress with successful shutdown."""
        # Configure mocks
        wait_calls = [False, False, True]  # First two calls return False, third returns True
        self.shutdown_coordinator_mock.wait_for_shutdown = AsyncMock(side_effect=wait_calls)
        self.shutdown_coordinator_mock.get_status = MagicMock(return_value={
            'phase': ShutdownPhase.COMPLETE.value,
            'elapsed_time': 5.0
        })
        
        # Execute
        with patch('src.cli.stop_command.Progress') as progress_mock:
            result = await self.cmd.monitor_shutdown_progress()
        
        # Verify
        self.assertEqual(result, 0)
        self.shutdown_coordinator_mock.wait_for_shutdown.assert_called()
        self.shutdown_coordinator_mock.get_status.assert_called()
    
    async def test_monitor_shutdown_progress_failure(self):
        """Test monitor_shutdown_progress with failed shutdown."""
        # Configure mocks
        wait_calls = [False, False, True]  # First two calls return False, third returns True
        self.shutdown_coordinator_mock.wait_for_shutdown = AsyncMock(side_effect=wait_calls)
        self.shutdown_coordinator_mock.get_status = MagicMock(return_value={
            'phase': ShutdownPhase.FAILED.value,
            'elapsed_time': 5.0
        })
        
        # Execute
        with patch('src.cli.stop_command.Progress') as progress_mock:
            result = await self.cmd.monitor_shutdown_progress()
        
        # Verify
        self.assertEqual(result, 1)
        self.shutdown_coordinator_mock.wait_for_shutdown.assert_called()
        self.shutdown_coordinator_mock.get_status.assert_called()
    
    async def test_monitor_shutdown_progress_timeout(self):
        """Test monitor_shutdown_progress with timeout."""
        # Configure mocks
        self.shutdown_coordinator_mock.wait_for_shutdown = AsyncMock(return_value=False)
        self.shutdown_coordinator_mock.get_status = MagicMock(return_value={
            'phase': ShutdownPhase.POSITIONS.value,
        })
        
        # Set start_time to be longer ago than timeout
        self.cmd.start_time = time.time() - 70  # 70 seconds ago
        
        # Execute with a timeout of 60 seconds
        with patch('src.cli.stop_command.Progress') as progress_mock:
            result = await self.cmd.monitor_shutdown_progress(timeout=60.0)
        
        # Verify
        self.assertEqual(result, 1)
        self.shutdown_coordinator_mock.wait_for_shutdown.assert_called()
    
    async def test_monitor_shutdown_progress_exception(self):
        """Test monitor_shutdown_progress with an exception."""
        # Configure mocks
        self.shutdown_coordinator_mock.wait_for_shutdown = AsyncMock(side_effect=Exception("Test error"))
        
        # Execute
        with patch('src.cli.stop_command.Progress') as progress_mock:
            result = await self.cmd.monitor_shutdown_progress()
        
        # Verify
        self.assertEqual(result, 1)
        self.shutdown_coordinator_mock.wait_for_shutdown.assert_called_once()


class TestStopCommandIntegration:
    """Integration tests for the stop command and its aliases."""
    
    @pytest.fixture
    def cli(self):
        """Create a test CLI with stop commands registered."""
        @click.group()
        def cli_group():
            pass
        
        register_commands(cli_group)
        return cli_group
    
    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()
    
    @patch('src.cli.stop_command.StopCommand')
    @patch('src.cli.stop_command.Confirm.ask')
    def test_stop_basic(self, confirm_ask_mock, stop_command_mock, cli, runner):
        """Test the basic stop command."""
        # Configure mocks
        confirm_ask_mock.return_value = True
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(return_value=0)
        
        # Run command
        result = runner.invoke(cli, ['stop'])
        
        # Verify
        assert result.exit_code == 0
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once_with(
            force=False,
            immediate=False,
            timeout=60.0,
            verbose=False
        )
    
    @patch('src.cli.stop_command.StopCommand')
    @patch('src.cli.stop_command.Confirm.ask')
    def test_stop_with_options(self, confirm_ask_mock, stop_command_mock, cli, runner):
        """Test the stop command with options."""
        # Configure mocks
        confirm_ask_mock.return_value = True
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(return_value=0)
        
        # Run command with options
        result = runner.invoke(cli, [
            'stop',
            '--force',
            '--immediate',
            '--timeout', '30.0',
            '--verbose'
        ])
        
        # Verify
        assert result.exit_code == 0
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once_with(
            force=True,
            immediate=True,
            timeout=30.0,
            verbose=True
        )
    
    @patch('src.cli.stop_command.StopCommand')
    @patch('src.cli.stop_command.Confirm.ask')
    def test_stop_confirmation_cancel(self, confirm_ask_mock, stop_command_mock, cli, runner):
        """Test cancellation in confirmation prompt."""
        # Configure mocks
        confirm_ask_mock.return_value = False
        
        # Run command
        result = runner.invoke(cli, ['stop'])
        
        # Verify
        assert result.exit_code == 0
        stop_command_mock.assert_not_called()
    
    @patch('src.cli.stop_command.StopCommand')
    def test_stop_no_confirm(self, stop_command_mock, cli, runner):
        """Test the stop command with no-confirm option."""
        # Configure mocks
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(return_value=0)
        
        # Run command with no-confirm
        result = runner.invoke(cli, ['stop', '--no-confirm'])
        
        # Verify
        assert result.exit_code == 0
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once()
    
    @patch('src.cli.stop_command.StopCommand')
    def test_stop_immediate_alias(self, stop_command_mock, cli, runner):
        """Test the stop-immediate alias."""
        # Configure mocks
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(return_value=0)
        
        # Run command with no-confirm to skip confirmation
        result = runner.invoke(cli, ['stop-immediate', '--no-confirm'])
        
        # Verify
        assert result.exit_code == 0
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once_with(
            force=False,
            immediate=True,
            timeout=60.0,
            verbose=False
        )
    
    @patch('src.cli.stop_command.StopCommand')
    def test_stop_force_alias(self, stop_command_mock, cli, runner):
        """Test the stop-force alias."""
        # Configure mocks
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(return_value=0)
        
        # Run command with no-confirm to skip confirmation
        result = runner.invoke(cli, ['stop-force', '--no-confirm'])
        
        # Verify
        assert result.exit_code == 0
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once_with(
            force=True,
            immediate=False,
            timeout=60.0,
            verbose=False
        )
    
    @patch('src.cli.stop_command.StopCommand')
    def test_stop_emergency_alias(self, stop_command_mock, cli, runner):
        """Test the stop-emergency alias."""
        # Configure mocks
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(return_value=0)
        
        # Run command (no need for --no-confirm as it's built into the alias)
        result = runner.invoke(cli, ['stop-emergency'])
        
        # Verify
        assert result.exit_code == 0
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once_with(
            force=True,
            immediate=True,
            timeout=30.0,  # Default for emergency is 30s
            verbose=False,
            no_confirm=True
        )
    
    @patch('src.cli.stop_command.StopCommand')
    def test_shutdown_alias(self, stop_command_mock, cli, runner):
        """Test the shutdown alias."""
        # Configure mocks
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(return_value=0)
        
        # Run command with no-confirm to skip confirmation
        result = runner.invoke(cli, ['shutdown', '--no-confirm'])
        
        # Verify
        assert result.exit_code == 0
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once_with(
            force=False,
            immediate=False,
            timeout=60.0,
            verbose=False
        )
    
    @patch('src.cli.stop_command.StopCommand')
    def test_stop_failure(self, stop_command_mock, cli, runner):
        """Test handling of command execution failure."""
        # Configure mocks
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(return_value=1)  # Return failure
        
        # Run command with no-confirm to skip confirmation
        result = runner.invoke(cli, ['stop', '--no-confirm'])
        
        # Verify
        assert result.exit_code == 1
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once()
    
    @patch('src.cli.stop_command.StopCommand')
    def test_stop_exception(self, stop_command_mock, cli, runner):
        """Test handling of exceptions during command execution."""
        # Configure mocks
        cmd_instance = MagicMock()
        stop_command_mock.return_value = cmd_instance
        cmd_instance.execute_shutdown = AsyncMock(side_effect=Exception("Test error"))
        
        # Run command with no-confirm to skip confirmation
        result = runner.invoke(cli, ['stop', '--no-confirm'])
        
        # Verify
        assert result.exit_code == 1
        stop_command_mock.assert_called_once()
        cmd_instance.execute_shutdown.assert_called_once()


if __name__ == '__main__':
    unittest.main() 