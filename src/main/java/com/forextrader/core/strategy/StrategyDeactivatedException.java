package com.forextrader.core.strategy;

/**
 * Exception thrown when attempting to execute a trading strategy that has been deactivated.
 */
public class StrategyDeactivatedException extends Exception {
    private final String strategyId;
    private final String deactivationReason;
    
    /**
     * Constructs a new StrategyDeactivatedException with the specified strategy ID.
     * 
     * @param strategyId the ID of the deactivated strategy
     */
    public StrategyDeactivatedException(String strategyId) {
        super("Strategy with ID: " + strategyId + " is currently deactivated");
        this.strategyId = strategyId;
        this.deactivationReason = null;
    }
    
    /**
     * Constructs a new StrategyDeactivatedException with the specified strategy ID and deactivation reason.
     * 
     * @param strategyId the ID of the deactivated strategy
     * @param deactivationReason the reason the strategy was deactivated
     */
    public StrategyDeactivatedException(String strategyId, String deactivationReason) {
        super("Strategy with ID: " + strategyId + " is currently deactivated. Reason: " + deactivationReason);
        this.strategyId = strategyId;
        this.deactivationReason = deactivationReason;
    }
    
    /**
     * Gets the ID of the deactivated strategy.
     * 
     * @return the strategy ID
     */
    public String getStrategyId() {
        return strategyId;
    }
    
    /**
     * Gets the reason the strategy was deactivated, or null if no reason was provided.
     * 
     * @return the deactivation reason, or null
     */
    public String getDeactivationReason() {
        return deactivationReason;
    }
} 