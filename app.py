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
        if 'Date' in meta.columns: meta['Date'] = pd.to_datetime(meta['Date']).dt.date
        if 'Date' in trans.columns: trans['Date'] = pd.to_datetime(trans['Date']).dt.date
        return init, trans, meta
    except: return None, None, None

def format_ticker(t):
    if not t or pd.isna(t): return ""
    t = str(t).strip().upper()
    if t in ["CASH", ""]: return "CASH"
    return f"{t}.NS" if not t.endswith('.NS') and not t.startswith('^') else t

def validate_ticker(ticker):
    """Checks if ticker exists in Yahoo Finance"""
    t_obj = yf.Ticker(ticker)
    # Fast check: history returns empty DF for invalid tickers
    hist = t_obj.history(period="1d")
    return not hist.empty

# --- APP START ---
st.title("🚀 Moonshot NAV Intelligence")
init_db, trans_db, meta_db = load_from_excel()

if 'locked' not in st.session_state:
    st.session_state['locked'] = False

# --- SIDEBAR: SEARCH & CONTROLS ---
st.sidebar.header("🔍 Ticker Discovery")
search_query = st.sidebar.text_input("Search Ticker (e.g. RELIANCE)", "").upper()
if search_query:
    formatted_search = format_ticker(search_query)
    if validate_ticker(formatted_search):
        st.sidebar.success(f"✅ {formatted_search} is Valid")
        info = yf.Ticker(formatted_search).info
        st.sidebar.write(f"**Name:** {info.get('longName', 'N/A')}")
        st.sidebar.write(f"**Price:** ₹{info.get('currentPrice', 'N/A')}")
    else:
        st.sidebar.error(f"❌ {formatted_search} not found on Yahoo Finance")

st.sidebar.divider()
st.sidebar.header("🕹️ Controls")
if st.sidebar.button("🔓 Unlock & Edit Data"):
    st.session_state['locked'] = False
    st.rerun()

# --- ENTRY MODE ---
if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    
    # Metadata
    m_df = meta_db if meta_db is not None else pd.DataFrame([{"Date": datetime(2025, 1, 1).date(), "Total_Value": 100000.0, "Cash_Percent": 10.0}])
    edited_meta = st.data_editor(m_df, key="meta_edit", use_container_width=True)
    
    # Initial Portfolio
    st.write("**Initial Portfolio Composition**")
    i_df = init_db if init_db is not None else pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    edited_init = st.data_editor(i_df, num_rows="dynamic", key="init_edit", use_container_width=True)
    
    # Transactions
    st.write("**Ongoing Transactions (BUY/SELL)**")
    t_df = trans_db if trans_db is not None else pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    edited_trans = st.data_editor(t_df, num_rows="dynamic", key="trans_edit", use_container_width=True)

    if st.button("🔒 Save & Lock to Analyze"):
        # VALIDATION BEFORE SAVING
        total_w = edited_init["Weight_Percent"].sum() + edited_meta["Cash_Percent"].iloc[0]
        
        # Check if tickers are valid before locking
        invalid_tickers = []
        for t in edited_init["Ticker"]:
            if not validate_ticker(format_ticker(t)): invalid_tickers.append(t)
        
        if invalid_tickers:
            st.error(f"Invalid Tickers Found: {', '.join(invalid_tickers)}. Please fix them.")
        elif round(total_w, 2) != 100.0:
            st.error(f"Total Weight must be 100% (Current: {total_w}%)")
        else:
            save_to_excel(edited_init, edited_trans, edited_meta)
            st.session_state['locked'] = True
            st.rerun()
    st.stop()

