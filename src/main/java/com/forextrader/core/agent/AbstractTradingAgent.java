package com.forextrader.core.agent;

import com.forextrader.core.health.HealthCheck;
import com.forextrader.core.health.HealthStatus;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Abstract base class for all trading agents in the system.
 * Provides common functionality and a standard interface for different types of agents.
 */
public abstract class AbstractTradingAgent implements HealthCheck {
    private static final Logger logger = LoggerFactory.getLogger(AbstractTradingAgent.class);
    
    protected final String agentId;
    protected final AgentType type;
    protected boolean initialized = false;
    protected boolean running = false;
    
    /**
     * Constructs a new trading agent with the specified ID and type.
     *
     * @param agentId Unique identifier for this agent
     * @param type The type of trading agent
     */
    protected AbstractTradingAgent(String agentId, AgentType type) {
        this.agentId = agentId;
        this.type = type;
        logger.info("Creating {} agent with ID: {}", type, agentId);
    }
    
    /**
     * Initialize the trading agent with required resources and configurations.
     * This method should be called before starting the agent.
     *
     * @return true if initialization was successful, false otherwise
     */
    public abstract boolean initialize();
    
    /**
     * Start the trading agent operations.
     * The agent must be initialized before it can be started.
     *
     * @return true if the agent was successfully started, false otherwise
     */
    public abstract boolean start();
    
    /**
     * Stop the trading agent operations.
     *
     * @return true if the agent was successfully stopped, false otherwise
     */
    public abstract boolean stop();
    
    /**
     * Perform a health check on the trading agent to determine its current status.
     *
     * @return the current health status of the agent
     */
    @Override
    public abstract HealthStatus checkHealth();
    
    /**
     * Get the unique identifier for this trading agent.
     *
     * @return the agent's ID
     */
    public String getAgentId() {
        return agentId;
    }
    
    /**
     * Get the type of this trading agent.
     *
     * @return the agent's type
     */
    public AgentType getType() {
        return type;
    }
    
    /**
     * Check if the agent has been initialized.
     *
     * @return true if the agent is initialized, false otherwise
     */
    public boolean isInitialized() {
        return initialized;
    }
    
    /**
     * Check if the agent is currently running.
     *
     * @return true if the agent is running, false otherwise
     */
    public boolean isRunning() {
        return running;
    }
    
    /**
     * Return the health check name for this agent.
     * 
     * @return the health check name
     */
    @Override
    public String getName() {
        return "TradingAgent-" + agentId;
    }
} 