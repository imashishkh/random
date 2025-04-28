/**
 * Type definitions for the Security Module
 */

declare module 'forex-trading-security' {
  /**
   * Error Handler Types
   */
  export interface HandledErrorOptions {
    message: string;
    code?: string;
    originalError?: Error;
    context?: string;
    userMessage?: string;
    isFatal?: boolean;
  }

  export class HandledError extends Error {
    originalError: Error | null;
    context: string;
    userMessage: string;
    code: string;
    isFatal: boolean;
    timestamp: Date;

    constructor(options: HandledErrorOptions);
  }

  export interface HandleErrorOptions {
    context?: string;
    userMessage?: string;
    code?: string;
    consoleLog?: boolean;
    rethrow?: boolean;
    isFatal?: boolean;
  }

  export function handleError(
    error: Error,
    options?: HandleErrorOptions
  ): HandledError;

  export function logSecurityEvent(
    message: string,
    level?: 'info' | 'warning' | 'error',
    metadata?: Record<string, any>
  ): void;

  /**
   * Secret Manager Types
   */
  export enum SecretErrorCodes {
    KEYCHAIN_ACCESS_DENIED = 'KEYCHAIN_ACCESS_DENIED',
    ENCRYPTION_FAILED = 'ENCRYPTION_FAILED',
    DECRYPTION_FAILED = 'DECRYPTION_FAILED',
    CREDENTIAL_NOT_FOUND = 'CREDENTIAL_NOT_FOUND',
    VERIFICATION_FAILED = 'VERIFICATION_FAILED',
    CONFIGURATION_ERROR = 'CONFIGURATION_ERROR',
    INVALID_PARAMETERS = 'INVALID_PARAMETERS'
  }

  export class SecretManagerError extends Error {
    code: string;
    name: string;
    constructor(message: string, code: string);
  }

  export interface SecretManagerOptions {
    appName?: string;
    namespace?: string;
    useKeychain?: boolean;
    fallbackDir?: string;
    masterPasswordFile?: string;
  }

  export interface SecretManagerInitOptions {
    masterPassword?: string;
  }

  export class SecretManager {
    constructor(options?: SecretManagerOptions);
    initialize(options?: SecretManagerInitOptions): Promise<boolean>;
    hasCredential(serviceName: string): Promise<boolean>;
    storeCredential(serviceName: string, credential: object): Promise<boolean>;
    getCredential(serviceName: string): Promise<object>;
    deleteCredential(serviceName: string): Promise<boolean>;
    verifyCredential(
      serviceName: string,
      verifyFn: (credential: any) => Promise<boolean> | boolean
    ): Promise<boolean>;
  }

  /**
   * Wizard Completion Types
   */
  export const DEFAULT_STEPS: string[];

  export interface WizardCompletionOptions {
    appName?: string;
    steps?: string[];
    dataDir?: string;
    secretManager?: SecretManager | null;
  }

  export interface CompletionStatus {
    completedSteps: string[];
    lastCompletedStep: string | null;
    lastCompletedTimestamp: string | null;
    isComplete: boolean;
    progress: {
      completed: number;
      total: number;
      percentage: number;
    };
    remainingSteps: string[];
    nextStep: string | null;
  }

  export class WizardCompletion {
    constructor(options?: WizardCompletionOptions);
    initialize(): Promise<boolean>;
    completeStep(step: string, metadata?: object): Promise<boolean>;
    getCompletionStatus(): CompletionStatus;
    isStepCompleted(step: string): boolean;
    resetWizard(preserveHistory?: boolean): Promise<boolean>;
  }

  /**
   * Secure Storage Types
   */
  export interface SecureStorageOptions {
    storageDir?: string;
    masterKey?: string | null;
    algorithm?: string;
  }

  export interface SecureStorageInitOptions {
    masterKey?: string;
  }

  export class SecureStorage {
    constructor(options?: SecureStorageOptions);
    initialize(options?: SecureStorageInitOptions): Promise<boolean>;
    setItem(key: string, data: any): Promise<boolean>;
    getItem<T = any>(key: string, parseJson?: boolean): Promise<T | null>;
    removeItem(key: string): Promise<boolean>;
    hasItem(key: string): Promise<boolean>;
    listKeys(): Promise<string[]>;
    clear(): Promise<boolean>;
  }
} 