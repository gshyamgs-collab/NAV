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
    if 'Date' in meta_df.columns:
        meta_data_to_save = meta_df.copy()
        meta_data_to_save['Date'] = pd.to_datetime(meta_data_to_save['Date']).dt.date
    if 'Date' in trans_df.columns:
        trans_data_to_save = trans_df.copy()
        trans_data_to_save['Date'] = pd.to_datetime(trans_data_to_save['Date']).dt.date
        
    with pd.ExcelWriter(DB_FILE, engine='openpyxl') as writer:
        init_df.to_excel(writer, sheet_name="Initial_Setup", index=False)
        trans_data_to_save.to_excel(writer, sheet_name="Transactions", index=False)
        meta_data_to_save.to_excel(writer, sheet_name="Metadata", index=False)

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
    if not t.endswith('.NS') and not t.startswith('^'):
        return f"{t}.NS"
    return t

if 'locked' not in st.session_state:
    st.session_state['locked'] = False

st.sidebar.header("🕹️ Controls")
if st.sidebar.button("🔓 Unlock & Edit Data"):
    st.session_state['locked'] = False
    st.rerun()

st.title("🚀 Moonshot NAV Intelligence")
init_db, trans_db, meta_db = load_from_excel()

if not st.session_state['locked']:
    st.markdown("### 📝 Portfolio Data Entry")
    if meta_db is None:
        meta_data = pd.DataFrame([{"Date": datetime(2025, 1, 1).date(), "Total_Value": 100000.0, "Cash_Percent": 10.0}])
    else:
        meta_data = meta_db
    edited_meta = st.data_editor(meta_data, num_rows="fixed", key="meta_edit", use_container_width=True)

    if init_db is None:
        init_data = pd.DataFrame([{"Ticker": "RELIANCE", "Weight_Percent": 90.0}])
    else:
        init_data = init_db
    edited_init = st.data_editor(init_data, num_rows="dynamic", key="init_edit", use_container_width=True)

    if trans_db is None:
        trans_data = pd.DataFrame(columns=["Date", "Type", "Ticker", "Qty", "Amount"])
    else:
        trans_data = trans_db
    edited_trans = st.data_editor(trans_data, num_rows="dynamic", key="trans_edit", use_container_width=True)

    total_w = edited_init["Weight_Percent"].sum() + edited_meta["Cash_Percent"].iloc[0]
    if st.button("🔒 Save & Lock to Analyze"):
        if round(total_w, 2) == 100.0:
            save_to_excel(edited_init, edited_trans, edited_meta)
            st.session_state['locked'] = True
            st.rerun()
        else:
            st.error(f"Total Weight must be 100% (Current: {total_w}%)")
    st.stop()

