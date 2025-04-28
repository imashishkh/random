"""
Boot Sequence Manager for Forex Trading System

This module provides a robust, deterministic boot sequence for the trading
environment, ensuring components start in the correct order with proper
error handling, recovery mechanisms, and graceful shutdown capabilities.
"""

import asyncio
import logging
import os
import signal
import sys
import time
import yaml
import random
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from abc import ABC, abstractmethod
import contextlib
import traceback
import functools
import inspect

# Import the dependency checking system
from .dependencies import (
    DependencyChecker,
    RedisCheck,
    PostgresCheck, 
    BinanceApiCheck,
    FileSystemCheck,
    PortCheck
)

# Import the boot configuration manager
from ..utils.boot_config_manager import BootConfigManager

# Import the logger
from ..utils.logger import get_logger

# Set up logger for this module
logger = get_logger("boot")

# Forward declaration for type checking
class Component:
    pass

class CircuitBreaker:
    pass

class RecoveryPolicy:
    pass

# States that components can be in during boot process
class ComponentState(Enum):
    """Enum for tracking component states during boot process."""
    UNINITIALIZED = auto()
    INITIALIZING = auto()
    READY = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    FAILED = auto()
    DEGRADED = auto()


# Component Registry data class
@dataclass
class ComponentEntry:
    """Entry in the component registry."""
    component: 'Component'
    circuit_breaker: Optional[CircuitBreaker] = None
    recovery_policy: Optional[RecoveryPolicy] = None
    hooks: Dict[str, List[Callable]] = field(default_factory=lambda: {
        "pre_initialize": [],
        "post_initialize": [],
        "pre_start": [],
        "post_start": [],
        "pre_stop": [],
        "post_stop": [],
        "health_check": []
    })


class ComponentRegistry:
    """
    Registry for tracking components and their states during boot process.
    
    This class manages component registration, state transitions, and hook execution
    throughout the component lifecycle.
    """
    
    def __init__(self):
        """Initialize the component registry."""
        self.components = {}  # name -> Component
        self.entries = {}     # name -> ComponentEntry
        self.component_states = {}  # name -> ComponentState
        self.state_change_log = []  # List of state change events
        logger.debug("Component registry initialized")
    
    async def register_component(
        self, 
        component: Component, 
        circuit_breaker: CircuitBreaker = None, 
        recovery_policy: RecoveryPolicy = None
    ):
        """
        Register a component with the registry.
        
        Args:
            component: Component to register
            circuit_breaker: Optional circuit breaker for the component
            recovery_policy: Optional recovery policy for the component
        """
        if component.name in self.components:
            logger.warning(f"Component {component.name} already registered. Replacing.")
        
        # Use default recovery policy if none provided
        if recovery_policy is None:
            recovery_policy = RecoveryPolicy()
        
        # Create component entry
        entry = ComponentEntry(
            component=component,
            circuit_breaker=circuit_breaker,
            recovery_policy=recovery_policy
        )
        
        # Store component and entry
        self.components[component.name] = component
        self.entries[component.name] = entry
        self.component_states[component.name] = ComponentState.UNINITIALIZED
        
        logger.info(f"Component {component.name} registered successfully")
    
    async def get_component(self, name: str) -> Component:
        """
        Get a component by name.
        
        Args:
            name: Component name
            
        Returns:
            Component instance
            
        Raises:
            ValueError: If component not found
        """
        if name not in self.components:
            raise ValueError(f"Component {name} not found in registry")
        
        return self.components[name]
    
    async def get_entry(self, name: str) -> ComponentEntry:
        """
        Get a component entry by name.
        
        Args:
            name: Component name
            
        Returns:
            ComponentEntry instance
            
        Raises:
            ValueError: If component not found
        """
        if name not in self.entries:
            raise ValueError(f"Component {name} not found in registry")
        
        return self.entries[name]
    
    async def get_component_state(self, name: str) -> ComponentState:
        """
        Get the current state of a component.
        
        Args:
            name: Component name
            
        Returns:
            Component state
            
        Raises:
            ValueError: If component not found
        """
        if name not in self.component_states:
            raise ValueError(f"Component {name} not found in registry")
        
        return self.component_states[name]
    
    async def update_component_state(self, name: str, state: ComponentState):
        """
        Update the state of a component.
        
        Args:
            name: Component name
            state: New component state
            
        Raises:
            ValueError: If component doesn't exist
        """
        if name not in self.components:
            raise ValueError(f"Component not found: {name}")
        
        old_state = self.component_states.get(name)
        if old_state != state:
            old_state_name = old_state.name if old_state else "None"
            logger.info(f"Component {name} state changed: {old_state_name} -> {state.name}")
            self.component_states[name] = state
            
            # Log entry for state changes
            self.state_change_log.append({
                "component": name,
                "old_state": old_state,
                "new_state": state,
                "timestamp": time.time()
            })
            
            # Get boot manager to emit event (if available)
            from_boot_manager = False
            try:
                # Avoid circular import
                boot_manager = BootManager.get_instance()
                # Check if we were called from BootManager to avoid infinite recursion
                current_frame = inspect.currentframe()
                calling_frame = inspect.getouterframes(current_frame, 2)
                for frame_info in calling_frame[1:]:  # Skip current frame
                    if frame_info.function in ["_phase_service_startup", "boot"]:
                        from_boot_manager = True
                        break
                
                # Only emit event if NOT called from BootManager (prevents duplicate events)
                if not from_boot_manager and hasattr(boot_manager, 'emit_event'):
                    # Use create_task to avoid blocking
                    asyncio.create_task(boot_manager.emit_event("component_state_changed", {
                        "component": name,
                        "state": state,
                        "previous_state": old_state
                    }))
            except (ImportError, AttributeError, Exception) as e:
                # This can happen if the ComponentRegistry is used outside the BootManager context
                logger.debug(f"Could not emit component state event: {str(e)}")
                pass
    
    async def register_hook(self, name: str, hook_type: str, hook_func: Callable):
        """
        Register a hook function for a component.
        
        Args:
            name: Component name
            hook_type: Hook type (pre_initialize, post_initialize, etc.)
            hook_func: Hook function
            
        Raises:
            ValueError: If component not found or hook type is invalid
        """
        if name not in self.entries:
            raise ValueError(f"Component {name} not found in registry")
        
        entry = self.entries[name]
        
        if hook_type not in entry.hooks:
            valid_hooks = list(entry.hooks.keys())
            raise ValueError(f"Invalid hook type: {hook_type}. Valid types: {valid_hooks}")
        
        entry.hooks[hook_type].append(hook_func)
        logger.debug(f"Registered {hook_type} hook for component {name}")
    
    async def call_hooks(self, name: str, hook_type: str):
        """
        Call all hooks of a specific type for a component.
        
        Args:
            name: Component name
            hook_type: Hook type (pre_initialize, post_initialize, etc.)
            
        Raises:
            ValueError: If component not found or hook type is invalid
        """
        if name not in self.entries:
            raise ValueError(f"Component {name} not found in registry")
        
        entry = self.entries[name]
        
        if hook_type not in entry.hooks:
            valid_hooks = list(entry.hooks.keys())
            raise ValueError(f"Invalid hook type: {hook_type}. Valid types: {valid_hooks}")
        
        for hook in entry.hooks[hook_type]:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.error(f"Error in {hook_type} hook for component {name}: {str(e)}")
    
    async def get_all_components(self) -> Dict[str, Component]:
        """
        Get all registered components.
        
        Returns:
            Dictionary of component names to component instances
        """
        return self.components.copy()


