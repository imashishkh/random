package com.forextrader.core.configuration;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Exception thrown when configuration validation fails.
 */
public class ConfigurationException extends RuntimeException {
    private final String serviceName;
    private final List<ConfigurationError> errors;
    
    /**
     * Creates a new configuration exception.
     * 
     * @param serviceName The name of the service with invalid configuration
     * @param message The error message
     */
    public ConfigurationException(String serviceName, String message) {
        super(message);
        this.serviceName = serviceName;
        this.errors = Collections.emptyList();
    }
    
    /**
     * Creates a new configuration exception with a list of errors.
     * 
     * @param serviceName The name of the service with invalid configuration
     * @param errors The list of configuration errors
     */
    public ConfigurationException(String serviceName, List<ConfigurationError> errors) {
        super(buildMessage(serviceName, errors));
        this.serviceName = serviceName;
        this.errors = new ArrayList<>(errors);
    }
    
    /**
     * Creates a new configuration exception with a cause.
     * 
     * @param serviceName The name of the service with invalid configuration
     * @param message The error message
     * @param cause The cause of the exception
     */
    public ConfigurationException(String serviceName, String message, Throwable cause) {
        super(message, cause);
        this.serviceName = serviceName;
        this.errors = Collections.emptyList();
    }
    
    /**
     * Returns the name of the service with invalid configuration.
     * 
     * @return The service name
     */
    public String getServiceName() {
        return serviceName;
    }
    
    /**
     * Returns the list of configuration errors.
     * 
     * @return The list of configuration errors
     */
    public List<ConfigurationError> getErrors() {
        return Collections.unmodifiableList(errors);
    }
    
    /**
     * Builds an error message from a list of configuration errors.
     * 
     * @param serviceName The name of the service with invalid configuration
     * @param errors The list of configuration errors
     * @return The error message
     */
    private static String buildMessage(String serviceName, List<ConfigurationError> errors) {
        StringBuilder message = new StringBuilder("Invalid configuration for service ")
            .append(serviceName)
            .append(": ");
        
        if (errors.isEmpty()) {
            message.append("Unknown error");
        } else if (errors.size() == 1) {
            ConfigurationError error = errors.get(0);
            message.append(error.getParameterName())
                  .append(" - ")
                  .append(error.getErrorMessage());
        } else {
            message.append(errors.size())
                  .append(" configuration errors (see getErrors() for details)");
        }
        
        return message.toString();
    }
} 