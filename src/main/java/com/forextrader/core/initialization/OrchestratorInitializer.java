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
import com.forextrader.core.service.orchestration.Orchestrator;
import com.forextrader.core.service.orchestration.OrchestratorConfig;
import com.forextrader.core.service.orchestration.OrchestratorImpl;
import com.forextrader.core.service.binance.BinanceClient;
import com.forextrader.core.error.ErrorAggregator;
import com.forextrader.core.initialization.exceptions.ServiceInitializationException;
import com.forextrader.core.orchestration.OrchestratorHealthCheck;
import com.forextrader.core.orchestration.TradingStrategy;
import com.forextrader.core.orchestration.impl.DefaultOrchestrator;
import com.forextrader.core.orchestration.impl.SimpleScalpingStrategy;

/**
 * Initializes the trading orchestration service.
 * Responsible for creating and configuring the orchestration layer that coordinates
 * trading activities between exchange services and trading agents.
 */
public class OrchestratorInitializer extends ServiceInitializer<Orchestrator> {
    private static final Logger logger = Logger.getLogger(OrchestratorInitializer.class.getName());
    private static final String SERVICE_NAME = "OrchestratorService";
    
    // Configuration parameter names
    private static final String MAX_CONCURRENT_STRATEGIES_PARAM = "orchestrator.maxConcurrentStrategies";
    private static final String EXECUTION_INTERVAL_MS_PARAM = "orchestrator.executionIntervalMs";
    private static final String RISK_CHECK_ENABLED_PARAM = "orchestrator.riskCheck.enabled";
    private static final String EMERGENCY_STOP_THRESHOLD_PARAM = "orchestrator.emergencyStop.thresholdPercent";
    private static final String DATA_SYNC_INTERVAL_MS_PARAM = "orchestrator.dataSync.intervalMs";
    
    private Orchestrator orchestrator;
    
    /**
     * Creates a new orchestrator initializer.
     *
     * @param configManager The configuration manager
     * @param errorAggregator The error aggregator
     * @param healthCheckRegistry The health check registry
     * @param metricsCollector The metrics collector
     */
    public OrchestratorInitializer(
            ConfigurationManager configManager,
            ErrorAggregator errorAggregator,
            HealthCheckRegistry healthCheckRegistry,
            MetricsCollector metricsCollector) {
        super(configManager, errorAggregator, healthCheckRegistry, metricsCollector);
    }
    
    @Override
    public String getServiceName() {
        return SERVICE_NAME;
    }
    
    @Override
    public String[] getDependencies() {
        // Orchestrator depends on exchange clients but can be initialized
        // before agents are created
        return new String[]{"BinanceClientService"};
    }
    
    @Override
    protected void validatePrerequisites() throws ServiceInitializationException {
        // Ensure we have the required configuration settings
        try {
            String strategyType = configManager.getString("trading.strategy.type", "simple-scalping");
            validateStrategyType(strategyType);
            
            logger.info("Orchestrator prerequisites validated successfully");
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Failed to validate orchestrator prerequisites", e);
            throw new ServiceInitializationException("Failed to validate orchestrator prerequisites", e);
        }
    }
    
    /**
     * Validates the strategy type from the configuration.
     *
     * @param strategyType The strategy type
     * @throws ServiceInitializationException If the strategy type is invalid
     */
    private void validateStrategyType(String strategyType) throws ServiceInitializationException {
        // Add more strategy types as they are implemented
        switch (strategyType) {
            case "simple-scalping":
                // Valid strategy
                break;
            default:
                throw new ServiceInitializationException("Unsupported trading strategy type: " + strategyType);
        }
    }
    
    @Override
    protected Orchestrator createService() throws ServiceInitializationException {
        try {
            // Create the trading strategy based on configuration
            TradingStrategy strategy = createTradingStrategy();
            
            // Create and configure the orchestrator
            orchestrator = new DefaultOrchestrator(
                    configManager,
                    errorAggregator,
                    metricsCollector,
                    strategy
            );
            
            logger.info("Orchestrator service created successfully");
            return orchestrator;
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Failed to create orchestrator service", e);
            throw new ServiceInitializationException("Failed to create orchestrator service", e);
        }
    }
    
    /**
     * Creates a trading strategy based on the configuration.
     *
     * @return The created trading strategy
     * @throws ServiceInitializationException If the strategy creation fails
     */
    private TradingStrategy createTradingStrategy() throws ServiceInitializationException {
        String strategyType = configManager.getString("trading.strategy.type", "simple-scalping");
        
        switch (strategyType) {
            case "simple-scalping":
                // Get strategy-specific configuration
                double takeProfitPct = configManager.getDouble("trading.strategy.scalping.takeProfit", 0.5);
                double stopLossPct = configManager.getDouble("trading.strategy.scalping.stopLoss", 0.3);
                int positionSizePercent = configManager.getInt("trading.strategy.scalping.positionSizePercent", 5);
                
                return new SimpleScalpingStrategy(takeProfitPct, stopLossPct, positionSizePercent);
            default:
                throw new ServiceInitializationException("Unsupported trading strategy type: " + strategyType);
        }
    }
    
