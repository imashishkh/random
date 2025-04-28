"""
Unit tests for the base dependency checking classes.
"""
import pytest
from unittest.mock import MagicMock, patch
import asyncio

from src.core.dependencies.base import (
    CheckStatus,
    CheckResult,
    DependencyCheck
)


class TestCheckStatus:
    """Tests for the CheckStatus enum."""
    
    def test_values(self):
        """Test that the enum has the expected values."""
        assert CheckStatus.SUCCESS is not None
        assert CheckStatus.WARNING is not None
        assert CheckStatus.FAILURE is not None
        
        # Test that the values are different
        assert CheckStatus.SUCCESS != CheckStatus.WARNING
        assert CheckStatus.SUCCESS != CheckStatus.FAILURE
        assert CheckStatus.WARNING != CheckStatus.FAILURE


class TestCheckResult:
    """Tests for the CheckResult class."""
    
    def test_init(self):
        """Test initialization of CheckResult."""
        result = CheckResult(
            name="test",
            status=CheckStatus.SUCCESS,
            message="Success",
            details={"key": "value"}
        )
        
        assert result.name == "test"
        assert result.status == CheckStatus.SUCCESS
        assert result.message == "Success"
        assert result.details == {"key": "value"}
    
    def test_is_successful(self):
        """Test is_successful property."""
        result = CheckResult(
            name="test",
            status=CheckStatus.SUCCESS,
            message="Success"
        )
        assert result.is_successful is True
        
        result = CheckResult(
            name="test",
            status=CheckStatus.WARNING,
            message="Warning"
        )
        assert result.is_successful is False
        
        result = CheckResult(
            name="test",
            status=CheckStatus.FAILURE,
            message="Failure"
        )
        assert result.is_successful is False
    
    def test_is_warning(self):
        """Test is_warning property."""
        result = CheckResult(
            name="test",
            status=CheckStatus.SUCCESS,
            message="Success"
        )
        assert result.is_warning is False
        
        result = CheckResult(
            name="test",
            status=CheckStatus.WARNING,
            message="Warning"
        )
        assert result.is_warning is True
        
        result = CheckResult(
            name="test",
            status=CheckStatus.FAILURE,
            message="Failure"
        )
        assert result.is_warning is False
    
    def test_is_failure(self):
        """Test is_failure property."""
        result = CheckResult(
            name="test",
            status=CheckStatus.SUCCESS,
            message="Success"
        )
        assert result.is_failure is False
        
        result = CheckResult(
            name="test",
            status=CheckStatus.WARNING,
            message="Warning"
        )
        assert result.is_failure is False
        
        result = CheckResult(
            name="test",
            status=CheckStatus.FAILURE,
            message="Failure"
        )
        assert result.is_failure is True
    
    def test_immutability(self):
        """Test that CheckResult is immutable."""
        result = CheckResult(
            name="test",
            status=CheckStatus.SUCCESS,
            message="Success"
        )
        
        with pytest.raises(Exception):
            result.name = "new_name"
        
        with pytest.raises(Exception):
            result.status = CheckStatus.FAILURE
        
        with pytest.raises(Exception):
            result.message = "New message"
        
        with pytest.raises(Exception):
            result.details = {"key": "value"}


class MockDependencyCheck(DependencyCheck):
    """Mock implementation of DependencyCheck for testing."""
    
    def __init__(self, name="test", result=None, **kwargs):
        super().__init__(name, **kwargs)
        self.result = result or CheckResult(
            name=name,
            status=CheckStatus.SUCCESS,
            message="Success"
        )
        self.execute_count = 0
    
    def _execute_check(self):
        self.execute_count += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class TestDependencyCheck:
    """Tests for the DependencyCheck class."""
    
    def test_init(self):
        """Test initialization of DependencyCheck."""
        check = MockDependencyCheck(
            name="test",
            description="Test description",
            dependencies=["dep1", "dep2"],
            retry_attempts=5,
            retry_backoff=10.0
        )
        
        assert check.name == "test"
        assert check.description == "Test description"
        assert check.dependencies == ["dep1", "dep2"]
        assert check.retry_attempts == 5
        assert check.retry_backoff == 10.0
    
    def test_execute_success(self):
        """Test execute method with successful check."""
        check = MockDependencyCheck()
        result = check.execute()
        
        assert check.execute_count == 1
        assert result.is_successful is True
        assert result.name == "test"
        assert result.message == "Success"
    
    def test_execute_failure(self):
        """Test execute method with failing check."""
        check = MockDependencyCheck(
            result=CheckResult(
                name="test",
                status=CheckStatus.FAILURE,
                message="Failure"
            )
        )
        result = check.execute()
        
        assert check.execute_count == 1
        assert result.is_failure is True
        assert result.name == "test"
        assert result.message == "Failure"
    
    def test_execute_exception(self):
        """Test execute method with exception."""
        check = MockDependencyCheck(
            result=Exception("Test exception")
        )
        result = check.execute()
        
        assert check.execute_count == 1
        assert result.is_failure is True
        assert result.name == "test"
        assert "Test exception" in result.message
    
    @pytest.mark.asyncio
    async def test_execute_async(self):
        """Test execute_async method."""
        check = MockDependencyCheck()
        result = await check.execute_async()
        
        assert check.execute_count == 1
        assert result.is_successful is True
        assert result.name == "test"
        assert result.message == "Success"
    
    @pytest.mark.asyncio
    async def test_execute_async_exception(self):
        """Test execute_async method with exception in thread pool execution."""
        check = MockDependencyCheck()
        
        # Mock the run_in_executor to raise an exception
        async def raise_exception(*args, **kwargs):
            raise Exception("Async exception")
        
        with patch.object(asyncio, "get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.run_in_executor = raise_exception
            mock_get_loop.return_value = mock_loop
            
            result = await check.execute_async()
            
            assert result.is_failure is True
            assert result.name == "test"
            assert "Async exception" in result.message 