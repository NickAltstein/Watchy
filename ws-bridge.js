// ws-bridge.js
const WebSocket = require('ws');
const axios = require('axios');

const wss = new WebSocket.Server({ port: 8080 });
const AI_ENDPOINT = 'http://localhost:8000/analyze';

wss.on('connection', (ws) => {
    console.log('Client connected');
    
    ws.on('message', async (data) => {
        try {
            // Forward to Python AI backend
            const response = await axios.post(AI_ENDPOINT, {
                message: JSON.parse(data),
                timestamp: new Date().toISOString()
            });
            
            // Send AI score back to client
            ws.send(JSON.stringify({
                deal_score: response.data.score,
                alert_tier: response.data.tier,
                recommendation: response.data.recommendation
            }));
        } catch (error) {
            console.error('Bridge error:', error);
        }
    });
});
