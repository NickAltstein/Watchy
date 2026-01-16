require('dotenv').config();
const Redis = require('ioredis');
const axios = require('axios');
const logger = require('./src/utils/logger');
const BaileysClient = require('./src/baileys/baileys-client');
const QueueManager = require('./src/queue/queue-manager');
const circuitBreaker = require('./src/utils/circuit-breaker');
const metricsCollector = require('./src/utils/metrics');
const HealthServer = require('./src/health-server');

/**
 * Production-grade WhatsApp scraper with all advanced features
 */
class WhatsAppScraperService {
  constructor() {
    this.config = this.loadConfig();
    this.redis = null;
    this.queueManager = null;
    this.baileysClient = null;
    this.healthServer = null;
    this.apiBreaker = null;
    this.isShuttingDown = false;
    this.stats = {
      startTime: Date.now(),
      messagesProcessed: 0,
      imagesSent: 0,
      apiCallsSuccess: 0,
      apiCallsFailed: 0,
    };
  }

  loadConfig() {
    return {
      // Redis configuration
      redisHost: process.env.REDIS_HOST || 'localhost',
      redisPort: parseInt(process.env.REDIS_PORT) || 6379,
      redisPassword: process.env.REDIS_PASSWORD || undefined,
      redisDb: parseInt(process.env.REDIS_DB) || 0,
      useFileAuth: process.env.USE_FILE_AUTH === 'true', // Fallback to file-based auth

      // API configuration
      pythonApiUrl: process.env.PYTHON_API_URL || 'http://localhost:8000',
      apiTimeout: parseInt(process.env.API_TIMEOUT) || 10000,
      apiMaxRetries: parseInt(process.env.API_MAX_RETRIES) || 3,

      // WhatsApp configuration
      sessionId: process.env.SESSION_ID || 'default',
      groupFilters: (process.env.WATCHED_GROUPS || '')
        .split(',')
        .map((g) => g.trim())
        .filter(Boolean),
      maxImageSizeMB: parseInt(process.env.MAX_IMAGE_SIZE_MB) || 5,
      maxReconnectAttempts: parseInt(process.env.MAX_RECONNECT_ATTEMPTS) || 10,
      reconnectInterval: parseInt(process.env.RECONNECT_INTERVAL) || 10000,

      // Queue configuration
      queueConcurrency: parseInt(process.env.QUEUE_CONCURRENCY) || 1,

      // Health server configuration
      healthPort: parseInt(process.env.HEALTH_PORT) || 3000,

      // Feature flags
      enableMetrics: process.env.ENABLE_METRICS !== 'false',
      enableHealthServer: process.env.ENABLE_HEALTH_SERVER !== 'false',
      enableQueue: process.env.ENABLE_QUEUE !== 'false',

      // Logging
      logLevel: process.env.LOG_LEVEL || 'info',
    };
  }

  async initialize() {
    logger.info('🚀 Initializing WhatsApp Scraper Service...');
    logger.info(`Configuration: ${JSON.stringify(this.config, null, 2)}`);

    try {
      // Initialize Redis (if not using file-based auth)
      if (!this.config.useFileAuth) {
        await this.initializeRedis();
      } else {
        logger.info('Using file-based authentication (Redis disabled)');
      }

      // Initialize Queue Manager (if enabled and Redis available)
      if (this.config.enableQueue && this.redis) {
        await this.initializeQueue();
      }

      // Initialize Circuit Breaker for API calls
      this.initializeCircuitBreaker();

      // Initialize Baileys Client
      await this.initializeBaileysClient();

      // Initialize Health Server (if enabled)
      if (this.config.enableHealthServer) {
        await this.initializeHealthServer();
      }

      logger.info('✅ Service initialized successfully');
    } catch (error) {
      logger.error('Failed to initialize service', { error: error.message });
      throw error;
    }
  }

  async initializeRedis() {
    try {
      this.redis = new Redis({
        host: this.config.redisHost,
        port: this.config.redisPort,
        password: this.config.redisPassword,
        db: this.config.redisDb,
        retryStrategy: (times) => {
          if (times > 10) {
            logger.error('Redis connection failed after 10 attempts');
            return null;
          }
          const delay = Math.min(times * 1000, 5000);
          logger.warn(`Retrying Redis connection in ${delay}ms...`);
          return delay;
        },
        maxRetriesPerRequest: 3,
      });

      this.redis.on('connect', () => {
        logger.info('✅ Connected to Redis');
      });

      this.redis.on('error', (error) => {
        logger.error('Redis error', { error: error.message });
      });

      this.redis.on('close', () => {
        logger.warn('Redis connection closed');
      });

      // Test connection
      await this.redis.ping();
    } catch (error) {
      logger.error('Failed to connect to Redis', { error: error.message });
      logger.warn('Falling back to file-based authentication');
      this.redis = null;
    }
  }

  async initializeQueue() {
    try {
      this.queueManager = new QueueManager({
        host: this.config.redisHost,
        port: this.config.redisPort,
        password: this.config.redisPassword,
        db: this.config.redisDb,
      });

      // Register message processing queue
      this.queueManager.registerProcessor(
        'message-processing',
        async (data) => await this.processMessage(data),
        this.config.queueConcurrency
      );

      logger.info('✅ Queue manager initialized');
    } catch (error) {
      logger.error('Failed to initialize queue', { error: error.message });
      this.queueManager = null;
    }
  }

