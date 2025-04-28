package com.forextrader.core.initialization;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.logging.Logger;

import com.forextrader.core.configuration.ConfigurationError;
import com.forextrader.core.configuration.ConfigurationException;
import com.forextrader.core.configuration.ConfigurationManager;
import com.forextrader.core.health.AbstractHealthCheck;
import com.forextrader.core.health.HealthCheckRegistry;
import com.forextrader.core.health.HealthStatus;
import com.forextrader.core.metrics.MetricsCollector;
import com.forextrader.core.service.agent.AgentManager;
import com.forextrader.core.service.agent.AgentManagerConfig;
import com.forextrader.core.service.agent.AgentManagerImpl;
import com.forextrader.core.service.orchestration.Orchestrator;
import com.forextrader.core.agent.TradingAgent;
import com.forextrader.core.agent.AgentFactory;
import com.forextrader.core.agent.AgentHealthCheck;
import com.forextrader.core.agent.impl.StandardAgentFactory;
import com.forextrader.core.config.ConfigurationManager;
import com.forextrader.core.error.ErrorAggregator;
import com.forextrader.core.initialization.exceptions.ServiceInitializationException;
import com.forextrader.core.orchestration.Orchestrator;

/**
 * Initializer for the Agent Manager service.
 * Handles the creation and management of trading agents with support for
 * dynamically adjusting the number of agents based on configuration.
 */
public class AgentInitializer extends ServiceInitializer<List<TradingAgent>> {
    private static final Logger logger = Logger.getLogger(AgentInitializer.class.getName());
    
    // Configuration parameter names
    private static final String AGENT_COUNT_PARAM = "agent.count";
    private static final String MAX_AGENTS_PARAM = "agent.max";
    private static final String MIN_AGENTS_PARAM = "agent.min";
    private static final String AUTO_SCALE_ENABLED_PARAM = "agent.autoScale.enabled";
    private static final String SCALE_THRESHOLD_PARAM = "agent.autoScale.thresholdPercent";
    private static final String AGENT_CHECK_INTERVAL_MS_PARAM = "agent.health.checkIntervalMs";
    
    private final CommandLineArgumentProcessor argProcessor;
    
    private List<TradingAgent> tradingAgents;
    private AgentFactory agentFactory;
    
    /**
     * Creates a new Agent initializer.
     * 
     * @param configManager Configuration manager for accessing configuration
     * @param metricsCollector Metrics collector for recording performance metrics
     * @param healthCheckRegistry Registry for health checks
     * @param errorAggregator Error aggregator for centralized error reporting
     * @param argProcessor Command line argument processor for dynamic agent count
     */
    public AgentInitializer(
            ConfigurationManager configManager,
            MetricsCollector metricsCollector,
            HealthCheckRegistry healthCheckRegistry,
            ErrorAggregator errorAggregator,
            CommandLineArgumentProcessor argProcessor) {
        super(configManager, metricsCollector, healthCheckRegistry, errorAggregator);
        this.argProcessor = argProcessor;
    }
    
    @Override
    public String getServiceName() {
        return "TradingAgentService";
    }
    
    @Override
    public String[] getDependencies() {
        // Agents depend on both the exchange client and the orchestrator
        return new String[]{"BinanceClientService", "OrchestratorService"};
    }
    
    @Override
    protected void validatePrerequisites() throws ServiceInitializationException {
        try {
            // Validate agent configuration
            int maxAgentCount = configManager.getInt(MAX_AGENTS_PARAM, 10);
            int requestedAgentCount = determineAgentCount();
            
            if (requestedAgentCount > maxAgentCount) {
                logger.warning(String.format(
                        "Requested agent count (%d) exceeds maximum allowed (%d). Using maximum instead.",
                        requestedAgentCount, maxAgentCount));
            }
            
            // Check that agent types are properly configured
            String[] agentTypes = configManager.getStringArray("agent.types.types", new String[]{"standard"});
            if (agentTypes.length == 0) {
                throw new ServiceInitializationException("No agent types configured");
            }
            
            logger.info("Trading agent prerequisites validated successfully");
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Failed to validate trading agent prerequisites", e);
            throw new ServiceInitializationException("Failed to validate trading agent prerequisites", e);
        }
    }
    
