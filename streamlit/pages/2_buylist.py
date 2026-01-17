"""
WatchEdge - Hot Buylist Page
Weekly recommendations for best buying opportunities
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(
    page_title="Buy List | WatchEdge",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 This Week's Hot Buys")
st.markdown("AI-curated buying opportunities based on market analysis, price trends, and velocity data.")

# Filters
st.markdown("### 🎯 Filter Opportunities")
col1, col2, col3, col4 = st.columns(4)

with col1:
    brand_filter = st.multiselect(
        "Brand",
        ["Rolex", "Patek Philippe", "Audemars Piguet", "Omega", "Tudor"],
        default=["Rolex", "Patek Philippe", "Audemars Piguet"]
    )

with col2:
    min_upside = st.slider("Min Upside %", 5, 25, 8)

with col3:
    max_budget = st.number_input("Max Budget ($)", 5000, 500000, 50000, step=5000)

with col4:
    velocity_filter = st.selectbox("Sell Velocity", ["All", "Fast", "Medium", "Slow"])

st.markdown("---")

# Generate buylist data
buylist = [
    {
        "rank": 1,
        "ref": "126610LN",
        "brand": "Rolex",
        "model": "Submariner Date 41mm",
        "target_buy": 13200,
        "market_mid": 14800,
        "upside": 12.1,
        "velocity": "Fast",
        "avg_days_to_sell": 8,
        "confidence": 0.92,
        "trend": "↗️ Rising",
        "notes": "Black dial, high demand. Easy flip under $14K."
    },
    {
        "rank": 2,
        "ref": "116500LN",
        "brand": "Rolex",
        "model": "Daytona Panda",
        "target_buy": 39500,
        "market_mid": 43500,
        "upside": 10.1,
        "velocity": "Medium",
        "avg_days_to_sell": 18,
        "confidence": 0.88,
        "trend": "→ Stable",
        "notes": "White dial preferred. Strong collector demand."
    },
    {
        "rank": 3,
        "ref": "15500ST",
        "brand": "Audemars Piguet",
        "model": "Royal Oak 41mm Blue",
        "target_buy": 31500,
        "market_mid": 36000,
        "upside": 14.3,
        "velocity": "Fast",
        "avg_days_to_sell": 12,
        "confidence": 0.85,
        "trend": "↗️ Rising",
        "notes": "Blue dial models moving fast. Check for scratches on bezel."
    },
    {
        "rank": 4,
        "ref": "5711/1A-010",
        "brand": "Patek Philippe",
        "model": "Nautilus Blue",
        "target_buy": 112000,
        "market_mid": 128000,
        "upside": 14.3,
        "velocity": "Slow",
        "avg_days_to_sell": 35,
        "confidence": 0.82,
        "trend": "↘️ Softening",
        "notes": "Discontinued. Long-term hold potential despite softening."
    },
    {
        "rank": 5,
        "ref": "126710BLRO",
        "brand": "Rolex",
        "model": "GMT-Master II Pepsi Jubilee",
        "target_buy": 19000,
        "market_mid": 21500,
        "upside": 13.2,
        "velocity": "Fast",
        "avg_days_to_sell": 10,
        "confidence": 0.90,
        "trend": "↗️ Rising",
        "notes": "Jubilee bracelet. Very liquid - easy money."
    },
    {
        "rank": 6,
        "ref": "126334",
        "brand": "Rolex",
        "model": "Datejust 41 Wimbledon",
        "target_buy": 11500,
        "market_mid": 13200,
        "upside": 14.8,
        "velocity": "Fast",
        "avg_days_to_sell": 7,
        "confidence": 0.87,
        "trend": "→ Stable",
        "notes": "Green Roman dial. Entry-level flip opportunity."
    },
    {
        "rank": 7,
        "ref": "25940SK",
        "brand": "Audemars Piguet",
        "model": "Royal Oak Offshore Chrono",
        "target_buy": 18500,
        "market_mid": 21000,
        "upside": 13.5,
        "velocity": "Medium",
        "avg_days_to_sell": 22,
        "confidence": 0.75,
        "trend": "↗️ Rising",
        "notes": "Older ref gaining collector interest. Verify authenticity."
    },
    {
        "rank": 8,
        "ref": "310.30.42.50.01.001",
        "brand": "Omega",
        "model": "Speedmaster Professional",
        "target_buy": 5800,
        "market_mid": 6500,
        "upside": 12.1,
        "velocity": "Fast",
        "avg_days_to_sell": 9,
        "confidence": 0.89,
        "trend": "→ Stable",
        "notes": "Hesalite crystal. Always liquid, great entry flip."
    },
    {
        "rank": 9,
        "ref": "M79360DK",
        "brand": "Tudor",
        "model": "Black Bay Chrono Panda",
        "target_buy": 4200,
        "market_mid": 4800,
        "upside": 14.3,
        "velocity": "Fast",
        "avg_days_to_sell": 6,
        "confidence": 0.91,
        "trend": "↗️ Rising",
        "notes": "Hot model right now. Best under $4.5K with box/papers."
    },
    {
        "rank": 10,
        "ref": "116520",
        "brand": "Rolex",
        "model": "Daytona (Previous Gen)",
        "target_buy": 28000,
        "market_mid": 31500,
        "upside": 12.5,
        "velocity": "Medium",
        "avg_days_to_sell": 25,
        "confidence": 0.83,
        "trend": "↘️ Softening",
        "notes": "Superseded but collector classic. White dial premium."
    },
]

# Convert to DataFrame and filter
df = pd.DataFrame(buylist)

# Apply filters
if brand_filter:
    df = df[df["brand"].isin(brand_filter)]

df = df[df["upside"] >= min_upside]
df = df[df["target_buy"] <= max_budget]

if velocity_filter != "All":
    df = df[df["velocity"] == velocity_filter]

# Display results
st.markdown(f"### 📋 {len(df)} Opportunities Found")

if len(df) == 0:
    st.warning("No opportunities match your filters. Try adjusting the criteria.")
else:
    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Avg Upside", f"{df['upside'].mean():.1f}%")
    with col2:
        st.metric("Avg Days to Sell", f"{df['avg_days_to_sell'].mean():.0f}")
    with col3:
        st.metric("Capital Required", f"${df['target_buy'].sum():,}")
    with col4:
        potential_profit = ((df['market_mid'] - df['target_buy']).sum())
        st.metric("Potential Profit", f"${potential_profit:,}")
    
    st.markdown("---")
    
    # Display each opportunity as a card
    for _, row in df.iterrows():
        with st.container():
            col1, col2, col3 = st.columns([3, 2, 1])
            
            with col1:
                velocity_color = {"Fast": "🟢", "Medium": "🟡", "Slow": "🔴"}
                st.markdown(f"""
                ### #{row['rank']} {row['brand']} {row['model']}
                **Ref:** {row['ref']} | {velocity_color.get(row['velocity'], '⚪')} {row['velocity']} Seller | {row['trend']}
                """)
                st.caption(f"💡 {row['notes']}")
            
            with col2:
                subcol1, subcol2 = st.columns(2)
                with subcol1:
                    st.markdown(f"""
                    <div style="background: #27ae60; padding: 0.8rem; border-radius: 8px; text-align: center; color: white;">
                        <small>Target Buy</small><br>
                        <strong>${row['target_buy']:,}</strong>
                    </div>
                    """, unsafe_allow_html=True)
                with subcol2:
                    st.markdown(f"""
                    <div style="background: #3498db; padding: 0.8rem; border-radius: 8px; text-align: center; color: white;">
                        <small>Market Mid</small><br>
                        <strong>${row['market_mid']:,}</strong>
                    </div>
                    """, unsafe_allow_html=True)
            
            with col3:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 1rem; border-radius: 8px; text-align: center; color: white;">
                    <h2 style="margin: 0;">↑{row['upside']:.1f}%</h2>
                    <small>Potential</small><br>
                    <small>{row['confidence']*100:.0f}% Conf</small>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("---")
    
    # Export functionality
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        st.download_button(
            "📥 Export Buy List",
            df.to_csv(index=False),
            f"watchedge_buylist_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv"
        )
    with col2:
        if st.button("🔔 Set Alerts (Pro)"):
            st.info("Upgrade to Pro for real-time alerts when these refs hit target prices!")

# Methodology section
with st.expander("📊 How We Calculate Recommendations"):
    st.markdown("""
    ### Our AI-Powered Analysis
    
    WatchEdge analyzes multiple data sources to identify buying opportunities:
    
    **Data Sources:**
    - Chrono24 listing data (updated hourly)
    - eBay completed sales
    - Dealer network pricing
    - Social sentiment (Instagram, Reddit)
    
    **Scoring Factors:**
    1. **Price Delta** - Gap between current listings and recent sales (40%)
    2. **Velocity Score** - How fast similar pieces sell (25%)
    3. **Trend Direction** - 7/30/90 day price movement (20%)
    4. **Liquidity** - Market depth and buyer demand (15%)
    
    **Confidence Score:**
    - Based on data quality and sample size
    - Higher confidence = more data points
    - We recommend >80% confidence for action
    
    **Risk Disclaimer:**
    Past performance doesn't guarantee future results. Always verify authenticity 
    and condition before purchasing.
    """)

# Pro upsell
st.markdown("---")
st.markdown("""
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 2rem; border-radius: 12px; text-align: center; color: white;">
    <h2>🚀 Upgrade to Pro</h2>
    <p>Get real-time alerts, unlimited pricing, and personalized buy lists</p>
    <p><strong>$99/month</strong> - Cancel anytime</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 1, 1])
with col2:
    if st.button("Start Free Trial", type="primary", use_container_width=True):
        st.info("Stripe checkout integration coming soon!")
