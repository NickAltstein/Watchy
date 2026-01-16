const client = require('prom-client');
const logger = require('./logger');

class MetricsCollector {
  constructor() {
    this.register = new client.Registry();
    client.collectDefaultMetrics({ register: this.register });

    this.messagesReceived = new client.Counter({
      name: 'whatsapp_messages_received_total',
      help: 'Total WhatsApp messages received',
      labelNames: ['group', 'type'],
      registers: [this.register],
    });

    this.messagesProcessed = new client.Counter({
      name: 'whatsapp_messages_processed_total',
      help: 'Total messages processed successfully',
      labelNames: ['status'],
      registers: [this.register],
    });

    this.messagesFailed = new client.Counter({
      name: 'whatsapp_messages_failed_total',
      help: 'Total messages that failed processing',
      labelNames: ['reason'],
      registers: [this.register],
    });

    this.imagesDownloaded = new client.Counter({
      name: 'whatsapp_images_downloaded_total',
      help: 'Total images downloaded',
      registers: [this.register],
    });

    this.imagesCompressed = new client.Counter({
      name: 'whatsapp_images_compressed_total',
      help: 'Total images compressed',
      registers: [this.register],
    });

    this.apiCalls = new client.Counter({
      name: 'api_calls_total',
      help: 'Total API calls made',
      labelNames: ['endpoint', 'status'],
      registers: [this.register],
    });

    this.apiLatency = new client.Histogram({
      name: 'api_latency_seconds',
      help: 'API call latency in seconds',
      labelNames: ['endpoint'],
      buckets: [0.1, 0.5, 1, 2, 5, 10],
      registers: [this.register],
    });

    this.messageProcessingLatency = new client.Histogram({
      name: 'message_processing_latency_seconds',
      help: 'Message processing latency in seconds',
      buckets: [0.01, 0.05, 0.1, 0.5, 1, 2],
      registers: [this.register],
    });

    this.groupsMonitored = new client.Gauge({
      name: 'whatsapp_groups_monitored',
      help: 'Number of WhatsApp groups monitored',
      registers: [this.register],
    });

    this.queueSize = new client.Gauge({
      name: 'queue_size',
      help: 'Current size of message queue',
      labelNames: ['queue'],
      registers: [this.register],
    });

    this.connectionStatus = new client.Gauge({
      name: 'whatsapp_connection_status',
      help: 'WhatsApp connection status (1=connected, 0=disconnected)',
      registers: [this.register],
    });

    this.circuitBreakerStatus = new client.Gauge({
      name: 'circuit_breaker_status',
      help: 'Circuit breaker status (0=closed, 1=open, 2=half-open)',
      labelNames: ['name'],
      registers: [this.register],
    });

    this.hotDeals = new client.Counter({
      name: 'hot_deals_detected_total',
      help: 'Total hot deals detected',
      labelNames: ['tier'],
      registers: [this.register],
    });

    this.duplicateMessages = new client.Counter({
      name: 'duplicate_messages_total',
      help: 'Total duplicate messages detected',
      registers: [this.register],
    });

    logger.info('Prometheus metrics initialized');
  }

  recordMessageReceived(groupName, messageType) {
    this.messagesReceived.inc({ group: groupName, type: messageType });
  }

  recordMessageProcessed(status) {
    this.messagesProcessed.inc({ status });
  }

  recordMessageFailed(reason) {
    this.messagesFailed.inc({ reason });
  }

  recordImageDownloaded() {
    this.imagesDownloaded.inc();
  }

  recordImageCompressed() {
    this.imagesCompressed.inc();
  }

  recordAPICall(endpoint, status) {
    this.apiCalls.inc({ endpoint, status });
  }

  recordAPILatency(endpoint, durationSeconds) {
    this.apiLatency.observe({ endpoint }, durationSeconds);
  }

  recordProcessingLatency(durationSeconds) {
    this.messageProcessingLatency.observe(durationSeconds);
  }

  setGroupsMonitored(count) {
    this.groupsMonitored.set(count);
  }

  setQueueSize(queueName, size) {
    this.queueSize.set({ queue: queueName }, size);
  }

  setConnectionStatus(connected) {
    this.connectionStatus.set(connected ? 1 : 0);
  }

  setCircuitBreakerStatus(name, status) {
    const statusValue = status === 'OPEN' ? 1 : status === 'HALF-OPEN' ? 2 : 0;
    this.circuitBreakerStatus.set({ name }, statusValue);
  }

  recordHotDeal(tier) {
    this.hotDeals.inc({ tier });
  }

  recordDuplicate() {
    this.duplicateMessages.inc();
  }

  async getMetrics() {
    return await this.register.metrics();
  }

  async getMetricsJSON() {
    return await this.register.getMetricsAsJSON();
  }
}

const metricsCollector = new MetricsCollector();
module.exports = metricsCollector;
