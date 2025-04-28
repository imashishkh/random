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
import com.forextrader.core.service.binance.BinanceClient;
import com.forextrader.core.service.binance.BinanceClientConfig;
import com.forextrader.core.service.binance.BinanceClientImpl;

/**
 * Initializer for the Binance client service.
 * Handles creation, configuration, and health check registration for the Binance client.
 */
public class BinanceClientInitializer extends ServiceInitializer<BinanceClient> {
    private static final Logger logger = Logger.getLogger(BinanceClientInitializer.class.getName());
    
    // Configuration parameter names
    private static final String API_KEY_PARAM = "binance.api.key";
    private static final String API_SECRET_PARAM = "binance.api.secret";
    private static final String API_BASE_URL_PARAM = "binance.api.baseUrl";
    private static final String RATE_LIMIT_PARAM = "binance.api.rateLimit.requestsPerMinute";
    private static final String RETRY_COUNT_PARAM = "binance.api.retry.count";
    private static final String CONNECT_TIMEOUT_PARAM = "binance.api.connectTimeoutMs";
    private static final String READ_TIMEOUT_PARAM = "binance.api.readTimeoutMs";
    
    /**
     * Creates a new Binance client initializer.
     * 
     * @param configManager Configuration manager for accessing configuration
     * @param metricsCollector Metrics collector for recording performance metrics
     * @param healthCheckRegistry Registry for health checks
     * @param errorAggregator Error aggregator for centralized error reporting
     */
    public BinanceClientInitializer(
            ConfigurationManager configManager,
            MetricsCollector metricsCollector,
            HealthCheckRegistry healthCheckRegistry,
            ErrorAggregator errorAggregator) {
        super(configManager, metricsCollector, healthCheckRegistry, errorAggregator);
    }
    
    @Override
    protected BinanceClient createServiceInstance() {
        logger.info("Creating Binance client instance");
        
        // Build client configuration from config parameters
        BinanceClientConfig config = new BinanceClientConfig.Builder()
            .withApiKey(configManager.getString(API_KEY_PARAM))
            .withApiSecret(configManager.getString(API_SECRET_PARAM))
            .withBaseUrl(configManager.getString(API_BASE_URL_PARAM, "https://api.binance.com"))
            .withRateLimit(configManager.getInt(RATE_LIMIT_PARAM, 1200))
            .withRetryCount(configManager.getInt(RETRY_COUNT_PARAM, 3))
            .withConnectTimeout(configManager.getInt(CONNECT_TIMEOUT_PARAM, 30000))
            .withReadTimeout(configManager.getInt(READ_TIMEOUT_PARAM, 30000))
            .build();
        
        // Create client with configuration
        return new BinanceClientImpl(config, metricsCollector);
    }
    
    @Override
    protected void configureService(BinanceClient service) {
        logger.info("Configuring Binance client");
        
        // Setup subscription to market data if needed
        boolean subscribeToMarketData = configManager.getBoolean("binance.subscribeToMarketData", true);
        if (subscribeToMarketData) {
            List<String> symbols = configManager.getStringList("binance.symbols", Arrays.asList("BTCUSDT", "ETHUSDT"));
            service.subscribeToMarketData(symbols);
        }
        
        // Configure any additional client parameters
        service.setLoggingEnabled(configManager.getBoolean("binance.logging.enabled", false));
    }
    
    @Override
    protected void startService(BinanceClient service) {
        logger.info("Starting Binance client");
        service.connect();
    }
    
    @Override
    protected void stopService(BinanceClient service) {
        logger.info("Stopping Binance client");
        service.disconnect();
    }
    
    @Override
    protected void registerHealthChecks(BinanceClient service) {
        logger.info("Registering Binance client health checks");
        
        // Register API connectivity health check
        healthCheckRegistry.register(new BinanceApiHealthCheck(service));
        
        // Register rate limit health check
        healthCheckRegistry.register(new BinanceRateLimitHealthCheck(service));
        
        // Register websocket health check if using websockets
        if (configManager.getBoolean("binance.useWebSocket", true)) {
            healthCheckRegistry.register(new BinanceWebSocketHealthCheck(service));
        }
    }
    
