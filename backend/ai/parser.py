"""
Multi-Model AI Parsing Engine for Watch Listings

Implements a sophisticated parsing system that:
1. Filters spam using GPT-4o-mini
2. Parses listings using GPT-4o Vision (images) or GPT-4o-mini (text)
3. Deep analysis for high-value listings using Claude 3.5 Sonnet
4. Caches results in Redis for cost optimization
5. Handles retries and fallbacks gracefully
"""

import asyncio
import hashlib
import json
import logging
from datetime import timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

from openai import AsyncOpenAI, OpenAIError
from anthropic import AsyncAnthropic, AnthropicError
import redis.asyncio as redis
from pydantic import BaseModel, Field, validator
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

logger = logging.getLogger("watch-engine.ai.parser")


class Sentiment(str, Enum):
    """Listing sentiment/intent"""
    WTS = "WTS"  # Want to sell
    WTB = "WTB"  # Want to buy
    WTT = "WTT"  # Want to trade


class ParsedListing(BaseModel):
    """Structured output from AI parsing"""
    # Watch identification
    brand: str = Field(..., description="Watch brand (e.g., Rolex, Patek Philippe)")
    model: str = Field(..., description="Watch model name")
    ref_number: Optional[str] = Field(None, description="Reference number")
    
    # Specifications
    year: Optional[int] = Field(None, description="Year of manufacture", ge=1900, le=2100)
    condition: Optional[str] = Field(None, description="Condition description")
    condition_score: Optional[float] = Field(None, description="Condition score 0-10", ge=0, le=10)
    
    # Pricing
    price_usd: Optional[int] = Field(None, description="Asking price in USD", ge=0)
    
    # Inclusions
    has_box: bool = Field(False, description="Includes original box")
    has_papers: bool = Field(False, description="Includes papers/warranty card")
    is_full_set: bool = Field(False, description="Complete set with box and papers")
    
    # Classification
    sentiment: Sentiment = Field(..., description="Listing intent (WTS/WTB/WTT)")
    
    # Confidence and metadata
    ai_confidence: float = Field(..., description="Confidence score 0-1", ge=0, le=1)
    is_spam: bool = Field(False, description="Detected as spam")
    parsing_notes: Optional[str] = Field(None, description="Additional parsing notes")
    
    @validator('is_full_set', always=True)
    def validate_full_set(cls, v, values):
        """Auto-set full_set if both box and papers present"""
        if values.get('has_box') and values.get('has_papers'):
            return True
        return v


class AIModel(str, Enum):
    """Available AI models"""
    GPT4O_MINI = "gpt-4o-mini"
    GPT4O = "gpt-4o"
    CLAUDE_SONNET = "claude-3-5-sonnet-20241022"


