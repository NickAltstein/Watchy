"""
Unit tests for AI Parser
Tests with sample messages and mocked AI responses
"""

import pytest
import asyncio
from ai_parser import AIParser, AIParserConfig, WatchExtraction

# Sample test messages
SAMPLE_MESSAGES = [
    {
        "text": "WTS Rolex Submariner 126610LN from 2023. Full set with box and papers. Mint condition. $14,500",
        "expected_brand": "Rolex",
        "expected_model": "Submariner",
        "expected_ref": "126610LN",
        "expected_sentiment": "WTS",
    },
    {
        "text": "AP Royal Oak 15500ST blue dial. 2021 card. Excellent condition. $32k",
        "expected_brand": "Audemars Piguet",
        "expected_model": "Royal Oak",
        "expected_ref": "15500ST",
        "expected_sentiment": "WTS",
    },
    {
        "text": "ISO Patek 5711/1A, any year, full set preferred. Budget 85k",
        "expected_brand": "Patek Philippe",
        "expected_model": "Nautilus",
        "expected_ref": "5711/1A",
        "expected_sentiment": "WTB",
    },
    {
        "text": "Check out this cool video",
        "expected_status": "ignore",
    },
]


@pytest.fixture
async def parser():
    """Create parser instance for testing"""
    config = AIParserConfig(
        openai_api_key="test_key",
        anthropic_api_key="test_key",
        redis_url="redis://localhost:6379",
        cache_ttl=3600,
        confidence_threshold=0.6,
    )
    
    parser = AIParser(config)
    try:
        await parser.initialize()
    except:
        pass  # Redis may not be available in tests
    
    yield parser
    
    await parser.close()


@pytest.mark.asyncio
async def test_watch_message_detection(parser):
    """Test detection of watch-related messages"""
    assert parser._is_watch_message("WTS Rolex Submariner") == True
    assert parser._is_watch_message("ISO Patek Philippe") == True
    assert parser._is_watch_message("Hello how are you") == False
    assert parser._is_watch_message("Check out this video") == False


@pytest.mark.asyncio
async def test_cache_key_generation(parser):
    """Test cache key generation"""
    key1 = parser._compute_cache_key("test message", None)
    key2 = parser._compute_cache_key("test message", None)
    key3 = parser._compute_cache_key("different message", None)
    
    assert key1 == key2
    assert key1 != key3
    assert len(key1) == 32  # MD5 hash length


@pytest.mark.asyncio
async def test_system_prompt_generation(parser):
    """Test system prompt contains key terminology"""
    prompt = parser._build_system_prompt()
    
    assert "NIB" in prompt
    assert "B+P" in prompt
    assert "CONDITION SCORING" in prompt
    assert "WTS" in prompt
    assert "WTB" in prompt


@pytest.mark.asyncio
async def test_few_shot_examples(parser):
    """Test few-shot examples are valid"""
    examples = parser._build_few_shot_examples()
    
    assert len(examples) >= 3
    for example in examples:
        assert "user" in example
        assert "assistant" in example
        # Validate JSON in assistant response
        import json
        parsed = json.loads(example["assistant"])
        assert "brand" in parsed
        assert "model" in parsed
        assert "sentiment" in parsed


def test_watch_extraction_validation():
    """Test WatchExtraction model validation"""
    # Valid extraction
    extraction = WatchExtraction(
        brand="Rolex",
        model="Submariner",
        ref_number="126610LN",
        condition="Mint",
        condition_score=9,
        price_usd=14500,
        sentiment="WTS",
    )
    
    assert extraction.brand == "Rolex"
    assert extraction.condition_score == 9
    
    # Test brand normalization
    extraction2 = WatchExtraction(
        brand="ap",
        model="Royal Oak",
        condition="Excellent",
        condition_score=8,
    )
    
    assert extraction2.brand == "Audemars Piguet"


def test_price_extraction():
    """Test price extraction from various formats"""
    from ai_parser import extract_price_from_text
    
    assert extract_price_from_text("$17,500") == 17500
    assert extract_price_from_text("17.5k") == 17500
    assert extract_price_from_text("17500++") == 17500
    assert extract_price_from_text("Price: $32,000 net") == 32000


@pytest.mark.asyncio
async def test_parser_stats(parser):
    """Test statistics tracking"""
    stats = parser.get_stats()
    
    assert 'total_parsed' in stats
    assert 'gpt4_used' in stats
    assert 'claude_used' in stats
    assert 'cache_hits' in stats
    assert 'errors' in stats
    assert 'cache_enabled' in stats
    assert 'claude_enabled' in stats


@pytest.mark.asyncio
async def test_non_watch_message_handling(parser):
    """Test that non-watch messages return ignore status"""
    result = await parser.parse("Hey, check out this funny video!")
    
    assert result.status == "ignore"
    assert result.confidence == 1.0
    assert result.ai_model_used == "rule-based"


if __name__ == "__main__":
    # Run simple test
    async def run_simple_test():
        config = AIParserConfig(
            openai_api_key="test_key",
            redis_url="redis://localhost:6379",
        )
        parser = AIParser(config)
        
        print("Testing watch message detection...")
        assert parser._is_watch_message("WTS Rolex Submariner") == True
        print("✅ Watch message detection works")
        
        print("Testing cache key generation...")
        key = parser._compute_cache_key("test", None)
        assert len(key) == 32
        print(f"✅ Cache key generation works: {key}")
        
        print("Testing prompt generation...")
        prompt = parser._build_system_prompt()
        assert len(prompt) > 100
        print(f"✅ Prompt generation works ({len(prompt)} chars)")
        
        print("\nAll basic tests passed! ✅")
    
    asyncio.run(run_simple_test())
