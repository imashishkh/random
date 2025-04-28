/**
 * Secret Manager - Secure storage and management of credentials
 * 
 * This module provides a secure way to store and retrieve sensitive credentials
 * using system keychain when available and falling back to encrypted file storage.
 */

const crypto = require('crypto');
const fs = require('fs').promises;
const path = require('path');
const os = require('os');
const { promisify } = require('util');
const keytar = require('keytar');
const { logSecurityEvent } = require('./errorHandler');

// Define error codes for better error handling
const ErrorCodes = {
  KEYCHAIN_ACCESS_DENIED: 'KEYCHAIN_ACCESS_DENIED',
  ENCRYPTION_FAILED: 'ENCRYPTION_FAILED',
  DECRYPTION_FAILED: 'DECRYPTION_FAILED',
  CREDENTIAL_NOT_FOUND: 'CREDENTIAL_NOT_FOUND',
  VERIFICATION_FAILED: 'VERIFICATION_FAILED',
  CONFIGURATION_ERROR: 'CONFIGURATION_ERROR',
  INVALID_PARAMETERS: 'INVALID_PARAMETERS'
};

/**
 * Custom error class for SecretManager-specific errors
 */
class SecretManagerError extends Error {
  /**
   * @param {string} message - Error message
   * @param {string} code - Error code from ErrorCodes
   */
  constructor(message, code) {
    super(message);
    this.name = 'SecretManagerError';
    this.code = code;
  }
}

/**
 * SecretManager provides secure storage and retrieval of credentials
 */
class SecretManager {
  /**
   * Create a new SecretManager instance
   * 
   * @param {Object} options - Configuration options
   * @param {string} options.appName - Application name (used for keychain service name)
   * @param {string} options.namespace - Namespace to organize credentials
   * @param {boolean} options.useKeychain - Whether to use system keychain (default: true)
   * @param {string} options.fallbackDir - Directory for fallback encrypted storage
   * @param {string} options.masterPasswordFile - File to store master password hash
   */
  constructor(options = {}) {
    const {
      appName = 'ForexTradingApp',
      namespace = 'default',
      useKeychain = true,
      fallbackDir = path.join(os.homedir(), '.forex-trading-secure'),
      masterPasswordFile = 'master-key.hash'
    } = options;
    
    this.appName = appName;
    this.namespace = namespace;
    this.useKeychain = useKeychain;
    this.fallbackDir = fallbackDir;
    this.masterPasswordFile = path.join(this.fallbackDir, masterPasswordFile);
    this.masterPassword = null;
    this.initialized = false;
  }
  
  /**
   * Initialize the SecretManager
   * 
   * @param {Object} options - Initialization options
   * @param {string} options.masterPassword - Master password for fallback encryption
   * @returns {Promise<boolean>} Whether initialization was successful
   */
  async initialize(options = {}) {
    try {
      // Create fallback directory if it doesn't exist
      await fs.mkdir(this.fallbackDir, { recursive: true });
      
      if (options.masterPassword) {
        this.masterPassword = options.masterPassword;
        
        // Store a hash of the master password
        const hash = crypto.createHash('sha256').update(this.masterPassword).digest('hex');
        await fs.writeFile(this.masterPasswordFile, hash);
      } else if (!this.useKeychain) {
        // If we're not using keychain, we need a master password
        throw new SecretManagerError(
          'Master password is required when keychain is disabled',
          ErrorCodes.CONFIGURATION_ERROR
        );
      }
      
      this.initialized = true;
      logSecurityEvent('SecretManager initialized successfully', 'info', { 
        namespace: this.namespace, 
        useKeychain: this.useKeychain 
      });
      
      return true;
    } catch (error) {
      // Handle initialization errors
      if (error instanceof SecretManagerError) {
        throw error;
      }
      
      throw new SecretManagerError(
        `Failed to initialize SecretManager: ${error.message}`,
        ErrorCodes.CONFIGURATION_ERROR
      );
    }
  }
  
  /**
   * Check if a credential exists
   * 
   * @param {string} serviceName - Service name
   * @returns {Promise<boolean>} Whether the credential exists
   */
  async hasCredential(serviceName) {
    this._checkInitialized();
    const key = this._getCredentialKey(serviceName);
    
    try {
      if (this.useKeychain) {
        const credential = await keytar.getPassword(this.appName, key);
        return credential !== null;
      } else {
        const filePath = this._getCredentialPath(key);
        try {
          await fs.access(filePath);
          return true;
        } catch {
          return false;
        }
      }
    } catch (error) {
      // Just return false on errors instead of throwing
      logSecurityEvent(`Error checking credential existence: ${error.message}`, 'warning', {
        service: serviceName
      });
      return false;
    }
  }
  
