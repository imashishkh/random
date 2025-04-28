# Agent Health Monitoring and Recovery System

This module provides a comprehensive monitoring and recovery system for agents in the Forex Trading platform. The system tracks agent health, detects failures, and implements automatic recovery mechanisms.

# Agent Types

The system includes various specialized agents for different aspects of forex trading analysis:

## Technical Analysis Agents

Technical analysis agents analyze price and volume data to generate trading signals:

- **Momentum Agents** - RSI, MACD, and other momentum indicators
- **Trend Agents** - Moving averages and trend strength analysis
- **Volatility Agents** - Bollinger Bands, ATR, and volatility breakouts
- **Pattern Recognition Agents** - Chart patterns and candlestick formations
- **Combined Analysis Agents** - Integration of multiple technical approaches
- **Market Condition Analyzer** - Detection of market anomalies and regime changes

For details on the Market Condition Analyzer, see [Market Condition Analyzer Documentation](technical_analysis/README_MARKET_CONDITION.md).

## Fundamental Analysis Agents

Fundamental analysis agents process economic and financial data:

- **Economic Data Agents** - Analysis of economic indicators
- **Financial Data Agents** - Analysis of company financials
- **News Analysis Agents** - Processing of financial news and sentiment

## Signal Synthesizer

The Signal Synthesizer combines signals from technical and fundamental analysis agents, incorporating market condition analysis to improve trading decisions.

# Features

- Real-time agent health monitoring
- Automatic failure detection based on heartbeats and execution results
- Multi-strategy recovery mechanisms
- Health status dashboard and metrics
- API endpoints for monitoring and managing agent health
- Custom alert system for critical failures

## Architecture

The agent health monitoring system consists of the following components:

### 1. Health Metrics

The `HealthMetrics` class in `health.py` tracks various metrics for each agent:

- Success and failure counts
- Consecutive failures (for triggering escalating recovery)
- Response times
- Error history
- Recovery attempts
- Current health status

### 2. Health Monitor

The `AgentHealthMonitor` class in `health.py` manages health tracking for multiple agents:

- Periodic health checks
- Heartbeat monitoring
- Failure detection
- Recovery orchestration
- Alerting

### 3. Integration with Base Agent

The `BaseAgent` class has been extended to integrate with the health monitoring system:

- Automatic registration with health monitor
- Heartbeat reporting
- Success and failure reporting
- Recovery support (reset method)

### 4. API Endpoints

Several API endpoints have been added in `main.py` for monitoring and managing agent health:

- `/health` - Enhanced to include agent health monitoring status
- `/api/agents/health` - Get health metrics for all agents
- `/api/agents/health/{agent_id}` - Get detailed health metrics for a specific agent
- `/api/agents/{agent_id}/restart` - Manually restart a specific agent
- `/api/agents/monitoring/start` - Start the agent health monitoring system
- `/api/agents/monitoring/stop` - Stop the agent health monitoring system

## Health Status Definitions

The system defines the following health statuses for agents:

- **HEALTHY** - Agent is functioning normally with no recent failures
- **DEGRADED** - Agent has experienced some failures but is still functional
- **FAILED** - Agent has experienced multiple consecutive failures and needs recovery
- **RECOVERING** - Agent is currently undergoing automated recovery
- **UNKNOWN** - Initial state or agent status cannot be determined

## Recovery Mechanisms

The system implements a progressive recovery strategy:

1. **Restart** - First recovery attempt simply resets the agent's state
2. **Recreate** - If restart fails, recreate the agent from scratch
3. **Alert** - If all recovery attempts fail, send alerts for manual intervention

## Usage Example

```python
from src.agents.factory import AgentFactory
from src.agents.health import get_health_monitor

# Create an agent
agent = AgentFactory.create_researcher(
    agent_name="Research Agent",
    model_name="gpt-3.5-turbo"
)

# The agent is automatically registered with the health monitor
# during initialization when enable_health_monitoring=True (default)

# Get the health monitor and start monitoring
health_monitor = get_health_monitor()
health_monitor.start_monitoring()

# Health metrics will be automatically reported during agent execution
# through the run() and arun() methods

# To manually check agent health
metrics = health_monitor.get_agent_health(agent.agent_id)
print(metrics)

# To stop monitoring
health_monitor.stop_monitoring()
```

## Example Script

An example script is provided in `src/examples/agent_health_example.py` to demonstrate the health monitoring system. This script:

1. Creates several test agents
2. Simulates agent activities including successes and failures
3. Triggers recovery mechanisms through forced failures
4. Displays a health dashboard with real-time metrics

To run the example:

```bash
python src/examples/agent_health_example.py
```

## Configuration

The health monitoring system can be configured through parameters to the `AgentHealthMonitor` constructor:

- `health_check_interval` - Interval in seconds between health checks (default: 30.0)
- `heartbeat_timeout` - Time in seconds after which an agent is considered unresponsive (default: 300.0)
- `max_recovery_attempts` - Maximum number of recovery attempts per agent (default: 3)
- `recovery_backoff_factor` - Exponential backoff factor for recovery attempts (default: 2.0)

## Extending the System

### Custom Recovery Strategies

You can add custom recovery strategies using the `register_recovery_strategy` method:

```python
def custom_recovery(agent_id, metrics):
    # Implement custom recovery logic
    return success_boolean

health_monitor = get_health_monitor()
health_monitor.register_recovery_strategy("custom_strategy", custom_recovery)
```

### Health Metrics Export

Health metrics can be exported for integration with external monitoring systems:

```python
health_monitor = get_health_monitor()
metrics = health_monitor.get_all_health_metrics()

# Export metrics to external monitoring system
export_to_monitoring_system(metrics)
``` 