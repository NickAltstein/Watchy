const Queue = require('bull');
const logger = require('../utils/logger');

class QueueManager {
  constructor(redisConfig) {
    this.redisConfig = redisConfig;
    this.queues = new Map();
    this.processors = new Map();
  }

  getQueue(queueName, options = {}) {
    if (this.queues.has(queueName)) {
      return this.queues.get(queueName);
    }

    const defaultOptions = {
      redis: this.redisConfig,
      defaultJobOptions: {
        attempts: 3,
        backoff: { type: 'exponential', delay: 2000 },
        removeOnComplete: 100,
        removeOnFail: 500,
      },
      ...options,
    };

    const queue = new Queue(queueName, defaultOptions);
    this.setupQueueEvents(queue, queueName);
    this.queues.set(queueName, queue);
    logger.info(`Queue created: ${queueName}`);

    return queue;
  }

  setupQueueEvents(queue, queueName) {
    queue.on('error', (error) => {
      logger.error(`Queue ${queueName} error`, { error: error.message });
    });

    queue.on('failed', (job, err) => {
      logger.error(`Job ${job.id} failed in ${queueName}`, {
        jobId: job.id,
        attempts: job.attemptsMade,
        error: err.message,
      });

      if (job.attemptsMade >= job.opts.attempts) {
        this.moveToDeadLetterQueue(queueName, job, err);
      }
    });

    queue.on('completed', (job) => {
      logger.debug(`Job ${job.id} completed in ${queueName}`);
    });

    queue.on('stalled', (job) => {
      logger.warn(`Job ${job.id} stalled in ${queueName}`);
    });
  }

  async moveToDeadLetterQueue(queueName, job, error) {
    try {
      const dlqName = `${queueName}-dlq`;
      const dlq = this.getQueue(dlqName);

      await dlq.add('failed-job', {
        originalQueue: queueName,
        originalJobId: job.id,
        failedAt: Date.now(),
        error: error.message,
        stack: error.stack,
        data: job.data,
        attempts: job.attemptsMade,
      }, { attempts: 1, removeOnComplete: false });

      logger.warn(`Job ${job.id} moved to DLQ: ${dlqName}`);
    } catch (err) {
      logger.error('Failed to move job to DLQ', { error: err.message });
    }
  }

  registerProcessor(queueName, processor, concurrency = 1) {
    const queue = this.getQueue(queueName);

    queue.process(concurrency, async (job) => {
      try {
        logger.debug(`Processing job ${job.id} from ${queueName}`);
        const result = await processor(job.data, job);
        return result;
      } catch (error) {
        logger.error(`Error processing job ${job.id}`, {
          error: error.message,
          stack: error.stack,
        });
        throw error;
      }
    });

    this.processors.set(queueName, processor);
    logger.info(`Processor registered for ${queueName} (concurrency: ${concurrency})`);
  }

  async addJob(queueName, data, options = {}) {
    const queue = this.getQueue(queueName);
    const job = await queue.add(data, options);
    logger.debug(`Job ${job.id} added to ${queueName}`);
    return job;
  }

  async getQueueStats(queueName) {
    const queue = this.queues.get(queueName);
    if (!queue) return null;

    const [waiting, active, completed, failed, delayed] = await Promise.all([
      queue.getWaitingCount(),
      queue.getActiveCount(),
      queue.getCompletedCount(),
      queue.getFailedCount(),
      queue.getDelayedCount(),
    ]);

    return {
      name: queueName,
      waiting,
      active,
      completed,
      failed,
      delayed,
      total: waiting + active + completed + failed + delayed,
    };
  }

  async getAllStats() {
    const stats = [];
    for (const queueName of this.queues.keys()) {
      const queueStats = await this.getQueueStats(queueName);
      if (queueStats) stats.push(queueStats);
    }
    return stats;
  }

  async pauseQueue(queueName) {
    const queue = this.queues.get(queueName);
    if (queue) {
      await queue.pause();
      logger.info(`Queue paused: ${queueName}`);
    }
  }

  async resumeQueue(queueName) {
    const queue = this.queues.get(queueName);
    if (queue) {
      await queue.resume();
      logger.info(`Queue resumed: ${queueName}`);
    }
  }

  async closeAll() {
    logger.info('Closing all queues...');
    const closePromises = Array.from(this.queues.values()).map((queue) => queue.close());
    await Promise.all(closePromises);
    logger.info('All queues closed');
  }
}

module.exports = QueueManager;
