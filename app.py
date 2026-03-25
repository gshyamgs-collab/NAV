import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="Equity Research Automator", layout="wide")

# --- CUSTOM STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_all_window_密=True)

# --- SIDEBAR: NAVIGATION & PORTFOLIO ---
with st.sidebar:
    st.title("📊 Portfolio Hub")
    
    # Quick Ticker Search
    search_ticker = st.text_input("Enter Ticker (e.g., SYNGENE.NS, PIIND.NS)", value="SYNGENE.NS").upper()
    
    st.divider()
    st.subheader("Sector Benchmarks")
    # Using correct 2026 tickers for Midcap indices
    benchmarks = {
        "Nifty Midcap 100": "^NSEMDCP100",
        "Nifty Midcap 150": "NIFTY_MIDCAP_150.NS" 
    }
    selected_benchmark = st.selectbox("Compare with:", list(benchmarks.keys()))

# --- DATA FETCHING FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_stock_data(ticker, period="1y"):
    try:
        data = yf.download(ticker, period=period, interval="1d")
        info = yf.Ticker(ticker).info
        return data, info
    except Exception as e:
        return None, None

# --- MAIN INTERFACE ---
st.title(f"Strategic Research: {search_ticker}")

hist_data, ticker_info = get_stock_data(search_ticker)

if hist_data is not None and not hist_data.empty:
    # 1. TOP METRICS ROW
    col1, col2, col3, col4 = st.columns(4)
    curr_price = hist_data['Close'].iloc[-1]
    prev_price = hist_data['Close'].iloc[-2]
    change = ((curr_price - prev_price) / prev_price) * 100

    col1.metric("Current Price", f"₹{curr_price:,.2f}", f"{change:+.2f}%")
    col2.metric("Market Cap", f"₹{ticker_info.get('marketCap', 0)/1e7:,.0f} Cr")
    col3.metric("P/E Ratio", f"{ticker_info.get('trailingPE', 'N/A')}")
    col4.metric("52W High", f"₹{ticker_info.get('fiftyTwoWeekHigh', 0):,.2f}")

    # 2. TABS FOR DEEP DIVE
    tab_chart, tab_fundamental, tab_news = st.tabs(["📈 Technical Chart", "🧬 Fundamental Analysis", "📰 News & Sentiment"])

    with tab_chart:
        # Time Period Selector for Chart
        period_col1, period_col2 = st.columns([1, 4])
        with period_col1:
            time_frame = st.radio("Time Frame", ["1M", "3M", "6M", "1Y", "5Y"], index=3, horizontal=True)
        
        # Plotly Candlestick Chart
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=hist_data.index,
            open=hist_data['Open'],
            high=hist_data['High'],
            low=hist_data['Low'],
            close=hist_data['Close'],
            name='Price'
        ))
        
        # Add a Moving Average
        hist_data['MA50'] = hist_data['Close'].rolling(window=50).mean()
        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['MA50'], line=dict(color='orange', width=1), name='50 Day MA'))

        fig.update_layout(
            template="plotly_white",
            xaxis_rangeslider_visible=False,
            height=500,
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab_fundamental:
        st.subheader("Key Ratios & Value Chain Info")
        f_col1, f_col2 = st.columns(2)
        
        with f_col1:
            st.write("**Margins & Efficiency**")
            st.write(f"- Operating Margin: {ticker_info.get('operatingMargins', 0)*100:.2f}%")
            st.write(f"- ROE: {ticker_info.get('returnOnEquity', 0)*100:.2f}%")
            st.write(f"- Debt to Equity: {ticker_info.get('debtToEquity', 'N/A')}")

        with f_col2:
            st.write("**Growth Metrics**")
            st.write(f"- Revenue Growth (YoY): {ticker_info.get('revenueGrowth', 0)*100:.2f}%")
            st.write(f"- Earnings Growth (YoY): {ticker_info.get('earningsGrowth', 0)*100:.2f}%")
            st.write(f"- Dividend Yield: {ticker_info.get('dividendYield', 0)*100:.2f}%")

    with tab_news:
        st.subheader(f"Latest Market Intelligence for {search_ticker}")
        news = yf.Ticker(search_ticker).news
        if news:
            for item in news[:5]:
                with st.expander(item['title']):
                    st.write(f"**Publisher:** {item['publisher']}")
                    st.write(f"**Link:** [Read Article]({item['link']})")
        else:
            st.info("No recent news found for this ticker.")

else:
    st.error("Ticker not found. Please ensure you include the '.NS' suffix for Indian stocks (e.g., RELIANCE.NS).")

# --- FOOTER / AUTOMATION STATUS ---
st.divider()
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data source: Yahoo Finance")
