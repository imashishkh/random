package com.forextrader.core.strategy;

import com.forextrader.core.model.MarketData;
import com.forextrader.core.model.Signal;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.logging.Logger;

/**
 * Abstract base implementation of the Strategy interface.
 * Provides common functionality for all trading strategies.
 */
public abstract class AbstractStrategy implements Strategy {
    private static final Logger logger = Logger.getLogger(AbstractStrategy.class.getName());
    
    private final String id;
    private final String name;
    private final String description;
    private final List<String> symbols;
    private final Map<String, Object> config;
    private boolean ready;
    
    /**
     * Creates a new strategy with a random ID.
     *
     * @param name The name of the strategy
     * @param description The description of the strategy
     */
    protected AbstractStrategy(String name, String description) {
        this(UUID.randomUUID().toString(), name, description);
    }
    
    /**
     * Creates a new strategy with the specified ID.
     *
     * @param id The unique identifier for this strategy
     * @param name The name of the strategy
     * @param description The description of the strategy
     */
    protected AbstractStrategy(String id, String name, String description) {
        this.id = id;
        this.name = name;
        this.description = description;
        this.symbols = new ArrayList<>();
        this.config = new HashMap<>();
        this.ready = false;
    }
    
    @Override
    public String getId() {
        return id;
    }
    
    @Override
    public String getName() {
        return name;
    }
    
    @Override
    public String getDescription() {
        return description;
    }
    
    @Override
    public List<String> getSymbols() {
        return new ArrayList<>(symbols);
    }
    
    @Override
    public void addSymbol(String symbol) {
        if (!symbols.contains(symbol)) {
            symbols.add(symbol);
            logger.info(String.format("Added symbol %s to strategy %s", symbol, name));
        }
    }
    
    @Override
    public void removeSymbol(String symbol) {
        if (symbols.remove(symbol)) {
            logger.info(String.format("Removed symbol %s from strategy %s", symbol, name));
        }
    }
    
    @Override
    public Map<String, Object> getConfig() {
        return new HashMap<>(config);
    }
    
    @Override
    public void setConfig(String key, Object value) {
        config.put(key, value);
        logger.fine(String.format("Set configuration %s=%s for strategy %s", key, value, name));
        
        // Configuration change might require re-initialization
        configChanged(key, value);
    }
    
    @Override
    public void initialize(Map<String, Object> config) {
        this.config.clear();
        if (config != null) {
            this.config.putAll(config);
        }
        
        // Call implementation-specific initialization
        doInitialize();
        
        // Mark the strategy as ready if initialization was successful
        ready = isInitialized();
        
        if (ready) {
            logger.info(String.format("Strategy %s (%s) initialized successfully", name, id));
        } else {
            logger.warning(String.format("Strategy %s (%s) initialization incomplete", name, id));
        }
    }
    
    @Override
    public void reset() {
        doReset();
        logger.info(String.format("Strategy %s (%s) reset", name, id));
    }
    
    @Override
    public boolean isReady() {
        return ready;
    }
    
    /**
     * Sets the ready state of the strategy.
     *
     * @param ready The new ready state
     */
    protected void setReady(boolean ready) {
        this.ready = ready;
    }
    
    /**
     * Called when a configuration parameter changes.
     * Override this method to handle configuration changes.
     *
     * @param key The configuration parameter key
     * @param value The new value
     */
    protected void configChanged(String key, Object value) {
        // Default implementation does nothing
    }
    
    /**
     * Implementation-specific initialization.
     * Override this method to perform strategy-specific initialization.
     */
    protected abstract void doInitialize();
    
    /**
     * Implementation-specific reset logic.
     * Override this method to perform strategy-specific reset.
     */
    protected abstract void doReset();
    
    /**
     * Checks if the strategy is properly initialized.
     * Override this method to provide initialization status.
     *
     * @return true if the strategy is initialized, false otherwise
     */
    protected abstract boolean isInitialized();
    
    /**
     * Creates a signal of the specified type for the given symbol.
     *
     * @param symbol The trading symbol
     * @param type The signal type
     * @return A new signal instance
     */
    protected Signal createSignal(String symbol, Signal.SignalType type) {
        return new Signal(symbol, type, id);
    }
    
    /**
     * Validates that the market data contains all required symbols.
     *
     * @param marketData The market data to validate
     * @return true if the market data is valid, false otherwise
     */
    protected boolean validateMarketData(MarketData marketData) {
        if (marketData == null) {
            logger.warning("Market data is null");
            return false;
        }
        
        for (String symbol : symbols) {
            if (marketData.getSymbolData(symbol) == null) {
                logger.warning(String.format("Market data does not contain required symbol: %s", symbol));
                return false;
            }
        }
        
        return true;
    }
} 