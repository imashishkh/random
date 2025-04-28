package com.forextrader.core.initialization;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.Set;
import java.util.logging.Logger;

/**
 * Registry that manages all service initializers and their dependencies.
 * Handles dependency resolution and ordered initialization of services.
 */
public class ServiceInitializerRegistry {
    private static final Logger logger = Logger.getLogger(ServiceInitializerRegistry.class.getName());
    
    // Map of initializer class to initializer instance
    private final Map<Class<? extends ServiceInitializer<?>>, ServiceInitializer<?>> initializers = new HashMap<>();
    
    // Set of initializers that have been initialized
    private final Set<Class<? extends ServiceInitializer<?>>> initialized = new HashSet<>();
    
    // Set of initializers that have been started
    private final Set<Class<? extends ServiceInitializer<?>>> started = new HashSet<>();
    
    /**
     * Registers a service initializer with the registry.
     * 
     * @param initializer The initializer to register
     */
    public void registerInitializer(ServiceInitializer<?> initializer) {
        Class<? extends ServiceInitializer<?>> initializerClass = (Class<? extends ServiceInitializer<?>>) initializer.getClass();
        initializers.put(initializerClass, initializer);
        logger.info("Registered initializer: " + initializer.getClass().getSimpleName());
    }
    
    /**
     * Returns a registered initializer by its class.
     * 
     * @param initializerClass The class of the initializer to retrieve
     * @return The initializer instance, or null if not registered
     */
    public <T extends ServiceInitializer<?>> T getInitializer(Class<T> initializerClass) {
        return (T) initializers.get(initializerClass);
    }
    
    /**
     * Checks if an initializer class is registered.
     * 
     * @param initializerClass The class of the initializer to check
     * @return true if the initializer is registered, false otherwise
     */
    public boolean isRegistered(Class<? extends ServiceInitializer<?>> initializerClass) {
        return initializers.containsKey(initializerClass);
    }
    
    /**
     * Returns a list of all registered initializers in dependency order.
     * 
     * @return List of initializers in dependency order
     */
    public List<ServiceInitializer<?>> getInitializersInDependencyOrder() {
        Map<Class<? extends ServiceInitializer<?>>, Set<Class<? extends ServiceInitializer<?>>>> dependencyGraph = buildDependencyGraph();
        
        // Check for cycles in the dependency graph
        checkForCycles(dependencyGraph);
        
        // Perform topological sort
        return topologicalSort(dependencyGraph);
    }
    
    /**
     * Initializes all registered initializers in dependency order.
     * Ensures that dependencies are initialized before the initializers that depend on them.
     */
    public void initializeAll() {
        List<ServiceInitializer<?>> orderedInitializers = getInitializersInDependencyOrder();
        
        logger.info("Initializing services in dependency order");
        for (ServiceInitializer<?> initializer : orderedInitializers) {
            Class<? extends ServiceInitializer<?>> initializerClass = (Class<? extends ServiceInitializer<?>>) initializer.getClass();
            
            if (initialized.contains(initializerClass)) {
                continue;
            }
            
            logger.info("Initializing service: " + initializer.getClass().getSimpleName());
            initializer.init();
            initialized.add(initializerClass);
        }
        logger.info("All services initialized successfully");
    }
    
    /**
     * Starts all initialized initializers in dependency order.
     * Ensures that dependencies are started before the initializers that depend on them.
     */
    public void startAll() {
        List<ServiceInitializer<?>> orderedInitializers = getInitializersInDependencyOrder();
        
        logger.info("Starting services in dependency order");
        for (ServiceInitializer<?> initializer : orderedInitializers) {
            Class<? extends ServiceInitializer<?>> initializerClass = (Class<? extends ServiceInitializer<?>>) initializer.getClass();
            
            if (!initialized.contains(initializerClass)) {
                throw new IllegalStateException("Cannot start uninitialized service: " + initializer.getClass().getSimpleName());
            }
            
            if (started.contains(initializerClass)) {
                continue;
            }
            
            logger.info("Starting service: " + initializer.getClass().getSimpleName());
            initializer.start();
            started.add(initializerClass);
        }
        logger.info("All services started successfully");
    }
    
    /**
     * Stops all started initializers in reverse dependency order.
     * Ensures that initializers are stopped before their dependencies.
     */
    public void stopAll() {
        List<ServiceInitializer<?>> orderedInitializers = getInitializersInDependencyOrder();
        
        // Reverse the order for shutdown to ensure correct dependency handling
        logger.info("Stopping services in reverse dependency order");
        for (int i = orderedInitializers.size() - 1; i >= 0; i--) {
            ServiceInitializer<?> initializer = orderedInitializers.get(i);
            Class<? extends ServiceInitializer<?>> initializerClass = (Class<? extends ServiceInitializer<?>>) initializer.getClass();
            
            if (!started.contains(initializerClass)) {
                continue;
            }
            
            try {
                logger.info("Stopping service: " + initializer.getClass().getSimpleName());
                initializer.stop();
                started.remove(initializerClass);
            } catch (Exception e) {
                logger.warning("Error stopping service " + initializer.getClass().getSimpleName() + ": " + e.getMessage());
                // Continue stopping other services even if one fails
            }
        }
        logger.info("All services stopped");
    }
    
