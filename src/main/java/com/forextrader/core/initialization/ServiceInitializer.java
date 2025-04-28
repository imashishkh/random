package com.forextrader.core.initialization;

import java.util.List;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Logger;

import com.forextrader.core.Component;
import com.forextrader.core.configuration.ConfigurationManager;
import com.forextrader.core.health.HealthCheckRegistry;
import com.forextrader.core.metrics.MetricsCollector;
import com.forextrader.core.service.Service;

/**
 * Base class for all service initializers in the system.
 * Implements the template method pattern for standardized service initialization.
 * 
 * @param <T> The type of service this initializer creates and manages
 */
public abstract class ServiceInitializer<T extends Service> implements Component {
    private static final Logger logger = Logger.getLogger(ServiceInitializer.class.getName());
    
    protected final ConfigurationManager configManager;
    protected final MetricsCollector metricsCollector;
    protected final HealthCheckRegistry healthCheckRegistry;
    protected final ErrorAggregator errorAggregator;
    
    // The service instance managed by this initializer
    protected final AtomicReference<T> serviceRef = new AtomicReference<>();
    
    // Lifecycle state tracking
    private volatile boolean initialized = false;
    private volatile boolean started = false;
    
    /**
     * Creates a new service initializer.
     * 
     * @param configManager Configuration manager for accessing configuration
     * @param metricsCollector Metrics collector for recording performance metrics
     * @param healthCheckRegistry Registry for health checks
     * @param errorAggregator Error aggregator for centralized error reporting
     */
    public ServiceInitializer(
            ConfigurationManager configManager,
            MetricsCollector metricsCollector,
            HealthCheckRegistry healthCheckRegistry,
            ErrorAggregator errorAggregator) {
        this.configManager = configManager;
        this.metricsCollector = metricsCollector;
        this.healthCheckRegistry = healthCheckRegistry;
        this.errorAggregator = errorAggregator;
    }
    
    /**
     * Returns the service instance managed by this initializer.
     * 
     * @return The service instance, or null if not yet initialized
     */
    public T getService() {
        return serviceRef.get();
    }
    
    /**
     * Returns the list of initializer classes this initializer depends on.
     * These will be initialized before this initializer during the startup sequence.
     * 
     * @return List of dependency initializer classes
     */
    public List<Class<? extends ServiceInitializer<?>>> dependencies() {
        // Default implementation returns no dependencies
        return Collections.emptyList();
    }
    
    // Component lifecycle methods - template pattern implementation
    
    @Override
    public final void init() {
        if (initialized) {
            logger.warning("Service already initialized: " + getServiceName());
            return;
        }
        
        logger.info("Initializing service: " + getServiceName());
        metricsCollector.startTimer(getServiceName() + ".initialization");
        
        try {
            // Validate configuration before proceeding
            validateConfiguration();
            
            // Create and configure the service instance
            T service = createServiceInstance();
            configureService(service);
            
            // Register health checks for the service
            registerHealthChecks(service);
            
            // Register shutdown hook
            setupShutdownHook(service);
            
            // Store the initialized service
            serviceRef.set(service);
            initialized = true;
            
            metricsCollector.stopTimer(getServiceName() + ".initialization");
            logger.info("Service initialized successfully: " + getServiceName());
        } catch (Exception e) {
            metricsCollector.recordInitializationFailure(getServiceName());
            errorAggregator.reportError(getServiceName(), "Initialization failed", e);
            throw new ServiceInitializationException(getServiceName(), e);
        }
    }
    
    @Override
    public final void start() {
        if (!initialized) {
            throw new IllegalStateException("Cannot start service before initialization: " + getServiceName());
        }
        
        if (started) {
            logger.warning("Service already started: " + getServiceName());
            return;
        }
        
        logger.info("Starting service: " + getServiceName());
        metricsCollector.startTimer(getServiceName() + ".startup");
        
        try {
            T service = serviceRef.get();
            startService(service);
            started = true;
            
            metricsCollector.stopTimer(getServiceName() + ".startup");
            logger.info("Service started successfully: " + getServiceName());
        } catch (Exception e) {
            metricsCollector.recordStartupFailure(getServiceName());
            errorAggregator.reportError(getServiceName(), "Startup failed", e);
            throw new ServiceStartupException(getServiceName(), e);
        }
    }
    
    @Override
    public final void stop() {
        if (!started) {
            logger.info("Service not started, nothing to stop: " + getServiceName());
            return;
        }
        
        logger.info("Stopping service: " + getServiceName());
        metricsCollector.startTimer(getServiceName() + ".shutdown");
        
        try {
            T service = serviceRef.get();
            stopService(service);
            started = false;
            
            metricsCollector.stopTimer(getServiceName() + ".shutdown");
            logger.info("Service stopped successfully: " + getServiceName());
        } catch (Exception e) {
            metricsCollector.recordShutdownFailure(getServiceName());
            errorAggregator.reportError(getServiceName(), "Shutdown failed", e);
            throw new ServiceShutdownException(getServiceName(), e);
        }
    }
    
    // Abstract methods to be implemented by concrete initializers
    
    /**
     * Creates a new instance of the service.
     * 
     * @return A new service instance
     */
    protected abstract T createServiceInstance();
    
    /**
     * Configures the service instance after creation.
     * 
     * @param service The service instance to configure
     */
    protected abstract void configureService(T service);
    
    /**
     * Starts the service.
     * 
     * @param service The service instance to start
     */
    protected abstract void startService(T service);
    
    /**
     * Stops the service.
     * 
     * @param service The service instance to stop
     */
    protected abstract void stopService(T service);
    
    /**
     * Returns the name of the service, used for logging and metrics.
     * 
     * @return The service name
     */
    protected abstract String getServiceName();
    
    /**
     * Validates the configuration for this service initializer.
     * Implementations should throw a ConfigurationException if validation fails.
     */
    protected abstract void validateConfiguration();
    
    /**
     * Registers health checks for the service.
     * 
     * @param service The service instance to register health checks for
     */
    protected abstract void registerHealthChecks(T service);
    
    /**
     * Sets up a shutdown hook for the service.
     * Default implementation does nothing.
     * 
     * @param service The service instance to set up a shutdown hook for
     */
    protected void setupShutdownHook(T service) {
        // Default implementation does nothing
    }
} 