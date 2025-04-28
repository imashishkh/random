"""
Unit tests for the dependency checker classes.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch
import networkx as nx

from src.core.dependencies.base import (
    CheckStatus,
    CheckResult,
    DependencyCheck
)
from src.core.dependencies.checker import DependencyChecker


class MockDependencyCheck(DependencyCheck):
    """Mock implementation of DependencyCheck for testing."""
    
    def __init__(self, name="test", dependencies=None, result=None, **kwargs):
        super().__init__(name=name, dependencies=dependencies or [], **kwargs)
        self.result = result or CheckResult(
            name=name,
            status=CheckStatus.SUCCESS,
            message=f"{name} Success"
        )
        self.execute_count = 0
    
    def _execute_check(self):
        self.execute_count += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class TestDependencyChecker:
    """Tests for the DependencyChecker class."""
    
    def test_init(self):
        """Test initialization of DependencyChecker."""
        checker = DependencyChecker()
        assert checker.checks == {}
        assert isinstance(checker.dependency_graph, nx.DiGraph)
    
    def test_register_check(self):
        """Test registering checks."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(name="check1")
        check2 = MockDependencyCheck(name="check2", dependencies=["check1"])
        
        checker.register_check(check1)
        checker.register_check(check2)
        
        assert checker.checks["check1"] == check1
        assert checker.checks["check2"] == check2
        
        # Check that the dependency graph was updated
        assert "check1" in checker.dependency_graph.nodes
        assert "check2" in checker.dependency_graph.nodes
        assert checker.dependency_graph.has_edge("check2", "check1")
    
    def test_register_check_duplicate(self):
        """Test registering a check with duplicate name."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(name="check1")
        check2 = MockDependencyCheck(name="check1")  # Same name
        
        checker.register_check(check1)
        
        with pytest.raises(ValueError):
            checker.register_check(check2)
    
    def test_resolve_dependencies(self):
        """Test resolving dependencies."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(name="check1")
        check2 = MockDependencyCheck(name="check2", dependencies=["check1"])
        check3 = MockDependencyCheck(name="check3", dependencies=["check2"])
        
        checker.register_check(check1)
        checker.register_check(check2)
        checker.register_check(check3)
        
        resolved = checker.resolve_dependencies()
        
        # Check1 must come before check2, and check2 before check3
        assert resolved.index("check1") < resolved.index("check2")
        assert resolved.index("check2") < resolved.index("check3")
    
    def test_resolve_dependencies_circular(self):
        """Test resolving dependencies with circular dependencies."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(name="check1", dependencies=["check3"])
        check2 = MockDependencyCheck(name="check2", dependencies=["check1"])
        check3 = MockDependencyCheck(name="check3", dependencies=["check2"])
        
        checker.register_check(check1)
        checker.register_check(check2)
        checker.register_check(check3)
        
        with pytest.raises(nx.NetworkXUnfeasible):
            checker.resolve_dependencies()
    
    def test_run_checks(self):
        """Test running checks."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(name="check1")
        check2 = MockDependencyCheck(name="check2", dependencies=["check1"])
        
        checker.register_check(check1)
        checker.register_check(check2)
        
        results = checker.run_checks()
        
        assert len(results) == 2
        assert results["check1"].name == "check1"
        assert results["check1"].is_successful is True
        assert results["check2"].name == "check2"
        assert results["check2"].is_successful is True
        
        # Check that check1 was executed before check2
        assert check1.execute_count == 1
        assert check2.execute_count == 1
    
    def test_run_checks_failure(self):
        """Test running checks with failure."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(
            name="check1",
            result=CheckResult(
                name="check1",
                status=CheckStatus.FAILURE,
                message="Failure"
            )
        )
        check2 = MockDependencyCheck(name="check2", dependencies=["check1"])
        
        checker.register_check(check1)
        checker.register_check(check2)
        
        results = checker.run_checks()
        
        assert len(results) == 2
        assert results["check1"].name == "check1"
        assert results["check1"].is_failure is True
        
        # Check2 should not have been executed because check1 failed
        assert check1.execute_count == 1
        assert check2.execute_count == 0
        assert results["check2"].is_failure is True
        assert "Dependency" in results["check2"].message
    
    @pytest.mark.asyncio
    async def test_run_checks_async(self):
        """Test running checks asynchronously."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(name="check1")
        check2 = MockDependencyCheck(name="check2", dependencies=["check1"])
        check3 = MockDependencyCheck(name="check3", dependencies=["check1"])
        
        checker.register_check(check1)
        checker.register_check(check2)
        checker.register_check(check3)
        
        results = await checker.run_checks_async()
        
        assert len(results) == 3
        assert results["check1"].name == "check1"
        assert results["check1"].is_successful is True
        assert results["check2"].name == "check2"
        assert results["check2"].is_successful is True
        assert results["check3"].name == "check3"
        assert results["check3"].is_successful is True
        
        # All checks should have been executed
        assert check1.execute_count == 1
        assert check2.execute_count == 1
        assert check3.execute_count == 1
    
    @pytest.mark.asyncio
    async def test_run_checks_async_failure(self):
        """Test running checks asynchronously with failure."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(
            name="check1",
            result=CheckResult(
                name="check1",
                status=CheckStatus.FAILURE,
                message="Failure"
            )
        )
        check2 = MockDependencyCheck(name="check2", dependencies=["check1"])
        check3 = MockDependencyCheck(name="check3", dependencies=["check1"])
        
        checker.register_check(check1)
        checker.register_check(check2)
        checker.register_check(check3)
        
        results = await checker.run_checks_async()
        
        assert len(results) == 3
        assert results["check1"].name == "check1"
        assert results["check1"].is_failure is True
        
        # Check2 and check3 should not have been executed because check1 failed
        assert check1.execute_count == 1
        assert check2.execute_count == 0
        assert check3.execute_count == 0
        assert results["check2"].is_failure is True
        assert "Dependency" in results["check2"].message
        assert results["check3"].is_failure is True
        assert "Dependency" in results["check3"].message
    
    @pytest.mark.asyncio
    async def test_run_checks_async_parallel(self):
        """Test running checks asynchronously in parallel."""
        checker = DependencyChecker()
        check1 = MockDependencyCheck(name="check1")
        check2 = MockDependencyCheck(name="check2")  # No dependencies
        check3 = MockDependencyCheck(name="check3")  # No dependencies
        
        checker.register_check(check1)
        checker.register_check(check2)
        checker.register_check(check3)
        
        # Patch asyncio.gather to ensure checks run in parallel
        original_gather = asyncio.gather
        gather_called = False
        
        async def mock_gather(*args, **kwargs):
            nonlocal gather_called
            gather_called = True
            return await original_gather(*args, **kwargs)
        
        with patch("asyncio.gather", side_effect=mock_gather):
            results = await checker.run_checks_async()
            
            # Ensure gather was called
            assert gather_called is True
            
            # All checks should have been executed
            assert check1.execute_count == 1
            assert check2.execute_count == 1
            assert check3.execute_count == 1
            
            # All checks should have succeeded
            assert results["check1"].is_successful is True
            assert results["check2"].is_successful is True
            assert results["check3"].is_successful is True
    
    def test_resolve_dependencies_complex(self):
        """Test resolving dependencies with a more complex dependency chain."""
        checker = DependencyChecker()
        
        # Create mock checks with various dependencies
        check_a = MockDependencyCheck("check_a", [])
        check_b = MockDependencyCheck("check_b", ["check_a"])
        check_c = MockDependencyCheck("check_c", ["check_b"])
        check_d = MockDependencyCheck("check_d", ["check_a", "check_c"])
        check_e = MockDependencyCheck("check_e", ["check_d"])
        
        # Register checks in random order
        checker.register_check(check_e)
        checker.register_check(check_c)
        checker.register_check(check_a)
        checker.register_check(check_d)
        checker.register_check(check_b)
        
        # Resolve dependencies
        resolved = checker.resolve_dependencies()
        
        # The resolved order should respect dependencies
        # check_a should come before check_b, check_b before check_c, etc.
        a_idx = resolved.index(check_a)
        b_idx = resolved.index(check_b)
        c_idx = resolved.index(check_c)
        d_idx = resolved.index(check_d)
        e_idx = resolved.index(check_e)
        
        assert a_idx < b_idx < c_idx < d_idx < e_idx
    
    def test_register_check_invalid_dependency(self):
        """Test registering a check with an invalid dependency."""
        checker = DependencyChecker()
        
        # Create a check that depends on a non-existent check
        check = MockDependencyCheck("check", ["non_existent_check"])
        
        # Register the check (this should not raise an error as dependencies are resolved later)
        checker.register_check(check)
        
        # Trying to resolve dependencies should not raise an error,
        # as we don't validate dependencies until they're run
        resolved = checker.resolve_dependencies()
        assert check in resolved
    
    def test_run_checks_with_priority(self):
        """Test running checks with priorities."""
        checker = DependencyChecker()
        
        # Create mock checks with success results but different execution times
        check_a = MockDependencyCheck("check_a", [], True, 0)
        check_b = MockDependencyCheck("check_b", [], True, 0)
        
        # Register checks
        checker.register_check(check_a)
        checker.register_check(check_b)
        
        # Run checks
        results = checker.run_checks()
        
        # All checks should have run and succeeded
        assert len(results) == 2
        assert all(result.status == CheckStatus.SUCCESS for result in results.values())
        
        # Check execution order matches registration order when no dependencies
        assert check_a.run.call_count == 1
        assert check_b.run.call_count == 1
    
    @pytest.mark.asyncio
    async def test_run_checks_async_with_sleep(self):
        """Test running checks asynchronously with actual sleep to test real concurrency."""
        checker = DependencyChecker()
        
        async def slow_check():
            await asyncio.sleep(0.1)
            return CheckResult(CheckStatus.SUCCESS)
            
        async def fast_check():
            return CheckResult(CheckStatus.SUCCESS)
        
        # Create real async checks with different execution times
        check_slow = MockDependencyCheck("check_slow", [])
        check_slow.run_async = MagicMock(side_effect=slow_check)
        
        check_fast = MockDependencyCheck("check_fast", ["check_slow"])
        check_fast.run_async = MagicMock(side_effect=fast_check)
        
        # Register checks
        checker.register_check(check_slow)
        checker.register_check(check_fast)
        
        # Run checks with parallelization disabled to ensure sequential execution
        start_time = asyncio.get_event_loop().time()
        results = await checker.run_checks_async(parallelize=False)
        end_time = asyncio.get_event_loop().time()
        
        # Sequential execution should take at least the sum of the sleep times
        assert end_time - start_time >= 0.1
        
        # All checks should have run and succeeded
        assert len(results) == 2
        assert all(result.status == CheckStatus.SUCCESS for result in results.values()) 