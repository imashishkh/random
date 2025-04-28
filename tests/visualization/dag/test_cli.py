"""
Tests for the DAG visualization command-line interface.

This module contains tests for the CLI entry points, argument parsing, and setup
of the DAG visualization from the command line.
"""

import unittest
import argparse
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

from src.visualization.dag.model import DAGModel, NodeData, EdgeData, AgentStatus
from src.visualization.dag.cli import async_main, run_visualization_with_demo_data, main


class TestDAGCLI(unittest.TestCase):
    """Tests for the DAG visualization CLI."""
    
    def setUp(self):
        """Set up test environment."""
        # Patch external modules and functions
        self.run_vis_patcher = patch('src.visualization.dag.cli.run_dag_visualization')
        self.mock_run_vis = self.run_vis_patcher.start()
        
        self.integration_patcher = patch('src.visualization.dag.cli.AgentDAGIntegration')
        self.mock_integration_cls = self.integration_patcher.start()
        self.mock_integration = self.mock_integration_cls.return_value
        self.mock_integration.connect_to_orchestrator = AsyncMock()
        self.mock_integration.monitor_redis_for_messages = AsyncMock()
        
        self.orchestrator_patcher = patch('src.visualization.dag.cli.get_orchestrator', new=MagicMock())
        self.mock_get_orchestrator = self.orchestrator_patcher.start()
        
        self.redis_patcher = patch('src.visualization.dag.cli.aioredis')
        self.mock_redis = self.redis_patcher.start()
        self.mock_redis_pool = MagicMock()
        self.mock_redis.create_redis_pool = AsyncMock(return_value=self.mock_redis_pool)
        
        self.threading_patcher = patch('src.visualization.dag.cli.threading')
        self.mock_threading = self.threading_patcher.start()
        
        self.asyncio_patcher = patch('src.visualization.dag.cli.asyncio')
        self.mock_asyncio = self.asyncio_patcher.start()
        
        # Mock thread for app
        self.mock_thread = MagicMock()
        self.mock_thread.is_alive.side_effect = [True, False]  # Return True once, then False to end loop
        self.mock_threading.Thread.return_value = self.mock_thread
    
    def tearDown(self):
        """Clean up after tests."""
        self.run_vis_patcher.stop()
        self.integration_patcher.stop()
        self.orchestrator_patcher.stop()
        self.redis_patcher.stop()
        self.threading_patcher.stop()
        self.asyncio_patcher.stop()
    
    async def test_async_main_with_orchestrator(self):
        """Test async_main function with orchestrator connection."""
        # Create mock args
        args = argparse.Namespace(
            config='test_config.yaml',
            redis=None,
            redis_pattern=None,
            demo=False,
            debug=False
        )
        
        # Call the function
        await async_main(args)
        
        # Check that the orchestrator was retrieved
        self.mock_get_orchestrator.assert_called_once_with('test_config.yaml')
        
        # Check that the integration connected to the orchestrator
        orchestrator = self.mock_get_orchestrator.return_value
        self.mock_integration.connect_to_orchestrator.assert_called_once_with(orchestrator)
        
        # Verify that the visualization was started
        self.mock_threading.Thread.assert_called_once()
        self.mock_thread.start.assert_called_once()
        
        # No Redis monitoring should have been started
        self.mock_integration.monitor_redis_for_messages.assert_not_called()
    
    async def test_async_main_with_redis(self):
        """Test async_main function with Redis monitoring."""
        # Create mock args with Redis
        args = argparse.Namespace(
            config='test_config.yaml',
            redis='redis://localhost:6379',
            redis_pattern='agent:*:message',
            demo=False,
            debug=False
        )
        
        # Call the function
        await async_main(args)
        
        # Check that Redis was connected to
        self.mock_redis.create_redis_pool.assert_called_once_with('redis://localhost:6379')
        
        # Check that Redis monitoring was started
        self.mock_asyncio.create_task.assert_called_once()
        self.mock_integration.monitor_redis_for_messages.assert_called_once_with(
            self.mock_redis_pool,
            'agent:*:message'
        )
    
    async def test_async_main_import_error(self):
        """Test async_main function when orchestrator import fails."""
        # Make get_orchestrator raise ImportError
        self.mock_get_orchestrator.side_effect = ImportError("Orchestrator not found")
        
        # Create mock args
        args = argparse.Namespace(
            config='test_config.yaml',
            redis=None,
            redis_pattern=None,
            demo=False,
            debug=False
        )
        
        # Create a mock for run_visualization_with_demo_data
        with patch('src.visualization.dag.cli.run_visualization_with_demo_data') as mock_run_demo:
            # Call the function
            await async_main(args)
            
            # Check that demo data was used instead
            mock_run_demo.assert_called_once()
    
    async def test_async_main_orchestrator_error(self):
        """Test async_main function when orchestrator connection fails."""
        # Make the connection raise an exception
        self.mock_integration.connect_to_orchestrator.side_effect = Exception("Connection failed")
        
        # Create mock args
        args = argparse.Namespace(
            config='test_config.yaml',
            redis=None,
            redis_pattern=None,
            demo=False,
            debug=False
        )
        
        # Create a mock for run_visualization_with_demo_data
        with patch('src.visualization.dag.cli.run_visualization_with_demo_data') as mock_run_demo:
            # Call the function
            await async_main(args)
            
            # Check that demo data was used instead
            mock_run_demo.assert_called_once()
    
    def test_run_visualization_with_demo_data(self):
        """Test run_visualization_with_demo_data function."""
        # Create a mock model
        model = MagicMock(spec=DAGModel)
        
        # Call the function
        run_visualization_with_demo_data(model)
        
        # Check that the model was populated with demo data
        self.assertEqual(model.add_node.call_count, 8)  # 8 nodes should be added
        self.assertEqual(model.add_edge.call_count, 9)  # 9 edges should be added
        self.assertGreaterEqual(model.add_log_to_edge.call_count, 9)  # At least 9 logs (one per edge)
        
        # Check that the visualization was run
        self.mock_run_vis.assert_called_once_with(model)
    
    @patch('src.visualization.dag.cli.argparse.ArgumentParser')
    @patch('src.visualization.dag.cli.asyncio.run')
    def test_main_with_demo(self, mock_asyncio_run, mock_argparse):
        """Test main function with demo flag."""
        # Set up mock args
        mock_args = MagicMock()
        mock_args.demo = True
        mock_args.debug = False
        
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = mock_args
        mock_argparse.return_value = mock_parser
        
        # Create a mock for run_visualization_with_demo_data
        with patch('src.visualization.dag.cli.run_visualization_with_demo_data') as mock_run_demo:
            # Call the function
            main()
            
            # Check that demo data was used
            mock_run_demo.assert_called_once()
            
            # Check that asyncio.run was not called
            mock_asyncio_run.assert_not_called()
    
    @patch('src.visualization.dag.cli.argparse.ArgumentParser')
    @patch('src.visualization.dag.cli.asyncio.run')
    def test_main_without_demo(self, mock_asyncio_run, mock_argparse):
        """Test main function without demo flag."""
        # Set up mock args
        mock_args = MagicMock()
        mock_args.demo = False
        mock_args.debug = False
        
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = mock_args
        mock_argparse.return_value = mock_parser
        
        # Call the function
        main()
        
        # Check that asyncio.run was called with the async_main function
        mock_asyncio_run.assert_called_once()
        # The first argument should be a coroutine from async_main
        call_args = mock_asyncio_run.call_args[0][0]
        self.assertTrue(asyncio.iscoroutine(call_args) or 
                      isinstance(call_args, asyncio.Future))
    
    @patch('src.visualization.dag.cli.argparse.ArgumentParser')
    @patch('src.visualization.dag.cli.logging')
    def test_main_with_debug(self, mock_logging, mock_argparse):
        """Test main function with debug flag."""
        # Set up mock args
        mock_args = MagicMock()
        mock_args.demo = True  # Use demo to simplify testing
        mock_args.debug = True
        
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = mock_args
        mock_argparse.return_value = mock_parser
        
        mock_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_logger
        
        # Create a mock for run_visualization_with_demo_data
        with patch('src.visualization.dag.cli.run_visualization_with_demo_data'):
            # Call the function
            main()
            
            # Check that logging level was set to DEBUG
            mock_logging.getLogger.assert_called()
            mock_logger.setLevel.assert_called_with(mock_logging.DEBUG)


if __name__ == "__main__":
    unittest.main() 