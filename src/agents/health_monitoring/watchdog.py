"""
Watchdog monitoring system for agent health checks.

This module implements a watchdog system that runs regular health checks on agents
and triggers appropriate actions when issues are detected. It supports various
types of checks and recovery actions, including Forex-specific monitoring.

The watchdog system is responsible for:
1. Scheduling and running health checks on registered agents
2. Taking appropriate actions when checks fail (notify, restart, circuit break)
3. Tracking recovery attempts and agent health status
4. Providing detailed health status information

Usage Examples:
---------------

Basic setup with a simple health check:
```python
from .health_monitoring.watchdog import AgentWatchdog, WatchdogAction

# Get the singleton instance
watchdog = AgentWatchdog()

# Define a health check function
def check_agent_health(agent_id):
    # Replace with actual health check logic
    agent = get_agent(agent_id)
    return agent.is_healthy()

# Register an agent check
watchdog.register_agent_check(
    agent_id="agent_1",
    check_func=lambda: check_agent_health("agent_1"),
    interval_seconds=30.0,
    actions=[WatchdogAction.NOTIFY, WatchdogAction.RESTART]
)

# Start the watchdog
watchdog.start()
```

Forex-specific checks with market awareness:
```python
from .health_monitoring.watchdog import (
    AgentWatchdog, 
    WatchdogAction,
    WatchdogPriority
)
from ...market.volatility import get_volatility_service

# Get services
watchdog = AgentWatchdog()
volatility_service = get_volatility_service()

# Register a forex agent check with EUR/USD and GBP/USD pairs
watchdog.register_forex_agent_check(
    agent_id="forex_agent_1",
    market_pairs=["EUR/USD", "GBP/USD"],
    volatility_service=volatility_service,
    check_func=lambda: check_forex_agent_health("forex_agent_1"),
    interval_seconds=15.0,
    priority=WatchdogPriority.HIGH,
    actions=[WatchdogAction.NOTIFY, WatchdogAction.RESTART]
)

# Update forex metrics (typically called from agent metrics collector)
watchdog.update_forex_metrics(
    agent_id="forex_agent_1",
    market_pair="EUR/USD",
    trade_latency=150.0,  # ms
    quote_time=time.time(),
    has_market_data_gap=False
)
```

Advanced configuration with custom recovery handler:
```python
# Register custom recovery handler
def custom_recovery(agent_id, error_message):
    print(f"Custom recovery for {agent_id}: {error_message}")
    # Implement custom recovery logic
    return True

watchdog.register_recovery_handler(
    action=WatchdogAction.CUSTOM,
    handler=custom_recovery
)

# Register check with custom action
watchdog.register_agent_check(
    agent_id="special_agent",
    check_func=lambda: special_agent_check(),
    interval_seconds=60.0,
    actions=[WatchdogAction.CUSTOM],
    max_consecutive_failures=5,
    recovery_timeout_seconds=300.0
)
```
"""

import time
import threading
import heapq
import asyncio
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime, timedelta

from ...utils.logging.logger import get_logger
from .health import AgentHealthStatus

logger = get_logger()


class WatchdogPriority(Enum):
    """Priority levels for watchdog checks"""
    HIGH = 0    # Critical components, highest priority
    MEDIUM = 5  # Important but not critical
    LOW = 10    # Non-essential components


class WatchdogAction(Enum):
    """Actions that the watchdog can take when a check fails"""
    NOTIFY = auto()             # Just notify about the issue
    RESTART = auto()           # Attempt to restart the agent
    CIRCUIT_BREAK = auto()  # Trigger circuit breaker
    ESCALATE = auto()         # Escalate to human operator
    FAILOVER = auto()         # Failover to backup system
    RECREATE = auto()         # Recreate the agent from scratch
    CUSTOM = auto()           # Custom handler


