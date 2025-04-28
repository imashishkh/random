"""
Monitoring modules for system metrics and agent activities.

Provides classes for collecting and tracking:
- System metrics (CPU, memory, disk, network)
- Trading agent status and activities
"""

import psutil
import time
import random
import threading
from typing import Dict, List, Optional, Any, Tuple
from collections import deque
from datetime import datetime


class SystemMonitor:
    """Monitor system resources including CPU, memory, disk, and network."""
    
    def __init__(self, history_length: int = 60):
        """
        Initialize the system monitor.
        
        Args:
            history_length: Number of historical data points to retain
        """
        self.history_length = history_length
        self.cpu_history = deque(maxlen=history_length)
        self.memory_history = deque(maxlen=history_length)
        self.disk_history = deque(maxlen=history_length)
        self.network_history = deque(maxlen=history_length)
        
        self.last_network_io = None
        self.last_disk_io = None
        self.last_update_time = None
        
        # Thresholds for warning/critical states
        self.thresholds = {
            "cpu": {"warning": 70.0, "critical": 90.0},
            "memory": {"warning": 75.0, "critical": 90.0},
            "disk": {"warning": 80.0, "critical": 95.0}
        }
        
        # Start data collection thread
        self._running = False
        self._lock = threading.RLock()
        self._thread = None
    
    def start(self, interval: float = 1.0):
        """Start the monitoring thread."""
        if self._running:
            return
            
        self._running = True
        self._interval = interval
        self._thread = threading.Thread(target=self._collect_data, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
    
    def _collect_data(self):
        """Data collection loop."""
        while self._running:
            try:
                with self._lock:
                    self._update_metrics()
                time.sleep(self._interval)
            except Exception as e:
                print(f"Error collecting system metrics: {e}")
                time.sleep(1.0)  # Sleep briefly before retrying
    
    def _update_metrics(self):
        """Update all system metrics."""
        current_time = datetime.now()
        
        # Update CPU metrics
        cpu_percent = psutil.cpu_percent(interval=None)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        self.cpu_history.append({
            "timestamp": current_time,
            "percent": cpu_percent,
            "per_core": cpu_per_core,
            "status": self._get_status_level("cpu", cpu_percent)
        })
        
        # Update memory metrics
        memory = psutil.virtual_memory()
        self.memory_history.append({
            "timestamp": current_time,
            "percent": memory.percent,
            "used": memory.used,
            "total": memory.total,
            "available": memory.available,
            "status": self._get_status_level("memory", memory.percent)
        })
        
        # Update disk metrics
        disk_usage = {}
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_usage[partition.mountpoint] = {
                    "percent": usage.percent,
                    "used": usage.used,
                    "total": usage.total,
                    "free": usage.free,
                    "status": self._get_status_level("disk", usage.percent)
                }
            except (PermissionError, OSError):
                # Skip if we don't have access
                continue
        
        # Calculate disk I/O rates
        current_disk_io = psutil.disk_io_counters()
        if self.last_disk_io and self.last_update_time:
            time_diff = (current_time - self.last_update_time).total_seconds()
            read_rate = (current_disk_io.read_bytes - self.last_disk_io.read_bytes) / time_diff
            write_rate = (current_disk_io.write_bytes - self.last_disk_io.write_bytes) / time_diff
            disk_io_rates = {"read_rate": read_rate, "write_rate": write_rate}
        else:
            disk_io_rates = {"read_rate": 0, "write_rate": 0}
        
        self.disk_history.append({
            "timestamp": current_time,
            "usage": disk_usage,
            "io_rates": disk_io_rates
        })
        self.last_disk_io = current_disk_io
        
        # Update network metrics
        current_net_io = psutil.net_io_counters()
        if self.last_network_io and self.last_update_time:
            time_diff = (current_time - self.last_update_time).total_seconds()
            send_rate = (current_net_io.bytes_sent - self.last_network_io.bytes_sent) / time_diff
            recv_rate = (current_net_io.bytes_recv - self.last_network_io.bytes_recv) / time_diff
            network_rates = {"send_rate": send_rate, "recv_rate": recv_rate}
        else:
            network_rates = {"send_rate": 0, "recv_rate": 0}
        
        network_stats = {
            "rates": network_rates,
            "connections": len(psutil.net_connections()),
            "interfaces": psutil.net_if_stats()
        }
        
        self.network_history.append({
            "timestamp": current_time,
            "stats": network_stats
        })
        self.last_network_io = current_net_io
        
        # Update timestamp for rate calculations
        self.last_update_time = current_time
    
    def _get_status_level(self, metric_type: str, value: float) -> str:
        """Determine status level based on thresholds."""
        thresholds = self.thresholds.get(metric_type, {"warning": 70.0, "critical": 90.0})
        
        if value >= thresholds["critical"]:
            return "critical"
        elif value >= thresholds["warning"]:
            return "warning"
        else:
            return "normal"
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get the current system metrics."""
        with self._lock:
            return {
                "cpu": self.cpu_history[-1] if self.cpu_history else None,
                "memory": self.memory_history[-1] if self.memory_history else None,
                "disk": self.disk_history[-1] if self.disk_history else None,
                "network": self.network_history[-1] if self.network_history else None
            }
    
    def get_history(self, metric_type: str) -> List[Dict[str, Any]]:
        """Get the historical data for a specific metric type."""
        with self._lock:
            if metric_type == "cpu":
                return list(self.cpu_history)
            elif metric_type == "memory":
                return list(self.memory_history)
            elif metric_type == "disk":
                return list(self.disk_history)
            elif metric_type == "network":
                return list(self.network_history)
            else:
                return []


class AgentMonitor:
    """Monitor and track trading agents' activities and status."""
    
    def __init__(self, agent_health_monitor=None):
        """
        Initialize the agent monitor.
        
        Args:
            agent_health_monitor: Optional reference to an AgentHealthMonitor instance
        """
        self.agent_health_monitor = agent_health_monitor
        self.agent_status = {}  # Current status of all agents
        self.agent_logs = {}    # Recent log entries for each agent
        self.max_log_entries = 100  # Max log entries to keep per agent
        
        # For demo/development without the real AgentHealthMonitor
        self.demo_mode = agent_health_monitor is None
        self._lock = threading.RLock()
    
    def update_status(self):
        """Update agent status information."""
        with self._lock:
            if self.demo_mode:
                self._update_demo_status()
            else:
                self._update_real_status()
    
    def _update_real_status(self):
        """Update agent status from the real AgentHealthMonitor."""
        if not self.agent_health_monitor:
            return
            
        try:
            # Get all health metrics from the AgentHealthMonitor
            all_metrics = self.agent_health_monitor.get_all_health_metrics()
            
            for agent_id, metrics in all_metrics.items():
                # Convert the health metrics to our status format
                status = self._convert_health_to_status(metrics)
                
                # Store the status
                self.agent_status[agent_id] = status
                
        except Exception as e:
            print(f"Error updating agent status: {e}")
    
    def _update_demo_status(self):
        """Generate demo agent status for development/testing."""
        # Example agents
        agents = [
            "TrendFollower", "MeanReversion", "BreakoutTrader", 
            "GridTrader", "NewsMomentum", "VolatilityArbitrage"
        ]
        
        statuses = ["active", "warning", "error", "stopped"]
        weights = [0.6, 0.15, 0.05, 0.2]  # Weighted probabilities
        
        # Update or create status for each agent
        for agent in agents:
            current_time = datetime.now()
            
            # Get existing status or create new
            if agent in self.agent_status:
                status = self.agent_status[agent]
                
                # Occasionally change status
                if random.random() < 0.05:  # 5% chance to change
                    status["status"] = random.choices(statuses, weights)[0]
                    status["status_since"] = current_time
                    
                    # Add a log entry about the status change
                    self._add_log_entry(agent, f"Status changed to {status['status']}")
                
                # Update timestamps and counters
                status["last_update"] = current_time
                status["processed_trades"] += random.randint(0, 3)
                
                # Randomly add log entries
                if random.random() < 0.2:  # 20% chance to add log
                    self._add_log_entry(agent, f"Processed trade #{status['processed_trades']}")
            else:
                # Create new status
                self.agent_status[agent] = {
                    "status": random.choices(statuses, weights)[0],
                    "status_since": current_time,
                    "created": current_time,
                    "last_update": current_time,
                    "processed_trades": random.randint(10, 100),
                    "success_rate": random.uniform(0.5, 0.95),
                    "version": f"v{random.randint(1, 3)}.{random.randint(0, 9)}"
                }
                
                # Initialize log entries
                if agent not in self.agent_logs:
                    self.agent_logs[agent] = []
                    self._add_log_entry(agent, f"Agent {agent} initialized")
    
    def _add_log_entry(self, agent: str, message: str):
        """Add a log entry for an agent."""
        if agent not in self.agent_logs:
            self.agent_logs[agent] = []
            
        # Add entry with timestamp
        entry = {
            "timestamp": datetime.now(),
            "message": message
        }
        
        self.agent_logs[agent].append(entry)
        
        # Trim if exceeding max entries
        if len(self.agent_logs[agent]) > self.max_log_entries:
            self.agent_logs[agent] = self.agent_logs[agent][-self.max_log_entries:]
    
    def _convert_health_to_status(self, health_metrics):
        """Convert health monitor metrics to status format."""
        # Example conversion logic - adjust based on actual health metrics structure
        status = "active"
        
        if health_metrics.get("error_count", 0) > 5:
            status = "error"
        elif health_metrics.get("warning_count", 0) > 0:
            status = "warning"
        elif not health_metrics.get("is_running", True):
            status = "stopped"
            
        return {
            "status": status,
            "status_since": health_metrics.get("status_since", datetime.now()),
            "created": health_metrics.get("created_at", datetime.now()),
            "last_update": health_metrics.get("last_update", datetime.now()),
            "processed_trades": health_metrics.get("processed_trades", 0),
            "success_rate": health_metrics.get("success_rate", 0.0),
            "version": health_metrics.get("version", "unknown")
        }
    
    def get_all_agents(self):
        """Get status of all agents."""
        with self._lock:
            return dict(self.agent_status)
    
    def get_agent_logs(self, agent=None, limit=20):
        """
        Get recent log entries for an agent or all agents.
        
        Args:
            agent: Agent name or None for all agents
            limit: Maximum number of log entries to return
        """
        with self._lock:
            if agent:
                # Return logs for specific agent
                logs = self.agent_logs.get(agent, [])
                return logs[-limit:] if logs else []
            else:
                # Return combined logs for all agents, sorted by timestamp
                all_logs = []
                for agent_name, logs in self.agent_logs.items():
                    for log in logs:
                        entry = log.copy()
                        entry["agent"] = agent_name
                        all_logs.append(entry)
                
                # Sort by timestamp, newest first
                all_logs.sort(key=lambda x: x["timestamp"], reverse=True)
                return all_logs[:limit] 