<<<<<<< HEAD
# ==========================================
# Multi-stage Dockerfile for Watch Trading Engine
# ==========================================

# Stage 1: Python API Builder
FROM python:3.11-slim as python-builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Node.js Builder
FROM node:18-slim as node-builder

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Stage 3: Final Runtime Image
FROM python:3.11-slim

WORKDIR /app

# Install Node.js in Python base image
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=python-builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy Node.js dependencies from builder
COPY --from=node-builder /app/node_modules ./node_modules
=======
FROM node:18-alpine

# Install Python for the API
RUN apk add --no-cache python3 py3-pip

WORKDIR /app

# Copy package files
COPY package*.json ./
COPY requirements.txt ./

# Install Node dependencies
RUN npm ci --only=production

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt
>>>>>>> origin/main

# Copy application files
COPY . .

<<<<<<< HEAD
# Create necessary directories
RUN mkdir -p auth_info_baileys logs

# Expose ports
EXPOSE 8000 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
=======
# Create logs directory
RUN mkdir -p logs

# Expose ports
EXPOSE 3000 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1); });"

# Start both services using PM2
CMD ["npx", "pm2-runtime", "start", "ecosystem.config.js"]
>>>>>>> origin/main
