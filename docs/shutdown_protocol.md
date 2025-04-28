# Agent Shutdown Protocol

## Overview

The Agent Shutdown Protocol provides a systematic three-phase approach to gracefully terminate trading agents. This document explains how the protocol works and how to implement it correctly in your agent classes.

## Three-Phase Shutdown

The shutdown protocol consists of three sequential phases:

1. **Preparation Phase**: Agents prepare for shutdown by finishing critical operations, flushing data to storage, and saving state.
2. **Stop Phase**: Agents stop processing new data and decisions, canceling any pending non-critical operations.
3. **Cleanup Phase**: Agents clean up resources, close connections, and perform final termination tasks.

## Key Components

### AgentShutdownRegistry

Tracks the status of each agent throughout the shutdown process:

- Registers agents with their dependencies and priorities
- Monitors phase transitions
- Provides progress information

### AgentShutdownProtocol

Implements the actual shutdown process:

- Manages timeouts for each phase
- Executes the three phases in sequence for each agent
- Respects dependencies and priorities

### ShutdownCoordinator

High-level interface for shutdown management:

- Initializes the shutdown with custom settings
- Manages progress reporting and callbacks
- Provides emergency shutdown capabilities

## How to Implement

### 1. Extend BaseAgentCore or Implement Shutdown Methods

All agent classes should either extend `BaseAgentCore` or implement the three shutdown protocol methods:

```python
async def prepare_shutdown(self) -> None:
    # Finish critical operations
    # Flush data to storage
    # Save state

async def stop(self) -> bool:
    # Stop processing new data
    # Cancel pending operations
    # Return True if stopped successfully

async def cleanup(self) -> None:
    # Release resources
    # Close connections
    # Terminate background tasks
```

### 2. Register with Shutdown Coordinator

Agents need to register with the shutdown coordinator during initialization:

```python
def __init__(self, agent_id: str, agent_type: str):
    # ... other initialization code
    self._register_with_shutdown_coordinator()

def _register_with_shutdown_coordinator(self) -> None:
    try:
        coordinator = get_shutdown_coordinator()
        coordinator.register_agent(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            agent_instance=self,
            shutdown_priority=self._get_shutdown_priority(),
            dependencies=self._get_shutdown_dependencies()
        )
    except Exception as e:
        logger.error(f"Failed to register with shutdown coordinator: {str(e)}")
```

### 3. Define Dependencies and Priorities

Customize shutdown behavior by defining dependencies and priorities:

```python
def _get_shutdown_priority(self) -> int:
    """Higher values are processed first."""
    return 50  # Medium priority

def _get_shutdown_dependencies(self) -> List[str]:
    """List agent IDs this agent depends on."""
    return ["other_agent_id"]  # This agent will shut down after other_agent_id
```

### 4. Implement Phase-Specific Logic

Add logic specific to your agent type for each phase:

#### Preparation Phase

```python
async def prepare_shutdown(self) -> None:
    await super().prepare_shutdown()  # Always call the parent method
    
    # Agent-specific preparation
    await self._save_current_state()
    await self._finish_critical_operations()
```

#### Stop Phase

```python
async def stop(self) -> bool:
    if not self._is_running:
        return True
    
    self.state = AgentState.STOPPING
    
    # Cancel background tasks
    for task in self._background_tasks:
        if not task.done():
            task.cancel()
    
    # Wait for tasks to complete
    await asyncio.gather(*self._background_tasks, return_exceptions=True)
    
    self.state = AgentState.STOPPED
    return True
```

#### Cleanup Phase

```python
async def cleanup(self) -> None:
    # Release resources
    for resource in self._resources:
        await resource.close()
    
    self._resources = []
    
    # Call parent cleanup
    await super().cleanup()
```

## Shutdown Timeouts

Each phase has configurable timeouts:

- Default timeouts: Preparation (10s), Stop (10s), Cleanup (5s)
- Custom timeouts can be set through the coordinator

```python
coordinator = get_shutdown_coordinator()
coordinator.initialize_shutdown(
    reason="Normal shutdown",
    preparation_timeout=15.0,  # 15 seconds
    stop_timeout=8.0,         # 8 seconds
    cleanup_timeout=3.0       # 3 seconds
)
```

## Emergency Shutdown

For critical situations, use emergency shutdown with minimal timeouts:

```python
await coordinator.emergency_shutdown(reason="Critical error detected")
```

## Initiating Shutdown

### For All Agents

```python
coordinator = get_shutdown_coordinator()
coordinator.initialize_shutdown(reason="End of trading day")
await coordinator.shutdown_all_agents(force=False)
```

### For a Specific Agent

```python
await coordinator.shutdown_agent("agent_id", force=False)
```

## Best Practices

1. **Register Early**: Register agents with the coordinator during initialization.
2. **Check Shutdown Flag**: Regularly check `self._is_shutting_down` to avoid starting new operations during shutdown.
3. **Cancel Tasks Properly**: Always handle `asyncio.CancelledError` in background tasks.
4. **Respect Dependencies**: Define dependencies correctly to ensure proper shutdown order.
5. **Timeout Management**: Implement phases to complete within expected timeouts.
6. **Error Handling**: Catch and log exceptions in shutdown methods to prevent one agent from blocking others.
7. **Signal Handlers**: Set up signal handlers to initiate graceful shutdown on SIGINT/SIGTERM.

## Monitoring Shutdown Progress

Get detailed progress information:

```python
progress = coordinator.get_shutdown_progress()
print(f"Completion: {progress['percent_complete']}%")
print(f"Status by phase: {progress['phases']}")
```

Register callbacks for shutdown events:

```python
coordinator.register_progress_callback(on_progress_update)
coordinator.register_completion_callback(on_shutdown_complete)
```

## Example Implementation

See `src/agents/shutdown_integration_example.py` for a complete example of agent implementations that correctly implement the shutdown protocol. 