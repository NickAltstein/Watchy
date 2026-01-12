const { default: makeWASocket, DisconnectReason, useMultiFileAuthState, downloadMediaMessage } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
require('dotenv').config();

// Configuration
const CONFIG = {
    PYTHON_API_URL: process.env.PYTHON_API_URL || 'http://localhost:8000',
    WATCHED_GROUPS: (process.env.WATCHED_GROUPS || '').split(',').map(g => g.trim()).filter(Boolean),
    LOG_LEVEL: process.env.LOG_LEVEL || 'info',
    MAX_RETRIES: parseInt(process.env.MAX_RETRIES) || 3,
    REQUEST_TIMEOUT: parseInt(process.env.REQUEST_TIMEOUT) || 10000,
    WHATSAPP_RECONNECT_INTERVAL: parseInt(process.env.WHATSAPP_RECONNECT_INTERVAL) || 10000,
    WHATSAPP_MAX_RECONNECT_ATTEMPTS: parseInt(process.env.WHATSAPP_MAX_RECONNECT_ATTEMPTS) || 10,
    MAX_IMAGE_SIZE_MB: parseInt(process.env.MAX_IMAGE_SIZE_MB) || 5,
    ENABLE_METRICS: process.env.ENABLE_METRICS === 'true' || false
};

// Enhanced logger
const logger = pino({
    level: CONFIG.LOG_LEVEL,
    transport: {
        target: 'pino-pretty',
        options: {
            colorize: true,
            translateTime: 'SYS:standard',
            ignore: 'pid,hostname'
        }
    }
});

// Metrics tracking
const metrics = {
    messagesProcessed: 0,
    messagesWithImages: 0,
    successfulAPIcalls: 0,
    failedAPIcalls: 0,
    hotDealsDetected: 0,
    ignoredMessages: 0,
    startTime: Date.now()
};

let sock;
let connectionAttempts = 0;
let isShuttingDown = false;
const messageQueue = [];
let isProcessingQueue = false;

// Rate limiting for API calls
const RATE_LIMIT = {
    maxRequests: 20,
    perMinute: 60000,
    requests: [],
    check: function() {
        const now = Date.now();
        this.requests = this.requests.filter(time => now - time < this.perMinute);
        return this.requests.length < this.maxRequests;
    },
    add: function() {
        this.requests.push(Date.now());
    }
};

class WhatsAppService {
    constructor() {
        this.isConnected = false;
        this.reconnectTimeout = null;
    }

    async connect() {
        try {
            logger.info('🔗 Connecting to WhatsApp...');
            
            const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
            
            sock = makeWASocket({
                auth: state,
                printQRInTerminal: false,
                logger: pino({ level: 'silent' }),
                browser: ['Watch Trading Engine', 'Chrome', '10.2.0'],
                markOnlineOnConnect: false,
                getMessage: async () => ({})
            });

            // Event handlers
            this.setupEventHandlers(saveCreds);
            
            logger.info('✅ WhatsApp service initialized');
            
        } catch (error) {
            logger.error(`Failed to initialize WhatsApp: ${error.message}`);
            this.scheduleReconnect();
        }
    }

