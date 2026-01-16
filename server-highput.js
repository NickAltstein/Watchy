require('dotenv').config();
const Redis = require('ioredis');
const express = require('express');
const logger = require('./src/utils/logger');
const BaileysClient = require('./src/baileys/baileys-client');
const QueueManager = require('./src/queue/queue-manager');
const { MessageProcessor, Priority } = require('./src/queue/message-processor');
const QueueAdminAPI = require('./src/queue/admin-api');
const metricsCollector = require('./src/utils/metrics');
const HealthServer = require('./src/health-server');

/**
 * High-throughput message processing service
 * Handles 1000+ messages/minute with priority queuing
 */
class HighThroughputService {
  constructor() {
    this.config = this.loadConfig();
    this.redis = null;
    this.queueManager = null;
    this.messageProcessor = null;
    this.baileysClient = null;
    this.healthServer = null;
    this.adminApp = null;
    this.isShuttingDown = false;
  }

  loadConfig() {
    return {
      // Redis configuration
      redisHost: process.env.REDIS_HOST || 'localhost',
      redisPort: parseInt(process.env.REDIS_PORT) || 6379,
      redisPassword: process.env.REDIS_PASSWORD || undefined,
      redisDb: parseInt(process.env.REDIS_DB) || 0,

      // API configuration
      pythonApiUrl: process.env.PYTHON_API_URL || 'http://localhost:8000',
      apiKey: process.env.API_KEY || '',
      apiTimeout: parseInt(process.env.API_TIMEOUT) || 10000,

      // Queue configuration
      queueConcurrency: parseInt(process.env.QUEUE_CONCURRENCY) || 10,
      rateLimitPerSecond: parseInt(process.env.RATE_LIMIT_PER_SECOND) || 20,
      queueCapacityAlert: parseInt(process.env.QUEUE_CAPACITY_ALERT) || 5000,

      // WhatsApp configuration
      sessionId: process.env.SESSION_ID || 'default',
      groupFilters: (process.env.WATCHED_GROUPS || '')
        .split(',')
        .map((g) => g.trim())
        .filter(Boolean),
      maxImageSizeMB: parseInt(process.env.MAX_IMAGE_SIZE_MB) || 5,

      // Known dealers (for priority routing)
      knownDealers: (process.env.KNOWN_DEALERS || '')
        .split(',')
        .map((d) => d.trim())
        .filter(Boolean),

      // Server ports
      healthPort: parseInt(process.env.HEALTH_PORT) || 3000,
      adminPort: parseInt(process.env.ADMIN_PORT) || 3001,

      // Feature flags
      enableBatchProcessing: process.env.ENABLE_BATCH_PROCESSING === 'true',
      batchSize: parseInt(process.env.BATCH_SIZE) || 10,
      batchTimeout: parseInt(process.env.BATCH_TIMEOUT) || 5000,
    };
  }

  async initialize() {
    logger.info('🚀 Initializing High-Throughput Service...');
    logger.info(`Configuration: Queue Concurrency=${this.config.queueConcurrency}, Rate Limit=${this.config.rateLimitPerSecond}/s`);

    try {
      // Initialize Redis
      await this.initializeRedis();

      // Initialize Queue Manager
      await this.initializeQueueManager();

      // Initialize Message Processor
      await this.initializeMessageProcessor();

      // Initialize Baileys Client
      await this.initializeBaileysClient();

      // Initialize Health Server
      if (this.config.healthPort) {
        await this.initializeHealthServer();
      }

      // Initialize Admin API
      if (this.config.adminPort) {
        await this.initializeAdminAPI();
      }

      logger.info('✅ Service initialized successfully');
      this.logConfiguration();
    } catch (error) {
      logger.error('Failed to initialize service', { error: error.message });
      throw error;
    }
  }

