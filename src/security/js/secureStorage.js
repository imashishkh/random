/**
 * Secure Storage - Encrypted local storage implementation
 * 
 * This module provides a simple interface for secure local storage
 * using strong encryption for sensitive data.
 */

const crypto = require('crypto');
const fs = require('fs').promises;
const path = require('path');
const os = require('os');
const { logSecurityEvent } = require('./errorHandler');

/**
 * SecureStorage provides an encrypted file-based storage solution
 */
class SecureStorage {
  /**
   * Create a new SecureStorage instance
   * 
   * @param {Object} options - Configuration options
   * @param {string} options.storageDir - Directory to store encrypted files
   * @param {string} options.masterKey - Master encryption key
   * @param {string} options.algorithm - Encryption algorithm to use
   */
  constructor(options = {}) {
    const {
      storageDir = path.join(os.homedir(), '.forex-trading-secure/storage'),
      masterKey = null,
      algorithm = 'aes-256-gcm'
    } = options;
    
    this.storageDir = storageDir;
    this.masterKey = masterKey;
    this.algorithm = algorithm;
    this.initialized = false;
  }
  
  /**
   * Initialize the secure storage
   * 
   * @param {Object} options - Initialization options
   * @param {string} options.masterKey - Master encryption key if not provided in constructor
   * @returns {Promise<boolean>} Whether initialization was successful
   */
  async initialize(options = {}) {
    try {
      // Set master key if provided
      if (options.masterKey) {
        this.masterKey = options.masterKey;
      }
      
      if (!this.masterKey) {
        throw new Error('Master key is required for secure storage');
      }
      
      // Create storage directory if it doesn't exist
      await fs.mkdir(this.storageDir, { recursive: true });
      
      this.initialized = true;
      logSecurityEvent('SecureStorage initialized', 'info');
      
      return true;
    } catch (error) {
      logSecurityEvent(`Failed to initialize SecureStorage: ${error.message}`, 'error');
      throw error;
    }
  }
  
  /**
   * Store data securely
   * 
   * @param {string} key - Storage key
   * @param {Object|string} data - Data to store
   * @returns {Promise<boolean>} Whether storage was successful
   */
  async setItem(key, data) {
    this._checkInitialized();
    
    try {
      const serializedData = typeof data === 'string' ? data : JSON.stringify(data);
      const encrypted = this._encrypt(serializedData);
      const filePath = this._getStoragePath(key);
      
      await fs.writeFile(filePath, encrypted, 'utf8');
      logSecurityEvent(`Data stored securely for key: ${key}`, 'info');
      
      return true;
    } catch (error) {
      logSecurityEvent(`Failed to store data securely: ${error.message}`, 'error');
      throw error;
    }
  }
  
  /**
   * Retrieve data securely
   * 
   * @param {string} key - Storage key
   * @param {boolean} parseJson - Whether to parse the data as JSON
   * @returns {Promise<Object|string>} The retrieved data
   */
  async getItem(key, parseJson = true) {
    this._checkInitialized();
    
    try {
      const filePath = this._getStoragePath(key);
      
      try {
        const encrypted = await fs.readFile(filePath, 'utf8');
        const decrypted = this._decrypt(encrypted);
        
        if (parseJson) {
          try {
            return JSON.parse(decrypted);
          } catch (parseError) {
            // If parsing fails, return the raw string
            return decrypted;
          }
        }
        
        return decrypted;
      } catch (fileError) {
        if (fileError.code === 'ENOENT') {
          return null; // Key doesn't exist
        }
        throw fileError;
      }
    } catch (error) {
      logSecurityEvent(`Failed to retrieve data: ${error.message}`, 'error');
      throw error;
    }
  }
  
  /**
   * Remove data from secure storage
   * 
   * @param {string} key - Storage key
   * @returns {Promise<boolean>} Whether removal was successful
   */
  async removeItem(key) {
    this._checkInitialized();
    
    try {
      const filePath = this._getStoragePath(key);
      
      try {
        await fs.unlink(filePath);
        logSecurityEvent(`Data removed for key: ${key}`, 'info');
        return true;
      } catch (fileError) {
        if (fileError.code === 'ENOENT') {
          return false; // Key doesn't exist
        }
        throw fileError;
      }
    } catch (error) {
      logSecurityEvent(`Failed to remove data: ${error.message}`, 'error');
      throw error;
    }
  }
  
