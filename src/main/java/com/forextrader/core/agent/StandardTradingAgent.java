package com.forextrader.core.agent;

import com.forextrader.core.health.HealthStatus;
import com.forextrader.core.strategy.TradingStrategy;
import com.forextrader.core.market.MarketDataProvider;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Standard implementation of a trading agent with basic trading capabilities.
 * This agent can execute strategies on market data and manage trading operations.
 */
public class StandardTradingAgent extends AbstractTradingAgent {
    private static final Logger logger = LoggerFactory.getLogger(StandardTradingAgent.class);
    
    private final List<TradingStrategy> strategies = new ArrayList<>();
    private MarketDataProvider marketDataProvider;
    private final int maxRetries;
    private final long retryDelayMs;
    
    /**
     * Creates a new standard trading agent with a randomly generated ID.
     */
    public StandardTradingAgent() {
        this(UUID.randomUUID().toString());
    }
    
    /**
     * Creates a new standard trading agent with the specified ID.
     *
     * @param agentId the unique identifier for this agent
     */
    public StandardTradingAgent(String agentId) {
        this(agentId, 3, 1000); // Default to 3 retries with 1 second delay
    }
    
    /**
     * Creates a new standard trading agent with the specified parameters.
     *
     * @param agentId the unique identifier for this agent
     * @param maxRetries maximum number of retries for operations
     * @param retryDelayMs delay between retries in milliseconds
     */
    public StandardTradingAgent(String agentId, int maxRetries, long retryDelayMs) {
        super(agentId, AgentType.STANDARD);
        this.maxRetries = maxRetries;
        this.retryDelayMs = retryDelayMs;
    }
    
    /**
     * Set the market data provider for this agent.
     *
     * @param marketDataProvider the market data provider to use
     */
    public void setMarketDataProvider(MarketDataProvider marketDataProvider) {
        this.marketDataProvider = marketDataProvider;
    }
    
    /**
     * Add a trading strategy to this agent.
     *
     * @param strategy the trading strategy to add
     */
    public void addStrategy(TradingStrategy strategy) {
        strategies.add(strategy);
    }
    
    @Override
    public boolean initialize() {
        try {
            logger.info("Initializing standard trading agent: {}", agentId);
            
            if (marketDataProvider == null) {
                logger.error("Market data provider not set for agent: {}", agentId);
                return false;
            }
            
            if (strategies.isEmpty()) {
                logger.warn("No strategies added to agent: {}", agentId);
            }
            
            // Initialize all strategies
            for (TradingStrategy strategy : strategies) {
                if (!initializeStrategy(strategy)) {
                    logger.error("Failed to initialize strategy: {}", strategy);
                    return false;
                }
            }
            
            initialized = true;
            logger.info("Standard trading agent initialized: {}", agentId);
            return true;
        } catch (Exception e) {
            logger.error("Error initializing standard trading agent: {}", agentId, e);
            return false;
        }
    }
    
    private boolean initializeStrategy(TradingStrategy strategy) {
        int retries = 0;
        Exception lastException = null;
        
        while (retries < maxRetries) {
            try {
                logger.debug("Initializing strategy: {}, attempt: {}", strategy, retries + 1);
                strategy.initialize();
                return true;
            } catch (Exception e) {
                lastException = e;
                logger.warn("Strategy initialization failed, retrying: {}", strategy, e);
                retries++;
                
                try {
                    Thread.sleep(retryDelayMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    logger.warn("Interrupted during retry delay", ie);
                    return false;
                }
            }
        }
        
        logger.error("Failed to initialize strategy after {} attempts: {}", maxRetries, strategy, lastException);
        return false;
    }
    
    @Override
    public boolean start() {
        if (!initialized) {
            logger.error("Cannot start agent {} - not initialized", agentId);
            return false;
        }
        
        if (running) {
            logger.warn("Agent {} already running", agentId);
            return true;
        }
        
        try {
            logger.info("Starting standard trading agent: {}", agentId);
            
            // Start all strategies
            for (TradingStrategy strategy : strategies) {
                strategy.start();
            }
            
            running = true;
            logger.info("Standard trading agent started: {}", agentId);
            return true;
        } catch (Exception e) {
            logger.error("Error starting standard trading agent: {}", agentId, e);
            return false;
        }
    }
    
    @Override
    public boolean stop() {
        if (!running) {
            logger.warn("Agent {} not running", agentId);
            return true;
        }
        
        try {
            logger.info("Stopping standard trading agent: {}", agentId);
            
            // Stop all strategies
            for (TradingStrategy strategy : strategies) {
                try {
                    strategy.stop();
                } catch (Exception e) {
                    logger.error("Error stopping strategy: {}", strategy, e);
                }
            }
            
            running = false;
            logger.info("Standard trading agent stopped: {}", agentId);
            return true;
        } catch (Exception e) {
            logger.error("Error stopping standard trading agent: {}", agentId, e);
            return false;
        }
    }
    
    @Override
    public HealthStatus checkHealth() {
        if (!initialized) {
            return HealthStatus.DOWN.withDetail("reason", "Agent not initialized");
        }
        
        if (!running) {
            return HealthStatus.DOWN.withDetail("reason", "Agent not running");
        }
        
        // Check market data provider health
        if (marketDataProvider == null) {
            return HealthStatus.DEGRADED.withDetail("reason", "Market data provider not set");
        }
        
        // Check strategies
        if (strategies.isEmpty()) {
            return HealthStatus.DEGRADED.withDetail("reason", "No strategies configured");
        }
        
        // Further health checks could include:
        // - Connectivity to trading platforms
        // - Strategy performance metrics
        // - Error rates
        
        return HealthStatus.UP.withDetail("strategies", strategies.size());
    }
} 