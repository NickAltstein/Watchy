const axios = require('axios');
const Bottleneck = require('bottleneck');
const logger = require('../utils/logger');
const metricsCollector = require('../utils/metrics');
const circuitBreaker = require('../utils/circuit-breaker');

/**
 * Priority levels for message processing
 */
const Priority = {
  HIGH: 1,    // Messages with images
  MEDIUM: 5,  // Text from known dealers
  LOW: 10,    // Messages from unknown senders
};

/**
 * High-throughput message processor with priority queue
 */
class MessageProcessor {
  constructor(config = {}) {
    this.config = {
      apiUrl: config.apiUrl || 'http://localhost:8000',
      apiKey: config.apiKey || process.env.API_KEY,
      apiTimeout: config.apiTimeout || 10000,
      maxRetries: config.maxRetries || 3,
      rateLimitPerSecond: config.rateLimitPerSecond || 20,
      batchSize: config.batchSize || 10,
      knownDealers: config.knownDealers || [],
      ...config,
    };

    // Rate limiter: 20 requests per second
    this.limiter = new Bottleneck({
      reservoir: this.config.rateLimitPerSecond,
      reservoirRefreshAmount: this.config.rateLimitPerSecond,
      reservoirRefreshInterval: 1000,
      maxConcurrent: 10,
      minTime: 50, // 50ms between requests = 20 req/sec
    });

    // Circuit breaker for API calls
    this.apiBreaker = circuitBreaker.createBreaker(
      'parse-watch-api',
      async (data) => await this.callAPI(data),
      {
        timeout: this.config.apiTimeout,
        errorThresholdPercentage: 50,
        resetTimeout: 30000,
      }
    );

    // Set fallback for circuit breaker
    this.apiBreaker.fallback(() => {
      logger.warn('Circuit breaker fallback: API unavailable');
      return { status: 'circuit_open', message: 'API temporarily unavailable' };
    });

    // Processing stats
    this.stats = {
      totalProcessed: 0,
      successCount: 0,
      failureCount: 0,
      circuitOpenCount: 0,
      totalLatency: 0,
      avgLatency: 0,
      batchesProcessed: 0,
      startTime: Date.now(),
    };

    // Alert thresholds
    this.alertThresholds = {
      queueDepth: 5000,
      successRate: 0.95,
    };
  }

  /**
   * Determine priority based on message characteristics
   */
  determinePriority(messageData) {
    // HIGH: Messages with images (more valuable)
    if (messageData.hasImage && messageData.imageBase64) {
      return Priority.HIGH;
    }

    // MEDIUM: Text from known dealers
    if (this.isKnownDealer(messageData.senderId)) {
      return Priority.MEDIUM;
    }

    // LOW: Messages from unknown senders
    return Priority.LOW;
  }

  /**
   * Check if sender is a known dealer
   */
  isKnownDealer(senderId) {
    return this.config.knownDealers.some((dealer) => 
      senderId.includes(dealer) || senderId === dealer
    );
  }

  /**
   * Process a single message
   */
  async processMessage(messageData, job) {
    const startTime = Date.now();

    try {
      logger.info('Processing message', {
        jobId: job.id,
        messageId: messageData.messageId,
        priority: job.opts.priority,
        hasImage: messageData.hasImage,
      });

      // Call API with rate limiting and circuit breaker
      const result = await this.limiter.schedule(() => 
        this.apiBreaker.fire(messageData)
      );

      const latency = Date.now() - startTime;
      this.updateStats(true, latency);

      // Handle circuit breaker response
      if (result.status === 'circuit_open') {
        this.stats.circuitOpenCount++;
        metricsCollector.recordAPICall('/parse-watch', 'circuit_open');
        throw new Error('Circuit breaker open - API unavailable');
      }

      // Track success
      metricsCollector.recordAPICall('/parse-watch', 'success');
      metricsCollector.recordAPILatency('/parse-watch', latency / 1000);

      logger.info('Message processed successfully', {
        jobId: job.id,
        messageId: messageData.messageId,
        latency: `${latency}ms`,
        status: result.status,
      });

      // Check for alerts
      this.checkAlerts();

      return result;
    } catch (error) {
      const latency = Date.now() - startTime;
      this.updateStats(false, latency);

      metricsCollector.recordAPICall('/parse-watch', 'failed');
      metricsCollector.recordMessageFailed('api_error');

      logger.error('Failed to process message', {
        jobId: job.id,
        messageId: messageData.messageId,
        error: error.message,
        latency: `${latency}ms`,
      });

      throw error;
    }
  }

