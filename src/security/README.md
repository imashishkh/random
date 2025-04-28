# Security Module

This module provides a comprehensive set of security-related features for the Forex Trading application, including error handling, secret management, secure storage, and setup wizard tracking.

## Components

### Error Handler (`errorHandler.js`)

Standardized error handling mechanism for security components.

- `HandledError` - Custom error class with structured information
- `handleError` - Function to process and format errors
- `logSecurityEvent` - Centralized security event logging

### Secret Manager (`secretManager.js`)

Secure credential storage using system keychain or encrypted files.

- System keychain integration using `keytar`
- Fallback to encrypted file storage
- Credential verification
- Secure deletion

### Secure Storage (`secureStorage.js`)

Encrypted local storage for sensitive data.

- AES-256-GCM encryption
- File-based storage with secure key derivation
- CRUD operations for secure data

### Wizard Completion (`wizardCompletion.js`)

Track and manage setup wizard completion status.

- Progress tracking
- Persistent storage of completion status
- Audit trail for setup steps

## Usage

Import the components from the main index file:

```javascript
const {
  handleError,
  logSecurityEvent,
  SecretManager,
  SecureStorage,
  WizardCompletion
} = require('./security/js');
```

See `examples.js` for detailed usage examples of each component.

## Error Handling Example

```javascript
try {
  // Application code that might throw an error
  throw new Error('API connection failed');
} catch (error) {
  handleError(error, {
    context: 'API Configuration',
    userMessage: 'Unable to connect to trading service',
    rethrow: false
  });
}
```

## Secret Management Example

```javascript
const secretManager = new SecretManager({
  appName: 'ForexTradingApp',
  namespace: 'trading'
});

await secretManager.initialize();

// Store API credentials
await secretManager.storeCredential('tradingApi', {
  apiKey: 'your-api-key',
  apiSecret: 'your-api-secret'
});

// Retrieve credentials later
const credentials = await secretManager.getCredential('tradingApi');
```

## Secure Storage Example

```javascript
const storage = new SecureStorage({
  masterKey: 'your-master-key'
});

await storage.initialize();

// Store user preferences
await storage.setItem('userPreferences', {
  theme: 'dark',
  chartSettings: { interval: '1h', indicators: ['MA', 'RSI'] }
});

// Retrieve preferences
const preferences = await storage.getItem('userPreferences');
```

## Wizard Completion Example

```javascript
const wizard = new WizardCompletion();
await wizard.initialize();

// Mark setup steps as completed
await wizard.completeStep('credentials', { source: 'user-input' });

// Get current progress
const status = wizard.getCompletionStatus();
console.log(`Setup progress: ${status.progress.percentage}%`);
```

## Dependencies

- Node.js 14+
- `crypto` (built-in)
- `keytar` for system keychain access
- `fs/promises` for file operations

## Security Notes

- All sensitive data is encrypted at rest
- Master keys should be stored securely and never hard-coded
- Secure memory handling for sensitive information
- Centralized logging for security-related events 