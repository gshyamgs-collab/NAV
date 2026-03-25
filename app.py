import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- CONFIG ---
DB_FILE = "moonshot_portfolio.xlsx"
BENCHMARKS = {
    "Nifty 50": "^NSEI",
    "Nifty Midcap 150": "NIFTY_MIDCAP_150.NS", # Note: yfinance ticker for Midcap 150
    "BSE 500": "^BSE500"
}

st.set_page_config(page_title="Moonshot Intelligence", layout="wide", page_icon="🚀")

# --- UTILS ---
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

# --- APP START ---
init_db, trans_db, meta_db = load_from_excel()

# SIDEBAR CONTROLS
st.sidebar.title("🎮 Dashboard Controls")
if 'locked' not in st.session_state: st.session_state['locked'] = False

if st.sidebar.button("🔓 Edit Portfolio Data"):
    st.session_state['locked'] = False
    st.rerun()

# --- DATA ENTRY MODE ---
if not st.session_state['locked']:
    st.header("📝 Portfolio Configuration")
    # (Data editor logic same as previous version for Initial_Setup, Transactions, Metadata)
    # ... [Assuming user enters data here] ...
    if st.button("🔒 Lock & Analyze"):
        st.session_state['locked'] = True
        st.rerun()
    st.stop()

# --- ANALYSIS MODE ---
else:
    # 1. PERIOD FILTER
    start_db = pd.to_datetime(meta_db['Date'].iloc[0]).date()
    today = datetime.now().date()
    
    st.sidebar.subheader("📅 View Period")
    date_range = st.sidebar.date_input("Select Range", value=(start_db, today), min_value=start_db, max_value=today)
    
    if len(date_range) == 2:
        view_start, view_end = date_range
    else:
        view_start, view_end = start_db, today

    # 2. CALCULATION ENGINE
    with st.spinner("Fetching Market Intelligence..."):
        # Setup holdings
        holdings = {}
        # [Same logic as before to calculate quantity based on initial weights + transactions]
        # ...
        
        tickers_to_track = list(holdings.keys()) + list(BENCHMARKS.values())
        data = yf.download(tickers_to_track, start=view_start, end=view_end, progress=False)['Close'].ffill()
        
        # Portfolio Value TS
        port_ts = pd.Series(0.0, index=data.index)
        for t, q in holdings.items():
            if t in data.columns: port_ts += data[t] * float(q)
        
        # Benchmarks
        bench_df = data[list(BENCHMARKS.values())].copy()
        for col in bench_df.columns:
            bench_df[col] = (bench_df[col] / bench_df[col].iloc[0]) * 100
        
        norm_nav = (port_ts / port_ts.iloc[0]) * 100

    # 3. UI TABS
    tab1, tab2, tab3 = st.tabs(["📈 Performance", "🧠 Insights & News", "📊 Composition"])

    with tab1:
        st.subheader("Benchmark Comparison (Normalized to 100)")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=norm_nav.index, y=norm_nav, name="Your Portfolio", line=dict(width=4, color='#00ff88')))
        for name, sym in BENCHMARKS.items():
            if sym in bench_df.columns:
                fig.add_trace(go.Scatter(x=bench_df.index, y=bench_df[sym], name=name, line=dict(dash='dot')))
        fig.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📢 Corporate Actions")
            for t in holdings.keys():
                if t == "CASH": continue
                ticker_obj = yf.Ticker(t)
                actions = ticker_obj.actions.tail(3)
                if not actions.empty:
                    st.write(f"**{t.replace('.NS','')}**")
                    st.dataframe(actions, use_container_width=True)
        
        with col2:
            st.subheader("📰 Latest Portfolio News")
            for t in list(holdings.keys())[:5]: # Top 5 holdings to save load time
                if t == "CASH": continue
                news = yf.Ticker(t).news
                if news:
                    st.caption(f"Latest for {t}")
                    st.write(f"🔗 [{news[0]['title']}]({news[0]['link']})")
                    st.divider()

    with tab3:
        # Show Sector allocation using yf.Ticker(t).info['sector']
        # ... [Dataframe of holdings with Sector info] ...
        st.download_button("📥 Download Excel Report", data=port_ts.to_csv(), file_name="Moonshot_NAV.csv")
