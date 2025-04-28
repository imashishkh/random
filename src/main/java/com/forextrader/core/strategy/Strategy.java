package com.forextrader.core.strategy;

import com.forextrader.core.model.MarketData;
import com.forextrader.core.model.Signal;
import java.util.List;
import java.util.Map;

/**
 * Interface defining the contract for all trading strategies.
 * Strategies analyze market data and generate trading signals.
 */
public interface Strategy {
    
    /**
     * Gets the unique identifier for this strategy.
     * 
     * @return the strategy ID
     */
    String getId();
    
    /**
     * Gets the user-friendly name of this strategy.
     * 
     * @return the strategy name
     */
    String getName();
    
    /**
     * Gets the description of how this strategy works.
     * 
     * @return the strategy description
     */
    String getDescription();
    
    /**
     * Gets the list of symbols this strategy is configured to trade.
     * 
     * @return the list of trading symbols
     */
    List<String> getSymbols();
    
    /**
     * Adds a symbol to the list of symbols this strategy will trade.
     * 
     * @param symbol the trading symbol to add
     */
    void addSymbol(String symbol);
    
    /**
     * Removes a symbol from the list of symbols this strategy will trade.
     * 
     * @param symbol the trading symbol to remove
     */
    void removeSymbol(String symbol);
    
    /**
     * Analyzes the given market data and generates a trading signal.
     * This is the core method where strategy logic is implemented.
     * 
     * @param marketData the market data to analyze
     * @return the generated trading signal, or null if no signal is generated
     */
    Signal analyze(MarketData marketData);
    
    /**
     * Gets the configuration parameters for this strategy.
     * 
     * @return a map of configuration parameters
     */
    Map<String, Object> getConfig();
    
    /**
     * Sets a configuration parameter for this strategy.
     * 
     * @param key the parameter key
     * @param value the parameter value
     */
    void setConfig(String key, Object value);
    
    /**
     * Initializes the strategy with the given configuration.
     * 
     * @param config the configuration parameters
     */
    void initialize(Map<String, Object> config);
    
    /**
     * Resets the strategy's internal state.
     */
    void reset();
    
    /**
     * Gets the timeframe(s) this strategy operates on.
     * 
     * @return the timeframe(s) as an array of strings (e.g., "1m", "5m", "1h")
     */
    String[] getTimeframes();
    
    /**
     * Checks if this strategy is ready to generate signals.
     * 
     * @return true if the strategy is ready, false otherwise
     */
    boolean isReady();
} 