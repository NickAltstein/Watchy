"""
Unit tests for the advanced deal scoring engine.

Tests cover:
- Base scoring calculations
- Multi-factor adjustments
- Tier classification
- Risk assessment
- Arbitrage calculations
- Edge cases and boundaries
"""

import pytest
from deal_scorer import (
    DealScorer,
    DealFactors,
    DealTier,
    RiskLevel,
    ConditionGrade,
    SellerType,
    MarketTrend,
    score_watch_deal,
    ScoringBreakdown,
)


class TestDealScorer:
    """Test suite for DealScorer class"""
    
    def setup_method(self):
        """Setup for each test"""
        self.scorer = DealScorer()
    
    def test_initialization(self):
        """Test scorer initializes correctly"""
        assert self.scorer.SCORE_MULTIPLIER == 1000
        assert self.scorer.MIN_SCORE == -500
        assert self.scorer.MAX_SCORE == 500
    
    def test_base_score_calculation(self):
        """Test base score calculation"""
        # 20% discount
        base_score, discount_pct = self.scorer.calculate_base_score(10000, 8000)
        assert base_score == 200
        assert discount_pct == 20.0
        
        # At market price
        base_score, discount_pct = self.scorer.calculate_base_score(10000, 10000)
        assert base_score == 0
        assert discount_pct == 0.0
        
        # 10% above market
        base_score, discount_pct = self.scorer.calculate_base_score(10000, 11000)
        assert base_score == -100
        assert discount_pct == -10.0
    
    def test_condition_bonuses(self):
        """Test condition bonus calculations"""
        # NIB condition
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            condition=ConditionGrade.NIB,
            has_papers=True,
            has_warranty=True
        )
        bonus = self.scorer.calculate_condition_bonus(factors)
        assert bonus == 25  # 20 base + 2 papers + 3 warranty
        
        # Unknown condition
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            condition=ConditionGrade.UNKNOWN
        )
        bonus = self.scorer.calculate_condition_bonus(factors)
        assert bonus == 0
    
    def test_inclusions_bonus(self):
        """Test inclusions bonus calculations"""
        # Full set
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            is_full_set=True
        )
        bonus = self.scorer.calculate_inclusions_bonus(factors)
        assert bonus == 15
        
        # Box and papers separately
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            has_box=True,
            has_papers=True
        )
        bonus = self.scorer.calculate_inclusions_bonus(factors)
        assert bonus == 13  # 5 + 8
        
        # No inclusions
        factors = DealFactors(
            market_price=10000,
            listing_price=8000
        )
        bonus = self.scorer.calculate_inclusions_bonus(factors)
        assert bonus == 0
    
    def test_seller_bonus(self):
        """Test seller reputation bonus"""
        # Verified dealer with high rating
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            seller_type=SellerType.VERIFIED_DEALER,
            seller_rating=4.9,
            seller_transaction_count=150
        )
        bonus = self.scorer.calculate_seller_bonus(factors)
        assert bonus == 10  # Maxed out (10 base + 2 txn + 2 rating, capped)
        
        # Unknown seller
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            seller_type=SellerType.UNKNOWN
        )
        bonus = self.scorer.calculate_seller_bonus(factors)
        assert bonus == 0
    
    def test_urgency_bonus(self):
        """Test urgency signals bonus"""
        # All urgency signals
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            quick_sale_indicated=True,
            price_reduced=True,
            motivated_seller=True
        )
        bonus = self.scorer.calculate_urgency_bonus(factors)
        assert bonus == 5  # Capped at 5
        
        # No urgency
        factors = DealFactors(
            market_price=10000,
            listing_price=8000
        )
        bonus = self.scorer.calculate_urgency_bonus(factors)
        assert bonus == 0
    
    def test_market_trend_adjustment(self):
        """Test market trend adjustments"""
        # Rising market
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            market_trend=MarketTrend.RISING
        )
        adjustment = self.scorer.calculate_market_adjustment(factors)
        assert adjustment == 20
        
        # Falling market
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            market_trend=MarketTrend.FALLING
        )
        adjustment = self.scorer.calculate_market_adjustment(factors)
        assert adjustment == -20
        
        # Stable/unknown market
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            market_trend=MarketTrend.STABLE
        )
        adjustment = self.scorer.calculate_market_adjustment(factors)
        assert adjustment == 0
    
    def test_risk_penalty(self):
        """Test risk penalty calculations"""
        # High risk factors
        factors = DealFactors(
            market_price=10000,
            listing_price=5000,  # 50% discount - too cheap
            vague_photos=True,
            new_seller_suspicious=True,
            payment_red_flags=True
        )
        penalty = self.scorer.calculate_risk_penalty(factors)
        assert penalty >= 50  # Should be high penalty
        
        # No risk factors
        factors = DealFactors(
            market_price=10000,
            listing_price=8000
        )
        penalty = self.scorer.calculate_risk_penalty(factors)
        assert penalty == 0
    
    def test_tier_classification(self):
        """Test deal tier classification"""
        assert self.scorer.classify_tier(450) == DealTier.URGENT
        assert self.scorer.classify_tier(350) == DealTier.URGENT
        assert self.scorer.classify_tier(250) == DealTier.PUSH
        assert self.scorer.classify_tier(200) == DealTier.PUSH
        assert self.scorer.classify_tier(150) == DealTier.NORMAL
        assert self.scorer.classify_tier(100) == DealTier.NORMAL
        assert self.scorer.classify_tier(50) == DealTier.SKIP
        assert self.scorer.classify_tier(0) == DealTier.SKIP
        assert self.scorer.classify_tier(-100) == DealTier.OVERPRICED
    
    def test_risk_assessment_low(self):
        """Test low risk assessment"""
        factors = DealFactors(
            market_price=10000,
            listing_price=8500,  # 15% discount - reasonable
            seller_type=SellerType.VERIFIED_DEALER,
            has_box=True,
            has_papers=True
        )
        risk = self.scorer.assess_risk(factors, 15.0)
        
        assert risk.level == RiskLevel.LOW
        assert len(risk.red_flags) == 0
        assert risk.score < 20
    
    def test_risk_assessment_critical(self):
        """Test critical risk assessment"""
        factors = DealFactors(
            market_price=10000,
            listing_price=4000,  # 60% discount - way too cheap
            seller_type=SellerType.PRIVATE_NEW,
            seller_transaction_count=0,
            vague_photos=True,
            payment_red_flags=True
        )
        risk = self.scorer.assess_risk(factors, 60.0)
        
        assert risk.level == RiskLevel.CRITICAL
        assert len(risk.red_flags) > 0
        assert risk.score >= 60
    
    def test_complete_scoring_urgent_deal(self):
        """Test complete scoring for a strong deal (PUSH tier with 22% discount)"""
        factors = DealFactors(
            market_price=21500,
            listing_price=16800,
            condition=ConditionGrade.NIB,
            has_box=True,
            has_papers=True,
            is_full_set=True,
            seller_type=SellerType.VERIFIED_DEALER,
            seller_rating=4.8,
            market_trend=MarketTrend.STABLE,
            comparable_count=47
        )
        
        result = self.scorer.score_deal(factors)
        
        # Should be PUSH tier (22% discount = 218 base + 47 bonuses = 265)
        assert result.tier == DealTier.PUSH
        assert result.score >= 200
        
        # Should have low risk
        assert result.risk_assessment.level in [RiskLevel.LOW, RiskLevel.MEDIUM]
        
        # Should have high confidence
        assert result.confidence >= 80
        
        # Breakdown should be populated
        assert result.breakdown.base_score > 0
        assert result.breakdown.condition_bonus > 0
        assert result.breakdown.inclusions_bonus > 0
        
        # Should have explanation
        assert len(result.explanation) > 0
        assert "PUSH" in result.explanation
    
    def test_complete_scoring_true_urgent_deal(self):
        """Test complete scoring for a true URGENT tier deal"""
        factors = DealFactors(
            market_price=20000,
            listing_price=13000,  # 35% discount
            condition=ConditionGrade.NIB,
            has_box=True,
            has_papers=True,
            is_full_set=True,
            seller_type=SellerType.VERIFIED_DEALER,
            seller_rating=4.9,
            seller_transaction_count=100,
            market_trend=MarketTrend.RISING,
            rarity_score=30,
            comparable_count=50
        )
        
        result = self.scorer.score_deal(factors)
        
        # Should be URGENT tier (35% discount + all bonuses)
        assert result.tier == DealTier.URGENT
        assert result.score >= 350
        
        # Should have low risk
        assert result.risk_assessment.level == RiskLevel.LOW
        
        # Should have high confidence
        assert result.confidence >= 90
        
        # Should have explanation mentioning URGENT
        assert "URGENT" in result.explanation
    
    def test_complete_scoring_overpriced(self):
        """Test complete scoring for overpriced listing"""
        factors = DealFactors(
            market_price=10000,
            listing_price=13000,  # 30% above market
            condition=ConditionGrade.FAIR
        )
        
        result = self.scorer.score_deal(factors)
        
        assert result.tier == DealTier.OVERPRICED
        assert result.score < 0
        assert "overpriced" in result.explanation.lower() or "avoid" in result.explanation.lower()
    
    def test_score_clamping(self):
        """Test that scores are clamped to [-500, 500]"""
        # Extreme discount with all bonuses
        factors = DealFactors(
            market_price=10000,
            listing_price=1000,  # 90% discount
            condition=ConditionGrade.NIB,
            has_box=True,
            has_papers=True,
            is_full_set=True,
            seller_type=SellerType.VERIFIED_DEALER,
            rarity_score=30
        )
        
        result = self.scorer.score_deal(factors)
        assert result.score <= 500
        
        # Extreme overpricing
        factors = DealFactors(
            market_price=10000,
            listing_price=20000  # 100% markup
        )
        
        result = self.scorer.score_deal(factors)
        assert result.score >= -500
    
    def test_arbitrage_calculation(self):
        """Test arbitrage opportunity calculation"""
        arb = self.scorer.calculate_arbitrage(
            buy_platform="whatsapp",
            sell_platform="chrono24",
            buy_price=16800,
            sell_price=21500
        )
        
        assert arb.source_platform == "whatsapp"
        assert arb.target_platform == "chrono24"
        assert arb.buy_price == 16800
        assert arb.sell_price == 21500
        assert arb.gross_profit == 4700
        assert arb.net_profit > 0
        assert arb.roi_percentage > 0
        
        # Should be viable (good profit and ROI)
        assert arb.is_viable
    
    def test_arbitrage_not_viable(self):
        """Test arbitrage that's not viable"""
        arb = self.scorer.calculate_arbitrage(
            buy_platform="whatsapp",
            sell_platform="chrono24",
            buy_price=20000,
            sell_price=20200  # Only $200 gross profit
        )
        
        # After fees, shipping, etc., this should not be viable
        assert not arb.is_viable
        assert arb.net_profit < 500 or arb.roi_percentage < 5
    
    def test_convenience_function(self):
        """Test the convenience scoring function"""
        result = score_watch_deal(
            market_price=21500,
            listing_price=16800,
            condition="NIB",
            has_box=True,
            has_papers=True,
            seller_type="VERIFIED_DEALER"
        )
        
        assert isinstance(result.score, int)
        assert result.tier in [DealTier.URGENT, DealTier.PUSH, DealTier.NORMAL]
        assert len(result.explanation) > 0
    
    def test_edge_case_zero_market_price(self):
        """Test that zero market price raises error"""
        with pytest.raises(ValueError):
            self.scorer.calculate_base_score(0, 5000)
    
    def test_edge_case_equal_prices(self):
        """Test scoring when prices are equal"""
        factors = DealFactors(
            market_price=10000,
            listing_price=10000
        )
        
        result = self.scorer.score_deal(factors)
        
        # Should be near SKIP tier (base score is 0)
        assert result.breakdown.base_score == 0
        assert result.tier in [DealTier.SKIP, DealTier.NORMAL]
    
    def test_explanation_generation_quality(self):
        """Test that explanations contain key information"""
        factors = DealFactors(
            market_price=21500,
            listing_price=16800,
            condition=ConditionGrade.NIB,
            has_box=True,
            has_papers=True,
            is_full_set=True,
            seller_type=SellerType.VERIFIED_DEALER,
            market_trend=MarketTrend.STABLE,
            comparable_count=47
        )
        
        result = self.scorer.score_deal(factors)
        explanation = result.explanation.lower()
        
        # Should mention key facts
        assert "below" in explanation or "discount" in explanation or "%"  in explanation
        assert "nib" in explanation or "condition" in explanation
        assert "full set" in explanation or "documentation" in explanation
    
    def test_confidence_scoring(self):
        """Test confidence score calculation"""
        # High confidence with many comparables
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            comparable_count=50,
            market_trend=MarketTrend.STABLE
        )
        result = self.scorer.score_deal(factors)
        assert result.confidence >= 80
        
        # Low confidence with few comparables and unknown trend
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            comparable_count=2,
            market_trend=MarketTrend.UNKNOWN
        )
        result = self.scorer.score_deal(factors)
        assert result.confidence < 60
    
    def test_rarity_bonus(self):
        """Test rarity score bonus"""
        factors = DealFactors(
            market_price=10000,
            listing_price=8000,
            rarity_score=30  # Maximum rarity
        )
        
        result = self.scorer.score_deal(factors)
        assert result.breakdown.rarity_bonus == 30
    
    def test_platform_fees(self):
        """Test platform fee calculations"""
        assert self.scorer.PLATFORM_FEES["whatsapp"] == 0.0
        assert self.scorer.PLATFORM_FEES["chrono24"] == 6.5
        assert self.scorer.PLATFORM_FEES["ebay"] == 12.9
    
    def test_multiple_risk_factors(self):
        """Test multiple risk factors compound correctly"""
        factors = DealFactors(
            market_price=10000,
            listing_price=5000,  # Too cheap
            vague_photos=True,
            new_seller_suspicious=True,
            payment_red_flags=True,
            contradictory_info=True
        )
        
        penalty = self.scorer.calculate_risk_penalty(factors)
        risk = self.scorer.assess_risk(factors, 50.0)
        
        # Should have maximum penalty
        assert penalty == 50
        
        # Should have critical risk
        assert risk.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert len(risk.red_flags) >= 3


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_minimum_price(self):
        """Test minimum valid price"""
        factors = DealFactors(
            market_price=1000,
            listing_price=1000
        )
        scorer = DealScorer()
        result = scorer.score_deal(factors)
        
        assert result.score == 0 or result.score > -500
    
    def test_very_high_prices(self):
        """Test with very high prices"""
        factors = DealFactors(
            market_price=500000,
            listing_price=400000
        )
        scorer = DealScorer()
        result = scorer.score_deal(factors)
        
        # 20% discount should give base score of 200
        assert result.breakdown.base_score == 200
    
    def test_all_unknown_factors(self):
        """Test scoring with all unknown/default factors"""
        factors = DealFactors(
            market_price=10000,
            listing_price=8000
        )
        scorer = DealScorer()
        result = scorer.score_deal(factors)
        
        # Should still produce valid score based on price alone
        assert -500 <= result.score <= 500
        assert result.tier != None
    
    def test_arbitrage_with_custom_platform(self):
        """Test arbitrage with platform not in fee list"""
        scorer = DealScorer()
        arb = scorer.calculate_arbitrage(
            buy_platform="custom_platform",
            sell_platform="another_custom",
            buy_price=10000,
            sell_price=12000
        )
        
        # Should use 0% or default fees
        assert arb.source_fees >= 0
        assert arb.net_profit > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
