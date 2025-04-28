"""
Exposure and Risk Dashboard for the Trading System

This module provides real-time monitoring of exposure levels and circuit breaker status
through a terminal-based dashboard.
"""

import logging
import time
import threading
from typing import Dict, List, Any, Optional
import os
from datetime import datetime
from tabulate import tabulate

from .risk.exposure_manager import (
    ExposureManager, 
    Observer, 
    CircuitBreakerState
)

logger = logging.getLogger(__name__)


class ExposureDashboard(Observer):
    """
    Terminal-based dashboard for monitoring exposure levels and circuit breaker status.
    
    Implements the Observer pattern to receive updates when exposure levels change
    or circuit breakers are triggered.
    """
    
    def __init__(self, exposure_manager: ExposureManager, update_interval_seconds: int = 5):
        """
        Initialize the exposure dashboard.
        
        Args:
            exposure_manager: The exposure manager to monitor
            update_interval_seconds: How often to update the dashboard
        """
        self.exposure_manager = exposure_manager
        self.update_interval_seconds = update_interval_seconds
        
        # Register as an observer with the exposure manager
        exposure_manager.attach(self)
        
        # Dashboard state
        self._running = False
        self._update_thread = None
        self._last_update = None
        self._circuit_breaker_events: List[Dict[str, Any]] = []
        self._max_events = 10  # Maximum number of events to track
        
    def start(self) -> None:
        """Start the dashboard update thread."""
        if self._running:
            return
            
        self._running = True
        self._update_thread = threading.Thread(target=self._update_loop)
        self._update_thread.daemon = True
        self._update_thread.start()
        
        logger.info("Exposure dashboard started")
        
    def stop(self) -> None:
        """Stop the dashboard update thread."""
        self._running = False
        
        if self._update_thread:
            self._update_thread.join(timeout=2.0)
            
        logger.info("Exposure dashboard stopped")
        
    def _update_loop(self) -> None:
        """Main update loop for the dashboard."""
        while self._running:
            try:
                self.update_display()
                time.sleep(self.update_interval_seconds)
            except Exception as e:
                logger.error(f"Error updating exposure dashboard: {str(e)}", exc_info=True)
                time.sleep(1.0)  # Shorter interval on error
                
    def update_display(self) -> None:
        """Update the terminal display with current information."""
        # Clear the terminal
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Get current data
        exposure_summary = self.exposure_manager.get_exposure_summary()
        active_breakers = self.exposure_manager.get_active_circuit_breakers()
        
        # Display header
        print("\n===== TRADING SYSTEM EXPOSURE DASHBOARD =====")
        print(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Display overall exposure
        total_percent = exposure_summary["total_exposure_percent"] * 100
        print(f"\nTotal Exposure: ${exposure_summary['total_exposure']:.2f} ({total_percent:.2f}%)")
        
        # Display asset exposure
        asset_exposure = []
        for symbol, amount in exposure_summary["asset_exposure"].items():
            percent = exposure_summary["asset_exposure_percent"][symbol] * 100
            asset_exposure.append([symbol, f"${amount:.2f}", f"{percent:.2f}%"])
            
        if asset_exposure:
            print("\nAsset Exposure:")
            print(tabulate(asset_exposure, headers=["Symbol", "Amount", "Percent"], tablefmt="simple"))
        
        # Display sector exposure
        sector_exposure = []
        for sector, amount in exposure_summary["sector_exposure"].items():
            percent = exposure_summary["sector_exposure_percent"][sector] * 100
            sector_exposure.append([sector, f"${amount:.2f}", f"{percent:.2f}%"])
            
        if sector_exposure:
            print("\nSector Exposure:")
            print(tabulate(sector_exposure, headers=["Sector", "Amount", "Percent"], tablefmt="simple"))
        
        # Display strategy exposure
        strategy_exposure = []
        for strategy, amount in exposure_summary["strategy_exposure"].items():
            percent = exposure_summary["strategy_exposure_percent"][strategy] * 100
            strategy_exposure.append([strategy, f"${amount:.2f}", f"{percent:.2f}%"])
            
        if strategy_exposure:
            print("\nStrategy Exposure:")
            print(tabulate(strategy_exposure, headers=["Strategy", "Amount", "Percent"], tablefmt="simple"))
        
        # Display active circuit breakers
        if active_breakers:
            print("\nActive Circuit Breakers:")
            breaker_data = []
            for name, breaker in active_breakers.items():
                trigger_time = breaker["last_trigger_time"].strftime("%H:%M:%S") if breaker["last_trigger_time"] else "N/A"
                breaker_data.append([
                    name, 
                    breaker["state"].upper(), 
                    breaker["trigger_type"],
                    trigger_time,
                    ", ".join(breaker["applies_to"][:3]) + ("..." if len(breaker["applies_to"]) > 3 else "")
                ])
                
            print(tabulate(breaker_data, 
                           headers=["Name", "State", "Trigger Type", "Trigger Time", "Applies To"],
                           tablefmt="simple"))
        
        # Display recent circuit breaker events
        if self._circuit_breaker_events:
            print("\nRecent Circuit Breaker Events:")
            event_data = []
            for event in self._circuit_breaker_events:
                timestamp = event["timestamp"].strftime("%H:%M:%S")
                event_data.append([
                    event["name"],
                    event["event"].upper(),
                    timestamp,
                    event["trigger_type"]
                ])
                
            print(tabulate(event_data, 
                           headers=["Name", "Event", "Time", "Type"],
                           tablefmt="simple"))
        
        self._last_update = datetime.now()
        
    def update(self, subject: Any, data: Dict[str, Any] = None) -> None:
        """
        Update method for the Observer pattern.
        
        Called when the exposure manager has updates.
        
        Args:
            subject: The subject that changed (the ExposureManager)
            data: Data about the change
        """
        if data and "event" in data:
            # It's a circuit breaker event
            event_copy = data.copy()
            
            # Add timestamp if not present
            if "timestamp" not in event_copy:
                event_copy["timestamp"] = datetime.now()
                
            # Add to the event list
            self._circuit_breaker_events.insert(0, event_copy)
            
            # Trim the list if needed
            if len(self._circuit_breaker_events) > self._max_events:
                self._circuit_breaker_events = self._circuit_breaker_events[:self._max_events]
                
            # Force a dashboard update
            self.update_display() 