  /**
   * Store a credential securely
   * 
   * @param {string} serviceName - Service name
   * @param {Object} credential - Credential object to store
   * @returns {Promise<boolean>} Whether the operation was successful
   */
  async storeCredential(serviceName, credential) {
    this._checkInitialized();
    
    if (!serviceName || typeof credential !== 'object') {
      throw new SecretManagerError(
        'Invalid parameters: serviceName must be a string and credential must be an object',
        ErrorCodes.INVALID_PARAMETERS
      );
    }
    
    const key = this._getCredentialKey(serviceName);
    const serializedCredential = JSON.stringify(credential);
    
    try {
      if (this.useKeychain) {
        await keytar.setPassword(this.appName, key, serializedCredential);
      } else {
        // Fallback to file-based storage with encryption
        const encryptedData = this._encrypt(serializedCredential);
        const filePath = this._getCredentialPath(key);
        await fs.writeFile(filePath, encryptedData);
      }
      
      logSecurityEvent(`Credential stored successfully`, 'info', {
        service: serviceName,
        storageType: this.useKeychain ? 'keychain' : 'file'
      });
      
      return true;
    } catch (error) {
      // Handle specific errors
      if (error.message && error.message.includes('access denied')) {
        throw new SecretManagerError(
          'Access to secure storage was denied. Check application permissions.',
          ErrorCodes.KEYCHAIN_ACCESS_DENIED
        );
      }
      
      throw new SecretManagerError(
        `Failed to store credential: ${error.message}`,
        ErrorCodes.ENCRYPTION_FAILED
      );
    }
  }
  
  /**
   * Retrieve a credential
   * 
   * @param {string} serviceName - Service name
   * @returns {Promise<Object>} The retrieved credential
   */
  async getCredential(serviceName) {
    this._checkInitialized();
    const key = this._getCredentialKey(serviceName);
    
    try {
      let credentialData;
      
      if (this.useKeychain) {
        credentialData = await keytar.getPassword(this.appName, key);
        if (!credentialData) {
          throw new SecretManagerError(
            `Credential not found for service: ${serviceName}`,
            ErrorCodes.CREDENTIAL_NOT_FOUND
          );
        }
      } else {
        // Get from encrypted file
        const filePath = this._getCredentialPath(key);
        try {
          const encryptedData = await fs.readFile(filePath, 'utf8');
          credentialData = this._decrypt(encryptedData);
        } catch (fileError) {
          if (fileError.code === 'ENOENT') {
            throw new SecretManagerError(
              `Credential not found for service: ${serviceName}`,
              ErrorCodes.CREDENTIAL_NOT_FOUND
            );
          }
          throw fileError;
        }
      }
      
      // Parse the JSON data
      try {
        return JSON.parse(credentialData);
      } catch (parseError) {
        throw new SecretManagerError(
          'Failed to parse credential data. Storage may be corrupted.',
          ErrorCodes.DECRYPTION_FAILED
        );
      }
    } catch (error) {
      // Pass through SecretManagerError instances
      if (error instanceof SecretManagerError) {
        throw error;
      }
      
      // Handle other errors
      if (error.message && error.message.includes('access denied')) {
        throw new SecretManagerError(
          'Access to secure storage was denied. Check application permissions.',
          ErrorCodes.KEYCHAIN_ACCESS_DENIED
        );
      }
      
      throw new SecretManagerError(
        `Failed to retrieve credential: ${error.message}`,
        ErrorCodes.DECRYPTION_FAILED
      );
    }
  }
  
  /**
   * Delete a credential
   * 
   * @param {string} serviceName - Service name
   * @returns {Promise<boolean>} Whether the deletion was successful
   */
  async deleteCredential(serviceName) {
    this._checkInitialized();
    const key = this._getCredentialKey(serviceName);
    
    try {
      if (this.useKeychain) {
        const deleted = await keytar.deletePassword(this.appName, key);
        if (!deleted) {
          // Password not found
          return false;
        }
      } else {
        // Delete the file
        const filePath = this._getCredentialPath(key);
        try {
          await fs.unlink(filePath);
        } catch (fileError) {
          if (fileError.code === 'ENOENT') {
            // File doesn't exist, consider it already deleted
            return false;
          }
          throw fileError;
        }
      }
      
      logSecurityEvent(`Credential deleted successfully`, 'info', {
        service: serviceName
      });
      
      return true;
    } catch (error) {
      if (error.message && error.message.includes('access denied')) {
        throw new SecretManagerError(
          'Access to secure storage was denied. Check application permissions.',
          ErrorCodes.KEYCHAIN_ACCESS_DENIED
        );
      }
      
      throw new SecretManagerError(
        `Failed to delete credential: ${error.message}`,
        ErrorCodes.CONFIGURATION_ERROR
      );
    }
  }
  
