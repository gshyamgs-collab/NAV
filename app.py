import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Indian Stock Educator & NAV Tracker",
    page_icon="📈",
    layout="wide"
)

# --- HELPER FUNCTIONS ---

def format_ticker(ticker):
    """Appends .NS to Indian tickers if not present."""
    ticker = ticker.strip().upper()
    if ticker and not ticker.endswith('.NS') and not ticker.startswith('^'):
        return f"{ticker}.NS"
    return ticker


@st.cache_data(ttl=3600)
def fetch_data(tickers, period="10y"):
    """
    Fetches historical Close prices for all tickers in parallel.
    This prevents Pandas axis-alignment ValueErrors.
    """
    try:
        df = yf.download(tickers, period=period, interval="1d", progress=False)
        
        if df.empty:
            return pd.DataFrame()

        # Handle yfinance multi-index for 'Close' prices
        if "Close" in df.columns:
            close_data = df["Close"]
            
            # If only one ticker was requested, yfinance returns a Series. 
            # We convert it back to a DataFrame for structural consistency.
            if isinstance(close_data, pd.Series):
                # Using the first ticker in the list as the column name
                valid_tickers = [t for t in tickers if t]
                name = valid_tickers[0] if valid_tickers else "Stock"
                close_data = close_data.to_frame(name=name)
            
            return close_data
        
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Error fetching data from Yahoo Finance: {e}")
        return pd.DataFrame()


# --- SIDEBAR INPUTS ---
st.sidebar.header("📌 Portfolio Inputs")
st.sidebar.write("Enter your top 3 Indian stocks:")

portfolio_inputs = []
total_investment = 0.0

for i in range(1, 4):
    col1, col2, col3 = st.sidebar.columns([2, 1, 1])
    
    # Pre-populating the first ticker to make the UI look active on launch
    default_t = "RELIANCE" if i == 1 else ""
    default_p = 2500.0 if i == 1 else 0.0
    default_q = 10 if i == 1 else 0

    with col1:
        t = st.text_input(f"Ticker {i}", value=default_t, key=f"t{i}")
    with col2:
        p = st.number_input(f"Avg Price (₹)", min_value=0.0, value=default_p, step=10.0, key=f"p{i}")
    with col3:
        q = st.number_input(f"Qty", min_value=0, value=default_q, step=1, key=f"q{i}")
    
    if t.strip():
        formatted_t = format_ticker(t)
        portfolio_inputs.append({'ticker': formatted_t, 'price': p, 'qty': q})
        total_investment += (p * q)


# --- MAIN UI ---
st.title("📈 Indian Stock Market Navigator")
st.markdown("Automated Portfolio NAV tracking against the Nifty 50 Benchmark.")