class WatchdogCheck:
    """
    Represents a scheduled health check to be performed by the watchdog.
    Implements comparison methods for priority queue ordering.
    """
    
    def __init__(
        self,
        agent_id: str,
        check_func: Callable[[], bool],
        interval_seconds: float,
        priority: WatchdogPriority = WatchdogPriority.MEDIUM,
        actions: List[WatchdogAction] = None,
        description: str = "",
        max_failures: int = 3,
        max_consecutive_failures: int = 3,
        recovery_timeout_seconds: float = 600.0
    ):
        """
        Initialize a watchdog check.
        
        Args:
            agent_id: ID of the agent to check
            check_func: Function that performs the health check, returns True if healthy
            interval_seconds: How often to run the check
            priority: Check priority level
            actions: Actions to take if check fails
            description: Human-readable description of the check
            max_failures: Maximum total failures before taking action
            max_consecutive_failures: Maximum consecutive failures before taking action
            recovery_timeout_seconds: Time to wait before attempting recovery again
        """
        self.agent_id = agent_id
        self.check_func = check_func
        self.interval_seconds = interval_seconds
        self.priority = priority
        self.actions = actions or [WatchdogAction.NOTIFY]
        self.description = description
        self.max_failures = max_failures
        self.max_consecutive_failures = max_consecutive_failures
        self.recovery_timeout_seconds = recovery_timeout_seconds
        
        # State tracking
        self.failure_count = 0
        self.consecutive_failures = 0
        self.last_check_time = 0
        self.next_check_time = time.time()
        self.last_status = None
        self.last_error = None
        self.check_history = []
        self.last_recovery_time = 0
        
    def __lt__(self, other):
        """Compare for priority queue ordering: by next_check_time, then priority"""
        if self.next_check_time != other.next_check_time:
            return self.next_check_time < other.next_check_time
        return self.priority.value < other.priority.value
        
    def __eq__(self, other):
        """Equality check for priority queue"""
        return (self.next_check_time == other.next_check_time and 
                self.priority == other.priority and
                self.agent_id == other.agent_id)
    
    def run_check(self) -> Tuple[bool, Optional[str]]:
        """
        Run the health check and update state.
        
        Returns:
            Tuple of (is_healthy, error_message)
        """
        self.last_check_time = time.time()
        self.next_check_time = self.last_check_time + self.interval_seconds
        
        try:
            result = self.check_func()
            if result:
                # Check passed
                self.consecutive_failures = 0
                self.last_status = True
                self.last_error = None
                
                # Add to history
                self.check_history.append({
                    "timestamp": self.last_check_time,
                    "status": "healthy",
                    "error": None
                })
                if len(self.check_history) > 100:  # Limit history size
                    self.check_history.pop(0)
                    
                return True, None
            else:
                # Check failed
                self.failure_count += 1
                self.consecutive_failures += 1
                self.last_status = False
                self.last_error = "Check returned False"
                
                # Add to history
                self.check_history.append({
                    "timestamp": self.last_check_time,
                    "status": "unhealthy",
                    "error": "Check returned False"
                })
                if len(self.check_history) > 100:
                    self.check_history.pop(0)
                    
                return False, "Check returned False"
                
        except Exception as e:
            # Check threw an exception
            error_message = f"{type(e).__name__}: {str(e)}"
            self.failure_count += 1
            self.consecutive_failures += 1
            self.last_status = False
            self.last_error = error_message
            
            # Add to history
            self.check_history.append({
                "timestamp": self.last_check_time,
                "status": "error",
                "error": error_message
            })
            if len(self.check_history) > 100:
                self.check_history.pop(0)
                
            logger.error(f"Watchdog check for {self.agent_id} failed with error: {error_message}")
            return False, error_message
    
    def should_take_action(self) -> bool:
        """
        Determine if an action should be taken based on failure thresholds.
        
        Returns:
            True if action should be taken, False otherwise
        """
        if self.consecutive_failures >= self.max_consecutive_failures:
            return True
        if self.failure_count >= self.max_failures:
            return True
        return False
    
    def reset_failures(self) -> None:
        """Reset failure counters after action has been taken"""
        self.failure_count = 0
        self.consecutive_failures = 0
    
    def get_status(self) -> Dict[str, Any]:
        """Get current check status information"""
        return {
            "agent_id": self.agent_id,
            "description": self.description,
            "priority": self.priority.name,
            "interval_seconds": self.interval_seconds,
            "last_check_time": self.last_check_time,
            "next_check_time": self.next_check_time,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "max_failures": self.max_failures,
            "max_consecutive_failures": self.max_consecutive_failures,
            "actions": [action.value for action in self.actions],
            "recent_history": self.check_history[-5:] if self.check_history else []
        }


