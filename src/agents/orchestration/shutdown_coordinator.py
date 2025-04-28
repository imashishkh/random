"""
Shutdown Coordinator for Agent Process Management

This module implements a coordinated, multi-stage shutdown process for agent
orchestration with proper position closing and resource cleanup.
"""

import asyncio
import logging
import signal
import time
from typing import Dict, List, Optional, Any, Set, Callable, Awaitable

from .base_agent import BaseAgent
from ...utils.logging.logger import get_logger
from .error_handling import ShutdownError

logger = get_logger()


class ShutdownCoordinator:
    """
    Coordinates the graceful shutdown process for all agents.
    
    This class implements a multi-stage shutdown procedure that ensures
    proper position closing and resource cleanup before agent termination.
    """
    
    def __init__(self):
        """Initialize the shutdown coordinator."""
        self.shutdown_event = asyncio.Event()
        self.shutdown_complete = asyncio.Event()
        self.shutdown_stages = []
        self.agents: Dict[str, BaseAgent] = {}
        self.running_tasks: Set[asyncio.Task] = set()
        self._shutdown_in_progress = False
        self._shutdown_priority = {}
        
        # Define shutdown stages with their handlers
        self.shutdown_stages = [
            self._notify_shutdown,
            self._close_trading_positions,
            self._cancel_pending_orders,
            self._flush_state_to_disk,
            self._terminate_agents
        ]
    
    def register_agent(self, agent_id: str, agent: BaseAgent, shutdown_priority: int = 0) -> None:
        """
        Register an agent with the shutdown coordinator.
        
        Args:
            agent_id: Unique identifier for the agent
            agent: The agent instance
            shutdown_priority: Priority during shutdown (higher values are processed first)
        """
        self.agents[agent_id] = agent
        self._shutdown_priority[agent_id] = shutdown_priority
        logger.debug(f"Agent {agent_id} registered with shutdown coordinator (priority: {shutdown_priority})")
    
    def register_task(self, task: asyncio.Task) -> None:
        """
        Register a task with the shutdown coordinator.
        
        Args:
            task: The task to register
        """
        self.running_tasks.add(task)
    
    def unregister_agent(self, agent_id: str) -> None:
        """
        Unregister an agent from the shutdown coordinator.
        
        Args:
            agent_id: Unique identifier for the agent to unregister
        """
        if agent_id in self.agents:
            self.agents.pop(agent_id)
            self._shutdown_priority.pop(agent_id, None)
            logger.debug(f"Agent {agent_id} unregistered from shutdown coordinator")
    
    def unregister_task(self, task: asyncio.Task) -> None:
        """
        Unregister a task from the shutdown coordinator.
        
        Args:
            task: The task to unregister
        """
        self.running_tasks.discard(task)
    
    async def initiate_shutdown(self, sig: Optional[signal.Signals] = None) -> None:
        """
        Initiate the shutdown process, optionally in response to a signal.
        
        Args:
            sig: The signal that triggered the shutdown, if applicable
        """
        if self._shutdown_in_progress:
            logger.info("Shutdown already in progress, ignoring repeated request")
            return
            
        self._shutdown_in_progress = True
        
        sig_name = signal.Signals(sig).name if sig else "INTERNAL"
        logger.info(f"Initiating graceful shutdown due to {sig_name} signal")
        
        # Set the shutdown event to notify all components
        self.shutdown_event.set()
        
        # Start the shutdown process
        asyncio.create_task(self.execute_shutdown())
    
    async def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for the shutdown process to complete.
        
        Args:
            timeout: Maximum time to wait in seconds (None = wait indefinitely)
            
        Returns:
            True if shutdown completed, False if timeout occurred
        """
        if not self.shutdown_event.is_set():
            return False
            
        try:
            await asyncio.wait_for(self.shutdown_complete.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    async def execute_shutdown(self, timeout: float = 60.0) -> bool:
        """
        Execute the multi-stage shutdown process.
        
        Args:
            timeout: Maximum time for the entire shutdown process in seconds
            
        Returns:
            True if shutdown was clean, False if some tasks were forced to cancel
        """
        if not self.shutdown_event.is_set():
            self.shutdown_event.set()
        
        logger.info(f"Beginning graceful shutdown sequence with {timeout}s timeout")
        overall_start = time.time()
        
        # Calculate per-stage timeout allocation, with position closing getting most time
        stage_timeouts = {}
        total_alloc = 0.0
        
        # Assign default weights to stages
        stage_weights = {
            0: 0.1,  # Notification - 10%
            1: 0.5,  # Position closing - 50%
            2: 0.2,  # Cancel orders - 20%
            3: 0.1,  # State persistence - 10%
            4: 0.1,  # Agent termination - 10%
        }
        
        # Calculate timeouts based on weights
        for i, weight in stage_weights.items():
            stage_timeouts[i] = timeout * weight
            total_alloc += stage_timeouts[i]
        
        # Execute each shutdown stage with its allocated timeout
        all_stages_completed = True
        for i, stage_func in enumerate(self.shutdown_stages):
            stage_name = stage_func.__name__.replace("_", " ")
            stage_timeout = stage_timeouts.get(i, timeout * 0.1)  # Default 10% if not specified
            
            # Check if we've already exceeded total timeout
            elapsed = time.time() - overall_start
            if elapsed >= timeout:
                logger.warning(f"Shutdown timeout exceeded, forcing remaining stages")
                all_stages_completed = False
                break
                
            # Adjust stage timeout if we're running out of time
            remaining = timeout - elapsed
            if stage_timeout > remaining:
                stage_timeout = remaining
                
            logger.info(f"Shutdown stage {i+1}/{len(self.shutdown_stages)}: {stage_name} (timeout: {stage_timeout:.1f}s)")
            try:
                # Execute the stage with a timeout
                success = await asyncio.wait_for(
                    asyncio.shield(stage_func()), 
                    timeout=stage_timeout
                )
                
                if not success:
                    logger.warning(f"Shutdown stage '{stage_name}' completed with warnings")
                    all_stages_completed = False
            except asyncio.TimeoutError:
                logger.error(f"Shutdown stage '{stage_name}' timed out after {stage_timeout:.1f}s")
                all_stages_completed = False
            except Exception as e:
                logger.error(f"Error in shutdown stage '{stage_name}': {str(e)}")
                all_stages_completed = False
        
        # Final cleanup of any remaining tasks
        remaining_tasks = list(self.running_tasks)
        if remaining_tasks:
            logger.warning(f"Forcing cancellation of {len(remaining_tasks)} remaining tasks")
            for task in remaining_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait briefly for cancellations to complete
            try:
                await asyncio.wait(remaining_tasks, timeout=2.0)
            except Exception:
                pass
        
        # Set shutdown complete event
        self.shutdown_complete.set()
        
        logger.info(
            f"Shutdown sequence completed: {'clean' if all_stages_completed else 'forced'}"
        )
        return all_stages_completed
    
    async def _notify_shutdown(self) -> bool:
        """
        Notify all agents about the impending shutdown.
        
        Returns:
            True if all notifications were successful, False otherwise
        """
        notifications_sent = 0
        failures = 0
        
        for agent_id, agent in self.agents.items():
            if hasattr(agent, "notify_shutdown") and callable(agent.notify_shutdown):
                try:
                    await agent.notify_shutdown()
                    notifications_sent += 1
                except Exception as e:
                    logger.warning(f"Failed to notify agent {agent_id} of shutdown: {str(e)}")
                    failures += 1
            else:
                logger.debug(f"Agent {agent_id} does not support shutdown notification")
        
        if self.agents:
            logger.info(
                f"Shutdown notification sent to {notifications_sent}/{len(self.agents)} agents "
                f"({failures} failures)"
            )
            
        return failures == 0
    
    async def _close_trading_positions(self) -> bool:
        """
        Close all open trading positions before shutdown.
        
        Returns:
            True if all positions were closed successfully, False otherwise
        """
        # Find all trading agents
        trading_agents = {}
        
        for agent_id, agent in self.agents.items():
            if hasattr(agent, "close_all_positions") and callable(agent.close_all_positions):
                priority = self._shutdown_priority.get(agent_id, 0)
                trading_agents[agent_id] = (agent, priority)
        
        if not trading_agents:
            logger.info("No trading agents with positions to close")
            return True
        
        logger.info(f"Closing positions for {len(trading_agents)} trading agents")
        
        # Sort agents by priority (higher first)
        prioritized_agents = sorted(
            trading_agents.items(), 
            key=lambda x: x[1][1], 
            reverse=True
        )
        
        # Close positions in parallel with individual timeouts
        position_closing_tasks = []
        
        for agent_id, (agent, priority) in prioritized_agents:
            task = asyncio.create_task(
                self._safely_close_agent_positions(agent_id, agent),
                name=f"close_positions:{agent_id}"
            )
            position_closing_tasks.append(task)
        
        # Wait for all position closing tasks to complete
        if position_closing_tasks:
            results = await asyncio.gather(*position_closing_tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for r in results if r is True)
            error_count = sum(1 for r in results if isinstance(r, Exception) or r is False)
            
            logger.info(
                f"Position closing completed: {success_count} successful, {error_count} failed"
            )
            return error_count == 0
        
        return True
    
    async def _safely_close_agent_positions(self, agent_id: str, agent: BaseAgent) -> bool:
        """
        Safely close positions for a single agent with error handling.
        
        Args:
            agent_id: Agent identifier
            agent: Agent instance
            
        Returns:
            True if positions were closed successfully, False otherwise
        """
        try:
            logger.info(f"Closing positions for agent {agent_id}")
            
            # Use shield to prevent cancellation during critical operation
            result = await asyncio.shield(agent.close_all_positions())
            
            # Check if the result indicates success
            if isinstance(result, dict) and not result.get("success", True):
                logger.warning(
                    f"Agent {agent_id} reported issues with position closing: {result.get('message', 'Unknown error')}"
                )
                return False
                
            logger.info(f"Successfully closed positions for agent {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Error closing positions for agent {agent_id}: {str(e)}")
            return False
    
    async def _cancel_pending_orders(self) -> bool:
        """
        Cancel all pending orders before shutdown.
        
        Returns:
            True if all orders were cancelled successfully, False otherwise
        """
        # Find all agents with cancel_all_orders method
        agents_with_orders = {}
        
        for agent_id, agent in self.agents.items():
            if hasattr(agent, "cancel_all_orders") and callable(agent.cancel_all_orders):
                priority = self._shutdown_priority.get(agent_id, 0)
                agents_with_orders[agent_id] = (agent, priority)
        
        if not agents_with_orders:
            logger.info("No agents with orders to cancel")
            return True
        
        logger.info(f"Cancelling orders for {len(agents_with_orders)} agents")
        
        # Sort agents by priority (higher first)
        prioritized_agents = sorted(
            agents_with_orders.items(), 
            key=lambda x: x[1][1], 
            reverse=True
        )
        
        # Cancel orders in parallel
        cancellation_tasks = []
        
        for agent_id, (agent, priority) in prioritized_agents:
            task = asyncio.create_task(
                self._safely_cancel_agent_orders(agent_id, agent),
                name=f"cancel_orders:{agent_id}"
            )
            cancellation_tasks.append(task)
        
        # Wait for all cancellation tasks to complete
        if cancellation_tasks:
            results = await asyncio.gather(*cancellation_tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for r in results if r is True)
            error_count = sum(1 for r in results if isinstance(r, Exception) or r is False)
            
            logger.info(
                f"Order cancellation completed: {success_count} successful, {error_count} failed"
            )
            return error_count == 0
        
        return True
    
    async def _safely_cancel_agent_orders(self, agent_id: str, agent: BaseAgent) -> bool:
        """
        Safely cancel orders for a single agent with error handling.
        
        Args:
            agent_id: Agent identifier
            agent: Agent instance
            
        Returns:
            True if orders were cancelled successfully, False otherwise
        """
        try:
            logger.info(f"Cancelling orders for agent {agent_id}")
            
            # Use shield to prevent cancellation during critical operation
            result = await asyncio.shield(agent.cancel_all_orders())
            
            # Check if the result indicates success
            if isinstance(result, dict) and not result.get("success", True):
                logger.warning(
                    f"Agent {agent_id} reported issues with order cancellation: {result.get('message', 'Unknown error')}"
                )
                return False
                
            logger.info(f"Successfully cancelled orders for agent {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling orders for agent {agent_id}: {str(e)}")
            return False
    
    async def _flush_state_to_disk(self) -> bool:
        """
        Persist agent states to disk for potential recovery.
        
        Returns:
            True if all state was saved successfully, False otherwise
        """
        # Find all agents with save_state method
        stateful_agents = {}
        
        for agent_id, agent in self.agents.items():
            if hasattr(agent, "save_state") and callable(agent.save_state):
                priority = self._shutdown_priority.get(agent_id, 0)
                stateful_agents[agent_id] = (agent, priority)
        
        if not stateful_agents:
            logger.info("No agents with state to persist")
            return True
        
        logger.info(f"Persisting state for {len(stateful_agents)} agents")
        
        # Sort agents by priority (higher first)
        prioritized_agents = sorted(
            stateful_agents.items(), 
            key=lambda x: x[1][1], 
            reverse=True
        )
        
        # Save state in parallel
        save_tasks = []
        
        for agent_id, (agent, priority) in prioritized_agents:
            task = asyncio.create_task(
                self._safely_save_agent_state(agent_id, agent),
                name=f"save_state:{agent_id}"
            )
            save_tasks.append(task)
        
        # Wait for all save tasks to complete
        if save_tasks:
            results = await asyncio.gather(*save_tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for r in results if r is True)
            error_count = sum(1 for r in results if isinstance(r, Exception) or r is False)
            
            logger.info(
                f"State persistence completed: {success_count} successful, {error_count} failed"
            )
            return error_count == 0
        
        return True
    
    async def _safely_save_agent_state(self, agent_id: str, agent: BaseAgent) -> bool:
        """
        Safely save state for a single agent with error handling.
        
        Args:
            agent_id: Agent identifier
            agent: Agent instance
            
        Returns:
            True if state was saved successfully, False otherwise
        """
        try:
            logger.info(f"Saving state for agent {agent_id}")
            
            # Use shield to prevent cancellation during critical operation
            result = await asyncio.shield(agent.save_state())
            
            # Check if the result indicates success
            if isinstance(result, dict) and not result.get("success", True):
                logger.warning(
                    f"Agent {agent_id} reported issues with state persistence: {result.get('message', 'Unknown error')}"
                )
                return False
                
            logger.info(f"Successfully saved state for agent {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving state for agent {agent_id}: {str(e)}")
            return False
    
    async def _terminate_agents(self) -> bool:
        """
        Terminate all remaining agent tasks.
        
        Returns:
            True if all agents were terminated cleanly, False otherwise
        """
        remaining_tasks = list(self.running_tasks)
        
        if not remaining_tasks:
            logger.info("No agent tasks remaining to terminate")
            return True
        
        logger.info(f"Terminating {len(remaining_tasks)} remaining agent tasks")
        
        # Cancel all remaining tasks
        for task in remaining_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for cancellations to complete
        try:
            done, pending = await asyncio.wait(remaining_tasks, timeout=5.0)
            
            # Check if any tasks are still pending
            if pending:
                logger.warning(f"{len(pending)} agent tasks could not be terminated gracefully")
                return False
        except Exception as e:
            logger.error(f"Error during agent task termination: {str(e)}")
            return False
            
        return True 