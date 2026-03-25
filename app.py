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

# --- DATABASE UTILS ---
def save_data(df, sheet_name):
    if not os.path.exists(DB_FILE):
        with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    else:
        with pd.ExcelWriter(DB_FILE, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

def load_data(sheet_name):
    if not os.path.exists(DB_FILE): return None
    try:
        df = pd.read_excel(DB_FILE, sheet_name=sheet_name)
        return df if not df.empty else None
    except: return None

def format_ticker(t):
    if not t or pd.isna(t): return ""
    t = str(t).strip().upper()
    if t in ["CASH", ""]: return t
    return f"{t}.NS" if not t.endswith('.NS') and not t.startswith('^') else t

def get_price_safely(ticker, start_date):
    """Prevents IndexError by searching a window for the first valid price."""
    try:
        # Search 7 days forward from start_date
        data = yf.download(ticker, start=start_date, end=start_date + timedelta(days=7), progress=False)
        if not data.empty and 'Close' in data.columns:
            return float(data['Close'].iloc[0])
        # Fallback to current price
        fallback = yf.download(ticker, period="1d", progress=False)
        return float(fallback['Close'].iloc[-1])
    except: return 0.0

@st.cache_data(ttl=3600)
def get_stock_info(tickers):
    info_list = []
    # Filter out benchmark and cash
    valid_stocks = [t for t in tickers if t and t != BENCHMARK and t != "CASH"]
    for t in valid_stocks:
        try:
            s = yf.Ticker(t)
            info_list.append({"Ticker": t, "Sector": s.info.get("sector", "Others")})
        except:
            info_list.append({"Ticker": t, "Sector": "Others"})
    return pd.DataFrame(info_list)

# --- APP LOGIC ---
st.title("🚀 Moonshot NAV")

# Load existing data
init_df = load_data("Initial_Setup")
meta_df = load_data("Metadata")
trans_df = load_data("Transactions")

# SIDEBAR OPTIONS
st.sidebar.header("System Controls")
if st.sidebar.button("♻️ Re-Initialize Database"):
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    st.rerun()

# --- 1. INITIAL SETUP SCREEN ---
if init_df is None or meta_df is None:
    st.header("🏗️ Initial Portfolio Setup")
    st.info("Setup your starting portfolio weights. This data will be saved to Excel.")
    
    with st.form("setup_form"):
        col1, col2 = st.columns(2)
        total_val = col1.number_input("Total Portfolio Value (₹)", min_value=1.0, value=100000.0)
        cash_val = col2.number_input("Initial Cash Balance (₹)", min_value=0.0, value=10000.0)
        start_date = st.date_input("Investment Date", value=datetime(2025, 1, 1))
        
        st.write("### Assets & Weights")
        c1, c2, c3 = st.columns(3)
        t1 = c1.text_input("Ticker 1", "RELIANCE")
        w1 = c1.slider("Weight 1 (%)", 0, 100, 40)
        t2 = c2.text_input("Ticker 2", "TCS")
        w2 = c2.slider("Weight 2 (%)", 0, 100, 30)
        t3 = c3.text_input("Ticker 3", "HDFCBANK")
        w3 = c3.slider("Weight 3 (%)", 0, 100, 30)
        
        if st.form_submit_button("Launch Portfolio"):
            if (w1 + w2 + w3) != 100:
                st.error("Weights must sum to 100%!")
            else:
                equity_val = total_val - cash_val
                setup_rows = []
                with st.spinner("Calculating starting quantities..."):
                    for t, w in [(t1, w1), (t2, w2), (t3, w3)]:
                        ft = format_ticker(t)
                        price = get_price_safely(ft, start_date)
                        qty = (equity_val * (w/100)) / price if price > 0 else 0
                        setup_rows.append({"Ticker": ft, "Qty": float(qty)})
                
                save_data(pd.DataFrame(setup_rows), "Initial_Setup")
                save_data(pd.DataFrame([{"Start_Date": start_date, "Init_Cash": cash_val}]), "Metadata")
                save_data(pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"]), "Transactions")
                st.rerun()
    st.stop()

# --- 2. MAIN DASHBOARD ---
# Process data
start_date = pd.to_datetime(meta_df['Start_Date'].iloc[0])
current_cash = float(meta_df['Init_Cash'].iloc[0])
holdings = init_df.set_index("Ticker")['Qty'].to_dict()

# Apply transactions
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

# Sidebar Transactions
with st.sidebar.expander("➕ Add Transaction"):
    ttype = st.selectbox("Action", ["Buy", "Sell", "Cash Deposit"])
    tdate = st.date_input("Date", value=datetime.now())
    if ttype != "Cash Deposit":
        ttick = format_ticker(st.text_input("Stock Ticker"))
        tqty = st.number_input("Quantity", min_value=0.0)
        tamt = st.number_input("Trade Value (₹)", min_value=0.0)
    else:
        ttick, tqty, tamt = "CASH", 0, st.number_input("Amount (₹)", min_value=0.0)
    
    if st.sidebar.button("Save to Ledger"):
        new_row = pd.DataFrame([{"Date": tdate, "Type": ttype, "Ticker": ttick, "Qty": tqty, "Amount": tamt}])
        updated_trans = pd.concat([trans_df, new_row]) if trans_df is not None else new_row
        save_data(updated_trans, "Transactions")
        st.rerun()

# Fetch Prices (STRICT FILTERING)
# Ensure no empty strings or "CASH" enter yfinance
clean_tickers = [t for t in holdings.keys() if t and t != "CASH"]
all_fetch = list(set(clean_tickers + [BENCHMARK]))

with st.spinner("Syncing Market Prices..."):
    # This specifically addresses the TypeError/ValueError by cleaning the ticker list
    price_data = yf.download(all_fetch, start=start_date, progress=False)['Close']
    price_data = price_data.ffill().dropna(how='all')

# NAV Calculation
port_val_series = pd.Series(0.0, index=price_data.index)
for t, q in holdings.items():
    if t in price_data.columns:
        port_val_series += price_data[t] * q

daily_nav = port_val_series + current_cash
norm_nav = (daily_nav / daily_nav.iloc[0]) * 100
norm_nifty = (price_data[BENCHMARK] / price_data[BENCHMARK].iloc[0]) * 100

# Visualization
col_left, col_right = st.columns([2, 1])

with col_left:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=norm_nav.index, y=norm_nav, name="Moonshot Portfolio", line=dict(color='#00ff88', width=2.5)))
    fig.add_trace(go.Scatter(x=norm_nifty.index, y=norm_nifty, name="Nifty 50", line=dict(color='white', dash='dot', width=1)))
    fig.update_layout(template="plotly_dark", title="NAV Performance (Base 100)", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    # Sector Breakdown
    info_df = get_stock_info(list(holdings.keys()))
    latest_p = price_data.iloc[-1]
    sec_rows = []
    for t, q in holdings.items():
        if t in latest_p:
            v = q * latest_p[t]
            s = info_df[info_df['Ticker'] == t]['Sector'].values[0] if not info_df.empty else "Others"
            sec_rows.append({"Sector": s, "Value": v})
    
    if sec_rows:
        sdf = pd.DataFrame(sec_rows).groupby("Sector").sum().reset_index()
        fig_p = px.pie(sdf, values='Value', names='Sector', hole=0.4, title="Sector Allocation", template="plotly_dark")
        st.plotly_chart(fig_p, use_container_width=True)

# Metrics
st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Current NAV", f"₹{daily_nav.iloc[-1]:,.2f}")
c2.metric("Cash Balance", f"₹{current_cash:,.2f}")
c3.metric("Total P/L", f"{((daily_nav.iloc[-1]/daily_nav.iloc[0])-1)*100:.2f}%")
c4.metric("Stocks", len(clean_tickers))
