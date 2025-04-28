package com.forextrader.core.agent;

/**
 * Enum representing the different types of trading agents in the system.
 */
public enum AgentType {
    /**
     * Standard trading agent with basic functionality.
     */
    STANDARD,
    
    /**
     * Advanced trading agent with additional features and strategies.
     */
    ADVANCED,
    
    /**
     * Research agent focused on market analysis and pattern detection.
     */
    RESEARCH,
    
    /**
     * Arbitrage agent designed to exploit price differences across markets.
     */
    ARBITRAGE,
    
    /**
     * High-frequency trading agent optimized for rapid trading.
     */
    HFT,
    
    /**
     * Risk management agent that monitors and manages portfolio risk.
     */
    RISK_MANAGEMENT,
    
    /**
     * Custom agent type for specialized implementations.
     */
    CUSTOM
} 