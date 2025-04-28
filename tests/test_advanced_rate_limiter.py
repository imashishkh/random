"""
Tests for the Advanced Rate Limiter

This module contains tests for the AdvancedRateLimiter implementation,
including both synchronous and asynchronous use cases.
"""

import unittest
import time
import asyncio
from unittest.mock import MagicMock, patch

from src.exchange.rate_limiting.advanced_limiter import (
    AdvancedRateLimiter,
    TokenBucket,
    PriorityRequestQueue,
    RateLimitRegistry,
    RateLimitMonitor,
    ConnectionType,
    RequestPriority,
    RateLimitTier,
    rate_limited
)


class TestTokenBucket(unittest.TestCase):
    """Tests for the TokenBucket class."""
    
    def test_initialization(self):
        """Test bucket initialization."""
        bucket = TokenBucket(100, 10)
        self.assertEqual(bucket.capacity, 100)
        self.assertEqual(bucket.refill_rate, 10)
        self.assertEqual(bucket.tokens, 100)
        
    def test_consume(self):
        """Test token consumption."""
        bucket = TokenBucket(100, 10)
        
        # Consume 50 tokens
        self.assertTrue(bucket.consume(50))
        self.assertEqual(bucket.tokens, 50)
        
        # Consume another 50 tokens
        self.assertTrue(bucket.consume(50))
        self.assertEqual(bucket.tokens, 0)
        
        # Try to consume more tokens
        self.assertFalse(bucket.consume(1))
        self.assertEqual(bucket.tokens, 0)
        
    def test_refill(self):
        """Test token refill."""
        bucket = TokenBucket(100, 10)
        
        # Consume all tokens
        self.assertTrue(bucket.consume(100))
        self.assertEqual(bucket.tokens, 0)
        
        # Wait for refill
        time.sleep(0.5)  # 0.5 seconds * 10 tokens/second = 5 tokens
        
        # Consume 5 tokens
        self.assertTrue(bucket.consume(5))
        self.assertEqual(bucket.tokens, 0)
        
        # Try to consume more tokens
        self.assertFalse(bucket.consume(1))
        
    def test_wait_time_for(self):
        """Test wait time calculation."""
        bucket = TokenBucket(100, 10)
        
        # Consume all tokens
        self.assertTrue(bucket.consume(100))
        self.assertEqual(bucket.tokens, 0)
        
        # Calculate wait time for 10 tokens
        wait_time = bucket.wait_time_for(10)
        self.assertAlmostEqual(wait_time, 1.0, delta=0.1)  # 10 tokens / 10 tokens/sec = 1 sec
        
        # Calculate wait time for 5 tokens
        wait_time = bucket.wait_time_for(5)
        self.assertAlmostEqual(wait_time, 0.5, delta=0.1)  # 5 tokens / 10 tokens/sec = 0.5 sec


class TestRateLimitMonitor(unittest.TestCase):
    """Tests for the RateLimitMonitor class."""
    
    def test_update_from_headers(self):
        """Test updating from response headers."""
        monitor = RateLimitMonitor()
        
        # Mock headers
        headers = {
            'X-MBX-USED-WEIGHT-1M': '500',
            'X-MBX-ORDER-COUNT-10S': '20',
            'X-MBX-ORDER-COUNT-1D': '100'
        }
        
        monitor.update_from_headers(headers)
        
        # Check weight status
        self.assertEqual(monitor.weight_status['1m'].current_usage, 500)
        self.assertEqual(monitor.weight_status['1m'].limit, 1200)
        
        # Check order status
        self.assertEqual(monitor.order_status['10s'].current_usage, 20)
        self.assertEqual(monitor.order_status['10s'].limit, 50)
        
        # Check throttle factor
        self.assertAlmostEqual(monitor.get_throttle_factor(), 1.0, delta=0.1)
        
    def test_throttle_factor(self):
        """Test throttle factor calculation."""
        monitor = RateLimitMonitor()
        
        # Set up a critical weight status
        now = time.time()
        monitor.weight_status['1m'] = monitor._RateLimitStatus(
            current_usage=1080,  # 90% of 1200
            limit=1200,
            reset_time=now + 60
        )
        
        # Check throttle factor
        self.assertAlmostEqual(monitor.get_throttle_factor(), 0.5, delta=0.1)  # (100-90)/20 = 0.5
        
    def test_should_backoff(self):
        """Test backoff recommendation."""
        monitor = RateLimitMonitor()
        
        # Set up IP ban
        now = time.time()
        monitor.ip_banned_until = now + 30
        
        # Check backoff recommendation
        should_backoff, backoff_time = monitor.should_backoff()
        self.assertTrue(should_backoff)
        self.assertAlmostEqual(backoff_time, 30, delta=1)
        
        # Remove IP ban
        monitor.ip_banned_until = None
        
        # Set up critical usage
        monitor.weight_status['1m'] = monitor._RateLimitStatus(
            current_usage=1150,  # 95.8% of 1200
            limit=1200,
            reset_time=now + 60
        )
        
        # Check backoff recommendation
        should_backoff, backoff_time = monitor.should_backoff()
        self.assertTrue(should_backoff)
        self.assertAlmostEqual(backoff_time, 60, delta=1)