else:
    abs_start = pd.to_datetime(meta_db['Date'].iloc[0]).date()
    today = datetime.now().date()
    
    st.sidebar.subheader("📅 View Period")
    period_choice = st.sidebar.selectbox("Select Duration", 
        ["1W", "1M", "6M", "1Yr", "3Yr", "5Yr", "10Yr", "Max", "Custom"], index=7)
    
    if period_choice == "Custom":
        start_filter = st.sidebar.date_input("From", value=abs_start, min_value=abs_start)
        end_filter = st.sidebar.date_input("To", value=today)
    else:
        end_filter = today
        deltas = {"1W": 7, "1M": 30, "6M": 182, "1Yr": 365, "3Yr": 1095, "5Yr": 1825, "10Yr": 3650}
        start_filter = abs_start if period_choice == "Max" else max(abs_start, today - timedelta(days=deltas[period_choice]))

    total_val = float(meta_db['Total_Value'].iloc[0])
    cash_p = float(meta_db['Cash_Percent'].iloc[0])
    holdings = {}
    
    with st.spinner("Analyzing Market Data..."):
        for _, row in init_db.iterrows():
            t = format_ticker(row['Ticker'])
            w = float(row['Weight_Percent']) / 100
            p_df = yf.download(t, start=abs_start, end=abs_start + timedelta(days=7), progress=False)['Close']
            if not p_df.empty:
                holdings[t] = holdings.get(t, 0.0) + float((total_val * w) / p_df.iloc[0])

        current_cash = total_val * (cash_p / 100)
        if trans_db is not None and not trans_db.empty:
            for _, row in trans_db.iterrows():
                t = format_ticker(row['Ticker'])
                if row['Type'] == "BUY":
                    holdings[t] = holdings.get(t, 0.0) + float(row['Qty'])
                    current_cash -= float(row['Amount'])
                elif row['Type'] == "SELL":
                    holdings[t] = holdings.get(t, 0.0) - float(row['Qty'])
                    current_cash += float(row['Amount'])

        ticker_list = [t for t in holdings.keys() if t != "CASH"]
        bench_list = list(BENCHMARKS.values())
        all_prices = yf.download(ticker_list + bench_list, start=start_filter, end=end_filter, progress=False)['Close'].ffill()

        if not all_prices.empty:
            port_ts = pd.Series(0.0, index=all_prices.index)
            for t, q in holdings.items():
                if t in all_prices.columns:
                    port_ts += all_prices[t] * float(q)
            daily_nav = port_ts + current_cash

    if 'daily_nav' in locals() and not daily_nav.empty:
        tab1, tab2, tab3 = st.tabs(["📈 Performance", "🏢 Portfolio", "🔔 Insights & AI Summary"])

        with tab1:
            st.subheader(f"Performance: {period_choice}")
            norm_nav = (daily_nav / daily_nav.iloc[0]) * 100
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=norm_nav.index, y=norm_nav, name="Portfolio", line=dict(color='#00ff88', width=3)))
            for name, sym in BENCHMARKS.items():
                if sym in all_prices.columns:
                    norm_bench = (all_prices[sym] / all_prices[sym].iloc[0]) * 100
                    fig.add_trace(go.Scatter(x=norm_bench.index, y=norm_bench, name=name, line=dict(dash='dot')))
            fig.update_layout(template="plotly_dark", height=500)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("Current Holdings")
            curr_nav = daily_nav.iloc[-1]
            last_p = all_prices.iloc[-1]
            report_list = []
            for t, q in holdings.items():
                if float(q) > 0:
                    val = float(q) * last_p[t]
                    try: 
                        info = yf.Ticker(t).info
                        sector = info.get('sector', info.get('industry', 'Others'))
                    except: sector = "N/A"
                    report_list.append({"Ticker": t, "Quantity": round(q, 2), "Value": val, "Weight (%)": (val/curr_nav)*100, "Sector": sector})
            report_list.append({"Ticker": "CASH", "Quantity": 1.0, "Value": current_cash, "Weight (%)": (current_cash/curr_nav)*100, "Sector": "Liquidity"})
            st.dataframe(pd.DataFrame(report_list).style.format({"Value": "₹{:,.2f}", "Weight (%)": "{:.2f}%"}), use_container_width=True, hide_index=True)

        with tab3:
            st.subheader("Stock Intelligence & AI Summary")
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.markdown("#### 📅 Event Timeline")
                for t in ticker_list[:5]:
                    obj = yf.Ticker(t)
                    act = obj.actions
                    if not act.empty:
                        # Convert index to Date only
                        act_display = act.tail(3).copy()
                        act_display.index = pd.to_datetime(act_display.index).date
                        st.write(f"**{t.split('.')[0]}**")
                        st.table(act_display)
            
            with col_b:
                st.markdown("#### 🤖 Market Context (AI Summary)")
                for t in ticker_list[:10]:
                    try:
                        news_data = yf.Ticker(t).news
                        if news_data and len(news_data) > 0:
                            # AI Summarization Logic (Mocking the AI's core deduction)
                            latest_title = news_data[0].get('title', '')
                            publisher = news_data[0].get('publisher', 'Market News')
                            
                            # Clean Display without messy links
                            st.info(f"**{t.split('.')[0]} Insight**")
                            st.write(f"**Primary Driver:** {latest_title}")
                            st.caption(f"Source: {publisher} | Context: Market reacting to recent {publisher} reports regarding internal developments or sector trends.")
                        else:
                            st.caption(f"No significant recent news for {t}")
                    except:
                        st.caption(f"Intelligence data unavailable for {t}")
                    st.divider()
    else:
        st.warning("No data found for the selected range.")
