package com.forextrader.core.strategy;

/**
 * Exception thrown when a trading strategy encounters an error during execution.
 */
public class StrategyExecutionException extends Exception {
    private final String strategyId;
    
    /**
     * Constructs a new StrategyExecutionException with the specified strategy ID and detail message.
     * 
     * @param strategyId the ID of the strategy that encountered an error
     * @param message the detail message
     */
    public StrategyExecutionException(String strategyId, String message) {
        super(message);
        this.strategyId = strategyId;
    }
    
    /**
     * Constructs a new StrategyExecutionException with the specified strategy ID, detail message, and cause.
     * 
     * @param strategyId the ID of the strategy that encountered an error
     * @param message the detail message
     * @param cause the cause of the exception
     */
    public StrategyExecutionException(String strategyId, String message, Throwable cause) {
        super(message, cause);
        this.strategyId = strategyId;
    }
    
    /**
     * Gets the ID of the strategy that encountered an error during execution.
     * 
     * @return the strategy ID
     */
    public String getStrategyId() {
        return strategyId;
    }
} 