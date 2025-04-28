"""
Tests for the Position Closer functionality.

This module tests the position closing mechanism during graceful shutdown.
"""

import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import logging
import time

from src.core.position_closer import PositionCloser, get_position_closer
from src.core.shutdown import PositionCloseStrategy, ShutdownPhase
from src.utils.concurrency import WaitGroup


class TestPositionCloser(unittest.TestCase):
    """Test cases for the PositionCloser class."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Set up mocks
        self.mock_risk_manager = MagicMock()
        self.mock_shutdown_coordinator = MagicMock()
        
        # Configure phase timeouts
        self.mock_shutdown_coordinator._phase_timeouts = {
            ShutdownPhase.POSITIONS: 10.0
        }
        
        # Create PositionCloser with mocks
        with patch('src.core.position_closer.get_shutdown_coordinator', 
                  return_value=self.mock_shutdown_coordinator):
            self.position_closer = PositionCloser(risk_manager=self.mock_risk_manager)
        
        # Configure logging for tests
        logging.basicConfig(level=logging.DEBUG)
    
    def mock_fetch_positions(self, empty=False):
        """Set up mock positions data."""
        if empty:
            return []
        
        return [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '1.5',
                'entryPrice': '50000',
                'markPrice': '50500'
            },
            {
                'symbol': 'ETHUSDT',
                'positionAmt': '-5.0',
                'entryPrice': '3000',
                'markPrice': '3100'
            }
        ]
    
    def mock_emergency_shutdown_result(self, success=True):
        """Set up mock emergency shutdown result."""
        if not success:
            return {
                'success': False,
                'error': 'Mock error'
            }
        
        return {
            'success': True,
            'closed_positions': [
                {
                    'symbol': 'BTCUSDT',
                    'positionAmt': '1.5',
                    'success': True
                },
                {
                    'symbol': 'ETHUSDT',
                    'positionAmt': '-5.0',
                    'success': True
                }
            ]
        }
    
    async def async_test_close_positions_immediate_success(self):
        """Test immediate position closing with successful outcome."""
        # Configure mocks
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            return_value=self.mock_fetch_positions()
        )
        self.mock_risk_manager.emergency_shutdown = MagicMock(
            return_value=self.mock_emergency_shutdown_result()
        )
        
        # Set strategy
        self.mock_shutdown_coordinator.position_close_strategy = PositionCloseStrategy.IMMEDIATE
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify fetch was called
        self.mock_risk_manager.fetch_binance_position_risk.assert_called_once()
        
        # Verify emergency shutdown was called
        self.mock_risk_manager.emergency_shutdown.assert_called_once()
        
        # Verify positions were tracked
        self.assertEqual(len(self.position_closer.closed_positions), 2)
        self.assertEqual(len(self.position_closer.failed_positions), 0)
        
        # Verify results
        results = self.position_closer.get_closing_results()
        self.assertEqual(results["total_closed"], 2)
        self.assertEqual(results["total_failed"], 0)
        self.assertTrue(results["details"]["success"])
    
    async def async_test_close_positions_immediate_failure(self):
        """Test immediate position closing with a failure."""
        # Configure mocks
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            return_value=self.mock_fetch_positions()
        )
        self.mock_risk_manager.emergency_shutdown = MagicMock(
            return_value=self.mock_emergency_shutdown_result(success=False)
        )
        
        # Set strategy
        self.mock_shutdown_coordinator.position_close_strategy = PositionCloseStrategy.IMMEDIATE
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify positions were not tracked
        self.assertEqual(len(self.position_closer.closed_positions), 0)
        
        # Verify results
        results = self.position_closer.get_closing_results()
        self.assertEqual(results["total_closed"], 0)
        self.assertFalse(results["details"]["success"])
    
    async def async_test_close_positions_gradual_success(self):
        """Test gradual position closing with a successful outcome."""
        # Configure mocks
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            side_effect=[
                self.mock_fetch_positions(),  # First call returns positions
                []  # Second call (verification) returns no positions (all closed)
            ]
        )
        
        # Set up emergency shutdown to return different results for different symbols
        def mock_emergency_shutdown(reason):
            if "BTCUSDT" in reason:
                return {
                    'success': True,
                    'closed_positions': [
                        {'symbol': 'BTCUSDT', 'positionAmt': '1.5', 'success': True}
                    ]
                }
            elif "ETHUSDT" in reason:
                return {
                    'success': True,
                    'closed_positions': [
                        {'symbol': 'ETHUSDT', 'positionAmt': '-5.0', 'success': True}
                    ]
                }
            else:
                return {
                    'success': True,
                    'closed_positions': []
                }
        
        self.mock_risk_manager.emergency_shutdown = MagicMock(side_effect=mock_emergency_shutdown)
        
        # Set strategy
        self.mock_shutdown_coordinator.position_close_strategy = PositionCloseStrategy.GRADUAL
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify positions were tracked
        self.assertGreaterEqual(len(self.position_closer.closed_positions), 1)
        
        # Verify results
        results = self.position_closer.get_closing_results()
        self.assertTrue(results["details"]["success"])
    
    async def async_test_verify_positions_still_open(self):
        """Test verification when positions are still open."""
        # First call returns positions, second call still returns positions (not closed)
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            side_effect=[
                self.mock_fetch_positions(),
                self.mock_fetch_positions()
            ]
        )
        
        # Emergency shutdown returns success but only closes one position
        self.mock_risk_manager.emergency_shutdown = MagicMock(
            side_effect=[
                # Initial closing attempt
                {
                    'success': True,
                    'closed_positions': [
                        {'symbol': 'BTCUSDT', 'positionAmt': '1.5', 'success': True}
                    ]
                },
                # Fallback closing attempt
                {
                    'success': True,
                    'closed_positions': [
                        {'symbol': 'ETHUSDT', 'positionAmt': '-5.0', 'success': True}
                    ]
                }
            ]
        )
        
        # Set strategy
        self.mock_shutdown_coordinator.position_close_strategy = PositionCloseStrategy.GRADUAL
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify emergency shutdown was called at least twice
        self.assertGreaterEqual(self.mock_risk_manager.emergency_shutdown.call_count, 2)
    
    async def async_test_no_open_positions(self):
        """Test when there are no open positions."""
        # Configure mocks to return empty position list
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            return_value=[]
        )
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify emergency shutdown was not called
        self.mock_risk_manager.emergency_shutdown.assert_not_called()
        
        # Verify results
        results = self.position_closer.get_closing_results()
        self.assertEqual(results["total_closed"], 0)
        self.assertTrue(results["details"]["success"])
    
    async def async_test_api_failure_during_fetch(self):
        """Test handling of API failures during position fetching."""
        # Configure mock to raise an exception during fetch
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            side_effect=Exception("API connection error")
        )
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify emergency shutdown was not called (since fetch failed)
        self.mock_risk_manager.emergency_shutdown.assert_not_called()
        
        # Verify results indicate failure
        results = self.position_closer.get_closing_results()
        self.assertFalse(results["details"]["success"])
        self.assertTrue("error" in results["details"])
    
    async def async_test_partial_position_closing(self):
        """Test handling of partial position closing."""
        # Configure mocks
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            side_effect=[
                self.mock_fetch_positions(),  # First call returns positions
                [  # Second call returns one position still open
                    {
                        'symbol': 'ETHUSDT',
                        'positionAmt': '-5.0',
                        'entryPrice': '3000',
                        'markPrice': '3100'
                    }
                ]
            ]
        )
        
        # Mock emergency shutdown to close only BTC position
        self.mock_risk_manager.emergency_shutdown = MagicMock(
            return_value={
                'success': True,
                'closed_positions': [
                    {'symbol': 'BTCUSDT', 'positionAmt': '1.5', 'success': True}
                ]
            }
        )
        
        # Set strategy
        self.mock_shutdown_coordinator.position_close_strategy = PositionCloseStrategy.IMMEDIATE
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify positions tracking reflects partial success
        self.assertEqual(len(self.position_closer.closed_positions), 1)
        
        # Verify results
        results = self.position_closer.get_closing_results()
        self.assertEqual(results["total_closed"], 1)
        self.assertEqual(results["total_failed"], 1)
    
    async def async_test_timeout_handling(self):
        """Test position closing with timeout."""
        # Configure mocks
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            return_value=self.mock_fetch_positions()
        )
        
        # Make emergency shutdown take a long time
        async def slow_emergency_shutdown(reason):
            await asyncio.sleep(2.0)  # Simulate slow operation
            return self.mock_emergency_shutdown_result()
        
        self.mock_risk_manager.emergency_shutdown = AsyncMock(
            side_effect=slow_emergency_shutdown
        )
        
        # Set a very short timeout for the positions phase
        self.mock_shutdown_coordinator._phase_timeouts[ShutdownPhase.POSITIONS] = 0.1
        
        # Set strategy
        self.mock_shutdown_coordinator.position_close_strategy = PositionCloseStrategy.IMMEDIATE
        
        # Execute position closing
        start_time = time.time()
        await self.position_closer.close_positions()
        end_time = time.time()
        
        # Verify the operation didn't take longer than the timeout
        self.assertLess(end_time - start_time, 0.5)  # Allow some overhead
        
        # Results should indicate timeout
        results = self.position_closer.get_closing_results()
        self.assertFalse(results["details"]["success"])
        self.assertTrue("timeout" in str(results["details"]).lower())
    
    async def async_test_concurrent_position_closing(self):
        """Test concurrent closing of multiple positions."""
        # Configure many positions
        many_positions = []
        for i in range(10):
            many_positions.append({
                'symbol': f'BTCUSDT_{i}',
                'positionAmt': '1.5',
                'entryPrice': '50000',
                'markPrice': '50500'
            })
        
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            side_effect=[
                many_positions,  # First call returns many positions
                []  # Second call returns no positions (all closed)
            ]
        )
        
        # Mock successful emergency shutdown for any position
        self.mock_risk_manager.emergency_shutdown = MagicMock(
            return_value={
                'success': True,
                'closed_positions': [{'success': True}]
            }
        )
        
        # Set strategy to gradual which processes each position separately
        self.mock_shutdown_coordinator.position_close_strategy = PositionCloseStrategy.GRADUAL
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify emergency shutdown was called for each position
        self.assertEqual(self.mock_risk_manager.emergency_shutdown.call_count, 10)
    
    async def async_test_close_with_retry(self):
        """Test position closing with retries after failure."""
        # Configure mocks
        self.mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            side_effect=[
                self.mock_fetch_positions(),  # First call
                self.mock_fetch_positions(),  # Second call (still open)
                []  # Third call (finally closed)
            ]
        )
        
        # First attempt fails, second succeeds
        self.mock_risk_manager.emergency_shutdown = MagicMock(
            side_effect=[
                {'success': False, 'error': 'Temporary error'},
                self.mock_emergency_shutdown_result()
            ]
        )
        
        # Set strategy
        self.mock_shutdown_coordinator.position_close_strategy = PositionCloseStrategy.IMMEDIATE
        
        # Enable retries in position closer (patch the retry settings)
        self.position_closer.max_retries = 3
        self.position_closer.retry_delay = 0.1
        
        # Execute position closing
        await self.position_closer.close_positions()
        
        # Verify emergency shutdown was called at least twice
        self.assertGreaterEqual(self.mock_risk_manager.emergency_shutdown.call_count, 2)
        
        # Verify results
        results = self.position_closer.get_closing_results()
        self.assertTrue(results["details"]["success"])
    
    async def async_test_factory_function(self):
        """Test the factory function for creating PositionCloser instances."""
        # Patch the shutdown coordinator getter
        with patch('src.core.position_closer.get_shutdown_coordinator', 
                  return_value=self.mock_shutdown_coordinator):
            # Call factory function
            closer = get_position_closer(self.mock_risk_manager)
            
            # Verify it returns a PositionCloser instance
            self.assertIsInstance(closer, PositionCloser)
            
            # Verify it was initialized with the correct risk manager
            self.assertEqual(closer.risk_manager, self.mock_risk_manager)
    
    def test_close_positions_immediate_success(self):
        """Run the async test for immediate closing."""
        asyncio.run(self.async_test_close_positions_immediate_success())
    
    def test_close_positions_immediate_failure(self):
        """Run the async test for immediate closing with failure."""
        asyncio.run(self.async_test_close_positions_immediate_failure())
    
    def test_close_positions_gradual_success(self):
        """Run the async test for gradual closing."""
        asyncio.run(self.async_test_close_positions_gradual_success())
    
    def test_verify_positions_still_open(self):
        """Run the async test for verification with open positions."""
        asyncio.run(self.async_test_verify_positions_still_open())
    
    def test_no_open_positions(self):
        """Run the async test for no open positions."""
        asyncio.run(self.async_test_no_open_positions())
    
    def test_api_failure_during_fetch(self):
        """Run the async test for API failures during fetch."""
        asyncio.run(self.async_test_api_failure_during_fetch())
    
    def test_partial_position_closing(self):
        """Run the async test for partial position closing."""
        asyncio.run(self.async_test_partial_position_closing())
    
    def test_timeout_handling(self):
        """Run the async test for timeout handling."""
        asyncio.run(self.async_test_timeout_handling())
    
    def test_concurrent_position_closing(self):
        """Run the async test for concurrent position closing."""
        asyncio.run(self.async_test_concurrent_position_closing())
    
    def test_close_with_retry(self):
        """Run the async test for position closing with retries."""
        asyncio.run(self.async_test_close_with_retry())
    
    def test_factory_function(self):
        """Run the async test for the factory function."""
        asyncio.run(self.async_test_factory_function())


if __name__ == "__main__":
    unittest.main() 