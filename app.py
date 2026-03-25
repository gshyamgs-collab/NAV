import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import yfinance as yf

# --- CONFIG ---
DB_FILE = "moonshot_portfolio.xlsx"
BENCHMARKS = {
    "Nifty 50": "^NSEI",
    "Nifty Midcap 100": "^NSEMDCP100"
}

st.set_page_config(page_title="Moonshot NAV Intelligence", layout="wide", page_icon="🚀")

# --- RESILIENT GOOGLE FINANCE SCRAPER ---
def get_google_price(ticker):
    """Fetches real-time price from Google Finance with fallback selectors"""
    try:
        # Format for Google Search
        search_ticker = ticker.replace(".NS", "").replace("NSE:", "")
        url = f"https://www.google.com/finance/quote/{search_ticker}:NSE"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Google Finance often uses this class for the main price
        price_div = soup.find("div", {"class": "YMlS1d"})
        if price_div:
            return float(price_div.text.replace('₹', '').replace(',', '').strip())
        
        # Fallback to yfinance if scraping fails
        yt = yf.Ticker(f"{search_ticker}.NS")
        return yt.fast_info['last_price']
    except:
        return None

# --- DATABASE ENGINE ---
def save_to_excel(init_df, trans_df, meta_df):
    with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
        init_df.to_excel(writer, sheet_name="Initial_Setup", index=False)
        trans_df.to_excel(writer, sheet_name="Transactions", index=False)
        meta_df.to_excel(writer, sheet_name="Metadata", index=False)

def load_from_excel():
    if not os.path.exists(DB_FILE): return None, None, None
    try:
        init = pd.read_excel(DB_FILE, sheet_name="Initial_Setup")
        trans = pd.read_excel(DB_FILE, sheet_name="Transactions")
        meta = pd.read_excel(DB_FILE, sheet_name="Metadata")
        return init, trans, meta
    except: return None, None, None

def format_ticker_yf(t):
    """Converts user input to Yahoo Finance format for reliable history"""
    t = str(t).strip().upper()
    if ":" in t: t = t.split(":")[-1]
    return f"{t}.NS" if not t.endswith(".NS") and not t.startswith("^") else t

# --- APP START ---
st.title("🚀 Moonshot NAV Intelligence")
init_db, trans_db, meta_db = load_from_excel()

if 'locked' not in st.session_state:
    st.session_state['locked'] = False

# --- SIDEBAR ---
st.sidebar.header("🕹️ Controls")
if st.sidebar.button("🔓 Unlock & Edit Data"):
    st.session_state['locked'] = False
    st.rerun()

# --- ENTRY MODE ---
if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    m_df = meta_db if meta_db is not None else pd.DataFrame([{"Date": "2025-01-01", "Total_Value": 100000.0, "Cash_Percent": 10.0}])
    edited_meta = st.data_editor(m_df, key="meta_edit")
    
    i_df = init_db if init_db is not None else pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    edited_init = st.data_editor(i_df, num_rows="dynamic", key="init_edit")
    
    t_df = trans_db if trans_db is not None else pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    edited_trans = st.data_editor(t_df, num_rows="dynamic", key="trans_edit")

    if st.button("🔒 Save & Lock to Analyze"):
        save_to_excel(edited_init, edited_trans, edited_meta)
        st.session_state['locked'] = True
        st.rerun()
    st.stop()

# --- ANALYTICS MODE ---
else:
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0])
    
    with st.spinner("Syncing Market Data..."):
        # 1. Map Holdings
        holdings_qty = {}
        total_initial_cap = float(meta_db['Total_Value'].iloc[0])
        
        # Calculate initial units
        for _, row in init_db.iterrows():
            tk_yf = format_ticker_yf(row['Ticker'])
            weight = float(row['Weight_Percent']) / 100
            hist = yf.download(tk_yf, start=abs_start, end=abs_start + timedelta(days=5), progress=False)
            if not hist.empty:
                px = float(hist['Close'].iloc[0])
                holdings_qty[tk_yf] = (total_initial_cap * weight) / px

        # Apply Transactions
        if not trans_db.empty:
            for _, row in trans_db.iterrows():
                tk_yf = format_ticker_yf(row['Ticker'])
                qty = float(row['Qty'])
                if row['Type'] == "BUY": holdings_qty[tk_yf] = holdings_qty.get(tk_yf, 0) + qty
                else: holdings_qty[tk_yf] = holdings_qty.get(tk_yf, 0) - qty

        # 2. Fetch History for Chart
        all_tickers = list(holdings_qty.keys()) + list(BENCHMARKS.values())
        df_all = yf.download(all_tickers, start=abs_start, progress=False)['Close'].ffill()

    tab1, tab2 = st.tabs(["📈 Performance Analysis", "🏢 Current Holdings"])

    with tab1:
        # Calculate Portfolio NAV
        port_value_series = pd.Series(0.0, index=df_all.index)
        for tk, qty in holdings_qty.items():
            if tk in df_all.columns:
                port_value_series += df_all[tk] * qty
        
        # Add Cash
        static_cash = total_initial_cap * (float(meta_db['Cash_Percent'].iloc[0])/100)
        daily_nav = port_value_series + static_cash
        
        # Metrics
        c1, c2, c3 = st.columns(3)
        current_nav = daily_nav.iloc[-1]
        total_ret = ((current_nav / daily_nav.iloc[0]) - 1) * 100
        c1.metric("Current Portfolio Value", f"₹{current_nav:,.2f}")
        c2.metric("Total Return", f"{total_ret:.2f}%")
        
        # Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily_nav.index, y=(daily_nav/daily_nav.iloc[0])*100, name="Portfolio", line=dict(color='#00ff88', width=3)))
        for name, sym in BENCHMARKS.items():
            if sym in df_all.columns:
                fig.add_trace(go.Scatter(x=df_all.index, y=(df_all[sym]/df_all[sym].iloc[0])*100, name=name, line=dict(dash='dot')))
        
        fig.update_layout(template="plotly_dark", title="Normalized NAV Growth (Base 100)", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Live Portfolio Status")
        holdings_data = []
        for tk, qty in holdings_qty.items():
            if qty > 0:
                live_px = get_google_price(tk) or df_all[tk].iloc[-1]
                curr_val = qty * live_px
                holdings_data.append({
                    "Ticker": tk.replace(".NS", ""),
                    "Quantity": round(qty, 2),
                    "Live Price": round(live_px, 2),
                    "Current Value": round(curr_val, 2),
                    "Weight %": round((curr_val / current_nav) * 100, 2)
                })
        
        holdings_df = pd.DataFrame(holdings_data)
        st.dataframe(holdings_df, use_container_width=True, hide_index=True)
        st.info("Live prices are fetched from Google Finance; historical data via Yahoo Finance for stability.")
