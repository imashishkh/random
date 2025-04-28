package com.forextrader.core.agent;

import com.forextrader.core.model.HealthStatus;

/**
 * Interface defining the contract for trading agents.
 * Trading agents are responsible for executing trading strategies
 * and managing trading decisions.
 */
public interface TradingAgent {
    
    /**
     * Gets the unique identifier for this agent.
     *
     * @return The agent's unique identifier
     */
    String getId();
    
    /**
     * Gets the type of this agent.
     *
     * @return The agent's type
     */
    AgentType getType();
    
    /**
     * Initializes the agent with necessary resources and configurations.
     */
    void initialize();
    
    /**
     * Starts the agent's operations.
     */
    void start();
    
    /**
     * Stops the agent's operations gracefully.
     */
    void stop();
    
    /**
     * Checks if the agent is currently running.
     *
     * @return true if the agent is running, false otherwise
     */
    boolean isRunning();
    
    /**
     * Performs a health check on the agent.
     *
     * @return The current health status of the agent
     */
    HealthStatus checkHealth();
    
    /**
     * Enum representing the different types of trading agents.
     */
    enum AgentType {
        STANDARD,
        ADVANCED,
        EXPERIMENTAL
    }
} 