    /**
     * Determines the agent count from command line args or configuration.
     * Command line args take precedence over configuration.
     * 
     * @return The agent count to use
     */
    private int determineAgentCount() {
        // Check if agent count is specified in command line args
        Integer cmdLineAgentCount = argProcessor.getAgentCount();
        if (cmdLineAgentCount != null) {
            logger.info("Using agent count from command line: " + cmdLineAgentCount);
            return cmdLineAgentCount;
        }
        
        // Fall back to configuration
        int configAgentCount = configManager.getInt(AGENT_COUNT_PARAM, 5);
        logger.info("Using agent count from configuration: " + configAgentCount);
        return configAgentCount;
    }
    
    @Override
    protected List<TradingAgent> createService() throws ServiceInitializationException {
        try {
            // Create agent factory
            agentFactory = new StandardAgentFactory(configManager, errorAggregator, metricsCollector);
            
            // Determine how many agents to create
            int agentCount = Math.min(
                    determineAgentCount(),
                    configManager.getInt(MAX_AGENTS_PARAM, 10)
            );
            
            logger.info("Creating " + agentCount + " trading agents");
            
            // Get the orchestrator service
            Orchestrator orchestrator = (Orchestrator) registry.getInitializedService("OrchestratorService");
            if (orchestrator == null) {
                throw new ServiceInitializationException("Orchestrator service not found or not initialized");
            }
            
            // Create the agents
            tradingAgents = new ArrayList<>(agentCount);
            for (int i = 0; i < agentCount; i++) {
                String agentId = "Agent-" + (i + 1);
                TradingAgent agent = agentFactory.createAgent(agentId, orchestrator);
                tradingAgents.add(agent);
                logger.info("Created trading agent: " + agentId);
            }
            
            return tradingAgents;
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Failed to create trading agents", e);
            throw new ServiceInitializationException("Failed to create trading agents", e);
        }
    }
    
    @Override
    protected void registerHealthCheck() {
        if (tradingAgents != null && !tradingAgents.isEmpty()) {
            for (TradingAgent agent : tradingAgents) {
                healthCheckRegistry.register(
                        new AgentHealthCheck(agent, "AgentHealthCheck-" + agent.getAgentId())
                );
            }
            logger.info("Trading agent health checks registered successfully");
        }
    }
    
    @Override
    protected void startService() throws ServiceInitializationException {
        if (tradingAgents == null || tradingAgents.isEmpty()) {
            throw new ServiceInitializationException("No trading agents created");
        }
        
        try {
            // Start each agent
            for (TradingAgent agent : tradingAgents) {
                agent.start();
                logger.info("Started trading agent: " + agent.getAgentId());
            }
            
            logger.info("All trading agents started successfully");
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Failed to start trading agents", e);
            throw new ServiceInitializationException("Failed to start trading agents", e);
        }
    }
    
    @Override
    public void shutdown() {
        if (tradingAgents != null) {
            logger.info("Shutting down trading agents...");
            for (TradingAgent agent : tradingAgents) {
                try {
                    agent.stop();
                    logger.info("Stopped trading agent: " + agent.getAgentId());
                } catch (Exception e) {
                    logger.log(Level.WARNING, "Error stopping trading agent: " + agent.getAgentId(), e);
                    errorAggregator.addError("Error stopping trading agent: " + agent.getAgentId(), e);
                }
            }
        }
    }
    
    @Override
    protected void configureService(List<TradingAgent> service) {
        logger.info("Configuring Trading Agent Service");
        
        // Inject dependencies from other services
        ServiceInitializerRegistry registry = new ServiceInitializerRegistry(); // This should be injected
        
        // Get the Orchestrator from its initializer
        OrchestratorInitializer orchestratorInitializer = 
            (OrchestratorInitializer) registry.getInitializer(OrchestratorInitializer.class);
        Orchestrator orchestrator = orchestratorInitializer.getService();
        
        // Register the orchestrator with the agent manager
        for (TradingAgent agent : service) {
            agent.setOrchestrator(orchestrator);
        }
        
        // Configure agent types and allocations
        configureAgentTypes(service);
        
        // Configure agent behavior parameters
        configureAgentBehavior(service);
    }
    
