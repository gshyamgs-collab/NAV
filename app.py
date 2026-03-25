import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Page Configuration
st.set_page_config(page_title="Indian Stock Educator & NAV Tracker", layout="wide")

def format_ticker(ticker):
    """Appends .NS to Indian tickers if not present."""
    ticker = ticker.strip().upper()
    if ticker and not ticker.endswith('.NS') and not ticker.startswith('^'):
        return f"{ticker}.NS"
    return ticker

@st.cache_data(ttl=3600)
def fetch_data(tickers, period="10y"):
    """Fetches historical data with error handling."""
    data = {}
    for t in tickers:
        try:
            df = yf.download(t, period=period, interval="1d")
            if not df.empty:
                data[t] = df['Close']
        except Exception as e:
            st.error(f"Error fetching data for {t}: {e}")
    return pd.DataFrame(data)

# --- SIDEBAR INPUTS ---
st.sidebar.header("📌 Portfolio Inputs")
st.sidebar.write("Enter your top 3 Indian stocks:")

portfolio_inputs = []
total_investment = 0

for i in range(1, 4):
    col1, col2, col3 = st.sidebar.columns([2, 1, 1])
    with col1:
        t = st.text_input(f"Ticker {i}", value="RELIANCE" if i==1 else "", key=f"t{i}")
    with col2:
        p = st.number_input(f"Avg Price", min_value=0.0, step=1.0, key=f"p{i}")
    with col3:
        q = st.number_input(f"Qty", min_value=0, step=1, key=f"q{i}")
    
    if t:
        formatted_t = format_ticker(t)
        portfolio_inputs.append({'ticker': formatted_t, 'price': p, 'qty': q})
        total_investment += (p * q)

# --- MAIN LOGIC ---
st.title("📈 Indian Stock Market Navigator")
st.markdown("Automated Portfolio NAV tracking vs. Nifty 50 Benchmark.")

if len(portfolio_inputs) > 0:
    with st.spinner("Analyzing 10 years of market data..."):
        # Tickers to fetch (Portfolio + Benchmark)
        tickers_to_get = [stock['ticker'] for stock in portfolio_inputs]
        benchmark = "^NSEI"
        all_tickers = tickers_to_get + [benchmark]
        
        hist_data = fetch_data(all_tickers)
        
        if not hist_data.empty and benchmark in hist_data.columns:
            # Calculate Portfolio NAV (Historical Value of current holdings)
            portfolio_nav = pd.Series(0, index=hist_data.index)
            for stock in portfolio_inputs:
                if stock['ticker'] in hist_data.columns:
                    portfolio_nav += hist_data[stock['ticker']] * stock['qty']
            
            # Normalization for comparison (Start at 100)
            norm_portfolio = (portfolio_nav / portfolio_nav.iloc[0]) * 100
            norm_nifty = (hist_data[benchmark] / hist_data[benchmark].iloc[0]) * 100

            # --- PLOTLY CHART ---
            fig = go.Figure()

            # Portfolio Line
            fig.add_trace(go.Scatter(x=norm_portfolio.index, y=norm_portfolio, 
                                     name="My Portfolio", line=dict(color='#00ff88', width=3)))
            
            # Nifty Line
            fig.add_trace(go.Scatter(x=norm_nifty.index, y=norm_nifty, 
                                     name="Nifty 50 (Benchmark)", line=dict(color='#ff3366', width=2, dash='dot')))

            # Historical Annotations
            annotations = [
                dict(date="2020-03-23", text="COVID Market Crash"),
                dict(date="2021-10-18", text="Post-Pandemic High"),
                dict(date="2024-06-04", text="Election Volatility")
            ]

            for ann in annotations:
                ann_date = pd.to_datetime(ann['date'])
                if ann_date in norm_portfolio.index:
                    fig.add_annotation(x=ann_date, y=norm_portfolio.loc[ann_date],
                                       text=ann['text'], showarrow=True, arrowhead=1)

            fig.update_layout(
                title="Relative Growth: Portfolio vs. Nifty 50 (10Y)",
                xaxis_title="Year",
                yaxis_title="Normalized Value (Base 100)",
                hovermode="x unified",
                template="plotly_dark",
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )

            st.plotly_chart(fig, use_container_width=True)

            # --- AI INSIGHTS SECTION ---
            st.divider()
            st.subheader("🤖 AI-Style Insights")
            
            curr_val = portfolio_nav.iloc[-1]
            total_ret_pct = ((curr_val - total_investment) / total_investment * 100) if total_investment > 0 else 0
            
            # Determine best stock
            best_stock = ""
            max_gain = -999
            for stock in portfolio_inputs:
                if stock['ticker'] in hist_data.columns:
                    s_data = hist_data[stock['ticker']]
                    gain = ((s_data.iloc[-1] - s_data.iloc[0]) / s_data.iloc[0]) * 100
                    if gain > max_gain:
                        max_gain = gain
                        best_stock = stock['ticker']

            # Trend Analysis (Moving Averages)
            sma_50 = portfolio_nav.rolling(window=50).mean().iloc[-1]
            sma_200 = portfolio_nav.rolling(window=200).mean().iloc[-1]
            trend = "🐂 Bullish" if sma_50 > sma_200 else "🐻 Bearish"

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Total Return", f"{total_ret_pct:.2f}%", delta=f"{curr_val - total_investment:,.2f} ₹")
            col_b.metric("Top Performer", best_stock, f"{max_gain:.1f}% Growth")
            col_c.metric("Current Trend", trend, "50-day vs 200-day MA")

            with st.expander("View Raw Data"):
                st.dataframe(hist_data.tail(10))
        else:
            st.warning("Could not retrieve enough data. Please check your tickers.")
else:
    st.info("👈 Enter your stock tickers and quantities in the sidebar to begin.")
