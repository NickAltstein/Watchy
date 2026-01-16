/**
 * Integration tests for WhatsApp Scraper
 */

const BaileysClient = require('../src/baileys/baileys-client');
const imageProcessor = require('../src/utils/image-processor');
const metricsCollector = require('../src/utils/metrics');

// Mock Redis client
class MockRedis {
  constructor() {
    this.store = new Map();
  }
  async get(key) { return this.store.get(key) || null; }
  async set(key, value) { this.store.set(key, value); return 'OK'; }
  async del(key) { this.store.delete(key); return 1; }
  async ping() { return 'PONG'; }
  async quit() { return 'OK'; }
}

describe('WhatsApp Scraper Tests', () => {
  test('should process text message', async () => {
    const mockRedis = new MockRedis();
    const messages = [];

    const client = new BaileysClient({
      redisClient: mockRedis,
      onMessage: async (data) => messages.push(data),
    });

    client.groupCache.set('test@g.us', 'Test Group');

    const mockMessage = {
      key: { id: 'msg1', remoteJid: 'test@g.us', fromMe: false },
      message: { conversation: 'WTS Rolex $12000' },
      pushName: 'User',
      messageTimestamp: Date.now() / 1000,
    };

    await client.handleMessages([mockMessage]);
    await new Promise(resolve => setTimeout(resolve, 100));

    expect(messages.length).toBe(1);
    expect(messages[0].text).toBe('WTS Rolex $12000');
  });

  test('should deduplicate messages', async () => {
    const mockRedis = new MockRedis();
    const messages = [];

    const client = new BaileysClient({
      redisClient: mockRedis,
      onMessage: async (data) => messages.push(data),
    });

    client.groupCache.set('test@g.us', 'Test Group');

    const mockMessage = {
      key: { id: 'msg2', remoteJid: 'test@g.us', fromMe: false },
      message: { conversation: 'Test' },
      messageTimestamp: Date.now() / 1000,
    };

    await client.handleMessages([mockMessage]);
    await client.handleMessages([mockMessage]);
    await new Promise(resolve => setTimeout(resolve, 100));

    expect(messages.length).toBe(1);
  });
});

module.exports = { MockRedis };