    /**
     * Configures the agent types and allocations.
     * 
     * @param service The agent manager service
     */
    private void configureAgentTypes(List<TradingAgent> service) {
        // Check if specific agent types are enabled in config
        boolean enableMomentumAgents = configManager.getBoolean("agent.types.momentum.enabled", true);
        if (enableMomentumAgents) {
            int momentumAgentCount = configManager.getInt("agent.types.momentum.count", 2);
            for (int i = 0; i < momentumAgentCount; i++) {
                TradingAgent agent = new TradingAgent("momentum", configManager.getSubConfiguration("agent.types.momentum"));
                service.add(agent);
            }
        }
        
        boolean enableMeanReversionAgents = configManager.getBoolean("agent.types.meanReversion.enabled", true);
        if (enableMeanReversionAgents) {
            int meanReversionAgentCount = configManager.getInt("agent.types.meanReversion.count", 2);
            for (int i = 0; i < meanReversionAgentCount; i++) {
                TradingAgent agent = new TradingAgent("meanReversion", configManager.getSubConfiguration("agent.types.meanReversion"));
                service.add(agent);
            }
        }
        
        boolean enableArbitrageAgents = configManager.getBoolean("agent.types.arbitrage.enabled", false);
        if (enableArbitrageAgents) {
            int arbitrageAgentCount = configManager.getInt("agent.types.arbitrage.count", 1);
            for (int i = 0; i < arbitrageAgentCount; i++) {
                TradingAgent agent = new TradingAgent("arbitrage", configManager.getSubConfiguration("agent.types.arbitrage"));
                service.add(agent);
            }
        }
    }
    
    /**
     * Configures agent behavior parameters.
     * 
     * @param service The agent manager service
     */
    private void configureAgentBehavior(List<TradingAgent> service) {
        // Configure risk management for agents
        double maxPositionSizePercent = configManager.getDouble("agent.riskManagement.maxPositionSizePercent", 5.0);
        for (TradingAgent agent : service) {
            agent.setMaxPositionSizePercent(maxPositionSizePercent);
        }
        
        double stopLossPercent = configManager.getDouble("agent.riskManagement.stopLossPercent", 2.0);
        for (TradingAgent agent : service) {
            agent.setDefaultStopLossPercent(stopLossPercent);
        }
        
        double takeProfitPercent = configManager.getDouble("agent.riskManagement.takeProfitPercent", 3.0);
        for (TradingAgent agent : service) {
            agent.setDefaultTakeProfitPercent(takeProfitPercent);
        }
        
        // Configure auto-scaling behavior
        if (configManager.getBoolean(AUTO_SCALE_ENABLED_PARAM, true)) {
            for (TradingAgent agent : service) {
                agent.enableAutoScaling(
                    configManager.getDouble("agent.autoScale.cpuThresholdPercent", 70.0),
                    configManager.getDouble("agent.autoScale.memoryThresholdPercent", 80.0)
                );
            }
        }
    }
    
    @Override
    protected void validateConfiguration() {
        logger.info("Validating Trading Agent Service configuration");
        
        List<ConfigurationError> errors = new ArrayList<>();
        
        // Validate agent count
        int agentCount = tradingAgents.size();
        if (agentCount <= 0) {
            errors.add(new ConfigurationError(AGENT_COUNT_PARAM, 
                    "Agent count must be positive", agentCount));
        }
        
        // Validate min/max agent settings
        int minAgents = configManager.getInt(MIN_AGENTS_PARAM, 1);
        if (minAgents <= 0) {
            errors.add(new ConfigurationError(MIN_AGENTS_PARAM, 
                    "Minimum agent count must be positive", minAgents));
        }
        
        int maxAgents = configManager.getInt(MAX_AGENTS_PARAM, 100);
        if (maxAgents < minAgents) {
            errors.add(new ConfigurationError(MAX_AGENTS_PARAM, 
                    "Maximum agent count must be greater than or equal to minimum agent count", 
                    maxAgents));
        }
        
        // Validate if agent count is within min/max range
        if (agentCount < minAgents || agentCount > maxAgents) {
            errors.add(new ConfigurationError(AGENT_COUNT_PARAM, 
                    "Agent count must be between " + minAgents + " and " + maxAgents, 
                    agentCount));
        }
        
        // Validate scale threshold
        double scaleThreshold = configManager.getDouble(SCALE_THRESHOLD_PARAM, 70.0);
        if (scaleThreshold <= 0 || scaleThreshold > 100) {
            errors.add(new ConfigurationError(SCALE_THRESHOLD_PARAM, 
                    "Scale threshold must be between 0 and 100", scaleThreshold));
        }
        
        // Validate agent check interval
        long agentCheckIntervalMs = configManager.getLong(AGENT_CHECK_INTERVAL_MS_PARAM, 30000);
        if (agentCheckIntervalMs <= 0) {
            errors.add(new ConfigurationError(AGENT_CHECK_INTERVAL_MS_PARAM, 
                    "Agent check interval must be positive", agentCheckIntervalMs));
        }
        
        // Throw exception if there are validation errors
        if (!errors.isEmpty()) {
            throw new ConfigurationException(getServiceName(), errors);
        }
    }
    
