package com.forextrader.core.model;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;

/**
 * Represents market data for a specific trading symbol.
 * Contains price information and additional indicators.
 */
public class SymbolData {
    private final String symbol;
    private BigDecimal bid;
    private BigDecimal ask;
    private BigDecimal lastPrice;
    private BigDecimal high;
    private BigDecimal low;
    private BigDecimal volume;
    private Map<String, Object> additionalData;
    
    /**
     * Creates a new SymbolData instance for the specified symbol.
     * 
     * @param symbol the trading symbol (e.g., "EURUSD")
     */
    public SymbolData(String symbol) {
        this.symbol = symbol;
        this.additionalData = new HashMap<>();
    }
    
    /**
     * Creates a new SymbolData instance with full price information.
     * 
     * @param symbol the trading symbol
     * @param bid the bid price
     * @param ask the ask price
     * @param lastPrice the last traded price
     * @param high the high price for the current period
     * @param low the low price for the current period
     * @param volume the trading volume
     */
    public SymbolData(String symbol, BigDecimal bid, BigDecimal ask, BigDecimal lastPrice, 
                     BigDecimal high, BigDecimal low, BigDecimal volume) {
        this.symbol = symbol;
        this.bid = bid;
        this.ask = ask;
        this.lastPrice = lastPrice;
        this.high = high;
        this.low = low;
        this.volume = volume;
        this.additionalData = new HashMap<>();
    }
    
    /**
     * Gets the trading symbol.
     * 
     * @return the symbol
     */
    public String getSymbol() {
        return symbol;
    }
    
    /**
     * Gets the bid price.
     * 
     * @return the bid price
     */
    public BigDecimal getBid() {
        return bid;
    }
    
    /**
     * Sets the bid price.
     * 
     * @param bid the bid price to set
     */
    public void setBid(BigDecimal bid) {
        this.bid = bid;
    }
    
    /**
     * Gets the ask price.
     * 
     * @return the ask price
     */
    public BigDecimal getAsk() {
        return ask;
    }
    
    /**
     * Sets the ask price.
     * 
     * @param ask the ask price to set
     */
    public void setAsk(BigDecimal ask) {
        this.ask = ask;
    }
    
    /**
     * Gets the last traded price.
     * 
     * @return the last price
     */
    public BigDecimal getLastPrice() {
        return lastPrice;
    }
    
    /**
     * Sets the last traded price.
     * 
     * @param lastPrice the last price to set
     */
    public void setLastPrice(BigDecimal lastPrice) {
        this.lastPrice = lastPrice;
    }
    
    /**
     * Gets the high price for the current period.
     * 
     * @return the high price
     */
    public BigDecimal getHigh() {
        return high;
    }
    
    /**
     * Sets the high price for the current period.
     * 
     * @param high the high price to set
     */
    public void setHigh(BigDecimal high) {
        this.high = high;
    }
    
    /**
     * Gets the low price for the current period.
     * 
     * @return the low price
     */
    public BigDecimal getLow() {
        return low;
    }
    
    /**
     * Sets the low price for the current period.
     * 
     * @param low the low price to set
     */
    public void setLow(BigDecimal low) {
        this.low = low;
    }
    
    /**
     * Gets the trading volume.
     * 
     * @return the volume
     */
    public BigDecimal getVolume() {
        return volume;
    }
    
    /**
     * Sets the trading volume.
     * 
     * @param volume the volume to set
     */
    public void setVolume(BigDecimal volume) {
        this.volume = volume;
    }
    
    /**
     * Gets the spread between ask and bid prices.
     * 
     * @return the spread, or null if either ask or bid is null
     */
    public BigDecimal getSpread() {
        if (ask != null && bid != null) {
            return ask.subtract(bid);
        }
        return null;
    }
    
    /**
     * Adds additional data for this symbol.
     * 
     * @param key the data key
     * @param value the data value
     */
    public void addAdditionalData(String key, Object value) {
        additionalData.put(key, value);
    }
    
    /**
     * Gets additional data for this symbol.
     * 
     * @param key the data key
     * @return the data value
     */
    public Object getAdditionalData(String key) {
        return additionalData.get(key);
    }
    
    /**
     * Gets all additional data for this symbol.
     * 
     * @return the map of additional data
     */
    public Map<String, Object> getAllAdditionalData() {
        return additionalData;
    }
} 