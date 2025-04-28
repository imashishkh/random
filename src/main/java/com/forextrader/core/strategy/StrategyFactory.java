package com.forextrader.core.strategy;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Factory for creating and managing strategy instances.
 * Provides mechanisms to create, register, and retrieve strategies.
 */
public class StrategyFactory {
    private static final Logger logger = Logger.getLogger(StrategyFactory.class.getName());
    
    private final Map<String, Strategy> strategies = new HashMap<>();
    private final Map<String, StrategyCreator> strategyCreators = new HashMap<>();
    
    /**
     * Interface for strategy creation.
     */
    public interface StrategyCreator {
        /**
         * Creates a new strategy instance.
         * 
         * @param config The strategy configuration
         * @return The created strategy
         */
        Strategy createStrategy(Map<String, Object> config);
    }
    
    /**
     * Creates a new strategy factory with default strategy types.
     */
    public StrategyFactory() {
        registerDefaultStrategies();
    }
    
    /**
     * Registers the default strategy types.
     */
    private void registerDefaultStrategies() {
        // Register Moving Average Crossover strategy
        registerStrategyType("MA_CROSSOVER", config -> {
            MovingAverageCrossoverStrategy strategy = new MovingAverageCrossoverStrategy();
            if (config != null) {
                strategy.initialize(config);
            }
            return strategy;
        });
        
        logger.info("Registered default strategy types");
    }
    
    /**
     * Registers a new strategy type.
     * 
     * @param strategyType The strategy type identifier
     * @param creator The strategy creator
     */
    public void registerStrategyType(String strategyType, StrategyCreator creator) {
        strategyCreators.put(strategyType, creator);
        logger.info("Registered strategy type: " + strategyType);
    }
    
    /**
     * Creates a new strategy of the specified type.
     * 
     * @param strategyType The strategy type identifier
     * @param config The strategy configuration
     * @return The created strategy, or null if the strategy type is not registered
     */
    public Strategy createStrategy(String strategyType, Map<String, Object> config) {
        StrategyCreator creator = strategyCreators.get(strategyType);
        if (creator == null) {
            logger.warning("Unknown strategy type: " + strategyType);
            return null;
        }
        
        try {
            Strategy strategy = creator.createStrategy(config);
            logger.info("Created strategy: " + strategy.getName() + " (" + strategy.getId() + ")");
            return strategy;
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Error creating strategy of type: " + strategyType, e);
            return null;
        }
    }
    
    /**
     * Registers a strategy instance.
     * 
     * @param strategy The strategy to register
     * @return true if the strategy was registered, false if a strategy with the same ID already exists
     */
    public boolean registerStrategy(Strategy strategy) {
        if (strategy == null) {
            return false;
        }
        
        String strategyId = strategy.getId();
        if (strategies.containsKey(strategyId)) {
            logger.warning("Strategy with ID already exists: " + strategyId);
            return false;
        }
        
        strategies.put(strategyId, strategy);
        logger.info("Registered strategy: " + strategy.getName() + " (" + strategyId + ")");
        return true;
    }
    
    /**
     * Gets a registered strategy by ID.
     * 
     * @param strategyId The strategy ID
     * @return The strategy, or null if not found
     */
    public Strategy getStrategy(String strategyId) {
        return strategies.get(strategyId);
    }
    
    /**
     * Gets all registered strategies.
     * 
     * @return A collection of all registered strategies
     */
    public Collection<Strategy> getAllStrategies() {
        return strategies.values();
    }
    
    /**
     * Unregisters a strategy.
     * 
     * @param strategyId The ID of the strategy to unregister
     * @return The unregistered strategy, or null if not found
     */
    public Strategy unregisterStrategy(String strategyId) {
        Strategy strategy = strategies.remove(strategyId);
        if (strategy != null) {
            logger.info("Unregistered strategy: " + strategy.getName() + " (" + strategyId + ")");
        }
        return strategy;
    }
    
    /**
     * Creates and registers a new strategy.
     * 
     * @param strategyType The strategy type identifier
     * @param config The strategy configuration
     * @return The created and registered strategy, or null if creation failed
     */
    public Strategy createAndRegisterStrategy(String strategyType, Map<String, Object> config) {
        Strategy strategy = createStrategy(strategyType, config);
        if (strategy != null && registerStrategy(strategy)) {
            return strategy;
        }
        return null;
    }
} 