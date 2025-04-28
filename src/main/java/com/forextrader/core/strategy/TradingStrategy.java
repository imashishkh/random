package com.forextrader.core.strategy;

import com.forextrader.core.health.HealthCheck;
import com.forextrader.core.health.HealthStatus;
import com.forextrader.core.model.MarketData;
import com.forextrader.core.model.Signal;
import com.forextrader.core.model.StrategyConfig;
import com.forextrader.core.model.StrategyState;

/**
 * Interface for trading strategies that can be executed by trading agents.
 * A trading strategy defines the logic for market analysis, entry/exit signals,
 * position sizing, and risk management.
 */
public interface TradingStrategy extends HealthCheck {
    
    /**
     * Get the unique identifier for this strategy.
     * 
     * @return the strategy ID
     */
    String getStrategyId();
    
    /**
     * Get the name of this strategy.
     * 
     * @return the strategy name
     */
    String getName();
    
    /**
     * Get the current configuration of this strategy.
     * 
     * @return the current strategy configuration
     */
    StrategyConfig getConfig();
    
    /**
     * Updates the strategy configuration.
     * 
     * @param config the new configuration to apply
     * @throws StrategyValidationException if the new configuration fails validation
     */
    void configure(StrategyConfig config) throws StrategyValidationException;
    
    /**
     * Gets the current internal state of this strategy.
     * 
     * @return the current strategy state
     */
    StrategyState getState();
    
    /**
     * Processes new market data and updates internal state.
     * 
     * @param marketData the market data to process
     */
    void processMarketData(MarketData marketData);
    
    /**
     * Evaluates the current market conditions and strategy state to generate trading signals.
     * 
     * @return the generated signal, or null if no signal is generated
     */
    Signal generateSignal();
    
    /**
     * Initialize the strategy, loading any necessary data,
     * establishing connections, and preparing for execution.
     * 
     * @throws StrategyInitializationException if initialization fails
     */
    void initialize() throws StrategyInitializationException;
    
    /**
     * Start the strategy execution.
     * 
     * @throws StrategyExecutionException if the strategy cannot be started
     */
    void start() throws StrategyExecutionException;
    
    /**
     * Stop the strategy execution.
     * 
     * @throws StrategyExecutionException if the strategy cannot be stopped cleanly
     */
    void stop() throws StrategyExecutionException;
    
    /**
     * Check if the strategy is currently running.
     * 
     * @return true if the strategy is running, false otherwise
     */
    boolean isRunning();
    
    /**
     * Check if the strategy has been initialized.
     * 
     * @return true if the strategy has been initialized, false otherwise
     */
    boolean isInitialized();
    
    /**
     * Check the health of the strategy.
     * 
     * @return the current health status of the strategy
     */
    @Override
    HealthStatus checkHealth();
    
    /**
     * Initializes the strategy with the given configuration.
     * 
     * @param config the initial configuration
     * @throws StrategyValidationException if the configuration fails validation
     */
    void initialize(StrategyConfig config) throws StrategyValidationException;
    
    /**
     * Resets the strategy to its initial state.
     */
    void reset();
} 