class ForexWatchdogCheck(WatchdogCheck):
    """
    Specialized watchdog check for Forex trading agents with market-aware monitoring.
    Extends the base WatchdogCheck with trading-specific metrics and thresholds.
    """
    
    def __init__(
        self,
        agent_id: str,
        check_func: Callable[[], bool],
        interval_seconds: float,
        market_pairs: List[str],
        volatility_service: Any,  # MarketVolatilityService
        priority: WatchdogPriority = WatchdogPriority.HIGH,  # Default to HIGH for trading agents
        actions: List[WatchdogAction] = None,
        description: str = "",
        max_failures: int = 3,
        max_consecutive_failures: int = 3,
        trade_latency_threshold_ms: float = 500.0,
        quote_staleness_threshold_ms: float = 2000.0,
        market_data_gap_threshold: int = 5,
        recovery_timeout_seconds: float = 600.0
    ):
        """
        Initialize a Forex-specific watchdog check.
        
        Args:
            agent_id: ID of the agent to check
            check_func: Function that performs the health check
            interval_seconds: How often to run the check
            market_pairs: List of currency pairs this agent trades
            volatility_service: Service for checking market volatility
            priority: Check priority level
            actions: Actions to take if check fails
            description: Human-readable description of the check
            max_failures: Maximum total failures before taking action
            max_consecutive_failures: Maximum consecutive failures before taking action
            trade_latency_threshold_ms: Maximum acceptable trade execution latency
            quote_staleness_threshold_ms: Maximum acceptable quote age
            market_data_gap_threshold: Maximum acceptable gaps in market data per minute
            recovery_timeout_seconds: Time to wait before attempting recovery again
        """
        super().__init__(
            agent_id=agent_id,
            check_func=check_func,
            interval_seconds=interval_seconds,
            priority=priority,
            actions=actions or [WatchdogAction.NOTIFY, WatchdogAction.RESTART],
            description=description,
            max_failures=max_failures,
            max_consecutive_failures=max_consecutive_failures,
            recovery_timeout_seconds=recovery_timeout_seconds
        )
        
        self.market_pairs = market_pairs
        self.volatility_service = volatility_service
        self.trade_latency_threshold_ms = trade_latency_threshold_ms
        self.quote_staleness_threshold_ms = quote_staleness_threshold_ms
        self.market_data_gap_threshold = market_data_gap_threshold
        
        # Trading metrics tracking
        self.trade_latencies = {pair: [] for pair in market_pairs}  # List of recent latencies
        self.last_quote_times = {pair: 0 for pair in market_pairs}  # Last quote timestamp per pair
        self.market_data_gaps = {pair: 0 for pair in market_pairs}  # Gaps detected in last minute
        self.last_trade_times = {pair: 0 for pair in market_pairs}  # Last trade timestamp per pair
        
        # Market condition tracking
        self.market_conditions = {
            "volatility": {},  # pair -> volatility level
            "is_active_hours": True,
            "recent_news_events": []
        }
        
    def update_trade_latency(self, market_pair: str, latency_ms: float) -> None:
        """Record a new trade execution latency measurement."""
        if market_pair in self.trade_latencies:
            self.trade_latencies[market_pair].append(latency_ms)
            # Keep only last 50 measurements
            if len(self.trade_latencies[market_pair]) > 50:
                self.trade_latencies[market_pair].pop(0)
            self.last_trade_times[market_pair] = time.time()
    
    def update_quote_time(self, market_pair: str, quote_time: float) -> None:
        """Update the last quote received time for a market pair."""
        if market_pair in self.last_quote_times:
            self.last_quote_times[market_pair] = quote_time
    
    def record_market_data_gap(self, market_pair: str) -> None:
        """Record a detected gap in market data."""
        if market_pair in self.market_data_gaps:
            self.market_data_gaps[market_pair] += 1
    
    def _adjust_thresholds_for_market_conditions(self) -> None:
        """Adjust failure thresholds based on current market conditions."""
        # Get current market conditions
        high_volatility_pairs = []
        for pair in self.market_pairs:
            volatility = self.volatility_service.get_volatility(pair)
            self.market_conditions["volatility"][pair] = volatility
            if volatility > 0.8:  # High volatility threshold
                high_volatility_pairs.append(pair)
        
        # Update active hours status
        self.market_conditions["is_active_hours"] = self.volatility_service.is_active_trading_hours()
        
        # Get recent significant news events
        self.market_conditions["recent_news_events"] = (
            self.volatility_service.get_recent_news_events()
        )
        
        # Adjust thresholds based on conditions
        if high_volatility_pairs:
            # More tolerant during high volatility
            self.max_consecutive_failures += 2
            self.trade_latency_threshold_ms *= 1.5
            self.quote_staleness_threshold_ms *= 1.2
        
        if not self.market_conditions["is_active_hours"]:
            # More tolerant during off-hours
            self.interval_seconds *= 2
            self.quote_staleness_threshold_ms *= 2
    
    def run_check(self) -> Tuple[bool, Optional[str]]:
        """
        Run the Forex-specific health check with market awareness.
        
        Returns:
            Tuple of (is_healthy, error_message)
        """
        # Adjust thresholds based on current market conditions
        self._adjust_thresholds_for_market_conditions()
        
        try:
            # Run the base check first
            is_healthy, error_message = super().run_check()
            if not is_healthy:
                return False, error_message
            
            # Additional Forex-specific health checks
            warnings = []
            
            # Check trade latencies
            for pair, latencies in self.trade_latencies.items():
                if latencies:
                    avg_latency = sum(latencies) / len(latencies)
                    if avg_latency > self.trade_latency_threshold_ms:
                        warnings.append(
                            f"High trade latency for {pair}: {avg_latency:.2f}ms "
                            f"(threshold: {self.trade_latency_threshold_ms}ms)"
                        )
            
            # Check quote staleness
            now = time.time()
            for pair, last_quote in self.last_quote_times.items():
                if last_quote > 0:  # Only check if we've received quotes
                    staleness = (now - last_quote) * 1000  # Convert to ms
                    if staleness > self.quote_staleness_threshold_ms:
                        warnings.append(
                            f"Stale quotes for {pair}: {staleness:.2f}ms old "
                            f"(threshold: {self.quote_staleness_threshold_ms}ms)"
                        )
            
            # Check market data gaps
            for pair, gaps in self.market_data_gaps.items():
                if gaps > self.market_data_gap_threshold:
                    warnings.append(
                        f"Excessive market data gaps for {pair}: {gaps} in last minute "
                        f"(threshold: {self.market_data_gap_threshold})"
                    )
            
            # Check trading activity
            for pair, last_trade in self.last_trade_times.items():
                # Only check during active hours
                if (self.market_conditions["is_active_hours"] and 
                    self.market_conditions["volatility"].get(pair, 0) > 0.3):
                    trade_gap = now - last_trade
                    if trade_gap > 300:  # 5 minutes without trades during active market
                        warnings.append(
                            f"No trades for {pair} in {trade_gap:.1f} seconds during "
                            f"active market conditions"
                        )
            
            if warnings:
                # Add market context to the warning message
                context = []
                if high_vol_pairs := [
                    p for p, v in self.market_conditions["volatility"].items() 
                    if v > 0.8
                ]:
                    context.append(f"High volatility in {', '.join(high_vol_pairs)}")
                if self.market_conditions["recent_news_events"]:
                    context.append("Recent market-moving news events")
                if not self.market_conditions["is_active_hours"]:
                    context.append("Outside of active trading hours")
                
                warning_msg = "\n".join(warnings)
                if context:
                    warning_msg += f"\nMarket Context: {'; '.join(context)}"
                
                return False, warning_msg
            
            return True, None
            
        except Exception as e:
            error_msg = f"Forex health check error: {type(e).__name__}: {str(e)}"
            logger.error(f"{error_msg} for agent {self.agent_id}")
            return False, error_msg
    
    def get_status(self) -> Dict[str, Any]:
        """Get current check status with Forex-specific metrics."""
        base_status = super().get_status()
        
        # Add Forex-specific status information
        forex_status = {
            "market_pairs": self.market_pairs,
            "trade_latencies": {
                pair: sum(lats) / len(lats) if lats else 0 
                for pair, lats in self.trade_latencies.items()
            },
            "quote_staleness": {
                pair: (time.time() - qt) * 1000 if qt > 0 else 0
                for pair, qt in self.last_quote_times.items()
            },
            "market_data_gaps": self.market_data_gaps,
            "market_conditions": self.market_conditions,
            "thresholds": {
                "trade_latency_ms": self.trade_latency_threshold_ms,
                "quote_staleness_ms": self.quote_staleness_threshold_ms,
                "market_data_gaps": self.market_data_gap_threshold
            }
        }
        
        base_status.update({"forex_metrics": forex_status})
        return base_status


