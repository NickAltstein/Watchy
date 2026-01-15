"""
Notification Service for Watch Trading Engine
Supports multiple notification channels: Discord, Slack, Telegram, Email
"""

import os
import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
import aiohttp
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

logger = logging.getLogger("watch-engine.notifications")


class NotificationService:
    """Handles notifications across multiple channels"""
    
    def __init__(self):
        self.discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Email settings
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.alert_email_to = os.getenv('ALERT_EMAIL_TO')
        
        self.enabled_channels = self._detect_enabled_channels()
        
        if self.enabled_channels:
            logger.info(f"📢 Notification service initialized. Channels: {', '.join(self.enabled_channels)}")
        else:
            logger.info("📢 Notification service initialized (no channels configured)")
    
    def _detect_enabled_channels(self) -> List[str]:
        """Detect which notification channels are configured"""
        channels = []
        
        if self.discord_webhook:
            channels.append('discord')
        if self.slack_webhook:
            channels.append('slack')
        if self.telegram_bot_token and self.telegram_chat_id:
            channels.append('telegram')
        if all([self.smtp_host, self.smtp_user, self.smtp_password, self.alert_email_to]):
            channels.append('email')
        
        return channels
    
    async def send_alert(
        self,
        ref_number: str,
        price: int,
        market_price: int,
        deal_score: int,
        alert_tier: str,
        group_name: str,
        sentiment: str = "WTS",
        raw_text: Optional[str] = None
    ):
        """Send alert to all configured channels"""
        
        if not self.enabled_channels:
            logger.debug("No notification channels configured, skipping alert")
            return
        
        # Only send notifications for significant deals
        if deal_score < 200:
            logger.debug(f"Score {deal_score} below notification threshold, skipping")
            return
        
        # Prepare message content
        message_data = {
            "ref_number": ref_number,
            "price": price,
            "market_price": market_price,
            "deal_score": deal_score,
            "alert_tier": alert_tier,
            "group_name": group_name,
            "sentiment": sentiment,
            "discount_pct": round(((market_price - price) / market_price) * 100, 1),
            "timestamp": datetime.now().isoformat(),
            "raw_text": raw_text
        }
        
        # Send to all channels concurrently
        tasks = []
        
        if 'discord' in self.enabled_channels:
            tasks.append(self._send_discord(message_data))
        
        if 'slack' in self.enabled_channels:
            tasks.append(self._send_slack(message_data))
        
        if 'telegram' in self.enabled_channels:
            tasks.append(self._send_telegram(message_data))
        
        if 'email' in self.enabled_channels:
            tasks.append(self._send_email(message_data))
        
        # Execute all notifications concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log results
        for channel, result in zip(self.enabled_channels, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send {channel} notification: {result}")
            else:
                logger.info(f"✅ Sent {channel} notification for {ref_number}")
    
    async def _send_discord(self, data: Dict):
        """Send notification to Discord"""
        
        # Determine color based on tier
        color_map = {
            "URGENT": 0xFF0000,  # Red
            "PUSH": 0xFFA500,    # Orange
            "NORMAL": 0x3B82F6   # Blue
        }
        color = color_map.get(data['alert_tier'], 0x3B82F6)
        
        # Determine emoji
        emoji_map = {
            "URGENT": "🔥",
            "PUSH": "⚡",
            "NORMAL": "📊"
        }
        emoji = emoji_map.get(data['alert_tier'], "📊")
        
        embed = {
            "title": f"{emoji} {data['alert_tier']} WATCH DEAL DETECTED",
            "color": color,
            "fields": [
                {
                    "name": "Reference",
                    "value": f"**{data['ref_number']}**",
                    "inline": True
                },
                {
                    "name": "Asking Price",
                    "value": f"${data['price']:,}",
                    "inline": True
                },
                {
                    "name": "Market Price",
                    "value": f"${data['market_price']:,}",
                    "inline": True
                },
                {
                    "name": "Deal Score",
                    "value": f"**{data['deal_score']}**",
                    "inline": True
                },
                {
                    "name": "Discount",
                    "value": f"{data['discount_pct']}% below market",
                    "inline": True
                },
                {
                    "name": "Sentiment",
                    "value": data['sentiment'],
                    "inline": True
                },
                {
                    "name": "Source",
                    "value": data['group_name'],
                    "inline": False
                }
            ],
            "footer": {
                "text": "Watch Trading Engine"
            },
            "timestamp": data['timestamp']
        }
        
        if data.get('raw_text'):
            embed['fields'].append({
                "name": "Original Message",
                "value": data['raw_text'][:1024],  # Discord limit
                "inline": False
            })
        
        payload = {
            "embeds": [embed]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.discord_webhook,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status not in [200, 204]:
                    raise Exception(f"Discord API returned {response.status}")
    
    async def _send_slack(self, data: Dict):
        """Send notification to Slack"""
        
        # Determine emoji
        emoji_map = {
            "URGENT": ":fire:",
            "PUSH": ":zap:",
            "NORMAL": ":chart_with_upwards_trend:"
        }
        emoji = emoji_map.get(data['alert_tier'], ":chart_with_upwards_trend:")
        
        # Create Slack blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {data['alert_tier']} WATCH DEAL",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Reference:*\n{data['ref_number']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Deal Score:*\n{data['deal_score']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Asking Price:*\n${data['price']:,}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Market Price:*\n${data['market_price']:,}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Discount:*\n{data['discount_pct']}%"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Source:*\n{data['group_name']}"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Watch Trading Engine • {data['timestamp']}"
                    }
                ]
            }
        ]
        
        payload = {
            "blocks": blocks
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.slack_webhook,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    raise Exception(f"Slack API returned {response.status}")
    
    async def _send_telegram(self, data: Dict):
        """Send notification to Telegram"""
        
        # Determine emoji
        emoji_map = {
            "URGENT": "🔥",
            "PUSH": "⚡",
            "NORMAL": "📊"
        }
        emoji = emoji_map.get(data['alert_tier'], "📊")
        
        # Format message with Markdown
        message = f"""
{emoji} *{data['alert_tier']} WATCH DEAL DETECTED*

*Reference:* `{data['ref_number']}`
*Asking Price:* ${data['price']:,}
*Market Price:* ${data['market_price']:,}
*Deal Score:* {data['deal_score']}
*Discount:* {data['discount_pct']}% below market

*Source:* {data['group_name']}
*Sentiment:* {data['sentiment']}

_Watch Trading Engine • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_
"""
        
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message.strip(),
            "parse_mode": "Markdown"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    raise Exception(f"Telegram API returned {response.status}")
    
    async def _send_email(self, data: Dict):
        """Send notification via email"""
        
        # Determine emoji for subject
        emoji_map = {
            "URGENT": "🔥",
            "PUSH": "⚡",
            "NORMAL": "📊"
        }
        emoji = emoji_map.get(data['alert_tier'], "📊")
        
        # Create email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"{emoji} {data['alert_tier']} Watch Deal: {data['ref_number']}"
        msg['From'] = self.smtp_user
        msg['To'] = self.alert_email_to
        
        # Plain text version
        text = f"""
{data['alert_tier']} WATCH DEAL DETECTED

Reference: {data['ref_number']}
Asking Price: ${data['price']:,}
Market Price: ${data['market_price']:,}
Deal Score: {data['deal_score']}
Discount: {data['discount_pct']}% below market

Source: {data['group_name']}
Sentiment: {data['sentiment']}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
Watch Trading Engine
"""
        
        # HTML version
        html = f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 2px solid #{'#FF0000' if data['alert_tier'] == 'URGENT' else '#FFA500' if data['alert_tier'] == 'PUSH' else '#3B82F6'};">
      <h2 style="color: #{'#FF0000' if data['alert_tier'] == 'URGENT' else '#FFA500' if data['alert_tier'] == 'PUSH' else '#3B82F6'};">
        {emoji} {data['alert_tier']} WATCH DEAL
      </h2>
      
      <table style="width: 100%; border-collapse: collapse;">
        <tr style="background-color: #f5f5f5;">
          <td style="padding: 10px; font-weight: bold;">Reference:</td>
          <td style="padding: 10px;">{data['ref_number']}</td>
        </tr>
        <tr>
          <td style="padding: 10px; font-weight: bold;">Asking Price:</td>
          <td style="padding: 10px; color: #10b981; font-weight: bold;">${data['price']:,}</td>
        </tr>
        <tr style="background-color: #f5f5f5;">
          <td style="padding: 10px; font-weight: bold;">Market Price:</td>
          <td style="padding: 10px;">${data['market_price']:,}</td>
        </tr>
        <tr>
          <td style="padding: 10px; font-weight: bold;">Deal Score:</td>
          <td style="padding: 10px; font-weight: bold; font-size: 18px;">{data['deal_score']}</td>
        </tr>
        <tr style="background-color: #f5f5f5;">
          <td style="padding: 10px; font-weight: bold;">Discount:</td>
          <td style="padding: 10px; color: #10b981;">{data['discount_pct']}% below market</td>
        </tr>
        <tr>
          <td style="padding: 10px; font-weight: bold;">Source:</td>
          <td style="padding: 10px;">{data['group_name']}</td>
        </tr>
        <tr style="background-color: #f5f5f5;">
          <td style="padding: 10px; font-weight: bold;">Sentiment:</td>
          <td style="padding: 10px;">{data['sentiment']}</td>
        </tr>
      </table>
      
      <div style="margin-top: 20px; padding: 15px; background-color: #f9fafb; border-left: 4px solid #3B82F6;">
        <p style="margin: 0; font-size: 12px; color: #666;">
          <strong>Watch Trading Engine</strong><br>
          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </p>
      </div>
    </div>
  </body>
</html>
"""
        
        # Attach both versions
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email (run in executor to avoid blocking)
        await asyncio.get_event_loop().run_in_executor(
            None,
            self._send_email_sync,
            msg
        )
    
    def _send_email_sync(self, msg: MIMEMultipart):
        """Synchronous email sending (called in executor)"""
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise


# Global notification service instance
notification_service = NotificationService()


async def send_deal_notification(
    ref_number: str,
    price: int,
    market_price: int,
    deal_score: int,
    alert_tier: str,
    group_name: str,
    sentiment: str = "WTS",
    raw_text: Optional[str] = None
):
    """Convenience function to send deal notifications"""
    await notification_service.send_alert(
        ref_number=ref_number,
        price=price,
        market_price=market_price,
        deal_score=deal_score,
        alert_tier=alert_tier,
        group_name=group_name,
        sentiment=sentiment,
        raw_text=raw_text
    )
