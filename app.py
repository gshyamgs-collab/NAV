import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Portfolio Command Center", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>button{border-radius: 8px;} .stMetric{background-color: #1e2130; padding: 15px; border-radius: 10px;}</style>", unsafe_allow_html=True)

st.title("🏛️ Sovereign Fund Command Center")
st.subheader("Fundamental Equity Analysis & Unitized NAV Tracker")

# --- DATA INPUT SECTION ---
with st.sidebar:
    st.header("⚙️ Data Source")
    data_mode = st.radio("Choose Input Mode:", ["Upload Excel/CSV", "Google Sheet URL"])
    
    if data_mode == "Upload Excel/CSV":
        uploaded_file = st.file_uploader("Upload Transaction Log", type=["xlsx", "csv"])
    else:
        sheet_url = st.text_input("Paste Public Google Sheet URL:")
        # Convert sharing link to export link
        if "edit" in sheet_url:
            uploaded_file = sheet_url.replace('/edit#gid=', '/export?format=csv&gid=')
        else:
            uploaded_file = None

# --- THE ENGINE: CALCULATION LOGIC ---
@st.cache_data(ttl=3600)
def process_performance(file):
    if file is None: return None
    
    # 1. Load Data
    df = pd.read_csv(file) if isinstance(file, str) else pd.read_excel(file)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date')
    
    # 2. Market Data
    tickers = [f"{t}.NS" for t in df['Ticker'].dropna().unique()]
    benchmarks = ["^NSEI", "^NSEMDCP100"]
    all_data = yf.download(tickers + benchmarks, start=df['Date'].min(), end=datetime.now())['Adj Close'].ffill()
    
    # 3. NAV Unitization Logic
    date_range = pd.date_range(df['Date'].min(), datetime.now(), freq='B')
    history = pd.DataFrame(index=date_range, columns=['NAV', 'Nifty50', 'Midcap100'])
    
    units, cash, base_nav = 0, 0, 100.0
    current_holdings = {t: 0 for t in df['Ticker'].unique() if str(t) != 'nan'}

    for today in date_range:
        if today not in all_data.index: continue
        
        # Process Transactions
        day_trans = df[df['Date'].dt.date == today.date()]
        day_cashflow = 0
        
        for _, row in day_trans.iterrows():
            if row['Type'] == 'DEPOSIT': 
                day_cashflow += row['Amount']
                cash += row['Amount']
            elif row['Type'] == 'BUY':
                cash -= (row['Quantity'] * row['Price'])
                current_holdings[row['Ticker']] += row['Quantity']
            elif row['Type'] == 'SELL':
                cash += (row['Quantity'] * row['Price'])
                current_holdings[row['Ticker']] -= row['Quantity']

        # Value Equity
        equity_val = sum(current_holdings[t] * all_data.loc[today, f"{t}.NS"] for t in current_holdings if current_holdings[t] > 0)
        total_value = equity_val + cash
        
        # Unitize
        if units == 0 and day_cashflow > 0:
            units = day_cashflow / base_nav
        elif units > 0 and day_cashflow != 0:
            prev_nav = history.iloc[history.index.get_loc(today)-1]['NAV']
            units += (day_cashflow / prev_nav)
            
        cur_nav = total_value / units if units > 0 else base_nav
        
        # Rebase Benchmarks
        nifty = (all_data.loc[today, "^NSEI"] / all_data.iloc[0]["^NSEI"]) * 100
        midcap = (all_data.loc[today, "^NSEMDCP100"] / all_data.iloc[0]["^NSEMDCP100"]) * 100
        
        history.loc[today] = [cur_nav, nifty, midcap]
        
    return history.ffill()

# --- UI DISPLAY ---
if uploaded_file:
    data = process_performance(uploaded_file)
    if data is not None:
        # Metrics
        latest = data.iloc[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric("Current NAV", f"₹{latest['NAV']:.2f}")
        c2.metric("vs Nifty 50", f"{(latest['NAV']/latest['Nifty50'] - 1)*100:.1f}% Alpha")
        c3.metric("vs Midcap 100", f"{(latest['NAV']/latest['Midcap100'] - 1)*100:.1f}% Alpha")
        
        # Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data.index, y=data['NAV'], name="Portfolio", line=dict(color='#00ffcc', width=3)))
        fig.add_trace(go.Scatter(x=data.index, y=data['Nifty50'], name="Nifty 50", line=dict(color='white', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=data.index, y=data['Midcap_100'], name="Midcap 100", line=dict(color='#ff9900', width=1, dash='dash')))
        fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("👋 Welcome, Fund Manager. Please upload your transaction file or link your Google Sheet in the sidebar to begin.")
