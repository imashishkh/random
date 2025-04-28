package com.forextrader.core.health;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

import com.forextrader.core.Component;

/**
 * Registry for health checks in the system.
 * Provides mechanisms to register, execute, and monitor health checks for all services.
 */
public class HealthCheckRegistry implements Component {
    private static final Logger logger = Logger.getLogger(HealthCheckRegistry.class.getName());
    
    // Map of health check ID to health check
    private final Map<String, HealthCheck> healthChecks = new ConcurrentHashMap<>();
    
    // Map of health check ID to last known status
    private final Map<String, HealthStatus> healthStatuses = new ConcurrentHashMap<>();
    
    // Executor for running health checks
    private ScheduledExecutorService executor;
    
    // Whether the health check system is running
    private volatile boolean running = false;
    
    /**
     * Registers a health check with the registry.
     * 
     * @param healthCheck The health check to register
     */
    public void register(HealthCheck healthCheck) {
        String id = healthCheck.getId();
        
        if (healthChecks.containsKey(id)) {
            logger.warning("Health check already registered with ID: " + id + ". Overwriting.");
        }
        
        healthChecks.put(id, healthCheck);
        healthStatuses.put(id, HealthStatus.unknown("Health check not yet executed"));
        
        logger.info("Registered health check: " + id);
    }
    
    /**
     * Unregisters a health check from the registry.
     * 
     * @param id The ID of the health check to unregister
     * @return true if the health check was unregistered, false if it wasn't registered
     */
    public boolean unregister(String id) {
        HealthCheck removed = healthChecks.remove(id);
        healthStatuses.remove(id);
        
        if (removed != null) {
            logger.info("Unregistered health check: " + id);
            return true;
        }
        
        return false;
    }
    
    /**
     * Returns a health check by its ID.
     * 
     * @param id The ID of the health check to retrieve
     * @return The health check, or null if not found
     */
    public HealthCheck getHealthCheck(String id) {
        return healthChecks.get(id);
    }
    
    /**
     * Returns all registered health checks.
     * 
     * @return Map of health check ID to health check
     */
    public Map<String, HealthCheck> getAllHealthChecks() {
        return Collections.unmodifiableMap(healthChecks);
    }
    
    /**
     * Returns the last known status of a health check.
     * 
     * @param id The ID of the health check
     * @return The health status, or HealthStatus.unknown() if the health check is not registered
     */
    public HealthStatus getHealthStatus(String id) {
        HealthStatus status = healthStatuses.get(id);
        if (status == null) {
            return HealthStatus.unknown("Health check not registered: " + id);
        }
        return status;
    }
    
    /**
     * Returns the last known status of all health checks.
     * 
     * @return Map of health check ID to health status
     */
    public Map<String, HealthStatus> getAllHealthStatuses() {
        return Collections.unmodifiableMap(healthStatuses);
    }
    
    /**
     * Returns an overall health status for the system.
     * The system is considered healthy if all health checks are healthy.
     * 
     * @return The overall health status
     */
    public HealthStatus getOverallHealthStatus() {
        if (healthStatuses.isEmpty()) {
            return HealthStatus.unknown("No health checks registered");
        }
        
        List<String> unhealthyChecks = new ArrayList<>();
        
        for (Map.Entry<String, HealthStatus> entry : healthStatuses.entrySet()) {
            if (!entry.getValue().isHealthy()) {
                unhealthyChecks.add(entry.getKey() + ": " + entry.getValue().getMessage());
            }
        }
        
        if (unhealthyChecks.isEmpty()) {
            return HealthStatus.healthy("All health checks passed");
        } else {
            return HealthStatus.unhealthy("Unhealthy checks: " + String.join(", ", unhealthyChecks));
        }
    }
    
    /**
     * Executes a health check by its ID.
     * Updates the health status in the registry.
     * 
     * @param id The ID of the health check to execute
     * @return The health status after execution
     */
    public HealthStatus executeHealthCheck(String id) {
        HealthCheck healthCheck = healthChecks.get(id);
        if (healthCheck == null) {
            HealthStatus status = HealthStatus.unknown("Health check not registered: " + id);
            healthStatuses.put(id, status);
            return status;
        }
        
        try {
            HealthStatus status = healthCheck.check();
            healthStatuses.put(id, status);
            return status;
        } catch (Exception e) {
            logger.log(Level.WARNING, "Health check failed: " + id, e);
            HealthStatus status = HealthStatus.unhealthy("Health check threw exception: " + e.getMessage());
            healthStatuses.put(id, status);
            return status;
        }
    }
    
