import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
from datetime import datetime

# --- CONFIG & CONSTANTS ---
DB_FILE = "moonshot_portfolio.xlsx"
BENCHMARK = "^NSEI"

st.set_page_config(page_title="Moonshot NAV", layout="wide", page_icon="🚀")

# --- DATA PERSISTENCE LOGIC ---
def save_data(df, sheet_name):
    with pd.ExcelWriter(DB_FILE, engine='openpyxl', mode='a' if os.path.exists(DB_FILE) else 'w') as writer:
        # If sheet exists, overwrite it; otherwise create it
        if sheet_name in writer.book.sheetnames:
            idx = writer.book.sheetnames.index(sheet_name)
            writer.book.remove(writer.book.worksheets[idx])
        df.to_excel(writer, sheet_name=sheet_name, index=False)

def load_data(sheet_name):
    if not os.path.exists(DB_FILE):
        return None
    try:
        return pd.read_excel(DB_FILE, sheet_name=sheet_name)
    except:
        return None

def format_ticker(t):
    t = t.strip().upper()
    return f"{t}.NS" if t and not t.endswith('.NS') and not t.startswith('^') else t

@st.cache_data(ttl=3600)
def get_stock_info(tickers):
    """Fetches Sector and Industry info for the pie chart."""
    info_list = []
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            inf = stock.info
            info_list.append({
                "Ticker": t,
                "Sector": inf.get("sector", "Unknown"),
                "Industry": inf.get("industry", "Unknown")
            })
        except:
            info_list.append({"Ticker": t, "Sector": "Unknown", "Industry": "Unknown"})
    return pd.DataFrame(info_list)

# --- APP INTERFACE ---
st.title("🚀 Moonshot NAV")
st.markdown("Professional Portfolio Management & Sector Analytics")

# Check if initial setup exists
initial_df = load_data("Initial_Setup")
trans_df = load_data("Transactions")

# --- INITIAL SETUP UI (First Time Only) ---
if initial_df is None:
    st.header("🏗️ Initial Portfolio Setup")
    st.info("This is a one-time setup. Provide your starting portfolio weights.")
    
    with st.form("setup_form"):
        col1, col2 = st.columns(2)
        total_val = col1.number_input("Total Portfolio Value (₹)", min_value=1000.0, value=100000.0)
        cash_val = col2.number_input("Initial Cash Balance (₹)", min_value=0.0, value=10000.0)
        start_date = st.date_input("Setup Date", value=datetime(2025, 1, 1))
        
        st.write("Enter Stock Tickers and Weights (must sum to 100% of non-cash value)")
        t1 = st.text_input("Ticker 1", "RELIANCE")
        w1 = st.slider("Weight 1 (%)", 0, 100, 40)
        t2 = st.text_input("Ticker 2", "TCS")
        w2 = st.slider("Weight 2 (%)", 0, 100, 30)
        t3 = st.text_input("Ticker 3", "HDFCBANK")
        w3 = st.slider("Weight 3 (%)", 0, 100, 30)
        
        submitted = st.form_submit_button("Initialize Moonshot NAV")
        
        if submitted:
            # Calculate initial quantities based on weights
            equity_val = total_val - cash_val
            setup_data = []
            for t, w in [(t1, w1), (t2, w2), (t3, w3)]:
                ft = format_ticker(t)
                price = yf.download(ft, start=start_date, end=datetime.now(), progress=False)['Close'].iloc[0]
                qty = (equity_val * (w/100)) / price
                setup_data.append({"Ticker": ft, "Qty": float(qty), "Price": float(price)})
            
            init_df = pd.DataFrame(setup_data)
            save_data(init_df, "Initial_Setup")
            # Save metadata
            meta = pd.DataFrame([{"Date": start_date, "Initial_Cash": cash_val, "Total_Val": total_val}])
            save_data(meta, "Metadata")
            # Create empty transactions sheet
            save_data(pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"]), "Transactions")
            st.rerun()

# --- MAIN DASHBOARD (If Setup Exists) ---
else:
    meta = load_data("Metadata")
    current_cash = meta['Initial_Cash'].iloc[0]
    
    # 1. Update Holdings with Transactions
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

    # 2. Sidebar: Transactions
    st.sidebar.header("🛠️ Manage Trades")
    with st.sidebar.expander("Add New Entry"):
        t_type = st.selectbox("Type", ["Buy", "Sell", "Cash Deposit"])
        t_date = st.date_input("Transaction Date")
        if t_type != "Cash Deposit":
            t_ticker = format_ticker(st.text_input("Ticker"))
            t_qty = st.number_input("Quantity", min_value=0.1)
            t_amt = st.number_input("Total Trade Value (₹)", min_value=1.0)
        else:
            t_ticker = "CASH"
            t_qty = 0
            t_amt = st.number_input("Amount (₹)", min_value=1.0)
            
        if st.button("Submit Transaction"):
            new_row = pd.DataFrame([{"Date": t_date, "Type": t_type, "Ticker": t_ticker, "Qty": t_qty, "Amount": t_amt}])
            updated_trans = pd.concat([trans_df, new_row])
            save_data(updated_trans, "Transactions")
            st.rerun()

    # 3. Market Data & NAV
    all_tickers = list(holdings.keys()) + [BENCHMARK]
    with st.spinner("Fetching market prices..."):
        prices = yf.download(all_tickers, start=meta['Date'].iloc[0], progress=False)['Close']
        prices = prices.ffill()

    # Calculate NAV Series
    portfolio_value = pd.Series(0.0, index=prices.index)
    for ticker, qty in holdings.items():
        if ticker in prices.columns:
            portfolio_value += prices[ticker] * qty
    
    daily_nav = portfolio_value + current_cash
    norm_nav = (daily_nav / daily_nav.iloc[0]) * 100
    norm_nifty = (prices[BENCHMARK] / prices[BENCHMARK].iloc[0]) * 100

    # 4. Charts
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        fig_nav = go.Figure()
        fig_nav.add_trace(go.Scatter(x=norm_nav.index, y=norm_nav, name="Moonshot NAV", line=dict(color='#00ff88', width=3)))
        fig_nav.add_trace(go.Scatter(x=norm_nifty.index, y=norm_nifty, name="Nifty 50", line=dict(color='white', width=1, dash='dot')))
        fig_nav.update_layout(template="plotly_dark", title="Portfolio Growth vs Nifty 50", hovermode="x unified")
        st.plotly_chart(fig_nav, use_container_width=True)

    with col_right:
        # Sector Breakdown
        info_df = get_stock_info(list(holdings.keys()))
        current_prices = prices.iloc[-1]
        sector_data = []
        for ticker, qty in holdings.items():
            val = qty * current_prices[ticker]
            sec = info_df[info_df['Ticker'] == ticker]['Sector'].values[0]
            sector_data.append({"Sector": sec, "Value": val})
        
        sector_df = pd.DataFrame(sector_data).groupby("Sector").sum().reset_index()
        fig_pie = px.pie(sector_df, values='Value', names='Sector', title="Sector Allocation", hole=0.4, template="plotly_dark")
        st.plotly_chart(fig_pie, use_container_width=True)

    # 5. Metrics
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Current NAV", f"₹{daily_nav.iloc[-1]:,.2f}")
    m2.metric("Total Returns", f"{((daily_nav.iloc[-1] / daily_nav.iloc[0]) - 1)*100:.2f}%")
    m3.metric("Available Cash", f"₹{current_cash:,.2f}")
    m4.metric("Holdings Count", len(holdings))

    if st.sidebar.button("Reset All Data (Danger)"):
        os.remove(DB_FILE)
        st.rerun()
