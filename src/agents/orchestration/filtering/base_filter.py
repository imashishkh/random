"""
Base Filter Module

This module contains the BaseFilter class, which serves as the foundation
for all signal filter implementations.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

from ..models import TradingSignal, SignalFilteringResult, MarketConditions

class BaseFilter(ABC):
    """
    Base class for all signal filters.
    
    Signal filters are responsible for identifying and removing false positive
    signals based on various criteria.
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize the filter.
        
        Args:
            name: Unique identifier for this filter
            config: Configuration dictionary with filter settings
        """
        self.name = name
        self.config = config
        
        # Performance metrics
        self.performance_metrics = {
            "total_signals_processed": 0,
            "signals_filtered_out": 0,
            "processing_time_ms": 0,
            "avg_processing_time_ms": 0
        }
        
        # Configure logging
        self.logger = self._configure_logging()
        self.logger.info("Filter '%s' initialized", self.name)
        
    def _configure_logging(self) -> logging.Logger:
        """Configure logging for this filter."""
        logger = logging.getLogger(f"filter.{self.name}")
        
        # Set log level from config
        log_level = self.config.get("log_level", "INFO").upper()
        logger.setLevel(getattr(logging, log_level))
        
        return logger
        
    def filter(self, signal: TradingSignal, 
              market_conditions: Optional[MarketConditions] = None) -> SignalFilteringResult:
        """
        Filter a trading signal.
        
        This method wraps the specific filtering logic with performance tracking,
        error handling, and metadata collection.
        
        Args:
            signal: The trading signal to filter
            market_conditions: Current market conditions (optional)
            
        Returns:
            SignalFilteringResult indicating whether the signal was filtered out
        """
        # Performance tracking
        start_time = time.time()
        
        try:
            # Call the specific filtering implementation
            result = self._filter_signal(signal, market_conditions)
            
            # Update performance metrics
            self.performance_metrics["total_signals_processed"] += 1
            if result.is_filtered_out:
                self.performance_metrics["signals_filtered_out"] += 1
            
            # Log filtering decision
            if result.is_filtered_out:
                self.logger.info("Filtered out signal %s (confidence: %.2f, threshold: %.2f)",
                               signal.id, result.confidence, result.threshold)
            else:
                self.logger.debug("Signal %s passed filtering (confidence: %.2f, threshold: %.2f)",
                                signal.id, result.confidence, result.threshold)
                
            return result
            
        except Exception as e:
            # Log the error
            self.logger.error("Error filtering signal %s: %s", signal.id, str(e), exc_info=True)
            
            # Default to not filtering the signal in case of errors
            return SignalFilteringResult(
                signal_id=signal.id,
                is_filtered_out=False,
                confidence=0.0,
                threshold=self.config.get("threshold", 0.5)
            )
            
        finally:
            # Update timing metrics
            end_time = time.time()
            processing_time_ms = (end_time - start_time) * 1000
            
            # Update the metrics
            self.performance_metrics["processing_time_ms"] += processing_time_ms
            
            total_processed = self.performance_metrics["total_signals_processed"]
            if total_processed > 0:
                self.performance_metrics["avg_processing_time_ms"] = (
                    self.performance_metrics["processing_time_ms"] / total_processed
                )
        
    @abstractmethod
    def _filter_signal(self, signal: TradingSignal,
                      market_conditions: Optional[MarketConditions] = None) -> SignalFilteringResult:
        """
        Implementation-specific signal filtering logic.
        
        Args:
            signal: The trading signal to filter
            market_conditions: Current market conditions (optional)
            
        Returns:
            SignalFilteringResult indicating whether the signal was filtered out
        """
        pass
        
    def update_threshold(self, new_threshold: float) -> None:
        """
        Update the filtering threshold.
        
        Args:
            new_threshold: New threshold value (between 0 and 1)
        """
        # Validate threshold value
        if not 0 <= new_threshold <= 1:
            self.logger.warning("Invalid threshold value %.2f, must be between 0 and 1", new_threshold)
            return
            
        # Update the threshold in the config
        self.config["threshold"] = new_threshold
        self.logger.info("Updated threshold to %.2f", new_threshold)
        
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """
        Update the filter configuration.
        
        Args:
            new_config: New configuration values
        """
        # Update the configuration
        self.config.update(new_config)
        self.logger.info("Updated filter configuration")
        
        # Reconfigure logging if log level changed
        if "log_level" in new_config:
            self.logger = self._configure_logging()
            
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get the filter's performance metrics.
        
        Returns:
            Dictionary of performance metrics
        """
        return self.performance_metrics.copy()
        
    def reset_performance_metrics(self) -> None:
        """Reset all performance metrics to zero."""
        for key in self.performance_metrics:
            self.performance_metrics[key] = 0
            
        self.logger.info("Reset performance metrics") 