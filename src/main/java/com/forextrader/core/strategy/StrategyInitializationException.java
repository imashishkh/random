package com.forextrader.core.strategy;

/**
 * Exception thrown when a trading strategy fails to initialize.
 */
public class StrategyInitializationException extends Exception {
    private final String strategyId;
    
    /**
     * Constructs a new StrategyInitializationException with the specified strategy ID and detail message.
     * 
     * @param strategyId the ID of the strategy that failed to initialize
     * @param message the detail message
     */
    public StrategyInitializationException(String strategyId, String message) {
        super(message);
        this.strategyId = strategyId;
    }
    
    /**
     * Constructs a new StrategyInitializationException with the specified strategy ID, detail message, and cause.
     * 
     * @param strategyId the ID of the strategy that failed to initialize
     * @param message the detail message
     * @param cause the cause of the exception
     */
    public StrategyInitializationException(String strategyId, String message, Throwable cause) {
        super(message, cause);
        this.strategyId = strategyId;
    }
    
    /**
     * Gets the ID of the strategy that failed to initialize.
     * 
     * @return the strategy ID
     */
    public String getStrategyId() {
        return strategyId;
    }
} 