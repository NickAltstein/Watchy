"""
Integration module for AI Parser with FastAPI
Provides endpoint integration and request/response handling
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException
from pydantic import BaseModel, Field
import logging

from ai_parser import AIParser, AIParserConfig, WatchExtraction

logger = logging.getLogger(__name__)

# =============================================================================
# REQUEST/RESPONSE MODELS FOR API
# =============================================================================

class ParseRequest(BaseModel):
    """Request model for /parse-watch endpoint"""
    messageId: str = Field(..., description="Unique message ID")
    groupName: str = Field(..., description="WhatsApp group name")
    groupId: str = Field(..., description="WhatsApp group ID")
    senderId: str = Field(..., description="Sender WhatsApp ID")
    senderName: str = Field(..., description="Sender display name")
    timestamp: int = Field(..., description="Unix timestamp")
    text: str = Field(..., description="Message text content")
    hasImage: bool = Field(False, description="Whether message has image")
    imageBase64: Optional[str] = Field(None, description="Base64 encoded image")
    imageCaption: Optional[str] = Field(None, description="Image caption")
    quotedMessage: Optional[Dict] = Field(None, description="Quoted message object")
    isForwarded: bool = Field(False, description="Whether message is forwarded")
    messageType: str = Field("text", description="Message type")


class ParseResponse(BaseModel):
    """Response model for /parse-watch endpoint"""
    status: str = Field(..., description="Processing status")
    extraction: Optional[Dict[str, Any]] = Field(None, description="Extracted watch data")
    message_id: str = Field(..., description="Original message ID")
    processing_time_ms: int = Field(..., description="Processing time")
    cached: bool = Field(False, description="Whether result was cached")


# =============================================================================
# AI PARSER INTEGRATION CLASS
# =============================================================================

class AIParserIntegration:
    """
    Integration layer between FastAPI and AI Parser
    Handles request transformation and response formatting
    """
    
    def __init__(self, openai_api_key: str, anthropic_api_key: Optional[str] = None, redis_url: str = "redis://localhost:6379"):
        self.config = AIParserConfig(
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            redis_url=redis_url,
            cache_ttl=86400,  # 24 hours
            confidence_threshold=0.6,
            use_claude_for_ambiguous=True if anthropic_api_key else False,
        )
        self.parser = AIParser(self.config)
        self._initialized = False
    
    async def initialize(self):
        """Initialize the parser"""
        if not self._initialized:
            await self.parser.initialize()
            self._initialized = True
            logger.info("AI Parser integration initialized")
    
    async def close(self):
        """Close the parser"""
        if self._initialized:
            await self.parser.close()
            self._initialized = False
    
    async def parse_watch_message(self, request: ParseRequest) -> ParseResponse:
        """
        Parse a watch message from WhatsApp
        
        Args:
            request: ParseRequest with message data
        
        Returns:
            ParseResponse with extraction results
        """
        if not self._initialized:
            await self.initialize()
        
        start_time_import = request.timestamp
        
        try:
            # Combine text from message and caption
            full_text = request.text
            if request.imageCaption:
                full_text += "\n" + request.imageCaption
            
            if request.quotedMessage and request.quotedMessage.get("text"):
                full_text += "\nQuoted: " + request.quotedMessage["text"]
            
            # Parse with AI
            extraction = await self.parser.parse(
                text=full_text,
                image_base64=request.imageBase64 if request.hasImage else None
            )
            
            # Format response
            return ParseResponse(
                status=extraction.status,
                extraction=extraction.dict() if extraction.status == "success" else None,
                message_id=request.messageId,
                processing_time_ms=extraction.processing_time_ms,
                cached=False  # TODO: Track cache hits
            )
        
        except Exception as e:
            logger.error(f"Error parsing message {request.messageId}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse message: {str(e)}"
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get parser statistics"""
        return self.parser.get_stats()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def should_process_message(request: ParseRequest) -> bool:
    """
    Determine if a message should be processed
    Quick filtering before sending to AI
    """
    # Skip if no text and no image
    if not request.text and not request.hasImage:
        return False
    
    # Skip very short messages without images
    if len(request.text) < 10 and not request.hasImage:
        return False
    
    return True


def enrich_extraction_with_metadata(
    extraction: WatchExtraction,
    request: ParseRequest
) -> Dict[str, Any]:
    """
    Enrich extraction with WhatsApp metadata
    """
    result = extraction.dict()
    result.update({
        "whatsapp_message_id": request.messageId,
        "whatsapp_group": request.groupName,
        "whatsapp_group_id": request.groupId,
        "whatsapp_sender": request.senderName,
        "whatsapp_sender_id": request.senderId,
        "whatsapp_timestamp": request.timestamp,
        "message_is_forwarded": request.isForwarded,
    })
    return result