    setupEventHandlers(saveCreds) {
        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', async (update) => {
            await this.handleConnectionUpdate(update);
        });

        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type === 'notify') {
                await this.handleMessages(messages);
            }
        });

        // Handle group updates
        sock.ev.on('groups.update', (updates) => {
            updates.forEach(update => {
                logger.info(`🔄 Group updated: ${update.subject || 'Unknown'} (ID: ${update.id})`);
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
            await this.handleDisconnection(lastDisconnect);
        }

        if (connection === 'open') {
            this.isConnected = true;
            connectionAttempts = 0;
            await this.onConnected();
        }
    }

    displayQRCode(qr) {
        console.log('\n' + '='.repeat(50));
        console.log('📱 SCAN THIS QR CODE WITH WHATSAPP');
        console.log('1. Open WhatsApp on your phone');
        console.log('2. Tap Menu → Linked Devices → Link a Device');
        console.log('3. Scan the QR code below');
        console.log('='.repeat(50) + '\n');
        qrcode.generate(qr, { small: true });
        console.log('\n' + '='.repeat(50));
    }

    async handleDisconnection(lastDisconnect) {
        const error = lastDisconnect?.error;
        
        if (error instanceof Boom) {
            const statusCode = error.output?.statusCode;
            
            switch (statusCode) {
                case DisconnectReason.loggedOut:
                    logger.error('❌ Logged out. Please delete auth_info_baileys folder and restart.');
                    process.exit(1);
                    break;
                    
                case DisconnectReason.connectionLost:
                case DisconnectReason.connectionClosed:
                case DisconnectReason.restartRequired:
                    logger.warn(`⚠️ Connection lost (Code: ${statusCode}). Reconnecting...`);
                    this.scheduleReconnect();
                    break;
                    
                case DisconnectReason.timedOut:
                    logger.warn('⏰ Connection timeout. Reconnecting...');
                    this.scheduleReconnect();
                    break;
                    
                default:
                    logger.warn(`Disconnected with code ${statusCode}. Reconnecting...`);
                    this.scheduleReconnect();
            }
        } else {
            logger.warn('Unexpected disconnection. Reconnecting...');
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (isShuttingDown) return;
        
        connectionAttempts++;
        
        if (connectionAttempts > CONFIG.WHATSAPP_MAX_RECONNECT_ATTEMPTS) {
            logger.error('❌ Maximum reconnection attempts reached. Please restart manually.');
            return;
        }
        
        const delay = CONFIG.WHATSAPP_RECONNECT_INTERVAL * Math.min(connectionAttempts, 5);
        logger.info(`⏳ Reconnecting in ${delay/1000} seconds... (Attempt ${connectionAttempts}/${CONFIG.WHATSAPP_MAX_RECONNECT_ATTEMPTS})`);
        
        clearTimeout(this.reconnectTimeout);
        this.reconnectTimeout = setTimeout(() => this.connect(), delay);
    }

    async onConnected() {
        logger.info('✅ Connected to WhatsApp successfully');
        
        // Update group metadata cache
        await this.updateGroupCache();
        
        if (CONFIG.WATCHED_GROUPS.length > 0) {
            logger.info(`👀 Watching ${CONFIG.WATCHED_GROUPS.length} groups:`, CONFIG.WATCHED_GROUPS);
        } else {
            logger.info('🌍 Monitoring all available groups');
        }
        
        this.logMetrics();
    }

    async updateGroupCache() {
        try {
            const groups = await sock.groupFetchAllParticipating();
            logger.info(`📊 Found ${Object.keys(groups).length} groups in your chats`);
        } catch (error) {
            logger.warn(`Could not fetch groups: ${error.message}`);
        }
    }

    async handleMessages(messages) {
        for (const msg of messages) {
            if (isShuttingDown) return;
            
            try {
                // Add to queue for async processing
                messageQueue.push(msg);
                if (!isProcessingQueue) {
                    this.processQueue();
                }
            } catch (error) {
                logger.error(`Error queuing message: ${error.message}`);
            }
        }
    }

    async processQueue() {
        if (isProcessingQueue || messageQueue.length === 0) return;
        
        isProcessingQueue = true;
        
        while (messageQueue.length > 0 && !isShuttingDown) {
            const msg = messageQueue.shift();
            await this.processMessage(msg);
            
            // Small delay to prevent overwhelming the API
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        
        isProcessingQueue = false;
    }

    async processMessage(msg) {
        // Basic validation
        if (!msg.message || msg.key.fromMe) return;
        
        const chatId = msg.key.remoteJid;
        const isGroup = chatId.endsWith('@g.us');
        if (!isGroup) return;
        
        try {
            const groupName = await this.getGroupName(chatId);
            
            // Check if we should monitor this group
            if (CONFIG.WATCHED_GROUPS.length > 0 && !CONFIG.WATCHED_GROUPS.includes(groupName)) {
                return;
            }
            
            // Extract message content
            const { text, imageBuffer } = await this.extractMessageContent(msg);
            
            // Skip if no meaningful content
            if (!this.hasWatchContent(text, imageBuffer)) {
                logger.debug(`⏭️ Skipping: No watch content in ${groupName}`);
                return;
            }
            
            logger.info(`📨 New message in "${groupName}"`);
            
            // Send to AI parser
            await this.sendToAPI({
                text,
                imageBase64: imageBuffer ? imageBuffer.toString('base64') : null,
                groupName,
                senderId: msg.key.participant || msg.key.remoteJid,
                messageId: msg.key.id,
                timestamp: msg.messageTimestamp
            });
            
        } catch (error) {
            logger.error(`Error processing message: ${error.message}`);
        }
    }

    async getGroupName(chatId) {
        try {
            const groupMetadata = await sock.groupMetadata(chatId);
            return groupMetadata.subject || 'Unknown Group';
        } catch (error) {
            logger.warn(`Could not fetch group name: ${error.message}`);
            return 'Unknown Group';
        }
    }

    async extractMessageContent(msg) {
        const messageContent = msg.message;
        let text = '';
        let imageBuffer = null;
        
        // Extract text from various message types
        text = messageContent.conversation || 
               messageContent.extendedTextMessage?.text || 
               messageContent.imageMessage?.caption ||
               messageContent.videoMessage?.caption ||
               '';
        
        // Clean text
        text = text.trim();
        
        // Handle images
        if (messageContent.imageMessage) {
            try {
                imageBuffer = await downloadMediaMessage(
                    msg,
                    'buffer',
                    {},
                    {
                        logger: pino({ level: 'silent' }),
                        reuploadRequest: sock.updateMediaMessage
                    }
                );
                
                // Check image size
                const sizeMB = imageBuffer.length / (1024 * 1024);
                if (sizeMB > CONFIG.MAX_IMAGE_SIZE_MB) {
                    logger.warn(`Image too large (${sizeMB.toFixed(2)}MB), skipping download`);
                    imageBuffer = null;
                } else {
                    metrics.messagesWithImages++;
                    logger.debug(`📷 Image downloaded (${Math.round(imageBuffer.length / 1024)}KB)`);
                }
            } catch (error) {
                logger.warn(`Failed to download image: ${error.message}`);
            }
        }
        
        return { text, imageBuffer };
    }

    hasWatchContent(text, imageBuffer) {
        // Skip if no content at all
        if (!text && !imageBuffer) return false;
        
        // Skip common non-watch messages
        const ignorePatterns = [
            /^bump$/i,
            /^\.$/,
            /^ttt$/i,
            /^up$/i,
            /^available$/i,
            /^sold$/i,
            /^thanks$/i,
            /^thank you$/i,
            /^👍$/,
            /^👌$/,
            /^\?+$/,
            /^lol$/i,
            /^haha$/i
        ];
        
        if (ignorePatterns.some(pattern => pattern.test(text.trim()))) {
            return false;
        }
        
        // Look for watch-related keywords
        const watchKeywords = [
            'rolex', 'patek', 'audemars', 'ap', 'richard', 'cartier', 'omega',
            'breitling', 'iwc', 'panerai', 'hublot', 'tag heuer', 'submariner',
            'gmt', 'daytona', 'nautilus', 'royal oak', 'wts', 'wtb', 'for sale',
            'selling', 'buying', 'trade', 'price', '$', 'usd', 'sgd', 'eur'
        ];
        
        const lowerText = text.toLowerCase();
        return watchKeywords.some(keyword => lowerText.includes(keyword)) || imageBuffer !== null;
    }

    async sendToAPI(data) {
        if (!RATE_LIMIT.check()) {
            logger.warn('⚠️ Rate limit exceeded, skipping API call');
            return;
        }
        
        let retries = 0;
        
        while (retries < CONFIG.MAX_RETRIES) {
            try {
                RATE_LIMIT.add();
                metrics.messagesProcessed++;
                
                logger.debug('🧠 Sending to AI parser...');
                
                const response = await axios.post(`${CONFIG.PYTHON_API_URL}/parse-watch`, data, {
                    timeout: CONFIG.REQUEST_TIMEOUT,
                    headers: {
                        'Content-Type': 'application/json',
                        'User-Agent': 'WatchTradingEngine/10.2.0'
                    },
                    validateStatus: function(status) {
                        return status < 500; // Reject only on server errors
                    }
                });
                
                metrics.successfulAPIcalls++;
                
                if (response.data.status === 'success') {
                    this.handleSuccessfulParse(response.data, data.groupName);
                } else if (response.data.status === 'ignore') {
                    metrics.ignoredMessages++;
                    logger.debug(`⏭️ Ignored: ${response.data.code || 'Not a watch listing'}`);
                } else {
                    logger.warn(`API returned: ${response.data.status} - ${response.data.code || ''}`);
                }
                
                return; // Success, exit retry loop
                
            } catch (error) {
                retries++;
                metrics.failedAPIcalls++;
                
                if (retries === CONFIG.MAX_RETRIES) {
                    logger.error(`❌ Failed after ${CONFIG.MAX_RETRIES} attempts: ${error.message}`);
                    
                    if (error.code === 'ECONNREFUSED') {
                        logger.error('Python API not running. Start with: npm run api');
                    } else if (error.response) {
                        logger.error(`API error ${error.response.status}: ${JSON.stringify(error.response.data)}`);
                    }
                } else {
                    logger.warn(`Retry ${retries}/${CONFIG.MAX_RETRIES}: ${error.message}`);
                    
                    // Exponential backoff
                    await new Promise(resolve => 
                        setTimeout(resolve, 1000 * Math.pow(2, retries - 1))
                    );
                }
            }
        }
    }

    handleSuccessfulParse(result, groupName) {
        logger.info('✅ Watch listing detected:');
        
        const displayData = {
            Ref: result.ref || 'Unknown',
            Price: `$${result.price?.toLocaleString() || 'N/A'}`,
            Market: `$${result.market_price?.toLocaleString() || 'N/A'}`,
            Score: result.score || 0,
            Tier: result.tier || 'NORMAL',
            Sentiment: result.sentiment || 'WTS',
            Drift: result.drift ? '📉 Price drop' : ''
        };
        
        // Format for console display
        console.log('\n' + '='.repeat(50));
        Object.entries(displayData).forEach(([key, value]) => {
            if (value) {
                console.log(`${key.padEnd(10)}: ${value}`);
            }
        });
        console.log('Group:', groupName);
        console.log('='.repeat(50) + '\n');
        
        // Log for hot deals
        if (result.tier === 'URGENT') {
            metrics.hotDealsDetected++;
            logger.info(`🔥 URGENT DEAL! Score: ${result.score}`);
            
            // Optional: Trigger notifications here
            // await this.sendNotification(result, groupName);
        }
    }

    async sendNotification(result, groupName) {
        // Implement your notification logic here
        // Discord, Slack, Telegram, Email, etc.
        
        const message = `🔥 URGENT WATCH DEAL DETECTED!\n` +
                       `Ref: ${result.ref}\n` +
                       `Price: $${result.price?.toLocaleString()}\n` +
                       `Market: $${result.market_price?.toLocaleString()}\n` +
                       `Score: ${result.score} (${result.tier})\n` +
                       `Group: ${groupName}\n` +
                       `Time: ${new Date().toLocaleTimeString()}`;
        
        logger.info('📢 Notification:', message);
    }

    logMetrics() {
        const uptime = Date.now() - metrics.startTime;
        const hours = Math.floor(uptime / (1000 * 60 * 60));
        const minutes = Math.floor((uptime % (1000 * 60 * 60)) / (1000 * 60));
        
        console.log('\n' + '📊 ' + '='.repeat(40));
        console.log('SYSTEM METRICS');
        console.log('='.repeat(40));
        console.log(`Uptime: ${hours}h ${minutes}m`);
        console.log(`Messages processed: ${metrics.messagesProcessed}`);
        console.log(`Images downloaded: ${metrics.messagesWithImages}`);
        console.log(`API success: ${metrics.successfulAPIcalls}`);
        console.log(`API failures: ${metrics.failedAPIcalls}`);
        console.log(`Hot deals: ${metrics.hotDealsDetected}`);
        console.log(`Ignored: ${metrics.ignoredMessages}`);
        console.log(`Queue size: ${messageQueue.length}`);
        console.log('='.repeat(40) + '\n');
    }

    async disconnect() {
        isShuttingDown = true;
        clearTimeout(this.reconnectTimeout);
        
        if (sock && this.isConnected) {
            try {
                logger.info('👋 Disconnecting from WhatsApp...');
                await sock.logout();
                logger.info('✅ Disconnected successfully');
            } catch (error) {
                logger.error(`Error during disconnect: ${error.message}`);
            }
        }
    }
}

// Create and start service
const whatsappService = new WhatsAppService();

// Graceful shutdown
const shutdown = async () => {
    logger.info('\n🛑 Shutdown signal received...');
    isShuttingDown = true;
    
    whatsappService.logMetrics();
    
    await whatsappService.disconnect();
    
    // Wait for queue to process
    if (messageQueue.length > 0) {
        logger.info(`Processing ${messageQueue.length} remaining messages...`);
        await new Promise(resolve => setTimeout(resolve, 5000));
    }
    
    logger.info('👋 Shutdown complete');
    process.exit(0);
};

// Handle various shutdown signals
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
process.on('SIGHUP', shutdown);

// Handle uncaught errors
process.on('uncaughtException', (error) => {
    logger.error(`Uncaught Exception: ${error.message}`);
    logger.error(error.stack);
    // Don't exit, let the service try to recover
});

process.on('unhandledRejection', (reason, promise) => {
    logger.error(`Unhandled Rejection at: ${promise}, reason: ${reason}`);
});

// Start the service
(async () => {
    logger.info('🚀 WhatsApp Watch Trading Engine v10.2 Starting...');
    logger.info(`📡 API Endpoint: ${CONFIG.PYTHON_API_URL}`);
    
    await whatsappService.connect();
})();

// Export for testing
module.exports = { WhatsAppService, CONFIG, metrics };
