"""
Agent Health Monitoring Example

This script demonstrates the agent health monitoring and recovery system by:
1. Creating several agents
2. Simulating agent successes and failures
3. Triggering agent recovery
4. Displaying health metrics
"""

import time
import random
import signal
import sys
import threading
from typing import List, Dict, Any

from ..agents.base_agent import BaseAgent
from ..agents.factory import AgentFactory
from ..agents.health import get_health_monitor, AgentHealthStatus
from ..utils.logging.logger import get_logger

logger = get_logger()

# Global variable to control the example
running = True

def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully shut down the example"""
    global running
    logger.info("Stopping example...")
    running = False
    sys.exit(0)

def create_test_agents(count: int = 3) -> List[BaseAgent]:
    """Create test agents for the example"""
    agents = []
    
    # Create a researcher agent
    researcher = AgentFactory.create_researcher(
        agent_name="Test Researcher",
        model_name="gpt-3.5-turbo",
        verbose=True
    )
    agents.append(researcher)
    
    # Create a planner agent
    planner = AgentFactory.create_planner(
        agent_name="Test Planner",
        planning_framework="agile",
        model_name="gpt-3.5-turbo",
        verbose=True
    )
    agents.append(planner)
    
    # Create an executor agent
    executor = AgentFactory.create_executor(
        agent_name="Test Executor",
        execution_mode="standard",
        model_name="gpt-3.5-turbo",
        verbose=True
    )
    agents.append(executor)
    
    # Create additional agents if needed
    for i in range(count - 3):
        if i % 3 == 0:
            agent = AgentFactory.create_researcher(
                agent_name=f"Researcher {i}",
                model_name="gpt-3.5-turbo"
            )
        elif i % 3 == 1:
            agent = AgentFactory.create_planner(
                agent_name=f"Planner {i}",
                model_name="gpt-3.5-turbo"
            )
        else:
            agent = AgentFactory.create_executor(
                agent_name=f"Executor {i}",
                model_name="gpt-3.5-turbo"
            )
        agents.append(agent)
    
    logger.info(f"Created {len(agents)} test agents")
    return agents

class AgentSimulator:
    """
    Simulates agent activities including successes and failures.
    """
    
    def __init__(self, agents: List[BaseAgent]):
        """
        Initialize the simulator with a list of agents.
        
        Args:
            agents: List of agents to simulate
        """
        self.agents = agents
        self.health_monitor = get_health_monitor()
        self.simulation_thread = None
        self.running = False
        
        # Configure failure probabilities and patterns
        self.agent_success_rates: Dict[str, float] = {}
        for agent in agents:
            # Random success rate between 70% and 95%
            self.agent_success_rates[agent.agent_id] = random.uniform(0.70, 0.95)
    
    def start_simulation(self) -> None:
        """Start the agent simulation"""
        if self.running:
            logger.warning("Simulation is already running")
            return
        
        self.running = True
        self.simulation_thread = threading.Thread(target=self._simulation_loop)
        self.simulation_thread.daemon = True
        self.simulation_thread.start()
        logger.info("Started agent simulation")
    
    def stop_simulation(self) -> None:
        """Stop the agent simulation"""
        if not self.running:
            logger.warning("Simulation is not running")
            return
        
        self.running = False
        if self.simulation_thread:
            self.simulation_thread.join(timeout=5.0)
        logger.info("Stopped agent simulation")
    
    def _simulation_loop(self) -> None:
        """Main simulation loop"""
        while self.running:
            try:
                # Select a random agent
                agent = random.choice(self.agents)
                agent_id = agent.agent_id
                
                # Decide success or failure based on the agent's success rate
                if random.random() < self.agent_success_rates[agent_id]:
                    # Simulate successful execution
                    logger.info(f"Simulating successful execution for agent {agent.agent_name} ({agent_id})")
                    response_time = random.uniform(0.5, 3.0)  # Random response time between 0.5 and 3 seconds
                    self.health_monitor.record_agent_success(agent_id, response_time)
                else:
                    # Simulate failure
                    logger.info(f"Simulating failure for agent {agent.agent_name} ({agent_id})")
                    error = random.choice([
                        "Timeout error",
                        "API rate limit exceeded",
                        "Network connection error",
                        "Resource unavailable",
                        "LLM returned malformed response"
                    ])
                    self.health_monitor.record_agent_failure(agent_id, error)
                
                # Sleep for a random interval (1-5 seconds)
                time.sleep(random.uniform(1.0, 5.0))
            except Exception as e:
                logger.error(f"Error in simulation loop: {str(e)}")
                time.sleep(1.0)  # Sleep briefly before retrying
    
    def display_health_dashboard(self) -> None:
        """Display a simple health dashboard for all agents"""
        print("\n=== AGENT HEALTH DASHBOARD ===")
        print(f"{'AGENT ID':<36} | {'AGENT NAME':<25} | {'STATUS':<10} | {'FAILURES':<8} | {'RECOVERY':<7}")
        print("-" * 100)
        
        # Get all metrics
        all_metrics = self.health_monitor.get_all_health_metrics()
        
        for agent in self.agents:
            agent_id = agent.agent_id
            metrics = all_metrics.get(agent_id, {})
            
            status = metrics.get("status", "unknown")
            failures = metrics.get("consecutive_failures", 0)
            recovery = metrics.get("recovery_attempts", 0)
            
            # Format status with color (using ANSI escape codes)
            if status == AgentHealthStatus.HEALTHY.value:
                status_display = "\033[92m" + status + "\033[0m"  # Green
            elif status == AgentHealthStatus.DEGRADED.value:
                status_display = "\033[93m" + status + "\033[0m"  # Yellow
            elif status == AgentHealthStatus.FAILED.value:
                status_display = "\033[91m" + status + "\033[0m"  # Red
            elif status == AgentHealthStatus.RECOVERING.value:
                status_display = "\033[94m" + status + "\033[0m"  # Blue
            else:
                status_display = status
            
            print(f"{agent_id:<36} | {agent.agent_name:<25} | {status_display:<10} | {failures:<8} | {recovery:<7}")
        
        print("\n")
    
    def force_agent_failure(self, agent_index: int, consecutive_failures: int = 5) -> None:
        """
        Force an agent to fail multiple times consecutively to trigger recovery.
        
        Args:
            agent_index: Index of the agent in the agents list
            consecutive_failures: Number of consecutive failures to simulate
        """
        if agent_index >= len(self.agents):
            logger.error(f"Invalid agent index: {agent_index}, max index is {len(self.agents) - 1}")
            return
        
        agent = self.agents[agent_index]
        agent_id = agent.agent_id
        
        logger.info(f"Forcing {consecutive_failures} consecutive failures for agent {agent.agent_name} ({agent_id})")
        
        for i in range(consecutive_failures):
            error = f"Simulated critical failure {i+1}/{consecutive_failures}"
            self.health_monitor.record_agent_failure(agent_id, error)
            time.sleep(0.5)  # Short delay between failures
        
        logger.info(f"Completed simulated failures for agent {agent.agent_name} ({agent_id})")


def main():
    """Main function for the agent health monitoring example"""
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Starting agent health monitoring example")
    
    # Create test agents
    agents = create_test_agents(count=5)
    
    # Start health monitoring
    health_monitor = get_health_monitor()
    health_monitor.start_monitoring()
    
    # Create and start simulator
    simulator = AgentSimulator(agents)
    simulator.start_simulation()
    
    try:
        logger.info("Running simulation. Press Ctrl+C to stop.")
        
        # Run for a while to generate some metrics
        for i in range(5):
            time.sleep(10)
            simulator.display_health_dashboard()
        
        # Force failures for the first agent to trigger recovery
        simulator.force_agent_failure(0, consecutive_failures=6)
        
        # Wait to see recovery in action
        for i in range(3):
            time.sleep(5)
            simulator.display_health_dashboard()
        
        # Force failures for another agent
        simulator.force_agent_failure(1, consecutive_failures=6)
        
        # Final status display
        for i in range(2):
            time.sleep(5)
            simulator.display_health_dashboard()
        
    except Exception as e:
        logger.error(f"Error in example: {str(e)}")
    finally:
        # Clean up
        simulator.stop_simulation()
        health_monitor.stop_monitoring()
        logger.info("Example completed")

if __name__ == "__main__":
    main() 