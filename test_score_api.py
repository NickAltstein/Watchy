"""
Integration tests for the deal scoring API endpoint.

Tests the /score-deal endpoint with various scenarios.
"""

import pytest
import os
from fastapi.testclient import TestClient

# Set required environment variables
os.environ["OPENAI_API_KEY"] = "test_key"
os.environ["DEEPSEEK_API_KEY"] = "test_key"
os.environ["ADMIN_SECRET"] = "test_secret_1234567890"
os.environ["DEBUG"] = "true"

from main import app, TARGET_PRICES_CACHE


class TestScoreDealEndpoint:
    """Test the /score-deal API endpoint"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        # Populate cache with test data
        TARGET_PRICES_CACHE.update({
            "126610LN": 21500,
            "5711/1A-010": 85000,
            "116500LN": 12000,
        })
        return TestClient(app)
    
    def test_score_deal_basic(self, client):
        """Test basic deal scoring"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 16800
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["ref_number"] == "126610LN"
        assert data["listing_price"] == 16800
        assert data["market_price"] == 21500
        assert "score" in data
        assert "tier" in data
        assert "explanation" in data
        assert data["discount_percentage"] > 0
    
    def test_score_deal_with_condition(self, client):
        """Test scoring with condition details"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 16800,
            "condition": "NIB",
            "has_box": True,
            "has_papers": True,
            "is_full_set": True
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have better score with NIB and full set
        assert data["breakdown"]["condition_bonus"] > 0
        assert data["breakdown"]["inclusions_bonus"] > 0
    
    def test_score_deal_with_seller_info(self, client):
        """Test scoring with seller information"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 16800,
            "seller_type": "VERIFIED_DEALER",
            "seller_rating": 4.9,
            "seller_transaction_count": 150
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have seller bonus
        assert data["breakdown"]["seller_bonus"] > 0
        
        # Should have low risk
        assert data["risk_level"] in ["LOW", "MEDIUM"]
    
    def test_score_deal_with_risk_factors(self, client):
        """Test scoring with risk factors"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 10000,  # 50% off - suspicious
            "vague_photos": True,
            "new_seller_suspicious": True,
            "payment_red_flags": True
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have high risk and penalties
        assert data["risk_level"] in ["HIGH", "CRITICAL"]
        assert data["breakdown"]["risk_penalty"] > 0
        assert len(data["red_flags"]) > 0
    
    def test_score_deal_with_urgency(self, client):
        """Test scoring with urgency signals"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 16800,
            "quick_sale": True,
            "price_reduced": True,
            "motivated_seller": True
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have urgency bonus
        assert data["breakdown"]["urgency_bonus"] > 0
    
    def test_score_deal_with_market_trend(self, client):
        """Test scoring with market trend"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 16800,
            "market_trend": "RISING",
            "comparable_count": 50
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have market trend adjustment
        assert data["breakdown"]["market_trend_adjustment"] == 20
        
        # Should have high confidence
        assert data["confidence"] >= 80
    
    def test_score_deal_with_rarity(self, client):
        """Test scoring with rarity factor"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 16800,
            "rarity_score": 30
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have rarity bonus
        assert data["breakdown"]["rarity_bonus"] == 30
    
    def test_score_deal_with_arbitrage(self, client):
        """Test scoring with arbitrage calculation"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 16800,
            "calculate_arbitrage": {
                "chrono24": 21500,
                "ebay": 20000
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have arbitrage data if viable
        if data["arbitrage"]:
            assert "net_profit" in data["arbitrage"]
            assert "roi_percentage" in data["arbitrage"]
    
    def test_score_deal_unknown_reference(self, client):
        """Test scoring with unknown reference"""
        response = client.post("/score-deal", json={
            "ref_number": "UNKNOWN123",
            "listing_price": 10000
        })
        
        assert response.status_code == 404
        assert "No market price found" in response.json()["detail"]
    
    def test_score_deal_invalid_condition(self, client):
        """Test scoring with invalid condition"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 16800,
            "condition": "INVALID_CONDITION"
        })
        
        assert response.status_code in [400, 422]  # Bad request or validation error
    
    def test_score_deal_overpriced(self, client):
        """Test scoring an overpriced listing"""
        response = client.post("/score-deal", json={
            "ref_number": "126610LN",
            "listing_price": 30000  # Way above market
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be OVERPRICED tier
        assert data["tier"] == "OVERPRICED"
        assert data["score"] < 0
    
    def test_score_deal_complete_scenario(self, client):
        """Test a complete scoring scenario"""
        response = client.post("/score-deal", json={
            "ref_number": "5711/1A-010",
            "listing_price": 70000,
            "condition": "EXCELLENT",
            "has_box": True,
            "has_papers": True,
            "is_full_set": True,
            "seller_type": "ESTABLISHED_DEALER",
            "seller_rating": 4.7,
            "seller_transaction_count": 75,
            "market_trend": "STABLE",
            "comparable_count": 30,
            "rarity_score": 25
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all components are present
        assert data["status"] == "success"
        assert data["score"] > 0  # Should be positive discount
        assert data["tier"] in ["URGENT", "PUSH", "NORMAL", "SKIP"]
        assert len(data["explanation"]) > 0
        assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert "breakdown" in data
        assert len(data["recommendations"]) > 0
        
        # Verify breakdown has all fields
        breakdown = data["breakdown"]
        assert "base_score" in breakdown
        assert "condition_bonus" in breakdown
        assert "inclusions_bonus" in breakdown
        assert "seller_bonus" in breakdown
        assert "urgency_bonus" in breakdown
        assert "market_trend_adjustment" in breakdown
        assert "rarity_bonus" in breakdown
        assert "risk_penalty" in breakdown
        assert "final_score" in breakdown


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