# --- ANALYTICS MODE ---
else:
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0]).date()
    today = datetime.now().date()
    
    with st.spinner("Calculating Performance..."):
        holdings = {}
        total_val = float(meta_db['Total_Value'].iloc[0])
        
        # 1. INITIAL UNITS CALCULATION (Fix: Added Lookback Window)
        for _, row in init_db.iterrows():
            t = format_ticker(row['Ticker'])
            w = float(row['Weight_Percent']) / 100
            
            # Use 7-day window to ensure we catch the last trading day price
            p_df = yf.download(t, start=abs_start - timedelta(days=7), end=abs_start + timedelta(days=1), progress=False)['Close']
            
            if not p_df.empty:
                start_price = float(p_df.iloc[-1]) # Closest price to start date
                holdings[t] = (total_val * w) / start_price
            else:
                st.error(f"CRITICAL: No price data for {t}. Is the ticker correct?")

        # 2. TRANSACTION UPDATES
        current_cash = total_val * (float(meta_db['Cash_Percent'].iloc[0]) / 100)
        if trans_db is not None and not trans_db.empty:
            for _, row in trans_db.iterrows():
                t = format_ticker(row['Ticker'])
                if row['Type'] == "BUY":
                    holdings[t] = holdings.get(t, 0.0) + float(row['Qty'])
                    current_cash -= float(row['Amount'])
                elif row['Type'] == "SELL":
                    holdings[t] = holdings.get(t, 0.0) - float(row['Qty'])
                    current_cash += float(row['Amount'])

        # 3. FETCH FULL PRICE HISTORY
        ticker_list = [t for t, q in holdings.items() if q != 0]
        bench_list = list(BENCHMARKS.values())
        all_prices = yf.download(ticker_list + bench_list, start=abs_start, end=today, progress=False)['Close'].ffill()

    # --- UI TABS ---
    tab_main, tab_comp, tab_ins = st.tabs(["📈 Performance", "🏢 Portfolio", "🔔 Corporate Actions"])

    with tab_main:
        st.write("### NAV vs Benchmarks")
        p_tabs = st.tabs(["1W", "1M", "6M", "1Yr", "3Yr", "5Yr", "Max"])
        deltas = {"1W": 7, "1M": 30, "6M": 182, "1Yr": 365, "3Yr": 1095, "5Yr": 1825, "Max": None}
        
        for i, p_tab in enumerate(p_tabs):
            p_key = list(deltas.keys())[i]
            days = deltas[p_key]
            
            with p_tab:
                start_f = abs_start if days is None else max(abs_start, today - timedelta(days=days))
                filtered_prices = all_prices[all_prices.index.date >= start_f]
                
                if not filtered_prices.empty:
                    port_ts = pd.Series(0.0, index=filtered_prices.index)
                    for t, q in holdings.items():
                        if t in filtered_prices.columns: port_ts += filtered_prices[t] * float(q)
                    daily_nav = port_ts + current_cash
                    
                    # Metrics
                    m_cols = st.columns(len(BENCHMARKS) + 1)
                    p_ret = (daily_nav.iloc[-1] / daily_nav.iloc[0] - 1) * 100
                    m_cols[0].metric("Portfolio Return", f"{p_ret:.2f}%")
                    for idx, (name, sym) in enumerate(BENCHMARKS.items()):
                        if sym in filtered_prices.columns:
                            b_ret = (filtered_prices[sym].iloc[-1] / filtered_prices[sym].iloc[0] - 1) * 100
                            m_cols[idx+1].metric(name, f"{b_ret:.2f}%")

                    # Chart
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=daily_nav.index, y=(daily_nav/daily_nav.iloc[0])*100, name="Portfolio", line=dict(color='#00ff88', width=3)))
                    for name, sym in BENCHMARKS.items():
                        if sym in filtered_prices.columns:
                            fig.add_trace(go.Scatter(x=filtered_prices.index, y=(filtered_prices[sym]/filtered_prices[sym].iloc[0])*100, name=name, line=dict(dash='dot')))
                    
                    fig.update_layout(template="plotly_dark", hovermode="x unified", height=500, margin=dict(l=20, r=20, t=30, b=20))
                    st.plotly_chart(fig, use_container_width=True, key=f"cht_{p_key}")

    with tab_comp:
        st.subheader("Current Composition")
        curr_total = (pd.Series({t: all_prices[t].iloc[-1] * float(q) for t, q in holdings.items() if t in all_prices.columns}).sum()) + current_cash
        comp_data = []
        for t, q in holdings.items():
            if float(q) > 0 and t in all_prices.columns:
                val = float(q) * all_prices[t].iloc[-1]
                comp_data.append({"Ticker": t, "Value": val, "Weight (%)": (val/curr_total)*100})
        comp_data.append({"Ticker": "CASH", "Value": current_cash, "Weight (%)": (current_cash/curr_total)*100})
        st.dataframe(pd.DataFrame(comp_data).style.format({"Value": "₹{:,.2f}", "Weight (%)": "{:.2f}%"}), use_container_width=True, hide_index=True)

    with tab_ins:
        st.subheader("Corporate Actions")
        for t in ticker_list:
            act = yf.Ticker(t).actions
            if not act.empty:
                st.write(f"**{t}**")
                st.table(act.tail(3))
