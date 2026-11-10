"""Shared Streamlit UI: page chrome, result normalisation, tables and result tabs."""

from __future__ import annotations

import math
import re
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.screener import (
    INSUFFICIENT_DATA,
    NOT_AVAILABLE,
    REC_COLOURS,
    REC_EMOJI,
    RECOMMENDATION_ORDER,
    fetch_price_history,
    sort_scored,
)
from core.indianapi import FIELD_MAP
from core.screening_logic import DEFAULT_RECOMMENDATION_THRESHOLDS, METRIC_DEFINITIONS

API_KEYS = {m.label: m.keys[0] for m in FIELD_MAP}

NAV = [
    ("app.py", "Screener"),
    ("pages/History.py", "History"),
    ("pages/Accuracy_Verification.py", "Accuracy Verification"),
    ("pages/Screening_Logic.py", "Screening Logic"),
]

METRIC_COLS = [m["column"] for m in METRIC_DEFINITIONS]

TABLE_COLS = [
    "Ticker",
    "Name",
    "Sector",
    "Score",
    "Recommendation",
    "Data Coverage %",
    "Price (₹)",
    "Market Cap (₹ Cr)",
    *METRIC_COLS,
    "52W Position %",
    "Data As Of",
    "Unavailable Metrics",
    "Filled From IndianAPI",
]

DISCLAIMER = (
    "For education and research only. Not investment advice. Scores are computed "
    "mechanically from Yahoo Finance data, which can be delayed, incomplete or wrong. "
    "Verify figures with company filings before acting."
)


