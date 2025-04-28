/**
 * Security Module - Main entry point
 * 
 * This module exports all security-related components to provide
 * a unified interface for security functionality.
 */

const { 
  handleError, 
  logSecurityEvent, 
  HandledError 
} = require('./errorHandler');

const { 
  SecretManager, 
  SecretManagerError, 
  ErrorCodes: SecretErrorCodes 
} = require('./secretManager');

const { 
  WizardCompletion, 
  DEFAULT_STEPS 
} = require('./wizardCompletion');

const { 
  SecureStorage 
} = require('./secureStorage');

module.exports = {
  // Error Handling
  handleError,
  logSecurityEvent,
  HandledError,
  
  // Secret Management
  SecretManager,
  SecretManagerError,
  SecretErrorCodes,
  
  // Wizard Completion
  WizardCompletion,
  DEFAULT_STEPS,
  
  // Secure Storage
  SecureStorage
}; 