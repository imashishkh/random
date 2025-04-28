# Graceful Shutdown Documentation

## Overview

The Forex Trading Bot includes a robust and configurable shutdown system designed to ensure safe termination of operations. The graceful shutdown subsystem handles:

1. Closing open trading positions
2. Stopping trading agents in the correct order 
3. Cleaning up system resources
4. Providing progress status during shutdown

This document outlines the shutdown architecture, usage patterns, and configuration options.

## Architecture

The shutdown system is composed of four main components:

### 1. Shutdown Coordinator

The `ShutdownCoordinator` is the central controller of the shutdown process. It:

- Manages the shutdown sequence
- Coordinates between components
- Tracks shutdown progress
- Provides status reporting

The coordinator is implemented as a singleton accessible via `get_shutdown_coordinator()`.

### 2. Position Closer

The `PositionCloser` is responsible for:

- Fetching current open positions
- Closing positions during shutdown
- Supporting different close strategies (immediate or gradual)
- Handling errors during position closure

Position closer is accessed via `get_position_closer(risk_manager)`.

### 3. Agent Terminator

The `AgentTerminator` manages:

- Preparing agents for shutdown
- Stopping agents in the correct dependency order
- Cleaning up agent resources
- Handling agent failures

Agent terminator is accessed via `get_agent_terminator(orchestrator)`.

### 4. Resource Cleaner

The `ResourceCleaner` handles:

- Registration of resource cleanup callbacks
- Organization of cleanup by resource type
- Executing cleanup callbacks in the correct order
- Managing dependencies between resources

Resource cleaner is accessed via `get_resource_cleaner()`.

## Shutdown Process

The shutdown process occurs in distinct phases:

1. **Initialization**: Signal handlers set up, shutdown reason recorded
2. **Position Closing**: All trading positions are closed using the selected strategy
3. **Agent Preparation**: Agents notified of imminent shutdown
4. **Agent Stopping**: Agents halted in the correct order
5. **Resource Cleanup**: System resources released
6. **Completion**: Final status reported

## Usage Examples

### Basic Usage

```python
from src.core.shutdown import get_shutdown_coordinator, PositionCloseStrategy

# Get the shutdown coordinator
coordinator = get_shutdown_coordinator()

# Initiate a shutdown
await coordinator.initiate_shutdown(
    reason="Manual shutdown requested",
    position_strategy=PositionCloseStrategy.IMMEDIATE
)

# Execute the shutdown process
result = await coordinator.shutdown_all_agents()

if result:
    print("Shutdown completed successfully")
else:
    print("Shutdown failed or was cancelled")
```

### Registering Cleanup Callbacks

```python
from src.core.resource_cleaner import register_cleanup_callback

# Register a database connection for cleanup
async def cleanup_database_connection():
    await db_connection.close()
    
register_cleanup_callback(
    resource_type="database",
    resource_key="main_db",
    callback=cleanup_database_connection
)

# Register a log file for cleanup
async def close_log_file():
    log_file.flush()
    log_file.close()
    
register_cleanup_callback(
    resource_type="file",
    resource_key="system_log",
    callback=close_log_file
)
```

### Setting Up Signal Handlers

```python
from src.core.shutdown import get_shutdown_coordinator, setup_signal_handlers

# Get the coordinator
coordinator = get_shutdown_coordinator()

# Set up signal handlers (SIGINT, SIGTERM)
setup_signal_handlers(coordinator)
```

### Monitoring Shutdown Progress

```python
from src.core.shutdown import get_shutdown_coordinator

coordinator = get_shutdown_coordinator()

# Get current shutdown status
status = coordinator.get_status()
print(f"Shutdown phase: {status['phase']}")
print(f"Reason: {status['reason']}")
print(f"Progress: {status['progress']}%")

# Register progress callback
def on_progress_update(phase, progress, message):
    print(f"Phase: {phase}, Progress: {progress}%, Message: {message}")
    
coordinator.register_progress_callback(on_progress_update)
```

## Configuration Options

### Position Close Strategies

The `PositionCloseStrategy` enum defines how positions are closed during shutdown:

* `IMMEDIATE`: Close all positions as quickly as possible using emergency shutdown (default)
* `GRADUAL`: Attempt to close positions in a controlled manner, less aggressive
* `NONE`: Skip position closing entirely (use with caution)

```python
from src.core.shutdown import get_shutdown_coordinator, PositionCloseStrategy

coordinator = get_shutdown_coordinator()
await coordinator.initiate_shutdown(
    reason="Market volatility",
    position_strategy=PositionCloseStrategy.GRADUAL
)
```