class Component(ABC):
    """
    Abstract base class for all bootable components.
    
    All components that need to be managed by the boot process should
    implement this interface.
    """
    
    def __init__(self, name: str, dependencies: List[str] = None):
        """
        Initialize a component.
        
        Args:
            name: Unique name of the component
            dependencies: List of component names this component depends on
        """
        self.name = name
        self.dependencies = dependencies or []
        self.state = ComponentState.UNINITIALIZED
        self.health_check_interval = 60  # seconds
        self.startup_timeout = 30  # seconds
        self.startup_time = None
        self.startup_order = None  # Will be set by the boot manager
        self.metadata = {}
        
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the component's resources.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """
        Start the component's operations.
        
        Returns:
            True if startup was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """
        Stop the component gracefully.
        
        Returns:
            True if shutdown was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the component is operating correctly.
        
        Returns:
            True if the component is healthy, False otherwise
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> bool:
        """
        Clean up resources used by the component.
        
        Returns:
            True if cleanup was successful, False otherwise
        """
        pass


class CircuitOpenError(Exception):
    """Exception raised when a circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Implements the Circuit Breaker pattern for external service calls.
    
    This pattern prevents cascading failures by cutting off calls to services
    that are likely to fail, allowing them time to recover.
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        half_open_max_calls: int = 1
    ):
        """
        Initialize the circuit breaker.
        
        Args:
            name: Name for this circuit breaker (for logging)
            failure_threshold: Number of failures before opening circuit
            reset_timeout: Seconds to wait before trying service again
            half_open_max_calls: Max concurrent calls in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls
        
        # State tracking
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.currently_executing = 0
        self._state_change_callbacks = []
    
    def register_state_change_callback(self, callback: Callable[[str, str], None]):
        """
        Register a callback for circuit state changes.
        
        Args:
            callback: Function to call when state changes, receives (old_state, new_state)
        """
        self._state_change_callbacks.append(callback)
    
    def _change_state(self, new_state: str):
        """
        Change the circuit state with notifications.
        
        Args:
            new_state: New circuit state
        """
        old_state = self.state
        self.state = new_state
        logger.info(f"Circuit breaker '{self.name}' state change: {old_state} -> {new_state}")
        
        for callback in self._state_change_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in circuit breaker callback: {str(e)}")
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of the function call
            
        Raises:
            CircuitOpenError: If the circuit is open
            Exception: Any exception from the function call
        """
        # Check if circuit is open
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
                # Transition to half-open after timeout
                self._change_state("HALF-OPEN")
            else:
                # Fast fail if circuit is open
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is open. "
                    f"Retry after {self.reset_timeout - (time.time() - self.last_failure_time):.2f}s"
                )
        
        # Handle half-open state (limit concurrent calls)
        if self.state == "HALF-OPEN" and self.currently_executing >= self.half_open_max_calls:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is half-open and at capacity. "
                f"Max allowed calls: {self.half_open_max_calls}"
            )
        
        # Track concurrent execution
        self.currently_executing += 1
        
        try:
            # Execute the function
            result = await func(*args, **kwargs)
            
            # Success case
            if self.state == "HALF-OPEN":
                # If successful in half-open state, close the circuit
                self._change_state("CLOSED")
            
            # Reset failure count on success
            self.failure_count = 0
            
            return result
            
        except Exception as e:
            # Failure case
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            # Check if we should open the circuit
            if (self.state == "CLOSED" and self.failure_count >= self.failure_threshold) or \
               (self.state == "HALF-OPEN"):
                self._change_state("OPEN")
            
            # Re-raise the original exception
            raise
            
        finally:
            # Always decrement concurrent execution count
            self.currently_executing -= 1


