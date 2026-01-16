const { default: makeWASocket, DisconnectReason, downloadMediaMessage, getContentType } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const logger = require('../utils/logger');
const { useRedisAuthState } = require('./redis-auth-state');
const imageProcessor = require('../utils/image-processor');
const metricsCollector = require('../utils/metrics');

/**
 * Production-grade WhatsApp client using Baileys
 */
class BaileysClient {
  constructor(options = {}) {
    this.options = {
      redisClient: options.redisClient,
      sessionId: options.sessionId || 'default',
      queueManager: options.queueManager,
      onMessage: options.onMessage || (() => {}),
      groupFilters: options.groupFilters || [],
      maxReconnectAttempts: options.maxReconnectAttempts || 10,
      reconnectInterval: options.reconnectInterval || 10000,
      maxImageSizeMB: options.maxImageSizeMB || 5,
      ...options,
    };

    this.sock = null;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.reconnectTimeout = null;
    this.messageDedup = new Set();
    this.groupCache = new Map();
    this.isShuttingDown = false;

    this.dedupCleanupInterval = setInterval(() => {
      this.messageDedup.clear();
    }, 5 * 60 * 1000);
  }

  async connect() {
    try {
      logger.info('🔗 Initializing WhatsApp connection...');

      const { state, saveCreds, clearSession } = await useRedisAuthState(
        this.options.redisClient,
        this.options.sessionId
      );

      this.clearSession = clearSession;

      this.sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: 'silent' }),
        browser: ['Watchy Trading Engine', 'Chrome', '10.2.0'],
        markOnlineOnConnect: false,
        getMessage: async () => ({}),
        syncFullHistory: false,
        retryRequestDelayMs: 250,
        connectTimeoutMs: 60000,
        keepAliveIntervalMs: 30000,
      });

      this.setupEventHandlers(saveCreds);
      logger.info('✅ WhatsApp client initialized');
    } catch (error) {
      logger.error('Failed to initialize WhatsApp client', { error: error.message });
      this.scheduleReconnect();
    }
  }

  setupEventHandlers(saveCreds) {
    this.sock.ev.on('creds.update', saveCreds);

    this.sock.ev.on('connection.update', async (update) => {
      await this.handleConnectionUpdate(update);
    });

    this.sock.ev.on('messages.upsert', async ({ messages, type }) => {
      if (type === 'notify') {
        await this.handleMessages(messages);
      }
    });

    this.sock.ev.on('groups.update', (updates) => {
      updates.forEach((update) => {
        if (update.subject) {
          this.groupCache.set(update.id, update.subject);
        }
      });
    });
  }

  async handleConnectionUpdate(update) {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      this.displayQRCode(qr);
    }

    if (connection === 'close') {
      this.isConnected = false;
      metricsCollector.setConnectionStatus(false);
      await this.handleDisconnection(lastDisconnect);
    }

    if (connection === 'open') {
      this.isConnected = true;
      this.reconnectAttempts = 0;
      metricsCollector.setConnectionStatus(true);
      await this.onConnected();
    }
  }

  displayQRCode(qr) {
    console.log('\n' + '='.repeat(60));
    console.log('📱 SCAN THIS QR CODE WITH WHATSAPP');
    qrcode.generate(qr, { small: true });
    console.log('='.repeat(60) + '\n');
  }

  async handleDisconnection(lastDisconnect) {
    const error = lastDisconnect?.error;

    if (error instanceof Boom) {
      const statusCode = error.output?.statusCode;

      if (statusCode === DisconnectReason.loggedOut) {
        logger.error('❌ Logged out. Clearing session...');
        await this.clearSession();
        process.exit(1);
      } else {
        logger.warn(`Connection lost (${statusCode}). Reconnecting...`);
        this.scheduleReconnect();
      }
    } else {
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (this.isShuttingDown) return;

    this.reconnectAttempts++;

    if (this.reconnectAttempts > this.options.maxReconnectAttempts) {
      logger.error(`❌ Max reconnect attempts reached`);
      return;
    }

    const delay = Math.min(
      this.options.reconnectInterval * Math.pow(2, this.reconnectAttempts - 1),
      this.options.reconnectInterval * 10
    );

    logger.info(`⏳ Reconnecting in ${(delay / 1000).toFixed(1)}s...`);
    clearTimeout(this.reconnectTimeout);
    this.reconnectTimeout = setTimeout(() => this.connect(), delay);
  }

  async onConnected() {
    logger.info('✅ Connected to WhatsApp');
    await this.loadGroupCache();
    metricsCollector.setGroupsMonitored(this.groupCache.size);
  }

  async loadGroupCache() {
    try {
      const groups = await this.sock.groupFetchAllParticipating();
      Object.entries(groups).forEach(([id, group]) => {
        this.groupCache.set(id, group.subject);
      });
      logger.info(`📊 Loaded ${this.groupCache.size} groups`);
    } catch (error) {
      logger.warn('Could not fetch groups', { error: error.message });
    }
  }

  async handleMessages(messages) {
    for (const msg of messages) {
      if (this.isShuttingDown || msg.key.fromMe) continue;

      if (this.messageDedup.has(msg.key.id)) {
        metricsCollector.recordDuplicate();
        continue;
      }

      this.messageDedup.add(msg.key.id);

      const chatId = msg.key.remoteJid;
      if (chatId.endsWith('@g.us')) {
        await this.processGroupMessage(msg, chatId);
      }
    }
  }

  async processGroupMessage(msg, chatId) {
    const groupName = this.groupCache.get(chatId) || 'Unknown';

    if (!this.shouldMonitorGroup(groupName, chatId)) {
      return;
    }

    const messageType = this.getMessageType(msg);
    metricsCollector.recordMessageReceived(groupName, messageType);

    const messageData = await this.extractMessageData(msg, groupName, chatId);

    if (messageData) {
      if (this.options.queueManager) {
        await this.options.queueManager.addJob('message-processing', messageData);
      } else {
        await this.options.onMessage(messageData);
      }
      metricsCollector.recordMessageProcessed('success');
    }
  }

  shouldMonitorGroup(groupName, groupId) {
    if (this.options.groupFilters.length === 0) return true;

    return this.options.groupFilters.some((filter) => {
      if (typeof filter === 'string') {
        return groupName.toLowerCase().includes(filter.toLowerCase());
      } else if (filter instanceof RegExp) {
        return filter.test(groupName) || filter.test(groupId);
      }
      return false;
    });
  }

  getMessageType(msg) {
    const contentType = getContentType(msg.message);
    if (!contentType) return 'text';
    if (contentType.includes('image')) return 'image';
    if (contentType.includes('video')) return 'video';
    if (contentType.includes('document')) return 'document';
    return 'text';
  }

  async extractMessageData(msg, groupName, groupId) {
    const startTime = Date.now();

    try {
      const messageContent = msg.message;
      const text = this.extractText(messageContent);
      const senderId = msg.key.participant || msg.key.remoteJid;
      const senderName = msg.pushName || 'Unknown';

      let imageBase64 = null;
      let imageCaption = null;
      let hasImage = false;

      if (messageContent.imageMessage) {
        hasImage = true;
        imageCaption = messageContent.imageMessage.caption || '';

        const imageBuffer = await this.downloadImage(msg);
        if (imageBuffer) {
          const compressed = await imageProcessor.compressImage(imageBuffer);
          imageBase64 = compressed.toString('base64');
          metricsCollector.recordImageDownloaded();
          metricsCollector.recordImageCompressed();
        }
      }

      let quotedMessage = null;
      if (messageContent.extendedTextMessage?.contextInfo?.quotedMessage) {
        quotedMessage = {
          text: this.extractText(messageContent.extendedTextMessage.contextInfo.quotedMessage),
          sender: messageContent.extendedTextMessage.contextInfo.participant,
        };
      }

      const isForwarded = messageContent.extendedTextMessage?.contextInfo?.isForwarded || false;

      const messageData = {
        messageId: msg.key.id,
        groupName,
        groupId,
        senderId,
        senderName,
        timestamp: msg.messageTimestamp,
        text,
        hasImage,
        imageBase64,
        imageCaption,
        quotedMessage,
        isForwarded,
        messageType: this.getMessageType(msg),
      };

      const duration = (Date.now() - startTime) / 1000;
      metricsCollector.recordProcessingLatency(duration);

      return messageData;
    } catch (error) {
      logger.error('Error extracting message data', { error: error.message });
      return null;
    }
  }

  extractText(messageContent) {
    if (!messageContent) return '';
    return (
      messageContent.conversation ||
      messageContent.extendedTextMessage?.text ||
      messageContent.imageMessage?.caption ||
      messageContent.videoMessage?.caption ||
      ''
    ).trim();
  }

  async downloadImage(msg, retries = 3) {
    for (let attempt = 1; attempt <= retries; attempt++) {
      try {
        const buffer = await downloadMediaMessage(msg, 'buffer', {}, {
          logger: pino({ level: 'silent' }),
          reuploadRequest: this.sock.updateMediaMessage,
        });

        const sizeMB = buffer.length / (1024 * 1024);
        if (sizeMB > this.options.maxImageSizeMB) {
          logger.warn(`Image too large (${sizeMB.toFixed(2)}MB)`);
          return null;
        }

        return buffer;
      } catch (error) {
        if (attempt < retries) {
          await new Promise((resolve) => setTimeout(resolve, 1000 * Math.pow(2, attempt - 1)));
        }
      }
    }
    return null;
  }

  getStatus() {
    return {
      connected: this.isConnected,
      reconnectAttempts: this.reconnectAttempts,
      groupsMonitored: this.groupCache.size,
      messagesSeen: this.messageDedup.size,
    };
  }

  async disconnect() {
    this.isShuttingDown = true;
    clearTimeout(this.reconnectTimeout);
    clearInterval(this.dedupCleanupInterval);

    if (this.sock && this.isConnected) {
      try {
        logger.info('👋 Disconnecting from WhatsApp...');
        await this.sock.logout();
      } catch (error) {
        logger.error('Error during disconnect', { error: error.message });
      }
    }
  }
}

module.exports = BaileysClient;
