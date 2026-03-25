import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import yfinance as yf
from datetime import datetime, timedelta

# --- CONFIG ---
DB_FILE = "moonshot_portfolio.xlsx"
BENCHMARKS = {
    "Nifty 50": "^NSEI",
    "Nifty Midcap 100": "^NSEMDCP100"
}

st.set_page_config(page_title="Moonshot NAV Intelligence", layout="wide", page_icon="🚀")

# --- CORE UTILITIES ---
def clean_ticker(t):
    if not t or pd.isna(t): return ""
    t = str(t).strip().upper()
    if ":" in t: t = t.split(":")[-1]
    if not t.endswith(".NS") and not t.startswith("^"): t = f"{t}.NS"
    return t

def get_live_price(ticker):
    """Fast fetch for current price"""
    try:
        t_obj = yf.Ticker(clean_ticker(ticker))
        return t_obj.fast_info['last_price']
    except:
        return None

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

# --- APP START ---
st.title("🚀 Moonshot NAV Intelligence")
init_db, trans_db, meta_db = load_from_excel()

if 'locked' not in st.session_state:
    st.session_state['locked'] = False

# --- SIDEBAR UI ---
with st.sidebar:
    st.header("🔍 Ticker Search")
    search_q = st.text_input("Search (e.g. RELIANCE, TCS)", "").upper()
    if search_q:
        lp = get_live_price(search_q)
        if lp:
            st.success(f"**{search_q}**: ₹{lp:,.2f}")
            st.caption("Valid Ticker for Entry")
        else:
            st.error("Invalid Ticker")
    
    st.divider()
    if st.button("🔓 Unlock & Edit Portfolio", use_container_width=True):
        st.session_state['locked'] = False
        st.rerun()

# --- ENTRY MODE ---
if not st.session_state['locked']:
    st.info("💡 Tip: Use simple names like RELIANCE or HDFCBANK. The app adds .NS automatically.")
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("1. Global Settings")
        m_df = meta_db if meta_db is not None else pd.DataFrame([{"Date": "2024-01-01", "Total_Value": 1000000.0, "Cash_Percent": 10.0}])
        edited_meta = st.data_editor(m_df, key="meta_edit")
    
    st.subheader("2. Initial Weights")
    i_df = init_db if init_db is not None else pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    edited_init = st.data_editor(i_df, num_rows="dynamic", key="init_edit", use_container_width=True)
    
    st.subheader("3. Transaction Ledger")
    t_df = trans_db if trans_db is not None else pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    edited_trans = st.data_editor(t_df, num_rows="dynamic", key="trans_edit", use_container_width=True)

    if st.button("🔒 Save & Generate Analysis", type="primary"):
        save_to_excel(edited_init, edited_trans, edited_meta)
        st.session_state['locked'] = True
        st.rerun()
    st.stop()

