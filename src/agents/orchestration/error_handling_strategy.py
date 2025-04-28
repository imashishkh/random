"""
Error Handling Strategies for Async Agent Orchestration

This module provides strategies for handling different types of errors 
that may occur during agent execution.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Type, Union, Awaitable

from .error_handling import (
    BaseAgentError, 
    ErrorCategory, 
    ExponentialBackoff,
    is_error_recoverable
)

logger = logging.getLogger(__name__)


class ErrorHandlingStrategy:
    """
    Base class for error handling strategies.
    
    An error handling strategy defines how to respond to 
    different types of errors during agent execution.
    """
    
    async def handle_error(
        self, 
        error: Exception, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle an error that occurred during agent execution.
        
        Args:
            error: The exception that was raised
            context: Context information about the error
            
        Returns:
            Dictionary with handling results and metadata
        """
        raise NotImplementedError("Subclasses must implement this method")
        
    def can_handle(self, error: Exception) -> bool:
        """
        Check if this strategy can handle the given error.
        
        Args:
            error: The exception to check
            
        Returns:
            True if this strategy can handle the error, False otherwise
        """
        return True


class RetryStrategy(ErrorHandlingStrategy):
    """
    Strategy that retries the operation after a delay.
    
    This strategy is useful for transient errors that may resolve
    with a simple retry after some time.
    """
    
    def __init__(
        self, 
        max_retries: int = 3,
        backoff_strategy: Optional[ExponentialBackoff] = None,
        retryable_categories: Optional[list[ErrorCategory]] = None
    ):
        """
        Initialize the retry strategy.
        
        Args:
            max_retries: Maximum number of retry attempts
            backoff_strategy: Strategy for calculating retry delays
            retryable_categories: Error categories this strategy can handle
        """
        self.max_retries = max_retries
        self.backoff_strategy = backoff_strategy or ExponentialBackoff()
        
        # Default retryable categories if none provided
        self.retryable_categories = retryable_categories or [
            ErrorCategory.TRANSIENT_NETWORK,
            ErrorCategory.EXCHANGE_RATE_LIMIT,
            ErrorCategory.MARKET_DATA_UNAVAILABLE
        ]
        
    def can_handle(self, error: Exception) -> bool:
        """
        Check if this strategy can handle the given error.
        
        Args:
            error: The exception to check
            
        Returns:
            True if error is recoverable and within retryable categories
        """
        # First check if error is generally recoverable
        if not is_error_recoverable(error):
            return False
            
        # Check if error category is in retryable categories
        if isinstance(error, BaseAgentError):
            return error.category in self.retryable_categories
            
        # For regular exceptions, categorize and check
        from .error_handling import categorize_error
        category = categorize_error(error)
        return category in self.retryable_categories
        
    async def handle_error(
        self, 
        error: Exception, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle an error by scheduling a retry after a delay.
        
        Args:
            error: The exception that was raised
            context: Context information about the error
            
        Returns:
            Dictionary with handling results and metadata
        """
        attempt = context.get("attempt", 1)
        
        if attempt > self.max_retries:
            return {
                "action": "abort",
                "message": f"Maximum retry attempts ({self.max_retries}) exceeded",
                "retry_exhausted": True,
                "original_error": error
            }
        
        # Calculate delay based on retry attempt
        delay = self.backoff_strategy.delay(attempt)
        
        # Override with explicit retry_after if provided
        if hasattr(error, "retry_after") and error.retry_after is not None:
            delay = error.retry_after
            
        logger.info(
            f"Scheduling retry attempt {attempt}/{self.max_retries} after {delay:.2f}s delay: {str(error)}"
        )
        
        # Wait for the delay
        await asyncio.sleep(delay)
        
        return {
            "action": "retry",
            "message": f"Retrying after attempt {attempt} (delay: {delay:.2f}s)",
            "attempt": attempt + 1,
            "delay": delay,
            "original_error": error
        }


class FallbackStrategy(ErrorHandlingStrategy):
    """
    Strategy that invokes a fallback handler when an error occurs.
    
    This strategy allows switching to an alternative approach when
    the primary method fails.
    """
    
    def __init__(
        self, 
        fallback_handler: Callable[[Exception, Dict[str, Any]], Awaitable[Any]],
        applicable_categories: Optional[list[ErrorCategory]] = None
    ):
        """
        Initialize the fallback strategy.
        
        Args:
            fallback_handler: Async function to call for fallback handling
            applicable_categories: Error categories this strategy can handle
        """
        self.fallback_handler = fallback_handler
        
        # Define categories this strategy applies to
        self.applicable_categories = applicable_categories or [
            ErrorCategory.INTERNAL_ERROR,
            ErrorCategory.MARKET_DATA_UNAVAILABLE,
            ErrorCategory.EXCHANGE_RATE_LIMIT
        ]
        
    def can_handle(self, error: Exception) -> bool:
        """
        Check if this strategy can handle the given error.
        
        Args:
            error: The exception to check
            
        Returns:
            True if error category is applicable for fallback
        """
        if isinstance(error, BaseAgentError):
            return error.category in self.applicable_categories
            
        # For regular exceptions, categorize and check
        from .error_handling import categorize_error
        category = categorize_error(error)
        return category in self.applicable_categories
        
    async def handle_error(
        self, 
        error: Exception, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle an error by invoking the fallback handler.
        
        Args:
            error: The exception that was raised
            context: Context information about the error
            
        Returns:
            Dictionary with handling results and metadata
        """
        logger.info(f"Invoking fallback handler for error: {str(error)}")
        
        try:
            result = await self.fallback_handler(error, context)
            
            return {
                "action": "fallback_complete",
                "message": "Fallback handler executed successfully",
                "fallback_result": result,
                "original_error": error
            }
        except Exception as fallback_error:
            logger.error(f"Fallback handler failed: {str(fallback_error)}")
            
            return {
                "action": "fallback_failed",
                "message": f"Fallback handler failed: {str(fallback_error)}",
                "fallback_error": fallback_error,
                "original_error": error
            }


class CompositeStrategy(ErrorHandlingStrategy):
    """
    Strategy that combines multiple strategies with priority ordering.
    
    This strategy tries each sub-strategy in order until one succeeds
    or all fail.
    """
    
    def __init__(self, strategies: list[ErrorHandlingStrategy]):
        """
        Initialize the composite strategy.
        
        Args:
            strategies: List of strategies to try in order
        """
        self.strategies = strategies
        
    def can_handle(self, error: Exception) -> bool:
        """
        Check if any sub-strategy can handle the given error.
        
        Args:
            error: The exception to check
            
        Returns:
            True if any sub-strategy can handle the error
        """
        return any(strategy.can_handle(error) for strategy in self.strategies)
        
    async def handle_error(
        self, 
        error: Exception, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle an error by trying each sub-strategy in order.
        
        Args:
            error: The exception that was raised
            context: Context information about the error
            
        Returns:
            Dictionary with handling results and metadata
        """
        for i, strategy in enumerate(self.strategies):
            if not strategy.can_handle(error):
                continue
                
            logger.debug(f"Trying error handling strategy {i+1}/{len(self.strategies)}: {strategy.__class__.__name__}")
            
            try:
                result = await strategy.handle_error(error, context)
                
                # If the strategy succeeded or explicitly returned an action, return it
                if result.get("action") != "continue":
                    return result
            except Exception as strategy_error:
                logger.error(f"Error in handling strategy {strategy.__class__.__name__}: {str(strategy_error)}")
                # Continue to the next strategy
        
        # If all strategies failed or returned "continue", return a default result
        return {
            "action": "unhandled",
            "message": "All error handling strategies failed or declined to handle",
            "original_error": error
        }


class LogAndContinueStrategy(ErrorHandlingStrategy):
    """
    Strategy that logs the error and allows execution to continue.
    
    This strategy is useful for non-critical errors that shouldn't
    interrupt the overall process.
    """
    
    def __init__(
        self, 
        log_level: int = logging.WARNING,
        applicable_categories: Optional[list[ErrorCategory]] = None
    ):
        """
        Initialize the log and continue strategy.
        
        Args:
            log_level: Logging level for error messages
            applicable_categories: Error categories this strategy can handle
        """
        self.log_level = log_level
        
        # Define categories this strategy applies to
        self.applicable_categories = applicable_categories or [
            ErrorCategory.MARKET_DATA_UNAVAILABLE,
            ErrorCategory.UNKNOWN
        ]
        
    def can_handle(self, error: Exception) -> bool:
        """
        Check if this strategy can handle the given error.
        
        Args:
            error: The exception to check
            
        Returns:
            True if error category is applicable
        """
        if isinstance(error, BaseAgentError):
            return error.category in self.applicable_categories
            
        # For regular exceptions, categorize and check
        from .error_handling import categorize_error
        category = categorize_error(error)
        return category in self.applicable_categories
        
    async def handle_error(
        self, 
        error: Exception, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle an error by logging it and allowing execution to continue.
        
        Args:
            error: The exception that was raised
            context: Context information about the error
            
        Returns:
            Dictionary with handling results and metadata
        """
        error_message = f"Non-critical error occurred: {str(error)}"
        
        # Log with the specified level
        logger.log(self.log_level, error_message)
        
        if "agent_id" in context:
            logger.log(self.log_level, f"Agent {context['agent_id']} continuing despite error")
        
        return {
            "action": "continue",
            "message": error_message,
            "original_error": error
        }


class ErrorHandlingStrategyFactory:
    """Factory for creating error handling strategies based on configuration."""
    
    @staticmethod
    def create_strategy(strategy_type: str, **kwargs) -> ErrorHandlingStrategy:
        """
        Create an error handling strategy of the specified type.
        
        Args:
            strategy_type: Type of strategy to create
            **kwargs: Additional parameters for the strategy
            
        Returns:
            Configured error handling strategy
            
        Raises:
            ValueError: If strategy type is unknown
        """
        if strategy_type == "retry":
            return RetryStrategy(**kwargs)
        elif strategy_type == "fallback":
            return FallbackStrategy(**kwargs)
        elif strategy_type == "log_and_continue":
            return LogAndContinueStrategy(**kwargs)
        elif strategy_type == "composite":
            # For composite, we need to create the sub-strategies
            sub_strategies = []
            for sub_config in kwargs.get("strategies", []):
                sub_type = sub_config.pop("type")
                sub_strategy = ErrorHandlingStrategyFactory.create_strategy(sub_type, **sub_config)
                sub_strategies.append(sub_strategy)
            
            return CompositeStrategy(sub_strategies)
        else:
            raise ValueError(f"Unknown error handling strategy type: {strategy_type}")
    
    @staticmethod
    def create_default_strategy() -> ErrorHandlingStrategy:
        """
        Create a default error handling strategy with sensible defaults.
        
        Returns:
            Default composite error handling strategy
        """
        # Create a composite strategy with retry, fallback, and log-and-continue
        return CompositeStrategy([
            RetryStrategy(max_retries=3),
            LogAndContinueStrategy()
        ]) 