class RecoveryPolicy:
    """Defines how to recover from component failures."""
    
    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        jitter: float = 0.2,
        retry_interval: float = 1.0
    ):
        """
        Initialize the recovery policy.
        
        Args:
            max_retries: Maximum number of retry attempts
            backoff_factor: Factor to increase delay between retries
            jitter: Random factor to add to delay (0-1)
            retry_interval: Initial retry interval in seconds
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.retry_interval = retry_interval
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with retry logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of the function call
            
        Raises:
            Exception: Last exception encountered after all retries
        """
        retries = 0
        last_exception = None
        
        while retries <= self.max_retries:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                retries += 1
                last_exception = e
                
                if retries > self.max_retries:
                    logger.error(
                        f"All {self.max_retries} retry attempts failed: {str(e)}"
                    )
                    break
                
                # Calculate backoff with jitter
                delay = self.retry_interval * (self.backoff_factor ** (retries - 1))
                jitter_amount = self.jitter * delay
                adjusted_delay = delay + random.uniform(-jitter_amount, jitter_amount)
                adjusted_delay = max(0, adjusted_delay)  # Ensure non-negative
                
                logger.warning(
                    f"Retry {retries}/{self.max_retries} after {adjusted_delay:.2f}s: {str(e)}"
                )
                await asyncio.sleep(adjusted_delay)
        
        # If we get here, all retries failed
        raise last_exception


class DependencyResolver:
    """
    Resolves component dependencies to determine boot order.
    
    This class implements topological sorting of a component dependency
    graph to ensure that components are started in the correct order.
    """
    
    def __init__(self):
        """Initialize the dependency resolver."""
        self.graph = {}
        self.visited = {}
        self.temp_mark = {}
        self.sorted_components = []
    
    def add_component(self, component_name: str, dependencies: List[str] = None):
        """
        Add a component to the dependency graph.
        
        Args:
            component_name: Name of the component
            dependencies: List of component names this component depends on
        """
        dependencies = dependencies or []
        if component_name not in self.graph:
            self.graph[component_name] = set()
        
        for dependency in dependencies:
            if dependency not in self.graph:
                self.graph[dependency] = set()
            self.graph[component_name].add(dependency)
    
    def topological_sort(self) -> List[str]:
        """
        Perform topological sort on the dependency graph.
        
        Returns:
            List of component names in dependency order (deepest first)
            
        Raises:
            ValueError: If there are circular dependencies
        """
        self.visited = {node: False for node in self.graph}
        self.temp_mark = {node: False for node in self.graph}
        self.sorted_components = []
        
        for node in self.graph:
            if not self.visited[node]:
                self._visit(node)
        
        # Reverse the order so that components with no dependencies start first
        return self.sorted_components
    
    def _visit(self, node: str):
        """
        Visit a node in the dependency graph (DFS).
        
        Args:
            node: Name of the node to visit
            
        Raises:
            ValueError: If a circular dependency is detected
        """
        if self.temp_mark[node]:
            cycle_path = self._find_cycle_path(node)
            raise ValueError(f"Circular dependency detected: {' -> '.join(cycle_path)}")
        
        if not self.visited[node]:
            self.temp_mark[node] = True
            
            for dependency in self.graph[node]:
                self._visit(dependency)
            
            self.temp_mark[node] = False
            self.visited[node] = True
            self.sorted_components.append(node)
    
    def _find_cycle_path(self, start_node: str) -> List[str]:
        """
        Find the path of a cycle in the dependency graph.
        
        Args:
            start_node: Node where the cycle was detected
            
        Returns:
            List of nodes in the cycle path
        """
        path = [start_node]
        current = start_node
        
        # Find a path back to the start node
        for node, deps in self.graph.items():
            if current in deps and self.temp_mark[node]:
                path.append(node)
                current = node
                if current == start_node:
                    break
        
        return path


