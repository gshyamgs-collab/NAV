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

st.set_page_config(page_title="Moonshot NAV", layout="wide")

# --- UTILS ---
def save_data(df, sheet_name):
    if not os.path.exists(DB_FILE):
        with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    else:
        with pd.ExcelWriter(DB_FILE, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

def load_data(sheet_name):
    if not os.path.exists(DB_FILE): return None
    try: return pd.read_excel(DB_FILE, sheet_name=sheet_name)
    except: return None

def format_ticker(t):
    if not t: return ""
    t = str(t).strip().upper()
    if t == "CASH": return "CASH"
    return f"{t}.NS" if not t.endswith('.NS') and not t.startswith('^') else t

def get_price_safely(ticker, start_date):
    try:
        # Search a window to avoid weekend/holiday gaps
        data = yf.download(ticker, start=start_date, end=start_date + timedelta(days=7), progress=False)
        if not data.empty: return float(data['Close'].iloc[0])
        fallback = yf.download(ticker, period="1d", progress=False)
        return float(fallback['Close'].iloc[-1])
    except: return 0.0

# --- DATA PREP ---
init_df = load_data("Initial_Setup")
meta_df = load_data("Metadata")
trans_df = load_data("Transactions")

if init_df is None:
    # ... (Keep your Initial Setup Form here as per previous version)
    st.info("Please complete the Initial Portfolio Setup to continue.")
    # [Insert the Setup Form logic from previous response here]
    st.stop()

# --- MAIN LOGIC ---
start_date = pd.to_datetime(meta_df['Start_Date'].iloc[0])
current_cash = float(meta_df['Init_Cash'].iloc[0])

# Reconstruct current holdings from Setup + Transactions
holdings = init_df.set_index("Ticker")['Qty'].to_dict()

if trans_df is not None and not trans_df.empty:
    for _, row in trans_df.iterrows():
        t = row['Ticker']
        if row['Type'] == "Buy":
            holdings[t] = holdings.get(t, 0) + row['Qty']
            current_cash -= row['Amount']
        elif row['Type'] == "Sell":
            holdings[t] = holdings.get(t, 0) - row['Qty']
            current_cash += row['Amount']
        elif row['Type'] == "Cash Deposit":
            current_cash += row['Amount']

# --- SIDEBAR ---
st.sidebar.header("Manage Moonshot")
with st.sidebar.expander("Add Entry"):
    ttype = st.selectbox("Type", ["Buy", "Sell", "Cash Deposit"])
    tdate = st.date_input("Date")
    if ttype != "Cash Deposit":
        ttick = format_ticker(st.text_input("Stock Ticker"))
        tqty = st.number_input("Qty", min_value=0.0)
        tamt = st.number_input("Total Value (₹)", min_value=0.0)
    else:
        ttick, tqty = "CASH", 0
        tamt = st.number_input("Amount (₹)", min_value=0.0)
    
    if st.button("Save Transaction"):
        new_row = pd.DataFrame([{"Date": tdate, "Type": ttype, "Ticker": ttick, "Qty": tqty, "Amount": tamt}])
        updated_trans = pd.concat([trans_df, new_row]) if trans_df is not None else new_row
        save_data(updated_trans, "Transactions")
        st.rerun()

# --- FETCH DATA ---
# IMPORTANT: Filter out "CASH" or empty tickers before passing to yf.download
fetch_list = [t for t in holdings.keys() if t and t != "CASH"]
fetch_list.append(BENCHMARK)

with st.spinner("Downloading Prices..."):
    # Using fetch_list ensures yfinance never sees the string "CASH"
    raw_data = yf.download(fetch_list, start=start_date, progress=False)['Close']
    raw_data = raw_data.ffill().dropna(how='all')

# --- CALCULATE NAV ---
portfolio_val = pd.Series(0.0, index=raw_data.index)
for t, q in holdings.items():
    if t in raw_data.columns:
        portfolio_val += raw_data[t] * q

daily_nav = portfolio_val + current_cash
norm_nav = (daily_nav / daily_nav.iloc[0]) * 100
norm_nifty = (raw_data[BENCHMARK] / raw_data[BENCHMARK].iloc[0]) * 100

# --- UI DISPLAY ---
st.header("🚀 Moonshot NAV Dashboard")
fig = go.Figure()
fig.add_trace(go.Scatter(x=norm_nav.index, y=norm_nav, name="Portfolio", line=dict(color='#00ff88')))
fig.add_trace(go.Scatter(x=norm_nifty.index, y=norm_nifty, name="Nifty 50", line=dict(color='white', dash='dot')))
st.plotly_chart(fig, use_container_width=True)

# Metrics
c1, c2, c3 = st.columns(3)
c1.metric("Current NAV", f"₹{daily_nav.iloc[-1]:,.2f}")
c2.metric("Available Cash", f"₹{current_cash:,.2f}")
c3.metric("Total Profit", f"{( (daily_nav.iloc[-1]/daily_nav.iloc[0]) -1)*100:.2f}%")

if st.sidebar.button("Reset Everything"):
    if os.path.exists(DB_FILE): os.remove(DB_FILE)
    st.rerun()
