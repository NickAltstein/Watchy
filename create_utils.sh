#!/bin/bash

# Create image processor
cat > src/utils/image-processor.js << 'EOFIMG'
const sharp = require('sharp');
const logger = require('./logger');

class ImageProcessor {
  constructor(options = {}) {
    this.maxSizeKB = options.maxSizeKB || 500;
    this.maxWidth = options.maxWidth || 1920;
    this.maxHeight = options.maxHeight || 1080;
    this.quality = options.quality || 80;
  }

  async compressImage(imageBuffer) {
    try {
      const metadata = await sharp(imageBuffer).metadata();
      const originalSizeKB = imageBuffer.length / 1024;

      logger.debug(`Processing image: ${metadata.format} ${metadata.width}x${metadata.height} (${originalSizeKB.toFixed(2)}KB)`);

      if (originalSizeKB <= this.maxSizeKB) {
        logger.debug('Image already within size limit');
        return imageBuffer;
      }

      let compressed = sharp(imageBuffer);

      if (metadata.width > this.maxWidth || metadata.height > this.maxHeight) {
        compressed = compressed.resize(this.maxWidth, this.maxHeight, {
          fit: 'inside',
          withoutEnlargement: true,
        });
      }

      let result = await compressed.jpeg({ quality: this.quality, mozjpeg: true }).toBuffer();
      let compressedSizeKB = result.length / 1024;

      let currentQuality = this.quality;
      while (compressedSizeKB > this.maxSizeKB && currentQuality > 40) {
        currentQuality -= 10;
        result = await sharp(imageBuffer)
          .resize(this.maxWidth, this.maxHeight, { fit: 'inside', withoutEnlargement: true })
          .jpeg({ quality: currentQuality, mozjpeg: true })
          .toBuffer();
        compressedSizeKB = result.length / 1024;
      }

      const compressionRatio = ((1 - compressedSizeKB / originalSizeKB) * 100).toFixed(1);
      logger.info(`Image compressed: ${originalSizeKB.toFixed(2)}KB → ${compressedSizeKB.toFixed(2)}KB (${compressionRatio}% reduction)`);

      return result;
    } catch (error) {
      logger.error('Image compression failed', { error: error.message });
      return imageBuffer;
    }
  }

  async validateImage(imageBuffer) {
    try {
      await sharp(imageBuffer).metadata();
      return true;
    } catch (error) {
      logger.warn('Invalid image buffer', { error: error.message });
      return false;
    }
  }

  async getMetadata(imageBuffer) {
    try {
      return await sharp(imageBuffer).metadata();
    } catch (error) {
      logger.error('Failed to get image metadata', { error: error.message });
      return null;
    }
  }
}

const imageProcessor = new ImageProcessor();
module.exports = imageProcessor;
EOFIMG

echo "Created image-processor.js"
