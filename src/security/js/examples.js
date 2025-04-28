/**
 * Security Module Examples
 * 
 * This file contains example code for using the security modules.
 * These examples are for reference and should not be used in production.
 */

const {
  handleError,
  logSecurityEvent,
  HandledError,
  SecretManager,
  WizardCompletion,
  SecureStorage
} = require('./index');

/**
 * Error Handler Examples
 */
async function errorHandlerExamples() {
  console.log('\n--- Error Handler Examples ---');
  
  try {
    // Basic error handling
    try {
      throw new Error('Something went wrong');
    } catch (error) {
      handleError(error, { 
        context: 'errorHandlerExamples',
        userMessage: 'We encountered an issue processing your request',
        rethrow: false
      });
    }
    
    // Logging security events
    logSecurityEvent('User login attempt', 'info', { userId: 123 });
    logSecurityEvent('Invalid access token', 'warning', { ip: '192.168.1.1' });
    
    // Using HandledError
    try {
      throw new HandledError({
        message: 'API request failed',
        code: 'API_ERROR',
        context: 'User profile update',
        userMessage: 'Unable to update your profile at this time',
        originalError: new Error('Network timeout')
      });
    } catch (error) {
      handleError(error, { rethrow: false });
    }
  } catch (error) {
    console.error('Error in errorHandlerExamples:', error.message);
  }
}

/**
 * Secret Manager Examples
 */
async function secretManagerExamples() {
  console.log('\n--- Secret Manager Examples ---');
  
  try {
    // Create and initialize SecretManager
    const secretManager = new SecretManager({
      appName: 'ExampleApp',
      namespace: 'example',
      useKeychain: false, // Use file-based storage for this example
      fallbackDir: './temp-secure'
    });
    
    await secretManager.initialize({
      masterPassword: 'SuperSecurePassword123!'
    });
    console.log('Secret Manager initialized');
    
    // Store credentials
    await secretManager.storeCredential('apiService', {
      apiKey: 'exampleApiKey123',
      apiSecret: 'exampleApiSecret456'
    });
    console.log('Credentials stored');
    
    // Check if credentials exist
    const hasCredentials = await secretManager.hasCredential('apiService');
    console.log('Has credentials:', hasCredentials);
    
    // Retrieve credentials
    const credentials = await secretManager.getCredential('apiService');
    console.log('Retrieved credentials:', credentials);
    
    // Verify credentials
    const isValid = await secretManager.verifyCredential('apiService', (creds) => {
      // This would typically make an API call to verify
      return creds.apiKey === 'exampleApiKey123';
    });
    console.log('Credentials valid:', isValid);
    
    // Delete credentials
    await secretManager.deleteCredential('apiService');
    console.log('Credentials deleted');
  } catch (error) {
    console.error('Error in secretManagerExamples:', error.message);
  }
}

/**
 * Wizard Completion Examples
 */
async function wizardCompletionExamples() {
  console.log('\n--- Wizard Completion Examples ---');
  
  try {
    // Create and initialize WizardCompletion
    const wizard = new WizardCompletion({
      appName: 'ExampleApp',
      dataDir: './temp-wizard-data'
    });
    
    await wizard.initialize();
    console.log('Wizard initialized');
    
    // Complete steps
    await wizard.completeStep('welcome', { source: 'examples.js' });
    await wizard.completeStep('credentials', { userId: 123 });
    console.log('Steps completed');
    
    // Get completion status
    const status = wizard.getCompletionStatus();
    console.log('Completion status:', status);
    
    // Check if specific step is completed
    const isWelcomeCompleted = wizard.isStepCompleted('welcome');
    console.log('Welcome step completed:', isWelcomeCompleted);
    
    // Reset wizard
    await wizard.resetWizard();
    console.log('Wizard reset');
    
    // Check updated status
    const updatedStatus = wizard.getCompletionStatus();
    console.log('Updated completion status:', updatedStatus);
  } catch (error) {
    console.error('Error in wizardCompletionExamples:', error.message);
  }
}

/**
 * Secure Storage Examples
 */
async function secureStorageExamples() {
  console.log('\n--- Secure Storage Examples ---');
  
  try {
    // Create and initialize SecureStorage
    const storage = new SecureStorage({
      storageDir: './temp-storage',
      masterKey: 'SuperSecureStorageKey123!'
    });
    
    await storage.initialize();
    console.log('Secure Storage initialized');
    
    // Store data
    await storage.setItem('userPreferences', {
      theme: 'dark',
      notifications: true,
      lastLogin: new Date().toISOString()
    });
    console.log('Data stored');
    
    // Check if item exists
    const hasItem = await storage.hasItem('userPreferences');
    console.log('Has item:', hasItem);
    
    // Retrieve data
    const data = await storage.getItem('userPreferences');
    console.log('Retrieved data:', data);
    
    // List all keys
    const keys = await storage.listKeys();
    console.log('All keys:', keys);
    
    // Remove item
    await storage.removeItem('userPreferences');
    console.log('Item removed');
    
    // Clear all data
    await storage.clear();
    console.log('All data cleared');
  } catch (error) {
    console.error('Error in secureStorageExamples:', error.message);
  }
}

/**
 * Run all examples
 */
async function runAllExamples() {
  try {
    console.log('Running security module examples...');
    
    await errorHandlerExamples();
    await secretManagerExamples();
    await wizardCompletionExamples();
    await secureStorageExamples();
    
    console.log('\nAll examples completed');
  } catch (error) {
    console.error('Error running examples:', error);
  }
}

// Only run if this file is executed directly
if (require.main === module) {
  runAllExamples();
}

module.exports = {
  errorHandlerExamples,
  secretManagerExamples,
  wizardCompletionExamples,
  secureStorageExamples,
  runAllExamples
}; 