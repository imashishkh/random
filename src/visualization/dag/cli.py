"""
Command-line interface for the agent DAG visualization.

This module provides a command-line interface for starting the
agent DAG visualization and connecting it to the agent orchestrator.
"""

import asyncio
import argparse
import logging
import sys
from typing import Optional

from .dag.model import DAGModel
from .dag.app import run_dag_visualization
from .dag.integration import AgentDAGIntegration
from .app import AgentDAGApp
from .demo import demo_dag_visualization
from ...agents.health_monitoring.metrics_collector import MetricsCollector
from ...orchestration.utils import load_orchestrator_config
from ...monitoring.redis_monitor import RedisMessageMonitor

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_arg_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser for the visualization CLI."""
    parser = argparse.ArgumentParser(
        description="Agent DAG Visualization with Performance Monitoring",
        epilog="""
        The visualization provides real-time monitoring of agent performance metrics 
        including health status, response times, memory usage, and more. 
        
        Features:
        - Interactive ASCII graph visualization of agent relationships
        - Real-time performance monitoring with health indicators 
        - Incremental rendering for improved performance
        - Detailed metrics and trend visualization
        - Log monitoring for agent communication
        
        Navigation:
        - Arrow keys to navigate between nodes
        - Enter to select nodes/edges
        - 'D' to toggle details panel
        - 'L' to toggle logs panel
        - 'H' to show help
        """
    )
    
    parser.add_argument(
        "--config",
        help="Path to the orchestrator configuration file"
    )
    
    parser.add_argument(
        "--redis",
        help="Redis connection string for message monitoring (e.g., redis://localhost:6379)"
    )
    
    parser.add_argument(
        "--redis-pattern",
        help="Redis channel pattern to subscribe to (default: agent:*:message)"
    )
    
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with demo data instead of connecting to the orchestrator"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--no-incremental",
        action="store_true",
        help="Disable incremental rendering (use if display issues occur)"
    )
    
    parser.add_argument(
        "--refresh-interval",
        type=float,
        default=2.0,
        help="Minimum interval between metric refreshes in seconds (default: 2.0)"
    )
    
    return parser


async def async_main(args: argparse.Namespace) -> int:
    """
    Main async function for setting up and running the DAG visualization with metrics.
    
    Args:
        args: Command-line arguments
        
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Initialize components based on arguments
    metrics_collector = MetricsCollector()
    redis_monitor = None
    config = None
    
    # Load configuration if provided
    if args.config:
        try:
            config = load_orchestrator_config(args.config)
            logging.info(f"Loaded configuration from {args.config}")
        except Exception as e:
            logging.error(f"Failed to load configuration: {e}")
            return 1
    
    # Set up Redis monitoring if requested
    if args.redis:
        try:
            pattern = args.redis_pattern or "agent:*:message"
            redis_monitor = RedisMessageMonitor(
                redis_url=args.redis,
                channel_pattern=pattern
            )
            logging.info(f"Redis monitoring enabled: {args.redis}, pattern: {pattern}")
        except Exception as e:
            logging.error(f"Failed to set up Redis monitoring: {e}")
            return 1
    
    # Create the DAG model with metrics collector
    dag_model = DAGModel(
        metrics_collector=metrics_collector,
        config=config,
        redis_monitor=redis_monitor,
        use_incremental_rendering=not args.no_incremental,
        refresh_interval=args.refresh_interval
    )
    
    # Create and run the DAG app
    app = AgentDAGApp(dag_model)
    await app.run_async()
    
    # Cleanup
    if redis_monitor:
        await redis_monitor.stop()
    
    return 0


