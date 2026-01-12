const { default: puppeteer } = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs').promises;
const path = require('path');

// Apply stealth plugin
puppeteer.use(StealthPlugin());

class WhatsAppStealthClient {
    constructor(sessionDir = './session') {
        this.sessionDir = sessionDir;
        this.browser = null;
        this.page = null;
        this.isAuthenticated = false;
    }

    async initialize() {
        console.log('[Sentinel] Launching stealth browser...');
        
        // 1. LAUNCH WITH HUMAN-LIKE CONFIGURATION
        this.browser = await puppeteer.launch({
            headless: false, // CRITICAL: WhatsApp detects & blocks headless
            args: [
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--window-size=1024,768',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage'
            ],
            ignoreDefaultArgs: ['--enable-automation'], // Remove automation flags
            userDataDir: this.sessionDir // Persistent session storage
        });

        // 2. CREATE PAGE WITH HUMAN-LIKE PROPERTIES
        this.page = await this.browser.newPage();
        
        // Mask Puppeteer's presence
        await this.page.evaluateOnNewDocument(() => {
            // Overwrite navigator properties
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { 
                get: () => [1, 2, 3, 4, 5] // Fake plugins array
            });
            // Overwrite chrome property
            window.chrome = { runtime: {} };
        });

        // Set realistic viewport and user agent
        await this.page.setViewport({ width: 1024, height: 768 });
        await this.page.setUserAgent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        );

        // 3. NAVIGATE TO WHATSAPP WEB
        await this.page.goto('https://web.whatsapp.com', { 
            waitUntil: 'networkidle2',
            timeout: 60000 
        });

        console.log('[Sentinel] Browser initialized. Awaiting QR scan...');
        return this;
    }

    // 4. AUTHENTICATION HANDLER WITH SESSION PERSISTENCE
    async waitForAuthentication(timeout = 120000) {
        return new Promise((resolve, reject) => {
            const checkInterval = setInterval(async () => {
                try {
                    // Check if we're logged in by looking for the main app panel
                    const isLoggedIn = await this.page.evaluate(() => {
                        return document.querySelector('div[data-testid="chat-list"]') !== null;
                    });

                    if (isLoggedIn) {
                        clearInterval(checkInterval);
                        this.isAuthenticated = true;
                        console.log('[Sentinel] Authentication successful!');
                        
                        // Save session state
                        await this.saveSession();
                        resolve(true);
                    }
                } catch (error) {
                    // Silently continue checking
                }
            }, 2000);

            // Timeout after specified period
            setTimeout(() => {
                clearInterval(checkInterval);
                reject(new Error('Authentication timeout'));
            }, timeout);
        });
    }

    // 5. LOCAL DATA SCRUBBER (CRITICAL PRIVACY LAYER)
    async scrubMessage(rawMessage) {
        // Extract and anonymize message data BEFORE sending to cloud
        const scrubbed = {
            // Generate hash-based identifiers (never send phone numbers)
            groupHash: await this.hashString(rawMessage.chatId),
            senderHash: await this.hashString(rawMessage.senderId),
            
            // Content (truncated for privacy)
            textSnippet: rawMessage.body ? rawMessage.body.substring(0, 500) : null,
            hasMedia: rawMessage.hasMedia,
            
            // Timing
            timestamp: new Date().toISOString(),
            messageId: await this.hashString(rawMessage.id)
        };

        // Only include media if absolutely necessary for analysis
        if (rawMessage.hasMedia && rawMessage.type === 'image') {
            // We'll download and buffer the image locally
            scrubbed.imageBuffer = await this.downloadImageToBuffer(rawMessage);
        }

        return scrubbed;
    }

    // 6. HUMAN-LIKE BEHAVIOR SIMULATION
    async simulateHumanPresence() {
        if (!this.isAuthenticated) return;

        // Random small mouse movements
        await this.page.mouse.move(
            100 + Math.random() * 300,
            100 + Math.random() * 200,
            { steps: 10 }
        );

        // Occasional gentle scrolling
        if (Math.random() > 0.7) {
            await this.page.evaluate(() => {
                window.scrollBy(0, 50 + Math.random() * 100);
            });
        }

        // Random "reading time" pauses
        await this.page.waitForTimeout(1000 + Math.random() * 4000);
    }

    // 7. MESSAGE MONITORING LOOP
    async startMonitoring(onNewMessage) {
        if (!this.isAuthenticated) {
            throw new Error('Not authenticated');
        }

        console.log('[Sentinel] Starting message monitoring...');
        
        let lastMessageCount = 0;
        
        // Continuous monitoring loop
        while (true) {
            try {
                // Get current messages
                const messages = await this.page.evaluate(() => {
                    const elements = document.querySelectorAll('[data-testid="msg-container"]');
                    return Array.from(elements).map(el => ({
                        id: el.getAttribute('data-id'),
                        text: el.innerText,
                        timestamp: el.getAttribute('data-pre-plain-text')
                    })).slice(-20); // Only check recent messages
                });

                // Check for new messages
                if (messages.length > lastMessageCount) {
                    const newMessages = messages.slice(lastMessageCount);
                    
                    for (const msg of newMessages) {
                        // Scrub locally first
                        const scrubbed = await this.scrubMessage({
                            chatId: await this.getCurrentChatId(),
                            senderId: 'extracted-from-dom', // You'll need to extract this
                            body: msg.text,
                            id: msg.id,
                            hasMedia: msg.text.includes('image omitted')
                        });

                        // Pass scrubbed data to handler
                        await onNewMessage(scrubbed);
                    }
                    
                    lastMessageCount = messages.length;
                }

                // Simulate human behavior between checks
                await this.simulateHumanPresence();
                
                // Wait before next check (variable timing)
                await this.page.waitForTimeout(2000 + Math.random() * 3000);

            } catch (error) {
                console.error('[Sentinel] Monitoring error:', error.message);
                // Recover gracefully
                await this.page.waitForTimeout(5000);
            }
        }
    }

    // 8. UTILITY FUNCTIONS
    async hashString(str) {
        // Simple hash for anonymization
        const encoder = new TextEncoder();
        const data = encoder.encode(str);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('').substring(0, 16);
    }

    async saveSession() {
        const sessionFile = path.join(this.sessionDir, 'session.json');
        const sessionData = {
            authenticated: true,
            timestamp: new Date().toISOString()
        };
        await fs.writeFile(sessionFile, JSON.stringify(sessionData, null, 2));
    }

    async cleanup() {
        if (this.browser) {
            await this.browser.close();
        }
    }
}

// 9. MAIN EXECUTION
async function main() {
    const client = new WhatsAppStealthClient();
    
    try {
        await client.initialize();
        await client.waitForAuthentication();
        
        // Once authenticated, start monitoring
        await client.startMonitoring(async (scrubbedMessage) => {
            console.log('[Sentinel] New scrubbed message:', {
                groupHash: scrubbedMessage.groupHash,
                textSnippet: scrubbedMessage.textSnippet?.substring(0, 100) + '...',
                timestamp: scrubbedMessage.timestamp
            });
            
            // HERE: Send to your AI cloud via encrypted WebSocket
            // await sendToAI(scrubbedMessage);
        });
        
    } catch (error) {
        console.error('[Sentinel] Fatal error:', error);
        await client.cleanup();
        process.exit(1);
    }
}

// Run if called directly
if (require.main === module) {
    main();
}

module.exports = WhatsAppStealthClient;
