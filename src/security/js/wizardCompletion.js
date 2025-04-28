/**
 * Wizard Completion - Track and manage setup wizard completion status
 * 
 * This module provides functionality to track, save, and retrieve the completion
 * status of various setup steps in the application.
 */

const fs = require('fs').promises;
const path = require('path');
const os = require('os');
const { logSecurityEvent } = require('./errorHandler');
const { SecretManager } = require('./secretManager');

// Default completion steps for the setup wizard
const DEFAULT_STEPS = [
  'welcome',
  'credentials',
  'api_setup',
  'data_sources',
  'notification_preferences',
  'security_options',
  'final_review'
];

/**
 * Class to handle wizard completion tracking
 */
class WizardCompletion {
  /**
   * Create a new WizardCompletion instance
   * 
   * @param {Object} options - Configuration options
   * @param {string} options.appName - Name of the application
   * @param {string[]} options.steps - Custom steps to track (optional)
   * @param {string} options.dataDir - Directory to save completion data
   * @param {SecretManager} options.secretManager - SecretManager instance
   */
  constructor(options = {}) {
    const {
      appName = 'ForexTradingApp',
      steps = DEFAULT_STEPS,
      dataDir = path.join(os.homedir(), '.forex-trading-data'),
      secretManager = null
    } = options;
    
    this.appName = appName;
    this.steps = steps;
    this.dataDir = dataDir;
    this.secretManager = secretManager;
    this.completionData = {
      completedSteps: [],
      lastCompletedStep: null,
      lastCompletedTimestamp: null,
      isComplete: false
    };
    
    this.dataFile = path.join(this.dataDir, 'wizard-completion.json');
    this.initialized = false;
  }
  
  /**
   * Initialize the WizardCompletion module
   * 
   * @returns {Promise<boolean>} Whether initialization was successful
   */
  async initialize() {
    try {
      // Create data directory if it doesn't exist
      await fs.mkdir(this.dataDir, { recursive: true });
      
      // Try to load existing completion data
      try {
        const data = await fs.readFile(this.dataFile, 'utf8');
        this.completionData = JSON.parse(data);
        
        // Migration for older versions without all fields
        if (!this.completionData.hasOwnProperty('completedSteps')) {
          this.completionData.completedSteps = [];
        }
        if (!this.completionData.hasOwnProperty('isComplete')) {
          this.completionData.isComplete = false;
        }
      } catch (readError) {
        if (readError.code !== 'ENOENT') {
          logSecurityEvent(`Error reading wizard completion data: ${readError.message}`, 'warning');
        }
        // File doesn't exist or is invalid - use default empty state
      }
      
      this.initialized = true;
      return true;
    } catch (error) {
      logSecurityEvent(`Failed to initialize WizardCompletion: ${error.message}`, 'error');
      throw error;
    }
  }
  
  /**
   * Mark a step as completed
   * 
   * @param {string} step - Step identifier
   * @param {Object} metadata - Additional metadata about the completion
   * @returns {Promise<boolean>} Whether the operation was successful
   */
  async completeStep(step, metadata = {}) {
    this._checkInitialized();
    
    if (!this.steps.includes(step)) {
      logSecurityEvent(`Attempted to complete unknown step: ${step}`, 'warning');
      return false;
    }
    
    const timestamp = new Date().toISOString();
    
    // Add to completed steps if not already there
    if (!this.completionData.completedSteps.includes(step)) {
      this.completionData.completedSteps.push(step);
    }
    
    this.completionData.lastCompletedStep = step;
    this.completionData.lastCompletedTimestamp = timestamp;
    
    // Check if all steps are completed
    const allStepsCompleted = this.steps.every(s => 
      this.completionData.completedSteps.includes(s)
    );
    
    this.completionData.isComplete = allStepsCompleted;
    
    // Store completion event using SecretManager if available (for audit)
    if (this.secretManager && this.secretManager.initialized) {
      try {
        await this.secretManager.storeCredential(`wizard_step_${step}`, {
          timestamp,
          step,
          metadata
        });
      } catch (storeError) {
        logSecurityEvent(`Failed to store step completion in SecretManager: ${storeError.message}`, 'warning');
        // Continue anyway - this is just for audit purposes
      }
    }
    
    // Save completion data to file
    await this._saveCompletionData();
    
    logSecurityEvent(`Wizard step completed: ${step}`, 'info', { 
      stepIndex: this.steps.indexOf(step) + 1,
      totalSteps: this.steps.length,
      isComplete: this.completionData.isComplete
    });
    
    return true;
  }
  
  /**
   * Get the current completion status
   * 
   * @returns {Object} Completion status object
   */
  getCompletionStatus() {
    this._checkInitialized();
    
    const totalSteps = this.steps.length;
    const completedCount = this.completionData.completedSteps.length;
    
    return {
      ...this.completionData,
      progress: {
        completed: completedCount,
        total: totalSteps,
        percentage: Math.round((completedCount / totalSteps) * 100)
      },
      remainingSteps: this.steps.filter(
        step => !this.completionData.completedSteps.includes(step)
      ),
      nextStep: this._getNextStep()
    };
  }
  
  /**
   * Check if a specific step is completed
   * 
   * @param {string} step - Step identifier
   * @returns {boolean} Whether the step is completed
   */
  isStepCompleted(step) {
    this._checkInitialized();
    return this.completionData.completedSteps.includes(step);
  }
  
  /**
   * Reset wizard completion data
   * 
   * @param {boolean} preserveHistory - Whether to keep history in SecretManager
   * @returns {Promise<boolean>} Whether the operation was successful
   */
  async resetWizard(preserveHistory = false) {
    this._checkInitialized();
    
    // Reset the completion data
    this.completionData = {
      completedSteps: [],
      lastCompletedStep: null,
      lastCompletedTimestamp: null,
      isComplete: false
    };
    
    // Save the reset state
    await this._saveCompletionData();
    
    if (!preserveHistory && this.secretManager && this.secretManager.initialized) {
      // Clean up history in SecretManager
      for (const step of this.steps) {
        try {
          await this.secretManager.deleteCredential(`wizard_step_${step}`);
        } catch (error) {
          // Ignore errors for non-existent entries
        }
      }
    }
    
    logSecurityEvent(`Wizard progress has been reset`, 'info', {
      preserveHistory
    });
    
    return true;
  }
  
  /**
   * Get the next incomplete step
   * 
   * @returns {string|null} Next step identifier or null if complete
   * @private
   */
  _getNextStep() {
    if (this.completionData.isComplete) {
      return null;
    }
    
    for (const step of this.steps) {
      if (!this.completionData.completedSteps.includes(step)) {
        return step;
      }
    }
    
    return null;
  }
  
  /**
   * Save completion data to file
   * 
   * @returns {Promise<void>}
   * @private
   */
  async _saveCompletionData() {
    try {
      await fs.writeFile(
        this.dataFile,
        JSON.stringify(this.completionData, null, 2),
        'utf8'
      );
    } catch (error) {
      logSecurityEvent(`Failed to save wizard completion data: ${error.message}`, 'error');
      throw error;
    }
  }
  
  /**
   * Check if the module is initialized
   * 
   * @throws {Error} If not initialized
   * @private
   */
  _checkInitialized() {
    if (!this.initialized) {
      throw new Error('WizardCompletion must be initialized before use');
    }
  }
}

module.exports = {
  WizardCompletion,
  DEFAULT_STEPS
}; 