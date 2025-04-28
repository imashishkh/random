/**
 * Error Handler - Standardized error handling for the security module
 * 
 * This module provides centralized error handling functionality for the
 * security-related components, ensuring consistent error messages and logging.
 */

const { ErrorCodes } = require('./secretManager');

/**
 * Standard structure for handled errors
 */
class HandledError {
  /**
   * @param {Error} originalError - The original error that was caught
   * @param {string} context - Contextual information about where the error occurred
   * @param {string} userMessage - User-friendly error message
   * @param {string} code - Error code for programmatic handling
   * @param {boolean} isFatal - Whether this error should be considered fatal
   */
  constructor(originalError, context, userMessage, code, isFatal = false) {
    this.originalError = originalError;
    this.context = context;
    this.userMessage = userMessage;
    this.code = code;
    this.isFatal = isFatal;
    this.timestamp = new Date();
  }
}

/**
 * Handles errors in a standardized way
 * 
 * @param {Error} error - The error to handle
 * @param {string} context - Context in which the error occurred
 * @param {Object} options - Additional options
 * @param {boolean} options.logToConsole - Whether to log the error to console
 * @param {boolean} options.rethrow - Whether to rethrow the error after handling
 * @returns {HandledError} Standardized error object
 */
function handleError(error, context = 'unknown context', options = {}) {
  const { logToConsole = true, rethrow = false } = options;
  
  // Default values
  let userMessage = 'An unexpected error occurred.';
  let errorCode = 'UNKNOWN_ERROR';
  let isFatal = false;
  
  // Handle errors from SecretManager specifically
  if (error.name === 'SecretManagerError') {
    errorCode = error.code;
    userMessage = error.message;
    
    // Determine if the error is fatal based on error code
    isFatal = [
      ErrorCodes.KEYCHAIN_ACCESS_DENIED,
      ErrorCodes.ENCRYPTION_FAILED,
      ErrorCodes.CONFIGURATION_ERROR
    ].includes(errorCode);
  } 
  // Handle generic errors with best-effort categorization
  else {
    const errorMessage = error.message.toLowerCase();
    
    if (errorMessage.includes('permission') || errorMessage.includes('access denied')) {
      errorCode = 'PERMISSION_ERROR';
      userMessage = 'Permission denied. You may not have the necessary access rights.';
      isFatal = true;
    } else if (errorMessage.includes('network') || errorMessage.includes('connection')) {
      errorCode = 'NETWORK_ERROR';
      userMessage = 'Network error. Please check your internet connection.';
    } else if (errorMessage.includes('timeout')) {
      errorCode = 'TIMEOUT_ERROR';
      userMessage = 'Operation timed out. Please try again later.';
    } else if (errorMessage.includes('not found')) {
      errorCode = 'NOT_FOUND_ERROR';
      userMessage = 'The requested resource was not found.';
    } else {
      userMessage = `An error occurred: ${error.message}`;
    }
  }
  
  // Create the handled error
  const handledError = new HandledError(
    error,
    context,
    userMessage,
    errorCode,
    isFatal
  );
  
  // Log to console if requested
  if (logToConsole) {
    console.error(`[ERROR] ${errorCode} in ${context}: ${userMessage}`);
    if (error.stack) {
      console.error(error.stack);
    }
  }
  
  // Rethrow if requested
  if (rethrow) {
    throw error;
  }
  
  return handledError;
}

/**
 * Log an error or warning to the appropriate channels
 * 
 * @param {string} message - The message to log
 * @param {string} level - Log level ('error', 'warning', 'info')
 * @param {Object} metadata - Additional metadata to include
 */
function logSecurityEvent(message, level = 'info', metadata = {}) {
  const timestamp = new Date().toISOString();
  const logEntry = {
    timestamp,
    level,
    message,
    ...metadata
  };
  
  // For now, just log to console, but this could be extended to log to a file or service
  switch (level) {
    case 'error':
      console.error(`[SECURITY ERROR] ${timestamp}: ${message}`, metadata);
      break;
    case 'warning':
      console.warn(`[SECURITY WARNING] ${timestamp}: ${message}`, metadata);
      break;
    case 'info':
    default:
      console.info(`[SECURITY INFO] ${timestamp}: ${message}`, metadata);
      break;
  }
  
  return logEntry;
}

module.exports = {
  handleError,
  HandledError,
  logSecurityEvent
}; 