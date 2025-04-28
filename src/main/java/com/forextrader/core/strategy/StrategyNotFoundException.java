package com.forextrader.core.strategy;

/**
 * Exception thrown when attempting to retrieve a trading strategy that does not exist.
 */
public class StrategyNotFoundException extends Exception {
    private final String strategyId;
    
    /**
     * Constructs a new StrategyNotFoundException with the specified strategy ID.
     * 
     * @param strategyId the ID of the strategy that was not found
     */
    public StrategyNotFoundException(String strategyId) {
        super("Strategy with ID: " + strategyId + " not found");
        this.strategyId = strategyId;
    }
    
    /**
     * Constructs a new StrategyNotFoundException with the specified strategy ID and cause.
     * 
     * @param strategyId the ID of the strategy that was not found
     * @param cause the cause of the exception
     */
    public StrategyNotFoundException(String strategyId, Throwable cause) {
        super("Strategy with ID: " + strategyId + " not found", cause);
        this.strategyId = strategyId;
    }
    
    /**
     * Gets the ID of the strategy that was not found.
     * 
     * @return the strategy ID
     */
    public String getStrategyId() {
        return strategyId;
    }
} 