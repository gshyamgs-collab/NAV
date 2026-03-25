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
    "Nifty Midcap 100": "^NSEMDCP100"
}

st.set_page_config(page_title="Moonshot NAV Intelligence", layout="wide", page_icon="🚀")

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

def format_ticker(t):
    if not t or pd.isna(t): return ""
    t = str(t).strip().upper()
    if t in ["CASH", ""]: return "CASH"
    # Ensure Indian stocks have .NS and indices keep their ^
    return f"{t}.NS" if not t.endswith('.NS') and not t.startswith('^') else t

# --- APP START ---
st.title("🚀 Moonshot NAV Intelligence")
init_db, trans_db, meta_db = load_from_excel()

if 'locked' not in st.session_state:
    st.session_state['locked'] = False

st.sidebar.header("🕹️ Controls")
if st.sidebar.button("🔓 Unlock & Edit Data"):
    st.session_state['locked'] = False
    st.rerun()

if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    m_df = meta_db if meta_db is not None else pd.DataFrame([{"Date": datetime(2025, 1, 1).date(), "Total_Value": 100000.0, "Cash_Percent": 10.0}])
    edited_meta = st.data_editor(m_df, key="meta_edit", use_container_width=True)
    
    i_df = init_db if init_db is not None else pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    edited_init = st.data_editor(i_df, num_rows="dynamic", key="init_edit", use_container_width=True)
    
    t_df = trans_db if trans_db is not None else pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    edited_trans = st.data_editor(t_df, num_rows="dynamic", key="trans_edit", use_container_width=True)

    if st.button("🔒 Save & Lock to Analyze"):
        # Clean data before saving (remove empty rows)
        edited_init = edited_init.dropna(subset=['Ticker'])
        save_to_excel(edited_init, edited_trans, edited_meta)
        st.session_state['locked'] = True
        st.rerun()
    st.stop()

else:
    # --- CALCULATION ENGINE ---
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0]).date()
    today = datetime.now().date()
    
    with st.spinner("Fetching Market Data & Updating Portfolio..."):
        holdings = {}
        total_val = float(meta_db['Total_Value'].iloc[0])
        
        # 1. Process Initial Setup
        for _, row in init_db.iterrows():
            t = format_ticker(row['Ticker'])
            if t == "CASH": continue
            
            w = float(row['Weight_Percent']) / 100
            # Lookback window to handle weekends/holidays for start price
            p_df = yf.download(t, start=abs_start - timedelta(days=7), end=abs_start + timedelta(days=1), progress=False)['Close']
            
            if not p_df.empty:
                start_price = float(p_df.iloc[-1]) # Get the closest price to start date
                holdings[t] = (total_val * w) / start_price
            else:
                st.warning(f"Could not find price for {t}. Check ticker symbol.")

        # 2. Process Transactions
        current_cash = total_val * (float(meta_db['Cash_Percent'].iloc[0]) / 100)
        if trans_db is not None and not trans_db.empty:
            for _, row in trans_db.iterrows():
                t = format_ticker(row['Ticker'])
                qty = float(row['Qty'])
                amt = float(row['Amount'])
                if row['Type'] == "BUY":
                    holdings[t] = holdings.get(t, 0.0) + qty
                    current_cash -= amt
                elif row['Type'] == "SELL":
                    holdings[t] = holdings.get(t, 0.0) - qty
                    current_cash += amt

        # 3. Get Time Series for Charting
        active_tickers = [t for t, q in holdings.items() if q > 0]
        bench_tickers = list(BENCHMARKS.values())
        all_prices = yf.download(active_tickers + bench_tickers, start=abs_start, end=today, progress=False)['Close'].ffill()

    # --- UI TABS ---
    tab_perf, tab_port, tab_act = st.tabs(["📈 Performance", "🏢 Portfolio", "📅 Actions"])

    with tab_perf:
        # Period Tabs
        p_tabs = st.tabs(["1W", "1M", "6M", "1Yr", "3Yr", "5Yr", "Max"])
        deltas = {"1W": 7, "1M": 30, "6M": 182, "1Yr": 365, "3Yr": 1095, "5Yr": 1825, "Max": None}
        
        for i, p_tab in enumerate(p_tabs):
            p_name = list(deltas.keys())[i]
            days = deltas[p_name]
            with p_tab:
                start_f = abs_start if days is None else max(abs_start, today - timedelta(days=days))
                f_prices = all_prices[all_prices.index.date >= start_f]
                
                if not f_prices.empty:
                    # Calculate Portfolio Value over time
                    port_ts = pd.Series(0.0, index=f_prices.index)
                    for t, q in holdings.items():
                        if t in f_prices.columns: port_ts += f_prices[t] * q
                    daily_nav = port_ts + current_cash
                    
                    # Header Metrics
                    m1, m2, m3 = st.columns(3)
                    p_ret = (daily_nav.iloc[-1] / daily_nav.iloc[0] - 1) * 100
                    m1.metric("Portfolio %", f"{p_ret:.2f}%")
                    
                    # Chart
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=daily_nav.index, y=(daily_nav/daily_nav.iloc[0])*100, name="Portfolio", line=dict(color='#00ff88', width=3)))
                    for name, sym in BENCHMARKS.items():
                        if sym in f_prices.columns:
                            b_ret = (f_prices[sym] / f_prices[sym].iloc[0]) * 100
                            fig.add_trace(go.Scatter(x=f_prices.index, y=b_ret, name=name, line=dict(dash='dot')))
                    
                    fig.update_layout(template="plotly_dark", hovermode="x unified", height=450)
                    st.plotly_chart(fig, use_container_width=True, key=f"cht_{p_name}")

    with tab_port:
        st.subheader("Current Holdings")
        curr_prices = all_prices.iloc[-1]
        summary = []
        for t, q in holdings.items():
            if q > 0:
                val = q * curr_prices[t]
                summary.append({"Ticker": t, "Qty": round(q, 2), "Value": val})
        summary.append({"Ticker": "CASH", "Qty": 1, "Value": current_cash})
        st.table(pd.DataFrame(summary))
