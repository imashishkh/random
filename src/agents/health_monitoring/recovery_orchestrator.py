"""
Recovery Orchestrator for Agent Health Management

This module provides functionality for managing agent recovery operations
like restarts, recreations, and failovers with exponential backoff.
"""

import time
import threading
import random
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Type, Tuple
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel

from ...utils.logging.logger import get_logger
from ...utils.singleton import Singleton

logger = get_logger()


class RecoveryStrategy(Enum):
    """Strategies for agent recovery."""
    RESTART = "restart"         # Simple agent restart
    RECREATE = "recreate"       # Recreate agent from scratch
    FAILOVER = "failover"       # Switch to backup agent instance
    THROTTLED = "throttled"     # Throttle agent operations
    ISOLATION = "isolation"     # Isolate agent operations


class RecoveryStatus(Enum):
    """Status of a recovery operation"""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecoveryRequest(BaseModel):
    """Request for agent recovery."""
    recovery_id: str
    agent_id: str
    agent_type: str
    strategy: RecoveryStrategy
    timestamp: float
    in_progress: bool = False
    retry_count: int = 0
    max_retries: int = 3
    options: Dict[str, Any] = {}


class RecoveryRecord:
    """
    Record of a recovery operation, including history and status.
    """
    
    def __init__(
        self,
        request: RecoveryRequest,
        scheduled_time: float,
        attempt: int = 1,
        max_attempts: int = 5
    ):
        """
        Initialize a recovery record.
        
        Args:
            request: The recovery request
            scheduled_time: When the recovery is scheduled to occur
            attempt: Current attempt number
            max_attempts: Maximum number of attempts allowed
        """
        self.request = request
        self.scheduled_time = scheduled_time
        self.attempt = attempt
        self.max_attempts = max_attempts
        
        self.status = RecoveryStatus.SCHEDULED
        self.job_id: Optional[str] = None
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.next_attempt_time: Optional[float] = None
        
        self.events: List[Dict[str, Any]] = [{
            "timestamp": time.time(),
            "status": self.status.value,
            "message": f"Recovery scheduled for {datetime.fromtimestamp(scheduled_time).isoformat()}"
        }]
    
    def update_status(self, status: RecoveryStatus, message: Optional[str] = None) -> None:
        """
        Update the recovery status and add an event.
        
        Args:
            status: New status
            message: Optional message to include
        """
        self.status = status
        
        # Update timestamps
        now = time.time()
        if status == RecoveryStatus.IN_PROGRESS:
            self.started_at = now
        elif status in (RecoveryStatus.SUCCEEDED, RecoveryStatus.FAILED, RecoveryStatus.CANCELLED):
            self.completed_at = now
            
        # Add event
        self.events.append({
            "timestamp": now,
            "status": status.value,
            "message": message or f"Status updated to {status.value}"
        })
    
    def set_result(self, success: bool, details: Dict[str, Any]) -> None:
        """
        Set the result of the recovery operation.
        
        Args:
            success: Whether the recovery succeeded
            details: Details about the operation
        """
        self.result = {
            "success": success,
            "details": details,
            "timestamp": time.time()
        }
        
        self.update_status(
            RecoveryStatus.SUCCEEDED if success else RecoveryStatus.FAILED,
            details.get("message")
        )
    
    def set_error(self, error: str) -> None:
        """
        Set an error for the recovery operation.
        
        Args:
            error: Error message
        """
        self.error = error
        self.update_status(RecoveryStatus.FAILED, error)
    
    def schedule_next_attempt(self, next_time: float) -> None:
        """
        Schedule the next recovery attempt.
        
        Args:
            next_time: When the next attempt should occur
        """
        self.next_attempt_time = next_time
        self.update_status(
            RecoveryStatus.SCHEDULED,
            f"Next attempt ({self.attempt + 1}/{self.max_attempts}) scheduled for {datetime.fromtimestamp(next_time).isoformat()}"
        )
    
    def can_retry(self) -> bool:
        """Check if another retry attempt is allowed"""
        return (
            self.status == RecoveryStatus.FAILED and 
            self.attempt < self.max_attempts
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "recovery_id": self.request.recovery_id,
            "agent_id": self.request.agent_id,
            "agent_type": self.request.agent_type,
            "recovery_strategy": self.request.strategy.value,
            "status": self.status.value,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "scheduled_time": self.scheduled_time,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "next_attempt_time": self.next_attempt_time,
            "events": self.events,
            "options": self.request.options
        }