### Timeout Configuration

Various timeout parameters can be configured:

```python
from src.core.shutdown import get_shutdown_coordinator

coordinator = get_shutdown_coordinator()

# Configure timeouts in seconds
coordinator.position_close_timeout = 30.0  # Position closing timeout
coordinator.agent_prepare_timeout = 10.0   # Agent preparation timeout
coordinator.agent_stop_timeout = 20.0      # Agent stopping timeout
coordinator.resource_cleanup_timeout = 15.0  # Resource cleanup timeout
```

### Emergency Shutdown Mode

For critical scenarios requiring immediate termination:

```python
from src.core.shutdown import get_shutdown_coordinator

coordinator = get_shutdown_coordinator()

# Initiate emergency shutdown (skips some phases)
await coordinator.emergency_shutdown(reason="Critical error detected")
```

## Best Practices

1. **Register Signal Handlers Early**: Call `setup_signal_handlers()` during application startup to ensure SIGINT and SIGTERM are properly handled.

2. **Register Cleanup Callbacks**: Register all resource cleanup callbacks when resources are created, not at shutdown time.

3. **Handle Agent Dependencies**: When agents depend on each other, use agent priorities to ensure they are shut down in the correct order.

4. **Monitor Shutdown Progress**: Register a progress callback to track and log the shutdown process.

5. **Configure Appropriate Timeouts**: Set reasonable timeouts based on system scale and resource closure requirements.

6. **Test Shutdown Regularly**: Include shutdown testing in your regular test cycle to ensure it works reliably.

## Handling Specific Scenarios

### Handling Network Failures During Shutdown

The shutdown system is designed to be resilient to network failures, but you can enhance behavior:

```python
# Custom position closer with fallback strategy
class EnhancedPositionCloser(PositionCloser):
    async def close_positions(self):
        try:
            return await super().close_positions()
        except NetworkError:
            logger.warning("Network error during position closing, using local fallback")
            # Implement fallback strategy
```

### Managing Database Connections

```python
# Register database connections with dependencies
async def cleanup_read_replica():
    await read_replica.close()
    
async def cleanup_write_master():
    await write_master.close()

# Register with resource cleaner, noting the dependency
register_cleanup_callback("database", "read_replica", cleanup_read_replica)
register_cleanup_callback("database", "write_master", cleanup_write_master, 
                         depends_on=["database.read_replica"])
```

### Graceful Agent Shutdown Workflow

Implement agent methods correctly:

```python
class MyTradingAgent:
    async def prepare_shutdown(self):
        """Prepare for shutdown, finish critical work"""
        self.accepting_new_trades = False
        await self.finish_pending_analysis()
        
    async def stop(self):
        """Stop agent activities"""
        await self.cancel_pending_orders()
        self.trading_thread.stop()
        return True
        
    async def cleanup(self):
        """Release resources"""
        await self.close_market_data_feed()
        await self.disconnect_exchange_api()
```

## Troubleshooting

### Common Issues

1. **Shutdown Hangs**: Usually caused by:
   - Agent stop method not returning or raising an exception
   - Unhandled exceptions in cleanup callbacks
   - Missing timeout configuration

2. **Positions Not Closing**: Check:
   - Risk manager configuration
   - Network connectivity to exchange
   - Proper API key permissions

3. **Resource Leaks**: Ensure:
   - All resources have registered cleanup callbacks
   - Cleanup callbacks properly await async operations
   - No circular dependencies in resource cleanup

### Debugging Tools

The shutdown system includes several debugging facilities:

```python
# Enable debug logging
import logging
logging.getLogger("shutdown").setLevel(logging.DEBUG)

# Get detailed shutdown status
status = coordinator.get_status(detailed=True)
print(status)

# Traceback of hanging shutdown (if available)
print(coordinator.get_last_error())
```

## Performance Considerations

1. **Position Closing**: The most time-consuming part of shutdown; consider:
   - Using `IMMEDIATE` strategy for critical shutdowns
   - Setting appropriate timeouts

2. **Resource Cleanup Order**: Organize for efficiency:
   - Close less critical resources first
   - Use dependencies to establish proper sequence

3. **Large-Scale Systems**: For systems with many agents:
   - Consider parallel agent shutdown when safe
   - Prioritize critical agents

## API Reference

See the API documentation for complete method signatures and parameters:

- [ShutdownCoordinator API](./api/shutdown_coordinator.md)
- [PositionCloser API](./api/position_closer.md)
- [AgentTerminator API](./api/agent_terminator.md)
- [ResourceCleaner API](./api/resource_cleaner.md) 