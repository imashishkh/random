package com.forextrader.core.initialization;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Centralized error aggregator for collecting and reporting errors from different services
 * during initialization and runtime.
 */
public class ErrorAggregator {
    private static final Logger logger = Logger.getLogger(ErrorAggregator.class.getName());
    
    // Map of service name to error messages
    private final Map<String, List<ErrorEntry>> errors = new ConcurrentHashMap<>();
    
    /**
     * Reports an error for a specific service.
     * 
     * @param serviceName The name of the service reporting the error
     * @param errorMessage The error message
     * @param exception The exception that caused the error, can be null
     */
    public void reportError(String serviceName, String errorMessage, Throwable exception) {
        ErrorEntry entry = new ErrorEntry(errorMessage, exception, System.currentTimeMillis());
        
        errors.computeIfAbsent(serviceName, k -> new ArrayList<>()).add(entry);
        
        if (exception != null) {
            logger.log(Level.SEVERE, "Error in service " + serviceName + ": " + errorMessage, exception);
        } else {
            logger.log(Level.SEVERE, "Error in service " + serviceName + ": " + errorMessage);
        }
    }
    
    /**
     * Reports an error for a specific service without an exception.
     * 
     * @param serviceName The name of the service reporting the error
     * @param errorMessage The error message
     */
    public void reportError(String serviceName, String errorMessage) {
        reportError(serviceName, errorMessage, null);
    }
    
    /**
     * Returns all errors reported for a specific service.
     * 
     * @param serviceName The name of the service
     * @return List of error entries for the service, or an empty list if none
     */
    public List<ErrorEntry> getErrorsForService(String serviceName) {
        List<ErrorEntry> serviceErrors = errors.get(serviceName);
        if (serviceErrors == null) {
            return Collections.emptyList();
        }
        return Collections.unmodifiableList(serviceErrors);
    }
    
    /**
     * Returns all errors reported for all services.
     * 
     * @return Map of service name to error entries
     */
    public Map<String, List<ErrorEntry>> getAllErrors() {
        return Collections.unmodifiableMap(errors);
    }
    
    /**
     * Checks if any errors have been reported for any service.
     * 
     * @return true if errors have been reported, false otherwise
     */
    public boolean hasErrors() {
        return !errors.isEmpty();
    }
    
    /**
     * Checks if any errors have been reported for a specific service.
     * 
     * @param serviceName The name of the service
     * @return true if errors have been reported for the service, false otherwise
     */
    public boolean hasErrorsForService(String serviceName) {
        List<ErrorEntry> serviceErrors = errors.get(serviceName);
        return serviceErrors != null && !serviceErrors.isEmpty();
    }
    
    /**
     * Clears all errors.
     */
    public void clearAllErrors() {
        errors.clear();
    }
    
    /**
     * Clears all errors for a specific service.
     * 
     * @param serviceName The name of the service
     */
    public void clearErrorsForService(String serviceName) {
        errors.remove(serviceName);
    }
    
    /**
     * Generates a formatted report of all errors.
     * 
     * @return A formatted string containing all errors
     */
    public String generateErrorReport() {
        if (!hasErrors()) {
            return "No errors reported.";
        }
        
        StringBuilder report = new StringBuilder("Error Report:\n");
        
        for (Map.Entry<String, List<ErrorEntry>> entry : errors.entrySet()) {
            String serviceName = entry.getKey();
            List<ErrorEntry> serviceErrors = entry.getValue();
            
            report.append("\nService: ").append(serviceName).append(" (").append(serviceErrors.size()).append(" errors)\n");
            
            for (ErrorEntry error : serviceErrors) {
                report.append("  - ").append(error.getFormattedTimestamp())
                      .append(": ").append(error.getMessage()).append("\n");
                
                Throwable exception = error.getException();
                if (exception != null) {
                    report.append("    Exception: ").append(exception.getClass().getName())
                          .append(": ").append(exception.getMessage()).append("\n");
                    
                    // Add stack trace for the first few frames
                    StackTraceElement[] stackTrace = exception.getStackTrace();
                    int framesToShow = Math.min(5, stackTrace.length);
                    for (int i = 0; i < framesToShow; i++) {
                        report.append("      at ").append(stackTrace[i]).append("\n");
                    }
                    if (stackTrace.length > framesToShow) {
                        report.append("      ... ").append(stackTrace.length - framesToShow)
                              .append(" more\n");
                    }
                }
            }
        }
        
        return report.toString();
    }
    
    /**
     * Represents a single error entry.
     */
    public static class ErrorEntry {
        private final String message;
        private final Throwable exception;
        private final long timestamp;
        
        /**
         * Creates a new error entry.
         * 
         * @param message The error message
         * @param exception The exception that caused the error, can be null
         * @param timestamp The timestamp when the error occurred
         */
        public ErrorEntry(String message, Throwable exception, long timestamp) {
            this.message = message;
            this.exception = exception;
            this.timestamp = timestamp;
        }
        
        /**
         * Returns the error message.
         * 
         * @return The error message
         */
        public String getMessage() {
            return message;
        }
        
        /**
         * Returns the exception that caused the error.
         * 
         * @return The exception, or null if no exception was provided
         */
        public Throwable getException() {
            return exception;
        }
        
        /**
         * Returns the timestamp when the error occurred.
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
    }
} 