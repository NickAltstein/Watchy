"""
Multi-modal AI Parser for Watch Listings
Uses GPT-4o Vision for initial parsing and Claude Sonnet 4 for complex cases
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import time
from typing import Dict, Any, Optional, List, Literal, Tuple
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, validator
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from PIL import Image
import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class WatchExtraction(BaseModel):
    """Structured output for watch listing extraction"""
    brand: str = Field(..., description="Watch brand (e.g., Rolex, Patek Philippe)")
    model: str = Field(..., description="Watch model name")
    ref_number: Optional[str] = Field(None, description="Reference number")
    year: Optional[int] = Field(None, ge=1900, le=2030, description="Year of manufacture")
    condition: str = Field(..., description="Condition description")
    condition_score: int = Field(..., ge=1, le=10, description="Condition score 1-10")
    inclusions: List[str] = Field(default_factory=list, description="Included items (box, papers, etc.)")
    is_full_set: bool = Field(False, description="Has all original accessories")
    price_usd: Optional[int] = Field(None, description="Price in USD")
    currency_original: str = Field("USD", description="Original currency")
    sentiment: Literal["WTS", "WTB", "UNKNOWN"] = Field("WTS", description="Selling or buying")
    seller_type: Literal["dealer", "private", "unknown"] = Field("unknown")
    urgency_level: int = Field(1, ge=1, le=5, description="Urgency level 1-5")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Extraction confidence")
    ai_model_used: str = Field("gpt-4o", description="AI model used")
    processing_time_ms: int = Field(0, description="Processing time in milliseconds")
    extracted_from: Literal["text", "image", "both"] = Field("text")
    status: Literal["success", "ignore", "unclear"] = Field("success")
    raw_text_analyzed: Optional[str] = Field(None, description="Text that was analyzed")

    @validator('brand')
    def normalize_brand(cls, v):
        """Normalize brand names"""
        brand_map = {
            'ap': 'Audemars Piguet',
            'pp': 'Patek Philippe',
            'vc': 'Vacheron Constantin',
            'jlc': 'Jaeger-LeCoultre',
            'iwc': 'IWC',
        }
        return brand_map.get(v.lower(), v.title())

    @validator('condition_score')
    def validate_condition_score(cls, v, values):
        """Ensure condition score matches condition description"""
        condition = values.get('condition', '').lower()
        if 'mint' in condition or 'unworn' in condition or 'nib' in condition:
            return max(v, 9)
        elif 'excellent' in condition:
            return max(v, 8)
        return v


class AIParserConfig(BaseModel):
    """Configuration for AI Parser"""
    openai_api_key: str
    anthropic_api_key: Optional[str] = None
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 86400  # 24 hours
    confidence_threshold: float = 0.6
    use_claude_for_ambiguous: bool = True
    max_retries: int = 3
    timeout_seconds: int = 20


# =============================================================================
# AI PARSER CLASS
# =============================================================================

class AIParser:
    """
    Multi-modal AI parser for watch listings
    Uses GPT-4o for fast parsing and Claude Sonnet 4 for complex cases
    """
    
    def __init__(self, config: AIParserConfig):
        self.config = config
        self.openai_client = AsyncOpenAI(api_key=config.openai_api_key)
        self.anthropic_client = None
        if config.anthropic_api_key:
            self.anthropic_client = AsyncAnthropic(api_key=config.anthropic_api_key)
        
        # Redis for caching
        self.redis_client = None
        
        # Statistics
        self.stats = {
            'total_parsed': 0,
            'gpt4_used': 0,
            'claude_used': 0,
            'cache_hits': 0,
            'errors': 0,
        }
    
    async def initialize(self):
        """Initialize async resources"""
        try:
            self.redis_client = await redis.from_url(
                self.config.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("AI Parser initialized with Redis cache")
        except Exception as e:
            logger.warning(f"Redis connection failed, caching disabled: {e}")
            self.redis_client = None
    
    async def close(self):
        """Close async resources"""
        if self.redis_client:
            await self.redis_client.close()
    
    def _compute_cache_key(self, text: str, image_base64: Optional[str]) -> str:
        """Compute cache key for deduplication"""
        content = text + (image_base64 or "")
        return hashlib.md5(content.encode()).hexdigest()
    
    async def _get_cached_result(self, cache_key: str) -> Optional[Dict]:
        """Get cached result if available"""
        if not self.redis_client:
            return None
        
        try:
            cached = await self.redis_client.get(f"ai_parse:{cache_key}")
            if cached:
                self.stats['cache_hits'] += 1
                logger.debug(f"Cache hit for key {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")
        
        return None
    
    async def _cache_result(self, cache_key: str, result: Dict):
        """Cache parsing result"""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.setex(
                f"ai_parse:{cache_key}",
                self.config.cache_ttl,
                json.dumps(result)
            )
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with watch domain knowledge"""
        return """You are an expert watch trading analyst with deep knowledge of luxury watches. Your task is to extract structured information from watch listings.

WATCH TERMINOLOGY:
- NIB: New In Box (unworn)
- BNIB: Brand New In Box
- B+P: Box and Papers
- Full Set: Watch + box + papers + warranty card
- Naked: Watch only, no accessories
- Stickered: Still has protective stickers
- Service Papers: Documentation of servicing
- AD: Authorized Dealer
- Gray Market: Non-AD seller
- Flip: Reselling quickly for profit

CONDITION SCORING (1-10):
10: BNIB, stickered, never worn
9: Mint, like new, barely worn
8: Excellent, light wear
7: Very good, normal wear
6: Good, visible wear
5: Average, heavy wear
4-1: Poor to damaged

REFERENCE NUMBER PATTERNS:
- Rolex: 6 digits (e.g., 126610, 116500)
- Patek Philippe: XXXX/XXX format (e.g., 5711/1A)
- Audemars Piguet: XXXXX format (e.g., 15500)
- Omega: XXX.XX.XX.XX format

PRICE FORMATS TO UNDERSTAND:
- 17.5k = $17,500
- 17500++ = $17,500 or best offer
- $17,5k = $17,500 (European format)
- net = after dealer fees

SENTIMENT DETECTION:
- WTS: Want To Sell, For Sale, Selling
- WTB: Want To Buy, Looking For, ISO (In Search Of)

Extract all available information with high accuracy. Return "ignore" status for non-watch messages."""

    def _build_few_shot_examples(self) -> List[Dict[str, str]]:
        """Build few-shot examples for better parsing"""
        return [
            {
                "user": "WTS Rolex Submariner 126610LN from 2023. Full set with box and papers. Mint condition, worn twice. $14,500 net.",
                "assistant": json.dumps({
                    "brand": "Rolex",
                    "model": "Submariner",
                    "ref_number": "126610LN",
                    "year": 2023,
                    "condition": "Mint condition, worn twice",
                    "condition_score": 9,
                    "inclusions": ["box", "papers"],
                    "is_full_set": True,
                    "price_usd": 14500,
                    "currency_original": "USD",
                    "sentiment": "WTS",
                    "seller_type": "private",
                    "urgency_level": 2,
                    "confidence": 0.95,
                    "extracted_from": "text",
                    "status": "success"
                })
            },
            {
                "user": "AP Royal Oak 15500ST white dial. 2021 card, B+P. Excellent condition, some desk diving marks. Looking for $32k. Quick sale!",
                "assistant": json.dumps({
                    "brand": "Audemars Piguet",
                    "model": "Royal Oak",
                    "ref_number": "15500ST",
                    "year": 2021,
                    "condition": "Excellent condition, some desk diving marks",
                    "condition_score": 8,
                    "inclusions": ["box", "papers", "warranty"],
                    "is_full_set": True,
                    "price_usd": 32000,
                    "currency_original": "USD",
                    "sentiment": "WTS",
                    "seller_type": "private",
                    "urgency_level": 4,
                    "confidence": 0.92,
                    "extracted_from": "text",
                    "status": "success"
                })
            },
            {
                "user": "ISO Patek 5711/1A blue dial, any year, preferably full set. Budget up to 85k.",
                "assistant": json.dumps({
                    "brand": "Patek Philippe",
                    "model": "Nautilus",
                    "ref_number": "5711/1A",
                    "condition": "Not specified - buying",
                    "condition_score": 7,
                    "inclusions": [],
                    "is_full_set": False,
                    "price_usd": 85000,
                    "currency_original": "USD",
                    "sentiment": "WTB",
                    "seller_type": "unknown",
                    "urgency_level": 2,
                    "confidence": 0.90,
                    "extracted_from": "text",
                    "status": "success"
                })
            },
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def _parse_with_gpt4(
        self,
        text: str,
        image_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        """Parse using GPT-4o (with vision if image provided)"""
        start_time = time.time()
        
        messages = [
            {"role": "system", "content": self._build_system_prompt()}
        ]
        
        # Add few-shot examples
        for example in self._build_few_shot_examples():
            messages.append({"role": "user", "content": example["user"]})
            messages.append({"role": "assistant", "content": example["assistant"]})
        
        # Add the actual message
        if image_base64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Extract watch details from this message: {text}"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "high"
                        }
                    }
                ]
            })
        else:
            messages.append({
                "role": "user",
                "content": f"Extract watch details from this message: {text}"
            })
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            result['ai_model_used'] = 'gpt-4o'
            result['processing_time_ms'] = int((time.time() - start_time) * 1000)
            result['extracted_from'] = 'both' if image_base64 else 'text'
            
            self.stats['gpt4_used'] += 1
            return result
            
        except Exception as e:
            logger.error(f"GPT-4 parsing error: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def _parse_with_claude(
        self,
        text: str,
        image_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        """Parse using Claude Sonnet 4 for complex cases"""
        if not self.anthropic_client:
            raise ValueError("Claude API key not configured")
        
        start_time = time.time()
        
        system_prompt = self._build_system_prompt()
        
        # Build message content
        content = []
        
        if image_base64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_base64,
                }
            })
        
        content.append({
            "type": "text",
            "text": f"""Extract watch details from this message and return as JSON:

{text}

Use this exact JSON structure:
{{
    "brand": "string",
    "model": "string",
    "ref_number": "string or null",
    "year": number or null,
    "condition": "string",
    "condition_score": number (1-10),
    "inclusions": ["array of strings"],
    "is_full_set": boolean,
    "price_usd": number or null,
    "currency_original": "string",
    "sentiment": "WTS" or "WTB" or "UNKNOWN",
    "seller_type": "dealer" or "private" or "unknown",
    "urgency_level": number (1-5),
    "confidence": number (0.0-1.0),
    "extracted_from": "text" or "image" or "both",
    "status": "success" or "ignore" or "unclear"
}}"""
        })
        
        try:
            response = await self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                temperature=0.1,
                system=system_prompt,
                messages=[{"role": "user", "content": content}]
            )
            
            # Extract JSON from response
            response_text = response.content[0].text
            
            # Try to extract JSON if wrapped in markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(response_text)
            result['ai_model_used'] = 'claude-sonnet-4'
            result['processing_time_ms'] = int((time.time() - start_time) * 1000)
            
            self.stats['claude_used'] += 1
            return result
            
        except Exception as e:
            logger.error(f"Claude parsing error: {e}")
            raise
    
    def _is_watch_message(self, text: str) -> bool:
        """Quick check if message is about watches"""
        watch_keywords = [
            'rolex', 'patek', 'audemars', 'omega', 'iwc', 'cartier',
            'wts', 'wtb', 'fs', 'for sale', 'looking for', 'iso',
            'submariner', 'daytona', 'nautilus', 'royal oak',
            'watch', 'timepiece', 'ref', 'box', 'papers'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in watch_keywords)
    
    async def parse(
        self,
        text: str,
        image_base64: Optional[str] = None,
        force_claude: bool = False
    ) -> WatchExtraction:
        """
        Parse watch listing from text and optional image
        
        Args:
            text: Message text
            image_base64: Optional base64-encoded image
            force_claude: Force using Claude instead of GPT-4
        
        Returns:
            WatchExtraction: Structured extraction result
        """
        start_time = time.time()
        
        try:
            # Quick check for non-watch messages
            if not self._is_watch_message(text) and not image_base64:
                return WatchExtraction(
                    brand="N/A",
                    model="N/A",
                    condition="N/A",
                    condition_score=1,
                    status="ignore",
                    confidence=1.0,
                    ai_model_used="rule-based",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    raw_text_analyzed=text[:200]
                )
            
            # Check cache
            cache_key = self._compute_cache_key(text, image_base64)
            cached_result = await self._get_cached_result(cache_key)
            if cached_result:
                logger.info(f"Using cached result for message")
                return WatchExtraction(**cached_result)
            
            # Parse with AI
            try:
                if force_claude or (self.config.use_claude_for_ambiguous and image_base64):
                    result = await self._parse_with_claude(text, image_base64)
                else:
                    result = await self._parse_with_gpt4(text, image_base64)
                
                # Validate and convert to Pydantic model
                result['raw_text_analyzed'] = text[:200]
                extraction = WatchExtraction(**result)
                
                # If confidence is low and Claude is available, try Claude
                if (extraction.confidence < self.config.confidence_threshold and 
                    not force_claude and 
                    self.anthropic_client and
                    self.config.use_claude_for_ambiguous):
                    
                    logger.info(f"Low confidence ({extraction.confidence}), retrying with Claude")
                    result = await self._parse_with_claude(text, image_base64)
                    result['raw_text_analyzed'] = text[:200]
                    extraction = WatchExtraction(**result)
                
                # Cache the result
                await self._cache_result(cache_key, extraction.dict())
                
                self.stats['total_parsed'] += 1
                return extraction
                
            except Exception as e:
                logger.error(f"AI parsing failed: {e}")
                self.stats['errors'] += 1
                
                # Return unclear status
                return WatchExtraction(
                    brand="Error",
                    model="Error",
                    condition=f"Parsing error: {str(e)[:100]}",
                    condition_score=1,
                    status="unclear",
                    confidence=0.0,
                    ai_model_used="error",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    raw_text_analyzed=text[:200]
                )
        
        except Exception as e:
            logger.error(f"Unexpected error in parse: {e}")
            self.stats['errors'] += 1
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get parser statistics"""
        return {
            **self.stats,
            'cache_enabled': self.redis_client is not None,
            'claude_enabled': self.anthropic_client is not None,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def preprocess_image(image_base64: str, max_size: Tuple[int, int] = (1024, 1024)) -> str:
    """Preprocess image for better OCR and AI parsing"""
    try:
        # Decode base64
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize if too large
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convert back to base64
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode()
        
    except Exception as e:
        logger.error(f"Image preprocessing error: {e}")
        return image_base64


def extract_price_from_text(text: str) -> Optional[int]:
    """Extract price from various formats"""
    import re
    
    # Patterns for price extraction
    patterns = [
        r'\$?(\d+),?(\d{3})',  # $17,500 or 17,500
        r'(\d+\.?\d*)k',  # 17.5k
        r'(\d+)\+\+',  # 17500++
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if 'k' in pattern:
                return int(float(match.group(1)) * 1000)
            elif '++' in pattern:
                return int(match.group(1))
            else:
                return int(match.group(1) + match.group(2))
    
    return None
