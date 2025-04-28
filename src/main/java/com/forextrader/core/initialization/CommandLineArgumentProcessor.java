package com.forextrader.core.initialization;

import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Logger;

/**
 * Processor for command-line arguments.
 * Provides methods to extract and validate command-line arguments,
 * with a focus on supporting dynamic agent count specification.
 */
public class CommandLineArgumentProcessor {
    private static final Logger logger = Logger.getLogger(CommandLineArgumentProcessor.class.getName());
    
    // Command-line argument names
    private static final String AGENT_COUNT_ARG = "--agent-count";
    private static final String SHORT_AGENT_COUNT_ARG = "-a";
    private static final String CONFIG_FILE_ARG = "--config";
    private static final String SHORT_CONFIG_FILE_ARG = "-c";
    private static final String HELP_ARG = "--help";
    private static final String SHORT_HELP_ARG = "-h";
    
    private final Map<String, String> parsedArgs = new HashMap<>();
    private final String[] originalArgs;
    
    /**
     * Creates a new command-line argument processor.
     * 
     * @param args The command-line arguments to process
     */
    public CommandLineArgumentProcessor(String[] args) {
        this.originalArgs = args;
        parseArgs(args);
    }
    
    /**
     * Parses the command-line arguments into a map of key-value pairs.
     * 
     * @param args The command-line arguments to parse
     */
    private void parseArgs(String[] args) {
        logger.info("Parsing command-line arguments: " + Arrays.toString(args));
        
        for (int i = 0; i < args.length; i++) {
            String arg = args[i];
            
            if (arg.equals(HELP_ARG) || arg.equals(SHORT_HELP_ARG)) {
                parsedArgs.put("help", "true");
                continue;
            }
            
            // Process args that have values
            if (i + 1 < args.length && !args[i + 1].startsWith("-")) {
                if (arg.equals(AGENT_COUNT_ARG) || arg.equals(SHORT_AGENT_COUNT_ARG)) {
                    parsedArgs.put("agentCount", args[i + 1]);
                    i++; // Skip the value in the next iteration
                } else if (arg.equals(CONFIG_FILE_ARG) || arg.equals(SHORT_CONFIG_FILE_ARG)) {
                    parsedArgs.put("configFile", args[i + 1]);
                    i++; // Skip the value in the next iteration
                } else {
                    // Store unknown arguments as well
                    if (arg.startsWith("--")) {
                        String key = arg.substring(2);
                        parsedArgs.put(key, args[i + 1]);
                        i++; // Skip the value in the next iteration
                    } else if (arg.startsWith("-")) {
                        String key = arg.substring(1);
                        parsedArgs.put(key, args[i + 1]);
                        i++; // Skip the value in the next iteration
                    }
                }
            } else {
                // Handle boolean flags (arguments with no values)
                if (arg.startsWith("--")) {
                    String key = arg.substring(2);
                    parsedArgs.put(key, "true");
                } else if (arg.startsWith("-")) {
                    String key = arg.substring(1);
                    parsedArgs.put(key, "true");
                }
            }
        }
        
        logger.info("Parsed arguments: " + parsedArgs);
    }
    
    /**
     * Gets the agent count specified in the command-line arguments.
     * 
     * @return The agent count, or null if not specified
     */
    public Integer getAgentCount() {
        String agentCountStr = parsedArgs.get("agentCount");
        if (agentCountStr != null) {
            try {
                int agentCount = Integer.parseInt(agentCountStr);
                if (agentCount <= 0) {
                    logger.warning("Invalid agent count: " + agentCount + ", must be positive");
                    return null;
                }
                return agentCount;
            } catch (NumberFormatException e) {
                logger.warning("Invalid agent count format: " + agentCountStr);
                return null;
            }
        }
        return null;
    }
    
    /**
     * Gets the config file path specified in the command-line arguments.
     * 
     * @return The config file path, or null if not specified
     */
    public String getConfigFile() {
        return parsedArgs.get("configFile");
    }
    
    /**
     * Checks if help was requested in the command-line arguments.
     * 
     * @return True if help was requested, false otherwise
     */
    public boolean isHelpRequested() {
        return "true".equals(parsedArgs.get("help"));
    }
    
    /**
     * Gets the value of a specific argument.
     * 
     * @param name The name of the argument to get
     * @return The value of the argument, or null if not specified
     */
    public String getArgument(String name) {
        return parsedArgs.get(name);
    }
    
    /**
     * Gets the original command-line arguments.
     * 
     * @return The original command-line arguments
     */
    public String[] getOriginalArgs() {
        return originalArgs.clone();
    }
    
    /**
     * Prints usage information for the command-line arguments.
     */
    public void printUsage() {
        System.out.println("Usage: java -jar forextrader.jar [options]");
        System.out.println("Options:");
        System.out.println("  -a, --agent-count <count>   Specify the number of trading agents to use");
        System.out.println("  -c, --config <file>         Specify the configuration file to use");
        System.out.println("  -h, --help                  Display this help message");
    }
} 