    @Override
    protected void registerHealthCheck() {
        if (orchestrator != null) {
            healthCheckRegistry.register(
                    new OrchestratorHealthCheck(orchestrator, "OrchestratorHealthCheck")
            );
            logger.info("Orchestrator health check registered successfully");
        }
    }
    
    @Override
    protected void startService() throws ServiceInitializationException {
        try {
            if (orchestrator != null) {
                orchestrator.start();
                logger.info("Orchestrator service started successfully");
            } else {
                throw new ServiceInitializationException("Cannot start orchestrator - service not created");
            }
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Failed to start orchestrator service", e);
            throw new ServiceInitializationException("Failed to start orchestrator service", e);
        }
    }
    
    @Override
    public void shutdown() {
        try {
            if (orchestrator != null) {
                orchestrator.stop();
                logger.info("Orchestrator service stopped successfully");
            }
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Error shutting down orchestrator service", e);
            errorAggregator.addError("Error shutting down orchestrator service", e);
        }
    }
    
    @Override
    protected void configureService(Orchestrator service) {
        logger.info("Configuring Orchestrator");
        
        // Inject dependencies from other services
        ServiceInitializerRegistry registry = new ServiceInitializerRegistry(); // This should be injected
        
        // Get the BinanceClient from its initializer
        BinanceClientInitializer binanceInitializer = 
            (BinanceClientInitializer) registry.getInitializer(BinanceClientInitializer.class);
        BinanceClient binanceClient = binanceInitializer.getService();
        
        // Register data sources with the orchestrator
        service.registerDataSource(binanceClient);
        
        // Configure trading pairs
        List<String> tradingPairs = configManager.getStringList(
            "orchestrator.tradingPairs", 
            Arrays.asList("BTCUSDT", "ETHUSDT")
        );
        service.setTradingPairs(tradingPairs);
        
        // Configure strategy parameters
        boolean enableMomentumStrategy = configManager.getBoolean("orchestrator.strategies.momentum.enabled", true);
        if (enableMomentumStrategy) {
            service.enableStrategy("momentum", configManager.getSubConfiguration("orchestrator.strategies.momentum"));
        }
        
        boolean enableMeanReversionStrategy = configManager.getBoolean("orchestrator.strategies.meanReversion.enabled", false);
        if (enableMeanReversionStrategy) {
            service.enableStrategy("meanReversion", configManager.getSubConfiguration("orchestrator.strategies.meanReversion"));
        }
        
        // Set emergency stop callback
        service.setEmergencyStopCallback(() -> {
            logger.severe("Emergency stop triggered, notifying administrators");
            // Notification logic would go here
        });
    }
    
    @Override
    protected void startService(Orchestrator service) {
        logger.info("Starting Orchestrator");
        service.start();
    }
    
    @Override
    protected void stopService(Orchestrator service) {
        logger.info("Stopping Orchestrator");
        service.stop();
    }
    
    @Override
    protected void registerHealthChecks(Orchestrator service) {
        logger.info("Registering Orchestrator health checks");
        
        // Register orchestration cycle health check
        healthCheckRegistry.register(new OrchestratorCycleHealthCheck(service));
        
        // Register strategy execution health check
        healthCheckRegistry.register(new StrategyExecutionHealthCheck(service));
        
        // Register data synchronization health check
        healthCheckRegistry.register(new DataSyncHealthCheck(service));
    }
    
    @Override
    protected void validateConfiguration() {
        logger.info("Validating Orchestrator configuration");
        
        List<ConfigurationError> errors = new ArrayList<>();
        
        // Validate numeric parameters
        int maxConcurrentStrategies = configManager.getInt(MAX_CONCURRENT_STRATEGIES_PARAM, 10);
        if (maxConcurrentStrategies <= 0) {
            errors.add(new ConfigurationError(MAX_CONCURRENT_STRATEGIES_PARAM, 
                    "Max concurrent strategies must be positive", maxConcurrentStrategies));
        }
        
        long executionIntervalMs = configManager.getLong(EXECUTION_INTERVAL_MS_PARAM, 1000);
        if (executionIntervalMs <= 0) {
            errors.add(new ConfigurationError(EXECUTION_INTERVAL_MS_PARAM, 
                    "Execution interval must be positive", executionIntervalMs));
        }
        
        double emergencyStopThreshold = configManager.getDouble(EMERGENCY_STOP_THRESHOLD_PARAM, 5.0);
        if (emergencyStopThreshold <= 0 || emergencyStopThreshold > 100) {
            errors.add(new ConfigurationError(EMERGENCY_STOP_THRESHOLD_PARAM, 
                    "Emergency stop threshold must be between 0 and 100", emergencyStopThreshold));
        }
        
        long dataSyncIntervalMs = configManager.getLong(DATA_SYNC_INTERVAL_MS_PARAM, 5000);
        if (dataSyncIntervalMs <= 0) {
            errors.add(new ConfigurationError(DATA_SYNC_INTERVAL_MS_PARAM, 
                    "Data sync interval must be positive", dataSyncIntervalMs));
        }
        
        // Validate trading pairs configuration
        List<String> tradingPairs = configManager.getStringList("orchestrator.tradingPairs", null);
        if (tradingPairs == null || tradingPairs.isEmpty()) {
            errors.add(new ConfigurationError("orchestrator.tradingPairs", 
                    "At least one trading pair must be configured"));
        }
        
        // Throw exception if there are validation errors
        if (!errors.isEmpty()) {
            throw new ConfigurationException(getServiceName(), errors);
        }
    }
    