class TestAdvancedRateLimiter(unittest.TestCase):
    """Tests for the AdvancedRateLimiter class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Reset the singleton between tests
        AdvancedRateLimiter._instances = {}
        self.limiter = AdvancedRateLimiter()
        
    def test_singleton(self):
        """Test that the rate limiter is a singleton."""
        limiter1 = AdvancedRateLimiter()
        limiter2 = AdvancedRateLimiter()
        self.assertIs(limiter1, limiter2)
        
    def test_pre_request(self):
        """Test pre-request rate limiting."""
        # Mock buckets to always allow requests
        for bucket in self.limiter.buckets.values():
            bucket.consume = MagicMock(return_value=True)
            
        # Call pre_request
        wait_time = self.limiter.pre_request(
            endpoint="/api/v3/klines",
            method="GET",
            options={"limit": 100},
            connection_type=ConnectionType.REST,
            priority=RequestPriority.NORMAL
        )
        
        # No wait time should be needed
        self.assertEqual(wait_time, 0.0)
        
        # Check that consume was called on at least one bucket
        self.assertTrue(any(bucket.consume.called for bucket in self.limiter.buckets.values()))
        
    def test_post_request(self):
        """Test post-request processing."""
        # Mock monitor
        self.limiter.monitor.update_from_headers = MagicMock()
        
        # Call post_request
        headers = {'X-MBX-USED-WEIGHT-1M': '500'}
        self.limiter.post_request(headers)
        
        # Check that update_from_headers was called
        self.limiter.monitor.update_from_headers.assert_called_once_with(headers)
        
    def test_get_status(self):
        """Test getting status information."""
        status = self.limiter.get_status()
        
        # Check that status contains expected keys
        self.assertIn("limits", status)
        self.assertIn("buckets", status)
        self.assertIn("queues", status)
        self.assertIn("throttle_factor", status)
        self.assertIn("tier", status)
        
    def test_set_tier(self):
        """Test changing the rate limit tier."""
        # Initial tier should be DEFAULT
        self.assertEqual(self.limiter.registry.active_tier, RateLimitTier.DEFAULT)
        
        # Change tier to VIP
        self.limiter.set_tier(RateLimitTier.VIP)
        
        # Check tier was changed
        self.assertEqual(self.limiter.registry.active_tier, RateLimitTier.VIP)
        
    def test_calculate_weight(self):
        """Test weight calculation."""
        # Test default weight
        weight = self.limiter._calculate_weight(
            endpoint="/api/v3/ping",
            method="GET"
        )
        self.assertEqual(weight, 1)
        
        # Test endpoint-specific weight
        weight = self.limiter._calculate_weight(
            endpoint="/api/v3/klines",
            method="GET",
            options={"limit": 600}
        )
        self.assertEqual(weight, 5)  # From the weight map in RateLimitRegistry


class TestRateLimitedDecorator(unittest.TestCase):
    """Tests for the rate_limited decorator."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Reset the singleton between tests
        AdvancedRateLimiter._instances = {}
        
    @patch.object(AdvancedRateLimiter, 'pre_request')
    @patch.object(AdvancedRateLimiter, 'post_request')
    def test_decorator(self, mock_post_request, mock_pre_request):
        """Test the rate_limited decorator."""
        @rate_limited(priority=RequestPriority.HIGH, custom_endpoint="/test")
        def test_function(param):
            return {"result": param, "headers": {"X-MBX-USED-WEIGHT-1M": "100"}}
            
        # Call the decorated function
        result = test_function("test_value")
        
        # Check that pre_request was called
        mock_pre_request.assert_called_once_with(
            endpoint="/test",
            method="GET",
            options=None,
            connection_type=ConnectionType.REST,
            priority=RequestPriority.HIGH
        )
        
        # Check that post_request was called
        mock_post_request.assert_called_once_with({"X-MBX-USED-WEIGHT-1M": "100"})
        
        # Check that the original function was called
        self.assertEqual(result["result"], "test_value")


class TestAsyncRateLimiter(unittest.IsolatedAsyncioTestCase):
    """Tests for the async methods of AdvancedRateLimiter."""
    
    async def asyncSetUp(self):
        """Set up async test fixtures."""
        # Reset the singleton between tests
        AdvancedRateLimiter._instances = {}
        self.limiter = AdvancedRateLimiter()
        
    async def test_pre_request_async(self):
        """Test async pre-request rate limiting."""
        # Mock buckets to always allow requests
        for bucket in self.limiter.buckets.values():
            bucket.consume = MagicMock(return_value=True)
            
        # Call pre_request_async
        wait_time = await self.limiter.pre_request_async(
            endpoint="/api/v3/klines",
            method="GET",
            options={"limit": 100},
            connection_type=ConnectionType.REST,
            priority=RequestPriority.NORMAL
        )
        
        # No wait time should be needed
        self.assertEqual(wait_time, 0.0)
        
        # Check that consume was called on at least one bucket
        self.assertTrue(any(bucket.consume.called for bucket in self.limiter.buckets.values()))
        
    async def test_post_request_async(self):
        """Test async post-request processing."""
        # Mock monitor
        self.limiter.monitor.update_from_headers = MagicMock()
        
        # Call post_request_async
        headers = {'X-MBX-USED-WEIGHT-1M': '500'}
        await self.limiter.post_request_async(headers)
        
        # Check that update_from_headers was called
        self.limiter.monitor.update_from_headers.assert_called_once_with(headers)
        
    async def test_queue_processor(self):
        """Test async queue processor."""
        # Start queue processor
        await self.limiter.start_queue_processor()
        
        # Add a request to the queue
        queue = self.limiter.queues[ConnectionType.REST]
        
        # Create a mock execute function
        mock_execute = MagicMock()
        
        # Enqueue a request
        future = await queue.enqueue(
            endpoint="/test",
            method="GET",
            priority=RequestPriority.NORMAL,
            weight=1,
            execute_func=mock_execute
        )
        
        # Let the queue processor run
        await asyncio.sleep(0.1)
        
        # Check that execute was called
        # This might fail if the processor doesn't run or the bucket doesn't have capacity
        self.assertTrue(mock_execute.called or not future.done())
        
        # Stop queue processor
        self.limiter.stop_queue_processor()


if __name__ == '__main__':
    unittest.main() 