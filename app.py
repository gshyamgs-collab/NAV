import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
from datetime import datetime, timedelta

# --- CONFIG & CONSTANTS ---
DB_FILE = "moonshot_portfolio.xlsx"
BENCHMARK = "^NSEI"

st.set_page_config(page_title="Moonshot NAV", layout="wide", page_icon="🚀")

# --- DATA PERSISTENCE LOGIC ---
def save_data(df, sheet_name):
    # Ensure directory exists if needed, but here we just manage the file
    mode = 'a' if os.path.exists(DB_FILE) else 'w'
    if mode == 'a':
        with pd.ExcelWriter(DB_FILE, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    else:
        with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

def load_data(sheet_name):
    if not os.path.exists(DB_FILE):
        return None
    try:
        return pd.read_excel(DB_FILE, sheet_name=sheet_name)
    except Exception:
        return None

def format_ticker(t):
    t = t.strip().upper()
    if not t: return ""
    return f"{t}.NS" if not t.endswith('.NS') and not t.startswith('^') else t

def get_price_safely(ticker, start_date):
    """Fetches price on start_date or the closest subsequent date to avoid IndexError."""
    try:
        # Fetch a small window of data starting from the chosen date
        end_search = start_date + timedelta(days=7)
        data = yf.download(ticker, start=start_date, end=end_search, progress=False)
        
        if not data.empty and 'Close' in data.columns:
            return float(data['Close'].iloc[0])
        
        # Absolute fallback: Get the most recent market price
        fallback = yf.download(ticker, period="1d", progress=False)
        return float(fallback['Close'].iloc[-1])
    except Exception:
        return 0.0

@st.cache_data(ttl=3600)
def get_stock_info(tickers):
    info_list = []
    for t in tickers:
        try:
            s = yf.Ticker(t)
            info_list.append({
                "Ticker": t,
                "Sector": s.info.get("sector", "Others"),
                "Industry": s.info.get("industry", "N/A")
            })
        except:
            info_list.append({"Ticker": t, "Sector": "Others", "Industry": "N/A"})
    return pd.DataFrame(info_list)

# --- APP INTERFACE ---
st.title("🚀 Moonshot NAV")

initial_df = load_data("Initial_Setup")
meta_df = load_data("Metadata")

# --- INITIAL SETUP UI ---
if initial_df is None or meta_df is None:
    st.header("🏗️ Initial Portfolio Setup")
    st.info("Set up your 'Day Zero' portfolio. This will be saved to Excel.")
    
    with st.form("setup_form"):
        col1, col2 = st.columns(2)
        total_val = col1.number_input("Total Portfolio Value (₹)", min_value=1.0, value=100000.0)
        cash_val = col2.number_input("Starting Cash Amount (₹)", min_value=0.0, value=10000.0)
        start_date = st.date_input("Investment Start Date", value=datetime(2025, 1, 1))
        
        st.write("### Stocks & Weights")
        c1, c2, c3 = st.columns(3)
        t1 = c1.text_input("Ticker 1", "RELIANCE")
        w1 = c1.slider("Weight 1 (%)", 0, 100, 40, key="w1")
        
        t2 = c2.text_input("Ticker 2", "TCS")
        w2 = c2.slider("Weight 2 (%)", 0, 100, 30, key="w2")
        
        t3 = c3.text_input("Ticker 3", "HDFCBANK")
        w3 = c3.slider("Weight 3 (%)", 0, 100, 30, key="w3")
        
        if st.form_submit_button("Launch Moonshot"):
            if (w1 + w2 + w3) != 100:
                st.error("Weights must sum to 100%!")
            else:
                equity_val = total_val - cash_val
                setup_rows = []
                with st.spinner("Fetching historical baseline prices..."):
                    for t, w in [(t1, w1), (t2, w2), (t3, w3)]:
                        ft = format_ticker(t)
                        price = get_price_safely(ft, start_date)
                        qty = (equity_val * (w/100)) / price if price > 0 else 0
                        setup_rows.append({"Ticker": ft, "Qty": float(qty), "Base_Price": float(price)})
                
                # Save to Excel
                save_data(pd.DataFrame(setup_rows), "Initial_Setup")
                save_data(pd.DataFrame([{"Start_Date": start_date, "Init_Cash": cash_val}]), "Metadata")
                save_data(pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"]), "Transactions")
                st.rerun()

# --- MAIN DASHBOARD ---
else:
    start_date = pd.to_datetime(meta_df['Start_Date'].iloc[0])
    current_cash = float(meta_df['Init_Cash'].iloc[0])
    trans_df = load_data("Transactions")

    # 1. Calculate Current Holdings
    holdings = initial_df.set_index("Ticker")['Qty'].to_dict()
    if trans_df is not None and not trans_df.empty:
        for _, row in trans_df.iterrows():
            if row['Type'] == "Buy":
                holdings[row['Ticker']] = holdings.get(row['Ticker'], 0) + row['Qty']
                current_cash -= row['Amount']
            elif row['Type'] == "Sell":
                holdings[row['Ticker']] = holdings.get(row['Ticker'], 0) - row['Qty']
                current_cash += row['Amount']
            elif row['Type'] == "Cash Deposit":
                current_cash += row['Amount']

    # 2. Sidebar Management
    st.sidebar.header("📝 Ledger Operations")
    with st.sidebar.expander("Add Transaction"):
        ttype = st.selectbox("Action", ["Buy", "Sell", "Cash Deposit"])
        tdate = st.date_input("Date", value=datetime.now())
        if ttype != "Cash Deposit":
            ttick = format_ticker(st.text_input("Ticker"))
            tqty = st.number_input("Quantity", min_value=0.01)
            tamt = st.number_input("Total ₹ Value", min_value=1.0)
        else:
            ttick, tqty = "CASH", 0
            tamt = st.number_input("Deposit Amount", min_value=1.0)
        
        if st.sidebar.button("Execute Trade"):
            new_t = pd.DataFrame([{"Date": tdate, "Type": ttype, "Ticker": ttick, "Qty": tqty, "Amount": tamt}])
            save_data(pd.concat([trans_df, new_t]), "Transactions")
            st.rerun()

    # 3. Processing Market Data
    all_tickers = list(holdings.keys()) + [BENCHMARK]
    with st.spinner("Updating Market Data..."):
        # We fetch from start_date to now
        data = yf.download(all_tickers, start=start_date, progress=False)['Close']
        data = data.ffill().dropna(how='all')

    # Calculate NAV
    port_val = pd.Series(0.0, index=data.index)
    for t, q in holdings.items():
        if t in data.columns:
            port_val += data[t] * q
    
    daily_nav = port_val + current_cash
    norm_nav = (daily_nav / daily_nav.iloc[0]) * 100
    norm_nifty = (data[BENCHMARK] / data[BENCHMARK].iloc[0]) * 100

    # 4. Visualization
    c_main, c_pie = st.columns([2, 1])
    
    with c_main:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=norm_nav.index, y=norm_nav, name="Moonshot NAV", line=dict(color='#00ff88', width=3)))
        fig.add_trace(go.Scatter(x=norm_nifty.index, y=norm_nifty, name="Nifty 50", line=dict(color='#888', width=1, dash='dot')))
        fig.update_layout(template="plotly_dark", title="Portfolio Performance vs Benchmark", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    with c_pie:
        # Sector Allocation
        info = get_stock_info(list(holdings.keys()))
        last_prices = data.iloc[-1]
        sector_map = []
        for t, q in holdings.items():
            val = q * last_prices[t] if t in last_prices else 0
            sec = info[info['Ticker'] == t]['Sector'].values[0] if not info.empty else "Unknown"
            sector_map.append({"Sector": sec, "Value": val})
        
        sdf = pd.DataFrame(sector_map).groupby("Sector").sum().reset_index()
        fig_p = px.pie(sdf, values='Value', names='Sector', hole=0.5, title="Sector Breakdown", template="plotly_dark")
        st.plotly_chart(fig_p, use_container_width=True)

    # 5. Summary Metrics
    st.divider()
    cols = st.columns(4)
    cols[0].metric("Current NAV", f"₹{daily_nav.iloc[-1]:,.0f}")
    cols[1].metric("Net Profit/Loss", f"{((daily_nav.iloc[-1]/daily_nav.iloc[0])-1)*100:.2f}%")
    cols[2].metric("Cash Position", f"₹{current_cash:,.0f}")
    cols[3].metric("Assets", len(holdings))

    if st.sidebar.button("🗑️ Factory Reset App"):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            st.rerun()
