import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
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

# 3. Calculate time window
# Extract date part even if ISO format (T separator) or space separator
scan_date = meta["created_at"][:10]  # Extract YYYY-MM-DD
scan_date_obj = datetime.strptime(scan_date, "%Y-%m-%d").date()
days_elapsed = (date.today() - scan_date_obj).days

# 4. Display scan info
st.caption(
    f"Returns measured from **{scan_date}** ({days_elapsed} days ago) to today "
    f"vs NIFTY 50 benchmark."
)

if days_elapsed < 30:
    st.warning(
        f"⚠️ This scan is only {days_elapsed} days old. "
        "Returns under 30 days are largely noise — accuracy results may not be meaningful yet."
    )

c1, c2, c3, c4 = st.columns(4)
c1.metric("Scan ID", scan_id)
c1.caption(f"Type: {meta['scan_type']}")
c2.metric("Scan Date", scan_date)
c3.metric("Total Scored", int(meta["total_scored"]))
c4.metric("Sectors", len(meta["selected_sectors"]))

st.divider()

# 5. Fetch returns and calculate outperformance
# FIX 1: Cache key uses tuple (lists are not hashable → cache miss every call)
# FIX 2: NIFTY key aligned to what fetch_price_returns actually returns ("^NSEI")
@st.cache_data(ttl=3600)
def get_cached_returns(tickers_tuple: tuple, start_date: str) -> dict:
    return fetch_price_returns(list(tickers_tuple), start_date)

with st.spinner("Fetching historical price data and calculating returns..."):
    tickers = results_df["Ticker"].unique().tolist()
    returns = get_cached_returns(tuple(sorted(tickers)), scan_date)

    # Try both key forms in case fetch_price_returns strips the "^"
    nifty_return = returns.get("^NSEI", returns.get("NSEI", np.nan))

    if np.isnan(nifty_return):
        st.error(
            "Could not fetch NIFTY 50 return data for the selected period. "
            "Check that fetch_price_returns includes '^NSEI' in its ticker list."
        )
        st.stop()

    results_df["Stock Return %"] = results_df["Ticker"].apply(
        lambda x: returns.get(x, np.nan)
    )
    results_df["NIFTY 50 Return %"] = nifty_return
    results_df["Outperformance %"] = results_df["Stock Return %"].apply(
        lambda x: calculate_outperformance(x, nifty_return)
    )

# 6. Display results grouped by recommendation
st.subheader("Performance by Recommendation Tier")

tabs = st.tabs(["Strong Buy", "Buy", "Hold", "Avoid"])
tiers = ["Strong Buy", "Buy", "Hold", "Avoid"]

def color_outperformance(val):
    """Color cell red if negative, green if positive."""
    if pd.isna(val):
        return ""
    color = "red" if val < 0 else "green"
    return f"color: {color}"

for i, tier in enumerate(tiers):
    with tabs[i]:
        tier_df = results_df[results_df["Recommendation"] == tier].copy()

        if tier_df.empty:
            st.info(f"No stocks found in the '{tier}' category for this scan.")
            continue

        # FIX 3: Exclude NaN rows from all summary stats so denominators are correct
        valid_df = tier_df.dropna(subset=["Outperformance %"])
        missing_count = len(tier_df) - len(valid_df)

        avg_out = valid_df["Outperformance %"].mean() if not valid_df.empty else np.nan
        count = len(valid_df)
        outperformed_count = len(valid_df[valid_df["Outperformance %"] > 0])
        outperformed_pct = (outperformed_count / count * 100) if count > 0 else 0

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Avg Outperformance", f"{avg_out:.2f}%" if not np.isnan(avg_out) else "N/A")
        s2.metric("Valid Stock Count", count)
        s3.metric("% Outperformed NIFTY", f"{outperformed_pct:.1f}%")
        s4.metric(
            "Data Unavailable",
            missing_count,
            help="Stocks skipped due to missing price data (delisted, ticker mismatch, etc.)"
        )

        if missing_count > 0:
            missing_tickers = tier_df[tier_df["Outperformance %"].isna()]["Ticker"].tolist()
            with st.expander(f"Show {missing_count} skipped ticker(s)"):
                st.write(", ".join(missing_tickers))

        # Table — FIX 4: styler now actually applied
        display_df = tier_df[[
            "Ticker", "Name", "Score", "Recommendation",
            "Stock Return %", "NIFTY 50 Return %", "Outperformance %"
        ]].sort_values("Outperformance %", ascending=False)

        st.dataframe(
            display_df.style.applymap(color_outperformance, subset=["Outperformance %"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Stock Return %": st.column_config.NumberColumn(format="%.2f%%"),
                "NIFTY 50 Return %": st.column_config.NumberColumn(format="%.2f%%"),
                "Outperformance %": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )

st.divider()
if st.button("Back to History"):
    st.switch_page("pages/History.py")