class AgentWatchdog:
    """
    Watchdog system that monitors agent health and triggers recovery actions.
    
    Uses a priority queue to schedule health checks efficiently, with
    high-priority checks processed first when multiple are due.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentWatchdog, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the watchdog if not already initialized"""
        if not hasattr(self, '_initialized') or not self._initialized:
            # Check queue and tracking
            self._check_queue = []  # Priority queue of checks
            self._checks_by_agent = {}  # Lookup by agent ID
            self._active = False
            self._stop_event = threading.Event()
            self._check_thread = None
            self._lock = threading.RLock()
            
            # Action handling
            self._action_handlers = {
                WatchdogAction.NOTIFY: self._handle_notify,
                WatchdogAction.RESTART: self._handle_restart,
                WatchdogAction.CIRCUIT_BREAK: self._handle_circuit_break,
                WatchdogAction.ESCALATE: self._handle_escalate,
                WatchdogAction.FAILOVER: self._handle_failover,
                WatchdogAction.RECREATE: self._handle_recreate,
                WatchdogAction.CUSTOM: self._handle_custom
            }
            
            # Recovery tracking
            self._recovery_history = []
            self._initialized = True
            
            # Forex-specific tracking
            self.forex_agents = set()  # Set of Forex agent IDs
            self.market_pairs_by_agent = {}  # agent_id -> List[market_pair]
            self.volatility_service = None  # Will be set when first Forex agent is registered
            
            logger.info("Agent watchdog initialized")
    
    def register_check(self, check: WatchdogCheck) -> None:
        """
        Register a new health check with the watchdog.
        
        Args:
            check: WatchdogCheck to register
        """
        with self._lock:
            # Store by agent ID for easy lookup
            if check.agent_id not in self._checks_by_agent:
                self._checks_by_agent[check.agent_id] = []
            self._checks_by_agent[check.agent_id].append(check)
            
            # Add to priority queue
            heapq.heappush(self._check_queue, check)
            
            logger.info(f"Registered watchdog check for agent {check.agent_id}: {check.description}")
    
    def register_heartbeat_check(
        self,
        agent_id: str,
        heartbeat_func: Callable[[], datetime],
        max_delay_seconds: float = 30.0,
        interval_seconds: float = 15.0,
        priority: WatchdogPriority = WatchdogPriority.HIGH,
        actions: List[WatchdogAction] = None,
        description: str = "Agent heartbeat check"
    ) -> None:
        """
        Register a standard heartbeat check.
        
        Args:
            agent_id: ID of the agent to check
            heartbeat_func: Function that returns the latest heartbeat time
            max_delay_seconds: Maximum allowed time since last heartbeat
            interval_seconds: How often to check
            priority: Check priority
            actions: Actions to take on failure
            description: Check description
        """
        actions = actions or [WatchdogAction.RESTART]
        
        # Create a check function to verify heartbeat
        def check_heartbeat() -> bool:
            try:
                last_heartbeat = heartbeat_func()
                now = datetime.now()
                delay = now - last_heartbeat
                
                # Check if delay exceeds threshold
                if delay.total_seconds() > max_delay_seconds:
                    logger.warning(
                        f"Agent {agent_id} heartbeat delayed: {delay.total_seconds():.1f}s "
                        f"(max allowed: {max_delay_seconds}s)"
                    )
                    return False
                    
                return True
            except Exception as e:
                logger.error(f"Error checking heartbeat for agent {agent_id}: {str(e)}")
                return False
        
        # Create and register the check
        check = WatchdogCheck(
            agent_id=agent_id,
            check_func=check_heartbeat,
            interval_seconds=interval_seconds,
            priority=priority,
            actions=actions,
            description=f"{description} (max delay: {max_delay_seconds}s)",
            max_failures=3,
            max_consecutive_failures=2
        )
        
        self.register_check(check)
    
    def register_status_check(
        self,
        agent_id: str,
        status_func: Callable[[], AgentHealthStatus],
        interval_seconds: float = 30.0,
        priority: WatchdogPriority = WatchdogPriority.MEDIUM,
        actions: List[WatchdogAction] = None,
        description: str = "Agent status check"
    ) -> None:
        """
        Register a standard status check.
        
        Args:
            agent_id: ID of the agent to check
            status_func: Function that returns the agent's health status
            interval_seconds: How often to check
            priority: Check priority
            actions: Actions to take on failure
            description: Check description
        """
        actions = actions or [WatchdogAction.NOTIFY, WatchdogAction.RESTART]
        
        # Create a check function to verify status
        def check_status() -> bool:
            try:
                status = status_func()
                return status == AgentHealthStatus.HEALTHY
            except Exception as e:
                logger.error(f"Error checking status for agent {agent_id}: {str(e)}")
                return False
        
        # Create and register the check
        check = WatchdogCheck(
            agent_id=agent_id,
            check_func=check_status,
            interval_seconds=interval_seconds,
            priority=priority,
            actions=actions,
            description=description,
            max_failures=3,
            max_consecutive_failures=2
        )
        
        self.register_check(check)
    
    def register_forex_agent_check(
        self,
        agent_id: str,
        market_pairs: List[str],
        volatility_service: Any,
        check_func: Callable[[], bool],
        interval_seconds: float = 15.0,
        trade_latency_threshold_ms: float = 500.0,
        quote_staleness_threshold_ms: float = 2000.0,
        market_data_gap_threshold: int = 5,
        priority: WatchdogPriority = WatchdogPriority.HIGH,
        actions: List[WatchdogAction] = None,
        description: str = "Forex agent health check"
    ) -> None:
        """
        Register a specialized health check for a Forex trading agent.
        
        Args:
            agent_id: ID of the Forex agent to monitor
            market_pairs: List of currency pairs this agent trades
            volatility_service: Service for checking market volatility
            check_func: Function that performs the basic health check
            interval_seconds: How often to run the check
            trade_latency_threshold_ms: Maximum acceptable trade execution latency
            quote_staleness_threshold_ms: Maximum acceptable quote age
            market_data_gap_threshold: Maximum acceptable gaps in market data per minute
            priority: Check priority level
            actions: Actions to take if check fails
            description: Human-readable description of the check
        """
        with self._lock:
            # Store Forex-specific information
            self.forex_agents.add(agent_id)
            self.market_pairs_by_agent[agent_id] = market_pairs
            if self.volatility_service is None:
                self.volatility_service = volatility_service
            
            # Create and register the Forex-specific check
            check = ForexWatchdogCheck(
                agent_id=agent_id,
                check_func=check_func,
                interval_seconds=interval_seconds,
                market_pairs=market_pairs,
                volatility_service=volatility_service,
                priority=priority,
                actions=actions,
                description=description,
                trade_latency_threshold_ms=trade_latency_threshold_ms,
                quote_staleness_threshold_ms=quote_staleness_threshold_ms,
                market_data_gap_threshold=market_data_gap_threshold
            )
            
            self._checks_by_agent[agent_id] = [check]
            heapq.heappush(self._check_queue, check)
            
            logger.info(
                f"Registered Forex health check for agent {agent_id} "
                f"monitoring {len(market_pairs)} pairs"
            )
    
    def update_forex_metrics(
        self,
        agent_id: str,
        market_pair: str,
        trade_latency: Optional[float] = None,
        quote_time: Optional[float] = None,
        has_market_data_gap: bool = False
    ) -> None:
        """
        Update health metrics for a Forex trading agent.
        
        Args:
            agent_id: ID of the Forex agent
            market_pair: The currency pair these metrics are for
            trade_latency: Trade execution latency in milliseconds (if a trade occurred)
            quote_time: Timestamp of the latest quote (if a quote was received)
            has_market_data_gap: True if a gap in market data was detected
        """
        with self._lock:
            if agent_id not in self.forex_agents:
                logger.warning(f"Attempted to update metrics for non-Forex agent {agent_id}")
                return
            
            checks = self._checks_by_agent.get(agent_id, [])
            if not checks:
                logger.error(f"No checks found for agent {agent_id}")
                return
            
            for check in checks:
                if isinstance(check, ForexWatchdogCheck):
                    if trade_latency is not None:
                        check.update_trade_latency(market_pair, trade_latency)
                    if quote_time is not None:
                        check.update_quote_time(market_pair, quote_time)
                    if has_market_data_gap:
                        check.record_market_data_gap(market_pair)
    
    def get_forex_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed status information for a Forex trading agent.
        
        Args:
            agent_id: ID of the Forex agent
        
        Returns:
            Dictionary with detailed Forex-specific health metrics, or None if not a Forex agent
        """
        with self._lock:
            if agent_id not in self.forex_agents:
                return None
            
            checks = self._checks_by_agent.get(agent_id, [])
            if not checks:
                return None
            
            for check in checks:
                if isinstance(check, ForexWatchdogCheck):
                    return check.get_status()
            return None
    
    def get_all_forex_agent_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status information for all Forex trading agents.
        
        Returns:
            Dictionary mapping agent IDs to their Forex-specific health metrics
        """
        with self._lock:
            return {
                agent_id: self.get_forex_agent_status(agent_id)
                for agent_id in self.forex_agents
                if self.get_forex_agent_status(agent_id) is not None
            }
    
    def start(self) -> None:
        """Start the watchdog monitoring thread"""
        with self._lock:
            if self._active:
                logger.warning("Watchdog already running")
                return
                
            self._active = True
            self._stop_event.clear()
            self._check_thread = threading.Thread(
                target=self._check_loop,
                name="WatchdogMonitorThread"
            )
            self._check_thread.daemon = True
            self._check_thread.start()
            
            logger.info("Watchdog monitoring started")
    
    def stop(self) -> None:
        """Stop the watchdog monitoring thread"""
        with self._lock:
            if not self._active:
                logger.warning("Watchdog not running")
                return
                
            self._active = False
            self._stop_event.set()
            
            if self._check_thread and self._check_thread.is_alive():
                self._check_thread.join(timeout=5.0)
                
            logger.info("Watchdog monitoring stopped")
    
    def _check_loop(self) -> None:
        """Main monitoring loop that runs in a separate thread"""
        logger.info("Watchdog monitoring thread started")
        
        while not self._stop_event.is_set():
            try:
                # Process any checks that are due
                self._process_due_checks()
                
                # Sleep briefly
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in watchdog check loop: {str(e)}")
                # Avoid tight error loop
                time.sleep(1.0)
    
    def _process_due_checks(self) -> None:
        """Process all checks that are due to run"""
        now = time.time()
        
        with self._lock:
            # Process checks until we find one that's not due yet
            while self._check_queue and self._check_queue[0].next_check_time <= now:
                # Get the next check
                check = heapq.heappop(self._check_queue)
                
                # Run the check outside the lock to avoid deadlock
                # (check implementations might acquire locks)
                
        # Run the check
        is_healthy, error_message = check.run_check()
        
        # Re-acquire lock to update state and queue
        with self._lock:
            # Check if action needs to be taken
            if not is_healthy and check.should_take_action():
                # Take appropriate actions
                self._take_actions(check, error_message)
                
                # Reset failure counters after taking action
                check.reset_failures()
                
            # Put the check back in the queue with updated next_check_time
            heapq.heappush(self._check_queue, check)
    
    def _take_actions(self, check: WatchdogCheck, error_message: Optional[str]) -> None:
        """
        Take the configured actions for a failed check.
        
        Args:
            check: The failed check
            error_message: Error message from the check
        """
        logger.warning(
            f"Taking actions for failed check on agent {check.agent_id}: "
            f"{check.description} - {error_message or 'No error details'}"
        )
        
        # Add market context for Forex agents
        if isinstance(check, ForexWatchdogCheck):
            context = []
            if high_vol_pairs := [
                p for p, v in check.market_conditions["volatility"].items() 
                if v > 0.8
            ]:
                context.append(f"High volatility in {', '.join(high_vol_pairs)}")
            if check.market_conditions["recent_news_events"]:
                context.append("Recent market-moving news events")
            if not check.market_conditions["is_active_hours"]:
                context.append("Outside of active trading hours")
            
            if context:
                error_message = (
                    f"{error_message}\nMarket Context: {'; '.join(context)}"
                    if error_message else f"Market Context: {'; '.join(context)}"
                )
        
        # Record recovery attempt
        recovery_record = {
            "timestamp": time.time(),
            "agent_id": check.agent_id,
            "check_description": check.description,
            "error": error_message,
            "actions_taken": [],
            "success": False
        }
        
        # Execute each configured action
        for action in check.actions:
            try:
                handler = self._action_handlers.get(action)
                if handler:
                    action_result = handler(check, error_message)
                    recovery_record["actions_taken"].append({
                        "action": action.value,
                        "result": action_result
                    })
                else:
                    logger.error(f"No handler for action: {action}")
            except Exception as e:
                logger.error(f"Error executing action {action} for agent {check.agent_id}: {str(e)}")
                recovery_record["actions_taken"].append({
                    "action": action.value,
                    "result": f"Error: {str(e)}"
                })
        
        # Update recovery history
        self._recovery_history.append(recovery_record)
        if len(self._recovery_history) > 1000:  # Limit history size
            self._recovery_history.pop(0)
    
    def _handle_notify(self, check: WatchdogCheck, error_message: Optional[str]) -> str:
        """
        Handle NOTIFY action.
        
        Args:
            check: The failed check
            error_message: Error message from the check
            
        Returns:
            Action result message
        """
        message = (
            f"AGENT HEALTH ALERT: Agent {check.agent_id} failed health check: "
            f"{check.description}. Error: {error_message or 'No details'}"
        )
        
        logger.warning(message)
        
        # In a real implementation, this might send an email, Slack message, etc.
        # For now just log it
        
        return "Notification logged"
    
    def _handle_restart(self, check: WatchdogCheck, error_message: Optional[str]) -> str:
        """
        Handle RESTART action.
        
        Args:
            check: The failed check
            error_message: Error message from the check
            
        Returns:
            Action result message
        """
        agent_id = check.agent_id
        logger.warning(f"Attempting to restart agent {agent_id} due to failed health check")
        
        try:
            # Get the recovery orchestrator and request a restart
            from src.agents.health_monitoring.recovery_orchestrator import get_recovery_orchestrator, RecoveryStrategy, RecoveryRequest
            import uuid
            
            recovery_orchestrator = get_recovery_orchestrator()
            
            # Create a unique recovery ID
            recovery_id = str(uuid.uuid4())
            
            # Get agent type if possible
            agent_type = "unknown"
            if agent_id in self._checks_by_agent:
                agent_checks = self._checks_by_agent[agent_id]
                if agent_checks and hasattr(agent_checks[0], 'agent_type'):
                    agent_type = agent_checks[0].agent_type
            
            # Check if this is a forex agent
            is_forex_agent = agent_id in self.forex_agents
            
            # Create recovery request
            request = RecoveryRequest(
                recovery_id=recovery_id,
                agent_id=agent_id,
                agent_type=agent_type,
                strategy=RecoveryStrategy.RESTART,
                timestamp=time.time(),
                options={
                    "error_message": error_message,
                    "is_forex_agent": is_forex_agent,
                    "market_pairs": self.market_pairs_by_agent.get(agent_id, []) if is_forex_agent else [],
                    "initiated_by": "watchdog"
                }
            )
            
            # Schedule immediate recovery
            recovery_orchestrator.schedule_recovery(request)
            
            return f"Recovery scheduled for agent {agent_id} (recovery ID: {recovery_id})"
        except Exception as e:
            error_msg = f"Error initiating recovery for agent {agent_id}: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _handle_circuit_break(self, check: WatchdogCheck, error_message: Optional[str]) -> str:
        """
        Handle CIRCUIT_BREAK action.
        
        Args:
            check: The failed check
            error_message: Error message from the check
            
        Returns:
            Action result message
        """
        agent_id = check.agent_id
        logger.warning(f"Triggering circuit breaker for agent {agent_id} due to failed health check")
        
        try:
            # Get the circuit breaker registry
            from src.agents.health_monitoring.circuit_breaker import (
                get_circuit_breaker_registry,
                CircuitState
            )
            
            registry = get_circuit_breaker_registry()
            
            # Get or create circuit for this agent
            circuit_name = f"agent-{agent_id}"
            circuit = registry.get_circuit(circuit_name)
            
            if not circuit:
                # Create a new circuit breaker with default settings
                circuit = registry.create_circuit(
                    name=circuit_name,
                    failure_threshold=3,
                    recovery_timeout=60.0,
                    half_open_max_calls=2
                )
                
            # Check if already open
            if circuit.state == CircuitState.OPEN:
                return f"Circuit breaker for agent {agent_id} is already open"
            
            # Forcibly transition to open state
            circuit._transition_to_open(reason=error_message or "Watchdog-initiated circuit break")
            
            logger.info(f"Circuit breaker for agent {agent_id} opened by watchdog")
            
            # Return result
            return f"Circuit breaker triggered for agent {agent_id}"
            
        except Exception as e:
            error_msg = f"Error triggering circuit breaker for agent {agent_id}: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _handle_escalate(self, check: WatchdogCheck, error_message: Optional[str]) -> str:
        """
        Handle ESCALATE action.
        
        Args:
            check: The failed check
            error_message: Error message from the check
            
        Returns:
            Action result message
        """
        agent_id = check.agent_id
        message = (
            f"ESCALATION REQUIRED: Agent {agent_id} failed health check: "
            f"{check.description}. Error: {error_message or 'No details'}"
        )
        
        logger.critical(message)
        
        # In a real implementation, this might trigger a pager duty alert, SMS, etc.
        # For now just log it
        
        return "Escalation logged"
    
    def _handle_failover(self, check: WatchdogCheck, error_message: Optional[str]) -> str:
        """
        Handle FAILOVER action.
        
        Args:
            check: The failed check
            error_message: Error message from the check
            
        Returns:
            Action result message
        """
        agent_id = check.agent_id
        logger.warning(f"Initiating failover for agent {agent_id} due to failed health check")
        
        # In a real implementation, this would call into a failover system
        # For now, just log the attempt
        
        try:
            # This is a placeholder; in the real implementation, this would call
            # the recovery orchestrator to handle the failover
            
            # from src.agents.health_monitoring.recovery_orchestrator import get_recovery_orchestrator
            # recovery_orchestrator = get_recovery_orchestrator()
            # result = recovery_orchestrator.failover_agent(agent_id)
            
            # For now, just simulate a successful failover
            time.sleep(0.5)  # Simulate failover time
            return f"Failover initiated for agent {agent_id}"
        except Exception as e:
            error_msg = f"Error initiating failover for agent {agent_id}: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _handle_recreate(self, check: WatchdogCheck, error_message: Optional[str]) -> str:
        """
        Handle RECREATE action.
        
        Args:
            check: The failed check
            error_message: Error message from the check
            
        Returns:
            Action result message
        """
        agent_id = check.agent_id
        logger.warning(f"Initiating recreate for agent {agent_id} due to failed health check")
        
        # In a real implementation, this would call into a recreate system
        # For now, just log the attempt
        
        try:
            # This is a placeholder; in the real implementation, this would call
            # the recovery orchestrator to handle the recreate
            
            # from src.agents.health_monitoring.recovery_orchestrator import get_recovery_orchestrator
            # recovery_orchestrator = get_recovery_orchestrator()
            # result = recovery_orchestrator.recreate_agent(agent_id)
            
            # For now, just simulate a successful recreate
            time.sleep(0.5)  # Simulate recreate time
            return f"Recreate initiated for agent {agent_id}"
        except Exception as e:
            error_msg = f"Error initiating recreate for agent {agent_id}: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _handle_custom(self, check: WatchdogCheck, error_message: Optional[str]) -> str:
        """
        Handle CUSTOM action.
        
        Args:
            check: The failed check
            error_message: Error message from the check
            
        Returns:
            Action result message
        """
        agent_id = check.agent_id
        logger.warning(f"Handling custom action for agent {agent_id} due to failed health check")
        
        # In a real implementation, this would call into a custom handler system
        # For now, just log the attempt
        
        try:
            # This is a placeholder; in the real implementation, this would call
            # the recovery orchestrator to handle the custom action
            
            # from src.agents.health_monitoring.recovery_orchestrator import get_recovery_orchestrator
            # recovery_orchestrator = get_recovery_orchestrator()
            # result = recovery_orchestrator.handle_custom_action(agent_id, error_message)
            
            # For now, just simulate a successful custom action
            time.sleep(0.5)  # Simulate custom action time
            return f"Custom action handled for agent {agent_id}"
        except Exception as e:
            error_msg = f"Error handling custom action for agent {agent_id}: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def get_check_status(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get status information about checks.
        
        Args:
            agent_id: Optional agent ID to filter checks
            
        Returns:
            Dictionary with check status information
        """
        with self._lock:
            if agent_id:
                # Get checks for a specific agent
                checks = self._checks_by_agent.get(agent_id, [])
                return {
                    "agent_id": agent_id,
                    "check_count": len(checks),
                    "checks": [check.get_status() for check in checks]
                }
            else:
                # Get status for all checks
                return {
                    "total_check_count": len(self._check_queue),
                    "agent_count": len(self._checks_by_agent),
                    "agents": {
                        agent_id: {
                            "check_count": len(checks),
                            "checks": [check.get_status() for check in checks]
                        }
                        for agent_id, checks in self._checks_by_agent.items()
                    }
                }
    
    def get_recovery_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent recovery actions.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of recovery action records
        """
        with self._lock:
            # Return the most recent records
            return self._recovery_history[-limit:] if self._recovery_history else []


# Singleton accessor
def get_agent_watchdog() -> AgentWatchdog:
    """Get the global agent watchdog instance"""
    return AgentWatchdog() 