  /**
   * Verify a credential by testing it with a verification function
   * 
   * @param {string} serviceName - Service name
   * @param {Function} verifyFn - Async function that returns a boolean
   * @returns {Promise<boolean>} Whether the credential is valid
   */
  async verifyCredential(serviceName, verifyFn) {
    if (typeof verifyFn !== 'function') {
      throw new SecretManagerError(
        'Verification function must be provided',
        ErrorCodes.INVALID_PARAMETERS
      );
    }
    
    try {
      const credential = await this.getCredential(serviceName);
      const isValid = await verifyFn(credential);
      
      if (!isValid) {
        logSecurityEvent(`Credential verification failed`, 'warning', {
          service: serviceName
        });
      }
      
      return isValid;
    } catch (error) {
      if (error instanceof SecretManagerError && 
          error.code === ErrorCodes.CREDENTIAL_NOT_FOUND) {
        return false;
      }
      throw error;
    }
  }
  
  /**
   * Generate a credential key from service name
   * 
   * @param {string} serviceName - Service name
   * @returns {string} Credential key
   * @private
   */
  _getCredentialKey(serviceName) {
    return `${this.namespace}:${serviceName}`;
  }
  
  /**
   * Generate a credential file path
   * 
   * @param {string} key - Credential key
   * @returns {string} File path
   * @private
   */
  _getCredentialPath(key) {
    // Replace characters that might not be valid in filenames
    const sanitizedKey = key.replace(/[/\\?%*:|"<>]/g, '-');
    return path.join(this.fallbackDir, `${sanitizedKey}.enc`);
  }
  
  /**
   * Check if SecretManager has been initialized
   * 
   * @private
   */
  _checkInitialized() {
    if (!this.initialized) {
      throw new SecretManagerError(
        'SecretManager must be initialized before use',
        ErrorCodes.CONFIGURATION_ERROR
      );
    }
  }
  
  /**
   * Encrypt data using master password
   * 
   * @param {string} data - Data to encrypt
   * @returns {string} Encrypted data
   * @private
   */
  _encrypt(data) {
    if (!this.masterPassword) {
      throw new SecretManagerError(
        'Master password is required for encryption',
        ErrorCodes.ENCRYPTION_FAILED
      );
    }
    
    try {
      // Generate random IV
      const iv = crypto.randomBytes(16);
      
      // Derive encryption key from master password
      const key = crypto.scryptSync(this.masterPassword, 'salt', 32);
      
      // Create cipher
      const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);
      
      // Encrypt data
      let encrypted = cipher.update(data, 'utf8', 'hex');
      encrypted += cipher.final('hex');
      
      // Return IV + encrypted data
      return `${iv.toString('hex')}:${encrypted}`;
    } catch (error) {
      throw new SecretManagerError(
        `Encryption failed: ${error.message}`,
        ErrorCodes.ENCRYPTION_FAILED
      );
    }
  }
  
  /**
   * Decrypt data using master password
   * 
   * @param {string} encryptedData - Data to decrypt
   * @returns {string} Decrypted data
   * @private
   */
  _decrypt(encryptedData) {
    if (!this.masterPassword) {
      throw new SecretManagerError(
        'Master password is required for decryption',
        ErrorCodes.DECRYPTION_FAILED
      );
    }
    
    try {
      // Split IV and encrypted data
      const [ivHex, encrypted] = encryptedData.split(':');
      
      if (!ivHex || !encrypted) {
        throw new Error('Invalid encrypted data format');
      }
      
      // Convert IV back to Buffer
      const iv = Buffer.from(ivHex, 'hex');
      
      // Derive key from master password
      const key = crypto.scryptSync(this.masterPassword, 'salt', 32);
      
      // Create decipher
      const decipher = crypto.createDecipheriv('aes-256-cbc', key, iv);
      
      // Decrypt data
      let decrypted = decipher.update(encrypted, 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      
      return decrypted;
    } catch (error) {
      throw new SecretManagerError(
        `Decryption failed: ${error.message}`,
        ErrorCodes.DECRYPTION_FAILED
      );
    }
  }
}

module.exports = {
  SecretManager,
  SecretManagerError,
  ErrorCodes
}; 