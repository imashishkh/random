# Shutdown Module

The Shutdown Module provides a robust, configurable system for gracefully terminating the Forex Trading Bot. This module ensures that all resources are properly cleaned up, open positions are handled according to strategy, and agents are terminated in the correct order.

## Table of Contents

- [Overview](#overview)
- [Components](#components)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Advanced Usage](#advanced-usage)
- [Testing](#testing)
- [Extending](#extending)

## Overview

The Shutdown Module is designed to handle the orderly shutdown of the Forex Trading Bot while ensuring that:

- Open trading positions are properly closed according to configured strategies
- Trading agents are terminated in the correct dependency order
- All system resources are cleaned up to prevent leaks
- The system can recover from unexpected shutdowns
- Progress can be monitored throughout the shutdown process

## Components

The module consists of four main components:

1. **Shutdown Coordinator**: Orchestrates the entire shutdown process
2. **Position Closer**: Manages the closing of open trading positions
3. **Agent Terminator**: Controls the orderly shutdown of trading agents
4. **Resource Cleaner**: Handles resource cleanup in dependency order

## Quick Start

### Basic Usage

```python
from src.core.shutdown import get_shutdown_coordinator, PositionCloseStrategy

# Initiate a graceful shutdown
coordinator = get_shutdown_coordinator()
await coordinator.shutdown(
    reason="User requested shutdown",
    position_strategy=PositionCloseStrategy.GRADUAL
)

# Check if shutdown is complete
status = coordinator.get_status()
is_complete = status['phase'] == 'COMPLETE'
```

### Signal Handler Integration

```python
import signal
from src.core.shutdown import get_shutdown_coordinator, setup_signal_handlers

# Setup signal handlers for graceful shutdown
setup_signal_handlers()

# Alternatively, create your own handler
def custom_signal_handler(signum, frame):
    coordinator = get_shutdown_coordinator()
    coordinator.initiate_shutdown(reason=f"Received signal {signum}")

signal.signal(signal.SIGTERM, custom_signal_handler)
```

### Resource Registration

```python
from src.core.shutdown import get_resource_cleaner

# Register a resource for cleanup
async def cleanup_database_connection():
    await db_connection.close()

get_resource_cleaner().register_cleanup_callback(
    "database_connection",
    cleanup_database_connection,
    dependencies=["cache_manager"]  # This will clean up after cache_manager
)
```

## Architecture

The Shutdown Module follows a phase-based architecture:

1. **Initialization Phase**: Begins the shutdown process and performs initial checks
2. **Preparation Phase**: Sets up systems for the upcoming phases
3. **Position Closing Phase**: Closes open trading positions according to the selected strategy
4. **Agent Termination Phase**: Stops all trading agents in the correct dependency order
5. **Resource Cleanup Phase**: Releases all registered resources
6. **Completion Phase**: Finalizes the shutdown and reports status

The process is designed to be fault-tolerant, with ability to force completion if any phase fails.

## Configuration

### Position Close Strategies

- `PositionCloseStrategy.IMMEDIATE`: Close positions as quickly as possible with market orders
- `PositionCloseStrategy.GRADUAL`: Attempt to close positions with limit orders first
- `PositionCloseStrategy.NONE`: Don't close positions (for testing or manual handling)

### Timeout Configuration

```python
coordinator = get_shutdown_coordinator()

# Configure timeout for position closing
coordinator.set_position_close_timeout(120.0)  # 120 seconds

# Configure timeout for agent termination
coordinator.set_agent_termination_timeout(30.0)  # 30 seconds

# Configure timeout for resource cleanup
coordinator.set_resource_cleanup_timeout(60.0)  # 60 seconds
```

### Progress Monitoring

```python
def progress_callback(status):
    phase = status['phase']
    elapsed = status['elapsed_time']
    print(f"Shutdown in phase {phase} ({elapsed:.2f}s elapsed)")

# Register the callback
coordinator = get_shutdown_coordinator()
coordinator.register_progress_callback(progress_callback)
```

## Advanced Usage

### Emergency Shutdown

```python
# When system integrity is at risk and you need to shut down immediately
coordinator = get_shutdown_coordinator()
await coordinator.emergency_shutdown(
    reason="Critical system error detected",
    max_wait_time=5.0  # Only wait 5 seconds maximum
)
```

### Customizing Agent Shutdown Order

```python
from src.core.shutdown import get_agent_terminator

terminator = get_agent_terminator()

# Set agent shutdown priority (higher numbers go first)
terminator.set_agent_priority("risk_manager", 100)
terminator.set_agent_priority("data_collector", 10)

# Add agent dependency (strategy agent will shut down before order_manager)
terminator.add_agent_dependency("strategy_agent", "order_manager")
```

### Handling Special Resources

```python
from src.core.shutdown import get_resource_cleaner

cleaner = get_resource_cleaner()

# Register a resource that needs special handling
async def cleanup_sensitive_resource():
    # Perform special cleanup
    try:
        await sensitive_resource.flush_all()
        await sensitive_resource.close()
        return True
    except Exception as e:
        logger.error(f"Error cleaning up sensitive resource: {e}")
        return False

# Register with high priority (cleaned up early)
cleaner.register_cleanup_callback(
    "sensitive_resource",
    cleanup_sensitive_resource,
    priority=100  # Higher priority resources are cleaned up first
)
```

## Testing

The Shutdown Module includes comprehensive test coverage:

- **Unit Tests**: Individual component testing
- **Integration Tests**: Component interaction testing
- **Stress Tests**: Behavior under high load testing
- **Fault Injection Tests**: Handling of failures during shutdown

Run the tests with:

```bash
pytest tests/unit/test_shutdown.py
pytest tests/integration/test_shutdown_integration.py
pytest tests/stress/test_shutdown_stress.py
```

## Extending

### Creating Custom Position Close Strategies

```python
from src.core.shutdown import PositionCloseStrategy, get_position_closer

# Define a custom strategy
class CustomPositionCloseStrategy(PositionCloseStrategy):
    CUSTOM = "custom"

# Implement the strategy handler
async def handle_custom_close_strategy(position, risk_manager):
    # Custom logic for closing positions
    if position.profit > 0:
        # Close profitable positions gradually
        await risk_manager.close_position_limit(position, slippage=0.05)
    else:
        # Close losing positions immediately
        await risk_manager.close_position_market(position)
    return True

# Register the custom strategy
position_closer = get_position_closer(None)
position_closer.register_close_strategy(
    CustomPositionCloseStrategy.CUSTOM,
    handle_custom_close_strategy
)

# Use the custom strategy
coordinator = get_shutdown_coordinator()
await coordinator.shutdown(
    reason="Using custom position close strategy",
    position_strategy=CustomPositionCloseStrategy.CUSTOM
)
```

### Adding Custom Shutdown Phases

For advanced use cases, you can extend the `ShutdownCoordinator` class to include custom phases that handle special requirements for your trading system.

## Further Reading

- [Graceful Shutdown Documentation](../../docs/graceful_shutdown.md)
- [Shutdown Troubleshooting Guide](../../docs/shutdown_troubleshooting.md)
- [API Reference](../../docs/api/shutdown_api.md) 