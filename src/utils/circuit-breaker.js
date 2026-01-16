const CircuitBreaker = require('opossum');
const logger = require('./logger');

class CircuitBreakerFactory {
  constructor() {
    this.breakers = new Map();
  }

  createBreaker(name, action, options = {}) {
    if (this.breakers.has(name)) {
      return this.breakers.get(name);
    }

    const defaultOptions = {
      timeout: 10000,
      errorThresholdPercentage: 50,
      resetTimeout: 30000,
      rollingCountTimeout: 10000,
      rollingCountBuckets: 10,
      name,
      ...options,
    };

    const breaker = new CircuitBreaker(action, defaultOptions);
    this.setupBreakerEvents(breaker, name);
    this.breakers.set(name, breaker);
    logger.info(`Circuit breaker created: ${name}`);

    return breaker;
  }

  setupBreakerEvents(breaker, name) {
    breaker.on('open', () => {
      logger.warn(`Circuit breaker OPEN: ${name}`);
    });

    breaker.on('halfOpen', () => {
      logger.info(`Circuit breaker HALF-OPEN: ${name}`);
    });

    breaker.on('close', () => {
      logger.info(`Circuit breaker CLOSED: ${name}`);
    });

    breaker.on('failure', (error) => {
      logger.debug(`Circuit breaker failure: ${name}`, { error: error.message });
    });

    breaker.on('timeout', () => {
      logger.warn(`Circuit breaker timeout: ${name}`);
    });

    breaker.on('reject', () => {
      logger.warn(`Circuit breaker rejected request: ${name}`);
    });
  }

  getStats(name) {
    const breaker = this.breakers.get(name);
    if (!breaker) return null;

    const stats = breaker.stats;
    return {
      name,
      state: breaker.opened ? 'OPEN' : breaker.halfOpen ? 'HALF-OPEN' : 'CLOSED',
      failures: stats.failures,
      successes: stats.successes,
      timeouts: stats.timeouts,
      rejects: stats.rejects,
      fires: stats.fires,
      fallbacks: stats.fallbacks,
      latencyMean: stats.latencyMean,
    };
  }

  getAllStats() {
    const stats = [];
    for (const name of this.breakers.keys()) {
      const breakerStats = this.getStats(name);
      if (breakerStats) stats.push(breakerStats);
    }
    return stats;
  }

  reset(name) {
    const breaker = this.breakers.get(name);
    if (breaker) {
      breaker.close();
      logger.info(`Circuit breaker reset: ${name}`);
    }
  }

  shutdown() {
    logger.info('Shutting down all circuit breakers');
    for (const breaker of this.breakers.values()) {
      breaker.shutdown();
    }
    this.breakers.clear();
  }
}

const breakerFactory = new CircuitBreakerFactory();
module.exports = breakerFactory;
