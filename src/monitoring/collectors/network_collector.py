"""
Network connectivity collector for Prometheus.

This module provides a collector for monitoring connectivity to external services
and network endpoints, measuring latency, availability, and other connectivity metrics.
"""

import logging
import time
import socket
import requests
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

from .collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)


class NetworkCollector(BaseCollector):
    """
    Collector for network connectivity metrics.
    
    This collector measures connectivity to external services and endpoints,
    including HTTP endpoints, TCP services, and DNS resolution.
    """
    
    def __init__(
        self, 
        endpoints: Dict[str, str] = None,
        tcp_services: Dict[str, Tuple[str, int]] = None,
        dns_targets: List[str] = None,
        http_timeout: float = 5.0,
        tcp_timeout: float = 3.0,
        dns_timeout: float = 2.0,
        collection_interval: float = 60.0
    ):
        """
        Initialize the network collector.
        
        Args:
            endpoints: Dict of HTTP endpoints to monitor {name: url}
            tcp_services: Dict of TCP services to monitor {name: (host, port)}
            dns_targets: List of DNS names to resolve and monitor
            http_timeout: Timeout in seconds for HTTP requests
            tcp_timeout: Timeout in seconds for TCP connections
            dns_timeout: Timeout in seconds for DNS resolution
            collection_interval: Interval in seconds between metric collection
        """
        super().__init__(collection_interval=collection_interval)
        
        self.endpoints = endpoints or {}
        self.tcp_services = tcp_services or {}
        self.dns_targets = dns_targets or []
        
        self.http_timeout = http_timeout
        self.tcp_timeout = tcp_timeout
        self.dns_timeout = dns_timeout
        
        # Initialize session for connection pooling and better performance
        self.session = requests.Session()
        
        # Error counters for tracking consecutive failures
        self.http_errors = {name: 0 for name in self.endpoints}
        self.tcp_errors = {name: 0 for name in self.tcp_services}
        self.dns_errors = {name: 0 for name in self.dns_targets}
        
        # Last success timestamps
        self.last_http_success = {name: 0 for name in self.endpoints}
        self.last_tcp_success = {name: 0 for name in self.tcp_services}
        self.last_dns_success = {name: 0 for name in self.dns_targets}
    
    def collect_metrics(self) -> List[Any]:
        """
        Collect network metrics.
        
        Returns:
            List of metrics for Prometheus
        """
        metrics = []
        
        # HTTP endpoints monitoring
        metrics.extend(self._collect_http_metrics())
        
        # TCP services monitoring
        metrics.extend(self._collect_tcp_metrics())
        
        # DNS resolution monitoring
        metrics.extend(self._collect_dns_metrics())
        
        # Add collector's own metrics
        metrics.extend(self.get_collector_metrics())
        
        return metrics
    
    def _collect_http_metrics(self) -> List[Any]:
        """
        Collect HTTP connectivity metrics.
        
        Returns:
            List of HTTP metrics
        """
        metrics = []
        
        # HTTP connectivity metrics
        http_up_gauge = GaugeMetricFamily(
            'network_http_up',
            'HTTP endpoint connectivity status (1 = up, 0 = down)',
            labels=['endpoint_name', 'url']
        )
        
        # HTTP response time metrics
        http_response_time_gauge = GaugeMetricFamily(
            'network_http_response_time_seconds',
            'HTTP endpoint response time in seconds',
            labels=['endpoint_name', 'url']
        )
        
        # HTTP status code metrics
        http_status_gauge = GaugeMetricFamily(
            'network_http_status_code',
            'HTTP endpoint status code',
            labels=['endpoint_name', 'url']
        )
        
        # HTTP error count
        http_error_counter = CounterMetricFamily(
            'network_http_error_total',
            'Number of HTTP connection errors',
            labels=['endpoint_name', 'url', 'error_type']
        )
        
        # Time since last successful check
        http_time_since_success_gauge = GaugeMetricFamily(
            'network_http_time_since_success_seconds',
            'Time in seconds since last successful HTTP check',
            labels=['endpoint_name', 'url']
        )
        
        # Check each HTTP endpoint
        for name, url in self.endpoints.items():
            try:
                parsed_url = urlparse(url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    logger.warning(f"Invalid URL format for endpoint {name}: {url}")
                    continue
                
                start_time = time.time()
                response = self.session.get(
                    url, 
                    timeout=self.http_timeout,
                    allow_redirects=False,
                    verify=True
                )
                response_time = time.time() - start_time
                
                # Record response time
                http_response_time_gauge.add_metric([name, url], response_time)
                
                # Record status code
                http_status_gauge.add_metric([name, url], response.status_code)
                
                # Consider success if status code < 400
                is_success = response.status_code < 400
                http_up_gauge.add_metric([name, url], 1 if is_success else 0)
                
                if is_success:
                    self.http_errors[name] = 0
                    self.last_http_success[name] = time.time()
                else:
                    self.http_errors[name] += 1
                    # Add error for non-success status code
                    http_error_counter.add_metric(
                        [name, url, f"status_{response.status_code}"],
                        1
                    )
                
            except requests.RequestException as e:
                logger.warning(f"HTTP connection error for {name} ({url}): {str(e)}")
                http_up_gauge.add_metric([name, url], 0)
                
                self.http_errors[name] += 1
                
                # Categorize error type
                error_type = type(e).__name__
                http_error_counter.add_metric([name, url, error_type], 1)
                
            except Exception as e:
                logger.error(f"Unexpected error monitoring HTTP endpoint {name} ({url}): {str(e)}")
                http_up_gauge.add_metric([name, url], 0)
                self.http_errors[name] += 1
            
            # Record time since last success
            time_since_success = time.time() - self.last_http_success[name] if self.last_http_success[name] > 0 else 0
            http_time_since_success_gauge.add_metric([name, url], time_since_success)
        
        metrics.append(http_up_gauge)
        metrics.append(http_response_time_gauge)
        metrics.append(http_status_gauge)
        metrics.append(http_error_counter)
        metrics.append(http_time_since_success_gauge)
        
        return metrics
    
    def _collect_tcp_metrics(self) -> List[Any]:
        """
        Collect TCP connectivity metrics.
        
        Returns:
            List of TCP metrics
        """
        metrics = []
        
        # TCP connectivity metrics
        tcp_up_gauge = GaugeMetricFamily(
            'network_tcp_up',
            'TCP service connectivity status (1 = up, 0 = down)',
            labels=['service_name', 'host', 'port']
        )
        
        # TCP connection time metrics
        tcp_connection_time_gauge = GaugeMetricFamily(
            'network_tcp_connection_time_seconds',
            'TCP service connection time in seconds',
            labels=['service_name', 'host', 'port']
        )
        
        # TCP error count
        tcp_error_counter = CounterMetricFamily(
            'network_tcp_error_total',
            'Number of TCP connection errors',
            labels=['service_name', 'host', 'port', 'error_type']
        )
        
        # Time since last successful check
        tcp_time_since_success_gauge = GaugeMetricFamily(
            'network_tcp_time_since_success_seconds',
            'Time in seconds since last successful TCP check',
            labels=['service_name', 'host', 'port']
        )
        
        # Check each TCP service
        for name, (host, port) in self.tcp_services.items():
            sock = None
            try:
                start_time = time.time()
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.tcp_timeout)
                
                result = sock.connect_ex((host, port))
                connection_time = time.time() - start_time
                
                is_success = (result == 0)
                tcp_up_gauge.add_metric([name, host, str(port)], 1 if is_success else 0)
                
                if is_success:
                    tcp_connection_time_gauge.add_metric([name, host, str(port)], connection_time)
                    self.tcp_errors[name] = 0
                    self.last_tcp_success[name] = time.time()
                else:
                    error_type = f"errno_{result}"
                    tcp_error_counter.add_metric([name, host, str(port), error_type], 1)
                    self.tcp_errors[name] += 1
                
            except socket.error as e:
                logger.warning(f"TCP connection error for {name} ({host}:{port}): {str(e)}")
                tcp_up_gauge.add_metric([name, host, str(port)], 0)
                
                error_type = type(e).__name__
                tcp_error_counter.add_metric([name, host, str(port), error_type], 1)
                self.tcp_errors[name] += 1
                
            except Exception as e:
                logger.error(f"Unexpected error monitoring TCP service {name} ({host}:{port}): {str(e)}")
                tcp_up_gauge.add_metric([name, host, str(port)], 0)
                self.tcp_errors[name] += 1
                
            finally:
                if sock:
                    sock.close()
            
            # Record time since last success
            time_since_success = time.time() - self.last_tcp_success[name] if self.last_tcp_success[name] > 0 else 0
            tcp_time_since_success_gauge.add_metric([name, host, str(port)], time_since_success)
        
        metrics.append(tcp_up_gauge)
        metrics.append(tcp_connection_time_gauge)
        metrics.append(tcp_error_counter)
        metrics.append(tcp_time_since_success_gauge)
        
        return metrics
    
    def _collect_dns_metrics(self) -> List[Any]:
        """
        Collect DNS resolution metrics.
        
        Returns:
            List of DNS metrics
        """
        metrics = []
        
        # DNS resolution metrics
        dns_up_gauge = GaugeMetricFamily(
            'network_dns_up',
            'DNS resolution status (1 = up, 0 = down)',
            labels=['hostname']
        )
        
        # DNS resolution time metrics
        dns_resolution_time_gauge = GaugeMetricFamily(
            'network_dns_resolution_time_seconds',
            'DNS resolution time in seconds',
            labels=['hostname']
        )
        
        # DNS resolution results (number of IPs returned)
        dns_result_count_gauge = GaugeMetricFamily(
            'network_dns_result_count',
            'Number of IP addresses returned from DNS resolution',
            labels=['hostname']
        )
        
        # DNS error count
        dns_error_counter = CounterMetricFamily(
            'network_dns_error_total',
            'Number of DNS resolution errors',
            labels=['hostname', 'error_type']
        )
        
        # Time since last successful resolution
        dns_time_since_success_gauge = GaugeMetricFamily(
            'network_dns_time_since_success_seconds',
            'Time in seconds since last successful DNS resolution',
            labels=['hostname']
        )
        
        # Check each DNS target
        for hostname in self.dns_targets:
            try:
                # Use default resolver
                start_time = time.time()
                
                # Set socket timeout temporarily for DNS lookups
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(self.dns_timeout)
                
                try:
                    result = socket.getaddrinfo(hostname, None)
                    resolution_time = time.time() - start_time
                    
                    # Count unique IPs
                    ips = set()
                    for res in result:
                        family, socktype, proto, canonname, sockaddr = res
                        if family == socket.AF_INET:  # IPv4
                            ips.add(sockaddr[0])
                        elif family == socket.AF_INET6:  # IPv6
                            ips.add(sockaddr[0])
                    
                    ip_count = len(ips)
                    
                    dns_up_gauge.add_metric([hostname], 1)
                    dns_resolution_time_gauge.add_metric([hostname], resolution_time)
                    dns_result_count_gauge.add_metric([hostname], ip_count)
                    
                    self.dns_errors[hostname] = 0
                    self.last_dns_success[hostname] = time.time()
                    
                finally:
                    # Restore original timeout
                    socket.setdefaulttimeout(old_timeout)
                
            except socket.gaierror as e:
                logger.warning(f"DNS resolution error for {hostname}: {str(e)}")
                dns_up_gauge.add_metric([hostname], 0)
                
                error_code = e.args[0] if e.args else 'unknown'
                dns_error_counter.add_metric([hostname, f"gaierror_{error_code}"], 1)
                self.dns_errors[hostname] += 1
                
            except socket.timeout:
                logger.warning(f"DNS resolution timeout for {hostname}")
                dns_up_gauge.add_metric([hostname], 0)
                
                dns_error_counter.add_metric([hostname, "timeout"], 1)
                self.dns_errors[hostname] += 1
                
            except Exception as e:
                logger.error(f"Unexpected error resolving DNS for {hostname}: {str(e)}")
                dns_up_gauge.add_metric([hostname], 0)
                self.dns_errors[hostname] += 1
            
            # Record time since last success
            time_since_success = time.time() - self.last_dns_success[hostname] if self.last_dns_success[hostname] > 0 else 0
            dns_time_since_success_gauge.add_metric([hostname], time_since_success)
        
        metrics.append(dns_up_gauge)
        metrics.append(dns_resolution_time_gauge)
        metrics.append(dns_result_count_gauge)
        metrics.append(dns_error_counter)
        metrics.append(dns_time_since_success_gauge)
        
        return metrics
    
    def add_endpoint(self, name: str, url: str):
        """
        Add an HTTP endpoint to monitor.
        
        Args:
            name: Name of the endpoint
            url: URL of the endpoint
        """
        self.endpoints[name] = url
        self.http_errors[name] = 0
        self.last_http_success[name] = 0
    
    def add_tcp_service(self, name: str, host: str, port: int):
        """
        Add a TCP service to monitor.
        
        Args:
            name: Name of the service
            host: Hostname or IP address of the service
            port: Port number of the service
        """
        self.tcp_services[name] = (host, port)
        self.tcp_errors[name] = 0
        self.last_tcp_success[name] = 0
    
    def add_dns_target(self, hostname: str):
        """
        Add a DNS hostname to monitor.
        
        Args:
            hostname: Hostname to resolve and monitor
        """
        if hostname not in self.dns_targets:
            self.dns_targets.append(hostname)
            self.dns_errors[hostname] = 0
            self.last_dns_success[hostname] = 0
    
    def remove_endpoint(self, name: str):
        """
        Remove an HTTP endpoint from monitoring.
        
        Args:
            name: Name of the endpoint to remove
        """
        if name in self.endpoints:
            del self.endpoints[name]
            del self.http_errors[name]
            del self.last_http_success[name]
    
    def remove_tcp_service(self, name: str):
        """
        Remove a TCP service from monitoring.
        
        Args:
            name: Name of the service to remove
        """
        if name in self.tcp_services:
            del self.tcp_services[name]
            del self.tcp_errors[name]
            del self.last_tcp_success[name]
    
    def remove_dns_target(self, hostname: str):
        """
        Remove a DNS hostname from monitoring.
        
        Args:
            hostname: Hostname to remove
        """
        if hostname in self.dns_targets:
            self.dns_targets.remove(hostname)
            del self.dns_errors[hostname]
            del self.last_dns_success[hostname] 