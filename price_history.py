"""
Price History and Prediction Module

Provides historical price data, trend analysis, and ML-based price predictions
for luxury watch references.
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("watch-engine.price_history")

# Configuration constants
MIN_CONFIDENCE = 0.3
MAX_CONFIDENCE = 0.95
MIN_INTERVAL_WIDTH = 100  # Minimum price interval width in USD
INTERVAL_GROWTH_FACTOR = 10  # Days factor for interval growth
Z_SCORE_95_PERCENT = 1.96  # Z-score for 95% confidence interval
MAX_REFERENCES_COMPARISON = 5  # Maximum references for comparison


class ConditionCategory(str, Enum):
    """Watch condition categories for color coding"""
    NIB = "NIB"  # New in box - green
    EXCELLENT = "EXCELLENT"  # 9-10/10 - light green
    GOOD = "GOOD"  # 7-8/10 - yellow
    FAIR = "FAIR"  # 5-6/10 - orange
    POOR = "POOR"  # <5/10 - red
    UNKNOWN = "UNKNOWN"  # gray


@dataclass
class PricePoint:
    """Individual price data point"""
    timestamp: str
    price: int
    deal_score: int
    condition: str
    seller_type: str
    has_box: bool
    has_papers: bool
    sentiment: str
    trade_id: int
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp,
            "price": self.price,
            "deal_score": self.deal_score,
            "condition": self.condition,
            "seller_type": self.seller_type,
            "has_box": self.has_box,
            "has_papers": self.has_papers,
            "sentiment": self.sentiment,
            "trade_id": self.trade_id
        }


@dataclass
class PricePrediction:
    """Price prediction for a future date"""
    date: str
    predicted_price: int
    lower_bound: int
    upper_bound: int
    confidence: float
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "date": self.date,
            "predicted_price": self.predicted_price,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "confidence": self.confidence
        }


@dataclass
class TrendAnalysis:
    """Trend analysis results"""
    trend_direction: str  # "up", "down", "stable"
    trend_strength: float  # 0-1
    volatility: float  # standard deviation
    avg_price: float
    price_change_30d: float  # percentage
    price_change_90d: float  # percentage
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "trend_direction": self.trend_direction,
            "trend_strength": self.trend_strength,
            "volatility": self.volatility,
            "avg_price": self.avg_price,
            "price_change_30d": self.price_change_30d,
            "price_change_90d": self.price_change_90d
        }


class PriceHistoryAnalyzer:
    """Analyzes price history and generates predictions"""
    
    def __init__(self):
        """Initialize the analyzer"""
        logger.info("PriceHistoryAnalyzer initialized")
    
    def calculate_trend(self, prices: List[float], timestamps: List[datetime]) -> Tuple[str, float]:
        """
        Calculate price trend using linear regression.
        
        Returns:
            Tuple of (direction, strength) where direction is "up", "down", or "stable"
            and strength is 0-1 indicating confidence.
        """
        if len(prices) < 2:
            return "stable", 0.0
        
        # Convert timestamps to days from start
        days = [(t - timestamps[0]).days for t in timestamps]
        
        # Linear regression
        x = np.array(days)
        y = np.array(prices)
        
        # Calculate slope
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        
        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)
        
        if denominator == 0:
            return "stable", 0.0
        
        slope = numerator / denominator
        
        # Calculate R-squared for trend strength
        y_pred = slope * x + (y_mean - slope * x_mean)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y_mean) ** 2)
        
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        strength = max(0, min(1, r_squared))
        
        # Determine direction based on slope (as percentage of mean price)
        slope_pct = (slope / y_mean) * 100 if y_mean > 0 else 0
        
        if slope_pct > 0.1:  # Rising more than 0.1% per day
            direction = "up"
        elif slope_pct < -0.1:  # Falling more than 0.1% per day
            direction = "down"
        else:
            direction = "stable"
        
        return direction, strength
    
    def calculate_volatility(self, prices: List[float]) -> float:
        """Calculate price volatility (standard deviation)"""
        if len(prices) < 2:
            return 0.0
        
        return float(np.std(prices))
    
    def calculate_bollinger_bands(
        self,
        prices: List[float],
        window: int = 20,
        num_std: float = 2.0
    ) -> Tuple[List[float], List[float], List[float]]:
        """
        Calculate Bollinger Bands for volatility visualization.
        
        Returns:
            Tuple of (middle_band, upper_band, lower_band)
        """
        if len(prices) < window:
            # Not enough data, return simple bands
            avg = np.mean(prices)
            std = np.std(prices)
            middle = [avg] * len(prices)
            upper = [avg + num_std * std] * len(prices)
            lower = [avg - num_std * std] * len(prices)
            return middle, upper, lower
        
        middle_band = []
        upper_band = []
        lower_band = []
        
        for i in range(len(prices)):
            if i < window:
                # Use available data
                window_data = prices[:i+1]
            else:
                window_data = prices[i-window+1:i+1]
            
            ma = np.mean(window_data)
            std = np.std(window_data)
            
            middle_band.append(ma)
            upper_band.append(ma + num_std * std)
            lower_band.append(ma - num_std * std)
        
        return middle_band, upper_band, lower_band
    
    def predict_prices(
        self,
        historical_prices: List[float],
        historical_timestamps: List[datetime],
        days_ahead: int = 30
    ) -> List[PricePrediction]:
        """
        Predict future prices using simple trend extrapolation.
        
        This is a simple implementation. In production, you'd use more sophisticated
        ML models like ARIMA, Prophet, or LSTM neural networks.
        """
        if len(historical_prices) < 3:
            logger.warning("Not enough historical data for prediction")
            return []
        
        # Calculate trend
        days = np.array([(t - historical_timestamps[0]).days for t in historical_timestamps])
        prices = np.array(historical_prices)
        
        # Linear regression
        x_mean = np.mean(days)
        y_mean = np.mean(prices)
        
        numerator = np.sum((days - x_mean) * (prices - y_mean))
        denominator = np.sum((days - x_mean) ** 2)
        
        if denominator == 0:
            # No trend, predict flat
            slope = 0
        else:
            slope = numerator / denominator
        
        intercept = y_mean - slope * x_mean
        
        # Calculate prediction error (RMSE)
        y_pred = slope * days + intercept
        rmse = np.sqrt(np.mean((prices - y_pred) ** 2))
        
        # Generate predictions
        predictions = []
        last_day = days[-1]
        base_date = historical_timestamps[-1]
        
        # Calculate confidence based on R-squared and data amount
        ss_res = np.sum((prices - y_pred) ** 2)
        ss_tot = np.sum((prices - y_mean) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        base_confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, r_squared))
        data_confidence = min(1.0, len(historical_prices) / 30)  # More data = higher confidence
        
        for day in range(1, days_ahead + 1):
            future_day = last_day + day
            future_date = base_date + timedelta(days=day)
            
            # Predict price
            predicted_price = slope * future_day + intercept
            
            # Confidence decreases with distance into future
            time_decay = 1.0 - (day / (days_ahead * 2))  # Slower decay
            confidence = base_confidence * data_confidence * max(0.2, time_decay)
            
            # Calculate confidence interval (grows with time)
            # Use minimum interval width to ensure bounds are different
            interval_width = max(MIN_INTERVAL_WIDTH, rmse * (1 + day / INTERVAL_GROWTH_FACTOR))
            
            lower_bound = max(0, int(predicted_price - interval_width * Z_SCORE_95_PERCENT))
            upper_bound = int(predicted_price + interval_width * Z_SCORE_95_PERCENT)
            
            # Ensure upper bound is strictly greater than lower bound
            if upper_bound <= lower_bound:
                upper_bound = lower_bound + max(MIN_INTERVAL_WIDTH, int(predicted_price * 0.01))
            
            predictions.append(PricePrediction(
                date=future_date.strftime("%Y-%m-%d"),
                predicted_price=int(predicted_price),
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                confidence=round(confidence, 3)
            ))
        
        return predictions
    
    def analyze_history(
        self,
        price_points: List[PricePoint]
    ) -> TrendAnalysis:
        """
        Analyze price history and generate trend metrics.
        
        Args:
            price_points: List of historical price points
            
        Returns:
            TrendAnalysis object with trend metrics
        """
        if not price_points:
            return TrendAnalysis(
                trend_direction="unknown",
                trend_strength=0.0,
                volatility=0.0,
                avg_price=0.0,
                price_change_30d=0.0,
                price_change_90d=0.0
            )
        
        # Extract prices and timestamps
        prices = [p.price for p in price_points]
        # Parse timestamps safely - handle both with and without 'Z' suffix
        timestamps = []
        for p in price_points:
            ts_str = p.timestamp
            # Remove 'Z' if present and add timezone
            if ts_str.endswith('Z'):
                ts_str = ts_str[:-1] + '+00:00'
            # Try to parse, fallback to datetime.fromisoformat
            try:
                timestamps.append(datetime.fromisoformat(ts_str))
            except ValueError:
                # Fallback: try without timezone
                try:
                    timestamps.append(datetime.fromisoformat(ts_str.split('+')[0].split('Z')[0]))
                except ValueError:
                    logger.warning(f"Failed to parse timestamp: {p.timestamp}")
                    timestamps.append(datetime.now())
        
        # Sort by timestamp
        sorted_data = sorted(zip(timestamps, prices), key=lambda x: x[0])
        timestamps, prices = zip(*sorted_data) if sorted_data else ([], [])
        timestamps = list(timestamps)
        prices = list(prices)
        
        # Calculate trend
        trend_direction, trend_strength = self.calculate_trend(prices, timestamps)
        
        # Calculate volatility
        volatility = self.calculate_volatility(prices)
        
        # Calculate average price
        avg_price = float(np.mean(prices))
        
        # Calculate price changes
        now = datetime.now()
        date_30d_ago = now - timedelta(days=30)
        date_90d_ago = now - timedelta(days=90)
        
        # Find prices around those dates
        price_30d = None
        price_90d = None
        
        for i, ts in enumerate(timestamps):
            if ts >= date_30d_ago and price_30d is None:
                price_30d = prices[i]
            if ts >= date_90d_ago and price_90d is None:
                price_90d = prices[i]
        
        # Calculate percentage changes with division by zero protection
        current_price = prices[-1] if prices else 0
        
        if price_30d and price_30d > 0:
            price_change_30d = ((current_price - price_30d) / price_30d) * 100
        else:
            price_change_30d = 0.0
        
        if price_90d and price_90d > 0:
            price_change_90d = ((current_price - price_90d) / price_90d) * 100
        else:
            price_change_90d = 0.0
        
        return TrendAnalysis(
            trend_direction=trend_direction,
            trend_strength=round(trend_strength, 3),
            volatility=round(volatility, 2),
            avg_price=round(avg_price, 2),
            price_change_30d=round(price_change_30d, 2),
            price_change_90d=round(price_change_90d, 2)
        )
