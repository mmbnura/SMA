import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.screening_logic import load_screening_config
from core import tickers as tickers_mod
from core.scan_history import init_db, save_scan_run
from core.screener import REC_EMOJI, fetch_and_score, fetch_price_history
from core.tickers import _LOAD_ERROR, get_all_sectors, load_nifty500

DISPLAY_COLS = [
    "Ticker",
    "Name",
    "Sector",
    "Price (Rs)",
    "Cap Bucket",
    "Score",
    "Recommendation",
    "P/E",
    "P/B",
    "ROE",
    "D/E",
    "EPS Growth",
    "Rev Growth",
    "Div Yield",
    "52W Position",
]


def build_scan_id(scan_type: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{scan_type}_{timestamp}"


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if "Price (Rs)" not in df.columns:
        for legacy_col in ["Price (₹)", "Price (â‚¹)"]:
            if legacy_col in df.columns:
                df = df.rename(columns={legacy_col: "Price (Rs)"})
                break

    for col in DISPLAY_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    return df


def render_results(df_all: pd.DataFrame, min_score: int, rec_filter: list[str], key_prefix: str) -> None:
    df_all = normalize_columns(df_all.copy())
    df = df_all[
        (df_all["Score"] >= min_score) & (df_all["Recommendation"].isin(rec_filter))
    ].sort_values("Score", ascending=False)

    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Screener", "Top Picks", "Deep Dive"])

    with tab1:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Stocks Scanned", len(df_all))
        c2.metric("Strong Buy", len(df_all[df_all["Recommendation"] == "Strong Buy"]))
        c3.metric("Buy", len(df_all[df_all["Recommendation"] == "Buy"]))
        c4.metric("Hold", len(df_all[df_all["Recommendation"] == "Hold"]))
        c5.metric("Avoid", len(df_all[df_all["Recommendation"] == "Avoid"]))

        st.divider()
        col_l, col_r = st.columns(2)

        with col_l:
            rec_counts = df_all["Recommendation"].value_counts().reset_index()
            rec_counts.columns = ["Recommendation", "Count"]
            fig_pie = px.pie(
                rec_counts,
                values="Count",
                names="Recommendation",
                title="Recommendation Distribution",
                hole=0.4,
            )
            fig_pie.update_layout(showlegend=False, margin=dict(t=50, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_r:
            sec_avg = (
                df_all.groupby("Sector")["Score"]
                .mean()
                .round(1)
                .sort_values(ascending=True)
                .reset_index()
            )
            fig_bar = px.bar(
                sec_avg,
                y="Sector",
                x="Score",
                orientation="h",
                title="Average Score by Sector",
                color="Score",
                color_continuous_scale="RdYlGn",
                range_color=[0, 100],
                text="Score",
            )
            fig_bar.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig_bar.update_layout(
                coloraxis_showscale=False,
                margin=dict(t=50, b=10),
                xaxis_range=[0, 110],
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        fig_hist = px.histogram(
            df_all,
            x="Score",
            nbins=20,
            title="Score Distribution Across All Scanned Stocks",
        )
        for cutoff in [75, 60, 45]:
            fig_hist.add_vline(x=cutoff, line_dash="dash")
        st.plotly_chart(fig_hist, use_container_width=True)

    with tab2:
        st.subheader(f"Screener Results - {len(df)} stocks")
        st.dataframe(
            df[DISPLAY_COLS],
            use_container_width=True,
            height=600,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
                "52W Position": st.column_config.ProgressColumn(
                    "52W Position",
                    min_value=0,
                    max_value=100,
                    format="%.0f%%",
                ),
                "Price (Rs)": st.column_config.NumberColumn("Price (Rs)", format="%.2f"),
            },
            hide_index=True,
        )

        csv = df[DISPLAY_COLS].to_csv(index=False)
        st.download_button(
            "Download Results as CSV",
            data=csv,
            file_name=f"nse_value_finder_{key_prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    with tab3:
        st.subheader("Top 20 Value Picks")
        top20 = df_all.sort_values("Score", ascending=False).head(20)
        for _, row in top20.iterrows():
            ca, cb, cc = st.columns([3, 5, 2])
            with ca:
                emoji = REC_EMOJI.get(row["Recommendation"], "")
                st.markdown(f"{emoji} **{row['Name']}**")
                st.caption(f"{row['Ticker']} | {row['Sector']}")
            with cb:
                score_val = int(row["Score"])
                color = row.get("Colour", "#4c9be8")
                st.markdown(
                    (
                        '<div style="background:#2a2d3e;border-radius:6px;height:22px;width:100%;">'
                        f'<div style="height:22px;border-radius:6px;background:{color};width:{score_val}%;'
                        f'display:flex;align-items:center;padding-left:8px;color:#000;font-size:12px;font-weight:700;">'
                        f"{score_val}/100</div></div>"
                    ),
                    unsafe_allow_html=True,
                )
            with cc:
                price = row.get("Price (Rs)")
                st.markdown(f"**Rs {price:,.2f}**" if price else "N/A")
                st.caption(row["Recommendation"])
            st.divider()

    with tab4:
        st.subheader("Stock Deep Dive")
        ticker_list = df_all["Ticker"].tolist()
        selected_base = st.selectbox(
            "Select a stock",
            ticker_list,
            key=f"deep_dive_select_{key_prefix}",
            format_func=lambda x: f"{x} - {df_all.loc[df_all['Ticker'] == x, 'Name'].values[0]}",
        )

        if selected_base:
            row = df_all[df_all["Ticker"] == selected_base].iloc[0]
            full_ticker = selected_base + ".NS"
            emoji = REC_EMOJI.get(row["Recommendation"], "")

            st.markdown(f"## {emoji} {row['Name']} `{selected_base}`")
            h1, h2, h3, h4, h5 = st.columns(5)
            price_val = row.get("Price (Rs)")
            h1.metric("Price", f"Rs {price_val:,.2f}" if price_val else "N/A")
            h2.metric("Score", f"{row['Score']}/100")
            h3.metric("Signal", row["Recommendation"])
            h4.metric("Sector", row["Sector"])
            h5.metric("Market Cap", row["Cap Bucket"])

            st.divider()
            with st.spinner("Loading 1-year price chart..."):
                hist = fetch_price_history(full_ticker)
                if not hist.empty and "Close" in hist.columns:
                    close = hist["Close"].squeeze()
                    ma50 = close.rolling(50).mean()
                    ma20 = close.rolling(20).mean()

                    fig_p = go.Figure()
                    fig_p.add_trace(
                        go.Scatter(x=hist.index, y=close, name="Close", mode="lines", line=dict(width=2))
                    )
                    fig_p.add_trace(
                        go.Scatter(
                            x=hist.index,
                            y=ma50,
                            name="50-Day MA",
                            mode="lines",
                            line=dict(width=1.5, dash="dash"),
                        )
                    )
                    fig_p.add_trace(
                        go.Scatter(
                            x=hist.index,
                            y=ma20,
                            name="20-Day MA",
                            mode="lines",
                            line=dict(width=1.5, dash="dot"),
                        )
                    )
                    fig_p.update_layout(
                        title=f"{row['Name']} - 1 Year Price Chart",
                        xaxis_title="Date",
                        yaxis_title="Price (Rs)",
                        hovermode="x unified",
                        margin=dict(t=60, b=20),
                    )
                    st.plotly_chart(fig_p, use_container_width=True)
                else:
                    st.warning("Price chart not available for this ticker.")

            left, right = st.columns(2)
            with left:
                categories = ["P/E", "P/B", "ROE", "D/E", "EPS Growth", "Rev Growth", "Div Yield"]
                scores = [
                    row.get("s_PE", 0),
                    row.get("s_PB", 0),
                    row.get("s_ROE", 0),
                    row.get("s_DE", 0),
                    row.get("s_EPS", 0),
                    row.get("s_Rev", 0),
                    row.get("s_Div", 0),
                ]
                max_pts = [
                    row.get("m_PE", 20),
                    row.get("m_PB", 15),
                    row.get("m_ROE", 20),
                    row.get("m_DE", 15),
                    row.get("m_EPS", 15),
                    row.get("m_Rev", 10),
                    row.get("m_Div", 5),
                ]
                pct = [(s / m * 100) if m else 0 for s, m in zip(scores, max_pts)]
                fig_r = go.Figure(
                    go.Scatterpolar(
                        r=pct + [pct[0]],
                        theta=categories + [categories[0]],
                        fill="toself",
                        name="Score %",
                    )
                )
                fig_r.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    title="Score Breakdown (% of max per metric)",
                )
                st.plotly_chart(fig_r, use_container_width=True)

            with right:
                st.markdown("#### Fundamental Metrics")

                def fmt_points(value: float) -> str:
                    value = float(value)
                    return str(int(value)) if value.is_integer() else f"{value:.1f}"

                metrics_df = pd.DataFrame(
                    {
                        "Metric": categories,
                        "Value": [row.get(c, "N/A") for c in categories],
                        "Score": [f"{fmt_points(s)}/{fmt_points(m)}" for s, m in zip(scores, max_pts)],
                    }
                )
                st.dataframe(metrics_df, use_container_width=True, hide_index=True, height=280)


st.set_page_config(
    page_title="BAC SMA",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
[data-testid="stSidebarNav"] {
    display: none;
}
.disclaimer {
    background: #1e2130;
    border-left: 4px solid #ff6d00;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    font-size: 0.8rem;
    color: #aaa;
}
</style>
""",
    unsafe_allow_html=True,
)

init_db()

if "results_df" not in st.session_state:
    st.session_state.results_df = None
if "scan_time" not in st.session_state:
    st.session_state.scan_time = None
if "last_scan_id" not in st.session_state:
    st.session_state.last_scan_id = None

with st.sidebar:
    st.title("BAC SMA")
    st.caption("Fundamental screener for Nifty 500")
    st.page_link("app.py", label="Screener")
    st.page_link("pages/History.py", label="History")
    st.page_link("pages/Screening_Logic.py", label="Screening Logic")
    st.divider()

    if "nifty500_stocks" not in st.session_state:
        st.session_state.nifty500_stocks = tickers_mod.NIFTY500_STOCKS
        st.session_state.all_sectors = tickers_mod.ALL_SECTORS

    col_ref1, col_ref2 = st.columns([3, 1])
    with col_ref1:
        n_total = len(st.session_state.nifty500_stocks)
        if n_total:
            st.success(f"{n_total} Nifty 500 stocks loaded")
        else:
            st.error("Could not load stock list")
    with col_ref2:
        if st.button("Refresh", help="Re-fetch Nifty 500 list from NSE"):
            with st.spinner("Fetching from NSE..."):
                try:
                    fresh = load_nifty500(force_refresh=True)
                    st.session_state.nifty500_stocks = fresh
                    st.session_state.all_sectors = get_all_sectors(fresh)
                    st.success(f"Refreshed - {len(fresh)} stocks")
                    st.rerun()
                except Exception as err:
                    st.error(f"Fetch failed: {err}")

    if _LOAD_ERROR:
        st.warning(f"NSE fetch error: {_LOAD_ERROR}")

    nifty500_stocks = st.session_state.nifty500_stocks
    all_sectors = st.session_state.all_sectors

    st.divider()
    st.subheader("Sector Filter")
    select_all = st.checkbox("Select All Sectors", value=True)
    if select_all:
        selected_sectors = all_sectors
    else:
        selected_sectors = st.multiselect(
            "Choose sectors",
            all_sectors,
            default=[s for s in ["Information Technology", "Bank", "FMCG", "Pharmaceuticals"] if s in all_sectors],
        )

    filtered_stocks = [(t, n, s) for t, n, s in nifty500_stocks if s in selected_sectors]
    st.info(f"{len(filtered_stocks)} stocks in scope")
    st.divider()

    scan_btn = st.button("Run Scan", type="primary", use_container_width=True)
    if st.session_state.scan_time:
        st.caption(f"Last scan: {st.session_state.scan_time}")
    if st.session_state.last_scan_id:
        st.caption(f"Last scan id: {st.session_state.last_scan_id}")

    st.divider()
    st.subheader("Result Filters")
    min_score = st.slider("Min Score", 0, 100, 0, step=5)
    rec_filter = st.multiselect(
        "Recommendation",
        ["Strong Buy", "Buy", "Hold", "Avoid"],
        default=["Strong Buy", "Buy", "Hold", "Avoid"],
    )

    st.divider()
    st.markdown(
        '<div class="disclaimer"><b>Disclaimer:</b> This app is for educational '
        "purposes only. It does not constitute investment advice.</div>",
        unsafe_allow_html=True,
    )

st.title("BAC SMA")
st.caption(
    "Multi-factor fundamental screener. Data source: Yahoo Finance. "
    "Scans are automatically saved to local history."
)

if scan_btn:
    if not filtered_stocks:
        st.error("No stocks selected. Please choose at least one sector.")
    else:
        results = []
        prog = st.progress(0, text="Starting scan...")
        status = st.empty()
        total = len(filtered_stocks)
        scan_started = datetime.now()
        screening_config = load_screening_config()

        for i, (ticker, name, sector) in enumerate(filtered_stocks):
            status.markdown(f"Fetching **{name}** ({i + 1}/{total})...")
            prog.progress((i + 1) / total, text=f"{i + 1}/{total} stocks")
            result = fetch_and_score(ticker, name, sector, screening_config=screening_config)
            if result:
                for legacy_col in ["Price (₹)", "Price (â‚¹)"]:
                    if legacy_col in result and "Price (Rs)" not in result:
                        result["Price (Rs)"] = result.pop(legacy_col)
                        break
                results.append(result)
            time.sleep(0.05)

        prog.empty()
        status.empty()

        results_df = pd.DataFrame(results) if results else pd.DataFrame(columns=DISPLAY_COLS)
        st.session_state.results_df = results_df
        st.session_state.scan_time = scan_started.strftime("%d %b %Y, %I:%M %p")

        scan_type = "FULL" if select_all or len(selected_sectors) == len(all_sectors) else "SECTOR"
        scan_id = build_scan_id(scan_type)
        save_scan_run(
            scan_id=scan_id,
            scan_type=scan_type,
            created_at=scan_started.isoformat(timespec="seconds"),
            selected_sectors=selected_sectors,
            total_in_scope=total,
            total_scored=len(results),
            results_df=results_df,
        )
        st.session_state.last_scan_id = scan_id

        if results:
            st.success(
                f"Scan complete - fetched data for {len(results)} of {total} stocks. "
                f"{total - len(results)} skipped. Saved as scan id: {scan_id}"
            )
        else:
            st.warning(
                f"Scan finished but no stock data was returned. "
                f"Saved empty run as scan id: {scan_id}"
            )

if st.session_state.results_df is not None and not st.session_state.results_df.empty:
    render_results(st.session_state.results_df, min_score, rec_filter, key_prefix="live")
else:
    st.info("Select sectors in the sidebar and click Run Scan to begin.")

