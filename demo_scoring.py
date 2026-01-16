#!/usr/bin/env python3
"""
Demonstration of the Advanced Deal Scoring Engine

Shows various scoring scenarios with different watch deals.
"""

from deal_scorer import (
    score_watch_deal,
    DealScorer,
    DealFactors,
    ConditionGrade,
    SellerType,
    MarketTrend,
)


def print_score_result(title: str, result):
    """Pretty print a scoring result"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")
    print(f"\n📊 SCORE: {result.score} | TIER: {result.tier.value} | RISK: {result.risk_assessment.level.value}")
    print(f"\n💰 Price Analysis:")
    print(f"   Listing: ${result.breakdown.discount_percentage:+.1f}% vs market")
    print(f"   Confidence: {result.confidence}%")
    print(f"\n📈 Breakdown:")
    print(f"   Base Score:        {result.breakdown.base_score:+4d}")
    print(f"   Condition Bonus:   {result.breakdown.condition_bonus:+4d}")
    print(f"   Inclusions Bonus:  {result.breakdown.inclusions_bonus:+4d}")
    print(f"   Seller Bonus:      {result.breakdown.seller_bonus:+4d}")
    print(f"   Urgency Bonus:     {result.breakdown.urgency_bonus:+4d}")
    print(f"   Market Adjustment: {result.breakdown.market_trend_adjustment:+4d}")
    print(f"   Rarity Bonus:      {result.breakdown.rarity_bonus:+4d}")
    print(f"   Risk Penalty:      {-result.breakdown.risk_penalty:+4d}")
    print(f"   {'─'*30}")
    print(f"   Final Score:       {result.breakdown.final_score:+4d}")
    print(f"\n💬 Explanation:")
    print(f"   {result.explanation}")
    
    if result.risk_assessment.red_flags:
        print(f"\n⚠️  Red Flags:")
        for flag in result.risk_assessment.red_flags:
            print(f"   • {flag}")
    
    if result.risk_assessment.concerns:
        print(f"\n⚡ Concerns:")
        for concern in result.risk_assessment.concerns:
            print(f"   • {concern}")
    
    print(f"\n✅ Recommendations:")
    for rec in result.risk_assessment.recommendations:
        print(f"   • {rec}")


def main():
    print("\n" + "="*80)
    print(" 🏆 Advanced Watch Deal Scoring Engine - Demonstration")
    print("="*80)
    
    # Example 1: URGENT deal - great price, NIB, verified dealer
    print("\n\n📍 SCENARIO 1: Exceptional Deal on Rolex Submariner")
    result1 = score_watch_deal(
        market_price=21500,
        listing_price=16800,
        condition="NIB",
        has_box=True,
        has_papers=True,
        seller_type="VERIFIED_DEALER",
        seller_rating=4.9,
        seller_transaction_count=150,
        market_trend="STABLE",
        comparable_count=47
    )
    print_score_result("Rolex 126610LN at $16,800 (Market: $21,500)", result1)
    
    # Example 2: Good deal but some risk
    print("\n\n📍 SCENARIO 2: Good Price but Unknown Seller")
    result2 = score_watch_deal(
        market_price=85000,
        listing_price=70000,
        condition="EXCELLENT",
        has_box=True,
        has_papers=True,
        seller_type="PRIVATE_NEW",
        seller_transaction_count=3,
        comparable_count=15
    )
    print_score_result("Patek Philippe 5711/1A at $70,000 (Market: $85,000)", result2)
    
    # Example 3: Too good to be true - HIGH RISK
    print("\n\n📍 SCENARIO 3: Suspicious Deal - Too Cheap")
    result3 = score_watch_deal(
        market_price=20000,
        listing_price=10000,
        condition="GOOD",
        has_box=False,
        has_papers=False,
        seller_type="UNKNOWN",
        vague_photos=True,
        payment_red_flags=True,
        comparable_count=8
    )
    print_score_result("Rolex GMT-Master II at $10,000 (Market: $20,000)", result3)
    
    # Example 4: Overpriced listing
    print("\n\n📍 SCENARIO 4: Overpriced Listing")
    result4 = score_watch_deal(
        market_price=12000,
        listing_price=15000,
        condition="FAIR",
        has_box=False,
        has_papers=True,
        seller_type="PRIVATE_NEW"
    )
    print_score_result("Rolex Submariner Date at $15,000 (Market: $12,000)", result4)
    
    # Example 5: Fair market price with bonuses
    print("\n\n📍 SCENARIO 5: At Market with Premium Condition")
    result5 = score_watch_deal(
        market_price=18000,
        listing_price=18000,
        condition="NIB",
        has_box=True,
        has_papers=True,
        seller_type="ESTABLISHED_DEALER",
        seller_rating=4.7,
        seller_transaction_count=85,
        comparable_count=30
    )
    print_score_result("Omega Speedmaster at $18,000 (Market: $18,000)", result5)
    
    # Example 6: Rare piece with urgency
    print("\n\n📍 SCENARIO 6: Rare Limited Edition - Rising Market")
    scorer = DealScorer()
    factors = DealFactors(
        market_price=150000,
        listing_price=125000,
        condition=ConditionGrade.UNWORN,
        has_box=True,
        has_papers=True,
        has_warranty=True,
        is_full_set=True,
        seller_type=SellerType.VERIFIED_DEALER,
        seller_rating=5.0,
        seller_transaction_count=200,
        quick_sale_indicated=True,
        motivated_seller=True,
        market_trend=MarketTrend.RISING,
        comparable_count=5,  # Rare piece
        rarity_score=30
    )
    result6 = scorer.score_deal(factors)
    print_score_result("Rare Patek Philippe Nautilus 5711 Tiffany at $125,000 (Market: $150,000)", result6)
    
    # Example 7: Arbitrage opportunity
    print("\n\n📍 SCENARIO 7: Arbitrage Opportunity - Buy WhatsApp, Sell Chrono24")
    arbitrage_platforms = {
        "chrono24": 21500,
        "ebay": 20000
    }
    result7 = scorer.score_deal(
        DealFactors(
            market_price=21500,
            listing_price=16800,
            condition=ConditionGrade.EXCELLENT,
            has_box=True,
            has_papers=True,
            is_full_set=True,
            seller_type=SellerType.VERIFIED_DEALER,
            comparable_count=40
        ),
        calculate_arbitrage_for=arbitrage_platforms
    )
    print_score_result("Rolex Sub with Arbitrage Analysis", result7)
    
    if result7.arbitrage:
        print(f"\n💵 Arbitrage Analysis:")
        print(f"   Buy Platform:  {result7.arbitrage.source_platform} @ ${result7.arbitrage.buy_price:,}")
        print(f"   Sell Platform: {result7.arbitrage.target_platform} @ ${result7.arbitrage.sell_price:,}")
        print(f"   Gross Profit:  ${result7.arbitrage.gross_profit:,}")
        print(f"   Total Costs:   ${result7.arbitrage.total_costs:,.2f}")
        print(f"   Net Profit:    ${result7.arbitrage.net_profit:,}")
        print(f"   ROI:           {result7.arbitrage.roi_percentage:.2f}%")
        print(f"   Viable:        {'✅ YES' if result7.arbitrage.is_viable else '❌ NO'}")
    
    print("\n\n" + "="*80)
    print(" 🎯 Demonstration Complete!")
    print("="*80)
    print("\n📚 The scoring engine considers:")
    print("   • Price vs market value (base score)")
    print("   • Watch condition and completeness")
    print("   • Seller reputation and history")
    print("   • Market trends and momentum")
    print("   • Urgency signals")
    print("   • Risk factors and red flags")
    print("   • Rarity and collectibility")
    print("   • Arbitrage opportunities")
    print("\n✨ Use the /score-deal API endpoint to score any watch deal!")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
