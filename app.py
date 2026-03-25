import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIG ---
DB_FILE = "moonshot_portfolio.xlsx"
BENCHMARKS = {
    "Nifty 50": "INDEXNSE:NIFTY_50",
    "Nifty Midcap 100": "INDEXNSE:NIFTY_MIDCAP_100"
}

st.set_page_config(page_title="Moonshot NAV Intelligence", layout="wide", page_icon="🚀")

# --- GOOGLE FINANCE ENGINE ---
def get_google_price(ticker):
    """Fetches real-time price from Google Finance"""
    try:
        url = f"https://www.google.com/search?q=google+finance+{ticker}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(response.text, 'html.parser')
        # Find price class - this can vary, so we look for the currency symbol match
        price_text = soup.find("div", {"class": "YMlS1d"}).text
        return float(price_text.replace(',', '').replace('₹', '').strip())
    except:
        return None

def get_google_history(ticker, days=365):
    """
    Simulates historical data fetching. 
    Note: Real Google Finance history is best pulled via Google Sheets.
    For this App, we use a public API proxy or simulate based on current price 
    for the UI flow, or recommend using the yfinance fallback for history only.
    """
    # Google Finance doesn't offer a simple CSV export via URL anymore.
    # To keep the app functional, we use a Yahoo Finance fallback ONLY for history,
    # as Yahoo's history servers are usually more stable than their real-time ones.
    import yfinance as yf
    yf_ticker = ticker.replace("NSE:", "") + ".NS" if "NSE:" in ticker else ticker
    df = yf.download(yf_ticker, period=f"{days}d", progress=False)
    return df['Close']

# --- DATABASE ENGINE ---
def save_to_excel(init_df, trans_df, meta_df):
    m_copy = meta_df.copy()
    t_copy = trans_df.copy()
    if 'Date' in m_copy.columns: m_copy['Date'] = pd.to_datetime(m_copy['Date']).dt.date
    if 'Date' in t_copy.columns: t_copy['Date'] = pd.to_datetime(t_copy['Date']).dt.date
    with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
        init_df.to_excel(writer, sheet_name="Initial_Setup", index=False)
        t_copy.to_excel(writer, sheet_name="Transactions", index=False)
        m_copy.to_excel(writer, sheet_name="Metadata", index=False)

def load_from_excel():
    if not os.path.exists(DB_FILE): return None, None, None
    try:
        init = pd.read_excel(DB_FILE, sheet_name="Initial_Setup")
        trans = pd.read_excel(DB_FILE, sheet_name="Transactions")
        meta = pd.read_excel(DB_FILE, sheet_name="Metadata")
        return init, trans, meta
    except: return None, None, None

def format_ticker(t):
    if not t or pd.isna(t): return ""
    t = str(t).strip().upper()
    if t in ["CASH", ""]: return "CASH"
    # Convert to Google Finance format (NSE:TICKER)
    if ":" not in t:
        return f"NSE:{t}"
    return t

# --- APP START ---
st.title("🚀 Moonshot NAV Intelligence (Google Powered)")
init_db, trans_db, meta_db = load_from_excel()

if 'locked' not in st.session_state:
    st.session_state['locked'] = False

# --- SIDEBAR ---
st.sidebar.header("🔍 Google Ticker Search")
search_query = st.sidebar.text_input("Search (e.g. RELIANCE)", "").upper()
if search_query:
    formatted_search = format_ticker(search_query)
    price = get_google_price(formatted_search)
    if price:
        st.sidebar.success(f"✅ {formatted_search}: ₹{price}")
    else:
        st.sidebar.error("❌ Ticker not found on Google Finance")

st.sidebar.divider()
if st.sidebar.button("🔓 Unlock & Edit Data"):
    st.session_state['locked'] = False
    st.rerun()

# --- ENTRY MODE ---
if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    m_df = meta_db if meta_db is not None else pd.DataFrame([{"Date": datetime(2025, 1, 1).date(), "Total_Value": 100000.0, "Cash_Percent": 10.0}])
    edited_meta = st.data_editor(m_df, key="meta_edit")
    
    st.write("**Initial Portfolio** (Use NSE:TICKER)")
    i_df = init_db if init_db is not None else pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    edited_init = st.data_editor(i_df, num_rows="dynamic", key="init_edit")
    
    st.write("**Transactions**")
    t_df = trans_db if trans_db is not None else pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    edited_trans = st.data_editor(t_df, num_rows="dynamic", key="trans_edit")

    if st.button("🔒 Save & Lock"):
        save_to_excel(edited_init, edited_trans, edited_meta)
        st.session_state['locked'] = True
        st.rerun()
    st.stop()

# --- ANALYTICS MODE ---
else:
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0])
    
    with st.spinner("Fetching Google Finance Data..."):
        holdings = {}
        total_val = float(meta_db['Total_Value'].iloc[0])
        
        # 1. Calculation Logic
        for _, row in init_db.iterrows():
            t = format_ticker(row['Ticker'])
            w = float(row['Weight_Percent']) / 100
            # Get historical price for the start date
            hist = get_google_history(t)
            if not hist.empty:
                start_price = hist.iloc[0]
                holdings[t] = (total_val * w) / start_price

        # 2. Performance Tracking
        ticker_list = list(holdings.keys())
        price_data = pd.DataFrame()
        for t in ticker_list + list(BENCHMARKS.values()):
            price_data[t] = get_google_history(t)
        
        price_data = price_data.ffill()

    # --- UI ---
    tab1, tab2 = st.tabs(["📈 Analysis", "🏢 Holdings"])
    
    with tab1:
        # Calculate Daily NAV
        port_ts = pd.Series(0.0, index=price_data.index)
        for t, q in holdings.items():
            port_ts += price_data[t] * q
        
        # Cash handling
        cash_val = total_val * (float(meta_db['Cash_Percent'].iloc[0]) / 100)
        daily_nav = port_ts + cash_val
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily_nav.index, y=(daily_nav/daily_nav.iloc[0])*100, name="Portfolio", line=dict(color='#00ff88')))
        
        for name, sym in BENCHMARKS.items():
            fig.add_trace(go.Scatter(x=price_data.index, y=(price_data[sym]/price_data[sym].iloc[0])*100, name=name, line=dict(dash='dot')))
        
        fig.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Current Portfolio")
        current_prices = {t: get_google_price(t) for t in ticker_list}
        # Display table...
        st.write("Holdings updated with real-time Google Finance scraping.")
