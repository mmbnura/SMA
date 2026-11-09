from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from core.scan_history import get_scan_run, init_db, list_scan_runs, load_scan_results
from core.screener import NIFTY50, RECOMMENDATION_ORDER, fetch_close_prices, period_return, reference_close_date
from core.timeutil import IST, now_ist, parse_timestamp
from screens.components import csv_bytes, is_missing, normalize_results, page_setup, sidebar_disclaimer, styled

page_setup("Accuracy Verification", "Accuracy verification")
init_db()
sidebar_disclaimer()

st.title("Accuracy Verification")
st.caption("How did each recommendation tier perform against the NIFTY 50 since the scan?")

history = list_scan_runs(limit=500)
if history.empty:
    st.info("No scans yet. Run a scan from the Screener page first.")
    st.stop()

ids = history["scan_id"].tolist()
created = dict(zip(history["scan_id"], history["created_at"]))
default = st.session_state.get("accuracy_scan_id")
scan_id = st.selectbox(
    "Scan",
    ids,
    index=ids.index(default) if default in ids else 0,
    format_func=lambda i: f"{i}  ·  {str(created[i]).replace('T', ' ')[:16]}",
)
st.session_state.accuracy_scan_id = scan_id

meta = get_scan_run(scan_id)
results = normalize_results(load_scan_results(scan_id))
if not meta or (results.empty and meta["disqualified"].empty):
    st.error(f"No stored results for scan {scan_id}.")
    st.stop()

scan_ts = parse_timestamp(meta["created_at"])
rows = results[["Ticker", "Name", "Sector", "Score", "Recommendation", "Data As Of"]].copy()
dq = meta["disqualified"]
if not dq.empty:
    dq_rows = dq.reindex(columns=["Ticker", "Name", "Sector", "Data As Of"]).copy()
    dq_rows["Score"] = np.nan
    dq_rows["Recommendation"] = "Disqualified"
    rows = pd.concat([rows, dq_rows], ignore_index=True)


def ref_date(as_of) -> date:
    ts = parse_timestamp(str(as_of).replace(" IST", "")) if isinstance(as_of, str) else None
    return reference_close_date(ts or scan_ts)


rows["Reference Date"] = rows["Data As Of"].map(ref_date)
uses_scan_time = rows["Data As Of"].isna() | (rows["Data As Of"] == "Not available")

days_elapsed = (now_ist().date() - scan_ts.astimezone(IST).date()).days
if days_elapsed < 30:
    st.warning(
        f"This scan is {days_elapsed} day(s) old. Returns over less than about 30 days are mostly noise, "
        "so treat these results as preliminary."
    )


@st.cache_data(ttl=3600, show_spinner=False)
def get_closes(tickers: tuple[str, ...], start: str) -> pd.DataFrame:
    return fetch_close_prices(list(tickers), pd.Timestamp(start).date())


start = min(rows["Reference Date"]) - timedelta(days=10)
with st.spinner("Downloading price history from Yahoo Finance..."):
    try:
        closes = get_closes(
            tuple(sorted({f"{t}.NS" for t in rows["Ticker"]} | {NIFTY50})), start.isoformat()
        )
    except Exception as err:
        st.error(f"Could not download price history from Yahoo Finance: {err}")
        st.stop()

if closes.empty or NIFTY50 not in closes.columns or closes[NIFTY50].dropna().empty:
    st.error("NIFTY 50 price history is not available from Yahoo Finance right now, so returns cannot be compared.")
    st.stop()