  async initializeRedis() {
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
        return delay;
      },
    });

    this.redis.on('connect', () => logger.info('✅ Connected to Redis'));
    this.redis.on('error', (error) => logger.error('Redis error', { error: error.message }));

    await this.redis.ping();
  }

  async initializeQueueManager() {
    this.queueManager = new QueueManager({
      host: this.config.redisHost,
      port: this.config.redisPort,
      password: this.config.redisPassword,
      db: this.config.redisDb,
    });

    // Register message processing queue with 10 concurrent workers
    this.queueManager.registerProcessor(
      'message-processing',
      async (data, job) => {
        if (Array.isArray(data)) {
          // Batch processing
          return await this.messageProcessor.processBatch(data, job);
        } else {
          // Single message processing
          return await this.messageProcessor.processMessage(data, job);
        }
      },
      this.config.queueConcurrency
    );

    logger.info(`✅ Queue manager initialized with ${this.config.queueConcurrency} workers`);
  }

  async initializeMessageProcessor() {
    this.messageProcessor = new MessageProcessor({
      apiUrl: this.config.pythonApiUrl,
      apiKey: this.config.apiKey,
      apiTimeout: this.config.apiTimeout,
      rateLimitPerSecond: this.config.rateLimitPerSecond,
      batchSize: this.config.batchSize,
      knownDealers: this.config.knownDealers,
    });

    logger.info('✅ Message processor initialized');
  }

  async initializeBaileysClient() {
    this.baileysClient = new BaileysClient({
      redisClient: this.redis,
      sessionId: this.config.sessionId,
      queueManager: this.queueManager,
      onMessage: async (data) => await this.handleMessage(data),
      groupFilters: this.config.groupFilters,
      maxImageSizeMB: this.config.maxImageSizeMB,
    });

    await this.baileysClient.connect();
  }

  async handleMessage(messageData) {
    try {
      // Determine priority
      const priority = this.messageProcessor.determinePriority(messageData);

      // Check queue capacity
      const isOverCapacity = await this.queueManager.isQueueOverCapacity(
        'message-processing',
        this.config.queueCapacityAlert
      );

      if (isOverCapacity) {
        logger.warn('⚠️ Queue over capacity threshold', {
          threshold: this.config.queueCapacityAlert,
        });
      }

      // Add to queue with priority
      await this.queueManager.addJob('message-processing', messageData, {
        priority,
        attempts: 3,
        backoff: { type: 'exponential', delay: 2000 },
      });

      logger.debug('Message queued', {
        messageId: messageData.messageId,
        priority: priority === Priority.HIGH ? 'HIGH' : priority === Priority.MEDIUM ? 'MEDIUM' : 'LOW',
        hasImage: messageData.hasImage,
      });
    } catch (error) {
      logger.error('Failed to queue message', {
        error: error.message,
        messageId: messageData.messageId,
      });
    }
  }

  async initializeHealthServer() {
    this.healthServer = new HealthServer(this.config.healthPort);

    // Register health checks
    this.healthServer.registerHealthCheck('whatsapp', async () => {
      const status = this.baileysClient.getStatus();
      return { healthy: status.connected, ...status };
    });

    this.healthServer.registerHealthCheck('redis', async () => {
      try {
        await this.redis.ping();
        return { healthy: true };
      } catch (error) {
        return { healthy: false, error: error.message };
      }
    });

    this.healthServer.registerHealthCheck('queue', async () => {
      const stats = await this.queueManager.getQueueStats('message-processing');
      const isHealthy = stats ? stats.waiting + stats.delayed < 10000 : false;
      return { healthy: isHealthy, ...stats };
    });

    this.healthServer.registerHealthCheck('processor', () => {
      const stats = this.messageProcessor.getStats();
      const successRate = parseFloat(stats.successRate) / 100;
      return {
        healthy: successRate >= 0.90,
        successRate: stats.successRate,
        avgLatency: stats.avgLatency,
      };
    });

    // Override stats method
    this.healthServer.getStats = async () => {
      const queueStats = await this.queueManager.getAllStats();
      const processorStats = this.messageProcessor.getStats();

      return {
        uptime: process.uptime(),
        whatsapp: this.baileysClient.getStatus(),
        queues: queueStats,
        processor: processorStats,
        memory: process.memoryUsage(),
      };
    };

    await this.healthServer.start();
  }

  async initializeAdminAPI() {
    this.adminApp = express();
    this.adminApp.use(express.json());

    // Setup admin routes
    const adminAPI = new QueueAdminAPI(this.queueManager, this.messageProcessor);
    this.adminApp.use('/api/admin', adminAPI.getRouter());

    // Start admin server
    this.adminServer = this.adminApp.listen(this.config.adminPort, () => {
      logger.info(`✅ Admin API listening on port ${this.config.adminPort}`);
      logger.info(`Admin endpoints: http://localhost:${this.config.adminPort}/api/admin`);
    });
  }

  logConfiguration() {
    console.log('\n' + '='.repeat(60));
    console.log('🎯 HIGH-THROUGHPUT SERVICE CONFIGURATION');
    console.log('='.repeat(60));
    console.log(`Queue Workers:     ${this.config.queueConcurrency}`);
    console.log(`Rate Limit:        ${this.config.rateLimitPerSecond} req/sec`);
    console.log(`Queue Alert:       ${this.config.queueCapacityAlert} messages`);
    console.log(`Groups Monitored:  ${this.baileysClient.groupCache.size}`);
    console.log(`Known Dealers:     ${this.config.knownDealers.length}`);
    console.log(`Health Port:       ${this.config.healthPort}`);
    console.log(`Admin Port:        ${this.config.adminPort}`);
    console.log('='.repeat(60));
    console.log('\n📊 Endpoints:');
    console.log(`  Health:    http://localhost:${this.config.healthPort}/health`);
    console.log(`  Metrics:   http://localhost:${this.config.healthPort}/metrics`);
    console.log(`  Stats:     http://localhost:${this.config.healthPort}/stats`);
    console.log(`  Admin:     http://localhost:${this.config.adminPort}/api/admin/queues/stats`);
    console.log(`  Alerts:    http://localhost:${this.config.adminPort}/api/admin/alerts`);
    console.log('='.repeat(60) + '\n');
  }

  async shutdown() {
    if (this.isShuttingDown) return;

    this.isShuttingDown = true;
    logger.info('🛑 Shutting down gracefully...');

    try {
      // Disconnect WhatsApp
      if (this.baileysClient) {
        await this.baileysClient.disconnect();
      }

      // Close queues
      if (this.queueManager) {
        await this.queueManager.closeAll();
      }

      // Close Redis
      if (this.redis) {
        await this.redis.quit();
      }

      // Stop servers
      if (this.healthServer) {
        await this.healthServer.stop();
      }

      if (this.adminServer) {
        await new Promise((resolve) => this.adminServer.close(resolve));
      }

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
  const service = new HighThroughputService();

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

module.exports = HighThroughputService;
