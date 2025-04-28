"""
Agent Wrapper Functions for Async Process Management

This module provides standardized wrapper functions for agent execution
with proper monitoring, error handling, and RiskAwareAgent integration.
"""

import asyncio
import logging
import time
import functools
from typing import Any, Dict, Optional, Callable, Awaitable, Type, Union, Tuple

from .base_agent import BaseAgent
from .risk import RiskAwareAgent, require_risk_approval
from ...utils.logging.logger import get_logger
from .error_handling import (
    BaseAgentError,
    RecoverableError, 
    NonRecoverableError,
    ErrorCategory,
    TradeExecutionError,
    RiskApprovalError
)

logger = get_logger()


async def execute_agent_with_monitoring(
    agent: BaseAgent,
    shutdown_event: Optional[asyncio.Event] = None,
    agent_metrics_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    max_consecutive_errors: int = 5,
    cycle_interval: Optional[float] = None
) -> None:
    """
    Execute an agent with comprehensive monitoring and error handling.
    
    This function handles the entire lifecycle of an agent, including
    initialization, main execution loop, error handling, and cleanup.
    
    Args:
        agent: The agent to execute
        shutdown_event: Event that signals when to shut down
        agent_metrics_callback: Callback for reporting agent metrics
        max_consecutive_errors: Maximum allowed consecutive errors before aborting
        cycle_interval: Interval between agent cycles (uses agent.cycle_interval if None)
        
    Raises:
        NonRecoverableError: If the agent encounters a fatal error
    """
    agent_id = getattr(agent, 'agent_id', 'unknown')
    consecutive_errors = 0
    total_cycles = 0
    start_time = time.time()
    
    # Use the provided shutdown event or create a new one
    shutdown_event = shutdown_event or asyncio.Event()
    
    # Use the agent's cycle interval if none provided
    if cycle_interval is None:
        cycle_interval = getattr(agent, 'cycle_interval', 1.0)
    
    try:
        # Initialize the agent
        logger.info(f"Initializing agent {agent_id}")
        await agent.initialize()
        
        # Report initial metrics
        if agent_metrics_callback:
            agent_metrics_callback(agent_id, {
                "status": "running",
                "start_time": start_time,
                "total_cycles": 0,
                "errors": 0
            })
        
        # Main agent execution loop
        while not shutdown_event.is_set():
            cycle_start = time.time()
            
            try:
                # Execute a single cycle of the agent
                await agent.process_cycle()
                total_cycles += 1
                
                # Reset error counter on success
                if consecutive_errors > 0:
                    consecutive_errors = 0
                    
                    # Report recovery
                    if agent_metrics_callback:
                        agent_metrics_callback(agent_id, {
                            "status": "recovered",
                            "consecutive_errors": 0
                        })
                
                # Calculate appropriate sleep time
                elapsed = time.time() - cycle_start
                sleep_time = max(0, cycle_interval - elapsed)
                
                # Wait for next cycle or shutdown event
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(),
                        timeout=sleep_time
                    )
                    # If we get here, shutdown event was triggered
                    logger.info(f"Shutdown event received for agent {agent_id}")
                    break
                except asyncio.TimeoutError:
                    # Normal timeout, continue to next cycle
                    pass
                    
            except RecoverableError as e:
                consecutive_errors += 1
                logger.warning(
                    f"Recoverable error in agent {agent_id} (attempt {consecutive_errors}): {str(e)}"
                )
                
                # Report error metrics
                if agent_metrics_callback:
                    agent_metrics_callback(agent_id, {
                        "status": "error",
                        "error_type": "recoverable",
                        "error_message": str(e),
                        "consecutive_errors": consecutive_errors
                    })
                
                # Check if too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"Agent {agent_id} exceeded maximum consecutive errors ({max_consecutive_errors})"
                    )
                    raise NonRecoverableError(
                        f"Too many consecutive errors: {str(e)}",
                        category=e.category if hasattr(e, 'category') else ErrorCategory.UNKNOWN
                    )
                
                # Allow agent to handle its own error if it can
                if hasattr(agent, 'handle_error') and callable(agent.handle_error):
                    try:
                        await agent.handle_error(e)
                    except Exception as handle_error:
                        logger.error(f"Error in agent.handle_error for {agent_id}: {str(handle_error)}")
                
                # Apply backoff for repeated errors
                if consecutive_errors > 1:
                    backoff_time = min(30, 2 ** (consecutive_errors - 1))
                    logger.info(f"Backing off for {backoff_time}s after {consecutive_errors} consecutive errors")
                    await asyncio.sleep(backoff_time)
                    
            except Exception as e:
                # Handle unexpected errors
                consecutive_errors += 1
                logger.error(f"Unexpected error in agent {agent_id}: {str(e)}")
                
                # Report error metrics
                if agent_metrics_callback:
                    agent_metrics_callback(agent_id, {
                        "status": "error",
                        "error_type": "unexpected",
                        "error_message": str(e),
                        "consecutive_errors": consecutive_errors
                    })
                
                # Check if too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"Agent {agent_id} exceeded maximum consecutive errors ({max_consecutive_errors})"
                    )
                    raise NonRecoverableError(
                        f"Too many consecutive unexpected errors: {str(e)}",
                        category=ErrorCategory.INTERNAL_ERROR
                    )
                    
                # Brief pause before retrying
                await asyncio.sleep(1)
                
    except Exception as e:
        logger.error(f"Agent {agent_id} terminating due to error: {str(e)}")
        
        # Report terminal error
        if agent_metrics_callback:
            agent_metrics_callback(agent_id, {
                "status": "terminated",
                "error_message": str(e),
                "total_cycles": total_cycles,
                "run_time": time.time() - start_time
            })
        
        # Re-raise to be handled by the TaskGroup
        raise
        
    finally:
        # Always perform cleanup
        logger.info(f"Cleaning up agent {agent_id}")
        try:
            if hasattr(agent, 'cleanup') and callable(agent.cleanup):
                await agent.cleanup()
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup of agent {agent_id}: {str(cleanup_error)}")
            
        # Report final metrics
        if agent_metrics_callback:
            agent_metrics_callback(agent_id, {
                "status": "shutdown" if shutdown_event.is_set() else "completed",
                "total_cycles": total_cycles,
                "run_time": time.time() - start_time,
                "clean_exit": shutdown_event.is_set() or consecutive_errors == 0
            })


