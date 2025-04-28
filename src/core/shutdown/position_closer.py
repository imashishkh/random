"""
PositionCloser - Responsible for safely closing open trading positions during shutdown
"""
import asyncio
import enum
import logging
import time
from typing import Dict, List, Optional, Any, Set, Callable

logger = logging.getLogger(__name__)

class PositionCloseStrategy(enum.Enum):
    """Strategy to use when closing positions during shutdown"""
    IMMEDIATE = "IMMEDIATE"  # Close all positions immediately at market price
    GRADUAL = "GRADUAL"  # Close positions gradually to minimize market impact
    NONE = "NONE"  # Don't close positions, just report their status


class Position:
    """
    Simplified representation of a trading position for demonstration.
    In a real system, this would likely come from a trading platform or database.
    """
    def __init__(self, 
                 position_id: str, 
                 symbol: str, 
                 size: float, 
                 entry_price: float,
                 agent_id: Optional[str] = None):
        """
        Initialize a Position object.
        
        Args:
            position_id: Unique identifier for the position
            symbol: Trading symbol (e.g., "EUR/USD")
            size: Size of the position (positive for long, negative for short)
            entry_price: Price at which the position was opened
            agent_id: ID of the agent that owns this position, if applicable
        """
        self.position_id = position_id
        self.symbol = symbol
        self.size = size
        self.entry_price = entry_price
        self.agent_id = agent_id
        self.is_closing = False
        self.close_price = None
        self.close_time = None
        
    def is_long(self) -> bool:
        """Check if this is a long position.
        
        Returns:
            bool: True if long, False if short
        """
        return self.size > 0
        
    def is_short(self) -> bool:
        """Check if this is a short position.
        
        Returns:
            bool: True if short, False if long
        """
        return self.size < 0
        
    def is_closed(self) -> bool:
        """Check if the position is closed.
        
        Returns:
            bool: True if closed, False otherwise
        """
        return self.close_price is not None
        
    def get_info(self) -> Dict[str, Any]:
        """Get position information as a dictionary.
        
        Returns:
            dict: Position information
        """
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "size": self.size,
            "entry_price": self.entry_price,
            "agent_id": self.agent_id,
            "is_closing": self.is_closing,
            "close_price": self.close_price,
            "close_time": self.close_time,
            "direction": "LONG" if self.is_long() else "SHORT"
        }

