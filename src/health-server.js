const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const compression = require('compression');
const logger = require('./utils/logger');
const metricsCollector = require('./utils/metrics');

class HealthServer {
  constructor(port = 3000) {
    this.port = port;
    this.app = express();
    this.server = null;
    this.healthChecks = new Map();
    
    this.setupMiddleware();
    this.setupRoutes();
  }

  setupMiddleware() {
    this.app.use(helmet());
    this.app.use(cors());
    this.app.use(compression());
    this.app.use(express.json());
  }

  setupRoutes() {
    this.app.get('/health', async (req, res) => {
      try {
        const checks = {};
        let overallHealthy = true;

        for (const [name, checkFn] of this.healthChecks.entries()) {
          try {
            const result = await checkFn();
            checks[name] = result;
            if (!result.healthy) overallHealthy = false;
          } catch (error) {
            checks[name] = { healthy: false, error: error.message };
            overallHealthy = false;
          }
        }

        const status = overallHealthy ? 200 : 503;
        res.status(status).json({
          status: overallHealthy ? 'healthy' : 'unhealthy',
          timestamp: new Date().toISOString(),
          checks,
        });
      } catch (error) {
        res.status(500).json({ status: 'error', error: error.message });
      }
    });

    this.app.get('/ready', async (req, res) => {
      try {
        const ready = await this.checkReadiness();
        res.status(ready ? 200 : 503).json({ ready, timestamp: new Date().toISOString() });
      } catch (error) {
        res.status(503).json({ ready: false, error: error.message });
      }
    });

    this.app.get('/live', (req, res) => {
      res.status(200).json({ alive: true, timestamp: new Date().toISOString() });
    });

    this.app.get('/metrics', async (req, res) => {
      try {
        const metrics = await metricsCollector.getMetrics();
        res.set('Content-Type', metricsCollector.register.contentType);
        res.send(metrics);
      } catch (error) {
        res.status(500).json({ error: error.message });
      }
    });

    this.app.get('/metrics/json', async (req, res) => {
      try {
        const metrics = await metricsCollector.getMetricsJSON();
        res.json(metrics);
      } catch (error) {
        res.status(500).json({ error: error.message });
      }
    });

    this.app.get('/stats', async (req, res) => {
      try {
        const stats = await this.getStats();
        res.json(stats);
      } catch (error) {
        res.status(500).json({ error: error.message });
      }
    });

    this.app.get('/version', (req, res) => {
      res.json({
        version: '10.2.0',
        node: process.version,
        uptime: process.uptime(),
      });
    });

    this.app.use((req, res) => {
      res.status(404).json({ error: 'Not found' });
    });

    this.app.use((err, req, res, next) => {
      logger.error('Express error', { error: err.message });
      res.status(500).json({ error: 'Internal server error' });
    });
  }

  registerHealthCheck(name, checkFn) {
    this.healthChecks.set(name, checkFn);
    logger.info(`Health check registered: ${name}`);
  }

  async checkReadiness() {
    return true;
  }

  async getStats() {
    return {
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      cpu: process.cpuUsage(),
    };
  }

  async start() {
    return new Promise((resolve, reject) => {
      try {
        this.server = this.app.listen(this.port, () => {
          logger.info(`Health server listening on port ${this.port}`);
          resolve();
        });

        this.server.on('error', (error) => {
          logger.error('Health server error', { error: error.message });
          reject(error);
        });
      } catch (error) {
        reject(error);
      }
    });
  }

  async stop() {
    return new Promise((resolve, reject) => {
      if (!this.server) {
        resolve();
        return;
      }

      this.server.close((err) => {
        if (err) {
          logger.error('Error stopping health server', { error: err.message });
          reject(err);
        } else {
          logger.info('Health server stopped');
          resolve();
        }
      });
    });
  }
}

module.exports = HealthServer;