class BootManager:
    """
    Central manager for the boot process.
    
    This class is responsible for coordinating the entire boot process,
    including dependency resolution, component initialization, startup,
    monitoring, and shutdown.
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls, config_path: str = None):
        """
        Get or create the singleton instance of BootManager.
        
        Args:
            config_path: Optional path to configuration file
            
        Returns:
            BootManager instance
        """
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance
    
    def __init__(self, config_path: str = None):
        """
        Initialize the boot manager.
        
        Args:
            config_path: Optional path to configuration file
        """
        if config_path:
            self.config_path = config_path
        else:
            # Try to find the configuration file in standard locations
            standard_paths = [
                "config/boot.yaml",
                "config/boot.yml",
                "boot.yaml",
                "boot.yml"
            ]
            
            for path in standard_paths:
                if os.path.exists(path):
                    self.config_path = path
                    break
            else:
                # Default to the first path if none found
                self.config_path = standard_paths[0]
        
        # Initialize managers and utilities
        self.boot_config_manager = BootConfigManager.get_instance()
        self.component_registry = ComponentRegistry()
        self.dependency_resolver = DependencyResolver()
        
        # Boot status tracking
        self.boot_metrics = {
            "start_time": None,
            "end_time": None,
            "phase_durations": {},
            "component_startup_times": {},
            "errors": []
        }
        
        # Boot phases
        self.phases = [
            "initialization",
            "dependency_verification",
            "service_startup",
            "health_check",
            "stabilization"
        ]
        
        # Phase hooks
        self.phase_hooks = {
            phase: {"pre": [], "post": []} for phase in self.phases
        }
        
        # Event listeners for real-time status updates
        self.event_listeners = []
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        # Shutdown event
        self.shutdown_event = asyncio.Event()
        
        # Boot status
        self.boot_completed = False
        self.boot_successful = False
        
        logger.info("Boot Manager initialized")
    
    def register_event_listener(self, listener):
        """
        Register an event listener function to receive boot events.
        
        The listener should be an async function that accepts two parameters:
        - event: str - The event type (e.g., 'phase_started', 'component_state_changed')
        - data: dict - Additional data about the event
        
        Args:
            listener: Async function to call with events
        """
        if listener not in self.event_listeners:
            self.event_listeners.append(listener)
            logger.debug(f"Event listener registered (total: {len(self.event_listeners)})")

    def unregister_event_listener(self, listener):
        """
        Unregister an event listener function.
        
        Args:
            listener: The listener function to remove
        """
        if listener in self.event_listeners:
            self.event_listeners.remove(listener)
            logger.debug(f"Event listener unregistered (remaining: {len(self.event_listeners)})")

    async def emit_event(self, event_type, data):
        """
        Emit an event to all registered listeners.
        
        Args:
            event_type: Type of event (e.g., 'phase_started')
            data: Additional event data
        """
        for listener in self.event_listeners:
            try:
                await listener(event_type, data)
            except Exception as e:
                logger.error(f"Error in event listener: {str(e)}")
    
    def _setup_signal_handlers(self):
        """Set up handlers for system signals."""
        # Register signal handlers with the event loop
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_event_loop().add_signal_handler(
                    sig, lambda s=sig: asyncio.create_task(self._handle_signal(s))
                )
                logger.debug(f"Registered signal handler for {sig}")
            except NotImplementedError:
                # add_signal_handler is not implemented on Windows
                logger.warning(f"Could not register signal handler for {sig} (not supported on this platform)")
    
    async def _handle_signal(self, signal_received):
        """
        Handle system signals.
        
        Args:
            signal_received: Signal that was received
        """
        logger.info(f"Received signal {signal_received}, initiating shutdown")
        await self.shutdown()
    
    def register_phase_hook(self, phase: str, hook_type: str, hook_func: Callable):
        """
        Register a hook function for a boot phase.
        
        Args:
            phase: Boot phase name
            hook_type: 'pre' or 'post'
            hook_func: Hook function to call
            
        Raises:
            ValueError: If phase or hook type is invalid
        """
        if phase not in self.phases:
            raise ValueError(f"Invalid boot phase: {phase}")
        
        if hook_type not in ["pre", "post"]:
            raise ValueError(f"Invalid hook type: {hook_type}")
        
        self.phase_hooks[phase][hook_type].append(hook_func)
        logger.debug(f"Registered {hook_type} hook for {phase} phase")
    
    async def call_phase_hooks(self, phase: str, hook_type: str):
        """
        Call all hooks for a specific phase and type.
        
        Args:
            phase: Boot phase name
            hook_type: 'pre' or 'post'
        """
        if phase not in self.phases:
            raise ValueError(f"Invalid boot phase: {phase}")
        
        if hook_type not in ["pre", "post"]:
            raise ValueError(f"Invalid hook type: {hook_type}")
        
        for hook in self.phase_hooks[phase][hook_type]:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.error(f"Error in {hook_type} hook for {phase} phase: {str(e)}")
    
    async def register_component(
        self,
        component: Component,
        circuit_breaker: CircuitBreaker = None,
        recovery_policy: RecoveryPolicy = None
    ):
        """
        Register a component with the boot manager.
        
        Args:
            component: Component to register
            circuit_breaker: Optional circuit breaker for the component
            recovery_policy: Optional recovery policy for the component
        """
        # Register with component registry
        await self.component_registry.register_component(
            component, circuit_breaker, recovery_policy
        )
        
        # Add to dependency resolver
        self.dependency_resolver.add_component(component.name, component.dependencies)
    
    async def boot(self) -> bool:
        """
        Start the boot process.
        
        Returns:
            True if boot was successful, False otherwise
        """
        logger.info("Starting boot sequence")
        self.boot_metrics["start_time"] = time.time()
        
        try:
            # Run each phase in sequence
            for phase in self.phases:
                phase_start = time.time()
                logger.info(f"Starting {phase} phase")
                
                # Emit phase started event
                await self.emit_event("phase_started", {"phase": phase})
                
                # Call pre-phase hooks
                await self.call_phase_hooks(phase, "pre")
                
                # Run the phase
                phase_method = getattr(self, f"_phase_{phase}")
                if not await phase_method():
                    logger.error(f"{phase} phase failed")
                    self.boot_metrics["errors"].append({
                        "phase": phase,
                        "message": f"{phase} phase failed",
                        "time": time.time()
                    })
                    
                    # Emit phase failed event
                    await self.emit_event("phase_failed", {"phase": phase})
                    
                    await self.shutdown()
                    return False
                
                # Call post-phase hooks
                await self.call_phase_hooks(phase, "post")
                
                # Record phase duration
                phase_end = time.time()
                self.boot_metrics["phase_durations"][phase] = phase_end - phase_start
                logger.info(f"Completed {phase} phase in {phase_end - phase_start:.2f}s")
                
                # Emit phase completed event
                await self.emit_event("phase_completed", {"phase": phase})
            
            # Boot successful
            self.boot_completed = True
            self.boot_successful = True
            self.boot_metrics["end_time"] = time.time()
            total_time = self.boot_metrics["end_time"] - self.boot_metrics["start_time"]
            logger.info(f"Boot sequence completed successfully in {total_time:.2f}s")
            
            # Emit boot completed event
            await self.emit_event("boot_completed", {"success": True, "boot_time": total_time})
            
            return True
            
        except Exception as e:
            logger.error(f"Boot sequence failed: {str(e)}")
            logger.debug(f"Stack trace: {traceback.format_exc()}")
            
            self.boot_metrics["errors"].append({
                "phase": phase if 'phase' in locals() else "unknown",
                "message": str(e),
                "stack_trace": traceback.format_exc(),
                "time": time.time()
            })
            
            # Emit boot failed event
            await self.emit_event("boot_failed", {"error": str(e)})
            
            await self.shutdown()
            return False
    
    async def shutdown(self):
        """Shut down all components in reverse dependency order."""
        logger.info("Initiating shutdown sequence")
        
        # Set shutdown event
        self.shutdown_event.set()
        
        # Get all components in dependency order
        components = await self.component_registry.get_all_components()
        
        # Sort by startup order (descending, so that dependents are shut down first)
        sorted_components = sorted(
            components.items(),
            key=lambda x: x[1].startup_order if hasattr(x[1], "startup_order") else 0,
            reverse=True
        )
        
        for name, component in sorted_components:
            logger.info(f"Shutting down component: {name}")
            
            try:
                # Call pre-stop hooks
                await self.component_registry.call_hooks(name, "pre_stop")
                
                # Update state
                await self.component_registry.update_component_state(
                    name, ComponentState.STOPPING
                )
                
                # Stop the component
                await component.stop()
                
                # Clean up resources
                await component.cleanup()
                
                # Update state
                await self.component_registry.update_component_state(
                    name, ComponentState.STOPPED
                )
                
                # Call post-stop hooks
                await self.component_registry.call_hooks(name, "post_stop")
                
                logger.info(f"Component {name} stopped successfully")
                
            except Exception as e:
                logger.error(f"Error shutting down component {name}: {str(e)}")
        
        logger.info("Shutdown sequence completed")
    
    async def _phase_initialization(self) -> bool:
        """
        Run the initialization phase of the boot process.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        logger.info("Initializing boot environment")
        
        try:
            # Ensure configuration is loaded
            self.boot_config_manager.refresh_config()
            
            # Validate boot configuration
            is_valid, issues = self.boot_config_manager.validate_boot_readiness()
            if not is_valid:
                for issue in issues:
                    logger.error(f"Boot configuration issue: {issue}")
                return False
            
            # Log boot configuration
            self.boot_config_manager.log_boot_configuration()
            
            # Create necessary directories
            await self._ensure_directories()
            
            return True
            
        except Exception as e:
            logger.error(f"Initialization phase failed: {str(e)}")
            return False
    
    async def _ensure_directories(self) -> bool:
        """
        Ensure that necessary directories exist.
        
        Returns:
            True if all directories were created/verified, False otherwise
        """
        required_dirs = self.boot_config_manager.boot_config.required_directories
        
        for dir_path in required_dirs:
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.debug(f"Ensured directory exists: {dir_path}")
            except Exception as e:
                logger.error(f"Failed to create directory {dir_path}: {str(e)}")
                return False
        
        return True
    
    async def _phase_dependency_verification(self) -> bool:
        """
        Verify that all required dependencies are available.
        
        Returns:
            True if all dependencies are available, False otherwise
        """
        logger.info("Verifying external dependencies")
        
        # Run dependency checks
        dependency_results = await self.boot_config_manager.check_service_dependencies()
        
        # Check if all critical services are available
        for service_name, is_available in dependency_results.items():
            service_config = self.boot_config_manager.boot_config.services.get(service_name, None)
            
            if not service_config:
                logger.warning(f"Service {service_name} not found in configuration")
                continue
            
            if not is_available and service_config.critical and not self.boot_config_manager.boot_config.force_boot:
                logger.error(f"Critical service {service_name} is not available")
                return False
        
        return True
    
    async def _phase_service_startup(self) -> bool:
        """
        Service startup phase.
        
        This phase starts all services in dependency order.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Starting service startup phase")
        
        try:
            # Get the resolved dependency order
            component_order = self.dependency_resolver.topological_sort()
            
            # Filter out disabled components if configured in boot_config
            if hasattr(self.boot_config_manager.boot_config, "services"):
                enabled_components = []
                for comp in component_order:
                    service_config = self.boot_config_manager.boot_config.services.get(comp)
                    if service_config and hasattr(service_config, "enabled"):
                        if service_config.enabled:
                            enabled_components.append(comp)
                    else:
                        # No specific config, assume enabled
                        enabled_components.append(comp)
                
                component_order = enabled_components
            
            logger.info(f"Starting {len(component_order)} components in dependency order")
            
            for component_name in component_order:
                logger.info(f"Starting component: {component_name}")
                
                try:
                    # Update component state to starting
                    await self.component_registry.update_component_state(
                        component_name, ComponentState.STARTING
                    )
                    
                    # Emit component state changed event
                    await self.emit_event("component_state_changed", {
                        "component": component_name,
                        "state": ComponentState.STARTING
                    })
                    
                    # Get the component
                    component = await self.component_registry.get_component(component_name)
                    
                    # Call hooks before starting
                    await self.component_registry.call_hooks(component_name, "pre_start")
                    
                    # Start the component with circuit breaker if configured
                    entry = await self.component_registry.get_entry(component_name)
                    
                    if entry.circuit_breaker:
                        # Use circuit breaker pattern
                        try:
                            start_success = await entry.circuit_breaker.execute(component.start)
                        except CircuitOpenError:
                            logger.error(f"Circuit breaker open for {component_name}")
                            start_success = False
                    else:
                        # Start directly
                        start_success = await component.start()
                    
                    if start_success:
                        # Update state to running
                        await self.component_registry.update_component_state(
                            component_name, ComponentState.RUNNING
                        )
                        
                        # Emit component state changed event
                        await self.emit_event("component_state_changed", {
                            "component": component_name,
                            "state": ComponentState.RUNNING
                        })
                        
                        # Call hooks after starting
                        await self.component_registry.call_hooks(component_name, "post_start")
                        
                        logger.info(f"Successfully started component: {component_name}")
                    else:
                        # Component failed to start
                        logger.error(f"Failed to start component: {component_name}")
                        await self.component_registry.update_component_state(
                            component_name, ComponentState.FAILED
                        )
                        
                        # Emit component state changed event
                        await self.emit_event("component_state_changed", {
                            "component": component_name,
                            "state": ComponentState.FAILED,
                            "error": "Component failed to start"
                        })
                        
                        # If this is a critical component, we should abort
                        service_config = self.boot_config_manager.boot_config.services.get(component_name)
                        if service_config and getattr(service_config, "critical", True):
                            logger.error(f"Critical component {component_name} failed to start")
                            return False
                
                except Exception as e:
                    logger.error(f"Error starting component {component_name}: {str(e)}")
                    await self.component_registry.update_component_state(
                        component_name, ComponentState.FAILED
                    )
                    
                    # Emit component state changed event with error
                    await self.emit_event("component_state_changed", {
                        "component": component_name,
                        "state": ComponentState.FAILED,
                        "error": str(e)
                    })
                    
                    # Check if this is a critical component
                    service_config = self.boot_config_manager.boot_config.services.get(component_name)
                    if service_config and getattr(service_config, "critical", True):
                        logger.error(f"Critical component {component_name} failed with exception")
                        return False
            
            # All services started (or non-critical failures handled)
            return True
            
        except Exception as e:
            logger.error(f"Service startup phase failed: {str(e)}")
            return False
    
    async def _phase_health_check(self) -> bool:
        """
        Verify that all services are healthy after startup.
        
        Returns:
            True if all services are healthy, False otherwise
        """
        logger.info("Performing health checks")
        
        # Get all components
        components = await self.component_registry.get_all_components()
        
        # Check health of each component
        for name, component in components.items():
            service_config = self.boot_config_manager.boot_config.services.get(name, None)
            
            if not service_config:
                logger.warning(f"Service {name} not found in configuration")
                continue
            
            if not service_config.enabled:
                logger.info(f"Skipping health check for disabled service: {name}")
                continue
            
            logger.info(f"Checking health of service: {name}")
            
            try:
                # Call health check hooks
                await self.component_registry.call_hooks(name, "health_check")
                
                # Check component health
                is_healthy = await component.health_check()
                
                if not is_healthy:
                    logger.warning(f"Service {name} health check failed")
                    
                    if service_config.critical:
                        logger.error(f"Critical service {name} failed health check")
                        return False
                else:
                    logger.info(f"Service {name} health check passed")
                
            except Exception as e:
                logger.error(f"Error during health check for {name}: {str(e)}")
                
                if service_config.critical:
                    return False
        
        return True
    
    async def _phase_stabilization(self) -> bool:
        """
        Allow the system to stabilize after startup.
        
        Returns:
            True if stabilization was successful, False otherwise
        """
        logger.info("Allowing system to stabilize")
        
        # Wait for stabilization period
        stabilization_time = self.boot_config_manager.boot_config.stabilization_time
        if stabilization_time > 0:
            logger.info(f"Waiting {stabilization_time}s for system stabilization")
            await asyncio.sleep(stabilization_time)
        
        return True

# Update the existing BootSequence to use the BootManager
class BootSequence:
    """
    Boot sequence for the trading environment.
    
    This class handles the deterministic startup sequence for the trading
    environment, ensuring components start in the correct order and all
    dependencies are available.
    
    Note: This class is maintained for backward compatibility.
    For new code, use BootManager instead.
    """
    
    def __init__(self, config_path: str):
        """
        Initialize the boot sequence.
        
        Args:
            config_path: Path to the configuration file
        """
        # Create boot manager
        self.boot_manager = BootManager.get_instance(config_path)
        
        # For backward compatibility
        self.config_path = config_path
        self.config = self._load_config()
        self.dependency_checker = None
        self.services = {}
        
        # Original boot stages (provided for compatibility)
        self.boot_stages = [
            self._verify_dependencies,
            self._initialize_services,
            self._start_orchestrator,
            self._start_agents
        ]
    
    def _load_config(self) -> dict:
        """
        Load the configuration file (backward compatibility method).
        
        Returns:
            Configuration dictionary
        """
        logger.info(f"Loading configuration from {self.config_path}")
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info("Configuration loaded successfully")
            return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in configuration file: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    async def _verify_dependencies(self) -> bool:
        """
        Verify that all dependencies are available.
        
        Returns:
            True if all dependencies are available, False otherwise
        """
        return await self.boot_manager._phase_dependency_verification()
    
    async def _initialize_services(self) -> bool:
        """
        Initialize required services.
        
        Returns:
            True if all services were initialized successfully, False otherwise
        """
        return await self.boot_manager._phase_initialization()
    
    async def _start_orchestrator(self) -> bool:
        """
        Start the agent orchestrator.
        
        Returns:
            True if the orchestrator was started successfully, False otherwise
        """
        # This functionality is now handled by the BootManager's service startup
        # For backward compatibility, we treat the orchestrator as a service
        logger.info("Starting agent orchestrator...")
        
        # Get the orchestrator service from configuration
        orchestrator_service = self.boot_manager.boot_config_manager.boot_config.services.get("orchestrator", None)
        
        if not orchestrator_service or not orchestrator_service.enabled:
            logger.warning("Orchestrator service not configured or disabled")
            return True  # Not fatal if not configured
        
        # Check if the orchestrator component exists in registry
        try:
            orchestrator = await self.boot_manager.component_registry.get_component("orchestrator")
            # Already started during service startup phase
            logger.info("Orchestrator is running")
            return True
        except ValueError:
            logger.warning("Orchestrator component not found in registry")
            # Create a placeholder entry for backward compatibility
            self.services["orchestrator"] = {"started": True}
            return True
    
    async def _start_agents(self) -> bool:
        """
        Start the trading agents.
        
        Returns:
            True if the agents were started successfully, False otherwise
        """
        # This functionality is now handled by the BootManager's service startup
        # For backward compatibility, we treat agents as services
        logger.info("Starting trading agents...")
        
        # Check if there are any agent services configured
        agent_services = {
            name: service for name, service in 
            self.boot_manager.boot_config_manager.boot_config.services.items()
            if name.startswith("agent_") and service.enabled
        }
        
        if not agent_services:
            logger.warning("No agent services configured or all disabled")
            # Create a placeholder entry for backward compatibility
            self.services["agents"] = {"started": True}
            return True
        
        # Check if all agent components exist in registry and are running
        all_running = True
        for name in agent_services:
            try:
                agent = await self.boot_manager.component_registry.get_component(name)
                state = await self.boot_manager.component_registry.get_component_state(name)
                if state != ComponentState.RUNNING:
                    logger.warning(f"Agent {name} is not running (state: {state.name})")
                    all_running = False
            except ValueError:
                logger.warning(f"Agent {name} not found in registry")
                all_running = False
        
        # For backward compatibility
        self.services["agents"] = {"started": all_running}
        return True
    
    async def boot(self) -> bool:
        """
        Start the boot process.
        
        Returns:
            True if boot was successful, False otherwise
        """
        logger.info("Starting boot sequence (legacy method)")
        
        # Use the BootManager's boot method for actual implementation
        return await self.boot_manager.boot()
        
        """
        # The code below is kept for reference, but not executed
        for stage in self.boot_stages:
            if not await stage():
                logger.error(f"Boot stage {stage.__name__} failed")
                return False
        
        logger.info("Boot sequence completed successfully")
        return True
        """


async def boot(config_path: str = None) -> bool:
    """
    Main boot function to start the system.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        True if boot was successful, False otherwise
    """
    # Create and initialize the boot manager
    boot_manager = BootManager.get_instance(config_path)
    
    # Register concrete components based on configuration
    await _register_components(boot_manager)
    
    # Start the boot process
    return await boot_manager.boot()


async def _register_components(boot_manager: BootManager):
    """
    Register components with the boot manager based on configuration.
    
    Args:
        boot_manager: Boot manager instance
    """
    boot_config = boot_manager.boot_config_manager.boot_config
    
    # Register available service components based on configuration
    for service_name, service_config in boot_config.services.items():
        if not service_config.enabled:
            logger.info(f"Skipping disabled service: {service_name}")
            continue
        
        # Create and register appropriate component based on service type
        if service_name == "redis":
            # Create Redis component
            component = RedisComponent(service_name, service_config)
            await boot_manager.register_component(
                component,
                recovery_policy=RecoveryPolicy(
                    max_retries=3,
                    backoff_factor=2.0,
                    retry_interval=1.0
                )
            )
        elif service_name == "postgres":
            # Create Postgres component (implementation left as exercise)
            logger.info(f"Postgres component would be created here for {service_name}")
        elif service_name == "orchestrator":
            # Create Orchestrator component (implementation left as exercise)
            logger.info(f"Orchestrator component would be created here for {service_name}")
        elif service_name.startswith("agent_"):
            # Create Agent component (implementation left as exercise)
            logger.info(f"Agent component would be created here for {service_name}")
        else:
            logger.warning(f"No component implementation available for service: {service_name}")


# Example concrete component implementation
class RedisComponent(Component):
    """Redis component implementation."""
    
    def __init__(self, name: str, config: dict):
        """
        Initialize the Redis component.
        
        Args:
            name: Component name
            config: Redis configuration
        """
        super().__init__(name, dependencies=config.get("dependencies", []))
        self.config = config
        self.client = None
    
    async def initialize(self) -> bool:
        """Initialize Redis client."""
        try:
            import redis
            
            self.client = redis.Redis(
                host=self.config.get("host", "localhost"),
                port=self.config.get("port", 6379),
                db=self.config.get("db", 0),
                password=self.config.get("password"),
                decode_responses=self.config.get("decode_responses", True)
            )
            
            return True
        except ImportError:
            logger.error("Redis package not installed. Run 'pip install redis'")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {str(e)}")
            return False
    
    async def start(self) -> bool:
        """Start the Redis component."""
        try:
            # Test connection
            self.client.ping()
            logger.info(f"Redis connection established: {self.config.get('host', 'localhost')}:{self.config.get('port', 6379)}")
            return True
        except Exception as e:
            logger.error(f"Failed to start Redis client: {str(e)}")
            return False
    
    async def stop(self) -> bool:
        """Stop the Redis component."""
        if self.client:
            try:
                self.client.close()
                logger.info("Redis connection closed")
                return True
            except Exception as e:
                logger.error(f"Error closing Redis connection: {str(e)}")
                return False
        return True
    
    async def health_check(self) -> bool:
        """Check if Redis is responsive."""
        if self.client:
            try:
                return self.client.ping()
            except Exception as e:
                logger.error(f"Redis health check failed: {str(e)}")
                return False
        return False
    
    async def cleanup(self) -> bool:
        """Clean up Redis resources."""
        # Already handled in stop()
        return True


def main():
    """Command line entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Boot the trading system")
    parser.add_argument(
        "--config", "-c",
        help="Path to configuration file",
        default=None
    )
    args = parser.parse_args()
    
    # Run the boot process
    success = asyncio.run(boot(args.config))
    
    # Exit with appropriate status
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 