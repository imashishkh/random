"""
System metrics collector for Prometheus.

This module provides a collector for system resource metrics like CPU,
memory, disk, and network usage.
"""

import logging
import os
import time
import platform
import psutil
from typing import Dict, List, Any

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

from .collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)


class SystemCollector(BaseCollector):
    """
    Collector for system resource metrics.
    
    This collector gathers metrics about system resources, including:
    - CPU usage and load
    - Memory usage
    - Disk usage and I/O
    - Network usage
    - Process information
    """
    
    def __init__(self, process_name: str = None, collection_interval: float = 15.0):
        """
        Initialize the system collector.
        
        Args:
            process_name: Optional name of specific process to monitor
            collection_interval: Interval in seconds between metric collection
        """
        super().__init__(collection_interval=collection_interval)
        self.process_name = process_name
        self.process = None
        self.hostname = platform.node()
        
        # Find our process if name provided
        if self.process_name:
            self._find_process()
    
    def _find_process(self):
        """Find the process to monitor by name."""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if self.process_name in proc.info['name']:
                    self.process = psutil.Process(proc.info['pid'])
                    logger.info(f"Monitoring process: {self.process_name} (PID: {self.process.pid})")
                    return
            logger.warning(f"Process not found: {self.process_name}")
        except Exception as e:
            logger.error(f"Error finding process: {str(e)}")
    
    def collect_metrics(self) -> List[Any]:
        """
        Collect system metrics.
        
        Returns:
            List of metrics for Prometheus
        """
        metrics = []
        
        # CPU metrics
        metrics.extend(self._collect_cpu_metrics())
        
        # Memory metrics
        metrics.extend(self._collect_memory_metrics())
        
        # Disk metrics
        metrics.extend(self._collect_disk_metrics())
        
        # Network metrics
        metrics.extend(self._collect_network_metrics())
        
        # Process metrics (if monitoring a specific process)
        if self.process_name:
            # Check if process still exists, try to find it again if not
            if not self.process or not self.process.is_running():
                self._find_process()
            
            if self.process:
                metrics.extend(self._collect_process_metrics())
        
        # Add collector's own metrics
        metrics.extend(self.get_collector_metrics())
        
        return metrics
    
    def _collect_cpu_metrics(self) -> List[Any]:
        """
        Collect CPU metrics.
        
        Returns:
            List of CPU metrics
        """
        metrics = []
        
        # CPU usage percentage
        cpu_percent_gauge = GaugeMetricFamily(
            'system_cpu_usage_percent',
            'System CPU usage percentage per CPU',
            labels=['hostname', 'cpu']
        )
        
        # Overall CPU usage
        overall_cpu_gauge = GaugeMetricFamily(
            'system_overall_cpu_usage_percent',
            'Overall system CPU usage percentage',
            labels=['hostname']
        )
        
        # CPU load averages
        load_avg_gauge = GaugeMetricFamily(
            'system_load_average',
            'System load average',
            labels=['hostname', 'period']
        )
        
        try:
            # Per-CPU usage
            per_cpu_percent = psutil.cpu_percent(interval=0.1, percpu=True)
            for i, percent in enumerate(per_cpu_percent):
                cpu_percent_gauge.add_metric([self.hostname, f"cpu{i}"], percent)
            
            # Overall CPU usage
            overall_cpu = psutil.cpu_percent(interval=0.1)
            overall_cpu_gauge.add_metric([self.hostname], overall_cpu)
            
            # Load averages (1, 5, 15 minute)
            if platform.system() != "Windows":  # Load avg not available on Windows
                load_avg = os.getloadavg()
                load_avg_gauge.add_metric([self.hostname, "1min"], load_avg[0])
                load_avg_gauge.add_metric([self.hostname, "5min"], load_avg[1])
                load_avg_gauge.add_metric([self.hostname, "15min"], load_avg[2])
        except Exception as e:
            logger.error(f"Error collecting CPU metrics: {str(e)}")
        
        metrics.append(cpu_percent_gauge)
        metrics.append(overall_cpu_gauge)
        
        if platform.system() != "Windows":
            metrics.append(load_avg_gauge)
        
        return metrics
    
    def _collect_memory_metrics(self) -> List[Any]:
        """
        Collect memory metrics.
        
        Returns:
            List of memory metrics
        """
        metrics = []
        
        # Virtual memory metrics
        vm_gauge = GaugeMetricFamily(
            'system_virtual_memory_bytes',
            'System virtual memory information in bytes',
            labels=['hostname', 'type']
        )
        
        # Swap memory metrics
        swap_gauge = GaugeMetricFamily(
            'system_swap_memory_bytes',
            'System swap memory information in bytes',
            labels=['hostname', 'type']
        )
        
        # Memory usage percentage
        mem_percent_gauge = GaugeMetricFamily(
            'system_memory_usage_percent',
            'System memory usage percentage',
            labels=['hostname', 'type']
        )
        
        try:
            # Virtual memory
            vm = psutil.virtual_memory()
            vm_gauge.add_metric([self.hostname, "total"], vm.total)
            vm_gauge.add_metric([self.hostname, "available"], vm.available)
            vm_gauge.add_metric([self.hostname, "used"], vm.used)
            vm_gauge.add_metric([self.hostname, "free"], vm.free)
            
            # Memory percentage
            mem_percent_gauge.add_metric([self.hostname, "virtual"], vm.percent)
            
            # Swap memory
            swap = psutil.swap_memory()
            swap_gauge.add_metric([self.hostname, "total"], swap.total)
            swap_gauge.add_metric([self.hostname, "used"], swap.used)
            swap_gauge.add_metric([self.hostname, "free"], swap.free)
            
            # Swap percentage
            mem_percent_gauge.add_metric([self.hostname, "swap"], swap.percent)
            
        except Exception as e:
            logger.error(f"Error collecting memory metrics: {str(e)}")
        
        metrics.append(vm_gauge)
        metrics.append(swap_gauge)
        metrics.append(mem_percent_gauge)
        
        return metrics
    
    def _collect_disk_metrics(self) -> List[Any]:
        """
        Collect disk metrics.
        
        Returns:
            List of disk metrics
        """
        metrics = []
        
        # Disk usage metrics
        disk_usage_gauge = GaugeMetricFamily(
            'system_disk_usage_bytes',
            'Disk usage information in bytes',
            labels=['hostname', 'mountpoint', 'type']
        )
        
        # Disk usage percentage
        disk_percent_gauge = GaugeMetricFamily(
            'system_disk_usage_percent',
            'Disk usage percentage',
            labels=['hostname', 'mountpoint']
        )
        
        # Disk IO counters
        disk_io_counter = CounterMetricFamily(
            'system_disk_io_total',
            'Disk I/O statistics',
            labels=['hostname', 'device', 'type']
        )
        
        try:
            # Disk usage for each mount point
            for partition in psutil.disk_partitions(all=False):
                if os.name == 'nt' and ('cdrom' in partition.opts or partition.fstype == ''):
                    # Skip CD-ROM drives on Windows
                    continue
                
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_usage_gauge.add_metric(
                        [self.hostname, partition.mountpoint, "total"], 
                        usage.total
                    )
                    disk_usage_gauge.add_metric(
                        [self.hostname, partition.mountpoint, "used"], 
                        usage.used
                    )
                    disk_usage_gauge.add_metric(
                        [self.hostname, partition.mountpoint, "free"], 
                        usage.free
                    )
                    
                    disk_percent_gauge.add_metric(
                        [self.hostname, partition.mountpoint], 
                        usage.percent
                    )
                except (PermissionError, FileNotFoundError) as e:
                    # Some mountpoints might not be accessible
                    logger.debug(f"Cannot access disk info for {partition.mountpoint}: {str(e)}")
            
            # Disk IO counters
            disk_io = psutil.disk_io_counters(perdisk=True)
            for disk_name, counters in disk_io.items():
                disk_io_counter.add_metric(
                    [self.hostname, disk_name, "read_count"], 
                    counters.read_count
                )
                disk_io_counter.add_metric(
                    [self.hostname, disk_name, "write_count"], 
                    counters.write_count
                )
                disk_io_counter.add_metric(
                    [self.hostname, disk_name, "read_bytes"], 
                    counters.read_bytes
                )
                disk_io_counter.add_metric(
                    [self.hostname, disk_name, "write_bytes"], 
                    counters.write_bytes
                )
                if hasattr(counters, 'read_time'):
                    disk_io_counter.add_metric(
                        [self.hostname, disk_name, "read_time_ms"], 
                        counters.read_time
                    )
                if hasattr(counters, 'write_time'):
                    disk_io_counter.add_metric(
                        [self.hostname, disk_name, "write_time_ms"], 
                        counters.write_time
                    )
                
        except Exception as e:
            logger.error(f"Error collecting disk metrics: {str(e)}")
        
        metrics.append(disk_usage_gauge)
        metrics.append(disk_percent_gauge)
        metrics.append(disk_io_counter)
        
        return metrics
    
    def _collect_network_metrics(self) -> List[Any]:
        """
        Collect network metrics.
        
        Returns:
            List of network metrics
        """
        metrics = []
        
        # Network IO counters
        net_io_counter = CounterMetricFamily(
            'system_network_io_total',
            'Network I/O statistics',
            labels=['hostname', 'interface', 'type']
        )
        
        # Network connections
        net_connections_gauge = GaugeMetricFamily(
            'system_network_connections',
            'Number of network connections',
            labels=['hostname', 'type']
        )
        
        try:
            # Network IO
            net_io = psutil.net_io_counters(pernic=True)
            for interface, counters in net_io.items():
                net_io_counter.add_metric(
                    [self.hostname, interface, "bytes_sent"], 
                    counters.bytes_sent
                )
                net_io_counter.add_metric(
                    [self.hostname, interface, "bytes_recv"], 
                    counters.bytes_recv
                )
                net_io_counter.add_metric(
                    [self.hostname, interface, "packets_sent"], 
                    counters.packets_sent
                )
                net_io_counter.add_metric(
                    [self.hostname, interface, "packets_recv"], 
                    counters.packets_recv
                )
                net_io_counter.add_metric(
                    [self.hostname, interface, "errin"], 
                    counters.errin
                )
                net_io_counter.add_metric(
                    [self.hostname, interface, "errout"], 
                    counters.errout
                )
                net_io_counter.add_metric(
                    [self.hostname, interface, "dropin"], 
                    counters.dropin
                )
                net_io_counter.add_metric(
                    [self.hostname, interface, "dropout"], 
                    counters.dropout
                )
            
            # Network connections by status
            try:
                connections = psutil.net_connections()
                status_counts = {}
                for conn in connections:
                    status = conn.status
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                for status, count in status_counts.items():
                    net_connections_gauge.add_metric([self.hostname, status.lower()], count)
                
                # Total connections
                net_connections_gauge.add_metric([self.hostname, "total"], len(connections))
                
            except (psutil.AccessDenied, PermissionError):
                logger.debug("Permission denied when accessing network connections")
                
        except Exception as e:
            logger.error(f"Error collecting network metrics: {str(e)}")
        
        metrics.append(net_io_counter)
        metrics.append(net_connections_gauge)
        
        return metrics
    
    def _collect_process_metrics(self) -> List[Any]:
        """
        Collect metrics for the specified process.
        
        Returns:
            List of process metrics
        """
        metrics = []
        
        # Process CPU and memory metrics
        proc_cpu_gauge = GaugeMetricFamily(
            'process_cpu_usage_percent',
            'Process CPU usage percentage',
            labels=['hostname', 'name', 'pid']
        )
        
        proc_memory_gauge = GaugeMetricFamily(
            'process_memory_usage_bytes',
            'Process memory usage in bytes',
            labels=['hostname', 'name', 'pid', 'type']
        )
        
        proc_io_counter = CounterMetricFamily(
            'process_io_total',
            'Process I/O statistics',
            labels=['hostname', 'name', 'pid', 'type']
        )
        
        proc_threads_gauge = GaugeMetricFamily(
            'process_threads',
            'Number of process threads',
            labels=['hostname', 'name', 'pid']
        )
        
        proc_open_files_gauge = GaugeMetricFamily(
            'process_open_files',
            'Number of open files by process',
            labels=['hostname', 'name', 'pid']
        )
        
        if not self.process:
            return metrics
        
        try:
            # Process info
            pid = self.process.pid
            name = self.process.name()
            
            # CPU usage
            cpu_percent = self.process.cpu_percent(interval=0.1)
            proc_cpu_gauge.add_metric([self.hostname, name, str(pid)], cpu_percent)
            
            # Memory usage
            memory_info = self.process.memory_info()
            proc_memory_gauge.add_metric([self.hostname, name, str(pid), "rss"], memory_info.rss)
            proc_memory_gauge.add_metric([self.hostname, name, str(pid), "vms"], memory_info.vms)
            
            if hasattr(memory_info, 'shared'):
                proc_memory_gauge.add_metric(
                    [self.hostname, name, str(pid), "shared"], 
                    memory_info.shared
                )
            
            # IO counters
            try:
                io_counters = self.process.io_counters()
                proc_io_counter.add_metric(
                    [self.hostname, name, str(pid), "read_count"], 
                    io_counters.read_count
                )
                proc_io_counter.add_metric(
                    [self.hostname, name, str(pid), "write_count"], 
                    io_counters.write_count
                )
                proc_io_counter.add_metric(
                    [self.hostname, name, str(pid), "read_bytes"], 
                    io_counters.read_bytes
                )
                proc_io_counter.add_metric(
                    [self.hostname, name, str(pid), "write_bytes"], 
                    io_counters.write_bytes
                )
            except (psutil.AccessDenied, AttributeError):
                logger.debug(f"Cannot access IO counters for process {name}")
            
            # Threads
            num_threads = self.process.num_threads()
            proc_threads_gauge.add_metric([self.hostname, name, str(pid)], num_threads)
            
            # Open files
            try:
                open_files = self.process.open_files()
                proc_open_files_gauge.add_metric(
                    [self.hostname, name, str(pid)], 
                    len(open_files)
                )
            except (psutil.AccessDenied, AttributeError):
                logger.debug(f"Cannot access open files for process {name}")
                
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            logger.error(f"Error accessing process {self.process_name}: {str(e)}")
            self.process = None
        except Exception as e:
            logger.error(f"Error collecting process metrics: {str(e)}")
        
        metrics.append(proc_cpu_gauge)
        metrics.append(proc_memory_gauge)
        metrics.append(proc_io_counter)
        metrics.append(proc_threads_gauge)
        metrics.append(proc_open_files_gauge)
        
        return metrics 