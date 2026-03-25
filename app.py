import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import os
from datetime import datetime, timedelta

# --- CONFIG ---
DB_FILE = "moonshot_portfolio.xlsx"
BENCHMARKS = {
    "Nifty 50": "^NSEI",
    "Nifty Midcap 150": "NIFTY_MIDCAP_150.NS",
    "BSE 500": "^BSE500"
}

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
    return f"{t}.NS" if not t.endswith('.NS') and not t.startswith('^') else t

# --- SESSION STATE FOR LOCKING ---
if 'locked' not in st.session_state:
    st.session_state['locked'] = False

# --- SIDEBAR ---
st.sidebar.header("🕹️ Controls")
if st.sidebar.button("🔓 Unlock Data Entry"):
    st.session_state['locked'] = False
    st.rerun()

# --- APP START ---
st.title("🚀 Moonshot NAV")

init_db, trans_db, meta_db = load_from_excel()

# 1. INPUT SECTION (Locked/Unlocked)
if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    
    if meta_db is None:
        meta_data = pd.DataFrame([{"Date": datetime(2025, 1, 1), "Total_Value": 100000.0, "Cash_Percent": 10.0}])
    else:
        meta_data = meta_db
    edited_meta = st.data_editor(meta_data, num_rows="fixed", key="meta_edit")

    if init_db is None:
        init_data = pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    else:
        init_data = init_db
    edited_init = st.data_editor(init_data, num_rows="dynamic", key="init_edit")

    if trans_db is None:
        trans_data = pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    else:
        trans_data = trans_db
    edited_trans = st.data_editor(trans_data, num_rows="dynamic", key="trans_edit")

    total_w = edited_init["Weight_Percent"].sum() + edited_meta["Cash_Percent"].iloc[0]
    
    if st.button("🔒 Save & Lock to View Report"):
        if round(total_w, 2) == 100.0:
            save_to_excel(edited_init, edited_trans, edited_meta)
            st.session_state['locked'] = True
            st.success("Data locked. Generating report...")
            st.rerun()
        else:
            st.error(f"Total Weight must be 100% (Current: {total_w}%)")
    st.stop()

# --- 2. READ-ONLY REPORT SECTION ---
else:
    st.info("🔒 Data is locked. Use the sidebar to unlock or filter periods.")
    
    # SETUP DATE FILTERS
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0])
    st.sidebar.subheader("📅 Filter Period")
    start_filter = st.sidebar.date_input("Start Date", value=abs_start, min_value=abs_start)
    end_filter = st.sidebar.date_input("End Date", value=datetime.now())

    total_val = float(meta_db['Total_Value'].iloc[0])
    cash_p = float(meta_db['Cash_Percent'].iloc[0])
    
    holdings = {}
    with st.spinner("Processing Market Intelligence..."):
        # Calculate Base Quantities
        for _, row in init_db.iterrows():
            t = format_ticker(row['Ticker'])
            w = float(row['Weight_Percent']) / 100
            # Get price at the absolute start to determine initial qty
            p_df = yf.download(t, start=abs_start, end=abs_start + timedelta(days=7), progress=False)['Close']
            if not p_df.empty:
                holdings[t] = holdings.get(t, 0.0) + float((total_val * w) / p_df.iloc[0])

        current_cash = total_val * (cash_p / 100)
        if trans_db is not None:
            for _, row in trans_db.iterrows():
                t = format_ticker(row['Ticker'])
                if row['Type'] == "BUY":
                    holdings[t] = holdings.get(t, 0.0) + float(row['Qty'])
                    current_cash -= float(row['Amount'])
                elif row['Type'] == "SELL":
                    holdings[t] = holdings.get(t, 0.0) - float(row['Qty'])
                    current_cash += float(row['Amount'])
                elif row['Type'] == "CASH_DEPOSIT":
                    current_cash += float(row['Amount'])

        # Fetch Prices for Portfolio + All Benchmarks
        ticker_list = [t for t in holdings.keys() if t != "CASH"]
        bench_list = list(BENCHMARKS.values())
        all_data = yf.download(ticker_list + bench_list, start=start_filter, end=end_filter, progress=False)['Close']
        all_data = all_data.ffill()

        # Portfolio NAV Calculation
        port_ts
