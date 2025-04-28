package com.forextrader.core.health;

/**
 * Interface for health checks in the system.
 * Health checks are used to verify that a service is functioning correctly.
 */
public interface HealthCheck {
    /**
     * Executes the health check and returns the status.
     * 
     * @return The health status after execution
     */
    HealthStatus check();
    
    /**
     * Returns the unique ID of this health check.
     * 
     * @return The health check ID
     */
    String getId();
    
    /**
     * Returns the name of the service this health check is associated with.
     * 
     * @return The service name
     */
    String getServiceName();
} 