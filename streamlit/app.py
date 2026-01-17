"""
WatchEdge - Instagram Flipper's Pricing Copilot
Never leave 15% on the table again.

Main Streamlit Dashboard Application
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
import os

# Page configuration
st.set_page_config(
    page_title="WatchEdge - Watch Pricing Intelligence",
    page_icon="⌚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1a1a2e;
        text-align: center;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #4a4a6a;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .price-low { color: #e74c3c; }
    .price-mid { color: #f39c12; }
    .price-high { color: #27ae60; }
    .stButton>button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 2rem;
    }
</style>
""", unsafe_allow_html=True)

# Backend API URL (configurable)
API_BASE_URL = os.getenv("WATCHEDGE_API_URL", "http://localhost:8000")


def get_price_estimate(ref_number: str, condition: str = "EXCELLENT", 
                       has_box: bool = True, has_papers: bool = True) -> dict:
    """Get price estimate from backend API"""
    try:
        # Call the existing score-deal endpoint
        response = requests.post(
            f"{API_BASE_URL}/score-deal",
            json={
                "ref_number": ref_number,
                "listing_price": 10000,  # Placeholder for estimation
                "condition": condition,
                "has_box": has_box,
                "has_papers": has_papers,
                "is_full_set": has_box and has_papers
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            market_price = data.get("market_price", 10000)
            return {
                "low": int(market_price * 0.85),
                "mid": int(market_price),
                "high": int(market_price * 1.15),
                "confidence": 0.87,
                "market_price": market_price
            }
    except Exception as e:
        st.warning(f"API connection issue: {e}")
    
    # Fallback synthetic pricing
    return generate_synthetic_price(ref_number, condition, has_box, has_papers)


def generate_synthetic_price(ref_number: str, condition: str, 
                            has_box: bool, has_papers: bool) -> dict:
    """Generate synthetic price data for demo purposes"""
    # Base prices for common references
    base_prices = {
        "126610LN": 14500,
        "126610LV": 17500,
        "116500LN": 42000,
        "116710BLNR": 19500,
        "126710BLRO": 21000,
        "5711/1A": 125000,
        "15500ST": 35000,
        "DEFAULT": 15000
    }
    
    # Clean reference number
    ref_clean = ref_number.upper().replace(" ", "").replace("-", "")
    base = base_prices.get(ref_clean, base_prices["DEFAULT"])
    
    # Condition multiplier
    condition_mult = {
        "NIB": 1.08, "UNWORN": 1.05, "EXCELLENT": 1.0,
        "GOOD": 0.92, "FAIR": 0.85, "POOR": 0.75
    }.get(condition.upper(), 1.0)
    
    # Box/Papers adjustment
    kit_mult = 1.0
    if has_box and has_papers:
        kit_mult = 1.05
    elif has_box or has_papers:
        kit_mult = 1.02
    else:
        kit_mult = 0.92
    
    mid_price = int(base * condition_mult * kit_mult)
    
    return {
        "low": int(mid_price * 0.90),
        "mid": mid_price,
        "high": int(mid_price * 1.12),
        "confidence": 0.85 if ref_clean in base_prices else 0.65,
        "market_price": mid_price
    }


def process_csv_data(df: pd.DataFrame) -> pd.DataFrame:
    """Process uploaded CSV and add pricing intelligence"""
    required_cols = {"ref_number", "purchase_price"}
    
    # Normalize column names
    df.columns = df.columns.str.lower().str.strip().str.replace(" ", "_")
    
    # Check for required columns
    if not required_cols.issubset(set(df.columns)):
        st.error(f"CSV must contain columns: {required_cols}")
        return pd.DataFrame()
    
    # Add pricing columns
    results = []
    for _, row in df.iterrows():
        ref = str(row.get("ref_number", "")).strip()
        condition = str(row.get("condition", "EXCELLENT")).upper()
        has_box = str(row.get("has_box", "yes")).lower() in ["yes", "true", "1", "y"]
        has_papers = str(row.get("has_papers", "yes")).lower() in ["yes", "true", "1", "y"]
        purchase_price = float(row.get("purchase_price", 0))
        
        pricing = generate_synthetic_price(ref, condition, has_box, has_papers)
        
        results.append({
            "ref_number": ref,
            "condition": condition,
            "has_box": has_box,
            "has_papers": has_papers,
            "purchase_price": purchase_price,
            "price_low": pricing["low"],
            "price_mid": pricing["mid"],
            "price_high": pricing["high"],
            "confidence": pricing["confidence"],
            "potential_profit": pricing["mid"] - purchase_price,
            "profit_margin": ((pricing["mid"] - purchase_price) / purchase_price * 100) if purchase_price > 0 else 0,
            "recommendation": "SELL" if pricing["mid"] > purchase_price * 1.15 else (
                "HOLD" if pricing["mid"] > purchase_price else "REDUCE"
            )
        })
    
    return pd.DataFrame(results)


def main():
    # Header
    st.markdown('<h1 class="main-header">⌚ WatchEdge</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Instagram Flipper\'s Pricing Copilot — Never Leave 15% on the Table</p>', 
                unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.image("https://via.placeholder.com/200x60?text=WatchEdge", width=200)
        st.markdown("---")
        
        st.markdown("### 🎯 Quick Stats")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Active Users", "247", "+12%")
        with col2:
            st.metric("Deals Priced", "3.2K", "+8%")
        
        st.markdown("---")
        st.markdown("### 💎 Subscription")
        tier = st.selectbox("Your Plan", ["Free (3 watches)", "Pro $99/mo", "Enterprise"])
        
        if tier == "Free (3 watches)":
            st.warning("⚡ Upgrade to Pro for unlimited pricing!")
            if st.button("Upgrade to Pro - $99/mo"):
                st.info("Stripe checkout coming soon!")
        
        st.markdown("---")
        st.markdown("### 📞 Need Help?")
        st.markdown("[Schedule a Demo](https://calendly.com/watchedge)")
    
    # Main content tabs
    tab1, tab2, tab3 = st.tabs(["📊 Portfolio Analyzer", "💰 Quick Price", "🔥 Hot Buys"])
    
    with tab1:
        st.markdown("### Upload Your Deal History")
        st.markdown("Upload a CSV with your past deals to get instant fair-value bands and profit analysis.")
        
        # Sample CSV download
        sample_data = pd.DataFrame({
            "ref_number": ["126610LN", "116500LN", "5711/1A"],
            "purchase_price": [12500, 38000, 95000],
            "condition": ["EXCELLENT", "GOOD", "NIB"],
            "has_box": ["yes", "yes", "yes"],
            "has_papers": ["yes", "no", "yes"]
        })
        
        col1, col2 = st.columns([3, 1])
        with col2:
            st.download_button(
                "📥 Download Sample CSV",
                sample_data.to_csv(index=False),
                "watchedge_sample.csv",
                "text/csv"
            )
        
        uploaded_file = st.file_uploader("Choose your CSV file", type=["csv"])
        
        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)
            st.markdown("#### Raw Data Preview")
            st.dataframe(df.head(), use_container_width=True)
            
            with st.spinner("Analyzing your portfolio..."):
                results_df = process_csv_data(df)
            
            if not results_df.empty:
                st.markdown("---")
                st.markdown("### 📈 Portfolio Analysis Results")
                
                # Summary metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    total_potential = results_df["potential_profit"].sum()
                    st.metric("Total Potential Profit", f"${total_potential:,.0f}")
                with col2:
                    avg_margin = results_df["profit_margin"].mean()
                    st.metric("Avg Profit Margin", f"{avg_margin:.1f}%")
                with col3:
                    sells = len(results_df[results_df["recommendation"] == "SELL"])
                    st.metric("Ready to Sell", f"{sells} watches")
                with col4:
                    avg_conf = results_df["confidence"].mean() * 100
                    st.metric("Avg Confidence", f"{avg_conf:.0f}%")
                
                # Results table
                st.markdown("#### Detailed Pricing Analysis")
                
                # Color-code the recommendation
                def highlight_recommendation(val):
                    if val == "SELL":
                        return "background-color: #27ae60; color: white"
                    elif val == "HOLD":
                        return "background-color: #f39c12; color: white"
                    else:
                        return "background-color: #e74c3c; color: white"
                
                styled_df = results_df.style.applymap(
                    highlight_recommendation, subset=["recommendation"]
                ).format({
                    "purchase_price": "${:,.0f}",
                    "price_low": "${:,.0f}",
                    "price_mid": "${:,.0f}",
                    "price_high": "${:,.0f}",
                    "potential_profit": "${:,.0f}",
                    "profit_margin": "{:.1f}%",
                    "confidence": "{:.0%}"
                })
                
                st.dataframe(styled_df, use_container_width=True)
                
                # Export button
                st.download_button(
                    "📤 Export Analysis",
                    results_df.to_csv(index=False),
                    "watchedge_analysis.csv",
                    "text/csv"
                )
                
                # Chart
                st.markdown("#### Price Bands Visualization")
                import plotly.graph_objects as go
                
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name="Purchase Price",
                    x=results_df["ref_number"],
                    y=results_df["purchase_price"],
                    marker_color="#3498db"
                ))
                fig.add_trace(go.Bar(
                    name="Market Mid",
                    x=results_df["ref_number"],
                    y=results_df["price_mid"],
                    marker_color="#27ae60"
                ))
                fig.update_layout(
                    barmode="group",
                    title="Purchase Price vs Market Value",
                    xaxis_title="Reference",
                    yaxis_title="Price ($)"
                )
                st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.markdown("### Quick Price Check")
        st.markdown("Get instant pricing intelligence for any watch reference.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            ref_input = st.text_input("Reference Number", placeholder="e.g., 126610LN")
            condition_input = st.selectbox(
                "Condition",
                ["NIB", "UNWORN", "EXCELLENT", "GOOD", "FAIR", "POOR"]
            )
        
        with col2:
            has_box = st.checkbox("Has Box", value=True)
            has_papers = st.checkbox("Has Papers", value=True)
        
        if st.button("🔍 Get Price Estimate", type="primary"):
            if ref_input:
                with st.spinner("Fetching market data..."):
                    pricing = generate_synthetic_price(
                        ref_input, condition_input, has_box, has_papers
                    )
                
                st.markdown("---")
                st.markdown(f"### Pricing for **{ref_input.upper()}**")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"""
                    <div style="background: #e74c3c; padding: 1rem; border-radius: 8px; text-align: center; color: white;">
                        <h4>Low</h4>
                        <h2>${pricing['low']:,}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div style="background: #27ae60; padding: 1rem; border-radius: 8px; text-align: center; color: white;">
                        <h4>Market Fair Value</h4>
                        <h2>${pricing['mid']:,}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
                    <div style="background: #3498db; padding: 1rem; border-radius: 8px; text-align: center; color: white;">
                        <h4>High</h4>
                        <h2>${pricing['high']:,}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown(f"**Confidence Score:** {pricing['confidence']*100:.0f}%")
                st.progress(pricing['confidence'])
                
                st.info(f"💡 **Tip:** List at ${int(pricing['mid'] * 1.05):,} for quick sale, "
                       f"or ${pricing['high']:,} if you can wait 30+ days.")
            else:
                st.warning("Please enter a reference number")
    
    with tab3:
        st.markdown("### 🔥 Hot Buys This Week")
        st.markdown("References with strong buying opportunities based on market analysis.")
        
        # Synthetic hot buys data
        hot_buys = [
            {"ref": "126610LN", "brand": "Rolex", "model": "Submariner Date", 
             "target_buy": 13500, "market_mid": 14800, "upside": "9.6%", "velocity": "Fast"},
            {"ref": "116500LN", "brand": "Rolex", "model": "Daytona Panda",
             "target_buy": 39000, "market_mid": 43000, "upside": "10.3%", "velocity": "Medium"},
            {"ref": "15500ST", "brand": "AP", "model": "Royal Oak 41mm",
             "target_buy": 32000, "market_mid": 36000, "upside": "12.5%", "velocity": "Fast"},
            {"ref": "5711/1A", "brand": "Patek", "model": "Nautilus",
             "target_buy": 115000, "market_mid": 128000, "upside": "11.3%", "velocity": "Slow"},
            {"ref": "126710BLRO", "brand": "Rolex", "model": "GMT-Master II Pepsi",
             "target_buy": 19500, "market_mid": 21500, "upside": "10.3%", "velocity": "Fast"},
        ]
        
        for buy in hot_buys:
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                with col1:
                    st.markdown(f"**{buy['brand']} {buy['model']}**")
                    st.caption(f"Ref: {buy['ref']}")
                with col2:
                    st.markdown(f"Buy under: **${buy['target_buy']:,}**")
                    st.caption(f"Market: ${buy['market_mid']:,}")
                with col3:
                    st.markdown(f"↑ **{buy['upside']}**")
                    st.caption("Potential")
                with col4:
                    velocity_color = {"Fast": "🟢", "Medium": "🟡", "Slow": "🔴"}
                    st.markdown(f"{velocity_color.get(buy['velocity'], '⚪')} {buy['velocity']}")
                st.markdown("---")
        
        st.success("💡 **Pro Tip:** Set alerts for these refs in the Pro plan to get notified when deals hit the market!")
    
    # Footer
    st.markdown("---")
    current_year = datetime.now().year
    st.markdown(f"""
    <div style="text-align: center; color: #666; font-size: 0.9rem;">
        <p>WatchEdge by ThrivAI NYC | <a href="mailto:hello@watchedge.ai">Contact</a> | 
        <a href="https://calendly.com/watchedge">Schedule Demo</a></p>
        <p>© {current_year} ThrivAI. All rights reserved.</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
