"""
Unit Tests for Burst Order Scenario Generators

This module contains tests to validate the functionality of burst order scenario generators.
"""

import asyncio
import unittest
import logging
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any
import random
import time

from harness.generators.burst_scenarios import (
    BurstOrderScenarioGenerator,
    SuddenBurstScenario,
    RampBurstScenario,
    OscillatingBurstScenario,
    create_burst_scenario
)
from harness.generators.order_events import OrderCancellation, OrderModification
from harness.generators.base import OrderData


class TestBurstScenarioGenerators(unittest.TestCase):
    """Test case for burst order scenario generators."""
    
    def setUp(self):
        """Set up test environment."""
        # Silence logger
        logging.basicConfig(level=logging.CRITICAL)
        
        # Base configuration for all scenarios
        self.config = {
            'symbols': ['EURUSD', 'GBPUSD', 'USDJPY'],
            'burst_size_min': 5,
            'burst_size_max': 10,
            'burst_interval_min': 0.1,
            'burst_interval_max': 0.2,
            'burst_duration_min': 0.1,
            'burst_duration_max': 0.2,
            'order_type_distribution': {'market': 0.6, 'limit': 0.3, 'stop': 0.1},
            'cancellation_rate': 0.2,
            'modification_rate': 0.1,
            'size_min': 0.1,
            'size_max': 5.0,
        }
        
        # List to store received orders
        self.received_orders = []
        
    def order_listener(self, order):
        """Listener function to capture generated orders."""
        self.received_orders.append(order)
    
    @patch('asyncio.sleep', return_value=None)  # Mock sleep to speed up tests
    async def test_sudden_burst_scenario(self, mock_sleep):
        """Test the SuddenBurstScenario generates orders correctly."""
        # Create scenario generator
        generator = SuddenBurstScenario(self.config)
        
        # Add listener
        generator.add_listener(self.order_listener)
        
        # Start generator
        await generator.start()
        
        # Run a single burst
        await generator._generate_burst()
        
        # Stop generator
        await generator.stop()
        
        # Verify orders were generated
        self.assertTrue(len(self.received_orders) > 0, "No orders were generated")
        
        # Verify all orders are OrderData objects
        for order in self.received_orders:
            self.assertIsInstance(order, OrderData, f"Expected OrderData, got {type(order)}")
        
        # Verify burst size is within configured limits
        self.assertGreaterEqual(len(self.received_orders), self.config['burst_size_min'])
        self.assertLessEqual(len(self.received_orders), self.config['burst_size_max'])
        
        # Verify order symbols are from the configured list
        for order in self.received_orders:
            self.assertIn(order.symbol, self.config['symbols'])
        
        # Verify order types follow distribution (with some tolerance)
        market_orders = sum(1 for o in self.received_orders if o.order_type == 'market')
        market_ratio = market_orders / len(self.received_orders)
        
        # In sudden bursts, market orders should be more common than the base distribution
        self.assertGreaterEqual(market_ratio, self.config['order_type_distribution']['market'])
    
    @patch('asyncio.sleep', return_value=None)  # Mock sleep to speed up tests
    async def test_ramp_burst_scenario(self, mock_sleep):
        """Test the RampBurstScenario generates orders correctly."""
        # Add ramp-specific configuration
        ramp_config = self.config.copy()
        ramp_config.update({
            'ramp_up_percentage': 0.3,
            'plateau_percentage': 0.4,
            'ramp_down_percentage': 0.3,
            'ramp_type': 'quadratic',
        })
        
        # Reset received orders
        self.received_orders = []
        
        # Create scenario generator
        generator = RampBurstScenario(ramp_config)
        
        # Add listener
        generator.add_listener(self.order_listener)
        
        # Start generator
        await generator.start()
        
        # Run a single burst
        await generator._generate_burst()
        
        # Stop generator
        await generator.stop()
        
        # Verify orders were generated
        self.assertTrue(len(self.received_orders) > 0, "No orders were generated")
        
        # Verify all orders are OrderData objects
        for order in self.received_orders:
            self.assertIsInstance(order, OrderData, f"Expected OrderData, got {type(order)}")
        
        # Verify burst size is within configured limits
        self.assertGreaterEqual(len(self.received_orders), self.config['burst_size_min'])
        self.assertLessEqual(len(self.received_orders), self.config['burst_size_max'])
        
        # Verify symbols are valid
        for order in self.received_orders:
            self.assertIn(order.symbol, self.config['symbols'])
    
    @patch('asyncio.sleep', return_value=None)  # Mock sleep to speed up tests
    async def test_oscillating_burst_scenario(self, mock_sleep):
        """Test that OscillatingBurstScenario generates orders correctly."""
        # Configure the scenario
        config = {
            'symbols': ['AAPL', 'MSFT', 'GOOGL'],
            'burst_frequency_min': 1,
            'burst_frequency_max': 5,
            'burst_size_min': 10,
            'burst_size_max': 20,
            'burst_duration_min': 1,
            'burst_duration_max': 3,
            'num_cycles': 2,
            'wave_type': 'sine',
            'amplitude_factor': 0.8,
            'phase_shift': 0.0,
            'market_triggered_oscillation': False
        }
        
        orders_received = []
        
        def order_callback(order: OrderData):
            orders_received.append(order)
        
        # Create and start the scenario
        generator = OscillatingBurstScenario(config)
        generator.add_listener(order_callback)
        
        # Run the generator for a short time
        task = asyncio.create_task(generator.start())
        await asyncio.sleep(0.1)  # Let it run briefly
        
        # Force a burst directly (bypassing the normal timer)
        await generator._generate_burst()
        
        # Stop the generator
        generator.stop()
        await task
        
        # Verify orders were generated
        self.assertTrue(len(orders_received) > 0)
        self.assertEqual(generator.bursts_generated, 1)
        
        # Check that orders have expected attributes
        for order in orders_received:
            self.assertIn(order.symbol, config['symbols'])
            self.assertIn(order.order_type, ['market', 'limit', 'stop'])
            self.assertTrue(order.order_id.startswith('ord_'))
    
    @patch('asyncio.sleep', return_value=None)  # Mock sleep to speed up tests
    async def test_oscillating_wave_types(self, mock_sleep):
        """Test OscillatingBurstScenario with different wave types."""
        wave_types = ['sine', 'square', 'triangle']
        
        for wave_type in wave_types:
            # Configure the scenario
            config = {
                'symbols': ['AAPL'],
                'burst_size_min': 15,
                'burst_size_max': 15,  # Fixed size for deterministic testing
                'burst_duration_min': 1,
                'burst_duration_max': 1,  # Fixed duration
                'num_cycles': 2,
                'wave_type': wave_type,
                'amplitude_factor': 0.8
            }
            
            orders_received = []
            
            def order_callback(order: OrderData):
                orders_received.append(order)
            
            # Create and run a single burst
            generator = OscillatingBurstScenario(config)
            generator.add_listener(order_callback)
            await generator._generate_burst()
            
            # Verify orders were generated
            self.assertGreater(len(orders_received), 0, f"No orders generated for wave type {wave_type}")
            self.assertEqual(generator.bursts_generated, 1)
    
    async def test_factory_creates_oscillating(self):
        """Test that the factory method creates OscillatingBurstScenario correctly."""
        config = {'symbols': ['AAPL']}
        
        # Create scenario through factory
        generator = create_burst_scenario('oscillating', config)
        
        # Verify type
        self.assertIsInstance(generator, OscillatingBurstScenario)
    
    def test_factory_invalid_type(self):
        """Test that factory raises error for invalid types."""
        with self.assertRaises(NotImplementedError):
            create_burst_scenario('invalid_type', {})


# Helper to run async tests
def run_async_test(coro):
    """Helper function to run coroutines in tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


if __name__ == '__main__':
    unittest.main() 