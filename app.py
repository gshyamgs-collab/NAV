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

# --- UTILITIES ---
def clean_ticker(t):
    """Standardizes any input to a clean symbol for Yahoo/Google lookup"""
    if not t or pd.isna(t): return ""
    t = str(t).strip().upper()
    if ":" in t: t = t.split(":")[-1]
    if t.endswith(".NS"): t = t.replace(".NS", "")
    return t

def get_google_price(ticker):
    """Scrapes Google Finance for real-time price"""
    try:
        symbol = clean_ticker(ticker)
        url = f"https://www.google.com/finance/quote/{symbol}:NSE"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        price_div = soup.find("div", {"class": "YMlS1d"})
        if price_div:
            return float(price_div.text.replace('₹', '').replace(',', '').strip())
    except:
        return None
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

# --- APP START ---
st.title("🚀 Moonshot NAV Intelligence")
init_db, trans_db, meta_db = load_from_excel()

if 'locked' not in st.session_state:
    st.session_state['locked'] = False

# --- SIDEBAR: TICKER SEARCH TOOL ---
st.sidebar.header("🔍 Ticker Search Tool")
search_q = st.sidebar.text_input("Search (e.g. INFOSYS, TCS)", "").upper()
if search_q:
    s_price = get_google_price(search_q)
    if s_price:
        st.sidebar.success(f"✅ {search_q}: ₹{s_price}")
        st.sidebar.caption("Symbol is valid for Portfolio Entry")
    else:
        st.sidebar.error("❌ Symbol not found on NSE")

st.sidebar.divider()
if st.sidebar.button("🔓 Unlock & Edit Data"):
    st.session_state['locked'] = False
    st.rerun()

# --- ENTRY MODE ---
if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        m_df = meta_db if meta_db is not None else pd.DataFrame([{"Date": "2025-01-01", "Total_Value": 100000.0, "Cash_Percent": 10.0}])
        edited_meta = st.data_editor(m_df, key="meta_edit", use_container_width=True)
    
    st.write("**1. Initial Setup (Weights must add to 100% with Cash)**")
    i_df = init_db if init_db is not None else pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    edited_init = st.data_editor(i_df, num_rows="dynamic", key="init_edit", use_container_width=True)
    
    st.write("**2. Ongoing Transactions**")
    t_df = trans_db if trans_db is not None else pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    edited_trans = st.data_editor(t_df, num_rows="dynamic", key="trans_edit", use_container_width=True)

    if st.button("🔒 Save & Generate Analysis"):
        save_to_excel(edited_init, edited_trans, edited_meta)
        st.session_state['locked'] = True
        st.rerun()
    st.stop()

# --- ANALYTICS MODE ---
else:
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0])
    today = datetime.now()
    
    with st.spinner("Processing Portfolio Data..."):
        # Map Holdings
        holdings_qty = {}
        initial_capital = float(meta_db['Total_Value'].iloc[0])
        
        # Step A: Calculate Initial Units
        for _, row in init_db.iterrows():
            sym = clean_ticker(row['Ticker'])
            weight = float(row['Weight_Percent']) / 100
            yf_sym = f"{sym}.NS"
            
            # Fetch price at start date
            data = yf.download(yf_sym, start=abs_start, end=abs_start + timedelta(days=7), progress=False)
            if not data.empty:
                start_px = float(data['Close'].iloc[0])
                holdings_qty[yf_sym] = (initial_capital * weight) / start_px

        # Step B: Adjust for Transactions
        if trans_db is not None and not trans_db.empty:
            for _, row in trans_db.iterrows():
                sym = f"{clean_ticker(row['Ticker'])}.NS"
                qty = float(row['Qty'])
                if row['Type'] == "BUY":
                    holdings_qty[sym] = holdings_qty.get(sym, 0) + qty
                else:
                    holdings_qty[sym] = holdings_qty.get(sym, 0) - qty

        # Step C: Load All History
        active_tickers = [t for t, q in holdings_qty.items() if q != 0]
        all_symbols = active_tickers + list(BENCHMARKS.values())
        df_history = yf.download(all_symbols, start=abs_start, progress=False)['Close'].ffill()

    # --- UI TABS ---
    tab1, tab2 = st.tabs(["📈 NAV Performance", "🏢 Current Holdings"])

    with tab1:
        st.write("### Portfolio NAV vs Benchmarks")
        periods = {"1W": 7, "1M": 30, "6M": 180, "1Y": 365, "Max": None}
        p_choice = st.radio("Select Period", list(periods.keys()), horizontal=True)
        
        # Filter data by period
        if periods[p_choice]:
            filter_date = today - timedelta(days=periods[p_choice])
            plot_df = df_history[df_history.index >= filter_date]
        else:
            plot_df = df_history

        if not plot_df.empty:
            # Calculate Portfolio NAV Series
            port_val = pd.Series(0.0, index=plot_df.index)
            for t, q in holdings_qty.items():
                if t in plot_df.columns:
                    port_val += plot_df[t] * q
            
            cash_val = initial_capital * (float(meta_db['Cash_Percent'].iloc[0])/100)
            daily_nav = port_val + cash_val
            
            # Metrics
            m1, m2 = st.columns(2)
            ret = ((daily_nav.iloc[-1] / daily_nav.iloc[0]) - 1) * 100
            m1.metric("Current Value", f"₹{daily_nav.iloc[-1]:,.2f}")
            m2.metric(f"{p_choice} Return", f"{ret:.2f}%")

            # Chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily_nav.index, y=(daily_nav/daily_nav.iloc[0])*100, 
                                     name="Portfolio", line=dict(color='#00ff88', width=3)))
            
            for b_name, b_sym in BENCHMARKS.items():
                if b_sym in plot_df.columns:
                    fig.add_trace(go.Scatter(x=plot_df.index, y=(plot_df[b_sym]/plot_df[b_sym].iloc[0])*100, 
                                             name=b_name, line=dict(dash='dot')))
            
            fig.update_layout(template="plotly_dark", height=500, hovermode="x unified",
                              yaxis_title="Indexed Value (Base 100)")
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Current Composition")
        h_list = []
        for t, q in holdings_qty.items():
            if q > 0:
                l_price = get_google_price(t) or float(df_history[t].iloc[-1])
                cur_val = q * l_price
                h_list.append({
                    "Ticker": t.replace(".NS", ""),
                    "Quantity": round(q, 2),
                    "Live Price": round(l_price, 2),
                    "Market Value": round(cur_val, 2),
                    "Weight %": round((cur_val / daily_nav.iloc[-1]) * 100, 2)
                })
        
        st.dataframe(pd.DataFrame(h_list), use_container_width=True, hide_index=True)