def run_visualization_with_demo_data(dag_model: DAGModel) -> None:
    """
    Run the visualization with demo data.
    
    Args:
        dag_model: The DAG model to populate with demo data.
    """
    from src.visualization.dag.model import NodeData, EdgeData, AgentStatus
    from datetime import datetime
    import random
    import threading
    import time
    
    logger.info("Running with demo data")
    
    # Create nodes
    agent_types = ["trader", "analyzer", "monitor", "executor", "risk_manager", "data_collector"]
    
    for i in range(8):
        node = NodeData(
            id=f"agent{i}",
            name=f"Demo Agent {i}",
            node_type=random.choice(agent_types),
            status=random.choice(list(AgentStatus)),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"demo": True, "version": "1.0.0"}
        )
        dag_model.add_node(node)
    
    # Create edges (representing different types of relationships)
    edges = [
        ("agent0", "agent1", "data_flow"),
        ("agent0", "agent2", "control"),
        ("agent1", "agent3", "data_flow"),
        ("agent2", "agent4", "data_flow"),
        ("agent2", "agent3", "notification"),
        ("agent4", "agent5", "data_flow"),
        ("agent5", "agent6", "control"),
        ("agent6", "agent7", "data_flow"),
        ("agent3", "agent7", "notification")
    ]
    
    for source, target, edge_type in edges:
        edge = EdgeData(
            source_id=source,
            target_id=target,
            edge_type=edge_type,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"demo": True}
        )
        dag_model.add_edge(edge)
    
    # Add some initial logs with different levels
    log_messages = {
        "INFO": [
            "Price update: BTC/USDT 45230.50",
            "New order: Buy 0.1 BTC at 45230.50",
            "Order filled: Buy 0.1 BTC at 45228.75",
            "Heartbeat received from exchange API",
            "System status: All components operational",
            "Market update received: BTC/ETH 0.06823",
            "Processing data batch #12345"
        ],
        "WARNING": [
            "Rate limit approaching (80% used)",
            "Latency increased to 250ms",
            "Unusual market volatility detected",
            "Retrying connection after temporary failure",
            "Order partially filled (75%)"
        ],
        "ERROR": [
            "Connection to exchange lost",
            "Order execution failed: Insufficient funds",
            "API request timeout after 5s",
            "Database query error: Deadlock detected",
            "Authentication failed after 3 retries"
        ],
        "DEBUG": [
            "Parsed 1250 ticker updates in 0.5s",
            "Cache hit ratio: 87%",
            "Memory usage: 512MB",
            "Thread pool status: 5/8 active",
            "Config loaded from /etc/config.yaml"
        ]
    }
    
    for source, target, _ in edges:
        # Add initial logs with different levels
        for level in ["INFO", "WARNING", "ERROR", "DEBUG"]:
            for _ in range(max(1, 3 if level == "INFO" else 1)):
                dag_model.add_log_to_edge(
                    source,
                    target,
                    random.choice(log_messages[level]),
                    level=level,
                    metadata={"timestamp": datetime.now().isoformat(), "demo": True}
                )
    
    # Set up a thread to periodically add new logs to simulate live updates
    def add_periodic_logs():
        while True:
            try:
                # Select a random edge
                source, target, _ = random.choice(edges)
                
                # Select a random log level with appropriate weights
                level = random.choices(
                    ["INFO", "WARNING", "ERROR", "DEBUG"],
                    weights=[0.7, 0.15, 0.1, 0.05],
                    k=1
                )[0]
                
                # Add a log entry
                dag_model.add_log_to_edge(
                    source,
                    target,
                    random.choice(log_messages[level]),
                    level=level,
                    metadata={"timestamp": datetime.now().isoformat(), "demo": True, "sequence": time.time()}
                )
                
                # Sleep for a random interval (1-5 seconds)
                time.sleep(random.uniform(1.0, 5.0))
            except Exception as e:
                logger.error(f"Error adding periodic logs: {str(e)}")
                time.sleep(5.0)  # Sleep longer on error
    
    # Start the periodic log thread
    log_thread = threading.Thread(target=add_periodic_logs, daemon=True)
    log_thread.start()
    
    # Run the visualization
    run_dag_visualization(dag_model)


def main():
    """Command-line entry point for the agent DAG visualization tool."""
    parser = create_arg_parser()
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Run in demo mode if requested
    if args.demo:
        logging.info("Running in demo mode")
        return demo_dag_visualization()
    
    # Run the async main function
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        logging.info("Visualization terminated by user")
        return 0
    except Exception as e:
        logging.error(f"Error running visualization: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main()) 