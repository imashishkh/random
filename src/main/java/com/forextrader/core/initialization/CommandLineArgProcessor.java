package com.forextrader.core.initialization;

import java.util.HashMap;
import java.util.Map;
import java.util.logging.Logger;

/**
 * Processes command-line arguments for the application.
 * Supports various argument formats:
 * --key=value
 * --key value
 * -k value
 */
public class CommandLineArgProcessor {
    private static final Logger logger = Logger.getLogger(CommandLineArgProcessor.class.getName());
    
    private final Map<String, String> arguments = new HashMap<>();
    
    /**
     * Creates a new command-line argument processor.
     *
     * @param args The command-line arguments to process
     */
    public CommandLineArgProcessor(String[] args) {
        processArgs(args);
    }
    
    /**
     * Processes the command-line arguments and stores them in the arguments map.
     *
     * @param args The command-line arguments to process
     */
    private void processArgs(String[] args) {
        if (args == null || args.length == 0) {
            logger.info("No command-line arguments provided");
            return;
        }
        
        for (int i = 0; i < args.length; i++) {
            String arg = args[i];
            
            // Handle --key=value format
            if (arg.startsWith("--") && arg.contains("=")) {
                String[] parts = arg.substring(2).split("=", 2);
                if (parts.length == 2) {
                    arguments.put(parts[0], parts[1]);
                    logger.fine("Processed argument: " + parts[0] + " = " + parts[1]);
                }
            }
            // Handle --key value format
            else if (arg.startsWith("--")) {
                String key = arg.substring(2);
                if (i + 1 < args.length && !args[i + 1].startsWith("-")) {
                    arguments.put(key, args[i + 1]);
                    logger.fine("Processed argument: " + key + " = " + args[i + 1]);
                    i++; // Skip the value in the next iteration
                } else {
                    // Flag without value
                    arguments.put(key, "true");
                    logger.fine("Processed flag: " + key);
                }
            }
            // Handle -k value format
            else if (arg.startsWith("-") && arg.length() == 2) {
                String key = arg.substring(1);
                if (i + 1 < args.length && !args[i + 1].startsWith("-")) {
                    arguments.put(key, args[i + 1]);
                    logger.fine("Processed argument: " + key + " = " + args[i + 1]);
                    i++; // Skip the value in the next iteration
                } else {
                    // Flag without value
                    arguments.put(key, "true");
                    logger.fine("Processed flag: " + key);
                }
            }
        }
        
        logger.info("Processed " + arguments.size() + " command-line arguments");
    }
    
    /**
     * Checks if an argument with the given key exists.
     *
     * @param key The argument key to check
     * @return true if the argument exists, false otherwise
     */
    public boolean hasArgument(String key) {
        return arguments.containsKey(key);
    }
    
    /**
     * Gets the value of an argument with the given key.
     *
     * @param key The argument key
     * @return The argument value, or null if the argument doesn't exist
     */
    public String getArgumentValue(String key) {
        return arguments.get(key);
    }
    
    /**
     * Gets the value of an argument with the given key, or returns a default value
     * if the argument doesn't exist.
     *
     * @param key The argument key
     * @param defaultValue The default value to return if the argument doesn't exist
     * @return The argument value, or the default value if the argument doesn't exist
     */
    public String getArgumentValue(String key, String defaultValue) {
        return arguments.getOrDefault(key, defaultValue);
    }
    
    /**
     * Gets the value of an argument as an integer.
     *
     * @param key The argument key
     * @param defaultValue The default value to return if the argument doesn't exist or can't be parsed
     * @return The argument value as an integer, or the default value if the argument doesn't exist or can't be parsed
     */
    public int getIntArgumentValue(String key, int defaultValue) {
        String value = getArgumentValue(key);
        if (value == null) {
            return defaultValue;
        }
        
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            logger.warning("Failed to parse argument " + key + " as integer: " + value);
            return defaultValue;
        }
    }
    
    /**
     * Gets the value of an argument as a boolean.
     *
     * @param key The argument key
     * @param defaultValue The default value to return if the argument doesn't exist
     * @return The argument value as a boolean, or the default value if the argument doesn't exist
     */
    public boolean getBooleanArgumentValue(String key, boolean defaultValue) {
        String value = getArgumentValue(key);
        if (value == null) {
            return defaultValue;
        }
        
        return "true".equalsIgnoreCase(value) || "yes".equalsIgnoreCase(value) || "1".equals(value);
    }
    
    /**
     * Gets the value of an argument as a double.
     *
     * @param key The argument key
     * @param defaultValue The default value to return if the argument doesn't exist or can't be parsed
     * @return The argument value as a double, or the default value if the argument doesn't exist or can't be parsed
     */
    public double getDoubleArgumentValue(String key, double defaultValue) {
        String value = getArgumentValue(key);
        if (value == null) {
            return defaultValue;
        }
        
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException e) {
            logger.warning("Failed to parse argument " + key + " as double: " + value);
            return defaultValue;
        }
    }
    
    /**
     * Gets all processed arguments.
     *
     * @return A map of all processed arguments
     */
    public Map<String, String> getAllArguments() {
        return new HashMap<>(arguments);
    }
} 