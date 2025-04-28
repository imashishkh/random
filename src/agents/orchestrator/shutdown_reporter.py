"""
Shutdown Reporter for Orchestrator Shutdown

This module provides status reporting and notification mechanisms for the
orchestrator shutdown process.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

from tabulate import tabulate

# Configure logger
logger = logging.getLogger(__name__)

class ShutdownPhase(Enum):
    """Enum representing the phases of the shutdown process."""
    INITIALIZED = "initialized"
    PREPARATION = "preparation"
    CLEANUP = "cleanup"
    VERIFICATION = "verification"
    TERMINATION = "termination"
    COMPLETE = "complete"
    FAILED = "failed"

class ShutdownStatus(Enum):
    """Status of the overall shutdown process."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

class PhaseStatus(Enum):
    """Status of a shutdown phase."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"

class ShutdownReporter:
    """
    Collects, records, and reports information about the shutdown process.
    
    This class is responsible for tracking the progress of shutdown,
    collecting metrics and statuses, and providing reports on the
    shutdown process. It can be used for logging, diagnostics, and
    user feedback during shutdown.
    """
    
    def __init__(self, report_to_file: bool = True, report_dir: Optional[str] = None):
        """
        Initialize the shutdown reporter.
        
        Args:
            report_to_file: Whether to save reports to files
            report_dir: Directory to save report files (default: "./shutdown_reports")
        """
        self.report_to_file = report_to_file
        self.report_dir = report_dir or "./shutdown_reports"
        self.shutdown_start_time: Optional[float] = None
        self.last_report_time: Optional[float] = None
        self.report_count = 0
        self.final_report_generated = False
        
        # Create report directory if needed
        if self.report_to_file and not os.path.exists(self.report_dir):
            try:
                os.makedirs(self.report_dir)
                logger.info(f"Created shutdown report directory: {self.report_dir}")
            except Exception as e:
                logger.error(f"Failed to create shutdown report directory: {str(e)}")
                self.report_to_file = False
        
        self._lock = asyncio.Lock()
        self._current_phase = ShutdownPhase.INITIALIZED
        self._phase_timestamps = {phase: None for phase in ShutdownPhase}
        self._phase_durations = {phase: None for phase in ShutdownPhase}
        self._component_statuses: Dict[str, Dict[str, Any]] = {}
        self._resource_statuses: Dict[str, Dict[str, Any]] = {}
        self._verification_statuses: Dict[str, Dict[str, Any]] = {}
        self._errors: List[Dict[str, Any]] = []
        self._warnings: List[Dict[str, Any]] = []
        self._info_messages: List[Dict[str, Any]] = []
        self._overall_success: Optional[bool] = None
        self._shutdown_reason: Optional[str] = None
        self._abort_reason: Optional[str] = None
        self._custom_metrics: Dict[str, Any] = {}
        self._listeners = set()
        self._cleanup_summary = {}
        self._verification_summary = {}
        self._shutdown_successful = None
        self._shutdown_in_progress = False
        self._shutdown_complete = False
        self._metadata = {}
    
    def start_shutdown_reporting(self) -> None:
        """Mark the start of shutdown reporting."""
        self.shutdown_start_time = time.time()
        self.last_report_time = self.shutdown_start_time
        self.report_count = 0
        self.final_report_generated = False
        
        start_time_str = datetime.fromtimestamp(self.shutdown_start_time).strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Shutdown process started at {start_time_str}")
    
    def generate_text_report(self, status: Dict[str, Any], is_final: bool = False) -> str:
        """
        Generate a human-readable text report.
        
        Args:
            status: Dictionary containing shutdown status
            is_final: Whether this is the final report
            
        Returns:
            Formatted text report
        """
        current_time = time.time()
        elapsed = current_time - (self.shutdown_start_time or current_time)
        
        report = []
        
        # Add header
        if is_final:
            report.append("=== ORCHESTRATOR SHUTDOWN: FINAL REPORT ===")
        else:
            report.append("=== ORCHESTRATOR SHUTDOWN: PROGRESS REPORT ===")
        
        report.append(f"Time elapsed: {elapsed:.2f} seconds")
        
        # Add overall status
        shutdown_complete = status.get("shutdown_complete", False)
        report.append(f"Status: {'COMPLETE' if shutdown_complete else 'IN PROGRESS'}")
        
        # Add component status if available
        if "components" in status:
            comp = status["components"]
            report.append("\nComponent Status:")
            
            component_table = [
                ["Total", comp.get("total", 0)],
                ["Shutdown", comp.get("shutdown", 0)],
                ["Failed", comp.get("failed", 0)],
                ["Pending", comp.get("pending", 0)]
            ]
            report.append(tabulate(component_table, headers=["Status", "Count"]))
            
            # List failed components if any
            failed_list = comp.get("failed_list", [])
            if failed_list:
                report.append("\nFailed Components:")
                for component in failed_list:
                    report.append(f"  - {component}")
            
            # List pending components if any
            pending_list = comp.get("pending_list", [])
            if pending_list:
                report.append("\nPending Components:")
                for component in pending_list:
                    report.append(f"  - {component}")
        
        # Add verification checks if available
        if "verification_checks" in status:
            checks = status["verification_checks"]
            report.append("\nVerification Checks:")
            
            checks_table = [
                ["Total", checks.get("total", 0)],
                ["Passed", checks.get("passed", 0)],
                ["Failed", checks.get("failed", 0)]
            ]
            report.append(tabulate(checks_table, headers=["Status", "Count"]))
            
            # Add checks by category
            if "by_category" in checks:
                report.append("\nChecks by Category:")
                category_rows = []
                
                for category, cat_stats in checks["by_category"].items():
                    category_rows.append([
                        category,
                        cat_stats.get("total", 0),
                        cat_stats.get("passed", 0),
                        cat_stats.get("failed", 0)
                    ])
                
                if category_rows:
                    report.append(tabulate(
                        category_rows, 
                        headers=["Category", "Total", "Passed", "Failed"]
                    ))
        
        # Add errors if available
        if "errors" in status and status["errors"]:
            report.append("\nErrors:")
            for check_id, error_msg in status["errors"].items():
                report.append(f"  - {check_id}: {error_msg}")
        
        # Add shutdown duration if available
        if "shutdown_duration" in status and status["shutdown_duration"] is not None:
            report.append(f"\nShutdown duration: {status['shutdown_duration']:.2f} seconds")
        
        # Add footer for final report
        if is_final:
            if shutdown_complete:
                report.append("\nSHUTDOWN COMPLETED SUCCESSFULLY")
            else:
                report.append("\nSHUTDOWN COMPLETED WITH ERRORS")
        
        return "\n".join(report)
    
    def log_report(self, text_report: str, log_level: int = logging.INFO) -> None:
        """
        Log a report with the specified log level.
        
        Args:
            text_report: Report text to log
            log_level: Logging level to use
        """
        for line in text_report.split("\n"):
            logger.log(log_level, line)
    
    def save_report_to_file(self, 
                           report_data: Dict[str, Any], 
                           text_report: str, 
                           is_final: bool = False) -> Optional[str]:
        """
        Save a report to a file.
        
        Args:
            report_data: Raw report data (for JSON)
            text_report: Formatted text report
            is_final: Whether this is the final report
            
        Returns:
            Path to the saved file, or None if saving failed
        """
        if not self.report_to_file:
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prefix = "final" if is_final else f"progress_{self.report_count:03d}"
            
            # Save text report
            text_filename = os.path.join(self.report_dir, f"{prefix}_shutdown_report_{timestamp}.txt")
            with open(text_filename, "w") as f:
                f.write(text_report)
            
            # Save JSON report
            json_filename = os.path.join(self.report_dir, f"{prefix}_shutdown_report_{timestamp}.json")
            with open(json_filename, "w") as f:
                json.dump(report_data, f, indent=2)
            
            logger.debug(f"Saved shutdown report to {text_filename} and {json_filename}")
            return text_filename
        except Exception as e:
            logger.error(f"Failed to save shutdown report: {str(e)}")
            return None
    
    def report_shutdown_progress(self, 
                               status: Dict[str, Any], 
                               force: bool = False, 
                               min_interval: float = 5.0) -> None:
        """
        Report shutdown progress if enough time has passed since the last report.
        
        Args:
            status: Dictionary containing shutdown status
            force: Whether to force reporting regardless of time interval
            min_interval: Minimum time in seconds between progress reports
        """
        current_time = time.time()
        
        # Check if we should generate a report
        if not force and self.last_report_time is not None:
            time_since_last = current_time - self.last_report_time
            if time_since_last < min_interval:
                return
        
        # Generate and log the report
        text_report = self.generate_text_report(status, is_final=False)
        self.log_report(text_report)
        
        # Save to file if enabled
        if self.report_to_file:
            self.save_report_to_file(status, text_report, is_final=False)
        
        # Update state
        self.last_report_time = current_time
        self.report_count += 1
    
    def report_shutdown_complete(self, status: Dict[str, Any]) -> None:
        """
        Report final shutdown status.
        
        Args:
            status: Dictionary containing final shutdown status
        """
        if self.final_report_generated:
            logger.warning("Final shutdown report already generated, ignoring")
            return
        
        # Generate and log the final report
        text_report = self.generate_text_report(status, is_final=True)
        
        # Use error level if shutdown failed, otherwise info
        log_level = logging.ERROR if not status.get("shutdown_complete", False) else logging.INFO
        self.log_report(text_report, log_level)
        
        # Save to file if enabled
        if self.report_to_file:
            self.save_report_to_file(status, text_report, is_final=True)
        
        # Update state
        self.final_report_generated = True
        
    def get_reporting_stats(self) -> Dict[str, Any]:
        """
        Get statistics about reporting.
        
        Returns:
            Dictionary with reporting statistics
        """
        current_time = time.time()
        
        return {
            "reports_generated": self.report_count,
            "final_report_generated": self.final_report_generated,
            "reporting_duration": (
                current_time - (self.shutdown_start_time or current_time)
                if self.shutdown_start_time is not None
                else None
            ),
            "last_report_time": self.last_report_time,
            "time_since_last_report": (
                current_time - (self.last_report_time or current_time)
                if self.last_report_time is not None
                else None
            )
        }

    async def initialize_shutdown(self, 
                                reason: str, 
                                forced: bool = False,
                                total_steps: int = 0,
                                phases: Optional[List[str]] = None) -> None:
        """
        Initialize the shutdown process for reporting.
        
        Args:
            reason: Reason for shutdown
            forced: Whether shutdown is forced
            total_steps: Total number of steps in shutdown
            phases: List of shutdown phases
        """
        async with self._lock:
            current_time = time.time()
            
            self.status["shutdown_state"] = "in_progress"
            self.status["start_time"] = current_time
            self.status["reason"] = reason
            self.status["forced"] = forced
            
            self.progress["total_steps"] = total_steps
            self.progress["completed_steps"] = 0
            
            if phases:
                self.progress["phases_remaining"] = list(phases)
                if phases:
                    self.progress["current_phase"] = phases[0]
        
        logger.info(
            f"Shutdown initiated: reason='{reason}', "
            f"forced={forced}, total_steps={total_steps}"
        )
        
        # Notify status callbacks
        await self._notify_status_updated()
    
    async def update_progress(self, 
                            steps_completed: Optional[int] = None,
                            current_phase: Optional[str] = None) -> None:
        """
        Update shutdown progress.
        
        Args:
            steps_completed: Number of steps completed (None to increment by 1)
            current_phase: Current shutdown phase (None for no change)
        """
        async with self._lock:
            # Update steps
            if steps_completed is not None:
                self.progress["completed_steps"] = steps_completed
            else:
                self.progress["completed_steps"] += 1
            
            # Ensure we don't exceed total
            self.progress["completed_steps"] = min(
                self.progress["completed_steps"],
                self.progress["total_steps"]
            )
            
            # Update phase if provided
            if current_phase is not None and current_phase != self.progress["current_phase"]:
                if self.progress["current_phase"] and self.progress["current_phase"] not in self.progress["phases_completed"]:
                    self.progress["phases_completed"].append(self.progress["current_phase"])
                
                self.progress["current_phase"] = current_phase
                
                if current_phase in self.progress["phases_remaining"]:
                    self.progress["phases_remaining"].remove(current_phase)
        
        # Calculate percentage
        if self.progress["total_steps"] > 0:
            percent = int(100 * self.progress["completed_steps"] / self.progress["total_steps"])
            logger.info(
                f"Shutdown progress: {percent}% ({self.progress['completed_steps']}/"
                f"{self.progress['total_steps']} steps), phase: {self.progress['current_phase']}"
            )
        else:
            logger.info(f"Shutdown progress: phase={self.progress['current_phase']}")
        
        # Notify status callbacks
        await self._notify_status_updated()
    
    async def record_component_status(self, 
                                    component_id: str, 
                                    status: str,
                                    details: Optional[Dict[str, Any]] = None) -> None:
        """
        Record status of a component during shutdown.
        
        Args:
            component_id: Component identifier
            status: Status string (e.g., 'stopped', 'failed')
            details: Optional details about component status
        """
        async with self._lock:
            self.status["components"][component_id] = {
                "status": status,
                "timestamp": time.time(),
                "details": details or {}
            }
        
        logger.debug(f"Component {component_id} status: {status}")
        
        # No need to notify for every component update
    
    async def record_resource_cleanup(self, 
                                    resource_type: str,
                                    success_count: int,
                                    fail_count: int,
                                    details: Optional[Dict[str, Any]] = None) -> None:
        """
        Record resource cleanup status.
        
        Args:
            resource_type: Type of resource
            success_count: Number of successfully cleaned up resources
            fail_count: Number of failed cleanups
            details: Optional details about resource cleanup
        """
        async with self._lock:
            self.status["resources"][resource_type] = {
                "success_count": success_count,
                "fail_count": fail_count,
                "total": success_count + fail_count,
                "timestamp": time.time(),
                "details": details or {}
            }
        
        logger.info(
            f"Resource cleanup status for {resource_type}: "
            f"{success_count} successful, {fail_count} failed"
        )
        
        # Notify status callbacks
        await self._notify_status_updated()
    
    async def record_error(self, 
                         error_message: str,
                         error_type: str = "general",
                         component_id: Optional[str] = None,
                         exception: Optional[Exception] = None) -> None:
        """
        Record an error during shutdown.
        
        Args:
            error_message: Error message
            error_type: Type of error
            component_id: Component that encountered the error
            exception: Exception object if available
        """
        error_entry = {
            "message": error_message,
            "type": error_type,
            "timestamp": time.time(),
            "component_id": component_id
        }
        
        if exception:
            error_entry["exception"] = str(exception)
            error_entry["exception_type"] = type(exception).__name__
        
        async with self._lock:
            self.status["errors"].append(error_entry)
        
        logger.error(
            f"Shutdown error: {error_message} "
            f"(type: {error_type}, component: {component_id or 'unknown'})"
        )
        
        # Notify status callbacks
        await self._notify_status_updated()
    
    async def complete_shutdown(self, success: bool) -> Dict[str, Any]:
        """
        Mark shutdown as complete and generate final report.
        
        Args:
            success: Whether shutdown was successful
            
        Returns:
            Shutdown status report
        """
        async with self._lock:
            current_time = time.time()
            
            self.status["shutdown_state"] = "completed" if success else "failed"
            self.status["end_time"] = current_time
            self.status["duration"] = current_time - (self.status["start_time"] or current_time)
            self.status["success"] = success
            
            # Ensure all phases are marked as completed
            if self.progress["current_phase"] and self.progress["current_phase"] not in self.progress["phases_completed"]:
                self.progress["phases_completed"].append(self.progress["current_phase"])
            
            # Update progress to 100% if successful
            if success:
                self.progress["completed_steps"] = self.progress["total_steps"]
                self.progress["phases_remaining"] = []
        
        # Generate report
        report = self.generate_report()
        
        # Log completion
        logger.info(
            f"Shutdown {report['shutdown_state']} in {report['duration']:.2f}s "
            f"(success: {success})"
        )
        
        # Save report if directory is set
        if self.report_dir:
            report_path = os.path.join(
                self.report_dir,
                f"shutdown_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            try:
                with open(report_path, 'w') as f:
                    json.dump(report, f, indent=2)
                logger.info(f"Shutdown report saved to {report_path}")
            except Exception as e:
                logger.warning(f"Failed to save shutdown report: {str(e)}")
        
        # Notify completion callbacks
        for callback in self._completion_callbacks:
            try:
                callback(report, success)
            except Exception as e:
                logger.error(f"Error in shutdown completion callback: {str(e)}")
        
        # Notify status callbacks one last time
        await self._notify_status_updated()
        
        return report
    
    def generate_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive shutdown report.
        
        Returns:
            Dictionary containing the shutdown report
        """
        # Create a copy of the status to avoid modification during report generation
        report = {**self.status}
        
        # Add formatted timestamps
        if report["start_time"]:
            report["start_time_iso"] = datetime.fromtimestamp(report["start_time"]).isoformat()
        if report["end_time"]:
            report["end_time_iso"] = datetime.fromtimestamp(report["end_time"]).isoformat()
        
        # Add progress information
        report["progress"] = {**self.progress}
        
        # Add completion percentage
        if self.progress["total_steps"] > 0:
            report["completion_percentage"] = int(
                100 * self.progress["completed_steps"] / self.progress["total_steps"]
            )
        else:
            report["completion_percentage"] = 100 if report["success"] else 0
        
        # Add component summary
        component_statuses = {}
        for component_id, details in report["components"].items():
            status = details["status"]
            component_statuses[status] = component_statuses.get(status, 0) + 1
        
        report["component_summary"] = component_statuses
        
        # Add resource summary
        resource_summary = {
            "total_resources": 0,
            "successful_cleanups": 0,
            "failed_cleanups": 0
        }
        
        for resource_type, details in report["resources"].items():
            resource_summary["total_resources"] += details["total"]
            resource_summary["successful_cleanups"] += details["success_count"]
            resource_summary["failed_cleanups"] += details["fail_count"]
        
        report["resource_summary"] = resource_summary
        
        # Add error summary
        report["error_count"] = len(report["errors"])
        
        return report
    
    def register_status_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a callback for status updates.
        
        Args:
            callback: Function to call with status updates
        """
        self._status_callbacks.append(callback)
        logger.debug(f"Registered status callback (total: {len(self._status_callbacks)})")
    
    def register_completion_callback(self, callback: Callable[[Dict[str, Any], bool], None]) -> None:
        """
        Register a callback for shutdown completion.
        
        Args:
            callback: Function to call when shutdown completes
        """
        self._completion_callbacks.append(callback)
        logger.debug(f"Registered completion callback (total: {len(self._completion_callbacks)})")
    
    async def _notify_status_updated(self) -> None:
        """Notify all status callbacks of updated status."""
        if not self._status_callbacks:
            return
        
        # Create a copy of the status for callbacks
        status_copy = self.generate_report()
        
        # Notify callbacks
        for callback in self._status_callbacks:
            try:
                callback(status_copy)
            except Exception as e:
                logger.error(f"Error in status callback: {str(e)}")
    
    def record_shutdown_start(self) -> None:
        """Record the start of the shutdown process."""
        self.shutdown_start_time = time.time()
        self.add_event("shutdown_started", "Orchestrator shutdown initiated")
        logger.info("Shutdown process started")
    
    def record_shutdown_end(self, success: bool) -> None:
        """
        Record the end of the shutdown process.
        
        Args:
            success: Whether shutdown completed successfully
        """
        self.shutdown_end_time = time.time()
        self.shutdown_successful = success
        
        if success:
            self.add_event("shutdown_completed", "Orchestrator shutdown completed successfully")
            logger.info("Shutdown process completed successfully")
        else:
            self.add_event("shutdown_failed", "Orchestrator shutdown completed with errors")
            logger.warning("Shutdown process completed with errors")
        
        # Calculate total shutdown duration
        if self.shutdown_start_time is not None:
            duration = self.shutdown_end_time - self.shutdown_start_time
            self.add_metric("timings", "total_shutdown_duration", duration)
    
    def add_event(self, event_type: str, message: str, **kwargs) -> None:
        """
        Add an event to the shutdown report.
        
        Args:
            event_type: Type of the event
            message: Human-readable description of the event
            **kwargs: Additional event data
        """
        event = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "type": event_type,
            "message": message,
            **kwargs
        }
        
        self.events.append(event)
        logger.debug(f"Shutdown event: {event_type} - {message}")
    
    def add_error(self, component: str, error_type: str, message: str, 
                 exception: Optional[Exception] = None, **kwargs) -> None:
        """
        Add an error to the shutdown report.
        
        Args:
            component: Component that encountered the error
            error_type: Type of error
            message: Human-readable error message
            exception: The actual exception, if any
            **kwargs: Additional error data
        """
        error = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "component": component,
            "type": error_type,
            "message": message,
            **kwargs
        }
        
        if exception:
            error["exception"] = str(exception)
            error["exception_type"] = type(exception).__name__
        
        self.errors.append(error)
        
        log_msg = f"Shutdown error in {component}: {message}"
        if exception:
            log_msg += f" ({type(exception).__name__}: {str(exception)})"
        
        logger.error(log_msg)
        
        self.add_event("error_occurred", f"Error in {component}: {error_type}", 
                       component=component, error_type=error_type)
    
    def add_metric(self, category: str, name: str, value: Any) -> None:
        """
        Add a metric to the shutdown report.
        
        Args:
            category: Category of the metric (e.g., 'timings', 'counts', 'resources')
            name: Name of the metric
            value: Value of the metric
        """
        if category not in self.metrics:
            self.metrics[category] = {}
        
        self.metrics[category][name] = value
        logger.debug(f"Shutdown metric: {category}.{name} = {value}")
    
    def record_component_shutdown(self, component_type: str, component_id: str, 
                                 success: bool, duration: float) -> None:
        """
        Record the shutdown of a component.
        
        Args:
            component_type: Type of component (e.g., 'service', 'agent')
            component_id: Identifier of the component
            success: Whether shutdown was successful
            duration: Time taken to shut down in seconds
        """
        # Count component shutdowns by type and status
        category = f"{component_type}s"
        if category not in self.metrics["counts"]:
            self.metrics["counts"][category] = {"total": 0, "success": 0, "failed": 0}
        
        self.metrics["counts"][category]["total"] += 1
        if success:
            self.metrics["counts"][category]["success"] += 1
        else:
            self.metrics["counts"][category]["failed"] += 1
        
        # Record timing
        if category not in self.metrics["timings"]:
            self.metrics["timings"][category] = {
                "total_duration": 0.0,
                "max_duration": 0.0,
                "count": 0
            }
        
        self.metrics["timings"][category]["total_duration"] += duration
        self.metrics["timings"][category]["count"] += 1
        self.metrics["timings"][category]["max_duration"] = max(
            self.metrics["timings"][category]["max_duration"], duration
        )
        
        # Record individual component metrics
        self.metrics["timings"][f"{component_type}_{component_id}"] = duration
        
        # Add event
        event_type = f"{component_type}_shutdown"
        status = "succeeded" if success else "failed"
        self.add_event(
            event_type,
            f"{component_type.capitalize()} '{component_id}' shutdown {status} in {duration:.2f}s",
            component_type=component_type,
            component_id=component_id,
            success=success,
            duration=duration
        )
    
    def record_resource_cleanup(self, category: str, resource_id: str, 
                               success: bool, duration: float) -> None:
        """
        Record the cleanup of a resource.
        
        Args:
            category: Category of the resource
            resource_id: Identifier of the resource
            success: Whether cleanup was successful
            duration: Time taken for cleanup in seconds
        """
        # Count resource cleanups by category and status
        if category not in self.metrics["resources"]:
            self.metrics["resources"][category] = {
                "total": 0, "success": 0, "failed": 0, "total_duration": 0.0
            }
        
        self.metrics["resources"][category]["total"] += 1
        if success:
            self.metrics["resources"][category]["success"] += 1
        else:
            self.metrics["resources"][category]["failed"] += 1
        
        self.metrics["resources"][category]["total_duration"] += duration
        
        # Add event
        status = "succeeded" if success else "failed"
        self.add_event(
            "resource_cleanup",
            f"Resource cleanup for '{resource_id}' ({category}) {status} in {duration:.2f}s",
            category=category,
            resource_id=resource_id,
            success=success,
            duration=duration
        )
    
    def get_summary_report(self) -> Dict[str, Any]:
        """
        Get a summary report of the shutdown process.
        
        Returns:
            Dict containing a summary of the shutdown process
        """
        # Calculate averages where appropriate
        for category, data in self.metrics["timings"].items():
            if isinstance(data, dict) and "total_duration" in data and "count" in data and data["count"] > 0:
                data["average_duration"] = data["total_duration"] / data["count"]
        
        shutdown_duration = None
        if self.shutdown_start_time is not None and self.shutdown_end_time is not None:
            shutdown_duration = self.shutdown_end_time - self.shutdown_start_time
        
        # Count events by type
        event_counts = {}
        for event in self.events:
            event_type = event["type"]
            if event_type not in event_counts:
                event_counts[event_type] = 0
            event_counts[event_type] += 1
        
        return {
            "status": "completed" if self.shutdown_successful else "failed" if self.shutdown_successful is not None else "in_progress",
            "start_time": datetime.fromtimestamp(self.shutdown_start_time).isoformat() if self.shutdown_start_time else None,
            "end_time": datetime.fromtimestamp(self.shutdown_end_time).isoformat() if self.shutdown_end_time else None,
            "duration_seconds": shutdown_duration,
            "error_count": len(self.errors),
            "event_count": len(self.events),
            "event_types": event_counts,
            "resource_summary": self.metrics["resources"],
            "component_summary": {
                k: v for k, v in self.metrics["counts"].items() 
                if k in ["services", "agents", "connections"]
            },
            "timing_summary": {
                k: {
                    kk: vv for kk, vv in v.items() 
                    if kk in ["average_duration", "max_duration", "count"]
                } 
                for k, v in self.metrics["timings"].items() 
                if isinstance(v, dict) and "count" in v and v["count"] > 0
            }
        }
    
    def get_detailed_report(self) -> Dict[str, Any]:
        """
        Get a detailed report of the shutdown process.
        
        Returns:
            Dict containing detailed information about the shutdown process
        """
        summary = self.get_summary_report()
        
        return {
            **summary,
            "events": self.events,
            "errors": self.errors,
            "metrics": self.metrics
        }
    
    def log_summary(self) -> None:
        """Log a summary of the shutdown process."""
        if self.shutdown_start_time is None:
            logger.warning("Cannot log shutdown summary - shutdown was never started")
            return
        
        summary = self.get_summary_report()
        
        if summary["status"] == "completed":
            logger.info(f"Shutdown completed successfully in {summary['duration_seconds']:.2f}s")
        elif summary["status"] == "failed":
            logger.warning(f"Shutdown completed with errors in {summary['duration_seconds']:.2f}s")
        else:
            logger.warning("Shutdown is still in progress")
        
        # Log component summary
        for component_type, counts in summary.get("component_summary", {}).items():
            logger.info(f"  {component_type}: {counts['success']}/{counts['total']} successful")
        
        # Log resource summary
        for category, data in summary.get("resource_summary", {}).items():
            logger.info(f"  {category} resources: {data['success']}/{data['total']} successful")
        
        # Log error summary if there are errors
        if summary["error_count"] > 0:
            logger.warning(f"  {summary['error_count']} errors occurred during shutdown")

    async def set_phase(self, phase: ShutdownPhase) -> None:
        """
        Set the current shutdown phase.
        
        Args:
            phase: The new phase to set
        """
        async with self._lock:
            # Record end time for previous phase
            if self._current_phase != ShutdownPhase.INITIALIZED:
                end_time = time.time()
                start_time = self._phase_timestamps.get(self._current_phase)
                if start_time:
                    self._phase_durations[self._current_phase] = end_time - start_time
            
            # If this is the first phase transition (to something other than INITIALIZED),
            # record the overall shutdown start time
            if self._current_phase == ShutdownPhase.INITIALIZED and phase != ShutdownPhase.INITIALIZED:
                self._shutdown_start_time = time.time()
            
            # Record start time for new phase
            self._phase_timestamps[phase] = time.time()
            previous_phase = self._current_phase
            self._current_phase = phase
            
            # If moving to a completion phase, record the overall shutdown end time
            if phase in [ShutdownPhase.COMPLETE, ShutdownPhase.FAILED]:
                self._shutdown_end_time = time.time()
                
                # Set overall success based on phase
                if phase == ShutdownPhase.COMPLETE:
                    self._overall_success = True
                elif phase == ShutdownPhase.FAILED:
                    self._overall_success = False
                # For COMPLETE, overall_success might be None or set explicitly elsewhere
            
            logger.info(f"Shutdown phase changed from {previous_phase.value} to {phase.value}")
    
    async def set_shutdown_reason(self, reason: str) -> None:
        """
        Set the reason for the shutdown.
        
        Args:
            reason: The reason for initiating shutdown
        """
        async with self._lock:
            self._shutdown_reason = reason
            logger.info(f"Shutdown reason: {reason}")
    
    async def set_abort_reason(self, reason: str) -> None:
        """
        Set the reason for aborting the shutdown.
        
        Args:
            reason: The reason for aborting the shutdown
        """
        async with self._lock:
            self._abort_reason = reason
            logger.warning(f"Shutdown aborted: {reason}")
    
    async def update_component_status(self, 
                                    component_id: str, 
                                    status: str, 
                                    metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Update the status of a component during shutdown.
        
        Args:
            component_id: Identifier for the component
            status: Current status (e.g., 'stopping', 'stopped', 'failed')
            metadata: Additional information about the component status
        """
        async with self._lock:
            # Create a timestamp for the status update
            timestamp = time.time()
            
            # Update or create component status
            if component_id not in self._component_statuses:
                self._component_statuses[component_id] = {
                    "current_status": status,
                    "history": [],
                    "first_update_time": timestamp,
                    "last_update_time": timestamp
                }
            else:
                self._component_statuses[component_id]["current_status"] = status
                self._component_statuses[component_id]["last_update_time"] = timestamp
            
            # Add to status history
            history_entry = {
                "timestamp": timestamp,
                "status": status,
                "metadata": metadata or {}
            }
            self._component_statuses[component_id]["history"].append(history_entry)
            
            log_level = logging.INFO
            if status == "failed":
                log_level = logging.ERROR
            elif status in ["warning", "degraded"]:
                log_level = logging.WARNING
                
            logger.log(log_level, f"Component {component_id} status: {status}")
    
    async def update_resource_status(self, 
                                   resource_id: str, 
                                   status: str, 
                                   resource_type: Optional[str] = None,
                                   metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Update the status of a resource during cleanup.
        
        Args:
            resource_id: Identifier for the resource
            status: Current status (e.g., 'cleaning', 'released', 'failed')
            resource_type: Type of the resource (e.g., 'database', 'file')
            metadata: Additional information about the resource status
        """
        async with self._lock:
            # Create a timestamp for the status update
            timestamp = time.time()
            
            # Update or create resource status
            if resource_id not in self._resource_statuses:
                self._resource_statuses[resource_id] = {
                    "current_status": status,
                    "resource_type": resource_type,
                    "history": [],
                    "first_update_time": timestamp,
                    "last_update_time": timestamp
                }
            else:
                self._resource_statuses[resource_id]["current_status"] = status
                self._resource_statuses[resource_id]["last_update_time"] = timestamp
                if resource_type and "resource_type" not in self._resource_statuses[resource_id]:
                    self._resource_statuses[resource_id]["resource_type"] = resource_type
            
            # Add to status history
            history_entry = {
                "timestamp": timestamp,
                "status": status,
                "metadata": metadata or {}
            }
            self._resource_statuses[resource_id]["history"].append(history_entry)
            
            log_level = logging.INFO
            if status == "failed":
                log_level = logging.ERROR
            elif status in ["warning", "partial"]:
                log_level = logging.WARNING
                
            logger.log(log_level, f"Resource {resource_id} status: {status}")
    
    async def update_verification_status(self, 
                                       check_id: str, 
                                       status: str, 
                                       metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Update the status of a verification check.
        
        Args:
            check_id: Identifier for the verification check
            status: Current status (e.g., 'running', 'passed', 'failed')
            metadata: Additional information about the verification status
        """
        async with self._lock:
            # Create a timestamp for the status update
            timestamp = time.time()
            
            # Update or create verification status
            if check_id not in self._verification_statuses:
                self._verification_statuses[check_id] = {
                    "current_status": status,
                    "history": [],
                    "first_update_time": timestamp,
                    "last_update_time": timestamp
                }
            else:
                self._verification_statuses[check_id]["current_status"] = status
                self._verification_statuses[check_id]["last_update_time"] = timestamp
            
            # Add to status history
            history_entry = {
                "timestamp": timestamp,
                "status": status,
                "metadata": metadata or {}
            }
            self._verification_statuses[check_id]["history"].append(history_entry)
            
            log_level = logging.INFO
            if status == "failed":
                log_level = logging.ERROR
            elif status in ["warning", "timeout"]:
                log_level = logging.WARNING
                
            logger.log(log_level, f"Verification check {check_id} status: {status}")
    
    async def add_error(self, 
                      message: str, 
                      component_id: Optional[str] = None, 
                      details: Optional[Dict[str, Any]] = None) -> None:
        """
        Record an error that occurred during shutdown.
        
        Args:
            message: Error message
            component_id: Optional identifier for the component that generated the error
            details: Additional details about the error
        """
        async with self._lock:
            error_entry = {
                "timestamp": time.time(),
                "message": message,
                "component_id": component_id,
                "details": details or {},
                "phase": self._current_phase.value
            }
            self._errors.append(error_entry)
            
            logger.error(f"Shutdown error: {message}" + 
                       f" [component: {component_id}]" if component_id else "")
    
    async def add_warning(self, 
                        message: str, 
                        component_id: Optional[str] = None, 
                        details: Optional[Dict[str, Any]] = None) -> None:
        """
        Record a warning that occurred during shutdown.
        
        Args:
            message: Warning message
            component_id: Optional identifier for the component that generated the warning
            details: Additional details about the warning
        """
        async with self._lock:
            warning_entry = {
                "timestamp": time.time(),
                "message": message,
                "component_id": component_id,
                "details": details or {},
                "phase": self._current_phase.value
            }
            self._warnings.append(warning_entry)
            
            logger.warning(f"Shutdown warning: {message}" + 
                         f" [component: {component_id}]" if component_id else "")
    
    async def add_info(self, 
                     message: str, 
                     component_id: Optional[str] = None, 
                     details: Optional[Dict[str, Any]] = None) -> None:
        """
        Record an informational message during shutdown.
        
        Args:
            message: Informational message
            component_id: Optional identifier for the component that generated the message
            details: Additional details
        """
        async with self._lock:
            info_entry = {
                "timestamp": time.time(),
                "message": message,
                "component_id": component_id,
                "details": details or {},
                "phase": self._current_phase.value
            }
            self._info_messages.append(info_entry)
            
            logger.info(f"Shutdown info: {message}" + 
                      f" [component: {component_id}]" if component_id else "")
    
    async def set_custom_metric(self, key: str, value: Any) -> None:
        """
        Set a custom metric for the shutdown process.
        
        Args:
            key: Metric name/key
            value: Metric value
        """
        async with self._lock:
            self._custom_metrics[key] = value
            logger.debug(f"Shutdown metric {key}: {value}")
    
    async def get_current_phase(self) -> ShutdownPhase:
        """
        Get the current shutdown phase.
        
        Returns:
            Current shutdown phase
        """
        async with self._lock:
            return self._current_phase
    
    async def get_component_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the current status of all components.
        
        Returns:
            Dictionary of component statuses
        """
        async with self._lock:
            return self._component_statuses.copy()
    
    async def get_resource_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the current status of all resources.
        
        Returns:
            Dictionary of resource statuses
        """
        async with self._lock:
            return self._resource_statuses.copy()
    
    async def get_verification_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the current status of all verification checks.
        
        Returns:
            Dictionary of verification check statuses
        """
        async with self._lock:
            return self._verification_statuses.copy()
    
    async def get_errors(self) -> List[Dict[str, Any]]:
        """
        Get all recorded errors.
        
        Returns:
            List of error entries
        """
        async with self._lock:
            return self._errors.copy()
    
    async def get_warnings(self) -> List[Dict[str, Any]]:
        """
        Get all recorded warnings.
        
        Returns:
            List of warning entries
        """
        async with self._lock:
            return self._warnings.copy()
    
    async def get_info_messages(self) -> List[Dict[str, Any]]:
        """
        Get all recorded info messages.
        
        Returns:
            List of info message entries
        """
        async with self._lock:
            return self._info_messages.copy()
    
    async def get_custom_metrics(self) -> Dict[str, Any]:
        """
        Get all custom metrics.
        
        Returns:
            Dictionary of custom metrics
        """
        async with self._lock:
            return self._custom_metrics.copy()
    
    def get_shutdown_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive report of the shutdown process.
        
        Returns:
            Dictionary with comprehensive shutdown information
        """
        # Calculate phase durations
        phase_durations = {}
        for phase, start_time in self._phase_timestamps.items():
            if phase in self._phase_durations:
                phase_durations[phase.value] = self._phase_durations[phase]
            elif phase == self._current_phase:
                phase_durations[phase.value] = time.time() - start_time
        
        # Count component statuses
        component_status_counts = {}
        for component in self._component_statuses.values():
            status = component["current_status"]
            component_status_counts[status] = component_status_counts.get(status, 0) + 1
        
        # Count resource statuses
        resource_status_counts = {}
        for resource in self._resource_statuses.values():
            status = resource["current_status"]
            resource_status_counts[status] = resource_status_counts.get(status, 0) + 1
        
        # Count verification statuses
        verification_status_counts = {}
        for verification in self._verification_statuses.values():
            status = verification["current_status"]
            verification_status_counts[status] = verification_status_counts.get(status, 0) + 1
        
        # Calculate total shutdown duration
        total_duration = None
        if self._shutdown_start_time is not None:
            if self._shutdown_end_time is not None:
                total_duration = self._shutdown_end_time - self._shutdown_start_time
            else:
                total_duration = time.time() - self._shutdown_start_time
        
        # Build the report
        report = {
            "current_phase": self._current_phase.value,
            "overall_success": self._overall_success,
            "shutdown_reason": self._shutdown_reason,
            "abort_reason": self._abort_reason,
            "start_time": self._shutdown_start_time,
            "end_time": self._shutdown_end_time,
            "total_duration": total_duration,
            "phase_durations": phase_durations,
            "components": {
                "total": len(self._component_statuses),
                "status_counts": component_status_counts
            },
            "resources": {
                "total": len(self._resource_statuses),
                "status_counts": resource_status_counts
            },
            "verification": {
                "total": len(self._verification_statuses),
                "status_counts": verification_status_counts
            },
            "errors": {
                "total": len(self._errors),
                "messages": [error["message"] for error in self._errors]
            },
            "warnings": {
                "total": len(self._warnings),
                "messages": [warning["message"] for warning in self._warnings]
            },
            "custom_metrics": self._custom_metrics
        }
        
        return report
    
    async def log_shutdown_summary(self) -> None:
        """Log a summary of the shutdown process."""
        report = self.get_shutdown_report()
        
        # Determine summary text based on success
        if report["overall_success"] is True:
            summary = "Shutdown completed successfully"
        elif report["overall_success"] is False:
            summary = "Shutdown failed"
        else:
            summary = "Shutdown aborted or incomplete"
        
        # Add duration if available
        if report["total_duration"] is not None:
            summary += f" in {report['total_duration']:.2f} seconds"
        
        # Add counts
        summary += f" ({report['components']['total']} components, {report['resources']['total']} resources)"
        
        # Log errors and warnings if any
        if report["errors"]["total"] > 0:
            summary += f", {report['errors']['total']} errors"
        
        if report["warnings"]["total"] > 0:
            summary += f", {report['warnings']['total']} warnings"
        
        # Log the summary
        if report["overall_success"] is True:
            logger.info(summary)
        elif report["overall_success"] is False:
            logger.error(summary)
        else:
            logger.warning(summary)
        
        # Log phase durations
        for phase, duration in report["phase_durations"].items():
            logger.info(f"Shutdown phase {phase} took {duration:.2f} seconds")
        
        # Log errors
        if report["errors"]["total"] > 0:
            logger.error(f"Shutdown errors ({report['errors']['total']}):")
            for i, error in enumerate(self._errors):
                logger.error(f"  {i+1}. {error['message']}" + 
                           f" [component: {error['component_id']}]" if error["component_id"] else "")
        
        # Log warnings
        if report["warnings"]["total"] > 0:
            logger.warning(f"Shutdown warnings ({report['warnings']['total']}):")
            for i, warning in enumerate(self._warnings):
                logger.warning(f"  {i+1}. {warning['message']}" + 
                             f" [component: {warning['component_id']}]" if warning["component_id"] else "")

    async def start_shutdown(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Mark the start of the shutdown process.
        
        Args:
            metadata: Additional information about the shutdown
        """
        async with self._lock:
            self._shutdown_start_time = time.time()
            self._shutdown_in_progress = True
            self._current_phase = ShutdownPhase.PREPARATION
            self._phase_timestamps[ShutdownPhase.INITIALIZED] = self._shutdown_start_time
            self._phase_timestamps[ShutdownPhase.PREPARATION] = self._shutdown_start_time
            
            if metadata:
                self._metadata.update(metadata)
            
            logger.info("Shutdown process started")
    
    async def update_phase(self, phase: Union[str, ShutdownPhase]) -> None:
        """
        Update the current shutdown phase.
        
        Args:
            phase: New phase to set
        """
        if isinstance(phase, str):
            try:
                phase = ShutdownPhase(phase)
            except ValueError:
                logger.warning(f"Invalid shutdown phase: {phase}")
                return
        
        async with self._lock:
            # Calculate duration for previous phase
            if self._current_phase is not None:
                prev_start = self._phase_timestamps.get(self._current_phase)
                if prev_start is not None:
                    self._phase_durations[self._current_phase] = time.time() - prev_start
            
            # Update current phase
            self._current_phase = phase
            self._phase_timestamps[phase] = time.time()
            
            # Mark as complete if complete
            if phase == ShutdownPhase.COMPLETE:
                await self.complete_shutdown(success=True)
            elif phase == ShutdownPhase.FAILED:
                await self.complete_shutdown(success=False)
                
            logger.info(f"Shutdown phase updated: {phase.value}")
            
            # Notify listeners
            await self._notify_listeners()
    
    async def complete_shutdown(self, success: bool) -> None:
        """
        Mark the shutdown process as complete.
        
        Args:
            success: Whether the shutdown was successful
        """
        async with self._lock:
            if self._shutdown_complete:
                return
            
            self._shutdown_end_time = time.time()
            self._shutdown_in_progress = False
            self._shutdown_complete = True
            self._shutdown_successful = success
            
            # Calculate final phase duration
            if self._current_phase is not None:
                phase_start = self._phase_timestamps.get(self._current_phase)
                if phase_start is not None:
                    self._phase_durations[self._current_phase] = time.time() - phase_start
            
            logger.info(f"Shutdown process completed: {'successful' if success else 'failed'}")
            
            # Notify listeners
            await self._notify_listeners()
    
    async def update_resource_cleanup_status(self, 
                                           resource_id: str, 
                                           status: str, 
                                           details: Optional[str] = None,
                                           duration: Optional[float] = None) -> None:
        """
        Update the status of a resource cleanup operation.
        
        Args:
            resource_id: ID of the resource
            status: New status value
            details: Additional details about the status
            duration: Duration of the cleanup operation in seconds
        """
        async with self._lock:
            # Create or update resource status
            if resource_id not in self._resource_statuses:
                self._resource_statuses[resource_id] = {
                    "status": status,
                    "details": details,
                    "duration": duration,
                    "timestamp": time.time(),
                    "history": []
                }
            else:
                # Add current status to history
                current = self._resource_statuses[resource_id]
                current["history"].append({
                    "status": current["status"],
                    "details": current["details"],
                    "timestamp": current["timestamp"]
                })
                
                # Update to new status
                current["status"] = status
                current["details"] = details
                current["duration"] = duration
                current["timestamp"] = time.time()
            
            # Notify listeners
            await self._notify_listeners()
    
    async def update_verification_status(self,
                                       check_name: str,
                                       status: str,
                                       details: Optional[str] = None,
                                       duration: Optional[float] = None) -> None:
        """
        Update the status of a verification check.
        
        Args:
            check_name: Name of the verification check
            status: New status value
            details: Additional details about the status
            duration: Duration of the verification check in seconds
        """
        async with self._lock:
            # Create or update verification status
            if check_name not in self._verification_statuses:
                self._verification_statuses[check_name] = {
                    "status": status,
                    "details": details,
                    "duration": duration,
                    "timestamp": time.time(),
                    "history": []
                }
            else:
                # Add current status to history
                current = self._verification_statuses[check_name]
                current["history"].append({
                    "status": current["status"],
                    "details": current["details"],
                    "timestamp": current["timestamp"]
                })
                
                # Update to new status
                current["status"] = status
                current["details"] = details
                current["duration"] = duration
                current["timestamp"] = time.time()
            
            # Notify listeners
            await self._notify_listeners()
    
    async def update_cleanup_summary(self, summary: Dict[str, Any]) -> None:
        """
        Update the resource cleanup summary.
        
        Args:
            summary: Summary information about the resource cleanup
        """
        async with self._lock:
            self._cleanup_summary = summary
            
            # Notify listeners
            await self._notify_listeners()
    
    async def update_verification_summary(self, summary: Dict[str, Any]) -> None:
        """
        Update the verification summary.
        
        Args:
            summary: Summary information about the verification checks
        """
        async with self._lock:
            self._verification_summary = summary
            
            # Notify listeners
            await self._notify_listeners()
    
    async def report_error(self, error: Union[str, Exception], details: Optional[str] = None) -> None:
        """
        Report an error during shutdown.
        
        Args:
            error: Error message or exception
            details: Additional details about the error
        """
        error_msg = str(error)
        
        async with self._lock:
            self._errors.append({
                "message": error_msg,
                "details": details,
                "timestamp": time.time()
            })
            
            logger.error(f"Shutdown error: {error_msg}")
            
            # Notify listeners
            await self._notify_listeners()
    
    async def add_listener(self, listener: Any) -> None:
        """
        Add a listener for shutdown updates.
        
        Args:
            listener: Object with an update_shutdown_status method
        """
        if not hasattr(listener, "update_shutdown_status"):
            logger.warning("Listener must have an update_shutdown_status method")
            return
        
        async with self._lock:
            self._listeners.add(listener)
    
    async def remove_listener(self, listener: Any) -> bool:
        """
        Remove a listener.
        
        Args:
            listener: Listener to remove
            
        Returns:
            True if removed, False if not found
        """
        async with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)
                return True
            
            return False
    
    async def _notify_listeners(self) -> None:
        """Notify all listeners of a status update."""
        # Get current status
        status = await self.get_shutdown_status()
        
        # Call listeners one by one to avoid one failure affecting others
        for listener in list(self._listeners):
            try:
                await listener.update_shutdown_status(status)
            except Exception as e:
                logger.warning(f"Error notifying listener: {str(e)}")
    
    async def get_shutdown_status(self) -> Dict[str, Any]:
        """
        Get the current shutdown status.
        
        Returns:
            Dictionary with shutdown status information
        """
        async with self._lock:
            # Calculate shutdown duration
            duration = None
            if self._shutdown_start_time is not None:
                if self._shutdown_end_time is not None:
                    duration = self._shutdown_end_time - self._shutdown_start_time
                else:
                    duration = time.time() - self._shutdown_start_time
            
            # Build status dict
            return {
                "in_progress": self._shutdown_in_progress,
                "complete": self._shutdown_complete,
                "successful": self._shutdown_successful,
                "current_phase": self._current_phase.value,
                "start_time": self._shutdown_start_time,
                "end_time": self._shutdown_end_time,
                "duration": duration,
                "phase_timestamps": {phase.value: ts for phase, ts in self._phase_timestamps.items() if ts is not None},
                "phase_durations": {phase.value: dur for phase, dur in self._phase_durations.items() if dur is not None},
                "resource_cleanup": self._resource_statuses,
                "verification": self._verification_statuses,
                "errors": self._errors,
                "cleanup_summary": self._cleanup_summary,
                "verification_summary": self._verification_summary,
                "metadata": self._metadata
            } 