class PositionCloser:
    """
    Responsible for safely closing open trading positions during shutdown.
    """
    def __init__(self):
        """Initialize the PositionCloser."""
        self._positions: Dict[str, Position] = {}  # position_id -> Position
        self._position_sources: List[Callable[[], List[Position]]] = []
        self._last_close_result: Optional[Dict[str, Any]] = None
        
    def register_position(self, position: Position) -> None:
        """
        Register a position for tracking by the position closer.
        
        Args:
            position: Position object to register
        """
        self._positions[position.position_id] = position
        logger.debug(f"Registered position {position.position_id} ({position.symbol})")
        
    def unregister_position(self, position_id: str) -> bool:
        """
        Unregister a position from tracking.
        
        Args:
            position_id: ID of the position to unregister
            
        Returns:
            bool: True if the position was found and unregistered, False otherwise
        """
        if position_id in self._positions:
            del self._positions[position_id]
            logger.debug(f"Unregistered position {position_id}")
            return True
        return False
        
    def register_position_source(self, source_func: Callable[[], List[Position]]) -> None:
        """
        Register a function that provides positions from an external source.
        
        Args:
            source_func: Function that returns a list of positions
        """
        self._position_sources.append(source_func)
        logger.debug("Registered position source")
        
    def unregister_position_source(self, source_func: Callable[[], List[Position]]) -> bool:
        """
        Unregister a previously registered position source.
        
        Args:
            source_func: The source function to unregister
            
        Returns:
            bool: True if the source was found and unregistered, False otherwise
        """
        if source_func in self._position_sources:
            self._position_sources.remove(source_func)
            logger.debug("Unregistered position source")
            return True
        return False
        
    async def close_all_positions(self, strategy: str = PositionCloseStrategy.GRADUAL) -> bool:
        """
        Close all registered positions using the specified strategy.
        
        Args:
            strategy: Position close strategy (IMMEDIATE, GRADUAL, NONE)
            
        Returns:
            bool: True if all positions were successfully closed, False otherwise
        """
        # First gather all positions from registered sources
        self._fetch_positions_from_sources()
        
        if not self._positions:
            logger.info("No positions to close")
            self._last_close_result = {
                "success": True,
                "total_positions": 0,
                "closed_positions": 0,
                "strategy": strategy,
                "time_taken": 0.0
            }
            return True
            
        start_time = time.time()
        logger.info(f"Starting to close {len(self._positions)} positions using strategy {strategy}")
        
        close_strategy = (
            PositionCloseStrategy.IMMEDIATE 
            if strategy == PositionCloseStrategy.IMMEDIATE.value
            else PositionCloseStrategy.GRADUAL 
            if strategy == PositionCloseStrategy.GRADUAL.value
            else PositionCloseStrategy.NONE
            if strategy == PositionCloseStrategy.NONE.value
            else PositionCloseStrategy(strategy)
        )
        
        if close_strategy == PositionCloseStrategy.NONE:
            # Just log positions without closing them
            for pos_id, pos in self._positions.items():
                logger.info(f"Position {pos_id} ({pos.symbol}): {pos.size} @ {pos.entry_price}")
                
            self._last_close_result = {
                "success": True,
                "total_positions": len(self._positions),
                "closed_positions": 0,
                "skipped_positions": len(self._positions),
                "strategy": strategy,
                "time_taken": time.time() - start_time
            }
            return True
            
        # Create tasks for closing positions
        close_tasks = []
        
        if close_strategy == PositionCloseStrategy.IMMEDIATE:
            # Close all positions at once
            for pos_id, pos in self._positions.items():
                close_tasks.append(self._close_position(pos, immediate=True))
                
            # Wait for all positions to close
            results = await asyncio.gather(*close_tasks, return_exceptions=True)
            
        else:  # GRADUAL
            # Close positions in batches, prioritizing larger positions
            sorted_positions = sorted(
                self._positions.values(),
                key=lambda p: abs(p.size),
                reverse=True  # Largest first
            )
            
            # Close positions in small batches to reduce market impact
            batch_size = max(1, len(sorted_positions) // 3)
            for i in range(0, len(sorted_positions), batch_size):
                batch = sorted_positions[i:i+batch_size]
                batch_tasks = [self._close_position(pos, immediate=False) for pos in batch]
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                # Small delay between batches to reduce market impact
                if i + batch_size < len(sorted_positions):
                    await asyncio.sleep(0.5)
        
        # Check results
        total_positions = len(self._positions)
        closed_positions = sum(1 for pos in self._positions.values() if pos.is_closed())
        success = closed_positions == total_positions
        
        time_taken = time.time() - start_time
        logger.info(f"Position closing completed: {closed_positions}/{total_positions} positions closed "
                    f"in {time_taken:.2f} seconds")
        
        self._last_close_result = {
            "success": success,
            "total_positions": total_positions,
            "closed_positions": closed_positions,
            "failed_positions": total_positions - closed_positions,
            "strategy": strategy,
            "time_taken": time_taken
        }
        
        return success
        
    async def _close_position(self, position: Position, immediate: bool = False) -> bool:
        """
        Close a single position.
        
        Args:
            position: Position to close
            immediate: Whether to close immediately or gradually
            
        Returns:
            bool: True if successfully closed, False otherwise
        """
        if position.is_closed():
            return True
            
        position.is_closing = True
        
        try:
            # This would normally interact with a trading API to close the position
            # For demonstration, we simulate the close
            logger.info(f"Closing position {position.position_id} ({position.symbol}): "
                        f"{position.size} @ {position.entry_price}")
            
            # Simulate API call latency
            await asyncio.sleep(0.1 if immediate else 0.3)
            
            # In a real system, we would get the actual close price from the API
            # For demo purposes, we simulate a close price
            import random
            price_change_percent = random.uniform(-0.001, 0.001)  # ±0.1%
            simulated_close_price = position.entry_price * (1 + price_change_percent)
            
            position.close_price = simulated_close_price
            position.close_time = time.time()
            position.is_closing = False
            
            logger.info(f"Position {position.position_id} closed at {position.close_price}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to close position {position.position_id}: {e}")
            position.is_closing = False
            return False
            
    def _fetch_positions_from_sources(self) -> None:
        """Fetch positions from all registered sources."""
        for source_func in self._position_sources:
            try:
                positions = source_func()
                for pos in positions:
                    if pos.position_id not in self._positions:
                        self._positions[pos.position_id] = pos
                        logger.debug(f"Added position {pos.position_id} from source")
            except Exception as e:
                logger.error(f"Error fetching positions from source: {e}")
                
    def get_positions(self) -> List[Position]:
        """
        Get all registered positions.
        
        Returns:
            List[Position]: All currently registered positions
        """
        return list(self._positions.values())
        
    def get_position(self, position_id: str) -> Optional[Position]:
        """
        Get a specific position by ID.
        
        Args:
            position_id: ID of the position to get
            
        Returns:
            Optional[Position]: The position if found, None otherwise
        """
        return self._positions.get(position_id)
        
    def get_last_close_result(self) -> Optional[Dict[str, Any]]:
        """
        Get the result of the last close_all_positions call.
        
        Returns:
            Optional[Dict[str, Any]]: Result of the last close operation, or None if not called yet
        """
        return self._last_close_result 