# --- ANALYTICS MODE ---
else:
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0])
    
    with st.spinner("Crunching Portfolio Data..."):
        holdings_qty = {}
        total_initial = float(meta_db['Total_Value'].iloc[0])
        cash_initial = total_initial * (float(meta_db['Cash_Percent'].iloc[0])/100)
        
        # Step 1: Initial Quantities
        for _, row in init_db.iterrows():
            tk = clean_ticker(row['Ticker'])
            weight_val = (total_initial * (float(row['Weight_Percent'])/100))
            hist = yf.download(tk, start=abs_start, end=abs_start + timedelta(days=7), progress=False)
            if not hist.empty:
                holdings_qty[tk] = weight_val / float(hist['Close'].iloc[0])

        # Step 2: Transaction Adjustments
        current_cash = cash_initial
        if trans_db is not None and not trans_db.empty:
            for _, row in trans_db.iterrows():
                tk = clean_ticker(row['Ticker'])
                qty = float(row['Qty'])
                amt = float(row['Amount'])
                if row['Type'] == "BUY":
                    holdings_qty[tk] = holdings_qty.get(tk, 0) + qty
                    current_cash -= amt
                else:
                    holdings_qty[tk] = holdings_qty.get(tk, 0) - qty
                    current_cash += amt

        # Step 3: Global History
        all_tk = list(holdings_qty.keys()) + list(BENCHMARKS.values())
        df_hist = yf.download(all_tk, start=abs_start, progress=False)['Close'].ffill()

    # --- UI DASHBOARD ---
    t1, t2 = st.tabs(["📈 Performance Hub", "🏢 Portfolio Holdings"])

    with t1:
        st.write("### NAV Performance vs Benchmarks")
        p_map = {"1W": 7, "1M": 30, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825, "Max": None}
        p_sel = st.radio("Timeframe", list(p_map.keys()), horizontal=True)
        
        # Date Filtering
        if p_map[p_sel]:
            start_f = datetime.now() - timedelta(days=p_map[p_sel])
            plot_df = df_hist[df_hist.index >= start_f]
        else:
            plot_df = df_hist

        if not plot_df.empty:
            # Portfolio NAV Calculation
            port_val = pd.Series(0.0, index=plot_df.index)
            for tk, q in holdings_qty.items():
                if tk in plot_df.columns: port_val += plot_df[tk] * q
            
            daily_nav = port_val + current_cash
            
            # Metric Bar
            m1, m2, m3 = st.columns(3)
            curr_v = daily_nav.iloc[-1]
            period_ret = ((curr_v / daily_nav.iloc[0]) - 1) * 100
            m1.metric("Current NAV", f"₹{curr_v:,.2f}")
            m2.metric(f"{p_sel} Return", f"{period_ret:.2f}%")
            
            # Performance Chart
            fig = go.Figure()
            # Normalize to 100 at start of period
            fig.add_trace(go.Scatter(x=daily_nav.index, y=(daily_nav/daily_nav.iloc[0])*100, 
                                     name="Portfolio", line=dict(color='#00ff88', width=4)))
            
            for b_name, b_sym in BENCHMARKS.items():
                if b_sym in plot_df.columns:
                    b_series = plot_df[b_sym]
                    fig.add_trace(go.Scatter(x=b_series.index, y=(b_series/b_series.iloc[0])*100, 
                                             name=b_name, line=dict(dash='dot', width=1.5)))

            fig.update_layout(template="plotly_dark", height=550, hovermode="x unified",
                              yaxis_title="Indexed Value (Start = 100)")
            st.plotly_chart(fig, use_container_width=True)

    with t2:
        st.subheader("Asset Allocation")
        h_data = []
        # Add Stocks
        for tk, q in holdings_qty.items():
            if q > 0:
                px = float(df_hist[tk].iloc[-1])
                val = q * px
                h_data.append({
                    "Asset": tk.replace(".NS", ""),
                    "Category": "Equity",
                    "Quantity": round(q, 2),
                    "Price": f"₹{px:,.2f}",
                    "Value": round(val, 2),
                    "Weight": round((val / curr_v) * 100, 2)
                })
        
        # Add Cash explicitly
        h_data.append({
            "Asset": "CASH",
            "Category": "Cash",
            "Quantity": 1.0,
            "Price": f"₹{current_cash:,.2f}",
            "Value": round(current_cash, 2),
            "Weight": round((current_cash / curr_v) * 100, 2)
        })
        
        h_df = pd.DataFrame(h_data).sort_values("Value", ascending=False)
        st.dataframe(h_df.style.format({"Value": "₹{:,.2f}", "Weight": "{:.2f}%"}), 
                     use_container_width=True, hide_index=True)
        
        # Allocation Chart
        fig_pie = go.Figure(data=[go.Pie(labels=h_df['Asset'], values=h_df['Value'], hole=.4)])
        fig_pie.update_layout(template="plotly_dark", title="Portfolio Concentration")
        st.plotly_chart(fig_pie)