class RecoveryOrchestrator(metaclass=Singleton):
    """
    Coordinates recovery actions for agents across the system.
    
    This service:
    1. Maintains a queue of recovery requests
    2. Dispatches recovery actions to appropriate handlers
    3. Tracks recovery progress and retries if needed
    4. Implements recovery strategies based on agent types
    """
    
    def __init__(self):
        """Initialize the recovery orchestrator."""
        self._recovery_queue: List[RecoveryRequest] = []
        self._in_progress_recoveries: Dict[str, RecoveryRequest] = {}
        
        # Registry of recovery handlers by agent type
        self._recovery_handlers: Dict[str, Dict[RecoveryStrategy, Callable]] = {}
        
        # Default recovery handlers
        self._default_recovery_handlers: Dict[RecoveryStrategy, Callable] = {
            RecoveryStrategy.RESTART: self._default_restart_handler,
            RecoveryStrategy.RECREATE: self._default_recreate_handler,
            RecoveryStrategy.FAILOVER: self._default_failover_handler,
            RecoveryStrategy.THROTTLED: self._default_throttled_handler,
            RecoveryStrategy.ISOLATION: self._default_isolation_handler,
        }
        
        # Executor for running recovery actions
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="recovery-")
        
        # Flag to indicate if processing is running
        self._is_processing = False
        
        logger.info("RecoveryOrchestrator initialized")
    
    def register_recovery_handler(
        self, 
        agent_type: str, 
        strategy: RecoveryStrategy, 
        handler: Callable[[str], bool]
    ) -> None:
        """
        Register a custom recovery handler for a specific agent type and strategy.
        
        Args:
            agent_type: Type of agent this handler applies to
            strategy: Recovery strategy this handler implements
            handler: Function that performs the recovery action, takes agent_id and returns success boolean
        """
        if agent_type not in self._recovery_handlers:
            self._recovery_handlers[agent_type] = {}
            
        self._recovery_handlers[agent_type][strategy] = handler
        logger.info(f"Registered custom recovery handler for {agent_type}, strategy: {strategy.name}")
    
    def schedule_recovery(
        self, 
        agent_id: str, 
        agent_type: str, 
        recovery_strategy: RecoveryStrategy,
        max_retries: int = 3
    ) -> None:
        """
        Schedule a recovery action for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of the agent
            recovery_strategy: Strategy to use for recovery
            max_retries: Maximum number of retry attempts
        """
        # Check if recovery is already in progress for this agent
        if agent_id in self._in_progress_recoveries:
            logger.warning(f"Recovery already in progress for agent {agent_id}, ignoring new request")
            return
            
        # Check if recovery is already queued for this agent
        for req in self._recovery_queue:
            if req.agent_id == agent_id:
                logger.warning(f"Recovery already queued for agent {agent_id}, ignoring new request")
                return
        
        # Create and queue the recovery request
        request = RecoveryRequest(
            agent_id=agent_id,
            agent_type=agent_type,
            strategy=recovery_strategy,
            timestamp=time.time(),
            max_retries=max_retries
        )
        
        self._recovery_queue.append(request)
        logger.info(f"Scheduled recovery for agent {agent_id} using strategy {recovery_strategy.name}")
        
        # Start processing if not already running
        if not self._is_processing:
            self._executor.submit(self._process_recovery_queue)
    
    def cancel_recovery(self, agent_id: str) -> bool:
        """
        Cancel a pending recovery for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            True if recovery was cancelled, False if no recovery was found
        """
        # Check if agent is in queue
        for i, req in enumerate(self._recovery_queue):
            if req.agent_id == agent_id:
                self._recovery_queue.pop(i)
                logger.info(f"Cancelled queued recovery for agent {agent_id}")
                return True
        
        # Check if agent recovery is in progress
        if agent_id in self._in_progress_recoveries:
            # We can't stop in-progress recovery, so log a warning
            logger.warning(f"Cannot cancel in-progress recovery for agent {agent_id}")
            return False
            
        return False
    
    def get_recovery_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a recovery action for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            Dictionary with recovery status details or None if no recovery exists
        """
        # Check in-progress recoveries
        if agent_id in self._in_progress_recoveries:
            req = self._in_progress_recoveries[agent_id]
            return {
                "agent_id": req.agent_id,
                "strategy": req.strategy.name,
                "status": "in_progress",
                "timestamp": req.timestamp,
                "retry_count": req.retry_count
            }
            
        # Check queued recoveries
        for i, req in enumerate(self._recovery_queue):
            if req.agent_id == agent_id:
                return {
                    "agent_id": req.agent_id,
                    "strategy": req.strategy.name,
                    "status": "queued",
                    "queue_position": i,
                    "timestamp": req.timestamp
                }
                
        return None
    
    def get_all_recovery_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all recovery actions.
        
        Returns:
            Dictionary mapping agent IDs to recovery status details
        """
        statuses = {}
        
        # Add in-progress recoveries
        for agent_id, req in self._in_progress_recoveries.items():
            statuses[agent_id] = {
                "agent_id": req.agent_id,
                "strategy": req.strategy.name,
                "status": "in_progress",
                "timestamp": req.timestamp,
                "retry_count": req.retry_count
            }
            
        # Add queued recoveries
        for i, req in enumerate(self._recovery_queue):
            statuses[req.agent_id] = {
                "agent_id": req.agent_id,
                "strategy": req.strategy.name,
                "status": "queued",
                "queue_position": i,
                "timestamp": req.timestamp
            }
            
        return statuses
    
    def _process_recovery_queue(self) -> None:
        """Process the recovery queue in a separate thread."""
        if self._is_processing:
            return
            
        self._is_processing = True
        
        try:
            # Process queue until empty
            while self._recovery_queue:
                # Get the next request
                request = self._recovery_queue.pop(0)
                agent_id = request.agent_id
                
                # Mark as in progress
                request.in_progress = True
                self._in_progress_recoveries[agent_id] = request
                
                logger.info(f"Processing recovery for agent {agent_id} with strategy {request.strategy.name}")
                
                try:
                    # Attempt recovery
                    success = self._execute_recovery(request)
                    
                    if success:
                        logger.info(f"Recovery successful for agent {agent_id}")
                        # Remove from in-progress
                        if agent_id in self._in_progress_recoveries:
                            del self._in_progress_recoveries[agent_id]
                    else:
                        # Increment retry count
                        request.retry_count += 1
                        
                        if request.retry_count < request.max_retries:
                            logger.warning(
                                f"Recovery failed for agent {agent_id}, retrying "
                                f"({request.retry_count}/{request.max_retries})"
                            )
                            # Re-queue for retry with exponential backoff
                            self._recovery_queue.append(request)
                            # Simple exponential backoff
                            time.sleep(2 ** request.retry_count)
                        else:
                            logger.error(
                                f"Recovery failed for agent {agent_id} after {request.retry_count} attempts"
                            )
                            # Remove from in-progress
                            if agent_id in self._in_progress_recoveries:
                                del self._in_progress_recoveries[agent_id]
                except Exception as e:
                    logger.exception(f"Error during recovery for agent {agent_id}: {str(e)}")
                    # Remove from in-progress
                    if agent_id in self._in_progress_recoveries:
                        del self._in_progress_recoveries[agent_id]
        finally:
            self._is_processing = False
                
    def _execute_recovery(self, request: RecoveryRequest) -> bool:
        """
        Execute a recovery action for an agent.
        
        Args:
            request: Recovery request to execute
            
        Returns:
            True if recovery was successful, False otherwise
        """
        agent_id = request.agent_id
        agent_type = request.agent_type
        strategy = request.strategy
        
        # Check if there's a custom handler for this agent type and strategy
        if (agent_type in self._recovery_handlers and 
            strategy in self._recovery_handlers[agent_type]):
            # Use custom handler
            handler = self._recovery_handlers[agent_type][strategy]
        else:
            # Use default handler for this strategy
            handler = self._default_recovery_handlers.get(strategy)
            
        if not handler:
            logger.error(f"No recovery handler found for strategy {strategy.name}")
            return False
            
        try:
            # Execute recovery action
            return handler(agent_id)
        except Exception as e:
            logger.exception(f"Error in recovery handler for agent {agent_id}: {str(e)}")
            return False
    
    # Default recovery handlers
    
    def _default_restart_handler(self, agent_id: str) -> bool:
        """
        Default handler for restarting an agent.
        
        Args:
            agent_id: ID of the agent to restart
            
        Returns:
            True if restart was successful, False otherwise
        """
        logger.info(f"Executing default restart handler for agent {agent_id}")
        
        try:
            # Import the agent registry and get the agent
            from src.agents.registry import get_agent_registry
            
            agent_registry = get_agent_registry()
            agent = agent_registry.get_agent(agent_id)
            
            if not agent:
                logger.error(f"Agent {agent_id} not found in registry")
                return False
            
            # Execute the restart sequence
            logger.info(f"Stopping agent {agent_id}")
            agent_registry.stop_agent(agent_id)
            
            # Add a small delay to ensure resources are released
            time.sleep(1.0)
            
            logger.info(f"Starting agent {agent_id}")
            success = agent_registry.start_agent(agent_id)
            
            if success:
                logger.info(f"Agent {agent_id} restarted successfully")
            else:
                logger.error(f"Failed to restart agent {agent_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error in default restart handler for agent {agent_id}: {str(e)}")
            return False
    
    def _default_recreate_handler(self, agent_id: str) -> bool:
        """
        Default handler for recreating an agent from scratch.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            True if recreation was successful, False otherwise
        """
        logger.info(f"Executing default recreate handler for agent {agent_id}")
        try:
            # In a real implementation, this would use the AgentFactory to recreate the agent
            # For now, we'll simulate a successful recreation
            # TODO: Implement actual agent recreation using AgentFactory
            logger.warning(f"Default recreate handler is a placeholder. Agent {agent_id} not actually recreated.")
            # Simulate recreation delay
            time.sleep(3)
            return True
        except Exception as e:
            logger.exception(f"Error in default recreate handler for agent {agent_id}: {str(e)}")
            return False
    
    def _default_failover_handler(self, agent_id: str) -> bool:
        """
        Default handler for failing over to a backup agent.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            True if failover was successful, False otherwise
        """
        logger.info(f"Executing default failover handler for agent {agent_id}")
        try:
            # In a real implementation, this would activate a backup agent
            # For now, we'll simulate a successful failover
            # TODO: Implement actual agent failover
            logger.warning(f"Default failover handler is a placeholder. No actual failover for agent {agent_id}.")
            # Simulate failover delay
            time.sleep(2)
            return True
        except Exception as e:
            logger.exception(f"Error in default failover handler for agent {agent_id}: {str(e)}")
            return False
    
    def _default_throttled_handler(self, agent_id: str) -> bool:
        """
        Default handler for throttling an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            True if throttling was successful, False otherwise
        """
        logger.info(f"Executing default throttled handler for agent {agent_id}")
        try:
            # In a real implementation, this would apply rate limiting to the agent
            # For now, we'll simulate a successful throttling
            # TODO: Implement actual agent throttling
            logger.warning(f"Default throttled handler is a placeholder. Agent {agent_id} not actually throttled.")
            # Simulate throttling setup delay
            time.sleep(1)
            return True
        except Exception as e:
            logger.exception(f"Error in default throttled handler for agent {agent_id}: {str(e)}")
            return False
    
    def _default_isolation_handler(self, agent_id: str) -> bool:
        """
        Default handler for isolating an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            True if isolation was successful, False otherwise
        """
        logger.info(f"Executing default isolation handler for agent {agent_id}")
        try:
            # In a real implementation, this would isolate the agent's operations
            # For now, we'll simulate a successful isolation
            # TODO: Implement actual agent isolation
            logger.warning(f"Default isolation handler is a placeholder. Agent {agent_id} not actually isolated.")
            # Simulate isolation setup delay
            time.sleep(1)
            return True
        except Exception as e:
            logger.exception(f"Error in default isolation handler for agent {agent_id}: {str(e)}")
            return False


