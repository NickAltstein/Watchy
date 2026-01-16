const express = require('express');
const logger = require('../utils/logger');

/**
 * Admin API for queue management
 * Provides endpoints to control and monitor queues
 */
class QueueAdminAPI {
  constructor(queueManager, messageProcessor) {
    this.queueManager = queueManager;
    this.messageProcessor = messageProcessor;
    this.router = express.Router();
    this.setupRoutes();
  }

  setupRoutes() {
    // Get queue statistics
    this.router.get('/queues/stats', async (req, res) => {
      try {
        const stats = await this.queueManager.getAllStats();
        const processorStats = this.messageProcessor.getStats();

        res.json({
          queues: stats,
          processor: processorStats,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        logger.error('Failed to get queue stats', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Get specific queue statistics
    this.router.get('/queues/:queueName/stats', async (req, res) => {
      try {
        const { queueName } = req.params;
        const stats = await this.queueManager.getQueueStats(queueName);

        if (!stats) {
          return res.status(404).json({ error: 'Queue not found' });
        }

        res.json(stats);
      } catch (error) {
        logger.error('Failed to get queue stats', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Pause a queue
    this.router.post('/queues/:queueName/pause', async (req, res) => {
      try {
        const { queueName } = req.params;
        await this.queueManager.pauseQueue(queueName);
        logger.info(`Queue paused via admin API: ${queueName}`);

        res.json({
          success: true,
          message: `Queue ${queueName} paused`,
        });
      } catch (error) {
        logger.error('Failed to pause queue', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Resume a queue
    this.router.post('/queues/:queueName/resume', async (req, res) => {
      try {
        const { queueName } = req.params;
        await this.queueManager.resumeQueue(queueName);
        logger.info(`Queue resumed via admin API: ${queueName}`);

        res.json({
          success: true,
          message: `Queue ${queueName} resumed`,
        });
      } catch (error) {
        logger.error('Failed to resume queue', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Clear completed jobs from queue
    this.router.post('/queues/:queueName/clear', async (req, res) => {
      try {
        const { queueName } = req.params;
        const { status } = req.body; // 'completed', 'failed', 'delayed', 'active', 'waiting'

        const queue = this.queueManager.queues.get(queueName);
        if (!queue) {
          return res.status(404).json({ error: 'Queue not found' });
        }

        let count = 0;
        switch (status) {
          case 'completed':
            count = await queue.clean(0, 'completed');
            break;
          case 'failed':
            count = await queue.clean(0, 'failed');
            break;
          case 'delayed':
            count = await queue.clean(0, 'delayed');
            break;
          case 'active':
            count = await queue.clean(0, 'active');
            break;
          case 'waiting':
            count = await queue.clean(0, 'wait');
            break;
          default:
            return res.status(400).json({ 
              error: 'Invalid status. Use: completed, failed, delayed, active, waiting' 
            });
        }

        logger.info(`Cleared ${count} ${status} jobs from ${queueName}`);

        res.json({
          success: true,
          message: `Cleared ${count} ${status} jobs from ${queueName}`,
          count,
        });
      } catch (error) {
        logger.error('Failed to clear queue', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Get failed jobs from queue
    this.router.get('/queues/:queueName/failed', async (req, res) => {
      try {
        const { queueName } = req.params;
        const { start = 0, end = 10 } = req.query;

        const queue = this.queueManager.queues.get(queueName);
        if (!queue) {
          return res.status(404).json({ error: 'Queue not found' });
        }

        const failedJobs = await queue.getFailed(parseInt(start), parseInt(end));
        
        const jobs = failedJobs.map((job) => ({
          id: job.id,
          data: job.data,
          failedReason: job.failedReason,
          attemptsMade: job.attemptsMade,
          timestamp: job.timestamp,
          processedOn: job.processedOn,
          finishedOn: job.finishedOn,
        }));

        res.json({
          queue: queueName,
          failed: jobs,
          count: jobs.length,
        });
      } catch (error) {
        logger.error('Failed to get failed jobs', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Retry failed jobs
    this.router.post('/queues/:queueName/retry-failed', async (req, res) => {
      try {
        const { queueName } = req.params;
        const { jobId } = req.body;

        const queue = this.queueManager.queues.get(queueName);
        if (!queue) {
          return res.status(404).json({ error: 'Queue not found' });
        }

        if (jobId) {
          // Retry specific job
          const job = await queue.getJob(jobId);
          if (!job) {
            return res.status(404).json({ error: 'Job not found' });
          }
          await job.retry();
          logger.info(`Retrying job ${jobId} in ${queueName}`);
          res.json({ success: true, message: `Job ${jobId} queued for retry` });
        } else {
          // Retry all failed jobs
          const failedJobs = await queue.getFailed();
          const retried = [];

          for (const job of failedJobs) {
            await job.retry();
            retried.push(job.id);
          }

          logger.info(`Retrying ${retried.length} failed jobs in ${queueName}`);
          res.json({
            success: true,
            message: `${retried.length} failed jobs queued for retry`,
            count: retried.length,
          });
        }
      } catch (error) {
        logger.error('Failed to retry jobs', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Get processor statistics
    this.router.get('/processor/stats', (req, res) => {
      try {
        const stats = this.messageProcessor.getStats();
        res.json(stats);
      } catch (error) {
        logger.error('Failed to get processor stats', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Reset processor statistics
    this.router.post('/processor/reset-stats', (req, res) => {
      try {
        this.messageProcessor.resetStats();
        res.json({
          success: true,
          message: 'Processor statistics reset',
        });
      } catch (error) {
        logger.error('Failed to reset processor stats', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Get queue alerts
    this.router.get('/alerts', async (req, res) => {
      try {
        const alerts = [];
        const stats = await this.queueManager.getAllStats();
        const processorStats = this.messageProcessor.getStats();

        // Check queue depth
        for (const queueStat of stats) {
          const totalPending = queueStat.waiting + queueStat.delayed;
          if (totalPending > 5000) {
            alerts.push({
              type: 'queue_depth',
              severity: 'warning',
              queue: queueStat.name,
              message: `Queue depth exceeds 5000 messages`,
              value: totalPending,
              threshold: 5000,
            });
          }
        }

        // Check success rate
        const successRate = parseFloat(processorStats.successRate) / 100;
        if (successRate < 0.95) {
          alerts.push({
            type: 'success_rate',
            severity: 'critical',
            message: `Success rate below 95%`,
            value: processorStats.successRate,
            threshold: '95%',
          });
        }

        // Check circuit breaker status
        if (processorStats.circuitBreakerStatus?.state === 'OPEN') {
          alerts.push({
            type: 'circuit_breaker',
            severity: 'critical',
            message: 'Circuit breaker is OPEN - API unavailable',
            state: processorStats.circuitBreakerStatus.state,
          });
        }

        res.json({
          alerts,
          count: alerts.length,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        logger.error('Failed to get alerts', { error: error.message });
        res.status(500).json({ error: error.message });
      }
    });

    // Health check for admin API
    this.router.get('/health', (req, res) => {
      res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
      });
    });
  }

  getRouter() {
    return this.router;
  }
}

module.exports = QueueAdminAPI;
