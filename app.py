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

st.set_set_page_config(page_title="Moonshot Intelligence", layout="wide", page_icon="🚀")

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

# --- SESSION STATE ---
if 'locked' not in st.session_state:
    st.session_state['locked'] = False

# --- SIDEBAR ---
st.sidebar.header("🕹️ Controls")
if st.sidebar.button("🔓 Unlock Data Entry"):
    st.session_state['locked'] = False
    st.rerun()

st.title("🚀 Moonshot NAV Intelligence")
init_db, trans_db, meta_db = load_from_excel()

# 1. INPUT MODE (Unlocked)
if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    
    # Metadata & Inputs
    m_df = meta_db if meta_db is not None else pd.DataFrame([{"Date": datetime(2025, 1, 1), "Total_Value": 100000.0, "Cash_Percent": 10.0}])
    i_df = init_db if init_db is not None else pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    t_df = trans_db if trans_db is not None else pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])

    edited_meta = st.data_editor(m_df, key="meta_edit")
    edited_init = st.data_editor(i_df, num_rows="dynamic", key="init_edit")
    edited_trans = st.data_editor(t_df, num_rows="dynamic", key="trans_edit")

    if st.button("🔒 Save & Lock to Analyze"):
        total_w = edited_init["Weight_Percent"].sum() + edited_meta["Cash_Percent"].iloc[0]
        if round(total_w, 2) == 100.0:
            save_to_excel(edited_init, edited_trans, edited_meta)
            st.session_state['locked'] = True
            st.rerun()
        else:
            st.error(f"Total Weight must be 100% (Current: {total_w}%)")
    st.stop()

# --- 2. REPORT MODE (Locked) ---
else:
    # Pre-Initialize to solve NameErrors
    daily_nav = pd.Series()
    all_prices = pd.DataFrame()
    
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0])
    st.sidebar.subheader("📅 Filter View Period")
    start_f = st.sidebar.date_input("From", value=abs_start, min_value=abs_start)
    end_f = st.sidebar.date_input("To", value=datetime.now())

    with st.spinner("Syncing Indian Market Data..."):
        holdings = {}
        total_val = float(meta_db['Total_Value'].iloc[0])
        
        # Calculate Base Quantities
        for _, row in init_db.iterrows():
            t = format_ticker(row['Ticker'])
            w = float(row['Weight_Percent']) / 100
            p_df = yf.download(t, start=abs_start, end=abs_start + timedelta(days=7), progress=False)['Close']
            if not p_df.empty:
                holdings[t] = holdings.get(t, 0.0) + float((total_val * w) / p_df.iloc[0])

        # Adjust for Transactions
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

        # Get Prices for NAV & Benchmarks
        ticker_list = [t for t in holdings.keys() if t != "CASH"]
        all_prices = yf.download(ticker_list + list(BENCHMARKS.values()), start=start_f, end=end_f, progress=False)['Close'].ffill()

        if not all_prices.empty:
            port_ts = pd.Series(0.0, index=all_prices.index)
            for t, q in holdings.items():
                if t in all_prices.columns: port_ts += all_prices[t] * float(q)
            daily_nav = port_ts + current_cash

    # UI TABS
    tab1, tab2, tab3 = st.tabs(["📈 Performance vs Indices", "📊 Sector Composition", "🔔 Insights & News"])

    with tab1:
        st.subheader("NAV Performance")
        norm_nav = (daily_nav / daily_nav.iloc[0]) * 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=norm_nav.index, y=norm_nav, name="Your Portfolio", line=dict(color='#00ff88', width=3)))
        for name, sym in BENCHMARKS.items():
            if sym in all_prices.columns:
                norm_b = (all_prices[sym] / all_prices[sym].iloc[0]) * 100
                fig.add_trace(go.Scatter(x=norm_b.index, y=norm_b, name=name, line=dict(dash='dot')))
        fig.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        curr_total = daily_nav.iloc[-1]
        comp_data = []
        for t, q in holdings.items():
            if float(q) > 0:
                val = float(q) * all_prices[t].iloc[-1]
                # Safe Sector Fetch
                try: sector = yf.Ticker(t).info.get('sector', 'N/A')
                except: sector = "N/A"
                comp_data.append({"Ticker": t, "Value": val, "Weight (%)": (val/curr_total)*100, "Sector": sector})
        
        comp_df = pd.DataFrame(comp_data)
        st.dataframe(comp_df.style.format({"Value": "₹{:,.2f}", "Weight (%)": "{:.2f}%"}), hide_index=True)
        st.download_button("📥 Download Excel Report", data=comp_df.to_csv(index=False).encode('utf-8'), file_name="Moonshot_NAV.csv")

    with tab3:
        # Fixed News/Events logic to prevent KeyError
        st.subheader("Portfolio Market Intelligence")
        for t in ticker_list[:5]:
            tick = yf.Ticker(t)
            news = tick.news
            if news and len(news) > 0:
                st.write(f"**{t.replace('.NS','')}**: 🔗 [{news[0].get('title')}]({news[0].get('link')})")
                st.divider()
