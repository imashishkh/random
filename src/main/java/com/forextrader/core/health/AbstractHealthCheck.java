package com.forextrader.core.health;

import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Abstract base class for health checks.
 * Provides common functionality for all health checks.
 */
public abstract class AbstractHealthCheck implements HealthCheck {
    private static final Logger logger = Logger.getLogger(AbstractHealthCheck.class.getName());
    
    private final String id;
    private final String serviceName;
    
    /**
     * Creates a new abstract health check.
     * 
     * @param serviceName The name of the service this health check is associated with
     * @param id The unique ID of this health check
     */
    public AbstractHealthCheck(String serviceName, String id) {
        this.serviceName = serviceName;
        this.id = id;
    }
    
    @Override
    public String getId() {
        return id;
    }
    
    @Override
    public String getServiceName() {
        return serviceName;
    }
    
    @Override
    public HealthStatus check() {
        try {
            logger.fine("Executing health check: " + id + " for service: " + serviceName);
            return doCheck();
        } catch (Exception e) {
            logger.log(Level.WARNING, "Health check failed: " + id, e);
            return HealthStatus.unhealthy("Exception during health check: " + e.getMessage());
        }
    }
    
    /**
     * Performs the actual health check.
     * Implementations should override this method to provide the specific health check logic.
     * 
     * @return The health status after execution
     * @throws Exception if an error occurs during the health check
     */
    protected abstract HealthStatus doCheck() throws Exception;
} 