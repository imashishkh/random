package com.forextrader.core.initialization;

/**
 * Exception thrown when a service fails to initialize.
 */
public class ServiceInitializationException extends RuntimeException {
    private final String serviceName;
    
    /**
     * Creates a new service initialization exception.
     * 
     * @param serviceName The name of the service that failed to initialize
     */
    public ServiceInitializationException(String serviceName) {
        super("Failed to initialize service: " + serviceName);
        this.serviceName = serviceName;
    }
    
    /**
     * Creates a new service initialization exception with a cause.
     * 
     * @param serviceName The name of the service that failed to initialize
     * @param cause The cause of the failure
     */
    public ServiceInitializationException(String serviceName, Throwable cause) {
        super("Failed to initialize service: " + serviceName, cause);
        this.serviceName = serviceName;
    }
    
    /**
     * Creates a new service initialization exception with a message and cause.
     * 
     * @param serviceName The name of the service that failed to initialize
     * @param message The error message
     * @param cause The cause of the failure
     */
    public ServiceInitializationException(String serviceName, String message, Throwable cause) {
        super(message, cause);
        this.serviceName = serviceName;
    }
    
    /**
     * Returns the name of the service that failed to initialize.
     * 
     * @return The service name
     */
    public String getServiceName() {
        return serviceName;
    }
} 