from pathlib import Path

import streamlit as st

from core.scan_history import init_db, save_scan_run
from core.screener import (
    cache_age_summary,
    check_yahoo_reachable,
    fetch_and_cache_base_data,
    load_base_cache,
    run_scan,
    tickers_needing_fetch,
)
from core.screening_logic import load_screening_config
from core.tickers import get_all_sectors, load_nifty500
from core.timeutil import format_age, now_ist
from screens.components import page_setup, render_results, result_filters, sidebar_disclaimer

BASE_DATA_PATH = Path(__file__).resolve().parent / "data" / "base_data.csv"

page_setup("Screener", "Fundamental screener for the Nifty 500")
init_db()


def load_universe(force: bool = False) -> None:
    try:
        st.session_state.universe = load_nifty500(force_refresh=force)
        st.session_state.universe_error = None
    except Exception as err:
        st.session_state.universe = None
        st.session_state.universe_error = str(err)


if "universe" not in st.session_state:
    load_universe()
st.session_state.setdefault("scan", None)

universe = st.session_state.universe
stocks = universe.stocks if universe else []
all_sectors = get_all_sectors(stocks)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Universe")
    if universe:
        src = "live from NSE" if universe.source == "nse" else "saved copy"
        as_of = f"{universe.as_of:%d %b %Y %H:%M} IST" if universe.as_of else "date not available"
        st.success(f"{len(stocks)} Nifty 500 stocks ({src}, {as_of})")
        if universe.warning:
            st.warning(universe.warning)
    else:
        st.error(st.session_state.universe_error or "Could not load the Nifty 500 list.")
    if st.button("Refresh list from NSE", width="stretch"):
        with st.spinner("Fetching from NSE..."):
            load_universe(force=True)
        st.rerun()

    st.divider()
    st.subheader("Sectors")
    select_all = st.checkbox("All sectors", value=True)
    if select_all:
        selected_sectors = all_sectors
    else:
        selected_sectors = st.multiselect("Choose sectors", all_sectors, default=all_sectors[:1])
    scope = [s for s in stocks if s[2] in selected_sectors]
    scope_bases = [t.replace(".NS", "") for t, _, _ in scope]

    st.divider()
    st.subheader("Fundamental data")
    max_age = st.number_input(
        "Re-download data older than (hours)",
        min_value=0, max_value=24 * 30, value=24, step=6,
        help="Run Scan re-downloads in-scope stocks whose cached data is older than this. 0 = always re-download.",
    )
    cache = load_base_cache(BASE_DATA_PATH)
    summary = cache_age_summary(cache, scope_bases)
    need = tickers_needing_fetch(cache, scope_bases, max_age)
    have = len(scope_bases) - len(summary["missing"])
    st.caption(f"Cached for {have} of {len(scope_bases)} stocks in scope.")
    if summary["dated"]:
        oldest = min(ts for _, ts in summary["dated"])
        st.caption(f"Oldest cached data: {oldest:%d %b %Y %H:%M} IST ({format_age(oldest)}).")
    if summary["undated"]:
        st.caption(f"{len(summary['undated'])} cached rows have no download time and will be re-downloaded.")
    st.caption(f"Run Scan will download {len(need)} stock(s).")

    scan_btn = st.button("Run Scan", type="primary", width="stretch", disabled=not scope)
    refresh_all = st.button(
        "Re-download all in scope, then scan", width="stretch", disabled=not scope,
        help="Ignores the age setting and fetches fresh data for every stock in scope.",
    )

    scan = st.session_state.scan
    if scan:
        st.caption(f"Last scan: {scan['scan_id']}")

    st.divider()
    st.subheader("Result filters")
    min_score, rec_filter = result_filters("live")

sidebar_disclaimer()

st.title("BAC SMA — Nifty 500 Screener")
st.caption(
    "Multi-factor fundamental screener. Data: NSE Indices (constituents) and Yahoo Finance (fundamentals, prices). "
    "Every scan is saved to History."
)

# ─────────────────────────────────────────────────────────────────────────────
# Scan
# ─────────────────────────────────────────────────────────────────────────────

if scan_btn or refresh_all:
    to_fetch = scope_bases if refresh_all else need
    failures = []
    download_error = None
    if to_fetch:
        fetch_set = set(to_fetch)
        fetch_list = [s for s in scope if s[0].replace(".NS", "") in fetch_set]
        cached = set(cache["Ticker"])
        with st.spinner("Checking connection to Yahoo Finance..."):
            download_error = check_yahoo_reachable()
        if download_error:
            failures = [
                {"Ticker": t.replace(".NS", ""), "Name": n, "Sector": s,
                 "Reason": download_error + (" — older cached data kept" if t.replace(".NS", "") in cached else "")}
                for t, n, s in fetch_list
            ]
        else:
            prog = st.progress(0.0, text=f"Downloading fundamentals for {len(fetch_list)} stocks from Yahoo Finance...")

            def on_progress(done: int, total: int, name: str) -> None:
                prog.progress(done / total, text=f"Downloaded {done}/{total} — {name}")

            cache, failures = fetch_and_cache_base_data(fetch_list, BASE_DATA_PATH, progress_callback=on_progress)
            prog.empty()

    config = load_screening_config()
    started = now_ist()
    result = run_scan(scope, cache, config, failures)

    scan_type = "FULL" if select_all or set(selected_sectors) == set(all_sectors) else "SECTOR"
    scan_id = f"{scan_type}_{started:%Y%m%d_%H%M%S_%f}"
    save_scan_run(
        scan_id=scan_id,
        scan_type=scan_type,
        created_at=started.isoformat(timespec="seconds"),
        selected_sectors=list(selected_sectors),
        total_in_scope=result.in_scope,
        results_df=result.scored,
        disqualified_df=result.disqualified,
        unavailable_df=result.unavailable,
        config=config,
    )
    st.session_state.scan = {
        "scan_id": scan_id,
        "result": result,
        "config": config,
        "failures": failures,
        "fetched": len(to_fetch),
        "download_error": download_error,
    }
    st.rerun()

scan = st.session_state.scan
if scan:
    result = scan["result"]
    if scan.get("download_error"):
        st.error(
            f"{scan['download_error']} No data was downloaded; this scan used only previously cached data. "
            "Check each stock's 'Data As Of' column."
        )
    msg = (
        f"Scan **{scan['scan_id']}** — {result.in_scope} in scope: {len(result.scored)} scored, "
        f"{len(result.disqualified)} disqualified, {len(result.unavailable)} without data."
    )
    if scan["fetched"]:
        msg += f" Downloaded {scan['fetched'] - len(scan['failures'])} of {scan['fetched']} requested."
    st.success(msg)
    if scan["failures"]:
        with st.expander(f"{len(scan['failures'])} download(s) failed — details"):
            st.dataframe(scan["failures"], width="stretch", hide_index=True)
    render_results(
        result.scored,
        result.disqualified,
        result.unavailable,
        result.in_scope,
        scan["config"],
        min_score,
        rec_filter,
        key_prefix="live",
    )
else:
    st.info("Choose sectors in the sidebar and click **Run Scan**. Missing or stale data is downloaded automatically.")
