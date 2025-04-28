"""
Performance Monitoring for RL Models
-----------------------------------
Monitors performance of deployed trading strategies and provides alerts.
"""

import logging
import threading
import time
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Callable

import numpy as np
import pandas as pd
from sortedcontainers import SortedDict

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """
    Monitors the performance of deployed RL models and trading strategies.
    
    Features:
    - Real-time metric tracking
    - Anomaly detection
    - Alert generation
    - Performance degradation detection
    """
    
    def __init__(self,
                metrics_dir: str,
                config: Optional[Dict[str, Any]] = None,
                check_interval: int = 60,
                alert_handlers: Optional[List[Callable]] = None):
        """
        Initialize the performance monitor.
        
        Args:
            metrics_dir: Directory to store metrics and logs
            config: Configuration dictionary
            check_interval: Interval between checks (seconds)
            alert_handlers: List of callables to handle alerts
        """
        self.metrics_dir = metrics_dir
        self.config = config or {}
        self.check_interval = check_interval
        self.alert_handlers = alert_handlers or []
        
        # Ensure metrics directory exists
        os.makedirs(metrics_dir, exist_ok=True)
        
        # Initialize metrics
        self.metrics = {
            'strategy_returns': SortedDict(),  # timestamp -> return
            'trade_metrics': [],
            'model_performance': {},
            'system_metrics': {
                'memory_usage': [],
                'cpu_usage': [],
                'inference_time': [],
                'timestamp': []
            }
        }
        
        # Detection thresholds
        self.thresholds = self.config.get('thresholds', {
            'return_anomaly_z_score': 3.0,  # 3 std devs from mean
            'drawdown_threshold': -0.1,     # 10% drawdown
            'consecutive_losses': 5,         # 5 consecutive losing trades
            'trade_win_rate_min': 0.4,       # 40% minimum win rate
            'system_memory_max': 0.9,        # 90% memory usage
            'system_cpu_max': 0.8,           # 80% CPU usage
            'inference_time_max': 0.1,       # 100ms max inference time
        })
        
        # Alert state (to avoid duplicate alerts)
        self.active_alerts = {}
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Running state
        self.running = True
        
        # Start monitoring thread
        self._start_monitor_thread()
    
    def add_strategy_return(self, strategy_id: str, timestamp: datetime, returns: float) -> None:
        """
        Add a strategy return data point.
        
        Args:
            strategy_id: ID of the strategy
            timestamp: Time of the return calculation
            returns: Return value (decimal, not percentage)
        """
        with self.lock:
            if strategy_id not in self.metrics['strategy_returns']:
                self.metrics['strategy_returns'][strategy_id] = []
            
            self.metrics['strategy_returns'][strategy_id].append({
                'timestamp': timestamp,
                'return': returns
            })
            
            # Keep only last 1000 points
            if len(self.metrics['strategy_returns'][strategy_id]) > 1000:
                self.metrics['strategy_returns'][strategy_id] = self.metrics['strategy_returns'][strategy_id][-1000:]
    
    def add_trade(self, strategy_id: str, trade_data: Dict[str, Any]) -> None:
        """
        Add a trade record.
        
        Args:
            strategy_id: ID of the strategy
            trade_data: Trade details dictionary
        """
        trade_data['strategy_id'] = strategy_id
        trade_data['timestamp'] = trade_data.get('timestamp', datetime.now())
        
        with self.lock:
            self.metrics['trade_metrics'].append(trade_data)
            
            # Keep only last 1000 trades
            if len(self.metrics['trade_metrics']) > 1000:
                self.metrics['trade_metrics'] = self.metrics['trade_metrics'][-1000:]
    
    def update_model_performance(self, model_id: str, performance_data: Dict[str, Any]) -> None:
        """
        Update performance metrics for a model.
        
        Args:
            model_id: ID of the model
            performance_data: Performance metrics
        """
        with self.lock:
            performance_data['timestamp'] = performance_data.get('timestamp', datetime.now())
            self.metrics['model_performance'][model_id] = performance_data
    
    def update_system_metrics(self, memory_usage: float, cpu_usage: float, inference_time: float) -> None:
        """
        Update system resource usage metrics.
        
        Args:
            memory_usage: Memory usage (0-1 scale)
            cpu_usage: CPU usage (0-1 scale)
            inference_time: Inference time in seconds
        """
        timestamp = datetime.now()
        
        with self.lock:
            self.metrics['system_metrics']['memory_usage'].append(memory_usage)
            self.metrics['system_metrics']['cpu_usage'].append(cpu_usage)
            self.metrics['system_metrics']['inference_time'].append(inference_time)
            self.metrics['system_metrics']['timestamp'].append(timestamp)
            
            # Keep only last 1000 data points
            if len(self.metrics['system_metrics']['timestamp']) > 1000:
                for key in self.metrics['system_metrics']:
                    self.metrics['system_metrics'][key] = self.metrics['system_metrics'][key][-1000:]
    
    def detect_anomalies(self) -> List[Dict[str, Any]]:
        """
        Detect anomalies in metrics.
        
        Returns:
            List of anomaly dictionaries
        """
        anomalies = []
        
        with self.lock:
            # Check strategy returns for anomalies
            for strategy_id, returns_data in self.metrics['strategy_returns'].items():
                if len(returns_data) < 30:  # Need enough data
                    continue
                
                # Get recent returns
                returns = [entry['return'] for entry in returns_data[-30:]]
                
                # Check for anomalous returns (using z-score)
                mean_return = np.mean(returns[:-1])  # All except the most recent
                std_return = np.std(returns[:-1])
                
                if std_return > 0:  # Avoid division by zero
                    latest_return = returns[-1]
                    z_score = abs((latest_return - mean_return) / std_return)
                    
                    if z_score > self.thresholds['return_anomaly_z_score']:
                        anomalies.append({
                            'type': 'return_anomaly',
                            'strategy_id': strategy_id,
                            'timestamp': datetime.now(),
                            'z_score': z_score,
                            'value': latest_return,
                            'mean': mean_return,
                            'std': std_return,
                            'severity': 'high' if z_score > 5 else 'medium'
                        })
                
                # Check for drawdown
                cumulative_return = np.cumprod(1 + np.array(returns))
                peak = np.maximum.accumulate(cumulative_return)
                drawdown = (cumulative_return - peak) / peak
                
                if drawdown[-1] < self.thresholds['drawdown_threshold']:
                    anomalies.append({
                        'type': 'drawdown',
                        'strategy_id': strategy_id,
                        'timestamp': datetime.now(),
                        'value': drawdown[-1],
                        'threshold': self.thresholds['drawdown_threshold'],
                        'severity': 'high' if drawdown[-1] < 2 * self.thresholds['drawdown_threshold'] else 'medium'
                    })
            
            # Check trade metrics
            for strategy_id, trades in self._group_trades_by_strategy().items():
                if len(trades) < 10:  # Need enough trades
                    continue
                
                # Check consecutive losses
                sorted_trades = sorted(trades, key=lambda x: x['timestamp'])
                consecutive_losses = 0
                for trade in sorted_trades:
                    if trade.get('pnl', 0) < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    
                    if consecutive_losses >= self.thresholds['consecutive_losses']:
                        anomalies.append({
                            'type': 'consecutive_losses',
                            'strategy_id': strategy_id,
                            'timestamp': datetime.now(),
                            'value': consecutive_losses,
                            'threshold': self.thresholds['consecutive_losses'],
                            'severity': 'medium'
                        })
                        break
                
                # Check win rate
                win_count = sum(1 for trade in trades if trade.get('pnl', 0) > 0)
                win_rate = win_count / len(trades)
                
                if win_rate < self.thresholds['trade_win_rate_min']:
                    anomalies.append({
                        'type': 'low_win_rate',
                        'strategy_id': strategy_id,
                        'timestamp': datetime.now(),
                        'value': win_rate,
                        'threshold': self.thresholds['trade_win_rate_min'],
                        'severity': 'medium' if win_rate > 0.3 else 'high'
                    })
            
            # Check system metrics
            if self.metrics['system_metrics']['memory_usage']:
                latest_memory = self.metrics['system_metrics']['memory_usage'][-1]
                if latest_memory > self.thresholds['system_memory_max']:
                    anomalies.append({
                        'type': 'high_memory_usage',
                        'timestamp': datetime.now(),
                        'value': latest_memory,
                        'threshold': self.thresholds['system_memory_max'],
                        'severity': 'high' if latest_memory > 0.95 else 'medium'
                    })
            
            if self.metrics['system_metrics']['cpu_usage']:
                latest_cpu = self.metrics['system_metrics']['cpu_usage'][-1]
                if latest_cpu > self.thresholds['system_cpu_max']:
                    anomalies.append({
                        'type': 'high_cpu_usage',
                        'timestamp': datetime.now(),
                        'value': latest_cpu,
                        'threshold': self.thresholds['system_cpu_max'],
                        'severity': 'medium'
                    })
            
            if self.metrics['system_metrics']['inference_time']:
                latest_inference = self.metrics['system_metrics']['inference_time'][-1]
                if latest_inference > self.thresholds['inference_time_max']:
                    anomalies.append({
                        'type': 'slow_inference',
                        'timestamp': datetime.now(),
                        'value': latest_inference,
                        'threshold': self.thresholds['inference_time_max'],
                        'severity': 'medium' if latest_inference < 0.5 else 'high'
                    })
        
        return anomalies
    
    def _group_trades_by_strategy(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group trades by strategy ID.
        
        Returns:
            Dictionary mapping strategy IDs to lists of trades
        """
        result = {}
        for trade in self.metrics['trade_metrics']:
            strategy_id = trade.get('strategy_id', 'unknown')
            if strategy_id not in result:
                result[strategy_id] = []
            result[strategy_id].append(trade)
        return result
    
    def handle_anomalies(self, anomalies: List[Dict[str, Any]]) -> None:
        """
        Handle detected anomalies.
        
        Args:
            anomalies: List of anomaly dictionaries
        """
        for anomaly in anomalies:
            # Generate a unique key for the anomaly
            anomaly_key = f"{anomaly['type']}_{anomaly.get('strategy_id', '')}"
            
            # Check if this is a new anomaly or a repeated one
            is_new = False
            now = datetime.now()
            
            if anomaly_key not in self.active_alerts:
                is_new = True
                self.active_alerts[anomaly_key] = now
            elif (now - self.active_alerts[anomaly_key]) > timedelta(hours=1):
                # Reset if it's been more than an hour since the last alert
                is_new = True
                self.active_alerts[anomaly_key] = now
            
            if is_new:
                # Log the anomaly
                if anomaly['severity'] == 'high':
                    logger.error(f"HIGH SEVERITY ANOMALY: {anomaly}")
                else:
                    logger.warning(f"ANOMALY DETECTED: {anomaly}")
                
                # Dispatch to alert handlers
                for handler in self.alert_handlers:
                    try:
                        handler(anomaly)
                    except Exception as e:
                        logger.error(f"Error in alert handler: {str(e)}")
                
                # Save to anomaly log
                self._save_anomaly(anomaly)
    
    def _save_anomaly(self, anomaly: Dict[str, Any]) -> None:
        """
        Save anomaly to log file.
        
        Args:
            anomaly: Anomaly dictionary
        """
        log_file = os.path.join(self.metrics_dir, 'anomalies.jsonl')
        
        # Convert timestamp to string if needed
        if isinstance(anomaly.get('timestamp'), datetime):
            anomaly = anomaly.copy()
            anomaly['timestamp'] = anomaly['timestamp'].isoformat()
        
        try:
            with open(log_file, 'a') as f:
                f.write(json.dumps(anomaly) + '\n')
        except Exception as e:
            logger.error(f"Failed to save anomaly to log: {str(e)}")
    
    def save_metrics(self) -> None:
        """Save all metrics to disk."""
        try:
            # Save strategy returns
            for strategy_id, returns_data in self.metrics['strategy_returns'].items():
                file_path = os.path.join(self.metrics_dir, f'returns_{strategy_id}.csv')
                df = pd.DataFrame(returns_data)
                df.to_csv(file_path, index=False)
            
            # Save trades
            trades_path = os.path.join(self.metrics_dir, 'trades.csv')
            if self.metrics['trade_metrics']:
                df = pd.DataFrame(self.metrics['trade_metrics'])
                df.to_csv(trades_path, index=False)
            
            # Save system metrics
            system_path = os.path.join(self.metrics_dir, 'system_metrics.csv')
            df = pd.DataFrame(self.metrics['system_metrics'])
            df.to_csv(system_path, index=False)
            
            # Save model performance
            for model_id, perf_data in self.metrics['model_performance'].items():
                file_path = os.path.join(self.metrics_dir, f'model_{model_id}.json')
                with open(file_path, 'w') as f:
                    json.dump(perf_data, f, default=str)
            
            logger.info(f"Metrics saved to {self.metrics_dir}")
        except Exception as e:
            logger.error(f"Failed to save metrics: {str(e)}")
    
    def load_metrics(self) -> None:
        """Load metrics from disk."""
        try:
            # Load strategy returns
            returns_files = [f for f in os.listdir(self.metrics_dir) if f.startswith('returns_') and f.endswith('.csv')]
            for file in returns_files:
                strategy_id = file[8:-4]  # Extract ID from filename
                file_path = os.path.join(self.metrics_dir, file)
                df = pd.read_csv(file_path)
                
                # Convert to list of dicts
                returns_data = df.to_dict('records')
                
                # Convert timestamp strings to datetime objects
                for entry in returns_data:
                    if isinstance(entry.get('timestamp'), str):
                        entry['timestamp'] = datetime.fromisoformat(entry['timestamp'])
                
                with self.lock:
                    self.metrics['strategy_returns'][strategy_id] = returns_data
            
            # Load trades
            trades_path = os.path.join(self.metrics_dir, 'trades.csv')
            if os.path.exists(trades_path):
                df = pd.read_csv(trades_path)
                trades = df.to_dict('records')
                
                # Convert timestamp strings to datetime objects
                for trade in trades:
                    if isinstance(trade.get('timestamp'), str):
                        trade['timestamp'] = datetime.fromisoformat(trade['timestamp'])
                
                with self.lock:
                    self.metrics['trade_metrics'] = trades
            
            # Load system metrics
            system_path = os.path.join(self.metrics_dir, 'system_metrics.csv')
            if os.path.exists(system_path):
                df = pd.read_csv(system_path)
                
                with self.lock:
                    for col in df.columns:
                        if col in self.metrics['system_metrics']:
                            self.metrics['system_metrics'][col] = df[col].tolist()
                    
                    # Convert timestamp strings to datetime objects
                    self.metrics['system_metrics']['timestamp'] = [
                        datetime.fromisoformat(ts) if isinstance(ts, str) else ts
                        for ts in self.metrics['system_metrics']['timestamp']
                    ]
            
            # Load model performance
            model_files = [f for f in os.listdir(self.metrics_dir) if f.startswith('model_') and f.endswith('.json')]
            for file in model_files:
                model_id = file[6:-5]  # Extract ID from filename
                file_path = os.path.join(self.metrics_dir, file)
                
                with open(file_path, 'r') as f:
                    perf_data = json.load(f)
                
                # Convert timestamp strings to datetime objects
                if isinstance(perf_data.get('timestamp'), str):
                    perf_data['timestamp'] = datetime.fromisoformat(perf_data['timestamp'])
                
                with self.lock:
                    self.metrics['model_performance'][model_id] = perf_data
            
            logger.info(f"Metrics loaded from {self.metrics_dir}")
        except Exception as e:
            logger.error(f"Failed to load metrics: {str(e)}")
    
    def _monitor_thread(self) -> None:
        """Background thread for periodic monitoring."""
        while self.running:
            try:
                # Detect anomalies
                anomalies = self.detect_anomalies()
                
                # Handle anomalies
                if anomalies:
                    self.handle_anomalies(anomalies)
                
                # Save metrics periodically (every 10 minutes)
                now = datetime.now()
                if now.minute % 10 == 0 and now.second < 10:
                    self.save_metrics()
                
                # Wait for next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring thread: {str(e)}")
                time.sleep(10)  # Wait a bit before trying again
    
    def _start_monitor_thread(self) -> None:
        """Start the monitoring background thread."""
        self.load_metrics()  # Load existing metrics first
        
        thread = threading.Thread(target=self._monitor_thread, daemon=True)
        thread.start()
        logger.info("Performance monitoring thread started")
    
    def add_alert_handler(self, handler: Callable) -> None:
        """
        Add a new alert handler.
        
        Args:
            handler: Callable that accepts an anomaly dictionary
        """
        self.alert_handlers.append(handler)
    
    def get_performance_summary(self, strategy_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a summary of performance metrics.
        
        Args:
            strategy_id: Optional strategy ID to filter for
            
        Returns:
            Dictionary with performance summary
        """
        with self.lock:
            summary = {'timestamp': datetime.now()}
            
            # Get strategies to summarize
            strategies = []
            if strategy_id:
                if strategy_id in self.metrics['strategy_returns']:
                    strategies = [strategy_id]
                else:
                    return {'error': f"Strategy {strategy_id} not found"}
            else:
                strategies = list(self.metrics['strategy_returns'].keys())
            
            # Calculate strategy metrics
            strategy_metrics = {}
            for sid in strategies:
                returns_data = self.metrics['strategy_returns'].get(sid, [])
                
                if len(returns_data) < 5:
                    continue
                    
                returns = [entry['return'] for entry in returns_data]
                
                # Calculate key metrics
                strategy_metrics[sid] = {
                    'total_return': np.prod(1 + np.array(returns)) - 1,
                    'mean_return': np.mean(returns),
                    'volatility': np.std(returns),
                    'sharpe_ratio': np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0,
                    'max_drawdown': self._calculate_max_drawdown(returns),
                    'win_rate': self._calculate_win_rate(sid),
                    'data_points': len(returns_data)
                }
            
            summary['strategy_metrics'] = strategy_metrics
            
            # System metrics
            if self.metrics['system_metrics']['timestamp']:
                # Get the most recent metrics
                idx = -1
                summary['system'] = {
                    'memory_usage': self.metrics['system_metrics']['memory_usage'][idx],
                    'cpu_usage': self.metrics['system_metrics']['cpu_usage'][idx],
                    'inference_time': self.metrics['system_metrics']['inference_time'][idx],
                    'timestamp': self.metrics['system_metrics']['timestamp'][idx]
                }
            
            # Model performance
            summary['models'] = self.metrics['model_performance']
            
            return summary
    
    def _calculate_max_drawdown(self, returns: List[float]) -> float:
        """
        Calculate maximum drawdown from a series of returns.
        
        Args:
            returns: List of return values
            
        Returns:
            Maximum drawdown as a positive number
        """
        cumulative = np.cumprod(1 + np.array(returns))
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak
        return abs(min(drawdown, default=0))
    
    def _calculate_win_rate(self, strategy_id: str) -> float:
        """
        Calculate win rate for a strategy from trade data.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            Win rate as a decimal
        """
        trades = [t for t in self.metrics['trade_metrics'] if t.get('strategy_id') == strategy_id]
        
        if not trades:
            return 0.0
        
        wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
        return wins / len(trades)
    
    def shutdown(self) -> None:
        """Gracefully shut down the performance monitor."""
        logger.info("Performance monitor shutting down...")
        self.running = False
        self.save_metrics()
        logger.info("Performance monitor shutdown complete") 