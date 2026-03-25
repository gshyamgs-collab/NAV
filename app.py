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
    "Nifty Midcap 150": "^NSEMDCP150"
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
        return init, trans, meta
    except: return None, None, None

def format_ticker(t):
    if not t or pd.isna(t): return ""
    t = str(t).strip().upper()
    return f"{t}.NS" if not t.endswith('.NS') and not t.startswith('^') else t

# --- APP START ---
st.title("🚀 Moonshot NAV Intelligence")
init_db, trans_db, meta_db = load_from_excel()

if 'locked' not in st.session_state:
    st.session_state['locked'] = False

if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    # Data editors for Meta, Initial, and Transactions
    m_df = meta_db if meta_db is not None else pd.DataFrame([{"Date": "2025-01-01", "Total_Value": 100000.0, "Cash_Percent": 10.0}])
    edited_meta = st.data_editor(m_df, key="meta_edit")
    i_df = init_db if init_db is not None else pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    edited_init = st.data_editor(i_df, num_rows="dynamic", key="init_edit")
    t_df = trans_db if trans_db is not None else pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    edited_trans = st.data_editor(t_df, num_rows="dynamic", key="trans_edit")

    if st.button("🔒 Save & Analyze"):
        save_to_excel(edited_init, edited_trans, edited_meta)
        st.session_state['locked'] = True
        st.rerun()
    st.stop()

else:
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0])
    
    with st.spinner("Fetching Market Data..."):
        holdings = {}
        total_val = float(meta_db['Total_Value'].iloc[0])
        # Initial Portfolio Setup
        for _, row in init_db.iterrows():
            t = format_ticker(row['Ticker'])
            w = float(row['Weight_Percent']) / 100
            px = yf.download(t, start=abs_start, end=abs_start + timedelta(days=7), progress=False)['Close']
            if not px.empty: holdings[t] = (total_val * w) / px.iloc[0]

        current_cash = total_val * (float(meta_db['Cash_Percent'].iloc[0]) / 100)
        ticker_list = list(holdings.keys())
        all_data = yf.download(ticker_list + list(BENCHMARKS.values()), start=abs_start, progress=False)['Close'].ffill()

    # --- TABBED PERIOD SELECTOR ---
    st.write("### Performance Analysis")
    p_tabs = st.tabs(["1W", "1M", "6M", "1Yr", "3Yr", "Max"])
    periods = {"1W": 7, "1M": 30, "6M": 182, "1Yr": 365, "3Yr": 1095, "Max": None}
    
    for i, tab in enumerate(p_tabs):
        with tab:
            period_name = list(periods.keys())[i]
            days = periods[period_name]
            
            start_date = abs_start if days is None else max(abs_start, pd.Timestamp.now() - timedelta(days=days))
            plot_df = all_data[all_data.index >= start_date].copy()
            
            if not plot_df.empty:
                # Portfolio NAV Calculation
                port_nav = pd.Series(0.0, index=plot_df.index)
                for t, qty in holdings.items():
                    if t in plot_df.columns: port_nav += plot_df[t] * float(qty)
                port_nav += current_cash
                
                # Normalization for Comparison (%)
                norm_port = (port_nav / port_nav.iloc[0]) * 100
                
                fig = go.Figure()
                # Portfolio Trace
                fig.add_trace(go.Scatter(
                    x=norm_port.index, y=norm_port, 
                    name="Portfolio", 
                    line=dict(color='#00ff88', width=3),
                    hovertemplate='NAV: %{y:.2f}%<extra></extra>'
                ))
                
                # Benchmark Traces
                for name, ticker in BENCHMARKS.items():
                    if ticker in plot_df.columns:
                        bench_norm = (plot_df[ticker] / plot_df[ticker].iloc[0]) * 100
                        fig.add_trace(go.Scatter(
                            x=bench_norm.index, y=bench_norm, 
                            name=name, 
                            line=dict(dash='dot'),
                            hovertemplate=f'{name}: %{{y:.2f}}%<extra></extra>'
                        ))

                fig.update_layout(
                    hovermode="x unified",  # SHOWS ALL VALUES AT CURSOR
                    template="plotly_dark",
                    height=500,
                    xaxis_title="Date",
                    yaxis_title="Relative Performance (%)",
                    margin=dict(l=0, r=0, t=30, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True)

    # PORTFOLIO COMPOSITION (CASH INCLUDED)
    st.divider()
    st.subheader("🏢 Portfolio Composition")
    curr_prices = all_data.iloc[-1]
    comp = []
    total_mkt_val = 0
    for t, q in holdings.items():
        val = q * curr_prices[t]
        total_mkt_val += val
        comp.append({"Asset": t, "Value": val})
    
    comp.append({"Asset": "CASH", "Value": current_cash})
    final_total = total_mkt_val + current_cash
    
    comp_df = pd.DataFrame(comp)
    comp_df["Weight (%)"] = (comp_df["Value"] / final_total) * 100
    st.dataframe(comp_df.style.format({"Value": "₹{:,.2f}", "Weight (%)": "{:.2f}%"}), use_container_width=True)
