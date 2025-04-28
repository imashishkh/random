"""
Agent Shutdown Protocol Integration Example

This module demonstrates how to properly integrate agent classes with the
three-phase shutdown protocol, including registration, dependency management,
and graceful shutdown for different types of agents.
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, List, Optional, Any

from .base_agent import BaseAgentCore, BaseAgent, AgentState
from .shutdown_coordinator import get_shutdown_coordinator
from ..utils.logging.logger import get_logger

logger = get_logger()


class TechnicalAnalysisAgent(BaseAgentCore):
    """Example implementation of a technical analysis agent with proper shutdown protocol."""
    
    def __init__(self, agent_id: str, indicators: List[str]):
        """
        Initialize a technical analysis agent.
        
        Args:
            agent_id: Unique identifier for this agent
            indicators: List of technical indicators to track
        """
        super().__init__(agent_id=agent_id, agent_type="technical_analysis")
        self.indicators = indicators
        self._background_tasks = []
        self._is_running = False
        
        # Initialize with idle state
        self.state = AgentState.IDLE
    
    def _get_shutdown_priority(self) -> int:
        """Technical agents have medium priority (shutdown before execution agents)."""
        return 50
    
    async def start(self) -> bool:
        """Start the technical analysis processing."""
        if self.is_running():
            logger.warning(f"Agent {self.agent_id} already running")
            return True
        
        logger.info(f"Starting technical analysis agent {self.agent_id} with indicators: {self.indicators}")
        
        # Start background tasks to monitor indicators
        for indicator in self.indicators:
            task = asyncio.create_task(self._monitor_indicator(indicator))
            self._background_tasks.append(task)
        
        self._is_running = True
        self.state = AgentState.RUNNING
        return True
    
    async def _monitor_indicator(self, indicator: str) -> None:
        """Background task to monitor a technical indicator."""
        try:
            while self._is_running and not self._is_shutting_down:
                logger.debug(f"Agent {self.agent_id} monitoring indicator: {indicator}")
                # Simulate indicator calculation
                await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            logger.debug(f"Indicator monitoring for {indicator} cancelled")
        except Exception as e:
            logger.error(f"Error monitoring indicator {indicator}: {str(e)}")
    
    async def prepare_shutdown(self) -> None:
        """
        Prepare for shutdown - phase 1.
        
        For technical agents, this involves:
        - Finishing current indicator calculations
        - Saving current indicator values
        """
        await super().prepare_shutdown()
        
        logger.info(f"Technical agent {self.agent_id} preparing for shutdown")
        
        # Simulate saving indicator states
        logger.info(f"Saving indicator states for agent {self.agent_id}")
        await asyncio.sleep(0.5)  # Simulate state saving
    
    async def stop(self) -> bool:
        """
        Stop processing - phase 2.
        
        For technical agents, this involves:
        - Stopping all background indicator monitoring tasks
        """
        if not self._is_running:
            return True
        
        logger.info(f"Stopping technical agent {self.agent_id}")
        
        # Set state to stopping to prevent new operations
        self.state = AgentState.STOPPING
        self._is_running = False
        
        # Cancel all background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for all tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self._background_tasks = []
        self.state = AgentState.STOPPED
        
        return True
    
    async def cleanup(self) -> None:
        """
        Clean up resources - phase 3.
        
        For technical agents, this involves:
        - Releasing any shared resources
        - Clearing indicator data structures
        """
        logger.info(f"Cleaning up technical agent {self.agent_id}")
        
        # Simulate resource cleanup
        await asyncio.sleep(0.2)
        
        # Clean up indicator data
        self.indicators = []
        
        await super().cleanup()


class ExecutionAgent(BaseAgentCore):
    """Example implementation of an execution agent with proper shutdown protocol."""
    
    def __init__(self, agent_id: str, technical_agent_ids: List[str]):
        """
        Initialize an execution agent.
        
        Args:
            agent_id: Unique identifier for this agent
            technical_agent_ids: IDs of technical agents this agent depends on
        """
        super().__init__(agent_id=agent_id, agent_type="execution")
        self.technical_agent_ids = technical_agent_ids
        self._execution_task = None
        self._is_running = False
        
        # Initialize with idle state
        self.state = AgentState.IDLE
    
    def _get_shutdown_priority(self) -> int:
        """Execution agents have high priority (shutdown first)."""
        return 100
    
    def _get_shutdown_dependencies(self) -> List[str]:
        """Execution agents depend on technical agents."""
        return self.technical_agent_ids
    
    async def start(self) -> bool:
        """Start the execution agent."""
        if self.is_running():
            logger.warning(f"Agent {self.agent_id} already running")
            return True
        
        logger.info(f"Starting execution agent {self.agent_id}")
        
        # Start the main execution loop
        self._execution_task = asyncio.create_task(self._execution_loop())
        self._is_running = True
        self.state = AgentState.RUNNING
        
        return True
    
    async def _execution_loop(self) -> None:
        """Main execution loop."""
        try:
            while self._is_running and not self._is_shutting_down:
                logger.debug(f"Execution agent {self.agent_id} running execution loop")
                # Simulate execution logic
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            logger.debug(f"Execution loop cancelled for agent {self.agent_id}")
        except Exception as e:
            logger.error(f"Error in execution loop for agent {self.agent_id}: {str(e)}")
            self.state = AgentState.ERROR
    
    async def prepare_shutdown(self) -> None:
        """
        Prepare for shutdown - phase 1.
        
        For execution agents, this involves:
        - Finishing current trades
        - Ensuring no open positions remain
        """
        await super().prepare_shutdown()
        
        logger.info(f"Execution agent {self.agent_id} preparing for shutdown")
        
        # Simulate closing open positions
        logger.info(f"Closing open positions for agent {self.agent_id}")
        await asyncio.sleep(1.0)  # Simulate position closing
    
    async def stop(self) -> bool:
        """
        Stop processing - phase 2.
        
        For execution agents, this involves:
        - Stopping the execution loop
        - Cancelling any pending orders
        """
        if not self._is_running:
            return True
        
        logger.info(f"Stopping execution agent {self.agent_id}")
        
        # Set state to stopping to prevent new operations
        self.state = AgentState.STOPPING
        self._is_running = False
        
        # Cancel execution task
        if self._execution_task and not self._execution_task.done():
            self._execution_task.cancel()
            try:
                await self._execution_task
            except asyncio.CancelledError:
                pass
        
        self._execution_task = None
        self.state = AgentState.STOPPED
        
        return True
    
    async def cleanup(self) -> None:
        """
        Clean up resources - phase 3.
        
        For execution agents, this involves:
        - Releasing any shared resources
        - Closing API connections
        """
        logger.info(f"Cleaning up execution agent {self.agent_id}")
        
        # Simulate resource cleanup
        await asyncio.sleep(0.5)
        
        await super().cleanup()


class ShutdownManager:
    """
    Example manager that sets up signal handlers and demonstrates the shutdown process.
    """
    
    def __init__(self):
        """Initialize the shutdown manager."""
        self.coordinator = get_shutdown_coordinator()
        self._shutdown_requested = False
        self._agents: Dict[str, BaseAgentCore] = {}
    
    def register_agent(self, agent: BaseAgentCore) -> None:
        """
        Register an agent with the shutdown manager.
        
        Args:
            agent: Agent to register
        """
        self._agents[agent.agent_id] = agent
    
    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._signal_handler)
        
        logger.info("Signal handlers for graceful shutdown registered")
    
    def _signal_handler(self, sig, frame) -> None:
        """
        Handle signals for graceful shutdown.
        
        Args:
            sig: Signal number
            frame: Current stack frame
        """
        if self._shutdown_requested:
            logger.warning("Forced exit requested, terminating immediately")
            sys.exit(1)
        
        self._shutdown_requested = True
        logger.info(f"Shutdown signal received ({sig}), initiating graceful shutdown")
        
        # Schedule the shutdown in the event loop
        asyncio.create_task(self._shutdown())
    
    async def _shutdown(self) -> None:
        """Perform graceful shutdown of all agents."""
        logger.info("Starting graceful shutdown of all agents")
        
        # Initialize the shutdown process
        self.coordinator.initialize_shutdown(reason="Signal received")
        
        # Shut down all agents
        success = await self.coordinator.shutdown_all_agents(force=False)
        
        if success:
            logger.info("All agents shut down successfully")
        else:
            logger.warning("Some agents failed to shut down cleanly")
        
        # Exit the application
        sys.exit(0)
    
    async def emergency_shutdown(self) -> None:
        """Perform emergency shutdown with minimal timeouts."""
        logger.warning("Initiating emergency shutdown")
        
        await self.coordinator.emergency_shutdown(reason="Emergency shutdown requested")
        
        # Exit the application
        sys.exit(1)


async def run_example() -> None:
    """Run the shutdown protocol integration example."""
    # Set up shutdown manager
    shutdown_mgr = ShutdownManager()
    shutdown_mgr.setup_signal_handlers()
    
    # Create and start technical agents
    tech_agent1 = TechnicalAnalysisAgent("tech1", ["RSI", "MACD"])
    tech_agent2 = TechnicalAnalysisAgent("tech2", ["Bollinger", "ATR"])
    
    # Register with shutdown manager
    shutdown_mgr.register_agent(tech_agent1)
    shutdown_mgr.register_agent(tech_agent2)
    
    # Start technical agents
    await tech_agent1.start()
    await tech_agent2.start()
    
    # Create and start execution agent that depends on technical agents
    exec_agent = ExecutionAgent("exec1", ["tech1", "tech2"])
    shutdown_mgr.register_agent(exec_agent)
    await exec_agent.start()
    
    logger.info("All agents started successfully")
    
    # Run for a while to demonstrate normal operation
    logger.info("System running normally. Press Ctrl+C to initiate graceful shutdown")
    try:
        while True:
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        # This will be triggered by the signal handler
        pass


if __name__ == "__main__":
    asyncio.run(run_example()) 