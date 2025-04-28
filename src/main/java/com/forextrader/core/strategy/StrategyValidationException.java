package com.forextrader.core.strategy;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Exception thrown when a strategy fails validation checks.
 */
public class StrategyValidationException extends Exception {
    private final String strategyId;
    private final List<String> validationErrors;
    
    /**
     * Constructs a new StrategyValidationException with the specified strategy ID and validation error.
     * 
     * @param strategyId the ID of the strategy that failed validation
     * @param validationError the validation error message
     */
    public StrategyValidationException(String strategyId, String validationError) {
        super("Strategy validation failed for ID: " + strategyId + ". Error: " + validationError);
        this.strategyId = strategyId;
        this.validationErrors = Collections.singletonList(validationError);
    }
    
    /**
     * Constructs a new StrategyValidationException with the specified strategy ID and multiple validation errors.
     * 
     * @param strategyId the ID of the strategy that failed validation
     * @param validationErrors the list of validation error messages
     */
    public StrategyValidationException(String strategyId, List<String> validationErrors) {
        super("Strategy validation failed for ID: " + strategyId + ". Errors: " + String.join(", ", validationErrors));
        this.strategyId = strategyId;
        this.validationErrors = new ArrayList<>(validationErrors);
    }
    
    /**
     * Gets the ID of the strategy that failed validation.
     * 
     * @return the strategy ID
     */
    public String getStrategyId() {
        return strategyId;
    }
    
    /**
     * Gets the list of validation errors.
     * 
     * @return an unmodifiable list of validation error messages
     */
    public List<String> getValidationErrors() {
        return Collections.unmodifiableList(validationErrors);
    }
} 