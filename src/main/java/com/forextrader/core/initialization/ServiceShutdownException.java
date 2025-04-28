package com.forextrader.core.initialization;

/**
 * Exception thrown when a service fails to shutdown gracefully.
 */
public class ServiceShutdownException extends RuntimeException {
    private final String serviceName;
    
    /**
     * Creates a new service shutdown exception.
     * 
     * @param serviceName The name of the service that failed to shutdown
     */
    public ServiceShutdownException(String serviceName) {
        super("Failed to shutdown service: " + serviceName);
        this.serviceName = serviceName;
    }
    
    /**
     * Creates a new service shutdown exception with a cause.
     * 
     * @param serviceName The name of the service that failed to shutdown
     * @param cause The cause of the failure
     */
    public ServiceShutdownException(String serviceName, Throwable cause) {
        super("Failed to shutdown service: " + serviceName, cause);
        this.serviceName = serviceName;
    }
    
    /**
     * Creates a new service shutdown exception with a message and cause.
     * 
     * @param serviceName The name of the service that failed to shutdown
     * @param message The error message
     * @param cause The cause of the failure
     */
    public ServiceShutdownException(String serviceName, String message, Throwable cause) {
        super(message, cause);
        this.serviceName = serviceName;
    }
    
    /**
     * Returns the name of the service that failed to shutdown.
     * 
     * @return The service name
     */
    public String getServiceName() {
        return serviceName;
    }
} 