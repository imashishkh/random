"""
Health Monitoring System Example

This script demonstrates the agent health monitoring system with:
1. Watchdog and heartbeat monitoring
2. Circuit breaker protection
3. Automatic recovery from failures
4. Early warning through anomaly detection
5. Forex-specific health monitoring

Run this script to see the health monitoring system in action.
"""

import time
import random
import signal
import sys
import threading
import logging
from typing import Dict, Any, List

from ..agents.health_monitoring import (
    get_health_client,
    HealthStatus,
    get_circuit_breaker_registry,
    get_anomaly_detector
)
from ..utils.logging.logger import get_logger

logger = get_logger()

# Global to control the example
running = True

def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully shut down the example"""
    global running
    logger.info("Stopping example...")
    running = False
    sys.exit(0)


class ForexAgentSimulator:
    """
    Simulates a forex trading agent for health monitoring demonstration.
    Generates random health metrics, occasional failures, and anomalies.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        market_pairs: List[str],
        normal_latency_range: tuple = (50, 150),
        normal_error_rate: float = 0.05,
        simulate_anomalies: bool = True
    ):
        """
        Initialize the forex agent simulator.
        
        Args:
            agent_id: Unique identifier for this agent
            agent_type: Type of agent (e.g., 'trader', 'analyzer')
            market_pairs: List of market pairs this agent trades
            normal_latency_range: Normal range for trade latency in ms
            normal_error_rate: Normal error rate for operations
            simulate_anomalies: Whether to simulate anomalies
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.market_pairs = market_pairs
        self.normal_latency_range = normal_latency_range
        self.normal_error_rate = normal_error_rate
        self.simulate_anomalies = simulate_anomalies
        
        # Get health client for this agent
        self.health_client = get_health_client(
            agent_id=agent_id,
            agent_type=agent_type,
            enable_forex_metrics=True,
            market_pairs=market_pairs
        )
        
        # Get circuit breaker registry
        self.circuit_registry = get_circuit_breaker_registry()
        
        # Create circuit breakers for each market pair
        self.circuit_breakers = {}
        for pair in market_pairs:
            self.circuit_breakers[pair] = self.circuit_registry.get_or_create(
                f"{agent_id}_{pair}_circuit",
                failure_threshold=5,
                recovery_timeout=30.0
            )
        
        # Simulation thread
        self.simulation_thread = None
        self.running = False
        
        # Anomaly simulation control
        self.simulate_latency_anomaly = False
        self.simulate_memory_leak = False
        self.simulate_market_data_gaps = False
        
        logger.info(f"Created forex agent simulator for {agent_id} ({agent_type})")
    
    def start(self):
        """Start the agent simulation"""
        if self.running:
            logger.warning("Simulator already running")
            return
        
        self.running = True
        
        # Start health client heartbeats
        self.health_client.start_automatic_heartbeats()
        
        # Start simulation thread
        self.simulation_thread = threading.Thread(
            target=self._simulation_loop,
            daemon=True,
            name=f"sim-{self.agent_id}"
        )
        self.simulation_thread.start()
        
        logger.info(f"Started forex agent simulator for {self.agent_id}")
    
    def stop(self):
        """Stop the agent simulation"""
        if not self.running:
            return
        
        self.running = False
        
        # Stop health client heartbeats
        self.health_client.stop_automatic_heartbeats()
        
        # Wait for simulation thread to stop
        if self.simulation_thread:
            self.simulation_thread.join(timeout=2.0)
            
        logger.info(f"Stopped forex agent simulator for {self.agent_id}")
    
    def trigger_anomaly(self, anomaly_type: str, duration_seconds: int = 60):
        """
        Trigger a specific type of anomaly for the specified duration.
        
        Args:
            anomaly_type: Type of anomaly ('latency', 'memory_leak', 'market_data_gaps')
            duration_seconds: How long the anomaly should last
        """
        if not self.simulate_anomalies:
            logger.warning("Anomaly simulation is disabled")
            return
            
        if anomaly_type == 'latency':
            self.simulate_latency_anomaly = True
            logger.info(f"Triggered latency anomaly for {self.agent_id} (duration: {duration_seconds}s)")
        elif anomaly_type == 'memory_leak':
            self.simulate_memory_leak = True
            logger.info(f"Triggered memory leak anomaly for {self.agent_id} (duration: {duration_seconds}s)")
        elif anomaly_type == 'market_data_gaps':
            self.simulate_market_data_gaps = True
            logger.info(f"Triggered market data gaps anomaly for {self.agent_id} (duration: {duration_seconds}s)")
        else:
            logger.warning(f"Unknown anomaly type: {anomaly_type}")
            return
            
        # Schedule anomaly to stop after duration
        def stop_anomaly():
            if anomaly_type == 'latency':
                self.simulate_latency_anomaly = False
            elif anomaly_type == 'memory_leak':
                self.simulate_memory_leak = False
            elif anomaly_type == 'market_data_gaps':
                self.simulate_market_data_gaps = False
            logger.info(f"Stopped {anomaly_type} anomaly for {self.agent_id}")
            
        timer = threading.Timer(duration_seconds, stop_anomaly)
        timer.daemon = True
        timer.start()
    
    def _simulation_loop(self):
        """Main simulation loop for the agent"""
        iteration = 0
        memory_usage = 100  # Starting memory usage in MB
        
        while self.running:
            try:
                iteration += 1
                
                # Simulate trade execution for each market pair
                for pair in self.market_pairs:
                    try:
                        # Determine if this operation will fail
                        will_fail = random.random() < self.normal_error_rate
                        
                        # Simulate trade execution through circuit breaker
                        def execute_trade():
                            # Simulate trade latency
                            if self.simulate_latency_anomaly:
                                # Anomaly: increasing latency
                                latency = random.uniform(
                                    self.normal_latency_range[1],
                                    self.normal_latency_range[1] + iteration * 10
                                )
                            else:
                                # Normal latency
                                latency = random.uniform(
                                    self.normal_latency_range[0],
                                    self.normal_latency_range[1]
                                )
                                
                            # Record trade latency
                            self.health_client.record_trade_latency(pair, latency)
                            
                            if will_fail:
                                raise Exception(f"Simulated trade execution failure for {pair}")
                                
                            return {"executed": True, "price": random.uniform(1.0, 2.0)}
                            
                        # Execute through circuit breaker
                        result = self.circuit_breakers[pair].execute(execute_trade)
                        
                        # Report success to health client
                        self.health_client.report_success()
                        
                    except Exception as e:
                        # Report failure to health client
                        self.health_client.report_failure(str(e))
                        
                        # Don't update quote time on failure as this could cause quote staleness
                
                # Simulate receiving market data quotes
                for pair in self.market_pairs:
                    # Skip some quotes if simulating market data gaps
                    if self.simulate_market_data_gaps and random.random() < 0.3:
                        self.health_client.record_market_data_gap(pair)
                        continue
                        
                    # Update quote time
                    self.health_client.update_quote_time(pair)
                
                # Simulate memory usage reporting
                if self.simulate_memory_leak:
                    # Anomaly: memory leak
                    memory_usage += random.uniform(5, 10)
                else:
                    # Normal fluctuation
                    memory_usage += random.uniform(-2, 2)
                    memory_usage = max(100, memory_usage)  # Don't go below minimum
                    
                self.health_client.record_memory_usage(memory_usage)
                
                # Simulate CPU usage
                cpu_usage = random.uniform(10, 30)
                self.health_client.record_cpu_usage(cpu_usage)
                
                # Simulate task queue size
                queue_size = random.randint(1, 10)
                self.health_client.record_task_queue_size(queue_size)
                
                # Sleep between iterations
                sleep_time = random.uniform(0.5, 2.0)
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Error in simulation loop: {str(e)}")
                time.sleep(1.0)


def setup_anomaly_detection():
    """Set up anomaly detection for early warning"""
    detector = get_anomaly_detector()
    
    # Start the detector
    detector.start()
    
    # Register callback for anomaly notifications
    def anomaly_callback(anomaly):
        logger.warning(
            f"[EARLY WARNING] Detected anomaly: {anomaly.pattern_name} "
            f"for agent {anomaly.agent_id} (severity: {anomaly.severity})"
        )
        
    detector.register_callback(anomaly_callback)
    
    return detector


def main():
    """Main function to run the health monitoring example"""
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    # Set up anomaly detection
    anomaly_detector = setup_anomaly_detection()
    
    # Create forex agent simulators
    agents = [
        ForexAgentSimulator(
            agent_id="trader_eur_usd",
            agent_type="forex_trader",
            market_pairs=["EUR/USD", "USD/JPY"],
            normal_latency_range=(30, 120),
            normal_error_rate=0.03
        ),
        ForexAgentSimulator(
            agent_id="trader_gbp_jpy",
            agent_type="forex_trader",
            market_pairs=["GBP/JPY", "GBP/USD"],
            normal_latency_range=(40, 150),
            normal_error_rate=0.04
        ),
        ForexAgentSimulator(
            agent_id="data_collector",
            agent_type="market_data",
            market_pairs=["EUR/USD", "USD/JPY", "GBP/USD", "GBP/JPY"],
            normal_latency_range=(10, 50),
            normal_error_rate=0.02
        )
    ]
    
    # Start all agents
    for agent in agents:
        agent.start()
    
    # Welcome message
    logger.info("=" * 60)
    logger.info("Health Monitoring Example Running")
    logger.info("=" * 60)
    logger.info("This example demonstrates the health monitoring system with:")
    logger.info("1. Heartbeat monitoring")
    logger.info("2. Circuit breaker protection")
    logger.info("3. Early warning through anomaly detection")
    logger.info("4. Forex-specific health monitoring")
    logger.info("\nPress Ctrl+C to stop the example.")
    logger.info("=" * 60)
    
    # Run for a while to collect baseline metrics
    logger.info("\nCollecting baseline metrics for 15 seconds...")
    time.sleep(15)
    
    # Trigger latency anomaly for first agent
    logger.info("\nTRIGGERING ANOMALY: Increasing trade latency for trader_eur_usd")
    agents[0].trigger_anomaly("latency", 30)
    time.sleep(35)  # Wait for anomaly to be detected
    
    # Trigger memory leak for second agent
    logger.info("\nTRIGGERING ANOMALY: Memory leak for trader_gbp_jpy")
    agents[1].trigger_anomaly("memory_leak", 30)
    time.sleep(35)  # Wait for anomaly to be detected
    
    # Trigger market data gaps for data collector
    logger.info("\nTRIGGERING ANOMALY: Market data gaps for data_collector")
    agents[2].trigger_anomaly("market_data_gaps", 30)
    time.sleep(35)  # Wait for anomaly to be detected
    
    # Example complete
    logger.info("\nExample complete. Press Ctrl+C to exit.")
    
    # Wait for Ctrl+C
    while running:
        time.sleep(1)
        
    # Stop all agents
    for agent in agents:
        agent.stop()
    
    # Stop anomaly detector
    anomaly_detector.stop()
    
    logger.info("Health monitoring example stopped.")


if __name__ == "__main__":
    main() 