records = []
nifty_cache: dict = {}
for _, r in rows.iterrows():
    ref = r["Reference Date"]
    if ref not in nifty_cache:
        nifty_cache[ref] = period_return(closes[NIFTY50], ref)
    nifty = nifty_cache[ref]
    col = f"{r['Ticker']}.NS"
    stock = period_return(closes[col], ref) if col in closes.columns else None

    note = ""
    stock_ret = nifty_ret = out = None
    start_d = end_d = start_px = end_px = None
    if stock is None:
        note = "Price data not available from Yahoo Finance"
    elif nifty is None:
        note = "NIFTY 50 data not available for this start date"
    elif stock["end_date"] <= stock["start_date"]:
        note = "No trading session since the reference close yet"
        start_d, end_d = stock["start_date"], stock["end_date"]
    else:
        start_d, end_d = stock["start_date"], stock["end_date"]
        start_px, end_px = stock["start_price"], stock["end_price"]
        stock_ret, nifty_ret = stock["return_pct"], nifty["return_pct"]
        out = stock_ret - nifty_ret
        if nifty["start_date"] != stock["start_date"]:
            note = f"Stock's last close before the scan was {stock['start_date']}; NIFTY 50 measured from {nifty['start_date']}"
        if stock["end_date"] != nifty["end_date"]:
            note = (note + "; " if note else "") + f"stock's latest close is {stock['end_date']}"
    records.append({
        "Ticker": r["Ticker"], "Name": r["Name"], "Score": r["Score"], "Recommendation": r["Recommendation"],
        "Start Date": start_d, "Start Price (₹)": start_px, "End Date": end_d, "End Price (₹)": end_px,
        "Stock Return %": stock_ret, "NIFTY 50 Return %": nifty_ret, "Outperformance %": out, "Note": note,
    })
perf = pd.DataFrame(records)

end_dates = perf["End Date"].dropna()
latest = max(end_dates) if not end_dates.empty else None
st.caption(
    f"Scan created {scan_ts:%d %b %Y %H:%M} IST · returns measured up to the close of "
    f"{latest:%d %b %Y}" if latest else "No price data available yet."
)
with st.expander("Method"):
    st.markdown(
        "- **Start:** the last official NSE close that was available when each stock's fundamentals were "
        "downloaded (if downloaded before 15:30 IST, the previous session's close).\n"
        "- **End:** the latest daily close available from Yahoo Finance.\n"
        "- **Price returns only:** dividends are excluded for stocks and the NIFTY 50 (a price index), so the "
        "comparison is like-for-like. Prices are split-adjusted.\n"
        "- Stocks without price data are counted separately and excluded from averages."
        + ("\n- This scan predates per-stock download times, so the scan time is used as the start for all stocks."
           if uses_scan_time.all() else "")
    )

tiers = [t for t in RECOMMENDATION_ORDER + ["Disqualified"] if (perf["Recommendation"] == t).any()]

summary = []
for tier in tiers:
    t = perf[perf["Recommendation"] == tier]
    valid = t.dropna(subset=["Outperformance %"])
    summary.append({
        "Tier": tier,
        "Stocks": len(t),
        "With price data": len(valid),
        "Avg Stock Return %": valid["Stock Return %"].mean() if len(valid) else None,
        "Avg NIFTY 50 Return %": valid["NIFTY 50 Return %"].mean() if len(valid) else None,
        "Avg Outperformance %": valid["Outperformance %"].mean() if len(valid) else None,
        "Median Outperformance %": valid["Outperformance %"].median() if len(valid) else None,
        "Beat NIFTY 50 %": (valid["Outperformance %"] > 0).mean() * 100 if len(valid) else None,
    })
summary_df = pd.DataFrame(summary)

st.subheader("Summary by tier")
pct = lambda v: f"{v:+.2f}%"
summary_df = summary_df.astype({c: float for c in summary_df.columns if c.endswith("%")})
st.dataframe(
    styled(
        summary_df,
        colour_cols=("Avg Outperformance %", "Median Outperformance %"),
        extra_formats={
            "Avg Stock Return %": pct,
            "Avg NIFTY 50 Return %": pct,
            "Avg Outperformance %": pct,
            "Median Outperformance %": pct,
            "Beat NIFTY 50 %": lambda v: f"{v:.0f}%",
        },
    ),
    width="stretch",
    hide_index=True,
)

st.subheader("Stocks by tier")
for tab, tier in zip(st.tabs(tiers), tiers):
    with tab:
        t = perf[perf["Recommendation"] == tier].sort_values("Outperformance %", ascending=False, na_position="last")
        missing = t["Outperformance %"].isna().sum()
        if missing:
            st.caption(f"{missing} stock(s) without a measurable return; see the Note column.")
        st.dataframe(
            styled(t, colour_cols=("Outperformance %", "Stock Return %")).format(
                {"Score": lambda v: "Not applicable" if is_missing(v) else f"{v:.0f}"}
            ),
            width="stretch",
            hide_index=True,
        )

st.download_button(
    "Download verification (CSV)",
    data=csv_bytes(perf),
    file_name=f"bac_sma_verification_{scan_id}.csv",
    mime="text/csv",
)
