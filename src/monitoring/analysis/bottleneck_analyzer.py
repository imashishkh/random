"""
Bottleneck Analyzer for performance metrics.

This module provides tools for analyzing performance metrics to identify
bottlenecks and performance issues in the system.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class BottleneckAnalyzer:
    """
    Analyzes performance metrics to identify bottlenecks in the system.
    
    This class correlates different types of metrics to identify patterns that
    indicate bottlenecks or performance issues. It uses statistical analysis
    and pattern recognition to pinpoint the root causes of performance problems.
    """
    
    def __init__(
        self,
        correlation_threshold: float = 0.7,
        anomaly_z_threshold: float = 3.0,
        time_window: int = 300,  # 5 minutes
        min_samples: int = 10
    ):
        """
        Initialize the bottleneck analyzer.
        
        Args:
            correlation_threshold: Threshold for considering metrics correlated
            anomaly_z_threshold: Z-score threshold for anomaly detection
            time_window: Time window for analysis in seconds
            min_samples: Minimum number of samples needed for analysis
        """
        self.correlation_threshold = correlation_threshold
        self.anomaly_z_threshold = anomaly_z_threshold
        self.time_window = time_window
        self.min_samples = min_samples
        
        # Mapping of known bottleneck patterns to their descriptions
        self.bottleneck_patterns = {
            "high_cpu_high_latency": {
                "conditions": [
                    ("system.cpu_usage", ">", 85),
                    ("performance.latency.total", ">", "2x_baseline")
                ],
                "description": "High CPU utilization causing increased latency",
                "recommendations": [
                    "Scale horizontally by adding more processing nodes",
                    "Optimize CPU-intensive operations",
                    "Check for CPU-intensive background processes"
                ]
            },
            "memory_pressure": {
                "conditions": [
                    ("system.memory_usage", ">", 90),
                    ("system.swap_usage", ">", 20)
                ],
                "description": "Memory pressure causing performance degradation",
                "recommendations": [
                    "Increase available memory",
                    "Check for memory leaks",
                    "Optimize memory-intensive operations"
                ]
            },
            "database_bottleneck": {
                "conditions": [
                    ("database.query_time", ">", "3x_baseline"),
                    ("database.connections", ">", "0.8x_max")
                ],
                "description": "Database performance bottleneck",
                "recommendations": [
                    "Optimize slow queries",
                    "Add appropriate indexes",
                    "Consider query caching",
                    "Scale database resources"
                ]
            },
            "network_congestion": {
                "conditions": [
                    ("system.network_utilization", ">", 80),
                    ("system.network_errors", ">", 0)
                ],
                "description": "Network congestion affecting performance",
                "recommendations": [
                    "Increase network capacity",
                    "Optimize network-intensive operations",
                    "Check for network misconfiguration"
                ]
            },
            "message_queue_backlog": {
                "conditions": [
                    ("application.queue_depth", ">", "5x_baseline"),
                    ("performance.latency.total", ">", "1.5x_baseline")
                ],
                "description": "Message queue backlog causing increased latency",
                "recommendations": [
                    "Increase consumer capacity",
                    "Optimize message processing",
                    "Check for slow consumers"
                ]
            }
        }
    
    def analyze_metrics(
        self,
        metrics: Dict[str, pd.DataFrame],
        baseline: Optional[Dict[str, pd.DataFrame]] = None
    ) -> Dict[str, Any]:
        """
        Analyze metrics to identify bottlenecks.
        
        Args:
            metrics: Dictionary of metric names to DataFrames with timestamps and values
            baseline: Optional baseline metrics for comparison
            
        Returns:
            Dictionary with analysis results
        """
        try:
            results = {
                "timestamp": datetime.now(),
                "bottlenecks": [],
                "correlations": [],
                "anomalies": [],
                "recommendations": []
            }
            
            # Check for predefined bottleneck patterns
            bottlenecks = self._check_bottleneck_patterns(metrics, baseline)
            results["bottlenecks"].extend(bottlenecks)
            
            # Find correlations between different metrics
            correlations = self._find_metric_correlations(metrics)
            results["correlations"] = correlations
            
            # Detect anomalies in metrics
            anomalies = self._detect_anomalies(metrics, baseline)
            results["anomalies"] = anomalies
            
            # Generate recommendations based on findings
            recommendations = self._generate_recommendations(bottlenecks, correlations, anomalies)
            results["recommendations"] = recommendations
            
            return results
        except Exception as e:
            logger.error(f"Error analyzing metrics: {str(e)}", exc_info=True)
            return {
                "timestamp": datetime.now(),
                "error": str(e),
                "bottlenecks": [],
                "correlations": [],
                "anomalies": [],
                "recommendations": []
            }
    
    def _check_bottleneck_patterns(
        self,
        metrics: Dict[str, pd.DataFrame],
        baseline: Optional[Dict[str, pd.DataFrame]] = None
    ) -> List[Dict[str, Any]]:
        """
        Check for known bottleneck patterns in metrics.
        
        Args:
            metrics: Dictionary of metric names to DataFrames
            baseline: Optional baseline metrics for comparison
            
        Returns:
            List of identified bottleneck patterns
        """
        bottlenecks = []
        
        for pattern_name, pattern_info in self.bottleneck_patterns.items():
            conditions = pattern_info["conditions"]
            matches = True
            
            for metric_name, operator, threshold in conditions:
                if metric_name not in metrics:
                    matches = False
                    break
                
                # Get current value (use last value in time series)
                if not metrics[metric_name].empty:
                    current_value = metrics[metric_name]["value"].iloc[-1]
                else:
                    matches = False
                    break
                
                # Handle dynamic thresholds that reference baseline
                if isinstance(threshold, str) and "x_baseline" in threshold:
                    if not baseline or metric_name not in baseline:
                        matches = False
                        break
                    
                    multiplier = float(threshold.split("x_")[0])
                    baseline_value = baseline[metric_name]["value"].mean()
                    threshold = baseline_value * multiplier
                
                # Handle max references
                if isinstance(threshold, str) and "x_max" in threshold:
                    if metric_name + ".max" not in metrics:
                        matches = False
                        break
                    
                    multiplier = float(threshold.split("x_")[0])
                    max_value = metrics[metric_name + ".max"]["value"].iloc[-1]
                    threshold = max_value * multiplier
                
                # Compare based on operator
                if operator == ">" and not current_value > threshold:
                    matches = False
                    break
                elif operator == ">=" and not current_value >= threshold:
                    matches = False
                    break
                elif operator == "<" and not current_value < threshold:
                    matches = False
                    break
                elif operator == "<=" and not current_value <= threshold:
                    matches = False
                    break
                elif operator == "==" and not current_value == threshold:
                    matches = False
                    break
            
            if matches:
                bottlenecks.append({
                    "pattern": pattern_name,
                    "description": pattern_info["description"],
                    "severity": self._calculate_severity(metrics, pattern_name),
                    "recommendations": pattern_info["recommendations"]
                })
        
        return bottlenecks
    
    def _find_metric_correlations(self, metrics: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        Find correlations between different metrics.
        
        Args:
            metrics: Dictionary of metric names to DataFrames
            
        Returns:
            List of correlations between metrics
        """
        correlations = []
        metric_names = list(metrics.keys())
        
        # Calculate correlations between pairs of metrics
        for i in range(len(metric_names)):
            for j in range(i + 1, len(metric_names)):
                metric1 = metric_names[i]
                metric2 = metric_names[j]
                
                # Skip if either DataFrame is empty
                if metrics[metric1].empty or metrics[metric2].empty:
                    continue
                
                # Align timestamps and compute correlation
                df1 = metrics[metric1]
                df2 = metrics[metric2]
                
                # Resample to common time points if needed
                if len(df1) >= self.min_samples and len(df2) >= self.min_samples:
                    try:
                        # Merge on timestamp and calculate correlation
                        merged = pd.merge_asof(
                            df1.sort_values("timestamp"),
                            df2.sort_values("timestamp"),
                            on="timestamp",
                            suffixes=("_1", "_2")
                        )
                        
                        if len(merged) >= self.min_samples:
                            corr = merged["value_1"].corr(merged["value_2"])
                            
                            # Only include strong correlations
                            if abs(corr) >= self.correlation_threshold:
                                correlations.append({
                                    "metric1": metric1,
                                    "metric2": metric2,
                                    "correlation": corr,
                                    "direction": "positive" if corr > 0 else "negative",
                                    "strength": abs(corr)
                                })
                    except Exception as e:
                        logger.warning(f"Error calculating correlation between {metric1} and {metric2}: {e}")
        
        return correlations
    
    def _detect_anomalies(
        self,
        metrics: Dict[str, pd.DataFrame],
        baseline: Optional[Dict[str, pd.DataFrame]] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect anomalies in metrics using statistical methods.
        
        Args:
            metrics: Dictionary of metric names to DataFrames
            baseline: Optional baseline metrics for comparison
            
        Returns:
            List of anomalies detected in metrics
        """
        anomalies = []
        
        for metric_name, df in metrics.items():
            if df.empty or len(df) < self.min_samples:
                continue
            
            # Calculate mean and standard deviation
            values = df["value"]
            mean_value = values.mean()
            std_value = values.std()
            
            # Skip if standard deviation is zero or very small
            if std_value < 1e-10:
                continue
            
            # Calculate z-scores
            z_scores = (values - mean_value) / std_value
            
            # Find anomalies (values with high z-scores)
            anomaly_indices = np.where(np.abs(z_scores) > self.anomaly_z_threshold)[0]
            
            for idx in anomaly_indices:
                timestamp = df["timestamp"].iloc[idx]
                value = values.iloc[idx]
                z_score = z_scores.iloc[idx]
                
                anomalies.append({
                    "metric": metric_name,
                    "timestamp": timestamp,
                    "value": value,
                    "z_score": z_score,
                    "direction": "high" if z_score > 0 else "low",
                    "severity": min(1.0, abs(z_score) / (2 * self.anomaly_z_threshold))
                })
        
        return anomalies
    
    def _calculate_severity(self, metrics: Dict[str, pd.DataFrame], pattern_name: str) -> float:
        """
        Calculate the severity of a bottleneck pattern.
        
        Args:
            metrics: Dictionary of metric names to DataFrames
            pattern_name: Name of the bottleneck pattern
            
        Returns:
            Severity score between 0 and 1
        """
        # Pattern-specific severity calculations
        if pattern_name == "high_cpu_high_latency" and "system.cpu_usage" in metrics:
            cpu_df = metrics["system.cpu_usage"]
            if not cpu_df.empty:
                cpu_value = cpu_df["value"].iloc[-1]
                # Severity increases as CPU usage approaches 100%
                return min(1.0, max(0.0, (cpu_value - 85) / 15))
        
        elif pattern_name == "memory_pressure" and "system.memory_usage" in metrics:
            memory_df = metrics["system.memory_usage"]
            if not memory_df.empty:
                memory_value = memory_df["value"].iloc[-1]
                # Severity increases as memory usage approaches 100%
                return min(1.0, max(0.0, (memory_value - 90) / 10))
        
        elif pattern_name == "database_bottleneck" and "database.query_time" in metrics:
            query_df = metrics["database.query_time"]
            if not query_df.empty:
                query_values = query_df["value"]
                baseline = query_values.mean()
                current = query_values.iloc[-1]
                # Severity based on how much higher than baseline
                ratio = current / baseline if baseline > 0 else 1.0
                return min(1.0, max(0.0, (ratio - 3) / 7))
        
        # Default severity calculation
        return 0.5  # Medium severity by default
    
    def _generate_recommendations(
        self,
        bottlenecks: List[Dict[str, Any]],
        correlations: List[Dict[str, Any]],
        anomalies: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate recommendations based on analysis results.
        
        Args:
            bottlenecks: List of identified bottlenecks
            correlations: List of metric correlations
            anomalies: List of detected anomalies
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Add recommendations from bottlenecks
        for bottleneck in bottlenecks:
            for rec in bottleneck["recommendations"]:
                recommendations.append({
                    "recommendation": rec,
                    "source": f"Bottleneck pattern: {bottleneck['pattern']}",
                    "severity": bottleneck["severity"],
                    "category": "bottleneck"
                })
        
        # Add recommendations based on correlations
        for correlation in correlations:
            if correlation["strength"] > 0.9:
                metric1 = correlation["metric1"]
                metric2 = correlation["metric2"]
                direction = correlation["direction"]
                
                # Example: If CPU usage strongly correlates with latency
                if "cpu" in metric1 and "latency" in metric2 and direction == "positive":
                    recommendations.append({
                        "recommendation": "Consider scaling CPU resources as it strongly impacts latency",
                        "source": f"Strong correlation between {metric1} and {metric2}",
                        "severity": min(1.0, correlation["strength"]),
                        "category": "correlation"
                    })
                
                # More correlation-based recommendations can be added here
        
        # Add recommendations based on anomalies
        severe_anomalies = [a for a in anomalies if a["severity"] > 0.8]
        if severe_anomalies:
            metric_groups = {}
            for anomaly in severe_anomalies:
                metric = anomaly["metric"]
                if metric not in metric_groups:
                    metric_groups[metric] = []
                metric_groups[metric].append(anomaly)
            
            for metric, group in metric_groups.items():
                if len(group) > 2:  # Multiple anomalies in the same metric
                    recommendations.append({
                        "recommendation": f"Investigate {metric} for multiple significant anomalies",
                        "source": f"{len(group)} anomalies detected in {metric}",
                        "severity": max(a["severity"] for a in group),
                        "category": "anomaly"
                    })
        
        # Sort recommendations by severity
        recommendations.sort(key=lambda x: x["severity"], reverse=True)
        
        return recommendations


class PerformanceReport:
    """
    Generates comprehensive performance reports based on metrics and analysis.
    
    This class takes metrics and bottleneck analysis results and generates
    detailed reports with visualizations and recommendations.
    """
    
    def __init__(self, output_format: str = "html"):
        """
        Initialize the performance report generator.
        
        Args:
            output_format: Format of the report (html, json, etc.)
        """
        self.output_format = output_format
    
    def generate_report(
        self,
        metrics: Dict[str, pd.DataFrame],
        analysis_results: Dict[str, Any],
        test_config: Optional[Dict[str, Any]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> str:
        """
        Generate a performance report.
        
        Args:
            metrics: Dictionary of metric names to DataFrames
            analysis_results: Results from bottleneck analysis
            test_config: Optional test configuration data
            time_range: Optional time range for the report
            
        Returns:
            Report content as string in the specified format
        """
        # Implementation will depend on the output format
        if self.output_format == "html":
            return self._generate_html_report(metrics, analysis_results, test_config, time_range)
        elif self.output_format == "json":
            return self._generate_json_report(metrics, analysis_results, test_config, time_range)
        else:
            raise ValueError(f"Unsupported output format: {self.output_format}")
    
    def _generate_html_report(
        self,
        metrics: Dict[str, pd.DataFrame],
        analysis_results: Dict[str, Any],
        test_config: Optional[Dict[str, Any]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> str:
        """
        Generate an HTML performance report.
        
        Args:
            metrics: Dictionary of metric names to DataFrames
            analysis_results: Results from bottleneck analysis
            test_config: Optional test configuration data
            time_range: Optional time range for the report
            
        Returns:
            HTML report content
        """
        # This is a placeholder for the actual HTML report generation
        # In a real implementation, this would generate a complete HTML report with charts
        
        html = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "    <title>Performance Analysis Report</title>",
            "    <style>",
            "        body { font-family: Arial, sans-serif; margin: 20px; }",
            "        h1 { color: #333; }",
            "        .section { margin-bottom: 20px; }",
            "        .bottleneck { background-color: #ffeeee; padding: 10px; margin: 5px 0; border-radius: 5px; }",
            "        .high { border-left: 5px solid #ff0000; }",
            "        .medium { border-left: 5px solid #ff9900; }",
            "        .low { border-left: 5px solid #ffcc00; }",
            "        table { border-collapse: collapse; width: 100%; }",
            "        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }",
            "        th { background-color: #f2f2f2; }",
            "    </style>",
            "</head>",
            "<body>"
        ]
        
        # Header section
        html.append("<h1>Performance Analysis Report</h1>")
        html.append(f"<p>Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>")
        
        if test_config:
            html.append("<div class='section'>")
            html.append("<h2>Test Configuration</h2>")
            html.append("<table>")
            html.append("<tr><th>Parameter</th><th>Value</th></tr>")
            for key, value in test_config.items():
                html.append(f"<tr><td>{key}</td><td>{value}</td></tr>")
            html.append("</table>")
            html.append("</div>")
        
        # Bottlenecks section
        bottlenecks = analysis_results.get("bottlenecks", [])
        if bottlenecks:
            html.append("<div class='section'>")
            html.append("<h2>Detected Bottlenecks</h2>")
            
            for bottleneck in bottlenecks:
                severity_class = "high" if bottleneck["severity"] > 0.7 else "medium" if bottleneck["severity"] > 0.4 else "low"
                html.append(f"<div class='bottleneck {severity_class}'>")
                html.append(f"<h3>{bottleneck['pattern']}</h3>")
                html.append(f"<p>{bottleneck['description']}</p>")
                html.append("<h4>Recommendations:</h4>")
                html.append("<ul>")
                for rec in bottleneck["recommendations"]:
                    html.append(f"<li>{rec}</li>")
                html.append("</ul>")
                html.append("</div>")
            
            html.append("</div>")
        
        # Correlations section
        correlations = analysis_results.get("correlations", [])
        if correlations:
            html.append("<div class='section'>")
            html.append("<h2>Metric Correlations</h2>")
            html.append("<table>")
            html.append("<tr><th>Metric 1</th><th>Metric 2</th><th>Correlation</th><th>Direction</th></tr>")
            
            for correlation in correlations:
                direction = correlation["direction"]
                strength = correlation["strength"]
                color = "#ff0000" if direction == "positive" else "#0000ff"
                opacity = min(1.0, strength)
                
                html.append("<tr>")
                html.append(f"<td>{correlation['metric1']}</td>")
                html.append(f"<td>{correlation['metric2']}</td>")
                html.append(f"<td style='color: {color}; opacity: {opacity};'>{correlation['correlation']:.3f}</td>")
                html.append(f"<td>{direction}</td>")
                html.append("</tr>")
            
            html.append("</table>")
            html.append("</div>")
        
        # Anomalies section
        anomalies = analysis_results.get("anomalies", [])
        if anomalies:
            html.append("<div class='section'>")
            html.append("<h2>Detected Anomalies</h2>")
            html.append("<table>")
            html.append("<tr><th>Metric</th><th>Timestamp</th><th>Value</th><th>Z-Score</th><th>Direction</th></tr>")
            
            for anomaly in anomalies:
                direction = anomaly["direction"]
                color = "#ff0000" if direction == "high" else "#0000ff"
                
                html.append("<tr>")
                html.append(f"<td>{anomaly['metric']}</td>")
                html.append(f"<td>{anomaly['timestamp']}</td>")
                html.append(f"<td>{anomaly['value']:.3f}</td>")
                html.append(f"<td style='color: {color};'>{anomaly['z_score']:.3f}</td>")
                html.append(f"<td>{direction}</td>")
                html.append("</tr>")
            
            html.append("</table>")
            html.append("</div>")
        
        # Recommendations section
        recommendations = analysis_results.get("recommendations", [])
        if recommendations:
            html.append("<div class='section'>")
            html.append("<h2>Recommendations</h2>")
            html.append("<ul>")
            
            for rec in recommendations:
                severity_class = "high" if rec["severity"] > 0.7 else "medium" if rec["severity"] > 0.4 else "low"
                html.append(f"<li class='{severity_class}'>")
                html.append(f"{rec['recommendation']} <em>({rec['source']})</em>")
                html.append("</li>")
            
            html.append("</ul>")
            html.append("</div>")
        
        # End of HTML
        html.append("</body>")
        html.append("</html>")
        
        return "\n".join(html)
    
    def _generate_json_report(
        self,
        metrics: Dict[str, pd.DataFrame],
        analysis_results: Dict[str, Any],
        test_config: Optional[Dict[str, Any]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> str:
        """
        Generate a JSON performance report.
        
        Args:
            metrics: Dictionary of metric names to DataFrames
            analysis_results: Results from bottleneck analysis
            test_config: Optional test configuration data
            time_range: Optional time range for the report
            
        Returns:
            JSON report content
        """
        import json
        
        # Create a report dictionary
        report = {
            "generated_at": datetime.now().isoformat(),
            "test_config": test_config,
            "time_range": [t.isoformat() for t in time_range] if time_range else None,
            "analysis_results": analysis_results,
            "metrics_summary": {}
        }
        
        # Add summary statistics for each metric
        for metric_name, df in metrics.items():
            if not df.empty:
                report["metrics_summary"][metric_name] = {
                    "min": float(df["value"].min()),
                    "max": float(df["value"].max()),
                    "mean": float(df["value"].mean()),
                    "median": float(df["value"].median()),
                    "std": float(df["value"].std()),
                    "count": int(len(df))
                }
        
        # Convert to JSON string
        return json.dumps(report, indent=2) 