    @Override
    public List<Class<? extends ServiceInitializer<?>>> dependencies() {
        // Trading Agent Service depends on Orchestrator for coordination
        return Arrays.asList(OrchestratorInitializer.class);
    }
    
    @Override
    protected void setupShutdownHook(List<TradingAgent> service) {
        logger.info("Setting up shutdown hook for Trading Agent Service");
        
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            logger.info("Shutdown hook called, stopping Trading Agent Service");
            try {
                shutdown();
            } catch (Exception e) {
                logger.warning("Error during Trading Agent Service shutdown: " + e.getMessage());
            }
        }));
    }
    
    /**
     * Health check for agent count maintenance.
     */
    private static class AgentCountHealthCheck extends AbstractHealthCheck {
        private final List<TradingAgent> tradingAgents;
        
        public AgentCountHealthCheck(List<TradingAgent> tradingAgents) {
            super("TradingAgentService", "agent-count");
            this.tradingAgents = tradingAgents;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            int targetAgentCount = tradingAgents.size();
            int currentAgentCount = tradingAgents.size();
            
            if (targetAgentCount == 0) {
                return HealthStatus.unhealthy("No agents are configured");
            }
            
            if (currentAgentCount == targetAgentCount) {
                return HealthStatus.healthy("Agent count matches target: " + currentAgentCount);
            } else {
                double countRatio = (double) currentAgentCount / targetAgentCount;
                
                if (countRatio >= 0.8) {
                    return HealthStatus.healthy("Current agent count (" + currentAgentCount + 
                            ") is close to target (" + targetAgentCount + "), scaling in progress");
                } else {
                    return HealthStatus.unhealthy("Agent count mismatch: current=" + currentAgentCount + 
                            ", target=" + targetAgentCount);
                }
            }
        }
    }
    
    /**
     * Health check for agent performance.
     */
    private static class AgentPerformanceHealthCheck extends AbstractHealthCheck {
        private final List<TradingAgent> tradingAgents;
        
        public AgentPerformanceHealthCheck(List<TradingAgent> tradingAgents) {
            super("TradingAgentService", "agent-performance");
            this.tradingAgents = tradingAgents;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            int failedAgents = 0;
            int totalAgents = tradingAgents.size();
            
            if (totalAgents == 0) {
                return HealthStatus.unhealthy("No agents are running");
            }
            
            for (TradingAgent agent : tradingAgents) {
                if (!agent.isRunning()) {
                    failedAgents++;
                }
            }
            
            if (failedAgents == 0) {
                return HealthStatus.healthy("All agents are performing normally");
            } else {
                double failureRate = (double) failedAgents / totalAgents;
                
                if (failureRate < 0.2) {
                    return HealthStatus.healthy(failedAgents + " of " + totalAgents + 
                            " agents have performance issues, monitoring situation");
                } else {
                    return HealthStatus.unhealthy(failedAgents + " of " + totalAgents + 
                            " agents have performance issues (" + (failureRate * 100) + "%)");
                }
            }
        }
    }
    
    /**
     * Health check for agent resource usage.
     */
    private static class AgentResourceHealthCheck extends AbstractHealthCheck {
        private final List<TradingAgent> tradingAgents;
        
        public AgentResourceHealthCheck(List<TradingAgent> tradingAgents) {
            super("TradingAgentService", "agent-resources");
            this.tradingAgents = tradingAgents;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            double cpuUsagePercent = 0;
            double memoryUsagePercent = 0;
            
            for (TradingAgent agent : tradingAgents) {
                cpuUsagePercent += agent.getCpuUsagePercent();
                memoryUsagePercent += agent.getMemoryUsagePercent();
            }
            
            cpuUsagePercent /= tradingAgents.size();
            memoryUsagePercent /= tradingAgents.size();
            
            if (cpuUsagePercent > 90 || memoryUsagePercent > 90) {
                return HealthStatus.unhealthy("Resource usage too high: CPU=" + 
                        cpuUsagePercent + "%, Memory=" + memoryUsagePercent + "%");
            } else if (cpuUsagePercent > 75 || memoryUsagePercent > 80) {
                return HealthStatus.unhealthy("Resource usage high: CPU=" + 
                        cpuUsagePercent + "%, Memory=" + memoryUsagePercent + 
                        "%, potential scaling needed");
            } else {
                return HealthStatus.healthy("Resource usage normal: CPU=" + 
                        cpuUsagePercent + "%, Memory=" + memoryUsagePercent + "%");
            }
        }
    }
} 