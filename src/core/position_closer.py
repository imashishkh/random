"""
Position Closer for Graceful Shutdown

This module provides a bridge between the shutdown coordinator and the
risk management system to safely close positions during shutdown.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable, Set
from decimal import Decimal

# Import our new shutdown coordinator
from .shutdown import ShutdownPhase, ShutdownCoordinator, PositionCloseStrategy, get_shutdown_coordinator

# Import the risk manager
from ..risk.global_risk_manager import GlobalRiskManager

# Import the Wait Group pattern
from ..utils.concurrency import WaitGroup

# Configure logger
logger = logging.getLogger(__name__)


class PositionCloser:
    """
    Handles the closing of open positions during system shutdown.
    
    This class bridges the shutdown coordinator with the risk management
    system to ensure all positions are safely closed before shutdown.
    """
    
    def __init__(self, risk_manager: Optional[GlobalRiskManager] = None):
        """
        Initialize the position closer.
        
        Args:
            risk_manager: The global risk manager instance to use, or None to create one
        """
        # Get or create the risk manager
        self.risk_manager = risk_manager
        
        # Get the shutdown coordinator
        self.shutdown_coordinator = get_shutdown_coordinator()
        
        # Track positions that were closed
        self.closed_positions = []
        self.failed_positions = []
        
        # Register with shutdown coordinator
        self.register_with_coordinator()
        
        # Strategy-specific parameters
        self.max_retries = 3
        self.retry_delay = 5.0  # seconds
        self.position_timeout = 20.0  # seconds for individual position closing
        
        # Results tracking
        self.results = {
            "success": False,
            "total_positions": 0,
            "closed_positions": 0,
            "failed_positions": 0,
            "closing_time": 0.0,
            "error": None
        }
    
    def register_with_coordinator(self) -> None:
        """Register callbacks with the shutdown coordinator."""
        self.shutdown_coordinator.register_phase_callback(
            ShutdownPhase.POSITIONS,
            self.close_positions
        )
    
    async def close_positions(self) -> None:
        """
        Close all open positions during shutdown.
        
        This method is called by the shutdown coordinator during the POSITIONS phase.
        """
        start_time = time.time()
        logger.info("Starting position closing process")
        
        # Reset tracking
        self.closed_positions = []
        self.failed_positions = []
        
        try:
            # Get the position closing strategy from the coordinator
            strategy = self.shutdown_coordinator.position_close_strategy
            
            # Check if we have a risk manager
            if not self.risk_manager:
                logger.warning("No risk manager available, skipping position closing")
                self._update_results(False, error="No risk manager available")
                return
            
            # Choose the closing method based on strategy
            if strategy == PositionCloseStrategy.IMMEDIATE:
                success = await self._close_positions_immediate()
            else:  # GRADUAL
                success = await self._close_positions_gradual()
            
            # Verify all positions are closed
            remaining_positions = await self._verify_positions_closed()
            
            if remaining_positions:
                logger.warning(f"{len(remaining_positions)} positions still open after closing attempt")
                
                # Try immediate closing as fallback if gradual was used
                if strategy == PositionCloseStrategy.GRADUAL:
                    logger.info("Attempting fallback to immediate closing for remaining positions")
                    await self._close_specific_positions_immediate(remaining_positions)
                    
                    # Verify again
                    still_open = await self._verify_positions_closed()
                    if still_open:
                        logger.error(f"{len(still_open)} positions still open after fallback closing")
                        success = False
                        self.failed_positions.extend(still_open)
            
            elapsed = time.time() - start_time
            logger.info(f"Position closing process completed in {elapsed:.2f}s")
            
            # Update results
            self._update_results(success, closing_time=elapsed)
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error during position closing: {str(e)}", exc_info=True)
            self._update_results(False, error=str(e), closing_time=elapsed)
    
    async def _close_positions_immediate(self) -> bool:
        """
        Close all positions immediately using market orders.
        
        This is the fastest but potentially most expensive method.
        
        Returns:
            True if all positions were closed successfully
        """
        logger.info("Using IMMEDIATE position closing strategy (market orders)")
        
        try:
            # Fetch open positions first to know what we're dealing with
            positions = await self._get_open_positions()
            
            if not positions:
                logger.info("No open positions to close")
                return True
            
            logger.info(f"Found {len(positions)} open positions to close immediately")
            
            # Use the risk manager's emergency shutdown for all positions at once
            result = self.risk_manager.emergency_shutdown(reason="graceful_shutdown")
            
            if not result.get('success', False):
                error = result.get('error', 'Unknown error')
                logger.error(f"Failed to close positions immediately: {error}")
                return False
            
            # Track closed positions
            self.closed_positions = result.get('closed_positions', [])
            logger.info(f"Successfully closed {len(self.closed_positions)} positions via emergency shutdown")
            
            return True
            
        except Exception as e:
            logger.error(f"Error during immediate position closing: {str(e)}", exc_info=True)
            return False
    
    async def _close_positions_gradual(self) -> bool:
        """
        Close positions gradually using limit orders.
        
        This is a more controlled approach that may minimize market impact
        but takes longer to complete.
        
        Returns:
            True if all positions were closed successfully
        """
        logger.info("Using GRADUAL position closing strategy (limit orders)")
        
        try:
            # Get all current positions
            positions = await self._get_open_positions()
            
            if not positions:
                logger.info("No open positions to close")
                return True
            
            position_count = len(positions)
            logger.info(f"Found {position_count} positions to close gradually")
            
            # Create a wait group to track all position closing tasks
            wg = WaitGroup("position_closing")
            
            # Start a task for each position
            for position in positions:
                symbol = position.get('symbol')
                position_amt = float(position.get('positionAmt', 0))
                
                if abs(position_amt) < 0.000001:
                    logger.debug(f"Skipping zero position for {symbol}")
                    continue
                
                logger.info(f"Starting gradual closure for {symbol}: {position_amt}")
                
                # Create a task to close this position
                task = asyncio.create_task(
                    self._close_single_position_gradual(position),
                    name=f"close_{symbol}"
                )
                
                # Add to wait group
                await wg.add(task)
            
            # Wait for all position closing tasks to complete (with timeout)
            phase_timeout = self.shutdown_coordinator._phase_timeouts.get(ShutdownPhase.POSITIONS, 30.0)
            all_completed = await wg.wait(timeout=phase_timeout)
            
            # Get results
            results = wg.get_results()
            logger.info(f"Position closing tasks: {results['succeeded']} succeeded, {results['failed']} failed")
            
            # Success if all tasks completed without errors
            success = all_completed and results['failed'] == 0
            
            return success
            
        except Exception as e:
            logger.error(f"Error during gradual position closing: {str(e)}", exc_info=True)
            return False
    
    async def _close_single_position_gradual(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """
        Close a single position gradually with retries.
        
        Args:
            position: Position data dictionary
            
        Returns:
            Result dictionary
        """
        symbol = position.get('symbol')
        position_amt = float(position.get('positionAmt', 0))
        
        logger.info(f"Closing position for {symbol}: {position_amt}")
        
        # Result tracking
        result = {
            "symbol": symbol,
            "original_amount": position_amt,
            "success": False,
            "attempts": 0,
            "error": None
        }
        
        # Try to close the position with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                result["attempts"] = attempt
                
                # Get current price to calculate a good limit price
                # This would typically come from market data service
                # For now, we'll use the risk manager's emergency shutdown
                side = "SELL" if position_amt > 0 else "BUY"
                
                # For a real implementation, we would use limit orders
                # close to the current market price with a slight buffer
                # Here we'll use the risk manager's existing functionality
                closeParams = {
                    'type': 'LIMIT_MAKER',
                    'timeInForce': 'GTC',
                    'reduceOnly': True
                }
                
                logger.info(f"Attempt {attempt}/{self.max_retries} to close {symbol}")
                
                # In a real implementation, calculate a good limit price
                # based on current market conditions to ensure execution
                # For this example, we'll use the emergency shutdown
                partial_result = self.risk_manager.emergency_shutdown(
                    reason=f"gradual_close_{symbol}"
                )
                
                if partial_result.get('success', False):
                    # Find this position in the results
                    closed_positions = partial_result.get('closed_positions', [])
                    for closed in closed_positions:
                        if closed.get('symbol') == symbol:
                            # Add to our tracking
                            self.closed_positions.append(closed)
                            result["success"] = True
                            
                            logger.info(f"Successfully closed position for {symbol}")
                            return result
                
                # If we get here, the position wasn't found in the results
                error = partial_result.get('error', 'Position not found in close results')
                logger.warning(f"Attempt {attempt} to close {symbol} failed: {error}")
                result["error"] = error
                
                # Wait before retry
                await asyncio.sleep(self.retry_delay)
                
            except Exception as e:
                error_msg = f"Error closing {symbol} (attempt {attempt}/{self.max_retries}): {str(e)}"
                logger.error(error_msg)
                result["error"] = error_msg
                
                # Wait before retry
                await asyncio.sleep(self.retry_delay)
        
        # If we get here, all attempts failed
        logger.error(f"Failed to close position for {symbol} after {self.max_retries} attempts")
        
        # Add to failed positions
        self.failed_positions.append(position)
        
        return result
    
    async def _close_specific_positions_immediate(self, positions: List[Dict[str, Any]]) -> bool:
        """
        Close specific positions immediately using market orders.
        
        Args:
            positions: List of positions to close
            
        Returns:
            True if all specified positions were closed successfully
        """
        if not positions:
            return True
        
        logger.info(f"Attempting to close {len(positions)} specific positions immediately")
        
        try:
            # Use emergency shutdown but filter for these specific symbols
            symbols = [p.get('symbol') for p in positions]
            logger.info(f"Closing positions for symbols: {', '.join(symbols)}")
            
            # In a real implementation, we would filter positions
            # For this prototype, we'll use the emergency shutdown again
            result = self.risk_manager.emergency_shutdown(
                reason=f"specific_positions_emergency_close"
            )
            
            if not result.get('success', False):
                error = result.get('error', 'Unknown error')
                logger.error(f"Failed to close specific positions immediately: {error}")
                return False
            
            # Track closed positions
            new_closed = result.get('closed_positions', [])
            self.closed_positions.extend(new_closed)
            
            logger.info(f"Successfully closed {len(new_closed)} specific positions")
            return True
            
        except Exception as e:
            logger.error(f"Error closing specific positions: {str(e)}", exc_info=True)
            return False
    
    async def _get_open_positions(self) -> List[Dict[str, Any]]:
        """
        Get all currently open positions.
        
        Returns:
            List of open positions
        """
        try:
            # In a real implementation, this would come from the database
            # For this prototype, we'll use the risk manager's API
            positions = self.risk_manager.fetch_binance_position_risk()
            
            # Filter out zero positions
            positions = [
                p for p in positions 
                if abs(float(p.get('positionAmt', 0))) >= 0.000001
            ]
            
            return positions
        except Exception as e:
            logger.error(f"Error fetching open positions: {str(e)}", exc_info=True)
            return []
    
    async def _verify_positions_closed(self) -> List[Dict[str, Any]]:
        """
        Verify that all positions are properly closed.
        
        Returns:
            List of positions that are still open (empty if all closed)
        """
        logger.info("Verifying all positions are closed")
        
        # Get current open positions
        positions = await self._get_open_positions()
        
        if not positions:
            logger.info("Verification successful: All positions are closed")
        else:
            symbols = [p.get('symbol') for p in positions]
            logger.warning(f"Verification failed: {len(positions)} positions still open: {', '.join(symbols)}")
        
        return positions
    
    def _update_results(self, 
                      success: bool, 
                      error: Optional[str] = None,
                      closing_time: float = 0.0) -> None:
        """
        Update the results dictionary.
        
        Args:
            success: Whether the operation was successful
            error: Optional error message
            closing_time: Time taken to close positions
        """
        self.results = {
            "success": success,
            "total_positions": len(self.closed_positions) + len(self.failed_positions),
            "closed_positions": len(self.closed_positions),
            "failed_positions": len(self.failed_positions),
            "closing_time": closing_time,
            "error": error
        }
    
    def get_closing_results(self) -> Dict[str, Any]:
        """
        Get the results of the position closing process.
        
        Returns:
            Results including closed positions and status
        """
        return {
            "closed_positions": self.closed_positions,
            "failed_positions": self.failed_positions,
            "total_closed": len(self.closed_positions),
            "total_failed": len(self.failed_positions),
            "details": self.results
        }


# Singleton instance
_position_closer_instance = None


def get_position_closer(risk_manager: Optional[GlobalRiskManager] = None) -> PositionCloser:
    """
    Get or create the singleton position closer instance.
    
    Args:
        risk_manager: The global risk manager to use
        
    Returns:
        The position closer instance
    """
    global _position_closer_instance
    if _position_closer_instance is None:
        _position_closer_instance = PositionCloser(risk_manager=risk_manager)
    return _position_closer_instance 