    /**
     * Builds a directed graph of initializer dependencies.
     * The keys in the map are initializers, and the values are the sets of initializers that depend on them.
     * 
     * @return A map representing the dependency graph
     */
    private Map<Class<? extends ServiceInitializer<?>>, Set<Class<? extends ServiceInitializer<?>>>> buildDependencyGraph() {
        Map<Class<? extends ServiceInitializer<?>>, Set<Class<? extends ServiceInitializer<?>>>> graph = new HashMap<>();
        
        // Initialize the graph with empty dependency sets
        for (Class<? extends ServiceInitializer<?>> initializerClass : initializers.keySet()) {
            graph.put(initializerClass, new HashSet<>());
        }
        
        // Add dependency edges to the graph
        for (Map.Entry<Class<? extends ServiceInitializer<?>>, ServiceInitializer<?>> entry : initializers.entrySet()) {
            Class<? extends ServiceInitializer<?>> initializerClass = entry.getKey();
            ServiceInitializer<?> initializer = entry.getValue();
            
            for (Class<? extends ServiceInitializer<?>> dependencyClass : initializer.dependencies()) {
                if (!initializers.containsKey(dependencyClass)) {
                    throw new IllegalStateException("Missing dependency: " + dependencyClass.getSimpleName() +
                        " required by " + initializerClass.getSimpleName());
                }
                
                // Add an edge from dependency to the initializer
                graph.get(dependencyClass).add(initializerClass);
            }
        }
        
        return graph;
    }
    
    /**
     * Checks for cycles in the dependency graph.
     * 
     * @param graph The dependency graph to check
     * @throws IllegalStateException if a cycle is detected
     */
    private void checkForCycles(Map<Class<? extends ServiceInitializer<?>>, Set<Class<? extends ServiceInitializer<?>>> graph) {
        Set<Class<? extends ServiceInitializer<?>>> visited = new HashSet<>();
        Set<Class<? extends ServiceInitializer<?>>> inStack = new HashSet<>();
        
        for (Class<? extends ServiceInitializer<?>> node : graph.keySet()) {
            if (!visited.contains(node)) {
                if (hasCycleDFS(node, graph, visited, inStack)) {
                    throw new IllegalStateException("Cyclic dependency detected in service initializers");
                }
            }
        }
    }
    
    /**
     * Helper method for cycle detection using depth-first search.
     */
    private boolean hasCycleDFS(
            Class<? extends ServiceInitializer<?>> node,
            Map<Class<? extends ServiceInitializer<?>>, Set<Class<? extends ServiceInitializer<?>>> graph,
            Set<Class<? extends ServiceInitializer<?>>> visited,
            Set<Class<? extends ServiceInitializer<?>>> inStack) {
        visited.add(node);
        inStack.add(node);
        
        for (Class<? extends ServiceInitializer<?>> dependent : graph.get(node)) {
            if (!visited.contains(dependent)) {
                if (hasCycleDFS(dependent, graph, visited, inStack)) {
                    return true;
                }
            } else if (inStack.contains(dependent)) {
                return true;
            }
        }
        
        inStack.remove(node);
        return false;
    }
    
    /**
     * Performs a topological sort on the dependency graph to determine initialization order.
     * 
     * @param graph The dependency graph to sort
     * @return A list of initializers in dependency order
     */
    private List<ServiceInitializer<?>> topologicalSort(
            Map<Class<? extends ServiceInitializer<?>>, Set<Class<? extends ServiceInitializer<?>>> graph) {
        // Calculate in-degree for each node (number of dependencies)
        Map<Class<? extends ServiceInitializer<?>>, Integer> inDegree = new HashMap<>();
        for (Class<? extends ServiceInitializer<?>> node : graph.keySet()) {
            inDegree.put(node, 0);
        }
        
        for (Class<? extends ServiceInitializer<?>> node : graph.keySet()) {
            for (Class<? extends ServiceInitializer<?>> dependent : graph.get(node)) {
                inDegree.put(dependent, inDegree.get(dependent) + 1);
            }
        }
        
        // Enqueue nodes with no dependencies
        Queue<Class<? extends ServiceInitializer<?>>> queue = new LinkedList<>();
        for (Map.Entry<Class<? extends ServiceInitializer<?>>, Integer> entry : inDegree.entrySet()) {
            if (entry.getValue() == 0) {
                queue.add(entry.getKey());
            }
        }
        
        // Process the queue
        List<ServiceInitializer<?>> sortedList = new ArrayList<>();
        while (!queue.isEmpty()) {
            Class<? extends ServiceInitializer<?>> node = queue.poll();
            ServiceInitializer<?> initializer = initializers.get(node);
            sortedList.add(initializer);
            
            for (Class<? extends ServiceInitializer<?>> dependent : graph.get(node)) {
                inDegree.put(dependent, inDegree.get(dependent) - 1);
                if (inDegree.get(dependent) == 0) {
                    queue.add(dependent);
                }
            }
        }
        
        // If sortedList does not include all nodes, there was a cycle
        if (sortedList.size() != graph.size()) {
            throw new IllegalStateException("Cyclic dependency detected during topological sort");
        }
        
        return sortedList;
    }
} 