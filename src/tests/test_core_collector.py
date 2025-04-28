"""
Unit tests for the core collector module.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

from ..core.collector import (
    BaseCollector,
    RetrySettings,
    RateLimitSettings,
    CollectorError,
    RequestError,
    ValidationError,
    RateLimitError
)


class TestCollector(BaseCollector[dict]):
    """Test implementation of BaseCollector."""
    
    def __init__(self, name="test-collector", *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.collect_mock = AsyncMock()
        self.validate_mock = AsyncMock()
    
    async def collect(self, *args, **kwargs) -> dict:
        """Mock implementation of collect."""
        return await self.collect_mock(*args, **kwargs)
    
    async def validate(self, data: dict) -> dict:
        """Mock implementation of validate."""
        return await self.validate_mock(data)


@pytest.fixture
def collector():
    """Fixture for a test collector."""
    return TestCollector()


@pytest.mark.asyncio
async def test_collector_successful_call(collector):
    """Test successful data collection."""
    # Setup
    collector.collect_mock.return_value = {"data": "test"}
    collector.validate_mock.return_value = {"validated": "data"}
    
    # Execute
    result = await collector.collect_and_validate()
    
    # Verify
    assert result == {"validated": "data"}
    collector.collect_mock.assert_called_once()
    collector.validate_mock.assert_called_once_with({"data": "test"})


@pytest.mark.asyncio
async def test_retry_logic_successful_after_retries():
    """Test that retry logic works when a call succeeds after failures."""
    # Setup
    mock_func = AsyncMock()
    mock_func.side_effect = [
        RequestError("First failure", 500),
        RequestError("Second failure", 500),
        {"success": True}
    ]
    
    retry_settings = RetrySettings(
        max_retries=3,
        initial_delay=0.01,  # Use small delays for testing
        max_delay=0.05,
        backoff_factor=2.0,
        jitter=0.1,
        retry_on_status_codes=[500]
    )
    
    collector = TestCollector(retry_settings=retry_settings)
    
    # Execute
    with patch('asyncio.sleep', AsyncMock()) as mock_sleep:
        result = await collector.process_with_retry(mock_func)
    
    # Verify
    assert result == {"success": True}
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2  # Sleep called between retries


@pytest.mark.asyncio
async def test_retry_logic_fails_after_max_retries():
    """Test that retry logic gives up after max_retries."""
    # Setup
    mock_func = AsyncMock()
    mock_func.side_effect = RequestError("Persistent failure", 500)
    
    retry_settings = RetrySettings(
        max_retries=2,
        initial_delay=0.01,
        max_delay=0.05,
        backoff_factor=2.0,
        retry_on_status_codes=[500]
    )
    
    collector = TestCollector(retry_settings=retry_settings)
    
    # Execute and verify
    with patch('asyncio.sleep', AsyncMock()):
        with pytest.raises(RequestError) as excinfo:
            await collector.process_with_retry(mock_func)
    
    # Verify
    assert "Persistent failure" in str(excinfo.value)
    assert mock_func.call_count == 3  # Initial call + 2 retries


@pytest.mark.asyncio
async def test_circuit_breaker_prevents_calls_when_open():
    """Test that circuit breaker prevents calls when open."""
    # Setup
    mock_func = AsyncMock()
    collector = TestCollector(
        circuit_breaker_failure_threshold=2,
        circuit_breaker_recovery_timeout=30
    )
    
    # Force circuit breaker open
    collector.circuit_breaker.failure_count = 2
    collector.circuit_breaker.is_open = True
    collector.circuit_breaker.last_failure_time = datetime.utcnow()
    
    # Execute and verify
    with pytest.raises(CollectorError) as excinfo:
        await collector.process_with_retry(mock_func)
    
    # Verify
    assert "Circuit breaker open" in str(excinfo.value)
    mock_func.assert_not_called()


@pytest.mark.asyncio
async def test_circuit_breaker_allows_retry_after_timeout():
    """Test that circuit breaker allows retry after recovery timeout."""
    # Setup
    mock_func = AsyncMock()
    mock_func.return_value = {"success": True}
    
    collector = TestCollector(
        circuit_breaker_failure_threshold=2,
        circuit_breaker_recovery_timeout=1  # 1 second
    )
    
    # Force circuit breaker open but with an old timestamp
    collector.circuit_breaker.failure_count = 2
    collector.circuit_breaker.is_open = True
    collector.circuit_breaker.last_failure_time = datetime.utcnow() - timedelta(seconds=2)
    
    # Execute
    result = await collector.process_with_retry(mock_func)
    
    # Verify
    assert result == {"success": True}
    mock_func.assert_called_once()
    assert collector.circuit_breaker.is_open is False  # Success should reset the breaker


@pytest.mark.asyncio
async def test_rate_limiting():
    """Test that rate limiting prevents too many calls."""
    # Setup
    mock_func = AsyncMock()
    mock_func.return_value = {"success": True}
    
    rate_limit_settings = RateLimitSettings(
        requests_per_minute=2,
        requests_per_hour=10,
        requests_per_day=20,
        enabled=True
    )
    
    collector = TestCollector(rate_limit_settings=rate_limit_settings)
    
    # Add simulated requests to hit the rate limit
    now = datetime.utcnow()
    collector.request_timestamps = [
        now - timedelta(seconds=10),
        now - timedelta(seconds=5)
    ]
    
    # Execute and verify
    with pytest.raises(RateLimitError) as excinfo:
        await collector.process_with_retry(mock_func)
    
    # Verify
    assert "Rate limit exceeded" in str(excinfo.value)
    mock_func.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limiting_disabled():
    """Test that rate limiting can be disabled."""
    # Setup
    mock_func = AsyncMock()
    mock_func.return_value = {"success": True}
    
    rate_limit_settings = RateLimitSettings(
        requests_per_minute=2,
        requests_per_hour=10,
        requests_per_day=20,
        enabled=False
    )
    
    collector = TestCollector(rate_limit_settings=rate_limit_settings)
    
    # Add simulated requests that would exceed the rate limit if enabled
    now = datetime.utcnow()
    collector.request_timestamps = [
        now - timedelta(seconds=10),
        now - timedelta(seconds=5)
    ]
    
    # Execute
    result = await collector.process_with_retry(mock_func)
    
    # Verify
    assert result == {"success": True}
    mock_func.assert_called_once()
    assert len(collector.request_timestamps) == 3  # Original 2 + new request 