class TradingRecoveryOrchestrator(RecoveryOrchestrator):
    """
    Specialized recovery orchestrator for trading agents with market awareness.
    
    This orchestrator handles trading-specific concerns like position management
    during agent restarts, volatility-aware recovery timing, and preserving trading state.
    """
    
    def __init__(self):
        """Initialize the trading recovery orchestrator."""
        super().__init__()
        
        # Register trading-specific recovery handlers
        self.register_recovery_handler(
            "forex_trader", 
            RecoveryStrategy.RESTART, 
            self._handle_trading_restart
        )
        
        from src.agents.health_monitoring.watchdog import get_agent_watchdog
        self.watchdog = get_agent_watchdog()
        
        # Get market data service if available
        try:
            from src.data.market_data_service import get_market_data_service
            self.market_data_service = get_market_data_service()
        except (ImportError, AttributeError):
            logger.warning("Market data service not available, using limited market awareness")
            self.market_data_service = None
        
        # Get trading manager if available
        try:
            from src.trading.trading_manager import get_trading_manager
            self.trading_manager = get_trading_manager()
        except (ImportError, AttributeError):
            logger.warning("Trading manager not available, using limited position management")
            self.trading_manager = None
        
        logger.info("TradingRecoveryOrchestrator initialized with market-aware recovery capabilities")
    
    def _handle_trading_restart(self, agent_id: str) -> bool:
        """
        Handle restart of a trading agent with position preservation.
        
        Args:
            agent_id: ID of the trading agent to restart
            
        Returns:
            True if restart was successful, False otherwise
        """
        logger.info(f"Executing trading-aware restart for agent {agent_id}")
        
        try:
            # Get current market conditions to inform restart strategy
            market_conditions = self._get_market_conditions(agent_id)
            high_volatility = market_conditions.get("high_volatility", False)
            is_market_open = market_conditions.get("is_market_open", True)
            
            # Get position information if trading manager is available
            open_positions = []
            open_orders = []
            
            if self.trading_manager:
                try:
                    open_positions = self.trading_manager.get_agent_positions(agent_id)
                    open_orders = self.trading_manager.get_agent_orders(agent_id)
                    logger.info(f"Agent {agent_id} has {len(open_positions)} open positions and {len(open_orders)} open orders")
                except Exception as e:
                    logger.error(f"Error getting position information: {str(e)}")
            
            # Choose appropriate restart strategy based on market conditions
            if not is_market_open:
                # Safe to do simple restart when market is closed
                logger.info(f"Market closed, performing simple restart for agent {agent_id}")
                return self._default_restart_handler(agent_id)
            elif high_volatility and open_positions:
                # If market is volatile and we have positions, preserve them
                logger.info(f"High volatility with open positions, performing state-preserving restart for agent {agent_id}")
                return self._handle_trading_preserve_state(agent_id)
            else:
                # Default case: try to preserve state but be cautious
                logger.info(f"Normal market conditions, performing standard trading restart for agent {agent_id}")
                return self._handle_trading_preserve_state(agent_id)
        except Exception as e:
            logger.error(f"Error in trading restart handler for agent {agent_id}: {str(e)}")
            # Fall back to default handler
            return self._default_restart_handler(agent_id)
    
    def _handle_trading_preserve_state(self, agent_id: str) -> bool:
        """
        Restart a trading agent while preserving its trading state.
        
        Args:
            agent_id: ID of the trading agent to restart
            
        Returns:
            True if restart was successful, False otherwise
        """
        logger.info(f"Executing state-preserving restart for trading agent {agent_id}")
        
        try:
            # Import needed modules
            from src.agents.registry import get_agent_registry
            
            agent_registry = get_agent_registry()
            agent = agent_registry.get_agent(agent_id)
            
            if not agent:
                logger.error(f"Agent {agent_id} not found in registry")
                return False
            
            # Capture the agent's state before restart
            agent_state = {}
            
            # Try to get agent state
            if hasattr(agent, "get_state"):
                try:
                    agent_state = agent.get_state()
                    logger.info(f"Captured state for agent {agent_id}")
                except Exception as e:
                    logger.error(f"Error capturing agent state: {str(e)}")
            
            # Add trading-specific state if trading manager is available
            if self.trading_manager:
                try:
                    agent_state["positions"] = self.trading_manager.get_agent_positions(agent_id)
                    agent_state["orders"] = self.trading_manager.get_agent_orders(agent_id)
                    agent_state["parameters"] = self.trading_manager.get_agent_parameters(agent_id)
                except Exception as e:
                    logger.error(f"Error capturing trading state: {str(e)}")
            
            # Perform the restart
            logger.info(f"Stopping agent {agent_id}")
            agent_registry.stop_agent(agent_id)
            
            # Add a small delay to ensure resources are released
            time.sleep(1.0)
            
            logger.info(f"Starting agent {agent_id} with preserved state")
            success = agent_registry.start_agent(agent_id, initial_state=agent_state)
            
            if success:
                logger.info(f"Agent {agent_id} restarted successfully with state preservation")
                # Verify the restart was successful
                return self._verify_trading_agent_restart(agent_id, agent_state)
            else:
                logger.error(f"Failed to restart agent {agent_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error in state-preserving restart for agent {agent_id}: {str(e)}")
            # Fall back to default handler
            return self._default_restart_handler(agent_id)
    
    def _verify_trading_agent_restart(self, agent_id: str, previous_state: Dict[str, Any]) -> bool:
        """
        Verify that a trading agent was restarted correctly with state preservation.
        
        Args:
            agent_id: ID of the trading agent to verify
            previous_state: State the agent had before restart
            
        Returns:
            True if verification passed, False otherwise
        """
        logger.info(f"Verifying restart for trading agent {agent_id}")
        
        try:
            # Import needed modules
            from src.agents.registry import get_agent_registry
            
            agent_registry = get_agent_registry()
            agent = agent_registry.get_agent(agent_id)
            
            if not agent:
                logger.error(f"Agent {agent_id} not found in registry after restart")
                return False
            
            # Basic health check: agent should be responsive
            if not agent_registry.is_agent_responsive(agent_id):
                logger.error(f"Agent {agent_id} is not responsive after restart")
                return False
            
            # Check if positions were preserved (if applicable)
            if self.trading_manager and "positions" in previous_state:
                try:
                    current_positions = self.trading_manager.get_agent_positions(agent_id)
                    prev_positions = previous_state["positions"]
                    
                    # Check that all previous positions are still present
                    prev_position_ids = {p.get("id") for p in prev_positions}
                    current_position_ids = {p.get("id") for p in current_positions}
                    
                    missing_positions = prev_position_ids - current_position_ids
                    if missing_positions:
                        logger.warning(f"Some positions were not preserved during restart: {missing_positions}")
                except Exception as e:
                    logger.error(f"Error verifying positions after restart: {str(e)}")
            
            logger.info(f"Verification passed for agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error verifying restart for agent {agent_id}: {str(e)}")
            return False
    
    def _get_market_conditions(self, agent_id: str) -> Dict[str, Any]:
        """
        Get current market conditions to inform recovery decisions.
        
        Args:
            agent_id: ID of the agent being recovered
            
        Returns:
            Dictionary with market condition information
        """
        conditions = {
            "high_volatility": False,
            "is_market_open": True,
            "recent_news_impact": False,
            "market_pairs": []
        }
        
        # Get which market pairs this agent trades
        if agent_id in self.watchdog.market_pairs_by_agent:
            conditions["market_pairs"] = self.watchdog.market_pairs_by_agent[agent_id]
        
        # If market data service is available, check market conditions
        if self.market_data_service and conditions["market_pairs"]:
            try:
                # Check if market is open
                conditions["is_market_open"] = self.market_data_service.is_forex_market_open()
                
                # Check volatility for each pair
                for pair in conditions["market_pairs"]:
                    try:
                        volatility = self.market_data_service.get_volatility(pair)
                        if volatility > 0.7:  # Threshold for high volatility
                            conditions["high_volatility"] = True
                            conditions["volatile_pairs"] = conditions.get("volatile_pairs", []) + [pair]
                    except Exception:
                        pass
                
                # Check for recent news impact
                try:
                    news_impact = self.market_data_service.get_recent_news_impact(conditions["market_pairs"])
                    conditions["recent_news_impact"] = news_impact > 0.5  # Threshold for significant news
                except Exception:
                    pass
                    
            except Exception as e:
                logger.error(f"Error getting market conditions: {str(e)}")
        
        return conditions


# Singleton accessors
def get_recovery_orchestrator() -> RecoveryOrchestrator:
    """Get the global recovery orchestrator instance"""
    return RecoveryOrchestrator()


def get_trading_recovery_orchestrator() -> TradingRecoveryOrchestrator:
    """Get the global trading recovery orchestrator instance"""
    return TradingRecoveryOrchestrator() 