  /**
   * Process messages in batch
   */
  async processBatch(messages, job) {
    const startTime = Date.now();

    try {
      logger.info('Processing message batch', {
        jobId: job.id,
        batchSize: messages.length,
      });

      // Process messages in parallel with rate limiting
      const results = await Promise.allSettled(
        messages.map((msg) => 
          this.limiter.schedule(() => this.apiBreaker.fire(msg))
        )
      );

      const latency = Date.now() - startTime;
      
      // Count successes and failures
      const successes = results.filter((r) => r.status === 'fulfilled').length;
      const failures = results.filter((r) => r.status === 'rejected').length;

      this.stats.batchesProcessed++;
      this.updateStats(true, latency, successes);
      
      if (failures > 0) {
        this.updateStats(false, 0, failures);
      }

      logger.info('Batch processed', {
        jobId: job.id,
        total: messages.length,
        successes,
        failures,
        latency: `${latency}ms`,
      });

      return {
        total: messages.length,
        successes,
        failures,
        results,
      };
    } catch (error) {
      logger.error('Batch processing failed', {
        jobId: job.id,
        error: error.message,
      });
      throw error;
    }
  }

  /**
   * Call the Python FastAPI endpoint
   */
  async callAPI(messageData) {
    const response = await axios.post(
      `${this.config.apiUrl}/parse-watch`,
      messageData,
      {
        timeout: this.config.apiTimeout,
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': this.config.apiKey || '',
          'User-Agent': 'Watchy-MessageProcessor/1.0',
        },
        validateStatus: (status) => status < 500,
      }
    );

    return response.data;
  }

  /**
   * Update processing statistics
   */
  updateStats(success, latency, count = 1) {
    this.stats.totalProcessed += count;
    
    if (success) {
      this.stats.successCount += count;
    } else {
      this.stats.failureCount += count;
    }

    this.stats.totalLatency += latency;
    this.stats.avgLatency = this.stats.totalLatency / this.stats.totalProcessed;
  }

  /**
   * Get success rate
   */
  getSuccessRate() {
    if (this.stats.totalProcessed === 0) return 1.0;
    return this.stats.successCount / this.stats.totalProcessed;
  }

  /**
   * Check alert conditions
   */
  checkAlerts() {
    const successRate = this.getSuccessRate();

    // Alert if success rate < 95%
    if (successRate < this.alertThresholds.successRate) {
      logger.warn('⚠️ ALERT: Success rate below threshold', {
        current: (successRate * 100).toFixed(2) + '%',
        threshold: (this.alertThresholds.successRate * 100) + '%',
        failures: this.stats.failureCount,
        total: this.stats.totalProcessed,
      });
    }
  }

  /**
   * Get processing statistics
   */
  getStats() {
    const uptime = Date.now() - this.stats.startTime;
    const successRate = this.getSuccessRate();
    const messagesPerMinute = (this.stats.totalProcessed / uptime) * 60000;

    return {
      ...this.stats,
      successRate: (successRate * 100).toFixed(2) + '%',
      avgLatency: Math.round(this.stats.avgLatency) + 'ms',
      uptime: Math.floor(uptime / 1000) + 's',
      messagesPerMinute: Math.round(messagesPerMinute),
      rateLimitStatus: this.limiter.counts(),
      circuitBreakerStatus: circuitBreaker.getStats('parse-watch-api'),
    };
  }

  /**
   * Reset statistics
   */
  resetStats() {
    this.stats = {
      totalProcessed: 0,
      successCount: 0,
      failureCount: 0,
      circuitOpenCount: 0,
      totalLatency: 0,
      avgLatency: 0,
      batchesProcessed: 0,
      startTime: Date.now(),
    };
    logger.info('Statistics reset');
  }
}

module.exports = { MessageProcessor, Priority };
