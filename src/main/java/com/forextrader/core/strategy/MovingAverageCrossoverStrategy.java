package com.forextrader.core.strategy;

import com.forextrader.core.model.MarketData;
import com.forextrader.core.model.Signal;
import com.forextrader.core.model.SymbolData;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.Map;
import java.util.logging.Logger;

/**
 * A strategy that generates trading signals based on the crossing of short-term and long-term
 * moving averages. When the short-term MA crosses above the long-term MA, a BUY signal is generated.
 * When the short-term MA crosses below the long-term MA, a SELL signal is generated.
 */
public class MovingAverageCrossoverStrategy extends AbstractStrategy {
    private static final Logger logger = Logger.getLogger(MovingAverageCrossoverStrategy.class.getName());
    
    // Configuration parameter keys
    private static final String SHORT_PERIOD_KEY = "shortPeriod";
    private static final String LONG_PERIOD_KEY = "longPeriod";
    private static final String CONFIDENCE_THRESHOLD_KEY = "confidenceThreshold";
    
    // Default values
    private static final int DEFAULT_SHORT_PERIOD = 10;
    private static final int DEFAULT_LONG_PERIOD = 30;
    private static final double DEFAULT_CONFIDENCE_THRESHOLD = 0.7;
    
    // Price data for calculating moving averages
    private final Map<String, LinkedList<BigDecimal>> priceHistory;
    
    // Last calculated MA values (for determining crossovers)
    private final Map<String, BigDecimal> lastShortMAs;
    private final Map<String, BigDecimal> lastLongMAs;
    
    // Last signal type to avoid duplicate signals
    private final Map<String, Signal.SignalType> lastSignalTypes;
    
    // Initialized flag
    private boolean initialized = false;
    
    /**
     * Creates a new moving average crossover strategy.
     */
    public MovingAverageCrossoverStrategy() {
        super("Moving Average Crossover", "Generates signals based on short-term and long-term moving average crossovers");
        this.priceHistory = new HashMap<>();
        this.lastShortMAs = new HashMap<>();
        this.lastLongMAs = new HashMap<>();
        this.lastSignalTypes = new HashMap<>();
    }
    
    /**
     * Creates a new moving average crossover strategy with specified periods.
     *
     * @param shortPeriod The short-term moving average period
     * @param longPeriod The long-term moving average period
     */
    public MovingAverageCrossoverStrategy(int shortPeriod, int longPeriod) {
        super("Moving Average Crossover", "Generates signals based on short-term and long-term moving average crossovers");
        this.priceHistory = new HashMap<>();
        this.lastShortMAs = new HashMap<>();
        this.lastLongMAs = new HashMap<>();
        this.lastSignalTypes = new HashMap<>();
        
        // Set initial configuration
        setConfig(SHORT_PERIOD_KEY, shortPeriod);
        setConfig(LONG_PERIOD_KEY, longPeriod);
    }
    
    @Override
    public Signal analyze(MarketData marketData) {
        if (!isReady()) {
            logger.warning("Strategy not ready");
            return null;
        }
        
        if (!validateMarketData(marketData)) {
            return null;
        }
        
        // Process all configured symbols
        for (String symbol : getSymbols()) {
            SymbolData symbolData = marketData.getSymbolData(symbol);
            if (symbolData != null && symbolData.getLastPrice() != null) {
                // Update price history
                updatePriceHistory(symbol, symbolData.getLastPrice());
                
                // Check if we have enough data for generating signals
                if (hasEnoughData(symbol)) {
                    // Calculate moving averages
                    int shortPeriod = getShortPeriod();
                    int longPeriod = getLongPeriod();
                    
                    BigDecimal shortMA = calculateMA(symbol, shortPeriod);
                    BigDecimal longMA = calculateMA(symbol, longPeriod);
                    
                    // Store current MAs for future comparison
                    BigDecimal prevShortMA = lastShortMAs.getOrDefault(symbol, shortMA);
                    BigDecimal prevLongMA = lastLongMAs.getOrDefault(symbol, longMA);
                    
                    lastShortMAs.put(symbol, shortMA);
                    lastLongMAs.put(symbol, longMA);
                    
                    // Detect crossovers
                    Signal signal = detectCrossover(symbol, shortMA, longMA, prevShortMA, prevLongMA, symbolData);
                    if (signal != null) {
                        return signal;
                    }
                }
            }
        }
        
        // No signals generated
        return null;
    }
    
