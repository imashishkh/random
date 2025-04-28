# Graceful Shutdown Troubleshooting Guide

This guide provides solutions for common issues encountered with the Forex Trading Bot's graceful shutdown system.

## Table of Contents

1. [Shutdown Process Overview](#shutdown-process-overview)
2. [Common Issues and Solutions](#common-issues-and-solutions)
3. [Diagnostic Tools](#diagnostic-tools)
4. [Performance Issues](#performance-issues)
5. [Emergency Procedures](#emergency-procedures)

## Shutdown Process Overview

As a refresher, the graceful shutdown process consists of the following phases:

1. **Initialization** (INITIALIZING)
2. **Preparation** (PREPARATION)
3. **Position Closing** (POSITIONS)
4. **Agent Stopping** (AGENTS)
5. **Resource Cleanup** (RESOURCES)
6. **Completion** (COMPLETE or FAILED)

Issues can occur at any phase of this process.

## Common Issues and Solutions

### Shutdown Never Completes

#### Symptoms
- Shutdown process hangs
- No COMPLETE or FAILED status
- Application doesn't terminate

#### Possible Causes and Solutions

1. **Hanging Agent**
   - **Cause**: An agent's `stop()` method isn't returning or is taking too long
   - **Solution**: 
     - Check logs for which agent is hanging
     - Implement timeouts in the agent's `stop()` method
     - Use force shutdown (`force=True`) for immediate termination

2. **Infinite Loop in Cleanup Callback**
   - **Cause**: A resource cleanup callback is stuck in a loop
   - **Solution**:
     - Review all cleanup callbacks for proper termination
     - Add timeouts to long-running cleanup operations
     - Consider using `asyncio.wait_for()` for callback execution

3. **Deadlocked Resources**
   - **Cause**: Resources are waiting for each other in a circular dependency
   - **Solution**:
     - Check resource dependencies for cycles
     - Use `get_resource_cleaner().validate_dependencies()` to find cycles
     - Break circular dependencies or use a different shutdown order

### Positions Not Closing

#### Symptoms
- Shutdown proceeds but positions remain open
- Error logs showing position close failures
- Exchange balances unchanged

#### Possible Causes and Solutions

1. **Exchange API Issues**
   - **Cause**: Exchange API is unavailable or returning errors
   - **Solution**:
     - Check API status and network connectivity
     - Implement retry logic in position closing
     - Add fallback to market orders for position closure

2. **Position Closer Configuration**
   - **Cause**: Incorrect position closing strategy or risk manager
   - **Solution**:
     - Verify position closer is registered with the correct risk manager
     - Try using `PositionCloseStrategy.IMMEDIATE` for more aggressive closure
     - Check risk manager has proper access permissions

3. **Timeout Too Short**
   - **Cause**: Position closing timeout expires before completion
   - **Solution**:
     - Increase the `position_close_timeout` parameter
     - Log position closing progress to identify bottlenecks
     - Consider parallel position closing for large position counts

### Agents Failing to Stop

#### Symptoms
- Shutdown proceeds but agents continue running
- Error logs from agent termination phase
- Resource usage doesn't decrease after shutdown

#### Possible Causes and Solutions

1. **Agent Stop Method Implementation**
   - **Cause**: Agent's `stop()` method is not properly implemented
   - **Solution**:
     - Verify the `stop()` method returns `True` when successful
     - Ensure all background tasks are cancelled
     - Add proper exception handling in the `stop()` method

2. **Dependency Order Issues**
   - **Cause**: Agents are stopping in the wrong order
   - **Solution**:
     - Check agent shutdown priority and dependencies
     - Adjust agent registration to set correct priority
     - Log the actual shutdown order for diagnosis

3. **Unhandled Exceptions in Agent Methods**
   - **Cause**: Exceptions in agent methods cause termination to fail
   - **Solution**:
     - Add try/except blocks in agent methods
     - Improve logging around agent shutdown
     - Return `False` from `stop()` if the method encounters errors

### Resource Leaks After Shutdown

#### Symptoms
- System resources remain allocated after shutdown
- Memory usage doesn't decrease
- Network connections remain open

#### Possible Causes and Solutions

1. **Missing Cleanup Callbacks**
   - **Cause**: Some resources don't have cleanup callbacks registered
   - **Solution**:
     - Audit all resource creation to ensure cleanup registration
     - Add callback registration to resource factory methods
     - Implement a resource tracking system to detect unregistered resources

2. **Cleanup Callbacks Not Executed**
   - **Cause**: Callbacks not called due to earlier phase failures
   - **Solution**:
     - Check shutdown logs for phase completions
     - Use `force=True` to ensure cleanup phase executes
     - Add resource cleanup as a separate process after shutdown

3. **Async Cleanup Not Awaited**
   - **Cause**: Async cleanup callbacks not properly awaited
   - **Solution**:
     - Ensure all async cleanup methods are properly awaited
     - Check for `asyncio.ensure_future()` without waiting
     - Add timeout protection around await operations

## Diagnostic Tools

### Shutdown Status Inspection

Check the current status of shutdown:

```python
coordinator = get_shutdown_coordinator()
status = coordinator.get_status()
print(f"Phase: {status['phase']}")
print(f"Reason: {status['reason']}")
print(f"Force mode: {status['force']}")
print(f"Position strategy: {status['position_strategy']}")
print(f"Elapsed time: {status['elapsed_time']} seconds")

# Get detailed phase results
if 'phase_results' in status:
    for phase, result in status['phase_results'].items():
        print(f"Phase {phase}: {'Success' if result['success'] else 'Failed'}")
        if 'error' in result:
            print(f"  Error: {result['error']}")
```

### Enhanced Logging

Configure more detailed shutdown logging:

```python
import logging

# Configure shutdown module logging
logging.getLogger('src.core.shutdown').setLevel(logging.DEBUG)
logging.getLogger('src.core.position_closer').setLevel(logging.DEBUG)
logging.getLogger('src.core.agent_terminator').setLevel(logging.DEBUG)
logging.getLogger('src.core.resource_cleaner').setLevel(logging.DEBUG)

# Add detailed logging handler
handler = logging.FileHandler('shutdown_debug.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

for logger_name in ['src.core.shutdown', 'src.core.position_closer', 
                   'src.core.agent_terminator', 'src.core.resource_cleaner']:
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
```

### Progress Callback for Detailed Monitoring

```python
def shutdown_progress_callback(status):
    phase = status.get('phase', 'unknown')
    elapsed = status.get('elapsed_time', 0)
    
    print(f"Shutdown progress - Phase: {phase}, Elapsed: {elapsed:.2f}s")
    
    # Log details based on current phase
    if phase == ShutdownPhase.POSITIONS.value:
        position_closer = get_position_closer(None)
        results = position_closer.get_closing_results()
        print(f"  Positions closed: {results['total_closed']}")
        print(f"  Positions failed: {results['total_failed']}")
    
    elif phase == ShutdownPhase.AGENTS.value:
        # Print active agents
        orchestrator = get_orchestrator()
        active_agents = [a for a in orchestrator.get_all_agents().values() 
                        if getattr(a, 'is_active', False)]
        print(f"  Remaining active agents: {len(active_agents)}")

# Register the callback    
coordinator = get_shutdown_coordinator()
coordinator.register_progress_callback(shutdown_progress_callback)
```

## Performance Issues

### Slow Shutdown

#### Symptoms
- Shutdown takes too long to complete
- Timeouts occur during shutdown
- Specific phases take much longer than expected

#### Possible Causes and Solutions

1. **Too Many Resources to Close**
   - **Cause**: Large number of resources or agents causes slow shutdown
   - **Solution**:
     - Enable concurrent resource cleanup where safe
     - Group similar resources together with a single cleanup callback
     - Prioritize important resources for earlier cleanup

2. **Position Closing Delays**
   - **Cause**: Position closing is slow due to API rate limits or latency
   - **Solution**:
     - Use `PositionCloseStrategy.IMMEDIATE` for faster shutdowns
     - Implement bulk closing where supported by the exchange
     - Close largest/most important positions first

3. **Sequential Operations That Could Be Parallel**
   - **Cause**: Operations that could be parallel are running sequentially
   - **Solution**:
     - Use `asyncio.gather()` for independent operations
     - Implement concurrent agent shutdown for independent agents
     - Separate agents into batches for parallel shutdown

### Memory Usage Spikes

#### Symptoms
- Memory usage increases significantly during shutdown
- Out of memory errors during shutdown
- System becomes sluggish during shutdown

#### Possible Causes and Solutions

1. **Large Log Generation**
   - **Cause**: Excessive logging during shutdown consumes memory
   - **Solution**:
     - Reduce log verbosity during shutdown
     - Implement log rotation during shutdown
     - Flush logs periodically rather than buffering

2. **Resource Accumulation in Callbacks**
   - **Cause**: Cleanup callbacks accumulate data in memory
   - **Solution**:
     - Review cleanup callbacks for memory efficiency
     - Process data in chunks rather than all at once
     - Add explicit garbage collection calls

## Emergency Procedures

### Force Shutdown for Hanging Process

If the normal shutdown process is hanging and you need to force termination:

```python
import signal
import os

# Send SIGTERM to your process
os.kill(os.getpid(), signal.SIGTERM)

# If that doesn't work, use SIGKILL (cannot be caught or ignored)
# WARNING: This bypasses all graceful shutdown logic
os.kill(os.getpid(), signal.SIGKILL)
```

### Recovery After Improper Shutdown

If the system was shut down improperly, perform these steps on next startup:

1. **Check for Orphaned Resources**:
   ```python
   # Implement resource check on startup
   def check_for_orphaned_resources():
       # Check database connection pools
       # Check file handles
       # Check network connections
       # Clean up any found resources
   ```

2. **Reconcile Positions with Exchange**:
   ```python
   async def reconcile_positions():
       # Fetch positions from exchange
       positions = await exchange_api.get_positions()
       
       # Compare with locally tracked positions
       untracked = [p for p in positions if p not in local_position_tracker]
       
       # Log any discrepancies
       if untracked:
           logger.warning(f"Found {len(untracked)} untracked positions: {untracked}")
           
       return untracked
   ```

3. **Reset Agent State**:
   ```python
   def reset_agent_state():
       # Reset all agents to clean initial state
       for agent in get_all_agents():
           agent.reset_state()
           
       # Clear any in-progress work
       work_queue.clear()
   ```

### Using Emergency Mode

For critical situations requiring immediate shutdown:

```python
coordinator = get_shutdown_coordinator()

# Use emergency shutdown mode - minimal timeouts, force mode
await coordinator.emergency_shutdown(
    reason="Critical system error",
    max_wait_time=5.0  # Maximum total shutdown time
)
```

## Preventative Measures

To avoid shutdown issues in the first place:

1. **Regular Shutdown Testing**:
   - Test shutdown regularly in development
   - Include shutdown tests in integration test suite
   - Test with various system loads and states

2. **Immediate Resource Registration**:
   - Register cleanup callbacks as soon as resources are created
   - Use context managers for automatic resource management
   - Create resource factories that handle registration automatically

3. **Proper Agent Implementation**:
   - Ensure all agents implement the shutdown methods correctly
   - Add timeout protection to all external calls in shutdown methods
   - Test agent shutdown methods independently

4. **Monitoring and Metrics**:
   - Track shutdown times and success rates
   - Monitor resource usage during shutdown
   - Set alerts for slow or failing shutdowns 