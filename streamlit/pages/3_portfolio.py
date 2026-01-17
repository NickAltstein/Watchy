"""
WatchEdge - Portfolio Manager Page
Track inventory, time-to-sell predictions, and risk management
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(
    page_title="Portfolio | WatchEdge",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Portfolio Manager")
st.markdown("Track your inventory, predict time-to-sell, and manage capital allocation.")

# Session state for portfolio
if "portfolio" not in st.session_state:
    # Demo portfolio data
    st.session_state.portfolio = pd.DataFrame({
        "ref": ["126610LN", "116500LN", "15500ST", "126710BLRO", "M79360DK"],
        "brand": ["Rolex", "Rolex", "AP", "Rolex", "Tudor"],
        "model": ["Submariner Date", "Daytona Panda", "Royal Oak", "GMT Pepsi", "BB Chrono"],
        "purchase_price": [12800, 39000, 33500, 19200, 4100],
        "purchase_date": [
            datetime.now() - timedelta(days=15),
            datetime.now() - timedelta(days=45),
            datetime.now() - timedelta(days=8),
            datetime.now() - timedelta(days=22),
            datetime.now() - timedelta(days=3),
        ],
        "condition": ["Excellent", "Good", "NIB", "Excellent", "Excellent"],
        "box_papers": ["Full Set", "Box Only", "Full Set", "Full Set", "Papers Only"],
        "current_market": [14600, 42500, 36200, 21200, 4750],
        "status": ["Listed", "Listed", "In Transit", "Listed", "Received"]
    })

portfolio = st.session_state.portfolio

# Add inventory
with st.expander("➕ Add New Watch to Portfolio"):
    col1, col2, col3 = st.columns(3)
    
    with col1:
        new_ref = st.text_input("Reference", placeholder="126610LN")
        new_brand = st.selectbox("Brand", ["Rolex", "Patek Philippe", "Audemars Piguet", "Omega", "Tudor", "Other"])
        new_model = st.text_input("Model", placeholder="Submariner Date")
    
    with col2:
        new_price = st.number_input("Purchase Price ($)", 1000, 500000, 10000, step=100)
        new_date = st.date_input("Purchase Date", datetime.now())
        new_condition = st.selectbox("Condition", ["NIB", "Unworn", "Excellent", "Good", "Fair"])
    
    with col3:
        new_bp = st.selectbox("Box/Papers", ["Full Set", "Box Only", "Papers Only", "None"])
        new_status = st.selectbox("Status", ["In Transit", "Received", "Listed", "Sold"])
    
    if st.button("Add to Portfolio"):
        # Estimate market value
        base_prices = {"126610LN": 14500, "116500LN": 42000, "DEFAULT": new_price * 1.1}
        market = base_prices.get(new_ref.upper(), base_prices["DEFAULT"])
        
        new_watch = pd.DataFrame({
            "ref": [new_ref.upper()],
            "brand": [new_brand],
            "model": [new_model],
            "purchase_price": [new_price],
            "purchase_date": [pd.Timestamp(new_date)],
            "condition": [new_condition],
            "box_papers": [new_bp],
            "current_market": [market],
            "status": [new_status]
        })
        
        st.session_state.portfolio = pd.concat([portfolio, new_watch], ignore_index=True)
        st.success(f"Added {new_ref} to portfolio!")
        st.rerun()

# Portfolio metrics
st.markdown("---")
st.markdown("### 📈 Portfolio Overview")

# Calculate metrics
portfolio["profit_potential"] = portfolio["current_market"] - portfolio["purchase_price"]
portfolio["profit_pct"] = (portfolio["profit_potential"] / portfolio["purchase_price"]) * 100
portfolio["days_held"] = (datetime.now() - pd.to_datetime(portfolio["purchase_date"])).dt.days

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    total_cost = portfolio["purchase_price"].sum()
    st.metric("Total Invested", f"${total_cost:,.0f}")

with col2:
    total_market = portfolio["current_market"].sum()
    st.metric("Current Value", f"${total_market:,.0f}")

with col3:
    total_profit = portfolio["profit_potential"].sum()
    pct_change = ((total_market - total_cost) / total_cost) * 100
    st.metric("Unrealized P&L", f"${total_profit:,.0f}", f"{pct_change:+.1f}%")

with col4:
    avg_days = portfolio["days_held"].mean()
    st.metric("Avg Days Held", f"{avg_days:.0f}")

with col5:
    active_count = len(portfolio[portfolio["status"] != "Sold"])
    st.metric("Active Pieces", str(active_count))

# Portfolio table
st.markdown("### 📋 Current Holdings")

# Time-to-sell prediction (synthetic)
np.random.seed(42)
portfolio["predicted_sell_days"] = np.random.randint(5, 45, len(portfolio))
portfolio["sell_probability_30d"] = np.random.uniform(0.4, 0.95, len(portfolio))

# Display table with styling
display_cols = ["ref", "brand", "model", "purchase_price", "current_market", 
                "profit_potential", "profit_pct", "days_held", "predicted_sell_days", "status"]

styled_df = portfolio[display_cols].style.format({
    "purchase_price": "${:,.0f}",
    "current_market": "${:,.0f}",
    "profit_potential": "${:+,.0f}",
    "profit_pct": "{:+.1f}%",
    "days_held": "{:.0f}d",
    "predicted_sell_days": "{:.0f}d"
}).applymap(
    lambda x: "color: green" if isinstance(x, (int, float)) and x > 0 else 
              ("color: red" if isinstance(x, (int, float)) and x < 0 else ""),
    subset=["profit_potential", "profit_pct"]
)

st.dataframe(styled_df, use_container_width=True)

# Visualizations
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🎯 Profit by Watch")
    
    fig = px.bar(
        portfolio,
        x="ref",
        y="profit_potential",
        color="profit_potential",
        color_continuous_scale=["red", "yellow", "green"],
        title="Unrealized Profit by Reference"
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("### ⏱️ Time-to-Sell Prediction")
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=portfolio["ref"],
        y=portfolio["days_held"],
        name="Days Held",
        marker_color="#3498db"
    ))
    fig.add_trace(go.Bar(
        x=portfolio["ref"],
        y=portfolio["predicted_sell_days"],
        name="Predicted to Sell",
        marker_color="#27ae60"
    ))
    fig.update_layout(
        barmode="group",
        title="Days Held vs Predicted Time to Sell"
    )
    st.plotly_chart(fig, use_container_width=True)

# Capital allocation
st.markdown("---")
st.markdown("### 💰 Capital Allocation")

col1, col2 = st.columns(2)

with col1:
    fig = px.pie(
        portfolio,
        values="purchase_price",
        names="brand",
        title="Allocation by Brand"
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    # Risk assessment
    st.markdown("#### ⚠️ Risk Assessment")
    
    # Calculate risk metrics
    high_exposure = portfolio[portfolio["purchase_price"] > portfolio["purchase_price"].mean() * 1.5]
    slow_movers = portfolio[portfolio["days_held"] > 30]
    underwater = portfolio[portfolio["profit_potential"] < 0]
    
    if len(high_exposure) > 0:
        st.warning(f"⚠️ **High Concentration Risk:** {len(high_exposure)} pieces above avg position size")
    
    if len(slow_movers) > 0:
        st.warning(f"⏰ **Slow Inventory:** {len(slow_movers)} pieces held 30+ days")
    
    if len(underwater) > 0:
        st.error(f"📉 **Underwater Positions:** {len(underwater)} pieces below purchase price")
    
    if len(high_exposure) == 0 and len(slow_movers) == 0 and len(underwater) == 0:
        st.success("✅ Portfolio looks healthy!")
    
    # Diversification score
    brand_concentration = (portfolio.groupby("brand")["purchase_price"].sum() / total_cost).max()
    div_score = max(0, 100 - (brand_concentration * 100))
    
    st.markdown(f"**Diversification Score:** {div_score:.0f}/100")
    st.progress(div_score / 100)

# Actions
st.markdown("---")
st.markdown("### 🎯 Recommended Actions")

actions = []

# Check for slow movers
for _, watch in portfolio.iterrows():
    if watch["days_held"] > 30 and watch["status"] == "Listed":
        actions.append({
            "type": "⚠️ Price Reduction",
            "ref": watch["ref"],
            "action": f"Consider 5% price reduction - held {watch['days_held']} days",
            "priority": "Medium"
        })
    
    if watch["profit_pct"] > 15 and watch["status"] == "Listed":
        actions.append({
            "type": "💰 Take Profit",
            "ref": watch["ref"],
            "action": f"Strong profit ({watch['profit_pct']:.1f}%) - consider selling",
            "priority": "High"
        })
    
    if watch["profit_pct"] < -5:
        actions.append({
            "type": "📉 Review Position",
            "ref": watch["ref"],
            "action": f"Underwater by {abs(watch['profit_pct']):.1f}% - review strategy",
            "priority": "High"
        })

if actions:
    actions_df = pd.DataFrame(actions)
    st.dataframe(actions_df, use_container_width=True)
else:
    st.success("✅ No immediate actions recommended - portfolio performing well!")

# Export
st.markdown("---")
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    st.download_button(
        "📥 Export Portfolio",
        portfolio.to_csv(index=False),
        f"watchedge_portfolio_{datetime.now().strftime('%Y%m%d')}.csv",
        "text/csv"
    )

with col2:
    if st.button("🔄 Refresh Prices"):
        st.info("Refreshing market prices... (Demo)")
        st.rerun()

# Pro features callout
st.markdown("---")
st.info("""
**🚀 Pro Features Available:**
- Real-time price alerts when positions hit target
- Automated email reports (daily/weekly)
- Multi-portfolio tracking for teams
- Tax lot tracking and P&L reporting
- API access for custom integrations
""")
