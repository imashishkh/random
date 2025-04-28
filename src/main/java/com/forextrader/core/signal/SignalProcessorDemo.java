package com.forextrader.core.signal;

import com.forextrader.core.model.MarketData;
import com.forextrader.core.model.Signal;
import com.forextrader.core.model.SymbolData;
import com.forextrader.core.strategy.MovingAverageCrossoverStrategy;
import com.forextrader.core.strategy.Strategy;
import com.forextrader.core.strategy.StrategyFactory;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Logger;

/**
 * Demonstrates the usage of the strategy and signal processor components.
 * This class shows how to set up strategies, generate signals, and process them.
 */
public class SignalProcessorDemo {
    private static final Logger logger = Logger.getLogger(SignalProcessorDemo.class.getName());
    
    private final StrategyFactory strategyFactory;
    private final SignalProcessor signalProcessor;
    
    private final AtomicInteger processedSignals = new AtomicInteger(0);
    private final AtomicInteger buySignals = new AtomicInteger(0);
    private final AtomicInteger sellSignals = new AtomicInteger(0);
    
    /**
     * Creates a new signal processor demo.
     */
    public SignalProcessorDemo() {
        strategyFactory = new StrategyFactory();
        signalProcessor = new SignalProcessor();
        
        // Set up signal handlers
        setupSignalHandlers();
    }
    
    /**
     * Sets up signal handlers for the signal processor.
     */
    private void setupSignalHandlers() {
        // Add a simple logging handler
        signalProcessor.addHandler(signal -> {
            logger.info("Received signal: " + signal);
            processedSignals.incrementAndGet();
            
            if (signal.getType() == Signal.SignalType.BUY) {
                buySignals.incrementAndGet();
            } else if (signal.getType() == Signal.SignalType.SELL) {
                sellSignals.incrementAndGet();
            }
        });
    }
    
    /**
     * Creates and configures a moving average crossover strategy.
     * 
     * @param symbol The trading symbol
     * @param shortPeriod The short-term moving average period
     * @param longPeriod The long-term moving average period
     * @return The configured strategy
     */
    public Strategy createMACrossoverStrategy(String symbol, int shortPeriod, int longPeriod) {
        // Create a strategy configuration
        Map<String, Object> config = new HashMap<>();
        config.put("shortPeriod", shortPeriod);
        config.put("longPeriod", longPeriod);
        config.put("confidenceThreshold", 0.6);
        
        // Create the strategy using the factory
        Strategy strategy = strategyFactory.createStrategy("MA_CROSSOVER", config);
        
        // Add the symbol to trade
        strategy.addSymbol(symbol);
        
        return strategy;
    }
    
    /**
     * Creates a sample market data object for a symbol.
     * 
     * @param symbol The trading symbol
     * @param price The current price
     * @return A market data object with the symbol data
     */
    public MarketData createMarketData(String symbol, BigDecimal price) {
        MarketData marketData = new MarketData();
        
        SymbolData symbolData = new SymbolData(symbol);
        symbolData.setLastPrice(price);
        symbolData.setBid(price.subtract(new BigDecimal("0.0001")));
        symbolData.setAsk(price.add(new BigDecimal("0.0001")));
        
        marketData.setSymbolData(symbol, symbolData);
        
        return marketData;
    }
    
    /**
     * Simulates price movement and processes signals.
     * 
     * @param strategy The strategy to use
     * @param symbol The trading symbol
     * @param initialPrice The initial price
     * @param priceMovements An array of price movements to simulate
     */
    public void simulatePriceMovements(Strategy strategy, String symbol, 
                                     BigDecimal initialPrice, double[] priceMovements) {
        BigDecimal currentPrice = initialPrice;
        
        logger.info("Starting price simulation for " + symbol + " at " + currentPrice);
        
        for (int i = 0; i < priceMovements.length; i++) {
            // Update price
            double movement = priceMovements[i];
            BigDecimal newPrice = currentPrice.add(new BigDecimal(movement));
            currentPrice = newPrice;
            
            // Create market data
            MarketData marketData = createMarketData(symbol, currentPrice);
            
            // Generate signal
            Signal signal = strategy.analyze(marketData);
            
            if (signal != null) {
                logger.info("Generated signal at price " + currentPrice + ": " + signal);
                signalProcessor.processSignal(signal);
            }
        }
        
        // Print summary
        logger.info("Simulation complete. Processed " + processedSignals.get() + " signals (" +
                   buySignals.get() + " buy, " + sellSignals.get() + " sell)");
    }
    
    /**
     * Main demo method.
     */
    public static void main(String[] args) {
        SignalProcessorDemo demo = new SignalProcessorDemo();
        
        // Create a strategy
        Strategy maStrategy = demo.createMACrossoverStrategy("EURUSD", 5, 10);
        
        // Initialize the strategy
        maStrategy.initialize(null);
        
        // Simulate price movements
        double[] priceMovements = {
            0.0002, 0.0003, 0.0001, -0.0001, -0.0002, 0.0004, 0.0005, 0.0003,
            -0.0006, -0.0005, -0.0004, -0.0003, 0.0001, 0.0002, 0.0004, 0.0006,
            0.0005, 0.0003, -0.0001, -0.0003, -0.0007, -0.0005, -0.0002, 0.0001
        };
        
        demo.simulatePriceMovements(maStrategy, "EURUSD", new BigDecimal("1.1000"), priceMovements);
    }
} 