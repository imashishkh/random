/**
 * Credential Wizard - Interactive process for secure credential setup
 * 
 * This module provides a step-by-step wizard for setting up and testing
 * credentials with appropriate validation and error handling at each step.
 */

const { SecretManager, ErrorCodes } = require('./secretManager');
const { handleError } = require('./errorHandler');
const inquirer = require('inquirer');
const chalk = require('chalk');

/**
 * CredentialWizard class provides an interactive wizard for credential setup
 */
class CredentialWizard {
  /**
   * Creates a new CredentialWizard instance
   * 
   * @param {Object} options - Configuration options
   * @param {string} options.serviceName - Name of the service for SecretManager
   * @param {string} options.namespace - Optional namespace for organizing credentials
   * @param {Function} options.onComplete - Optional callback when wizard completes
   */
  constructor(options = {}) {
    this.serviceName = options.serviceName || 'ForexTradingV4';
    this.namespace = options.namespace || 'default';
    this.onComplete = options.onComplete || null;
    this.secretManager = new SecretManager(this.serviceName, this.namespace);
    this.steps = [];
    this.currentStep = 0;
    this.results = {};
    this.completed = false;
  }

  /**
   * Add a step to the credential wizard
   * 
   * @param {Object} step - Step configuration
   * @param {string} step.id - Unique identifier for the step
   * @param {string} step.title - Title displayed during the step
   * @param {Function} step.action - Function that performs the step's action
   * @param {boolean} step.required - Whether the step is required to complete the wizard
   * @returns {CredentialWizard} This instance for chaining
   */
  addStep(step) {
    if (!step.id || !step.action) {
      throw new Error('Steps must have an id and action function');
    }
    
    this.steps.push({
      id: step.id,
      title: step.title || `Step ${this.steps.length + 1}`,
      action: step.action,
      required: step.required !== false,
      description: step.description || '',
      validate: step.validate || null
    });
    
    return this;
  }

  /**
   * Start the wizard process
   * 
   * @returns {Promise<Object>} Results of the wizard
   */
  async start() {
    console.log(chalk.blue.bold(`\n${this.serviceName} Credential Setup Wizard`));
    console.log(chalk.blue('='.repeat(50)));
    
    if (this.steps.length === 0) {
      console.log(chalk.yellow('No steps defined for this wizard.'));
      return {};
    }
    
    try {
      for (this.currentStep = 0; this.currentStep < this.steps.length; this.currentStep++) {
        const step = this.steps[this.currentStep];
        
        console.log(chalk.green(`\n${step.title}`));
        if (step.description) {
          console.log(chalk.gray(step.description));
        }
        
        try {
          // Execute the step action
          const result = await step.action(this.results);
          
          // Validate the result if a validator is provided
          if (step.validate && typeof step.validate === 'function') {
            const isValid = await step.validate(result);
            if (!isValid) {
              throw new Error(`Validation failed for step: ${step.id}`);
            }
          }
          
          // Store the result
          this.results[step.id] = result;
          
          console.log(chalk.green(`✓ Completed: ${step.title}`));
        } catch (error) {
          const handled = handleError(error, `Error in step "${step.id}"`);
          console.error(chalk.red(`✗ ${handled.userMessage}`));
          
          // Ask to retry, skip, or abort
          if (step.required) {
            const { action } = await inquirer.prompt([{
              type: 'list',
              name: 'action',
              message: 'What would you like to do?',
              choices: [
                { name: 'Retry this step', value: 'retry' },
                { name: 'Abort wizard', value: 'abort' }
              ]
            }]);
            
            if (action === 'retry') {
              this.currentStep--; // Retry the current step
              continue;
            } else {
              console.log(chalk.red('Wizard aborted.'));
              return this.results;
            }
          } else {
            // For non-required steps, offer skip option
            const { action } = await inquirer.prompt([{
              type: 'list',
              name: 'action',
              message: 'What would you like to do?',
              choices: [
                { name: 'Retry this step', value: 'retry' },
                { name: 'Skip this step', value: 'skip' },
                { name: 'Abort wizard', value: 'abort' }
              ]
            }]);
            
            if (action === 'retry') {
              this.currentStep--; // Retry the current step
            } else if (action === 'skip') {
              console.log(chalk.yellow(`Skipped: ${step.title}`));
            } else {
              console.log(chalk.red('Wizard aborted.'));
              return this.results;
            }
          }
        }
      }
      
      this.completed = true;
      console.log(chalk.blue('='.repeat(50)));
      console.log(chalk.green.bold('Wizard completed successfully!'));
      
      // Call onComplete callback if provided
      if (typeof this.onComplete === 'function') {
        await this.onComplete(this.results);
      }
      
      return this.results;
    } catch (error) {
      const handled = handleError(error, 'Unexpected error in credential wizard');
      console.error(chalk.red(`Wizard failed: ${handled.userMessage}`));
      return this.results;
    }
  }

