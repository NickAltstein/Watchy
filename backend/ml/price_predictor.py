"""
Machine Learning Price Prediction for Luxury Watches

Features:
- Historical price trend analysis
- Future price prediction with confidence intervals
- Market trend detection (bullish/bearish)
- Anomaly detection for fake/mispriced listings
- Feature engineering from watch attributes

Model: Random Forest Regressor (scikit-learn)
Training data: Historical price_history table + listing prices
"""

import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import joblib
import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class PricePrediction:
    """Price prediction result"""
    predicted_price: float
    confidence_lower: float  # 95% confidence interval lower bound
    confidence_upper: float  # 95% confidence interval upper bound
    confidence_score: float  # 0-1, how confident the model is
    trend: str  # "bullish", "bearish", "stable"
    historical_avg: float
    days_ahead: int


@dataclass
class AnomalyResult:
    """Anomaly detection result"""
    is_anomaly: bool
    anomaly_score: float  # -1 to 1, more negative = more anomalous
    reason: str
    expected_price_range: Tuple[float, float]


class WatchPricePredictor:
    """
    Price prediction engine using Random Forest
    
    Features used:
    - Brand (one-hot encoded)
    - Reference number patterns
    - Condition score (0-10)
    - Has box, papers, full set (boolean)
    - Days since release
    - Historical average price
    - Price volatility (std dev)
    - Market trend (7, 30, 90 day momentum)
    """
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.model: Optional[RandomForestRegressor] = None
        self.scaler = StandardScaler()
        self.anomaly_detector = IsolationForest(contamination=0.05, random_state=42)
        self.feature_names: List[str] = []
        self.brand_mapping: Dict[str, int] = {}
        
    async def train(self, min_samples: int = 100):
        """
        Train the price prediction model
        
        Args:
            min_samples: Minimum samples per watch reference to include in training
        """
        logger.info("Starting model training...")
        
        # Fetch training data
        training_data = await self._fetch_training_data(min_samples)
        
        if len(training_data) < 100:
            raise ValueError(f"Insufficient training data: {len(training_data)} samples")
        
        # Extract features and labels
        X, y = self._prepare_features(training_data)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train Random Forest
        self.model = RandomForestRegressor(
            n_estimators=200,
            max_depth=20,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        
        logger.info(f"Training on {len(X_train)} samples...")
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        train_pred = self.model.predict(X_train_scaled)
        test_pred = self.model.predict(X_test_scaled)
        
        train_mae = mean_absolute_error(y_train, train_pred)
        test_mae = mean_absolute_error(y_test, test_pred)
        train_r2 = r2_score(y_train, train_pred)
        test_r2 = r2_score(y_test, test_pred)
        
        logger.info(f"Training MAE: ${train_mae:.2f}, R²: {train_r2:.3f}")
        logger.info(f"Test MAE: ${test_mae:.2f}, R²: {test_r2:.3f}")
        
        # Train anomaly detector
        self.anomaly_detector.fit(X_train_scaled)
        
        logger.info("Model training complete!")
        
        return {
            "samples": len(training_data),
            "train_mae": float(train_mae),
            "test_mae": float(test_mae),
            "train_r2": float(train_r2),
            "test_r2": float(test_r2)
        }
    
    async def _fetch_training_data(self, min_samples: int) -> List[Dict]:
        """Fetch historical listing and price data for training"""
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # Fetch listings with price history
            query = """
                SELECT 
                    l.ref_number,
                    l.brand,
                    l.model,
                    l.price_usd,
                    l.condition_score,
                    l.has_box,
                    l.has_papers,
                    l.is_full_set,
                    l.year,
                    l.created_at,
                    ph.avg_price as historical_avg,
                    ph.median_price,
                    ph.min_price,
                    ph.max_price
                FROM listings l
                LEFT JOIN LATERAL (
                    SELECT 
                        AVG(avg_price) as avg_price,
                        AVG(median_price) as median_price,
                        MIN(min_price) as min_price,
                        MAX(max_price) as max_price
                    FROM price_history
                    WHERE ref_number = l.ref_number
                    AND date <= l.created_at
                    AND date >= l.created_at - INTERVAL '90 days'
                ) ph ON true
                WHERE l.status IN ('sold', 'active')
                AND l.price_usd IS NOT NULL
                AND l.ref_number IS NOT NULL
            """
            
            rows = await conn.fetch(query)
            
            return [dict(row) for row in rows]
            
        finally:
            await conn.close()
    
    def _prepare_features(self, data: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert raw data to feature matrix and target vector
        
        Features:
        1. Brand (one-hot encoded top 20 brands)
        2. Condition score (0-10)
        3. Has box (0/1)
        4. Has papers (0/1)
        5. Is full set (0/1)
        6. Years old (current year - watch year)
        7. Historical average price
        8. Price volatility (max - min / avg)
        9-11. Market momentum (7, 30, 90 day trends)
        """
        # Build brand mapping
        brands = [d.get("brand") for d in data if d.get("brand")]
        unique_brands = list(set(brands))
        self.brand_mapping = {brand: i for i, brand in enumerate(unique_brands[:20])}
        
        features = []
        targets = []
        
        current_year = datetime.now().year
        
        for item in data:
            price = item.get("price_usd")
            if not price or price <= 0:
                continue
            
            # Extract features
            brand = item.get("brand", "")
            brand_id = self.brand_mapping.get(brand, -1)
            
            condition = float(item.get("condition_score", 7.0))
            has_box = 1 if item.get("has_box") else 0
            has_papers = 1 if item.get("has_papers") else 0
            is_full_set = 1 if item.get("is_full_set") else 0
            
            year = item.get("year")
            years_old = current_year - year if year else 5.0
            
            hist_avg = item.get("historical_avg") or price
            hist_min = item.get("min_price") or price * 0.9
            hist_max = item.get("max_price") or price * 1.1
            
            # Calculate volatility
            volatility = (hist_max - hist_min) / hist_avg if hist_avg > 0 else 0
            
            # Feature vector
            feature_vec = [
                brand_id,
                condition,
                has_box,
                has_papers,
                is_full_set,
                years_old,
                hist_avg,
                volatility,
                0.0,  # 7-day momentum (placeholder)
                0.0,  # 30-day momentum (placeholder)
                0.0,  # 90-day momentum (placeholder)
            ]
            
            features.append(feature_vec)
            targets.append(price)
        
        self.feature_names = [
            "brand_id", "condition", "has_box", "has_papers", "is_full_set",
            "years_old", "hist_avg", "volatility", 
            "momentum_7d", "momentum_30d", "momentum_90d"
        ]
        
        return np.array(features), np.array(targets)
    
    async def predict_price(
        self,
        ref_number: str,
        brand: str,
        condition_score: float,
        has_box: bool,
        has_papers: bool,
        is_full_set: bool,
        year: Optional[int] = None,
        days_ahead: int = 0
    ) -> PricePrediction:
        """
        Predict price for a watch
        
        Args:
            ref_number: Watch reference number
            brand: Brand name
            condition_score: Condition (0-10)
            has_box: Has original box
            has_papers: Has papers
            is_full_set: Has full set
            year: Year of manufacture
            days_ahead: Predict price N days in the future (0 = current)
        
        Returns:
            PricePrediction with predicted price and confidence intervals
        """
        if not self.model:
            raise ValueError("Model not trained. Call train() first.")
        
        # Fetch historical data for this reference
        conn = await asyncpg.connect(self.db_url)
        
        try:
            hist_query = """
                SELECT 
                    AVG(avg_price) as avg_price,
                    MIN(min_price) as min_price,
                    MAX(max_price) as max_price,
                    STDDEV(avg_price) as std_price
                FROM price_history
                WHERE ref_number = $1
                AND date >= NOW() - INTERVAL '90 days'
            """
            
            hist = await conn.fetchrow(hist_query, ref_number)
            
            hist_avg = float(hist["avg_price"]) if hist and hist["avg_price"] else 10000.0
            hist_min = float(hist["min_price"]) if hist and hist["min_price"] else hist_avg * 0.9
            hist_max = float(hist["max_price"]) if hist and hist["max_price"] else hist_avg * 1.1
            std_price = float(hist["std_price"]) if hist and hist["std_price"] else hist_avg * 0.1
            
        finally:
            await conn.close()
        
        # Prepare features
        current_year = datetime.now().year
        brand_id = self.brand_mapping.get(brand, -1)
        years_old = current_year - year if year else 5.0
        volatility = (hist_max - hist_min) / hist_avg if hist_avg > 0 else 0
        
        feature_vec = np.array([[
            brand_id,
            condition_score,
            1 if has_box else 0,
            1 if has_papers else 0,
            1 if is_full_set else 0,
            years_old,
            hist_avg,
            volatility,
            0.0,  # momentum placeholders
            0.0,
            0.0,
        ]])
        
        # Scale and predict
        feature_scaled = self.scaler.transform(feature_vec)
        
        # Get predictions from all trees for confidence interval
        predictions = np.array([tree.predict(feature_scaled)[0] for tree in self.model.estimators_])
        
        predicted_price = predictions.mean()
        confidence_lower = np.percentile(predictions, 2.5)
        confidence_upper = np.percentile(predictions, 97.5)
        confidence_score = 1.0 - (predictions.std() / predicted_price if predicted_price > 0 else 0.5)
        
        # Determine trend
        trend = "stable"
        if hist_avg > 0:
            change = (predicted_price - hist_avg) / hist_avg
            if change > 0.05:
                trend = "bullish"
            elif change < -0.05:
                trend = "bearish"
        
        return PricePrediction(
            predicted_price=float(predicted_price),
            confidence_lower=float(confidence_lower),
            confidence_upper=float(confidence_upper),
            confidence_score=float(max(0.0, min(1.0, confidence_score))),
            trend=trend,
            historical_avg=float(hist_avg),
            days_ahead=days_ahead
        )
    
    async def detect_anomaly(
        self,
        ref_number: str,
        listed_price: float,
        brand: str,
        condition_score: float,
        has_box: bool,
        has_papers: bool,
        is_full_set: bool,
        year: Optional[int] = None
    ) -> AnomalyResult:
        """
        Detect if a listing price is anomalous (potential fake or mispricing)
        
        Returns:
            AnomalyResult indicating if price is suspicious
        """
        # Get price prediction
        prediction = await self.predict_price(
            ref_number, brand, condition_score,
            has_box, has_papers, is_full_set, year
        )
        
        # Check if price is outside confidence interval
        is_too_low = listed_price < prediction.confidence_lower * 0.8
        is_too_high = listed_price > prediction.confidence_upper * 1.2
        
        # Prepare features for anomaly detection
        current_year = datetime.now().year
        brand_id = self.brand_mapping.get(brand, -1)
        years_old = current_year - year if year else 5.0
        
        feature_vec = np.array([[
            brand_id,
            condition_score,
            1 if has_box else 0,
            1 if has_papers else 0,
            1 if is_full_set else 0,
            years_old,
            prediction.historical_avg,
            (prediction.confidence_upper - prediction.confidence_lower) / prediction.historical_avg,
            0.0, 0.0, 0.0,
        ]])
        
        feature_scaled = self.scaler.transform(feature_vec)
        anomaly_score = self.anomaly_detector.score_samples(feature_scaled)[0]
        
        is_anomaly = anomaly_score < -0.5 or is_too_low or is_too_high
        
        # Determine reason
        reason = "Normal"
        if is_too_low:
            reason = "Price significantly below market (potential fake or urgent sale)"
        elif is_too_high:
            reason = "Price significantly above market (potential scam)"
        elif anomaly_score < -0.5:
            reason = "Unusual feature combination for this price"
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=float(anomaly_score),
            reason=reason,
            expected_price_range=(
                float(prediction.confidence_lower),
                float(prediction.confidence_upper)
            )
        )
    
    def save_model(self, filepath: str):
        """Save trained model to disk"""
        joblib.dump({
            "model": self.model,
            "scaler": self.scaler,
            "anomaly_detector": self.anomaly_detector,
            "brand_mapping": self.brand_mapping,
            "feature_names": self.feature_names
        }, filepath)
        logger.info(f"Model saved to {filepath}")
    
    def load_model(self, filepath: str):
        """Load trained model from disk"""
        data = joblib.load(filepath)
        self.model = data["model"]
        self.scaler = data["scaler"]
        self.anomaly_detector = data["anomaly_detector"]
        self.brand_mapping = data["brand_mapping"]
        self.feature_names = data["feature_names"]
        logger.info(f"Model loaded from {filepath}")


# Convenience function for easy integration
async def get_price_prediction(
    predictor: WatchPricePredictor,
    ref_number: str,
    **kwargs
) -> Dict:
    """
    Get price prediction as a dictionary (for API responses)
    """
    prediction = await predictor.predict_price(ref_number, **kwargs)
    
    return {
        "ref_number": ref_number,
        "predicted_price": prediction.predicted_price,
        "confidence_interval": {
            "lower": prediction.confidence_lower,
            "upper": prediction.confidence_upper
        },
        "confidence_score": prediction.confidence_score,
        "trend": prediction.trend,
        "historical_avg": prediction.historical_avg,
        "recommendation": _get_recommendation(prediction)
    }


def _get_recommendation(prediction: PricePrediction) -> str:
    """Generate buy/sell/hold recommendation"""
    if prediction.trend == "bullish" and prediction.confidence_score > 0.7:
        return "Strong Buy - Price trending upward"
    elif prediction.trend == "bullish":
        return "Buy - Moderate upward trend"
    elif prediction.trend == "bearish" and prediction.confidence_score > 0.7:
        return "Sell/Avoid - Price likely to decline"
    elif prediction.trend == "bearish":
        return "Hold/Caution - Slight downward pressure"
    else:
        return "Hold - Stable market"
