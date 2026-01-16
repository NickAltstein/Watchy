"""
Real-Time WebSocket Server for Watch Marketplace

Provides live updates for:
- New deal notifications
- Price updates
- Listing status changes
- Chat messages

Architecture:
- FastAPI WebSocket connections
- Redis Pub/Sub for multi-instance coordination
- Room-based broadcasting (per user, per listing, global)
"""

import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect, Depends
from fastapi.routing import APIRouter
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Pydantic models for messages
class WSMessage(BaseModel):
    """Base WebSocket message"""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = datetime.utcnow()

class NewListingMessage(BaseModel):
    """New listing notification"""
    type: str = "new_listing"
    listing_id: int
    brand: str
    model: str
    price_usd: int
    deal_score: float
    image_url: Optional[str]
    sentiment: str  # WTS/WTB/WTT

class PriceUpdateMessage(BaseModel):
    """Price update notification"""
    type: str = "price_update"
    ref_number: str
    old_price: int
    new_price: int
    change_percent: float

class ChatMessage(BaseModel):
    """Chat message notification"""
    type: str = "chat_message"
    conversation_id: int
    sender_id: int
    sender_name: str
    message: str
    timestamp: datetime


class ConnectionManager:
    """
    Manages WebSocket connections with Redis Pub/Sub for multi-instance support.
    
    Features:
    - Room-based connections (users can subscribe to specific topics)
    - Redis Pub/Sub for cross-instance communication
    - Automatic reconnection handling
    - Heartbeat/ping-pong for connection health
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.active_connections: Dict[str, Set[WebSocket]] = {}  # room_id -> set of websockets
        self.user_connections: Dict[int, WebSocket] = {}  # user_id -> websocket
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self._listener_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Initialize Redis connection and start listening"""
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe("deals:new", "prices:update", "chat:messages")
        self._listener_task = asyncio.create_task(self._listen_to_redis())
        logger.info("WebSocket ConnectionManager started")
        
    async def stop(self):
        """Cleanup connections"""
        if self._listener_task:
            self._listener_task.cancel()
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        logger.info("WebSocket ConnectionManager stopped")
    
    async def _listen_to_redis(self):
        """Listen to Redis Pub/Sub and broadcast to connected clients"""
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    data = json.loads(message["data"])
                    
                    # Broadcast based on channel
                    if channel == "deals:new":
                        await self.broadcast_to_room("global_deals", data)
                    elif channel == "prices:update":
                        await self.broadcast_to_room("global_prices", data)
                    elif channel == "chat:messages":
                        # Send to specific user
                        user_id = data.get("recipient_id")
                        if user_id:
                            await self.send_to_user(user_id, data)
        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
        except Exception as e:
            logger.error(f"Error in Redis listener: {e}")
    
    async def connect(self, websocket: WebSocket, user_id: int, rooms: list[str]):
        """
        Connect a new WebSocket client
        
        Args:
            websocket: FastAPI WebSocket instance
            user_id: User ID for this connection
            rooms: List of rooms to subscribe to (e.g., ["global_deals", "user_123"])
        """
        await websocket.accept()
        
        # Add to user connections
        self.user_connections[user_id] = websocket
        
        # Add to rooms
        for room in rooms:
            if room not in self.active_connections:
                self.active_connections[room] = set()
            self.active_connections[room].add(websocket)
        
        logger.info(f"User {user_id} connected to rooms: {rooms}")
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "rooms": rooms,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def disconnect(self, websocket: WebSocket, user_id: int):
        """Disconnect a WebSocket client"""
        # Remove from user connections
        if user_id in self.user_connections:
            del self.user_connections[user_id]
        
        # Remove from all rooms
        for room_id, connections in self.active_connections.items():
            connections.discard(websocket)
        
        logger.info(f"User {user_id} disconnected")
    
    async def send_to_user(self, user_id: int, message: dict):
        """Send message to specific user"""
        if user_id in self.user_connections:
            websocket = self.user_connections[user_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
    
    async def broadcast_to_room(self, room_id: str, message: dict):
        """Broadcast message to all clients in a room"""
        if room_id not in self.active_connections:
            return
        
        disconnected = set()
        for websocket in self.active_connections[room_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to room {room_id}: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected clients
        self.active_connections[room_id] -= disconnected
    
    async def publish_new_listing(self, listing_data: dict):
        """Publish new listing to Redis (will be broadcast to all instances)"""
        if self.redis_client:
            await self.redis_client.publish("deals:new", json.dumps(listing_data))
    
    async def publish_price_update(self, price_data: dict):
        """Publish price update to Redis"""
        if self.redis_client:
            await self.redis_client.publish("prices:update", json.dumps(price_data))
    
    async def publish_chat_message(self, message_data: dict):
        """Publish chat message to Redis"""
        if self.redis_client:
            await self.redis_client.publish("chat:messages", json.dumps(message_data))


# Global connection manager instance
manager = ConnectionManager()

# FastAPI router
router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/deals")
async def websocket_deals_endpoint(
    websocket: WebSocket,
    user_id: int,
    deal_score_min: int = 70
):
    """
    WebSocket endpoint for real-time deal notifications
    
    Query params:
    - user_id: User ID (from JWT token in production)
    - deal_score_min: Minimum deal score to receive (default: 70)
    """
    rooms = ["global_deals"]
    
    await manager.connect(websocket, user_id, rooms)
    
    try:
        while True:
            # Receive messages from client (ping/pong, subscription changes)
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
            elif message.get("type") == "subscribe":
                # Add new room subscription
                new_room = message.get("room")
                if new_room:
                    if new_room not in manager.active_connections:
                        manager.active_connections[new_room] = set()
                    manager.active_connections[new_room].add(websocket)
                    logger.info(f"User {user_id} subscribed to {new_room}")
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(websocket, user_id)


@router.websocket("/prices/{ref_number}")
async def websocket_price_endpoint(
    websocket: WebSocket,
    ref_number: str,
    user_id: int
):
    """
    WebSocket endpoint for real-time price updates for a specific watch reference
    
    Path params:
    - ref_number: Watch reference number (e.g., "126610LN")
    
    Query params:
    - user_id: User ID
    """
    room = f"price:{ref_number}"
    
    await manager.connect(websocket, user_id, [room])
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(websocket, user_id)


# Utility functions for triggering broadcasts (to be called from other modules)
async def notify_new_listing(listing_data: dict):
    """Call this when a new listing is created"""
    await manager.publish_new_listing(listing_data)


async def notify_price_update(price_data: dict):
    """Call this when prices are updated"""
    await manager.publish_price_update(price_data)


async def notify_chat_message(message_data: dict):
    """Call this when a new chat message is sent"""
    await manager.publish_chat_message(message_data)


# Server-Sent Events (SSE) alternative for browsers that prefer it
@router.get("/sse/deals")
async def sse_deals_endpoint(user_id: int, deal_score_min: int = 70):
    """
    Server-Sent Events endpoint for deal notifications
    
    Alternative to WebSocket for simpler clients
    """
    async def event_generator():
        # Subscribe to Redis channel
        redis_client = await redis.from_url(manager.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("deals:new")
        
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    
                    # Filter by deal score
                    if data.get("deal_score", 0) >= deal_score_min:
                        yield {
                            "event": "new_deal",
                            "data": json.dumps(data)
                        }
        finally:
            await pubsub.unsubscribe()
            await redis_client.close()
    
    from fastapi.responses import StreamingResponse
    return StreamingResponse(event_generator(), media_type="text/event-stream")