  initializeCircuitBreaker() {
    this.apiBreaker = circuitBreaker.createBreaker(
      'python-api',
      async (data) => {
        return await this.sendToAPI(data);
      },
      {
        timeout: this.config.apiTimeout,
        errorThresholdPercentage: 50,
        resetTimeout: 30000,
      }
    );

    // Set fallback for circuit breaker
    this.apiBreaker.fallback(() => {
      logger.warn('Circuit breaker fallback triggered');
      return { status: 'circuit_open', message: 'API temporarily unavailable' };
    });
  }

  async initializeBaileysClient() {
    this.baileysClient = new BaileysClient({
      redisClient: this.redis,
      sessionId: this.config.sessionId,
      queueManager: this.queueManager,
      onMessage: async (data) => await this.processMessage(data),
      groupFilters: this.config.groupFilters,
      maxReconnectAttempts: this.config.maxReconnectAttempts,
      reconnectInterval: this.config.reconnectInterval,
      maxImageSizeMB: this.config.maxImageSizeMB,
    });

    await this.baileysClient.connect();
  }

  async initializeHealthServer() {
    this.healthServer = new HealthServer(this.config.healthPort);

    // Register health checks
    this.healthServer.registerHealthCheck('whatsapp', async () => {
      const status = this.baileysClient.getStatus();
      return {
        healthy: status.connected,
        ...status,
      };
    });

    this.healthServer.registerHealthCheck('redis', async () => {
      if (!this.redis) {
        return { healthy: true, message: 'Redis disabled (file-based auth)' };
      }
      try {
        await this.redis.ping();
        return { healthy: true };
      } catch (error) {
        return { healthy: false, error: error.message };
      }
    });

    this.healthServer.registerHealthCheck('api', async () => {
      const stats = circuitBreaker.getStats('python-api');
      return {
        healthy: stats.state === 'CLOSED',
        ...stats,
      };
    });

    // Override stats method
    this.healthServer.getStats = async () => {
      const queueStats = this.queueManager
        ? await this.queueManager.getAllStats()
        : [];

      return {
        uptime: Math.floor((Date.now() - this.stats.startTime) / 1000),
        stats: this.stats,
        whatsapp: this.baileysClient.getStatus(),
        queues: queueStats,
        circuitBreakers: circuitBreaker.getAllStats(),
      };
    };

    await this.healthServer.start();
  }

  async processMessage(messageData) {
    const startTime = Date.now();

    try {
      logger.info('Processing message', {
        messageId: messageData.messageId,
        group: messageData.groupName,
        hasImage: messageData.hasImage,
      });

      // Send to API via circuit breaker
      const result = await this.apiBreaker.fire(messageData);

      const duration = (Date.now() - startTime) / 1000;
      metricsCollector.recordAPILatency('/parse-watch', duration);

      if (result.status === 'circuit_open') {
        metricsCollector.recordAPICall('/parse-watch', 'circuit_open');
        this.stats.apiCallsFailed++;
        return;
      }

      this.stats.messagesProcessed++;
      this.stats.apiCallsSuccess++;

      if (messageData.hasImage) {
        this.stats.imagesSent++;
      }

      metricsCollector.recordAPICall('/parse-watch', 'success');

      logger.info('Message processed successfully', {
        messageId: messageData.messageId,
        duration: `${duration.toFixed(2)}s`,
      });
    } catch (error) {
      logger.error('Failed to process message', {
        error: error.message,
        messageId: messageData.messageId,
      });
      this.stats.apiCallsFailed++;
      metricsCollector.recordAPICall('/parse-watch', 'failed');
      metricsCollector.recordMessageFailed('api_error');
      throw error;
    }
  }

  async sendToAPI(data) {
    const response = await axios.post(`${this.config.pythonApiUrl}/parse-watch`, data, {
      timeout: this.config.apiTimeout,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'WhatsAppScraper/10.2.0',
      },
    });

    return response.data;
  }

  async shutdown() {
    if (this.isShuttingDown) {
      logger.info('Shutdown already in progress...');
      return;
    }

    this.isShuttingDown = true;
    logger.info('🛑 Shutting down gracefully...');

    try {
      // Disconnect WhatsApp client
      if (this.baileysClient) {
        await this.baileysClient.disconnect();
      }

      // Close queue manager
      if (this.queueManager) {
        await this.queueManager.closeAll();
      }

      // Close Redis connection
      if (this.redis) {
        await this.redis.quit();
      }

      // Stop health server
      if (this.healthServer) {
        await this.healthServer.stop();
      }

      // Shutdown circuit breakers
      circuitBreaker.shutdown();

      logger.info('👋 Shutdown complete');
      process.exit(0);
    } catch (error) {
      logger.error('Error during shutdown', { error: error.message });
      process.exit(1);
    }
  }
}

// Main execution
(async () => {
  const service = new WhatsAppScraperService();

  // Graceful shutdown handlers
  const shutdown = () => service.shutdown();
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
  process.on('SIGHUP', shutdown);

  // Error handlers
  process.on('uncaughtException', (error) => {
    logger.error('Uncaught exception', { error: error.message, stack: error.stack });
  });

  process.on('unhandledRejection', (reason) => {
    logger.error('Unhandled rejection', { reason });
  });

  try {
    await service.initialize();
  } catch (error) {
    logger.error('Failed to start service', { error: error.message });
    process.exit(1);
  }
})();

module.exports = WhatsAppScraperService;
