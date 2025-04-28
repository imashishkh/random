package com.forextrader.core.model;

import java.time.Instant;
import java.util.Map;
import java.util.Collections;
import java.util.HashMap;

/**
 * Represents a snapshot of market data at a specific point in time.
 * Contains price information and other market indicators for various symbols.
 */
public class MarketData {
    private final Instant timestamp;
    private final Map<String, SymbolData> symbolDataMap;
    
    /**
     * Creates a new MarketData instance with the current timestamp.
     */
    public MarketData() {
        this(Instant.now(), new HashMap<>());
    }
    
    /**
     * Creates a new MarketData instance with the specified timestamp.
     * 
     * @param timestamp the timestamp for this market data snapshot
     * @param symbolDataMap map of symbol data keyed by symbol name
     */
    public MarketData(Instant timestamp, Map<String, SymbolData> symbolDataMap) {
        this.timestamp = timestamp;
        this.symbolDataMap = new HashMap<>(symbolDataMap);
    }
    
    /**
     * Gets the timestamp when this market data was captured.
     * 
     * @return the timestamp
     */
    public Instant getTimestamp() {
        return timestamp;
    }
    
    /**
     * Gets the data for a specific symbol.
     * 
     * @param symbol the symbol to get data for
     * @return the symbol data, or null if no data exists for the symbol
     */
    public SymbolData getSymbolData(String symbol) {
        return symbolDataMap.get(symbol);
    }
    
    /**
     * Adds or updates data for a specific symbol.
     * 
     * @param symbol the symbol to update
     * @param data the new symbol data
     */
    public void setSymbolData(String symbol, SymbolData data) {
        symbolDataMap.put(symbol, data);
    }
    
    /**
     * Gets an unmodifiable view of all symbol data in this market data snapshot.
     * 
     * @return an unmodifiable map of symbol data keyed by symbol name
     */
    public Map<String, SymbolData> getAllSymbolData() {
        return Collections.unmodifiableMap(symbolDataMap);
    }
} 