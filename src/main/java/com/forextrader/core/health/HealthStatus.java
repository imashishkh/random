package com.forextrader.core.health;

/**
 * Represents the status of a health check.
 * A health check can be in one of three states: healthy, unhealthy, or unknown.
 */
public class HealthStatus {
    // Status constants
    private static final int STATUS_HEALTHY = 1;
    private static final int STATUS_UNHEALTHY = 0;
    private static final int STATUS_UNKNOWN = -1;
    
    private final int status;
    private final String message;
    private final long timestamp;
    
    /**
     * Creates a new health status.
     * 
     * @param status The status code (healthy, unhealthy, or unknown)
     * @param message A message describing the status
     */
    private HealthStatus(int status, String message) {
        this.status = status;
        this.message = message;
        this.timestamp = System.currentTimeMillis();
    }
    
    /**
     * Creates a healthy status.
     * 
     * @param message A message describing the healthy status
     * @return A healthy status with the provided message
     */
    public static HealthStatus healthy(String message) {
        return new HealthStatus(STATUS_HEALTHY, message);
    }
    
    /**
     * Creates an unhealthy status.
     * 
     * @param message A message describing the unhealthy status
     * @return An unhealthy status with the provided message
     */
    public static HealthStatus unhealthy(String message) {
        return new HealthStatus(STATUS_UNHEALTHY, message);
    }
    
    /**
     * Creates an unknown status.
     * 
     * @param message A message describing the unknown status
     * @return An unknown status with the provided message
     */
    public static HealthStatus unknown(String message) {
        return new HealthStatus(STATUS_UNKNOWN, message);
    }
    
    /**
     * Checks if this status is healthy.
     * 
     * @return true if healthy, false otherwise
     */
    public boolean isHealthy() {
        return status == STATUS_HEALTHY;
    }
    
    /**
     * Checks if this status is unhealthy.
     * 
     * @return true if unhealthy, false otherwise
     */
    public boolean isUnhealthy() {
        return status == STATUS_UNHEALTHY;
    }
    
    /**
     * Checks if this status is unknown.
     * 
     * @return true if unknown, false otherwise
     */
    public boolean isUnknown() {
        return status == STATUS_UNKNOWN;
    }
    
    /**
     * Returns the status message.
     * 
     * @return The status message
     */
    public String getMessage() {
        return message;
    }
    
    /**
     * Returns the timestamp when this status was created.
     * 
     * @return The timestamp in milliseconds since epoch
     */
    public long getTimestamp() {
        return timestamp;
    }
    
    /**
     * Returns a formatted timestamp string.
     * 
     * @return The formatted timestamp
     */
    public String getFormattedTimestamp() {
        return new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS").format(new java.util.Date(timestamp));
    }
    
    @Override
    public String toString() {
        String statusStr;
        if (isHealthy()) {
            statusStr = "HEALTHY";
        } else if (isUnhealthy()) {
            statusStr = "UNHEALTHY";
        } else {
            statusStr = "UNKNOWN";
        }
        
        return statusStr + " - " + message + " (" + getFormattedTimestamp() + ")";
    }
} 