async def create_agent_task(
    agent_factory_func: Callable[..., BaseAgent],
    agent_config: Dict[str, Any],
    shutdown_event: asyncio.Event,
    metrics_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    **kwargs
) -> Tuple[str, asyncio.Task]:
    """
    Factory function to create a properly configured agent task.
    
    Args:
        agent_factory_func: Function that creates an agent
        agent_config: Configuration for the agent
        shutdown_event: Event that signals when to shut down
        metrics_callback: Callback for reporting agent metrics
        **kwargs: Additional arguments for agent creation
        
    Returns:
        Tuple of (agent_id, task)
    """
    # Create the agent
    agent = agent_factory_func(**agent_config, **kwargs)
    agent_id = getattr(agent, 'agent_id', 'unknown')
    
    # Create and return the task
    task = asyncio.create_task(
        execute_agent_with_monitoring(
            agent=agent,
            shutdown_event=shutdown_event,
            agent_metrics_callback=metrics_callback
        ),
        name=f"agent:{agent_id}"
    )
    
    return agent_id, task


async def execute_trade_with_risk_check(
    agent: RiskAwareAgent,
    trade_params: Dict[str, Any],
    retry_on_rejection: bool = False,
    max_retries: int = 3,
    backoff_factor: float = 2.0
) -> Dict[str, Any]:
    """
    Execute a trade with proper risk management checks.
    
    This function ensures that trades are approved by the risk management system
    before execution and handles various error conditions.
    
    Args:
        agent: Risk-aware agent instance
        trade_params: Parameters for the trade execution
        retry_on_rejection: Whether to retry if trade is rejected by risk management
        max_retries: Maximum number of retries for recoverable errors
        backoff_factor: Backoff factor for retries
        
    Returns:
        Trade execution results
        
    Raises:
        RiskApprovalError: If trade is rejected by risk management and retry_on_rejection is False
        TradeExecutionError: If execution fails and cannot be recovered
    """
    agent_id = getattr(agent, 'agent_id', 'unknown')
    retry_count = 0
    
    while True:
        try:
            # Check if agent has proper risk approval decorator
            if not hasattr(agent.execute_trade, 'risk_approval_required'):
                logger.warning(f"Agent {agent_id} execute_trade method lacks @require_risk_approval decorator")
            
            # Verify that agent has risk management capabilities
            if not isinstance(agent, RiskAwareAgent):
                raise NonRecoverableError(
                    f"Agent {agent_id} is not a RiskAwareAgent",
                    category=ErrorCategory.INTERNAL_ERROR
                )
            
            # Check risk status before attempting trade
            risk_status = agent.check_risk_status()
            if not risk_status.get('approved', False):
                rejection_reason = risk_status.get('reason', 'Risk check failed')
                logger.warning(f"Risk check failed for agent {agent_id}: {rejection_reason}")
                
                if not retry_on_rejection or retry_count >= max_retries:
                    raise RiskApprovalError(f"Trade rejected: {rejection_reason}")
                
                # Wait before retrying
                backoff_time = backoff_factor ** retry_count
                logger.info(f"Retrying trade after risk rejection in {backoff_time}s")
                await asyncio.sleep(backoff_time)
                retry_count += 1
                continue
            
            # Execute trade with risk approval
            return await agent.execute_trade(**trade_params)
            
        except RecoverableError as e:
            retry_count += 1
            
            if retry_count > max_retries:
                logger.error(f"Maximum retries exceeded for trade execution: {str(e)}")
                raise TradeExecutionError(
                    f"Maximum retries exceeded: {str(e)}",
                    category=e.category if hasattr(e, 'category') else ErrorCategory.UNKNOWN
                )
            
            # Calculate backoff time
            backoff_time = backoff_factor ** (retry_count - 1)
            if hasattr(e, 'retry_after') and e.retry_after is not None:
                backoff_time = e.retry_after
                
            logger.warning(
                f"Recoverable error during trade execution (attempt {retry_count}/{max_retries}): {str(e)}. "
                f"Retrying in {backoff_time}s"
            )
            
            await asyncio.sleep(backoff_time)
            
        except RiskApprovalError:
            # Re-raise without wrapping if retry_on_rejection is False
            if not retry_on_rejection or retry_count >= max_retries:
                raise
                
            # Calculate backoff time for risk approval retries
            retry_count += 1
            backoff_time = backoff_factor ** (retry_count - 1)
            
            logger.warning(
                f"Trade rejected by risk management (attempt {retry_count}/{max_retries}). "
                f"Retrying in {backoff_time}s"
            )
            
            await asyncio.sleep(backoff_time)
            
        except Exception as e:
            # Wrap unexpected errors
            logger.error(f"Unexpected error during trade execution: {str(e)}")
            raise TradeExecutionError(
                f"Trade execution failed: {str(e)}",
                category=ErrorCategory.UNKNOWN
            ) from e 