"""
Tests for price history and prediction functionality.
"""

import pytest
import random
from datetime import datetime, timedelta
from price_history import (
    PriceHistoryAnalyzer,
    PricePoint,
    ConditionCategory,
)


class TestPriceHistoryAnalyzer:
    """Test suite for PriceHistoryAnalyzer"""
    
    def setup_method(self):
        """Setup for each test"""
        self.analyzer = PriceHistoryAnalyzer()
    
    def test_initialization(self):
        """Test analyzer initializes correctly"""
        assert self.analyzer is not None
    
    def test_calculate_trend_rising(self):
        """Test trend calculation for rising prices"""
        prices = [10000, 10500, 11000, 11500, 12000]
        timestamps = [
            datetime.now() - timedelta(days=i*10)
            for i in range(4, -1, -1)
        ]
        
        direction, strength = self.analyzer.calculate_trend(prices, timestamps)
        
        assert direction == "up"
        assert strength > 0.5  # Should have decent confidence
    
    def test_calculate_trend_falling(self):
        """Test trend calculation for falling prices"""
        prices = [12000, 11500, 11000, 10500, 10000]
        timestamps = [
            datetime.now() - timedelta(days=i*10)
            for i in range(4, -1, -1)
        ]
        
        direction, strength = self.analyzer.calculate_trend(prices, timestamps)
        
        assert direction == "down"
        assert strength > 0.5
    
    def test_calculate_trend_stable(self):
        """Test trend calculation for stable prices"""
        prices = [10000, 10050, 9980, 10020, 10000]
        timestamps = [
            datetime.now() - timedelta(days=i*10)
            for i in range(4, -1, -1)
        ]
        
        direction, strength = self.analyzer.calculate_trend(prices, timestamps)
        
        assert direction == "stable"
    
    def test_calculate_trend_insufficient_data(self):
        """Test trend with insufficient data"""
        prices = [10000]
        timestamps = [datetime.now()]
        
        direction, strength = self.analyzer.calculate_trend(prices, timestamps)
        
        assert direction == "stable"
        assert strength == 0.0
    
    def test_calculate_volatility(self):
        """Test volatility calculation"""
        # Low volatility
        prices_low = [10000, 10050, 10020, 10040, 10030]
        volatility_low = self.analyzer.calculate_volatility(prices_low)
        
        # High volatility
        prices_high = [10000, 12000, 8000, 11000, 9000]
        volatility_high = self.analyzer.calculate_volatility(prices_high)
        
        assert volatility_high > volatility_low
        assert volatility_low > 0
    
    def test_calculate_volatility_single_price(self):
        """Test volatility with single price"""
        prices = [10000]
        volatility = self.analyzer.calculate_volatility(prices)
        
        assert volatility == 0.0
    
    def test_bollinger_bands(self):
        """Test Bollinger bands calculation"""
        prices = [10000 + i * 100 for i in range(30)]
        
        middle, upper, lower = self.analyzer.calculate_bollinger_bands(prices, window=20)
        
        assert len(middle) == len(prices)
        assert len(upper) == len(prices)
        assert len(lower) == len(prices)
        
        # Upper should be above middle, lower should be below
        for i in range(len(prices)):
            assert upper[i] >= middle[i]
            assert lower[i] <= middle[i]
    
    def test_bollinger_bands_insufficient_data(self):
        """Test Bollinger bands with less than window size"""
        prices = [10000, 10100, 10200]
        
        middle, upper, lower = self.analyzer.calculate_bollinger_bands(prices, window=20)
        
        # Should still return data
        assert len(middle) == len(prices)
        assert len(upper) == len(prices)
        assert len(lower) == len(prices)
    
    def test_predict_prices(self):
        """Test price prediction"""
        # Create upward trending prices
        prices = [10000 + i * 100 for i in range(30)]
        timestamps = [
            datetime.now() - timedelta(days=30-i)
            for i in range(30)
        ]
        
        predictions = self.analyzer.predict_prices(prices, timestamps, days_ahead=30)
        
        assert len(predictions) == 30
        assert all(p.predicted_price > 0 for p in predictions)
        assert all(0 <= p.confidence <= 1 for p in predictions)
        assert all(p.lower_bound <= p.predicted_price <= p.upper_bound for p in predictions)
        
        # Confidence should decrease over time
        assert predictions[0].confidence >= predictions[-1].confidence
    
    def test_predict_prices_insufficient_data(self):
        """Test prediction with insufficient data"""
        prices = [10000, 10100]
        timestamps = [datetime.now() - timedelta(days=1), datetime.now()]
        
        predictions = self.analyzer.predict_prices(prices, timestamps, days_ahead=30)
        
        # Should return empty list or handle gracefully
        assert isinstance(predictions, list)
    
    def test_analyze_history(self):
        """Test complete history analysis"""
        # Create sample price points
        price_points = []
        base_date = datetime.now() - timedelta(days=90)
        
        for i in range(90):
            price_points.append(PricePoint(
                timestamp=(base_date + timedelta(days=i)).isoformat(),
                price=10000 + i * 50,  # Rising prices
                deal_score=200,
                condition="EXCELLENT",
                seller_type="VERIFIED_DEALER",
                has_box=True,
                has_papers=True,
                sentiment="WTS",
                trade_id=i
            ))
        
        analysis = self.analyzer.analyze_history(price_points)
        
        assert analysis.trend_direction == "up"
        assert analysis.trend_strength > 0
        assert analysis.volatility > 0
        assert analysis.avg_price > 0
        # Should show positive 30d and 90d changes
        assert analysis.price_change_30d > 0
        assert analysis.price_change_90d > 0
    
    def test_analyze_history_empty(self):
        """Test analysis with no data"""
        analysis = self.analyzer.analyze_history([])
        
        assert analysis.trend_direction == "unknown"
        assert analysis.trend_strength == 0.0
        assert analysis.avg_price == 0.0
    
    def test_analyze_history_single_point(self):
        """Test analysis with single price point"""
        price_point = PricePoint(
            timestamp=datetime.now().isoformat(),
            price=10000,
            deal_score=200,
            condition="EXCELLENT",
            seller_type="UNKNOWN",
            has_box=False,
            has_papers=False,
            sentiment="WTS",
            trade_id=1
        )
        
        analysis = self.analyzer.analyze_history([price_point])
        
        # Should handle gracefully
        assert analysis.avg_price == 10000
        assert analysis.volatility == 0.0
    
    def test_price_point_to_dict(self):
        """Test PricePoint serialization"""
        point = PricePoint(
            timestamp="2024-01-01T00:00:00",
            price=15000,
            deal_score=250,
            condition="NIB",
            seller_type="VERIFIED_DEALER",
            has_box=True,
            has_papers=True,
            sentiment="WTS",
            trade_id=123
        )
        
        data = point.to_dict()
        
        assert data["timestamp"] == "2024-01-01T00:00:00"
        assert data["price"] == 15000
        assert data["deal_score"] == 250
        assert data["condition"] == "NIB"
        assert data["trade_id"] == 123
    
    def test_prediction_confidence_bounds(self):
        """Test that prediction confidence is within valid range"""
        prices = [10000 + i * 100 for i in range(50)]
        timestamps = [
            datetime.now() - timedelta(days=50-i)
            for i in range(50)
        ]
        
        predictions = self.analyzer.predict_prices(prices, timestamps, days_ahead=60)
        
        for pred in predictions:
            assert 0 <= pred.confidence <= 1, f"Confidence {pred.confidence} out of bounds"
            assert pred.lower_bound >= 0, "Lower bound cannot be negative"
            assert pred.upper_bound > pred.lower_bound, "Upper bound must be higher than lower"
    
    def test_flat_price_prediction(self):
        """Test prediction for flat/stable prices"""
        prices = [10000] * 30
        timestamps = [
            datetime.now() - timedelta(days=30-i)
            for i in range(30)
        ]
        
        predictions = self.analyzer.predict_prices(prices, timestamps, days_ahead=30)
        
        # Predictions should be close to 10000
        for pred in predictions:
            assert 9000 <= pred.predicted_price <= 11000
    
    def test_volatile_price_prediction(self):
        """Test prediction for volatile prices"""
        random.seed(42)
        
        prices = [10000 + random.randint(-1000, 1000) for _ in range(30)]
        timestamps = [
            datetime.now() - timedelta(days=30-i)
            for i in range(30)
        ]
        
        predictions = self.analyzer.predict_prices(prices, timestamps, days_ahead=30)
        
        # Should still produce predictions
        assert len(predictions) == 30
        # Confidence intervals should be wide
        for pred in predictions:
            interval_width = pred.upper_bound - pred.lower_bound
            assert interval_width > 100  # Should have wide interval for volatile data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