    /**
     * Executes all registered health checks.
     * Updates all health statuses in the registry.
     * 
     * @return Map of health check ID to health status after execution
     */
    public Map<String, HealthStatus> executeAllHealthChecks() {
        for (String id : healthChecks.keySet()) {
            executeHealthCheck(id);
        }
        
        return Collections.unmodifiableMap(healthStatuses);
    }
    
    /**
     * Starts running all health checks on a schedule.
     * 
     * @param initialDelaySeconds Initial delay in seconds before the first execution
     * @param periodSeconds Period in seconds between executions
     */
    public void startChecks(long initialDelaySeconds, long periodSeconds) {
        if (running) {
            logger.warning("Health checks already running");
            return;
        }
        
        logger.info("Starting health checks with initialDelay=" + initialDelaySeconds + "s, period=" + periodSeconds + "s");
        
        executor = Executors.newScheduledThreadPool(1);
        executor.scheduleAtFixedRate(
            this::executeAllHealthChecks,
            initialDelaySeconds,
            periodSeconds,
            TimeUnit.SECONDS
        );
        
        running = true;
    }
    
    /**
     * Starts running health checks with default timing (5s initial delay, 30s period).
     */
    public void startChecks() {
        startChecks(5, 30);
    }
    
    /**
     * Stops running health checks.
     */
    public void stopChecks() {
        if (!running) {
            logger.info("Health checks not running");
            return;
        }
        
        logger.info("Stopping health checks");
        
        if (executor != null) {
            executor.shutdown();
            try {
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException e) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            }
            executor = null;
        }
        
        running = false;
    }
    
    /**
     * Generates a report of all health checks and their statuses.
     * 
     * @return A formatted report string
     */
    public String generateHealthReport() {
        StringBuilder report = new StringBuilder("Health Check Report:\n");
        
        HealthStatus overallStatus = getOverallHealthStatus();
        report.append("Overall Status: ")
              .append(overallStatus.isHealthy() ? "HEALTHY" : "UNHEALTHY")
              .append(" - ")
              .append(overallStatus.getMessage())
              .append("\n\n");
        
        // Group health checks by service
        Map<String, List<Map.Entry<String, HealthStatus>>> serviceChecks = new ConcurrentHashMap<>();
        
        for (Map.Entry<String, HealthStatus> entry : healthStatuses.entrySet()) {
            String id = entry.getKey();
            HealthCheck healthCheck = healthChecks.get(id);
            
            String serviceName = healthCheck != null ? healthCheck.getServiceName() : "unknown";
            
            serviceChecks
                .computeIfAbsent(serviceName, k -> new ArrayList<>())
                .add(entry);
        }
        
        // Generate report for each service
        for (Map.Entry<String, List<Map.Entry<String, HealthStatus>>> serviceEntry : serviceChecks.entrySet()) {
            String serviceName = serviceEntry.getKey();
            List<Map.Entry<String, HealthStatus>> checks = serviceEntry.getValue();
            
            report.append("Service: ").append(serviceName).append("\n");
            
            for (Map.Entry<String, HealthStatus> check : checks) {
                String id = check.getKey();
                HealthStatus status = check.getValue();
                
                report.append("  - ")
                      .append(id)
                      .append(": ")
                      .append(status.isHealthy() ? "HEALTHY" : (status.isUnknown() ? "UNKNOWN" : "UNHEALTHY"))
                      .append(" - ")
                      .append(status.getMessage())
                      .append("\n");
            }
            
            report.append("\n");
        }
        
        return report.toString();
    }
    
    // Component lifecycle methods
    
    @Override
    public void init() {
        // Nothing to initialize
    }
    
    @Override
    public void start() {
        startChecks();
    }
    
    @Override
    public void stop() {
        stopChecks();
    }
} 