    @Override
    protected void validateConfiguration() {
        logger.info("Validating Binance client configuration");
        
        List<ConfigurationError> errors = new ArrayList<>();
        
        // Validate required parameters
        if (!configManager.hasParameter(API_KEY_PARAM)) {
            errors.add(new ConfigurationError(API_KEY_PARAM, "API key is required"));
        }
        
        if (!configManager.hasParameter(API_SECRET_PARAM)) {
            errors.add(new ConfigurationError(API_SECRET_PARAM, "API secret is required"));
        }
        
        // Validate parameter values
        String apiKey = configManager.getString(API_KEY_PARAM);
        if (apiKey != null && apiKey.trim().isEmpty()) {
            errors.add(new ConfigurationError(API_KEY_PARAM, "API key cannot be empty"));
        }
        
        String apiSecret = configManager.getString(API_SECRET_PARAM);
        if (apiSecret != null && apiSecret.trim().isEmpty()) {
            errors.add(new ConfigurationError(API_SECRET_PARAM, "API secret cannot be empty"));
        }
        
        // Validate numeric parameters
        int rateLimit = configManager.getInt(RATE_LIMIT_PARAM, 1200);
        if (rateLimit <= 0) {
            errors.add(new ConfigurationError(RATE_LIMIT_PARAM, "Rate limit must be positive", rateLimit));
        }
        
        int retryCount = configManager.getInt(RETRY_COUNT_PARAM, 3);
        if (retryCount < 0) {
            errors.add(new ConfigurationError(RETRY_COUNT_PARAM, "Retry count cannot be negative", retryCount));
        }
        
        int connectTimeout = configManager.getInt(CONNECT_TIMEOUT_PARAM, 30000);
        if (connectTimeout <= 0) {
            errors.add(new ConfigurationError(CONNECT_TIMEOUT_PARAM, "Connect timeout must be positive", connectTimeout));
        }
        
        int readTimeout = configManager.getInt(READ_TIMEOUT_PARAM, 30000);
        if (readTimeout <= 0) {
            errors.add(new ConfigurationError(READ_TIMEOUT_PARAM, "Read timeout must be positive", readTimeout));
        }
        
        // Throw exception if there are validation errors
        if (!errors.isEmpty()) {
            throw new ConfigurationException(getServiceName(), errors);
        }
    }
    
    @Override
    protected String getServiceName() {
        return "BinanceClient";
    }
    
    @Override
    protected void setupShutdownHook(BinanceClient service) {
        logger.info("Setting up shutdown hook for Binance client");
        
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            logger.info("Shutdown hook called, disconnecting Binance client");
            try {
                service.disconnect();
            } catch (Exception e) {
                logger.warning("Error during Binance client shutdown: " + e.getMessage());
            }
        }));
    }
    
    /**
     * Health check for Binance API connectivity.
     */
    private static class BinanceApiHealthCheck extends AbstractHealthCheck {
        private final BinanceClient client;
        
        public BinanceApiHealthCheck(BinanceClient client) {
            super("BinanceClient", "binance-api-connectivity");
            this.client = client;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            boolean connected = client.ping();
            
            if (connected) {
                return HealthStatus.healthy("Binance API is reachable");
            } else {
                return HealthStatus.unhealthy("Failed to ping Binance API");
            }
        }
    }
    
    /**
     * Health check for Binance rate limit usage.
     */
    private static class BinanceRateLimitHealthCheck extends AbstractHealthCheck {
        private final BinanceClient client;
        private static final double WARNING_THRESHOLD = 0.8; // 80% of rate limit
        
        public BinanceRateLimitHealthCheck(BinanceClient client) {
            super("BinanceClient", "binance-rate-limit");
            this.client = client;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            double usedRateLimit = client.getRateLimitUsage();
            
            if (usedRateLimit < WARNING_THRESHOLD) {
                return HealthStatus.healthy("Rate limit usage: " + (usedRateLimit * 100) + "%");
            } else {
                return HealthStatus.unhealthy("Rate limit usage too high: " + (usedRateLimit * 100) + "%");
            }
        }
    }
    
    /**
     * Health check for Binance WebSocket connectivity.
     */
    private static class BinanceWebSocketHealthCheck extends AbstractHealthCheck {
        private final BinanceClient client;
        
        public BinanceWebSocketHealthCheck(BinanceClient client) {
            super("BinanceClient", "binance-websocket-connectivity");
            this.client = client;
        }
        
        @Override
        protected HealthStatus doCheck() throws Exception {
            boolean connected = client.isWebSocketConnected();
            
            if (connected) {
                long lastMessageTime = client.getLastWebSocketMessageTime();
                long now = System.currentTimeMillis();
                long elapsedSinceLastMessage = now - lastMessageTime;
                
                // Consider unhealthy if no message received in the last 60 seconds
                if (elapsedSinceLastMessage > 60000) {
                    return HealthStatus.unhealthy("No WebSocket message received in the last " + 
                        (elapsedSinceLastMessage / 1000) + " seconds");
                }
                
                return HealthStatus.healthy("WebSocket connected, last message received " + 
                    (elapsedSinceLastMessage / 1000) + " seconds ago");
            } else {
                return HealthStatus.unhealthy("WebSocket not connected");
            }
        }
    }
} 