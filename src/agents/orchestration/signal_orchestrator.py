"""
Signal Orchestrator Module

This module provides the main orchestrator for the Signal Validation and Orchestration System,
which coordinates the validation, filtering, and publishing of trading signals.
"""

import logging
import time
import uuid
from typing import Dict, List, Any, Optional, Set, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from .base_orchestrator import BaseOrchestrator
from .models import TradingSignal, SignalValidationResult, SignalFilteringResult, PublishedSignal, MarketConditions
from .validation.base_validator import BaseSignalValidator
from .validation.statistical_validator import StatisticalValidator
from .filtering.base_filter import BaseSignalFilter
from .api.signal_api import SignalAPI

class SignalOrchestrator(BaseOrchestrator):
    """
    Coordinates the validation, filtering, and publishing of trading signals.
    
    This orchestrator manages the entire signal processing pipeline, from receiving
    raw signals from agents to publishing validated signals for consumption.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the signal orchestrator.
        
        Args:
            config: Configuration dictionary
        """
        super().__init__("signal_orchestrator", config or {})
        
        # Initialize components
        self._initialize_components()
        
        # Signal processing queues
        self.pending_signals: List[TradingSignal] = []
        self.validated_signals: Dict[str, SignalValidationResult] = {}
        self.filtered_signals: Dict[str, SignalFilteringResult] = {}
        self.published_signals: Dict[str, PublishedSignal] = {}
        
        # Market conditions by trading pair
        self.market_conditions: Dict[str, MarketConditions] = {}
        
        # Thread pool for parallel processing
        self.max_workers = self.config.get("max_workers", 10)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Thread lock for thread safety
        self.lock = threading.Lock()
        
        # Processing flags
        self.is_processing = False
        self.should_stop = False
        
        self.logger.info("Signal orchestrator initialized")
    
    def _initialize_components(self) -> None:
        """Initialize validators, filters, and API components."""
        # Initialize validators
        self.validators: List[BaseSignalValidator] = []
        validator_configs = self.config.get("validators", [])
        
        # Add default statistical validator if no validators configured
        if not validator_configs:
            self.validators.append(StatisticalValidator())
            self.logger.info("Added default statistical validator")
        else:
            for validator_config in validator_configs:
                validator_type = validator_config.get("type", "statistical")
                validator_name = validator_config.get("name", f"{validator_type}_validator")
                
                if validator_type == "statistical":
                    validator = StatisticalValidator(validator_name, validator_config)
                    self.validators.append(validator)
                    self.logger.info(f"Added statistical validator: {validator_name}")
                # Add other validator types here as needed
        
        # Initialize filters
        self.filters: List[BaseSignalFilter] = []
        filter_configs = self.config.get("filters", [])
        
        for filter_config in filter_configs:
            filter_type = filter_config.get("type")
            filter_name = filter_config.get("name", f"{filter_type}_filter")
            
            # Dynamically import and initialize filter
            try:
                module_path = f".filtering.{filter_type}_filter"
                module = __import__(module_path, fromlist=[""])
                filter_class = getattr(module, f"{filter_type.title()}Filter")
                
                filter_instance = filter_class(filter_name, filter_config)
                self.filters.append(filter_instance)
                self.logger.info(f"Added filter: {filter_name}")
            except (ImportError, AttributeError) as e:
                self.logger.error(f"Failed to load filter {filter_type}: {str(e)}")
        
        # Initialize API
        api_config = self.config.get("api", {})
        self.api = SignalAPI(api_config)
        self.logger.info("Signal API initialized")
    
    def start(self) -> None:
        """Start the signal orchestrator processing loop."""
        if self.is_processing:
            self.logger.warning("Signal orchestrator is already running")
            return
            
        self.should_stop = False
        self.is_processing = True
        
        # Start processing in a separate thread
        self.processing_thread = threading.Thread(target=self._processing_loop)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
        self.logger.info("Signal orchestrator started")
    
    def stop(self) -> None:
        """Stop the signal orchestrator processing loop."""
        if not self.is_processing:
            self.logger.warning("Signal orchestrator is not running")
            return
            
        self.should_stop = True
        self.processing_thread.join(timeout=5.0)
        self.is_processing = False
        
        self.logger.info("Signal orchestrator stopped")
    
    def _processing_loop(self) -> None:
        """Main processing loop that runs in a separate thread."""
        try:
            while not self.should_stop:
                # Process any pending signals
                self._process_pending_signals()
                
                # Short sleep to avoid excessive CPU usage
                time.sleep(0.1)
        except Exception as e:
            self.logger.error(f"Error in processing loop: {str(e)}")
            self.is_processing = False
    
    def _process_pending_signals(self) -> None:
        """Process all pending signals."""
        with self.lock:
            if not self.pending_signals:
                return
                
            signals_to_process = self.pending_signals.copy()
            self.pending_signals = []
        
        # Process signals in parallel
        futures = {}
        for signal in signals_to_process:
            futures[self.executor.submit(self._process_signal, signal)] = signal
        
        # Wait for all to complete
        for future in as_completed(futures):
            signal = futures[future]
            try:
                future.result()
            except Exception as e:
                self.logger.error(f"Error processing signal {signal.id}: {str(e)}")
    
    def _process_signal(self, signal: TradingSignal) -> None:
        """
        Process a single signal through the validation and filtering pipeline.
        
        Args:
            signal: Trading signal to process
        """
        # Record start time for performance tracking
        start_time = time.time()
        
        # 1. Validate signal
        validation_result = self._validate_signal(signal)
        
        # Only proceed if signal is valid
        if validation_result.is_valid:
            # 2. Filter signal
            filtering_result = self._filter_signal(signal)
            
            # Only publish if signal is not filtered out
            if not filtering_result.is_filtered_out:
                # 3. Publish signal
                self._publish_signal(signal, validation_result, filtering_result)
        
        # Record performance metrics
        processing_time = time.time() - start_time
        with self.lock:
            self.performance_metrics["signals_processed"] += 1
            self.performance_metrics["avg_processing_time"] = (
                (self.performance_metrics["avg_processing_time"] * 
                 (self.performance_metrics["signals_processed"] - 1) +
                 processing_time) / self.performance_metrics["signals_processed"]
            )
        
        # Emit event
        self.emit_event("signal_processed", {
            "signal_id": signal.id,
            "trading_pair": signal.trading_pair,
            "processing_time": processing_time,
            "validated": validation_result.is_valid,
            "filtered": False if not validation_result.is_valid else filtering_result.is_filtered_out,
            "published": (validation_result.is_valid and not filtering_result.is_filtered_out)
        })
    
    def _validate_signal(self, signal: TradingSignal) -> SignalValidationResult:
        """
        Validate a signal using all validators.
        
        Args:
            signal: Trading signal to validate
            
        Returns:
            SignalValidationResult indicating whether the signal is valid
        """
        # Get market conditions for the trading pair
        market_conditions = self.market_conditions.get(signal.trading_pair)
        
        # Start with a passing validation
        combined_confidence = 0.0
        validation_threshold = 0.0
        is_valid = True
        
        # Apply all validators
        for validator in self.validators:
            try:
                # Pass market conditions to validator if available
                result = validator.validate(signal)
                
                # Track result
                with self.lock:
                    self.validated_signals[signal.id] = result
                
                # Combine confidence (average)
                combined_confidence += result.confidence
                validation_threshold += result.threshold
                
                # If any validator rejects, the signal is invalid
                if not result.is_valid:
                    is_valid = False
            except Exception as e:
                self.logger.error(f"Error in validator {validator.name}: {str(e)}")
                is_valid = False  # Fail safe on error
        
        # Average the confidence and threshold
        if self.validators:
            combined_confidence /= len(self.validators)
            validation_threshold /= len(self.validators)
        
        # Create combined result
        result = SignalValidationResult(
            signal_id=signal.id,
            is_valid=is_valid,
            confidence=combined_confidence,
            threshold=validation_threshold,
            validator_name="combined"
        )
        
        # Log result
        if is_valid:
            self.logger.info(f"Signal {signal.id} validated with combined confidence {combined_confidence:.2f}")
        else:
            self.logger.info(f"Signal {signal.id} rejected with combined confidence {combined_confidence:.2f}")
        
        return result
    
    def _filter_signal(self, signal: TradingSignal) -> SignalFilteringResult:
        """
        Filter a signal using all filters.
        
        Args:
            signal: Trading signal to filter
            
        Returns:
            SignalFilteringResult indicating whether the signal is filtered out
        """
        # Get market conditions for the trading pair
        market_conditions = self.market_conditions.get(signal.trading_pair)
        
        # If no filters, don't filter anything
        if not self.filters:
            result = SignalFilteringResult(
                signal_id=signal.id,
                is_filtered_out=False,
                confidence=1.0,
                threshold=0.5,
                filter_name="none"
            )
            
            with self.lock:
                self.filtered_signals[signal.id] = result
                
            return result
        
        # Apply all filters
        is_filtered_out = False
        combined_confidence = 0.0
        filtering_threshold = 0.0
        filter_reasons = []
        
        for filter_instance in self.filters:
            try:
                # Pass market conditions to filter if available
                result = filter_instance.filter_signal(
                    signal, market_conditions
                )
                
                # Combine confidence (average)
                combined_confidence += result.confidence
                filtering_threshold += result.threshold
                
                # If any filter says to filter out, the signal is filtered
                if result.is_filtered_out:
                    is_filtered_out = True
                    filter_reasons.append(
                        f"{filter_instance.name}: {result.filter_reason}"
                    )
            except Exception as e:
                self.logger.error(f"Error in filter {filter_instance.name}: {str(e)}")
                is_filtered_out = True  # Fail safe on error
                filter_reasons.append(f"Error in {filter_instance.name}")
        
        # Average the confidence and threshold
        combined_confidence /= len(self.filters)
        filtering_threshold /= len(self.filters)
        
        # Create combined result
        result = SignalFilteringResult(
            signal_id=signal.id,
            is_filtered_out=is_filtered_out,
            confidence=combined_confidence,
            threshold=filtering_threshold,
            filter_name="combined",
            filter_reason="; ".join(filter_reasons) if filter_reasons else None
        )
        
        # Store result
        with self.lock:
            self.filtered_signals[signal.id] = result
        
        # Log result
        if is_filtered_out:
            self.logger.info(
                f"Signal {signal.id} filtered out: {result.filter_reason}"
            )
        else:
            self.logger.info(f"Signal {signal.id} passed filtering")
        
        return result
    
    def _publish_signal(self, signal: TradingSignal, 
                       validation_result: SignalValidationResult,
                       filtering_result: SignalFilteringResult) -> None:
        """
        Publish a validated and filtered signal.
        
        Args:
            signal: Trading signal to publish
            validation_result: Validation result for the signal
            filtering_result: Filtering result for the signal
        """
        # Create a published signal
        published_signal = PublishedSignal(
            id=str(uuid.uuid4()),
            original_signal_id=signal.id,
            trading_pair=signal.trading_pair,
            timestamp=signal.created_at,
            direction=signal.direction,
            timeframe=signal.timeframe,
            strength=signal.strength,
            confidence=validation_result.confidence,
            signal_type=signal.signal_type,
            metadata={
                "agent_id": signal.agent_id,
                "validation_confidence": validation_result.confidence,
                "filtering_confidence": filtering_result.confidence,
                "original_confidence": signal.confidence
            }
        )
        
        # Store published signal
        with self.lock:
            self.published_signals[published_signal.id] = published_signal
        
        # Publish to API
        try:
            self.api.handle_published_signal(published_signal)
            self.logger.info(f"Published signal {published_signal.id} for {signal.trading_pair}")
        except Exception as e:
            self.logger.error(f"Error publishing signal {published_signal.id}: {str(e)}")
    
    def add_signal(self, signal: TradingSignal) -> None:
        """
        Add a signal to the processing queue.
        
        Args:
            signal: Trading signal to process
        """
        with self.lock:
            self.pending_signals.append(signal)
            self.performance_metrics["signals_received"] += 1
        
        self.logger.info(f"Received signal {signal.id} for {signal.trading_pair}")
        
        # Emit event
        self.emit_event("signal_received", {
            "signal_id": signal.id,
            "trading_pair": signal.trading_pair,
            "agent_id": signal.agent_id,
            "signal_type": signal.signal_type,
            "direction": signal.direction
        })
    
    def update_market_conditions(self, conditions: MarketConditions) -> None:
        """
        Update market conditions for a trading pair.
        
        Args:
            conditions: New market conditions
        """
        with self.lock:
            self.market_conditions[conditions.trading_pair] = conditions
        
        self.logger.info(f"Updated market conditions for {conditions.trading_pair}: {conditions.regime}")
    
    def get_published_signals(self, trading_pair: Optional[str] = None, 
                            limit: int = 100) -> List[PublishedSignal]:
        """
        Get recently published signals.
        
        Args:
            trading_pair: Optional trading pair to filter by
            limit: Maximum number of signals to return
            
        Returns:
            List of published signals
        """
        with self.lock:
            signals = list(self.published_signals.values())
            
        # Filter by trading pair if specified
        if trading_pair:
            signals = [s for s in signals if s.trading_pair == trading_pair]
        
        # Sort by timestamp (newest first) and limit
        signals.sort(key=lambda s: s.timestamp, reverse=True)
        return signals[:limit]
    
    def get_validation_result(self, signal_id: str) -> Optional[SignalValidationResult]:
        """
        Get validation result for a signal.
        
        Args:
            signal_id: ID of the signal
            
        Returns:
            ValidationResult or None if not found
        """
        with self.lock:
            return self.validated_signals.get(signal_id)
    
    def get_filtering_result(self, signal_id: str) -> Optional[SignalFilteringResult]:
        """
        Get filtering result for a signal.
        
        Args:
            signal_id: ID of the signal
            
        Returns:
            FilteringResult or None if not found
        """
        with self.lock:
            return self.filtered_signals.get(signal_id)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for the orchestrator.
        
        Returns:
            Dictionary of performance metrics
        """
        metrics = super().get_performance_metrics()
        
        with self.lock:
            # Add additional metrics
            metrics.update({
                "pending_signals_count": len(self.pending_signals),
                "validated_signals_count": len(self.validated_signals),
                "filtered_signals_count": len(self.filtered_signals),
                "published_signals_count": len(self.published_signals),
                "max_workers": self.max_workers,
                "is_processing": self.is_processing
            })
            
            # Add validator metrics
            validator_metrics = {}
            for validator in self.validators:
                validator_metrics[validator.name] = validator.get_performance_metrics()
            metrics["validators"] = validator_metrics
            
            # Add filter metrics
            filter_metrics = {}
            for filter_instance in self.filters:
                filter_metrics[filter_instance.name] = filter_instance.get_performance_metrics()
            metrics["filters"] = filter_metrics
        
        return metrics
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the orchestrator to a dictionary.
        
        Returns:
            Dictionary representation of the orchestrator
        """
        base_dict = super().to_dict()
        
        # Add additional fields
        base_dict.update({
            "validators_count": len(self.validators),
            "filters_count": len(self.filters),
            "pending_signals_count": len(self.pending_signals),
            "validated_signals_count": len(self.validated_signals),
            "filtered_signals_count": len(self.filtered_signals),
            "published_signals_count": len(self.published_signals),
            "market_conditions_count": len(self.market_conditions),
            "is_processing": self.is_processing
        })
        
        return base_dict