    @Override
    protected void setupShutdownHook(Orchestrator service) {
        logger.info("Setting up shutdown hook for Orchestrator");
        
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            logger.info("Shutdown hook called, stopping Orchestrator");
            try {
                service.stop();
            } catch (Exception e) {
                logger.warning("Error during Orchestrator shutdown: " + e.getMessage());
            }
        }));
    }
    
    /**
     * Health check for Orchestrator execution cycle.
     */
    private static class OrchestratorCycleHealthCheck extends AbstractHealthCheck {
        private final Orchestrator orchestrator;
        
        public OrchestratorCycleHealthCheck(Orchestrator orchestrator) {
            super("Orchestrator", "orchestrator-cycle");
            this.orchestrator = orchestrator;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            long lastCycleTimeMs = orchestrator.getLastCycleTimeMs();
            
            if (lastCycleTimeMs <= 0) {
                return HealthStatus.unhealthy("Orchestrator has not completed any execution cycles");
            }
            
            long targetCycleTimeMs = orchestrator.getTargetCycleTimeMs();
            double cycleTimeRatio = (double) lastCycleTimeMs / targetCycleTimeMs;
            
            if (cycleTimeRatio <= 1.5) {
                return HealthStatus.healthy("Orchestrator cycle time: " + lastCycleTimeMs + 
                        "ms (target: " + targetCycleTimeMs + "ms)");
            } else {
                return HealthStatus.unhealthy("Orchestrator cycle time too high: " + lastCycleTimeMs + 
                        "ms (target: " + targetCycleTimeMs + "ms)");
            }
        }
    }
    
    /**
     * Health check for strategy execution.
     */
    private static class StrategyExecutionHealthCheck extends AbstractHealthCheck {
        private final Orchestrator orchestrator;
        
        public StrategyExecutionHealthCheck(Orchestrator orchestrator) {
            super("Orchestrator", "strategy-execution");
            this.orchestrator = orchestrator;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            int failedStrategies = orchestrator.getFailedStrategyCount();
            int totalStrategies = orchestrator.getTotalStrategyCount();
            
            if (totalStrategies == 0) {
                return HealthStatus.unknown("No strategies are configured");
            }
            
            if (failedStrategies == 0) {
                return HealthStatus.healthy("All strategies executing normally");
            } else {
                double failureRate = (double) failedStrategies / totalStrategies;
                
                if (failureRate < 0.25) {
                    return HealthStatus.healthy(failedStrategies + " of " + totalStrategies + 
                            " strategies have execution errors, monitoring situation");
                } else {
                    return HealthStatus.unhealthy(failedStrategies + " of " + totalStrategies + 
                            " strategies have execution errors (" + (failureRate * 100) + "%)");
                }
            }
        }
    }
    
    /**
     * Health check for data synchronization.
     */
    private static class DataSyncHealthCheck extends AbstractHealthCheck {
        private final Orchestrator orchestrator;
        
        public DataSyncHealthCheck(Orchestrator orchestrator) {
            super("Orchestrator", "data-sync");
            this.orchestrator = orchestrator;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            long lastSyncTimeMs = orchestrator.getLastDataSyncTimeMs();
            long now = System.currentTimeMillis();
            long timeSinceLastSyncMs = now - lastSyncTimeMs;
            
            long expectedSyncIntervalMs = orchestrator.getDataSyncIntervalMs();
            double syncRatio = (double) timeSinceLastSyncMs / expectedSyncIntervalMs;
            
            if (lastSyncTimeMs <= 0) {
                return HealthStatus.unhealthy("Data synchronization has not occurred yet");
            }
            
            if (syncRatio <= 2.0) {
                return HealthStatus.healthy("Last data sync: " + (timeSinceLastSyncMs / 1000) + 
                        " seconds ago (expected every " + (expectedSyncIntervalMs / 1000) + " seconds)");
            } else {
                return HealthStatus.unhealthy("Data sync delay: " + (timeSinceLastSyncMs / 1000) + 
                        " seconds since last sync (expected every " + (expectedSyncIntervalMs / 1000) + " seconds)");
            }
        }
    }
} 