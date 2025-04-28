// src/utils/circuit-breaker.js
class CircuitBreaker {
  constructor(options = {}) {
    this.failureThreshold = options.failureThreshold || 5;
    this.resetTimeout = options.resetTimeout || 30000;
    this.failures = 0;
    this.lastFailure = 0;
    this.state = 'CLOSED';
  }
  
  async executeWithBreaker(fn) {
    if (this.isOpen()) {
      throw new Error(`Circuit breaker is open - service unavailable`);
    }
    
    try {
      const result = await fn();
      this.recordSuccess();
      return result;
    } catch (error) {
      this.recordFailure();
      throw error;
    }
  }
  
  isOpen() {
    if (this.state === 'OPEN') {
      const timeSinceLastFailure = Date.now() - this.lastFailure;
      if (timeSinceLastFailure > this.resetTimeout) {
        this.state = 'HALF_OPEN';
        return false;
      }
      return true;
    }
    return false;
  }
  
  recordSuccess() {
    this.failures = 0;
    if (this.state === 'HALF_OPEN') {
      this.state = 'CLOSED';
    }
  }
  
  recordFailure() {
    this.failures++;
    this.lastFailure = Date.now();
    if (this.failures >= this.failureThreshold || this.state === 'HALF_OPEN') {
      this.state = 'OPEN';
    }
  }
}

module.exports = CircuitBreaker; 