class AIParser:
    """
    Multi-model AI parsing engine with cost optimization
    
    Strategy:
    - Use GPT-4o-mini for spam detection (fast, cheap)
    - Use GPT-4o-mini for text-only parsing (80% of cases)
    - Use GPT-4o Vision for image parsing
    - Use Claude Sonnet for deep analysis of $50K+ listings
    - Cache all responses in Redis (24 hours)
    """
    
    # Pricing per 1M tokens (approximate)
    COSTS = {
        AIModel.GPT4O_MINI: 0.15,
        AIModel.GPT4O: 2.50,
        AIModel.CLAUDE_SONNET: 3.00
    }
    
    # Few-shot examples for prompt
    FEW_SHOT_EXAMPLES = [
        {
            "input": "WTS Rolex Sub 126610LN. 2023. Unworn. Full set. $14,500 firm.",
            "output": {
                "brand": "Rolex",
                "model": "Submariner Date",
                "ref_number": "126610LN",
                "year": 2023,
                "condition": "unworn",
                "condition_score": 10.0,
                "has_box": True,
                "has_papers": True,
                "is_full_set": True,
                "price_usd": 14500,
                "sentiment": "WTS",
                "ai_confidence": 0.95
            }
        },
        {
            "input": "Looking for Patek 5711 blue dial. Budget 110k. Cash ready.",
            "output": {
                "brand": "Patek Philippe",
                "model": "Nautilus",
                "ref_number": "5711/1A-010",
                "price_usd": 110000,
                "sentiment": "WTB",
                "ai_confidence": 0.92
            }
        },
        {
            "input": "AP 15500 black dial. 2021. B+P. Some wear. 47k OBO",
            "output": {
                "brand": "Audemars Piguet",
                "model": "Royal Oak",
                "ref_number": "15500ST.OO.1220ST.01",
                "year": 2021,
                "condition": "good",
                "condition_score": 7.5,
                "has_box": True,
                "has_papers": True,
                "is_full_set": True,
                "price_usd": 47000,
                "sentiment": "WTS",
                "ai_confidence": 0.88
            }
        },
        {
            "input": "Daytona 116500LN white panda. NIB stickered. 38k",
            "output": {
                "brand": "Rolex",
                "model": "Daytona",
                "ref_number": "116500LN",
                "condition": "new in box",
                "condition_score": 10.0,
                "has_box": True,
                "has_papers": True,
                "is_full_set": True,
                "price_usd": 38000,
                "sentiment": "WTS",
                "ai_confidence": 0.94,
                "parsing_notes": "Stickered indicates unworn with protective stickers"
            }
        },
        {
            "input": "Check out my new Casio G-Shock! Like and subscribe!",
            "output": {
                "brand": "Unknown",
                "model": "Unknown",
                "sentiment": "WTS",
                "ai_confidence": 0.1,
                "is_spam": True,
                "parsing_notes": "Social media spam, not a serious listing"
            }
        }
    ]
    
    SYSTEM_PROMPT = """You are an expert watch dealer and appraiser with deep knowledge of luxury timepieces.

Your task is to parse watch listings from WhatsApp messages and extract structured information.

WATCH TERMINOLOGY:
- NIB: New In Box
- BNIB: Brand New In Box
- B+P: Box and Papers
- Full set: Watch + box + papers + all accessories
- Stickered: Unworn with protective stickers still on
- WTS: Want To Sell
- WTB: Want To Buy
- WTT: Want To Trade
- OBO: Or Best Offer

REFERENCE NUMBER KNOWLEDGE:
- Rolex: 6 digits (e.g., 126610LN, 116500LN)
- Patek Philippe: 4-5 digits with slash (e.g., 5711/1A-010)
- Audemars Piguet: 5 digits + code (e.g., 15500ST.OO.1220ST.01)
- Omega: Complex codes (e.g., 310.30.42.50.01.001)

CONDITION SCORING:
10.0 = New, unworn, stickered
9.0-9.5 = Excellent, barely worn
8.0-8.5 = Very good, light wear
7.0-7.5 = Good, normal wear
6.0-6.5 = Fair, visible wear
<6.0 = Poor, heavy wear or damage

OUTPUT FORMAT:
Return a valid JSON object matching the ParsedListing schema.
If information is missing or unclear, omit the field (don't guess).
Set ai_confidence based on clarity of information (0-1).
Mark obvious spam or off-topic messages as is_spam=true.

EXAMPLES:
[See few-shot examples in code]
"""

    def __init__(
        self,
        openai_api_key: str,
        anthropic_api_key: str,
        redis_url: str = "redis://localhost:6379",
        cache_ttl_hours: int = 24
    ):
        """
        Initialize AI parser with API clients
        
        Args:
            openai_api_key: OpenAI API key
            anthropic_api_key: Anthropic API key
            redis_url: Redis connection URL
            cache_ttl_hours: Cache TTL in hours
        """
        self.openai = AsyncOpenAI(api_key=openai_api_key)
        self.anthropic = AsyncAnthropic(api_key=anthropic_api_key)
        self.redis: Optional[redis.Redis] = None
        self.redis_url = redis_url
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        
        # Statistics
        self.stats = {
            "total_parses": 0,
            "cache_hits": 0,
            "spam_filtered": 0,
            "errors": 0,
            "cost_usd": 0.0
        }
    
    async def initialize(self):
        """Initialize Redis connection"""
        self.redis = await redis.from_url(self.redis_url, decode_responses=True)
        logger.info("AI Parser initialized with Redis cache")
    
    async def close(self):
        """Close connections"""
        if self.redis:
            await self.redis.close()
    
    def _generate_cache_key(self, text: str, image_base64: Optional[str] = None) -> str:
        """Generate cache key from input"""
        content = text
        if image_base64:
            content += f"|image:{hashlib.md5(image_base64.encode()).hexdigest()}"
        return f"ai_parse:{hashlib.sha256(content.encode()).hexdigest()}"
    
    async def _get_cached(self, cache_key: str) -> Optional[ParsedListing]:
        """Retrieve cached result"""
        if not self.redis:
            return None
        
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                self.stats["cache_hits"] += 1
                logger.debug(f"Cache hit for key {cache_key[:16]}...")
                return ParsedListing(**json.loads(cached))
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")
        
        return None
    
    async def _set_cached(self, cache_key: str, result: ParsedListing):
        """Store result in cache"""
        if not self.redis:
            return
        
        try:
            await self.redis.setex(
                cache_key,
                int(self.cache_ttl.total_seconds()),
                result.model_dump_json()  # Pydantic v2 method
            )
            logger.debug(f"Cached result for key {cache_key[:16]}...")
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")
    
    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((OpenAIError, AnthropicError)),
        reraise=True
    )
    async def _call_openai(
        self,
        model: AIModel,
        messages: List[Dict[str, Any]],
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Call OpenAI API with retry logic
        
        Args:
            model: Model to use
            messages: Message history
            response_format: Optional response format (for JSON mode)
            
        Returns:
            Model response text
        """
        kwargs = {
            "model": model.value,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2000
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = await self.openai.chat.completions.create(**kwargs)
        
        # Track approximate cost
        usage = response.usage
        if usage:
            cost = (usage.total_tokens / 1_000_000) * self.COSTS.get(model, 0)
            self.stats["cost_usd"] += cost
        
        return response.choices[0].message.content
    
    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(AnthropicError),
        reraise=True
    )
    async def _call_anthropic(
        self,
        messages: List[Dict[str, Any]],
        system: str
    ) -> str:
        """
        Call Anthropic Claude API with retry logic
        
        Args:
            messages: Message history
            system: System prompt
            
        Returns:
            Model response text
        """
        response = await self.anthropic.messages.create(
            model=AIModel.CLAUDE_SONNET.value,
            max_tokens=2000,
            temperature=0.1,
            system=system,
            messages=messages
        )
        
        # Track approximate cost
        usage = response.usage
        if usage:
            cost = (usage.input_tokens + usage.output_tokens) / 1_000_000 * self.COSTS[AIModel.CLAUDE_SONNET]
            self.stats["cost_usd"] += cost
        
        return response.content[0].text
    
    async def _is_spam(self, text: str) -> bool:
        """
        Fast spam detection using GPT-4o-mini
        
        Args:
            text: Message text
            
        Returns:
            True if spam detected
        """
        try:
            messages = [
                {"role": "system", "content": "You are a spam filter for watch trading groups. Return only 'SPAM' or 'VALID'."},
                {"role": "user", "content": f"Is this a legitimate watch listing or spam/off-topic?\n\n{text}"}
            ]
            
            response = await self._call_openai(AIModel.GPT4O_MINI, messages)
            return "SPAM" in response.upper()
            
        except Exception as e:
            logger.warning(f"Spam detection failed: {e}")
            return False  # Fail open - better to process than reject
    
    async def parse_listing(
        self,
        text: str,
        image_base64: Optional[str] = None,
        force_deep_analysis: bool = False
    ) -> ParsedListing:
        """
        Parse a watch listing from text and/or image
        
        Args:
            text: Message text
            image_base64: Optional base64-encoded image
            force_deep_analysis: Force use of Claude for deep analysis
            
        Returns:
            ParsedListing object with extracted information
        """
        self.stats["total_parses"] += 1
        
        # Check cache first
        cache_key = self._generate_cache_key(text, image_base64)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        try:
            # Step 1: Spam filter (fast pre-screening)
            if await self._is_spam(text):
                self.stats["spam_filtered"] += 1
                result = ParsedListing(
                    brand="Unknown",
                    model="Unknown",
                    sentiment=Sentiment.WTS,
                    ai_confidence=0.1,
                    is_spam=True,
                    parsing_notes="Filtered as spam"
                )
                await self._set_cached(cache_key, result)
                return result
            
            # Step 2: Choose parsing strategy
            if image_base64:
                # Use GPT-4o Vision for image parsing
                result = await self._parse_with_vision(text, image_base64)
            elif force_deep_analysis:
                # Use Claude for deep analysis
                result = await self._parse_with_claude(text)
            else:
                # Use GPT-4o-mini for text-only parsing
                result = await self._parse_with_text(text)
            
            # Cache result
            await self._set_cached(cache_key, result)
            
            return result
            
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Parsing failed: {e}", exc_info=True)
            
            # Return minimal fallback result
            return ParsedListing(
                brand="Unknown",
                model="Unknown",
                sentiment=Sentiment.WTS,
                ai_confidence=0.0,
                parsing_notes=f"Parsing error: {str(e)}"
            )
    
    async def _parse_with_text(self, text: str) -> ParsedListing:
        """Parse text-only listing using GPT-4o-mini"""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"Parse this watch listing:\n\n{text}"}
        ]
        
        # Add few-shot examples
        for example in self.FEW_SHOT_EXAMPLES[:3]:
            messages.insert(1, {"role": "user", "content": example["input"]})
            messages.insert(2, {"role": "assistant", "content": json.dumps(example["output"])})
        
        response = await self._call_openai(
            AIModel.GPT4O_MINI,
            messages,
            response_format={"type": "json_object"}
        )
        
        return ParsedListing(**json.loads(response))
    
    async def _parse_with_vision(self, text: str, image_base64: str) -> ParsedListing:
        """Parse listing with image using GPT-4o Vision"""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Parse this watch listing:\n\n{text}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            }
        ]
        
        response = await self._call_openai(
            AIModel.GPT4O,
            messages,
            response_format={"type": "json_object"}
        )
        
        return ParsedListing(**json.loads(response))
    
    async def _parse_with_claude(self, text: str) -> ParsedListing:
        """Deep analysis using Claude Sonnet (for high-value listings)"""
        messages = [
            {"role": "user", "content": f"Parse this watch listing:\n\n{text}"}
        ]
        
        response = await self._call_anthropic(messages, self.SYSTEM_PROMPT)
        
        # Extract JSON from response (Claude may wrap in markdown)
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        return ParsedListing(**json.loads(response))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get parser statistics"""
        cache_hit_rate = 0.0
        if self.stats["total_parses"] > 0:
            cache_hit_rate = self.stats["cache_hits"] / self.stats["total_parses"]
        
        return {
            **self.stats,
            "cache_hit_rate": cache_hit_rate
        }