  /**
   * Check if a key exists in storage
   * 
   * @param {string} key - Storage key
   * @returns {Promise<boolean>} Whether the key exists
   */
  async hasItem(key) {
    this._checkInitialized();
    
    try {
      const filePath = this._getStoragePath(key);
      
      try {
        await fs.access(filePath);
        return true;
      } catch {
        return false;
      }
    } catch (error) {
      logSecurityEvent(`Error checking item existence: ${error.message}`, 'warning');
      return false;
    }
  }
  
  /**
   * List all keys in the secure storage
   * 
   * @returns {Promise<string[]>} Array of stored keys
   */
  async listKeys() {
    this._checkInitialized();
    
    try {
      const files = await fs.readdir(this.storageDir);
      return files
        .filter(file => file.endsWith('.enc'))
        .map(file => file.slice(0, -4)); // Remove .enc extension
    } catch (error) {
      logSecurityEvent(`Failed to list storage keys: ${error.message}`, 'error');
      throw error;
    }
  }
  
  /**
   * Clear all stored data
   * 
   * @returns {Promise<boolean>} Whether the operation was successful
   */
  async clear() {
    this._checkInitialized();
    
    try {
      const keys = await this.listKeys();
      
      for (const key of keys) {
        await this.removeItem(key);
      }
      
      logSecurityEvent('All secure storage data cleared', 'warning');
      return true;
    } catch (error) {
      logSecurityEvent(`Failed to clear secure storage: ${error.message}`, 'error');
      throw error;
    }
  }
  
  /**
   * Get the storage file path for a key
   * 
   * @param {string} key - Storage key
   * @returns {string} File path
   * @private
   */
  _getStoragePath(key) {
    const sanitizedKey = key.replace(/[/\\?%*:|"<>]/g, '-');
    return path.join(this.storageDir, `${sanitizedKey}.enc`);
  }
  
  /**
   * Encrypt data using the master key
   * 
   * @param {string} data - Data to encrypt
   * @returns {string} Encrypted data
   * @private
   */
  _encrypt(data) {
    try {
      // Generate a random initialization vector
      const iv = crypto.randomBytes(16);
      
      // Create a key from the master key
      const key = crypto.createHash('sha256').update(this.masterKey).digest();
      
      // Create cipher with key and IV
      const cipher = crypto.createCipheriv(this.algorithm, key, iv);
      
      // Encrypt the data
      let encrypted = cipher.update(data, 'utf8', 'hex');
      encrypted += cipher.final('hex');
      
      // Get the auth tag (for GCM mode)
      const authTag = cipher.getAuthTag ? cipher.getAuthTag().toString('hex') : '';
      
      // Return IV + encrypted data + auth tag
      return `${iv.toString('hex')}:${encrypted}:${authTag}`;
    } catch (error) {
      throw new Error(`Encryption failed: ${error.message}`);
    }
  }
  
  /**
   * Decrypt data using the master key
   * 
   * @param {string} encryptedData - Data to decrypt
   * @returns {string} Decrypted data
   * @private
   */
  _decrypt(encryptedData) {
    try {
      // Split the encrypted data into components
      const [ivHex, encrypted, authTagHex] = encryptedData.split(':');
      
      if (!ivHex || !encrypted) {
        throw new Error('Invalid encrypted data format');
      }
      
      // Convert hex strings back to buffers
      const iv = Buffer.from(ivHex, 'hex');
      const key = crypto.createHash('sha256').update(this.masterKey).digest();
      
      // Create decipher
      const decipher = crypto.createDecipheriv(this.algorithm, key, iv);
      
      // Set auth tag for GCM mode
      if (authTagHex && decipher.setAuthTag) {
        decipher.setAuthTag(Buffer.from(authTagHex, 'hex'));
      }
      
      // Decrypt the data
      let decrypted = decipher.update(encrypted, 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      
      return decrypted;
    } catch (error) {
      throw new Error(`Decryption failed: ${error.message}`);
    }
  }
  
  /**
   * Check if the storage is initialized
   * 
   * @private
   */
  _checkInitialized() {
    if (!this.initialized) {
      throw new Error('SecureStorage must be initialized before use');
    }
  }
}

module.exports = {
  SecureStorage
}; 