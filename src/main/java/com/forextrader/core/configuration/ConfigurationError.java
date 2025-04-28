package com.forextrader.core.configuration;

/**
 * Represents a single configuration error.
 */
public class ConfigurationError {
    private final String parameterName;
    private final String errorMessage;
    private final Object invalidValue;
    
    /**
     * Creates a new configuration error with a parameter name and error message.
     * 
     * @param parameterName The name of the configuration parameter with an error
     * @param errorMessage A descriptive error message
     */
    public ConfigurationError(String parameterName, String errorMessage) {
        this(parameterName, errorMessage, null);
    }
    
    /**
     * Creates a new configuration error with a parameter name, error message, and invalid value.
     * 
     * @param parameterName The name of the configuration parameter with an error
     * @param errorMessage A descriptive error message
     * @param invalidValue The invalid value that caused the error, can be null
     */
    public ConfigurationError(String parameterName, String errorMessage, Object invalidValue) {
        this.parameterName = parameterName;
        this.errorMessage = errorMessage;
        this.invalidValue = invalidValue;
    }
    
    /**
     * Returns the name of the configuration parameter with an error.
     * 
     * @return The parameter name
     */
    public String getParameterName() {
        return parameterName;
    }
    
    /**
     * Returns the error message describing the configuration error.
     * 
     * @return The error message
     */
    public String getErrorMessage() {
        return errorMessage;
    }
    
    /**
     * Returns the invalid value that caused the error, if provided.
     * 
     * @return The invalid value, or null if not provided
     */
    public Object getInvalidValue() {
        return invalidValue;
    }
    
    @Override
    public String toString() {
        StringBuilder builder = new StringBuilder()
            .append(parameterName)
            .append(" - ")
            .append(errorMessage);
            
        if (invalidValue != null) {
            builder.append(" (value: ")
                  .append(invalidValue)
                  .append(")");
        }
        
        return builder.toString();
    }
} 