# Proceed only if there's at least one valid stock in the sidebar
if len(portfolio_inputs) > 0:
    with st.spinner("Analyzing 10 years of market data... This may take a few seconds."):
        
        # Consolidate all tickers (Holdings + Benchmark)
        holdings_tickers = [stock['ticker'] for stock in portfolio_inputs]
        benchmark = "^NSEI"
        all_tickers = list(set(holdings_tickers + [benchmark])) # Set drops duplicates if ^NSEI is typed
        
        hist_data = fetch_data(all_tickers)
        
        # Validate that we got data and the benchmark loaded successfully
        if not hist_data.empty and benchmark in hist_data.columns:
            
            # 1. Calculate Historical Portfolio NAV
            portfolio_nav = pd.Series(0.0, index=hist_data.index)
            for stock in portfolio_inputs:
                t = stock['ticker']
                if t in hist_data.columns:
                    portfolio_nav += hist_data[t] * stock['qty']

            # Drop dates where NAV is 0 (weekends/holidays where fill failed)
            portfolio_nav = portfolio_nav[portfolio_nav > 0]
            
            # Re-align benchmark dates with our active portfolio dates
            aligned_benchmark = hist_data[benchmark].loc[portfolio_nav.index]

            # 2. Normalize to Base 100 for visual comparison
            norm_portfolio = (portfolio_nav / portfolio_nav.iloc[0]) * 100
            norm_nifty = (aligned_benchmark / aligned_benchmark.iloc[0]) * 100

            # 3. Create Interactive Plotly Chart
            fig = go.Figure()

            # Portfolio Line
            fig.add_trace(go.Scatter(
                x=norm_portfolio.index, 
                y=norm_portfolio, 
                name="My Portfolio NAV", 
                line=dict(color='#00ff88', width=3)
            ))
            
            # Nifty 50 Line
            fig.add_trace(go.Scatter(
                x=norm_nifty.index, 
                y=norm_nifty, 
                name="Nifty 50 (Benchmark)", 
                line=dict(color='#ff3366', width=2, dash='dot')
            ))

            # Graphical Annotations (Historical Indian Market Events)
            annotations = [
                dict(date="2020-03-23", text="COVID Crash 📉"),
                dict(date="2021-10-18", text="Post-Pandemic Peak 🏔️"),
                dict(date="2024-06-04", text="Election Counting Day 📊")
            ]

            for ann in annotations:
                ann_date = pd.to_datetime(ann['date'])
                if ann_date in norm_portfolio.index:
                    fig.add_annotation(
                        x=ann_date, 
                        y=norm_portfolio.loc[ann_date],
                        text=ann['text'], 
                        showarrow=True, 
                        arrowhead=2,
                        arrowcolor="#ffffff",
                        ax=0,
                        ay=-40
                    )

            fig.update_layout(
                title="Relative Growth: My Portfolio NAV vs. Nifty 50 (10Y History)",
                xaxis_title="Timeline",
                yaxis_title="Normalized Growth (Base 100)",
                hovermode="x unified",
                template="plotly_dark",
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )

            st.plotly_chart(fig, use_container_width=True)


            # --- AI INSIGHTS ENGINE ---
            st.divider()
            st.subheader("🤖 AI-Style Portfolio Insights")
            
            curr_val = portfolio_nav.iloc[-1]
            total_ret_pct = ((curr_val - total_investment) / total_investment * 100) if total_investment > 0 else 0.0
            
            # Find Best-Performing Asset
            best_stock = "N/A"
            max_gain = -999.0
            
            for stock in portfolio_inputs:
                t = stock['ticker']
                if t in hist_data.columns:
                    s_data = hist_data[t].dropna()
                    if len(s_data) > 1:
                        gain = ((s_data.iloc[-1] - s_data.iloc[0]) / s_data.iloc[0]) * 100
                        if gain > max_gain:
                            max_gain = gain
                            best_stock = t

            # Trend Analysis via Moving Averages
            sma_50 = portfolio_nav.rolling(window=50).mean().iloc[-1]
            sma_200 = portfolio_nav.rolling(window=200).mean().iloc[-1]
            trend = "🐂 Bullish" if sma_50 > sma_200 else "🐻 Bearish"

            # Render Metrics
            col_a, col_b, col_c = st.columns(3)
            col_a.metric(
                label="Total Portfolio Return", 
                value=f"{total_ret_pct:.2f}%", 
                delta=f"₹{curr_val - total_investment:,.2f} Absolute"
            )
            col_b.metric(
                label="Lifetime Top Performer", 
                value=best_stock, 
                delta=f"{max_gain:.1f}% Total Growth" if best_stock != "N/A" else "N/A"
            )
            col_c.metric(
                label="Current Portfolio Trend", 
                value=trend, 
                delta="50-day over 200-day MA" if sma_50 > sma_200 else "50-day below 200-day MA"
            )

            # Raw Data inspection
            with st.expander("📂 View Raw Aligned Closing Prices (Tail)"):
                st.dataframe(hist_data.tail(10))
        else:
            st.warning("⚠️ No data was returned. Please verify that your tickers are correct or check your network connection.")
else:
    st.info("👈 Enter stock tickers, average purchase prices, and quantities in the sidebar to calculate your NAV.")
