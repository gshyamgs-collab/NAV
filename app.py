import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
from datetime import datetime, timedelta

# --- CONFIG ---
DB_FILE = "moonshot_portfolio.xlsx"
BENCHMARK = "^NSEI"

st.set_page_config(page_title="Moonshot NAV", layout="wide", page_icon="🚀")

# --- DATABASE ENGINE ---
def save_to_excel(init_df, trans_df, meta_df):
    with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
        init_df.to_excel(writer, sheet_name="Initial_Setup", index=False)
        trans_df.to_excel(writer, sheet_name="Transactions", index=False)
        meta_df.to_excel(writer, sheet_name="Metadata", index=False)

def load_from_excel():
    if not os.path.exists(DB_FILE): return None, None, None
    try:
        return (pd.read_excel(DB_FILE, sheet_name="Initial_Setup"),
                pd.read_excel(DB_FILE, sheet_name="Transactions"),
                pd.read_excel(DB_FILE, sheet_name="Metadata"))
    except: return None, None, None

def format_ticker(t):
    if not t or pd.isna(t): return ""
    t = str(t).strip().upper()
    if t in ["CASH", ""]: return "CASH"
    return f"{t}.NS" if not t.endswith('.NS') and not t.startswith('^') else t

# --- SIDEBAR: SEARCH TOOL ---
st.sidebar.header("🔍 Ticker Finder (NSE)")
search_query = st.sidebar.text_input("Search Company Name", placeholder="e.g. Reliance, HDFC")

if search_query:
    try:
        # Simple heuristic search for Indian markets
        search_results = yf.Search(search_query, max_results=5).quotes
        if search_results:
            st.sidebar.write("Found Tickers:")
            for res in search_results:
                symbol = res.get('symbol', '')
                short_name = res.get('shortname', 'N/A')
                if ".NS" in symbol or "^" in symbol:
                    st.sidebar.code(symbol.replace(".NS", ""), language=None)
                    st.sidebar.caption(short_name)
        else:
            st.sidebar.warning("No NSE tickers found.")
    except:
        st.sidebar.error("Search temporarily unavailable.")

st.sidebar.divider()
st.sidebar.header("🛡️ Validation Check")

# --- APP START ---
st.title("🚀 Moonshot NAV")

init_db, trans_db, meta_db = load_from_excel()

# 1. SETUP UI (Spreadsheet Style)
st.markdown("### 📊 Portfolio Initialization")

if meta_db is None:
    meta_data = pd.DataFrame([{"Date": datetime(2025, 1, 1), "Total_Value": 100000.0, "Cash_Percent": 10.0}])
else:
    meta_data = meta_db

edited_meta = st.data_editor(meta_data, num_rows="fixed", key="meta_edit", use_container_width=True)

if init_db is None:
    init_data = pd.DataFrame([
        {"Ticker": "RELIANCE", "Weight_Percent": 40.0},
        {"Ticker": "TCS", "Weight_Percent": 30.0},
        {"Ticker": "HDFCBANK", "Weight_Percent": 20.0}
    ])
else:
    init_data = init_db

edited_init = st.data_editor(init_data, num_rows="dynamic", key="init_edit", use_container_width=True)

# Validation Logic
total_stock_w = edited_init["Weight_Percent"].sum()
cash_w = edited_meta["Cash_Percent"].iloc[0]
grand_total_w = total_stock_w + cash_w

if round(grand_total_w, 2) == 100.00:
    st.sidebar.success(f"✅ Balance: {grand_total_w}%")
    can_save = True
else:
    st.sidebar.error(f"❌ Balance: {grand_total_w}%")
    st.sidebar.warning(f"Needed: {round(100 - grand_total_w, 2)}%")
    can_save = False

# 2. TRANSACTIONS
st.markdown("### 💸 Activity Ledger")
if trans_db is None:
    trans_data = pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
else:
    trans_data = trans_db

edited_trans = st.data_editor(trans_data, num_rows="dynamic", key="trans_edit", use_container_width=True)

if st.button("💾 Save Ledger", disabled=not can_save):
    save_to_excel(edited_init, edited_trans, edited_meta)
    st.success("Changes Saved!")
    st.rerun()

# --- 3. DASHBOARD ---
if init_db is not None and can_save:
    start_dt = pd.to_datetime(edited_meta['Date'].iloc[0])
    total_val = float(edited_meta['Total_Value'].iloc[0])
    
    holdings = {}
    with st.spinner("Calculating Live NAV..."):
        for _, row in edited_init.iterrows():
            t = format_ticker(row['Ticker'])
            w = float(row['Weight_Percent']) / 100
            p_df = yf.download(t, start=start_dt, end=start_dt + timedelta(days=7), progress=False)['Close']
            if not p_df.empty:
                holdings[t] = (total_val * w) / p_df.iloc[0]

        current_cash = total_val * (cash_w / 100)
        for _, row in edited_trans.iterrows():
            t = format_ticker(row['Ticker'])
            if row['Type'] == "BUY":
                holdings[t] = holdings.get(t, 0) + row['Qty']
                current_cash -= row['Amount']
            elif row['Type'] == "SELL":
                holdings[t] = holdings.get(t, 0) - row['Qty']
                current_cash += row['Amount']
            elif row['Type'] == "CASH_DEPOSIT":
                current_cash += row['Amount']

        clean_tix = [t for t in holdings.keys() if t != "CASH"] + [BENCHMARK]
        prices = yf.download(clean_tix, start=start_dt, progress=False)['Close']
        prices = prices.ffill()

        port_ts = pd.Series(0.0, index=prices.index)
        for t, q in holdings.items():
            if t in prices.columns: port_ts += prices[t] * q
        
        daily_nav = port_ts + current_cash

    # Display Visuals
    norm_nav = (daily_nav / daily_nav.iloc[0]) * 100
    norm_nifty = (prices[BENCHMARK] / prices[BENCHMARK].iloc[0]) * 100
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=norm_nav.index, y=norm_nav, name="Moonshot NAV", line=dict(color='#00ff88')))
    fig.add_trace(go.Scatter(x=norm_nifty.index, y=norm_nifty, name="Nifty 50", line=dict(color='white', dash='dot')))
    fig.update_layout(template="plotly_dark", height=450, margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Current Status Table
    st.write("### 💎 Live Portfolio Composition")
    curr_total = daily_nav.iloc[-1]
    last_p = prices.iloc[-1]
    comp_data = []
    for t, q in holdings.items():
        if q > 0:
            val = q * last_p[t]
            comp_data.append({"Ticker": t, "Value": val, "Weight (%)": (val/curr_total)*100})
    comp_data.append({"Ticker": "CASH", "Value": current_cash, "Weight (%)": (current_cash/curr_total)*100})
    
    st.dataframe(pd.DataFrame(comp_data).style.format({"Value": "₹{:,.2f}", "Weight (%)": "{:.2f}%"}), use_container_width=True, hide_index=True)