def page_setup(page_title: str, caption: str) -> None:
    st.set_page_config(page_title=f"BAC SMA - {page_title}", layout="wide", initial_sidebar_state="expanded")
    st.markdown(
        "<style>[data-testid='stSidebarNav']{display:none;}</style>",
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.title("BAC SMA")
        st.caption(caption)
        for path, label in NAV:
            st.page_link(path, label=label)
        st.divider()


def sidebar_disclaimer() -> None:
    with st.sidebar:
        st.divider()
        st.caption(f"**Disclaimer:** {DISCLAIMER}")


# ─────────────────────────────────────────────────────────────────────────────
# Normalising results (including scans saved by older versions)
# ─────────────────────────────────────────────────────────────────────────────

_LEGACY_RENAMES = {
    "Price (Rs)": "Price (₹)",
    "Price (â‚¹)": "Price (₹)",
    "52W Position": "52W Position %",
    "ROE": "ROE %",
    "ROA": "ROA %",
    "FCF Yield": "FCF Yield %",
    "Op Margin": "Op Margin %",
    "EPS Growth": "Earnings Growth %",
    "Rev Growth": "Revenue Growth %",
}
_NUMBER_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[x%]?\s*$")


def _parse_legacy(value):
    if value is None or isinstance(value, (int, float)):
        return value
    match = _NUMBER_RE.match(str(value))
    return float(match.group(1)) if match else None


def normalize_results(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=TABLE_COLS)
    df = df.rename(columns={k: v for k, v in _LEGACY_RENAMES.items() if k in df.columns})
    if "Market Cap (₹ Cr)" not in df.columns and "Market Cap" in df.columns:
        df["Market Cap (₹ Cr)"] = pd.to_numeric(df["Market Cap"], errors="coerce") / 1e7
    for col in METRIC_COLS + ["Price (₹)", "52W Position %", "Score", "Data Coverage %"]:
        if col in df.columns and df[col].dtype == object:
            df[col] = df[col].map(_parse_legacy)
    for col in TABLE_COLS:
        if col not in df.columns:
            df[col] = None
    for col in METRIC_COLS + ["Price (₹)", "Market Cap (₹ Cr)", "52W Position %", "Score", "Data Coverage %"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Data As Of"] = df["Data As Of"].fillna(NOT_AVAILABLE)
    df["Unavailable Metrics"] = df["Unavailable Metrics"].fillna("")
    df["Filled From IndianAPI"] = df["Filled From IndianAPI"].fillna("")
    return df


def thresholds_of(config: dict | None) -> dict:
    if config and isinstance(config.get("recommendation_thresholds"), dict):
        return config["recommendation_thresholds"]
    return DEFAULT_RECOMMENDATION_THRESHOLDS


# ─────────────────────────────────────────────────────────────────────────────
# Formatting
# ─────────────────────────────────────────────────────────────────────────────

def is_missing(v) -> bool:
    if v is None:
        return True
    try:
        return math.isnan(v) or math.isinf(v)
    except TypeError:
        return False


def _fmt(pattern: str):
    def inner(v):
        if is_missing(v):
            return NOT_AVAILABLE
        if isinstance(v, str):
            return v
        return pattern.format(v)
    return inner


FORMATS = {
    "Score": _fmt("{:.0f}"),
    "Data Coverage %": _fmt("{:.0f}%"),
    "Price (₹)": _fmt("₹{:,.2f}"),
    "52W High": _fmt("₹{:,.2f}"),
    "52W Low": _fmt("₹{:,.2f}"),
    "Market Cap (₹ Cr)": _fmt("{:,.0f}"),
    "52W Position %": _fmt("{:.0f}%"),
    "P/E": _fmt("{:.1f}"),
    "PEG": _fmt("{:.2f}"),
    "P/B": _fmt("{:.2f}"),
    "D/E": _fmt("{:.2f}x"),
    "ROE %": _fmt("{:.1f}%"),
    "ROA %": _fmt("{:.1f}%"),
    "FCF Yield %": _fmt("{:.2f}%"),
    "Op Margin %": _fmt("{:.1f}%"),
    "Earnings Growth %": _fmt("{:.1f}%"),
    "Revenue Growth %": _fmt("{:.1f}%"),
    "Stock Return %": _fmt("{:+.2f}%"),
    "NIFTY 50 Return %": _fmt("{:+.2f}%"),
    "Outperformance %": _fmt("{:+.2f}%"),
    "Start Price (₹)": _fmt("₹{:,.2f}"),
    "End Price (₹)": _fmt("₹{:,.2f}"),
}

# Streamlit renders NaN as a grey "None" and ignores the Styler text for it, so
# missing numbers are swapped for +/-inf in the displayed copy (the Styler then
# shows the label). The sign keeps them at the bottom under the natural sort.
LOWER_IS_BETTER = {"P/E", "PEG", "P/B", "D/E"}


def styled(
    df: pd.DataFrame,
    colour_cols: tuple[str, ...] = (),
    extra_formats: dict | None = None,
    missing_text: str = NOT_AVAILABLE,
) -> "pd.io.formats.style.Styler":
    formats = {c: f for c, f in FORMATS.items() if c in df.columns}
    formats.update(extra_formats or {})

    disp = df.copy()
    for col in disp.columns:
        if pd.api.types.is_numeric_dtype(disp[col]) and not pd.api.types.is_bool_dtype(disp[col]):
            if disp[col].isna().any():
                sentinel = math.inf if col in LOWER_IS_BETTER else -math.inf
                disp[col] = disp[col].astype(float).fillna(sentinel)
                formats.setdefault(col, _fmt("{:,.0f}"))

    def wrap(f, text):
        return lambda v: text if is_missing(v) else f(v)

    styler = disp.style.format({c: wrap(f, missing_text) for c, f in formats.items()})

    # Metric cells that are "not applicable" (e.g. D/E for financials) get their own label and grey italics.
    if "Unavailable Metrics" in disp.columns:
        notes = disp["Unavailable Metrics"].astype(str)
        css = pd.DataFrame("", index=disp.index, columns=disp.columns)
        for metric in METRIC_DEFINITIONS:
            col = metric["column"]
            if col not in disp.columns:
                continue
            mask = notes.str.contains(f"{metric['label']}: not applicable", regex=False)
            if mask.any():
                styler = styler.format(
                    wrap(formats[col], "Not applicable"), subset=pd.IndexSlice[disp.index[mask], [col]]
                )
                css.loc[mask, col] = "color: #8a8f98; font-style: italic"
        styler = styler.apply(lambda _: css, axis=None)

    for col in colour_cols:
        if col in disp.columns:
            styler = styler.map(
                lambda v: "" if is_missing(v) else ("color: #d50000" if v < 0 else "color: #00a843"),
                subset=[col],
            )
    if "Recommendation" in disp.columns:
        styler = styler.map(
            lambda v: f"color: {REC_COLOURS.get(v, 'inherit')}; font-weight: 600", subset=["Recommendation"]
        )
    return styler


def csv_bytes(df: pd.DataFrame) -> bytes:
    # utf-8-sig so Excel shows ₹ correctly.
    return df.to_csv(index=False, na_rep=NOT_AVAILABLE).encode("utf-8-sig")


# ─────────────────────────────────────────────────────────────────────────────
# Result tabs
# ─────────────────────────────────────────────────────────────────────────────

def result_filters(key_prefix: str, container=None) -> tuple[int, list[str]]:
    target = container or st
    min_score = target.slider("Min score", 0, 100, 0, step=5, key=f"{key_prefix}_min_score")
    rec_filter = target.multiselect(
        "Recommendation",
        RECOMMENDATION_ORDER,
        default=RECOMMENDATION_ORDER,
        key=f"{key_prefix}_rec_filter",
    )
    return min_score, rec_filter


def _unavailable_by_label(row: pd.Series) -> dict[str, str]:
    notes = {}
    for part in str(row.get("Unavailable Metrics") or "").split("; "):
        if ": " in part:
            label, note = part.split(": ", 1)
            notes[label] = note
    return notes


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_history(yf_ticker: str) -> pd.DataFrame:
    return fetch_price_history(yf_ticker)


def render_results(
    scored: pd.DataFrame,
    disqualified: pd.DataFrame | None,
    unavailable: pd.DataFrame | None,
    in_scope: int | None,
    config: dict | None,
    min_score: int,
    rec_filter: list[str],
    key_prefix: str,
) -> None:
    df_all = normalize_results(scored)
    disqualified = disqualified if disqualified is not None else pd.DataFrame()
    unavailable = unavailable if unavailable is not None else pd.DataFrame()
    thresholds = thresholds_of(config)

    score_ok = df_all["Score"].fillna(-1) >= min_score if min_score > 0 else pd.Series(True, index=df_all.index)
    df = sort_scored(df_all[score_ok & df_all["Recommendation"].isin(rec_filter)])

    tab_dash, tab_table, tab_top, tab_deep, tab_excl = st.tabs(
        ["Dashboard", "Screener", "Top Picks", "Deep Dive", f"Excluded ({len(disqualified) + len(unavailable)})"]
    )

    with tab_dash:
        _render_dashboard(df_all, disqualified, unavailable, in_scope, thresholds)

    with tab_table:
        st.subheader(f"Screener results — {len(df)} of {len(df_all)} scored stocks")
        st.caption(
            "Cells marked **Not available** had no data from Yahoo Finance and were left out of the score "
            "(never counted as zero). **Data Coverage** is the share of scoring weight backed by real data."
        )
        table = df[TABLE_COLS]
        st.dataframe(styled(table), width="stretch", height=600, hide_index=True)
        st.download_button(
            "Download results (CSV)",
            data=csv_bytes(table),
            file_name=f"bac_sma_{key_prefix}_{datetime.now():%Y%m%d_%H%M}.csv",
            mime="text/csv",
            key=f"{key_prefix}_csv",
        )

    with tab_top:
        _render_top_picks(df)

    with tab_deep:
        _render_deep_dive(df_all, key_prefix)

    with tab_excl:
        _render_excluded(disqualified, unavailable, key_prefix)


def _render_dashboard(df_all, disqualified, unavailable, in_scope, thresholds) -> None:
    c = st.columns(4)
    c[0].metric("In scope", in_scope if in_scope is not None else "Not recorded")
    c[1].metric("Scored", len(df_all))
    c[2].metric("Disqualified", len(disqualified), help="Failed a hard filter; see the Excluded tab.")
    c[3].metric("Data unavailable", len(unavailable), help="No fundamentals could be downloaded; see the Excluded tab.")

    counts = df_all["Recommendation"].value_counts()
    c = st.columns(len(RECOMMENDATION_ORDER))
    for col, rec in zip(c, RECOMMENDATION_ORDER):
        col.metric(f"{REC_EMOJI[rec]} {rec}", int(counts.get(rec, 0)))

    if df_all.empty:
        st.info("No stocks were scored in this scan.")
        return

    st.divider()
    left, right = st.columns(2)
    with left:
        rec_counts = (
            counts.reindex(RECOMMENDATION_ORDER).fillna(0).astype(int).rename_axis("Recommendation").reset_index(name="Count")
        )
        rec_counts = rec_counts[rec_counts["Count"] > 0]
        fig = px.pie(
            rec_counts, values="Count", names="Recommendation", hole=0.45,
            title="Recommendation mix", color="Recommendation", color_discrete_map=REC_COLOURS,
            category_orders={"Recommendation": RECOMMENDATION_ORDER},
        )
        fig.update_traces(sort=False)
        fig.update_layout(margin=dict(t=50, b=10), height=380)
        st.plotly_chart(fig, width="stretch")

    with right:
        rated = df_all[df_all["Recommendation"] != INSUFFICIENT_DATA]
        if rated.empty:
            st.info("No stock had enough data for a sector comparison.")
        else:
            sec = rated.groupby("Sector")["Score"].agg(["mean", "count"]).reset_index()
            sec.columns = ["Sector", "Average score", "Stocks"]
            sec = sec.sort_values("Average score")
            fig = px.bar(
                sec, y="Sector", x="Average score", orientation="h", text="Average score",
                hover_data={"Stocks": True}, color="Average score", color_continuous_scale="RdYlGn",
                range_color=[0, 100], title="Average score by sector (stocks with sufficient data)",
            )
            fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
            fig.update_layout(coloraxis_showscale=False, xaxis_range=[0, 110], margin=dict(t=50, b=10),
                              height=max(350, 28 * len(sec)))
            st.plotly_chart(fig, width="stretch")

    scored_only = df_all.dropna(subset=["Score"])
    if not scored_only.empty:
        fig = px.histogram(scored_only, x="Score", nbins=20, title="Score distribution")
        for key, label in (("strong_buy", "Strong Buy"), ("buy", "Buy"), ("hold", "Hold")):
            fig.add_vline(x=thresholds[key], line_dash="dash", annotation_text=label)
        fig.update_xaxes(range=[0, 100])
        st.plotly_chart(fig, width="stretch")

    availability = []
    for metric in METRIC_DEFINITIONS:
        col = metric["column"]
        notes = df_all["Unavailable Metrics"].astype(str)
        n_na = int(notes.str.contains(f"{metric['label']}: not applicable", regex=False).sum())
        n_avail = int(df_all[col].notna().sum())
        availability.append({
            "Metric": metric["label"],
            "Available": n_avail,
            "Not available": len(df_all) - n_avail - n_na,
            "Not applicable": n_na,
        })
    av = pd.DataFrame(availability)
    fig = go.Figure()
    for name, colour in (("Available", "#2e7d32"), ("Not available", "#d50000"), ("Not applicable", "#8a8f98")):
        fig.add_bar(y=av["Metric"], x=av[name], name=name, orientation="h", marker_color=colour)
    fig.update_layout(barmode="stack", title="Data availability per metric (scored stocks)",
                      margin=dict(t=50, b=10), height=380, xaxis_title="Stocks")
    st.plotly_chart(fig, width="stretch")


def _render_top_picks(df: pd.DataFrame) -> None:
    rated = df[df["Recommendation"] != INSUFFICIENT_DATA].dropna(subset=["Score"]).head(20)
    st.subheader("Top 20 by score")
    st.caption(f"Respects the sidebar filters. Stocks rated '{INSUFFICIENT_DATA}' are left out.")
    if rated.empty:
        st.info("No stocks match the current filters.")
        return
    for _, row in rated.iterrows():
        a, b, c = st.columns([3, 5, 2])
        rec = row["Recommendation"]
        with a:
            st.markdown(f"{REC_EMOJI.get(rec, '')} **{row['Name']}**")
            st.caption(f"{row['Ticker']} · {row['Sector']}")
        with b:
            score = int(row["Score"])
            colour = REC_COLOURS.get(rec, "#4c9be8")
            st.markdown(
                '<div style="background:rgba(128,128,128,.2);border-radius:6px;height:22px;width:100%;">'
                f'<div style="height:22px;border-radius:6px;background:{colour};width:{score}%;'
                'display:flex;align-items:center;padding-left:8px;color:#000;font-size:12px;font-weight:700;">'
                f"{score}/100</div></div>",
                unsafe_allow_html=True,
            )
            st.caption(f"Data coverage {FORMATS['Data Coverage %'](row['Data Coverage %'])}")
        with c:
            st.markdown(f"**{FORMATS['Price (₹)'](row['Price (₹)'])}**")
            st.caption(rec)
        st.divider()


def _render_deep_dive(df_all: pd.DataFrame, key_prefix: str) -> None:
    if df_all.empty:
        st.info("No scored stocks to show.")
        return
    names = dict(zip(df_all["Ticker"], df_all["Name"]))
    ticker = st.selectbox(
        "Select a stock",
        df_all["Ticker"].tolist(),
        key=f"{key_prefix}_deep_dive",
        format_func=lambda t: f"{t} — {names.get(t, '')}",
    )
    if not ticker:
        return
    row = df_all[df_all["Ticker"] == ticker].iloc[0]
    rec = row["Recommendation"]

    st.markdown(f"## {REC_EMOJI.get(rec, '')} {row['Name']} `{ticker}`")
    st.caption(f"Sector: {row['Sector']} · Fundamentals as of {row['Data As Of']}")
    h = st.columns(5)
    h[0].metric("Price", FORMATS["Price (₹)"](row["Price (₹)"]))
    h[1].metric("Score", f"{int(row['Score'])}/100" if pd.notna(row["Score"]) else NOT_AVAILABLE)
    h[2].metric("Signal", rec)
    h[3].metric("Data coverage", FORMATS["Data Coverage %"](row["Data Coverage %"]))
    h[4].metric("Market cap (₹ Cr)", FORMATS["Market Cap (₹ Cr)"](row["Market Cap (₹ Cr)"]))
    if rec == INSUFFICIENT_DATA:
        st.warning(
            "Not enough of the scoring data is available for this stock to issue a recommendation. "
            "The score shown uses only the metrics that are available."
        )

    st.divider()
    with st.spinner("Loading 1-year price chart..."):
        hist = _cached_history(f"{ticker}.NS")
    if not hist.empty and "Close" in hist.columns and hist["Close"].notna().any():
        close = hist["Close"].squeeze()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=close, name="Close", mode="lines", line=dict(width=2)))
        fig.add_trace(go.Scatter(x=hist.index, y=close.rolling(50).mean(), name="50-day MA",
                                 mode="lines", line=dict(width=1.5, dash="dash")))
        fig.add_trace(go.Scatter(x=hist.index, y=close.rolling(20).mean(), name="20-day MA",
                                 mode="lines", line=dict(width=1.5, dash="dot")))
        fig.update_layout(title=f"{row['Name']} — 1 year", yaxis_title="Price (₹)",
                          hovermode="x unified", margin=dict(t=60, b=20))
        st.plotly_chart(fig, width="stretch")
    else:
        st.warning("Price history is not available from Yahoo Finance for this stock right now.")

    notes = _unavailable_by_label(row)
    filled = {x.strip() for x in str(row.get("Filled From IndianAPI") or "").split(",") if x.strip()}
    api_as_of = row.get("IndianAPI As Of")
    api_date = f" (as of {api_as_of})" if isinstance(api_as_of, str) and api_as_of else ""
    if filled:
        st.info(f"Filled from IndianAPI{api_date} because Yahoo Finance did not provide them: {', '.join(sorted(filled))}.")
    lines = []
    for metric in METRIC_DEFINITIONS:
        col = metric["column"]
        value = row.get(col)
        pts, mx = row.get(metric["score_col"]), row.get(metric["max_col"])
        note = notes.get(metric["label"], "")
        if note.startswith("not applicable"):
            shown, points = "Not applicable", "Excluded"
        elif value is None or pd.isna(value):
            shown, points = NOT_AVAILABLE, "Excluded"
        else:
            shown = FORMATS[col](value)
            if mx is None or pd.isna(mx) or mx == 0:
                points = "Disabled"
            elif pts is None or pd.isna(pts):
                points = NOT_AVAILABLE
            else:
                points = f"{pts:.1f} / {mx:g}"
        source = metric["source"]
        if metric["label"] in filled:
            source = f"IndianAPI `{API_KEYS[metric['label']]}`{api_date}"
        elif metric["label"] == "FCF Yield" and "Market cap" in filled:
            source = f"Yahoo Finance `freeCashflow` / IndianAPI market cap{api_date}"
        lines.append({"Metric": metric["label"], "Value": shown, "Points": points,
                      "Note": note or "", "Source": source})
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Fundamentals and points")
        st.dataframe(pd.DataFrame(lines), width="stretch", hide_index=True, height=400)
    with right:
        scored_rows = [ln for ln in lines if "/" in ln["Points"]]
        if scored_rows:
            pct = []
            for metric in METRIC_DEFINITIONS:
                pts, mx = row.get(metric["score_col"]), row.get(metric["max_col"])
                if pts is not None and pd.notna(pts) and mx:
                    pct.append({"Metric": metric["label"], "% of max": pts / mx * 100})
            fig = px.bar(pd.DataFrame(pct), x="% of max", y="Metric", orientation="h",
                         range_x=[0, 100], title="Points earned (% of max, available metrics only)")
            fig.update_layout(margin=dict(t=50, b=10), height=400)
            st.plotly_chart(fig, width="stretch")
        st.markdown("#### 52-week range")
        lo, hi, pos = row.get("52W Low"), row.get("52W High"), row.get("52W Position %")
        if pd.notna(pos):
            st.progress(min(max(float(pos) / 100, 0.0), 1.0),
                        text=f"{pos:.0f}% of the way from {FORMATS['52W Low'](lo)} to {FORMATS['52W High'](hi)}")
        else:
            st.caption(f"52-week range: {NOT_AVAILABLE}")


def _render_excluded(disqualified: pd.DataFrame, unavailable: pd.DataFrame, key_prefix: str) -> None:
    st.subheader("Disqualified by hard filters")
    st.caption(
        "Hard filters are only applied when the underlying value exists: current ratio < 0.8 (non-financials), "
        "negative trailing ROE, D/E > 3.0x (non-financials), or negative free cash flow together with a negative "
        "operating margin."
    )
    if disqualified.empty:
        st.info("No stocks were disqualified.")
    else:
        cols = [c for c in ["Ticker", "Name", "Sector", "Reason", "Data As Of"] if c in disqualified.columns]
        st.dataframe(disqualified[cols], width="stretch", hide_index=True)
        st.download_button("Download disqualified (CSV)", csv_bytes(disqualified[cols]),
                           file_name=f"bac_sma_{key_prefix}_disqualified.csv", mime="text/csv",
                           key=f"{key_prefix}_dq_csv")

    st.subheader("Data not available")
    st.caption("In scope, but no fundamentals could be obtained, so they were not scored.")
    if unavailable.empty:
        st.info("Data was available for every stock in scope.")
    else:
        st.dataframe(unavailable, width="stretch", hide_index=True)
