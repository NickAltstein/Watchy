const { initAuthCreds, BufferJSON } = require('@whiskeysockets/baileys');
const logger = require('../utils/logger');

class RedisAuthState {
  constructor(redisClient, sessionId = 'default') {
    this.redis = redisClient;
    this.sessionId = sessionId;
    this.keyPrefix = `baileys:${sessionId}`;
  }

  async getAuthState() {
    const creds = await this.loadCreds();
    const keys = await this.loadKeys();

    return {
      state: { creds, keys },
      saveCreds: async () => await this.saveCreds(creds),
      saveKeys: async (keys) => await this.saveKeysData(keys),
    };
  }

  async loadCreds() {
    try {
      const data = await this.redis.get(`${this.keyPrefix}:creds`);
      if (data) {
        logger.debug('Loaded credentials from Redis');
        return JSON.parse(data, BufferJSON.reviver);
      }
      logger.info('No credentials found, creating new');
      return initAuthCreds();
    } catch (error) {
      logger.error('Failed to load credentials', { error: error.message });
      return initAuthCreds();
    }
  }

  async saveCreds(creds) {
    try {
      await this.redis.set(
        `${this.keyPrefix}:creds`,
        JSON.stringify(creds, BufferJSON.replacer),
        'EX',
        60 * 60 * 24 * 30
      );
      logger.debug('Saved credentials to Redis');
    } catch (error) {
      logger.error('Failed to save credentials', { error: error.message });
      throw error;
    }
  }

  async loadKeys() {
    try {
      const keysStr = await this.redis.get(`${this.keyPrefix}:keys`);
      if (keysStr) {
        logger.debug('Loaded keys from Redis');
        return JSON.parse(keysStr, BufferJSON.reviver);
      }
      return {};
    } catch (error) {
      logger.error('Failed to load keys', { error: error.message });
      return {};
    }
  }

  async saveKeysData(keys) {
    try {
      await this.redis.set(
        `${this.keyPrefix}:keys`,
        JSON.stringify(keys, BufferJSON.replacer),
        'EX',
        60 * 60 * 24 * 30
      );
      logger.debug('Saved keys to Redis');
    } catch (error) {
      logger.error('Failed to save keys', { error: error.message });
    }
  }

  async clearSession() {
    try {
      await this.redis.del(`${this.keyPrefix}:creds`);
      await this.redis.del(`${this.keyPrefix}:keys`);
      logger.info('Cleared session from Redis');
    } catch (error) {
      logger.error('Failed to clear session', { error: error.message });
    }
  }
}

async function useRedisAuthState(redisClient, sessionId = 'default') {
  const authState = new RedisAuthState(redisClient, sessionId);
  const { state, saveCreds } = await authState.getAuthState();

  return {
    state,
    saveCreds,
    clearSession: () => authState.clearSession(),
  };
}

module.exports = { RedisAuthState, useRedisAuthState };