    /**
     * Detects if a crossover has occurred and generates appropriate signals.
     */
    private Signal detectCrossover(String symbol, BigDecimal shortMA, BigDecimal longMA, 
                                 BigDecimal prevShortMA, BigDecimal prevLongMA, 
                                 SymbolData symbolData) {
        
        // Determine current position (short MA above or below long MA)
        boolean isAbove = shortMA.compareTo(longMA) > 0;
        boolean wasAbove = prevShortMA.compareTo(prevLongMA) > 0;
        
        // Get the last signal type for this symbol
        Signal.SignalType lastSignalType = lastSignalTypes.getOrDefault(symbol, Signal.SignalType.UNKNOWN);
        
        // Calculate crossover confidence (0 to 1)
        BigDecimal confidence = calculateConfidence(shortMA, longMA);
        
        // Check if confidence meets threshold
        double confidenceThreshold = getConfidenceThreshold();
        if (confidence.doubleValue() < confidenceThreshold) {
            return null;
        }
        
        // Generate signals based on crossover detection
        if (isAbove && !wasAbove) {
            // Bullish crossover (short MA crosses above long MA)
            if (lastSignalType != Signal.SignalType.BUY) {
                Signal signal = createSignal(symbol, Signal.SignalType.BUY);
                signal.setPrice(symbolData.getLastPrice());
                signal.setConfidence(confidence);
                
                // Set target price and stop loss based on recent volatility
                BigDecimal atr = calculateATR(symbol);
                signal.setTargetPrice(symbolData.getLastPrice().add(atr.multiply(new BigDecimal("2"))));
                signal.setStopLoss(symbolData.getLastPrice().subtract(atr));
                
                signal.setRationale(String.format("Bullish crossover: Short MA (%.2f) crossed above Long MA (%.2f)", 
                        shortMA.doubleValue(), longMA.doubleValue()));
                
                lastSignalTypes.put(symbol, Signal.SignalType.BUY);
                return signal;
            }
        } else if (!isAbove && wasAbove) {
            // Bearish crossover (short MA crosses below long MA)
            if (lastSignalType != Signal.SignalType.SELL) {
                Signal signal = createSignal(symbol, Signal.SignalType.SELL);
                signal.setPrice(symbolData.getLastPrice());
                signal.setConfidence(confidence);
                
                // Set target price and stop loss based on recent volatility
                BigDecimal atr = calculateATR(symbol);
                signal.setTargetPrice(symbolData.getLastPrice().subtract(atr.multiply(new BigDecimal("2"))));
                signal.setStopLoss(symbolData.getLastPrice().add(atr));
                
                signal.setRationale(String.format("Bearish crossover: Short MA (%.2f) crossed below Long MA (%.2f)", 
                        shortMA.doubleValue(), longMA.doubleValue()));
                
                lastSignalTypes.put(symbol, Signal.SignalType.SELL);
                return signal;
            }
        }
        
        // No crossover or no new signal
        return null;
    }
    
    /**
     * Updates the price history for a symbol.
     */
    private void updatePriceHistory(String symbol, BigDecimal price) {
        LinkedList<BigDecimal> prices = priceHistory.computeIfAbsent(symbol, k -> new LinkedList<>());
        prices.add(price);
        
        // Limit history size to maximum required period plus some buffer
        int maxPeriod = Math.max(getShortPeriod(), getLongPeriod()) + 10;
        while (prices.size() > maxPeriod) {
            prices.removeFirst();
        }
    }
    
    /**
     * Calculates a simple moving average for the specified period.
     */
    private BigDecimal calculateMA(String symbol, int period) {
        LinkedList<BigDecimal> prices = priceHistory.get(symbol);
        if (prices == null || prices.size() < period) {
            return BigDecimal.ZERO;
        }
        
        BigDecimal sum = BigDecimal.ZERO;
        int count = 0;
        
        // Calculate sum of last 'period' prices
        for (int i = prices.size() - 1; i >= Math.max(0, prices.size() - period); i--) {
            sum = sum.add(prices.get(i));
            count++;
        }
        
        // Prevent division by zero
        if (count == 0) return BigDecimal.ZERO;
        
        // Calculate average
        return sum.divide(new BigDecimal(count), 8, BigDecimal.ROUND_HALF_UP);
    }
    