  /**
   * Create a common step for collecting credentials
   * 
   * @param {Object} options - Step options
   * @param {string} options.id - Unique identifier for the step
   * @param {string} options.title - Step title
   * @param {string} options.credentialName - Name to use when storing the credential
   * @param {Array<Object>} options.fields - Form fields to collect
   * @param {Function} options.validator - Optional function to validate the credentials
   * @returns {Object} Step configuration object
   */
  static createCredentialStep(options) {
    if (!options.id || !options.credentialName || !options.fields) {
      throw new Error('Credential steps require id, credentialName, and fields');
    }
    
    return {
      id: options.id,
      title: options.title || `Enter ${options.credentialName} credentials`,
      description: options.description || `Please provide your ${options.credentialName} credentials:`,
      required: options.required !== false,
      action: async (wizardData) => {
        // Collect credential information using inquirer
        const answers = await inquirer.prompt(options.fields);
        
        // If a transformer is provided, use it to process the credentials
        const credentials = options.transformer ? 
          options.transformer(answers) : answers;
        
        return credentials;
      },
      validate: options.validator
    };
  }

  /**
   * Create a common step for testing credentials
   * 
   * @param {Object} options - Step options
   * @param {string} options.id - Unique identifier for the step
   * @param {string} options.title - Step title
   * @param {string} options.credentialStepId - ID of the step containing credentials to test
   * @param {Function} options.testFn - Function that tests the credentials
   * @returns {Object} Step configuration object
   */
  static createTestStep(options) {
    if (!options.id || !options.credentialStepId || !options.testFn) {
      throw new Error('Test steps require id, credentialStepId, and testFn');
    }
    
    return {
      id: options.id,
      title: options.title || 'Test connection',
      description: options.description || 'Testing your credentials...',
      required: options.required !== false,
      action: async (wizardData) => {
        const credentials = wizardData[options.credentialStepId];
        
        if (!credentials) {
          throw new Error(`Credentials from step '${options.credentialStepId}' not found`);
        }
        
        console.log(chalk.yellow('Testing credentials...'));
        
        // Test the credentials
        const result = await options.testFn(credentials);
        
        console.log(chalk.green('✓ Connection test successful!'));
        
        return result;
      }
    };
  }

  /**
   * Create a common step for saving credentials
   * 
   * @param {Object} options - Step options
   * @param {string} options.id - Unique identifier for the step
   * @param {string} options.title - Step title
   * @param {string} options.credentialStepId - ID of the step containing credentials to save
   * @param {string} options.credentialName - Name to use when storing the credential
   * @param {Function} options.transformer - Optional function to transform data before saving
   * @returns {Object} Step configuration object
   */
  static createSaveStep(options) {
    if (!options.id || !options.credentialStepId || !options.credentialName) {
      throw new Error('Save steps require id, credentialStepId, and credentialName');
    }
    
    return {
      id: options.id,
      title: options.title || `Save ${options.credentialName} credentials`,
      description: options.description || `Securely saving your ${options.credentialName} credentials...`,
      action: async (wizardData) => {
        const credentials = wizardData[options.credentialStepId];
        
        if (!credentials) {
          throw new Error(`Credentials from step '${options.credentialStepId}' not found`);
        }
        
        // Allow transforming the data before saving
        const dataToSave = options.transformer ? 
          options.transformer(credentials) : 
          JSON.stringify(credentials);
        
        // Create a secret manager if not already part of the instance
        const secretManager = this?.secretManager || 
          new SecretManager(options.serviceName || 'ForexTradingV4', options.namespace || 'default');
        
        // Check if credential already exists
        const exists = await secretManager.hasSecret(options.credentialName);
        
        if (exists) {
          // Ask for confirmation before overwriting
          const { confirm } = await inquirer.prompt([{
            type: 'confirm',
            name: 'confirm',
            message: `Credential '${options.credentialName}' already exists. Overwrite?`,
            default: false
          }]);
          
          if (!confirm) {
            console.log(chalk.yellow('Skipped saving credentials.'));
            return { saved: false, exists: true };
          }
        }
        
        // Save the credential
        await secretManager.storeSecret(options.credentialName, dataToSave);
        
        console.log(chalk.green(`✓ Credentials saved as '${options.credentialName}'`));
        
        return { saved: true, name: options.credentialName };
      }
    };
  }
}

module.exports = CredentialWizard; 