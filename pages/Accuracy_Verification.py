import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from core.scan_history import get_scan_run, load_scan_results
from core.screener import fetch_price_returns, calculate_outperformance

st.set_page_config(
    page_title="BAC SMA - Accuracy Verification",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
[data-testid="stSidebarNav"] {
    display: none;
}
</style>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.title("BAC SMA")
    st.caption("Accuracy Verification")
    st.page_link("app.py", label="Screener")
    st.page_link("pages/History.py", label="History")
    st.page_link("pages/Screening_Logic.py", label="Screening Logic")

st.title("Stock Accuracy Verification")
st.caption("Compare predicted returns against actual NIFTY 50 performance since the scan date.")

# 1. Receive scan_id from session state
if "accuracy_scan_id" not in st.session_state:
    st.warning("No scan selected for verification. Please go to the History page.")
    if st.button("Go to History"):
        st.switch_page("pages/History.py")
    st.stop()

scan_id = st.session_state.accuracy_scan_id

# 2. Load scan metadata and results
meta = get_scan_run(scan_id)
results_df = load_scan_results(scan_id)

if not meta or results_df.empty:
    st.error(f"Could not load results for scan ID: {scan_id}")
    st.stop()

# 3. Display scan info
c1, c2, c3, c4 = st.columns(4)
c1.metric("Scan ID", scan_id)
c1.caption(f"Type: {meta['scan_type']}")
c2.metric("Scan Date", meta["created_at"].split()[0])
c3.metric("Total Scored", int(meta["total_scored"]))
c4.metric("Sectors", len(meta["selected_sectors"]))

st.divider()

# 4. Fetch returns and calculate outperformance
scan_date = meta["created_at"].split()[0] # YYYY-MM-DD

@st.cache_data(ttl=3600)
def get_cached_returns(tickers, start_date):
    return fetch_price_returns(tickers, start_date)

with st.spinner("Fetching historical price data and calculating returns..."):
    tickers = results_df["Ticker"].unique().tolist()
    returns = get_cached_returns(tickers, scan_date)
    
    nifty_return = returns.get("NIFTY50", np.nan)
    
    if np.isnan(nifty_return):
        st.error("Could not fetch NIFTY 50 return data for the selected period.")
        st.stop()

    results_df["Stock Return %"] = results_df["Ticker"].apply(lambda x: returns.get(x, np.nan))
    results_df["NIFTY 50 Return %"] = nifty_return
    results_df["Outperformance %"] = results_df["Stock Return %"].apply(lambda x: calculate_outperformance(x, nifty_return))

# 5. Display results grouped by recommendation
st.subheader("Performance by Recommendation Tier")

tabs = st.tabs(["Strong Buy", "Buy", "Hold", "Avoid"])
tiers = ["Strong Buy", "Buy", "Hold", "Avoid"]

for i, tier in enumerate(tiers):
    with tabs[i]:
        tier_df = results_df[results_df["Recommendation"] == tier].copy()
        
        if tier_df.empty:
            st.info(f"No stocks found in the '{tier}' category for this scan.")
            continue
            
        # Summary stats
        avg_out = tier_df["Outperformance %"].mean()
        count = len(tier_df)
        outperformed_count = len(tier_df[tier_df["Outperformance %"] > 0])
        outperformed_pct = (outperformed_count / count * 100) if count > 0 else 0
        
        s1, s2, s3 = st.columns(3)
        s1.metric("Avg Outperformance", f"{avg_out:.2f}%")
        s2.metric("Stock Count", count)
        s3.metric("% Outperformed NIFTY", f"{outperformed_pct:.1f}%")
        
        # Table
        display_df = tier_df[[
            "Ticker", "Name", "Score", "Recommendation", 
            "Stock Return %", "NIFTY 50 Return %", "Outperformance %"
        ]].sort_values("Outperformance %", ascending=False)
        
        def color_outperformance(val):
            color = 'red' if val < 0 else 'green'
            return f'color: {color}'

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Stock Return %": st.column_config.NumberColumn(format="%.2f%%"),
                "NIFTY 50 Return %": st.column_config.NumberColumn(format="%.2f%%"),
                "Outperformance %": st.column_config.NumberColumn(format="%.2f%%"),
            }
        )

if st.button("Back to History"):
    st.switch_page("pages/History.py")
