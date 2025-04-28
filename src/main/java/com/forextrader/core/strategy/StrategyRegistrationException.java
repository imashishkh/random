package com.forextrader.core.strategy;

/**
 * Exception thrown when there is an error during strategy registration.
 */
public class StrategyRegistrationException extends Exception {
    private final String strategyId;
    
    /**
     * Constructs a new StrategyRegistrationException with the specified strategy ID and message.
     * 
     * @param strategyId the ID of the strategy that failed to register
     * @param message the detailed error message
     */
    public StrategyRegistrationException(String strategyId, String message) {
        super("Failed to register strategy with ID: " + strategyId + ". " + message);
        this.strategyId = strategyId;
    }
    
    /**
     * Constructs a new StrategyRegistrationException with the specified strategy ID, message, and cause.
     * 
     * @param strategyId the ID of the strategy that failed to register
     * @param message the detailed error message
     * @param cause the cause of the exception
     */
    public StrategyRegistrationException(String strategyId, String message, Throwable cause) {
        super("Failed to register strategy with ID: " + strategyId + ". " + message, cause);
        this.strategyId = strategyId;
    }
    
    /**
     * Gets the ID of the strategy that failed to register.
     * 
     * @return the strategy ID
     */
    public String getStrategyId() {
        return strategyId;
    }
} 