    /**
     * Calculates a simple Average True Range indicator to estimate volatility.
     */
    private BigDecimal calculateATR(String symbol) {
        // Simplified ATR calculation based on price variance
        LinkedList<BigDecimal> prices = priceHistory.get(symbol);
        if (prices == null || prices.size() < 5) {
            return new BigDecimal("0.001").multiply(prices.getLast()); // Default 0.1% if not enough data
        }
        
        // Calculate a simple approximation of ATR using standard deviation
        BigDecimal sum = BigDecimal.ZERO;
        BigDecimal sumOfSquares = BigDecimal.ZERO;
        int count = Math.min(14, prices.size());
        
        for (int i = prices.size() - count; i < prices.size(); i++) {
            sum = sum.add(prices.get(i));
            sumOfSquares = sumOfSquares.add(prices.get(i).multiply(prices.get(i)));
        }
        
        BigDecimal mean = sum.divide(new BigDecimal(count), 8, BigDecimal.ROUND_HALF_UP);
        BigDecimal variance = sumOfSquares.divide(new BigDecimal(count), 8, BigDecimal.ROUND_HALF_UP)
                .subtract(mean.multiply(mean));
        
        // Square root approx for standard deviation
        BigDecimal stdDev = new BigDecimal(Math.sqrt(variance.doubleValue()));
        
        // Return ATR approximation (using 1.5x standard deviation)
        return stdDev.multiply(new BigDecimal("1.5"));
    }
    
    /**
     * Calculates confidence value for the crossover signal.
     */
    private BigDecimal calculateConfidence(BigDecimal shortMA, BigDecimal longMA) {
        // Calculate divergence between MAs as a percentage
        BigDecimal divergence = shortMA.subtract(longMA).abs();
        BigDecimal relativeDiv = divergence.divide(longMA, 8, BigDecimal.ROUND_HALF_UP);
        
        // A simple confidence calculation:
        // - Higher divergence increases confidence (up to a point)
        // - Scale to 0-1 range
        double confidence = Math.min(1.0, relativeDiv.doubleValue() * 20.0);
        
        return new BigDecimal(confidence).setScale(2, BigDecimal.ROUND_HALF_UP);
    }
    
    /**
     * Checks if we have enough price history to generate signals.
     */
    private boolean hasEnoughData(String symbol) {
        LinkedList<BigDecimal> prices = priceHistory.get(symbol);
        return prices != null && prices.size() >= getLongPeriod();
    }
    
    @Override
    protected void doInitialize() {
        // Validate configuration
        int shortPeriod = getShortPeriod();
        int longPeriod = getLongPeriod();
        
        if (shortPeriod >= longPeriod) {
            logger.warning("Short period must be less than long period");
            return;
        }
        
        if (shortPeriod < 2) {
            logger.warning("Short period must be at least 2");
            return;
        }
        
        if (longPeriod < 3) {
            logger.warning("Long period must be at least 3");
            return;
        }
        
        // Clear price history and calculated MAs
        priceHistory.clear();
        lastShortMAs.clear();
        lastLongMAs.clear();
        lastSignalTypes.clear();
        
        // Mark as initialized
        initialized = true;
        logger.info(String.format("Initialized Moving Average Crossover strategy with short period %d and long period %d", 
                shortPeriod, longPeriod));
    }
    
    @Override
    protected void doReset() {
        // Reset all data except configuration
        priceHistory.clear();
        lastShortMAs.clear();
        lastLongMAs.clear();
        lastSignalTypes.clear();
    }
    
    @Override
    protected boolean isInitialized() {
        return initialized;
    }
    
    @Override
    public String[] getTimeframes() {
        // This strategy works on various timeframes
        return new String[]{"1m", "5m", "15m", "1h", "4h", "1d"};
    }
    
    /**
     * Gets the short period from configuration.
     */
    private int getShortPeriod() {
        Object value = getConfig().get(SHORT_PERIOD_KEY);
        if (value instanceof Integer) {
            return (Integer) value;
        } else if (value instanceof String) {
            try {
                return Integer.parseInt((String) value);
            } catch (NumberFormatException e) {
                // Fall back to default
            }
        }
        return DEFAULT_SHORT_PERIOD;
    }
    
    /**
     * Gets the long period from configuration.
     */
    private int getLongPeriod() {
        Object value = getConfig().get(LONG_PERIOD_KEY);
        if (value instanceof Integer) {
            return (Integer) value;
        } else if (value instanceof String) {
            try {
                return Integer.parseInt((String) value);
            } catch (NumberFormatException e) {
                // Fall back to default
            }
        }
        return DEFAULT_LONG_PERIOD;
    }
    
    /**
     * Gets the confidence threshold from configuration.
     */
    private double getConfidenceThreshold() {
        Object value = getConfig().get(CONFIDENCE_THRESHOLD_KEY);
        if (value instanceof Double) {
            return (Double) value;
        } else if (value instanceof String) {
            try {
                return Double.parseDouble((String) value);
            } catch (NumberFormatException e) {
                // Fall back to default
            }
        }
        return DEFAULT_CONFIDENCE_THRESHOLD;
    }
} 