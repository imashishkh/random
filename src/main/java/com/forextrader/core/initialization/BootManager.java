package com.forextrader.core.initialization;

import com.forextrader.core.config.ConfigurationManager;
import com.forextrader.core.error.ErrorAggregator;
import com.forextrader.core.initialization.exceptions.ServiceInitializationException;
import com.forextrader.core.health.HealthCheckRegistry;
import com.forextrader.core.metrics.MetricsCollector;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Manages the boot sequence of the application.
 * Coordinates the initialization of all services based on their dependencies.
 */
public class BootManager {
    private static final Logger logger = Logger.getLogger(BootManager.class.getName());
    
    private final ConfigurationManager configManager;
    private final ErrorAggregator errorAggregator;
    private final HealthCheckRegistry healthCheckRegistry;
    private final ServiceInitializerRegistry initializerRegistry;
    private final MetricsCollector metricsCollector;
    private final CommandLineArgumentProcessor argProcessor;
    
    private final Map<String, Object> initializedServices = new ConcurrentHashMap<>();
    private final List<ServiceInitializer<?>> failedInitializers = new ArrayList<>();
    
    /**
     * Creates a new boot manager.
     * 
     * @param configManager The configuration manager
     * @param errorAggregator The error aggregator
     * @param healthCheckRegistry The health check registry
     * @param metricsCollector The metrics collector
     * @param args Command-line arguments
     */
    public BootManager(
            ConfigurationManager configManager,
            ErrorAggregator errorAggregator,
            HealthCheckRegistry healthCheckRegistry,
            MetricsCollector metricsCollector,
            String[] args) {
        this.configManager = configManager;
        this.errorAggregator = errorAggregator;
        this.healthCheckRegistry = healthCheckRegistry;
        this.metricsCollector = metricsCollector;
        this.argProcessor = new CommandLineArgumentProcessor(args);
        this.initializerRegistry = new ServiceInitializerRegistry(configManager);
        
        registerInitializers();
    }
    
    /**
     * Registers all service initializers with the initializer registry.
     */
    private void registerInitializers() {
        // Core services
        initializerRegistry.register(new BinanceClientInitializer(
                configManager, errorAggregator, healthCheckRegistry, metricsCollector));
                
        // Orchestration services
        initializerRegistry.register(new OrchestratorInitializer(
                configManager, errorAggregator, healthCheckRegistry, metricsCollector));
        
        // Agent services - pass command line args processor
        initializerRegistry.register(new AgentInitializer(
                configManager, errorAggregator, healthCheckRegistry, metricsCollector, argProcessor));
        
        // Additional initializers would be registered here
    }
    
    /**
     * Boots the application by initializing all services in order of dependencies.
     * 
     * @return True if all services initialized successfully, false otherwise
     */
    public boolean boot() {
        logger.info("Starting application boot sequence");
        
        if (argProcessor.isHelpRequested()) {
            argProcessor.printUsage();
            return false;
        }
        
        long startTime = System.currentTimeMillis();
        
        try {
            initializeAllServices();
            
            long bootTime = System.currentTimeMillis() - startTime;
            logger.info("Application boot sequence completed successfully in " + bootTime + "ms");
            return true;
        } catch (ServiceInitializationException e) {
            long bootTime = System.currentTimeMillis() - startTime;
            logger.log(Level.SEVERE, "Application boot sequence failed after " + bootTime + "ms", e);
            
            // Log all failed initializers
            for (ServiceInitializer<?> initializer : failedInitializers) {
                logger.severe("Failed to initialize service: " + initializer.getServiceName());
            }
            
            return false;
        }
    }
    
    /**
     * Initializes all services in order of dependencies.
     * 
     * @throws ServiceInitializationException If any service initialization fails
     */
    private void initializeAllServices() throws ServiceInitializationException {
        // Get all initializers sorted by dependencies
        List<ServiceInitializer<?>> sortedInitializers = initializerRegistry.getSortedInitializers();
        
        // Initialize each service
        for (ServiceInitializer<?> initializer : sortedInitializers) {
            try {
                logger.info("Initializing service: " + initializer.getServiceName());
                
                // Initialize the service
                Object service = initializer.initialize();
                
                // Store the initialized service
                initializedServices.put(initializer.getServiceName(), service);
                
                logger.info("Service initialized successfully: " + initializer.getServiceName());
            } catch (ServiceInitializationException e) {
                failedInitializers.add(initializer);
                logger.log(Level.SEVERE, "Failed to initialize service: " + initializer.getServiceName(), e);
                throw e;
            }
        }
    }
    
    /**
     * Shuts down all initialized services in reverse order of initialization.
     */
    public void shutdown() {
        logger.info("Starting application shutdown sequence");
        
        long startTime = System.currentTimeMillis();
        
        // Get initializers in reverse order of dependencies
        List<ServiceInitializer<?>> reversedInitializers = initializerRegistry.getReversedInitializers();
        
        for (ServiceInitializer<?> initializer : reversedInitializers) {
            String serviceName = initializer.getServiceName();
            if (initializedServices.containsKey(serviceName)) {
                try {
                    logger.info("Shutting down service: " + serviceName);
                    initializer.shutdown();
                    logger.info("Service shut down successfully: " + serviceName);
                } catch (Exception e) {
                    logger.log(Level.SEVERE, "Error shutting down service: " + serviceName, e);
                }
            }
        }
        
        long shutdownTime = System.currentTimeMillis() - startTime;
        logger.info("Application shutdown sequence completed in " + shutdownTime + "ms");
    }
    
    /**
     * Gets an initialized service by name.
     * 
     * @param <T> The type of the service
     * @param serviceName The name of the service
     * @return The service instance, or null if not found
     */
    @SuppressWarnings("unchecked")
    public <T> T getService(String serviceName) {
        return (T) initializedServices.get(serviceName);
    }
    
    /**
     * Gets the command-line argument processor.
     * 
     * @return The command-line argument processor
     */
    public CommandLineArgumentProcessor getArgProcessor() {
        return argProcessor;
    }
} 