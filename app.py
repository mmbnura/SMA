# app.py — NSE Value Finder  |  Streamlit multi-tab fundamental screener
# Run: streamlit run app.py

import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from screener import fetch_and_score, fetch_price_history, get_recommendation, REC_EMOJI
from tickers import NIFTY500_STOCKS, ALL_SECTORS

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NSE Value Finder",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Score pill */
.score-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 700;
    font-size: 0.85rem;
}
/* Score bar rows in Top Picks */
.bar-wrap {
    background: #2a2d3e;
    border-radius: 6px;
    height: 22px;
    width: 100%;
    overflow: hidden;
}
.bar-fill {
    height: 22px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    padding-left: 8px;
    font-size: 12px;
    font-weight: 700;
    color: #000;
}
/* Disclaimer banner */
.disclaimer {
    background: #1e2130;
    border-left: 4px solid #ff6d00;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    font-size: 0.8rem;
    color: #aaa;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "results_df" not in st.session_state:
    st.session_state.results_df = None
if "scan_time" not in st.session_state:
    st.session_state.scan_time = None

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 NSE Value Finder")
    st.caption("Fundamental screener for Nifty 500")
    st.divider()

    # Sector filter
    st.subheader("🗂️ Sector Filter")
    select_all = st.checkbox("Select All Sectors", value=True)
    if select_all:
        selected_sectors = ALL_SECTORS
    else:
        selected_sectors = st.multiselect(
            "Choose sectors",
            ALL_SECTORS,
            default=["IT", "Banking", "FMCG", "Pharma"],
        )

    filtered_stocks = [(t, n, s) for t, n, s in NIFTY500_STOCKS if s in selected_sectors]
    st.info(f"**{len(filtered_stocks)}** stocks in scope")

    st.divider()

    # Scan button
    scan_btn = st.button("🔍 Run Scan", type="primary", use_container_width=True)
    if st.session_state.scan_time:
        st.caption(f"Last scan: {st.session_state.scan_time}")

    st.divider()

    # Filters (applied after scan)
    st.subheader("🎚️ Result Filters")
    min_score = st.slider("Min Score", 0, 100, 0, step=5)
    rec_filter = st.multiselect(
        "Recommendation",
        ["Strong Buy", "Buy", "Hold", "Avoid"],
        default=["Strong Buy", "Buy", "Hold", "Avoid"],
    )

    st.divider()
    st.markdown(
        '<div class="disclaimer">⚠️ <b>Disclaimer:</b> This app is for educational '
        "purposes only. It does not constitute SEBI-registered investment advice. "
        "Past fundamentals do not guarantee future returns. Always consult a "
        "qualified financial advisor before investing.</div>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("📈 NSE Value Finder")
st.caption(
    "Multi-factor fundamental screener · Scores stocks 0–100 on P/E, P/B, ROE, "
    "D/E, EPS Growth, Revenue Growth & Dividend Yield · Data via Yahoo Finance"
)

# ─────────────────────────────────────────────────────────────────────────────
# SCAN EXECUTION
# ─────────────────────────────────────────────────────────────────────────────
if scan_btn:
    if not filtered_stocks:
        st.error("No stocks selected. Please choose at least one sector.")
    else:
        results = []
        prog = st.progress(0, text="Starting scan…")
        status = st.empty()
        total = len(filtered_stocks)

        for i, (ticker, name, sector) in enumerate(filtered_stocks):
            status.markdown(f"⏳ Fetching **{name}** ({i + 1}/{total})…")
            prog.progress((i + 1) / total, text=f"{i+1}/{total} stocks")
            result = fetch_and_score(ticker, name, sector)
            if result:
                results.append(result)
            time.sleep(0.05)      # gentle rate limiting

        prog.empty()
        status.empty()

        if results:
            st.session_state.results_df = pd.DataFrame(results)
            st.session_state.scan_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
            st.success(
                f"✅ Scan complete — fetched data for **{len(results)}** of "
                f"{total} stocks. {total - len(results)} skipped (no data)."
            )
        else:
            st.error("Could not fetch data for any stock. Check your internet connection.")

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.results_df is not None:
    df_all = st.session_state.results_df.copy()

    # Apply sidebar filters
    df = df_all[
        (df_all["Score"] >= min_score) &
        (df_all["Recommendation"].isin(rec_filter))
    ].sort_values("Score", ascending=False).reset_index(drop=True)

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 Dashboard", "📋 Screener", "🏆 Top Picks", "🔍 Deep Dive"]
    )

    # ── TAB 1 : DASHBOARD ────────────────────────────────────────────────────
    with tab1:
        # KPI row
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("📦 Stocks Scanned", len(df_all))
        c2.metric("🟢 Strong Buy",     len(df_all[df_all["Recommendation"] == "Strong Buy"]))
        c3.metric("🟡 Buy",            len(df_all[df_all["Recommendation"] == "Buy"]))
        c4.metric("🟠 Hold",           len(df_all[df_all["Recommendation"] == "Hold"]))
        c5.metric("🔴 Avoid",          len(df_all[df_all["Recommendation"] == "Avoid"]))

        st.divider()
        col_l, col_r = st.columns(2)

        # Pie: recommendation distribution
        with col_l:
            rec_counts = df_all["Recommendation"].value_counts().reset_index()
            rec_counts.columns = ["Recommendation", "Count"]
            colour_map = {
                "Strong Buy": "#00c853",
                "Buy":        "#ffd600",
                "Hold":       "#ff6d00",
                "Avoid":      "#d50000",
            }
            fig_pie = px.pie(
                rec_counts, values="Count", names="Recommendation",
                title="Recommendation Distribution",
                color="Recommendation", color_discrete_map=colour_map,
                hole=0.4,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(showlegend=False, margin=dict(t=50, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

        # Bar: average score per sector
        with col_r:
            sec_avg = (
                df_all.groupby("Sector")["Score"]
                .mean()
                .round(1)
                .sort_values(ascending=True)
                .reset_index()
            )
            fig_bar = px.bar(
                sec_avg, y="Sector", x="Score", orientation="h",
                title="Average Score by Sector",
                color="Score", color_continuous_scale="RdYlGn",
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

        # Histogram: score distribution
        fig_hist = px.histogram(
            df_all, x="Score", nbins=20,
            title="Score Distribution Across All Scanned Stocks",
            color_discrete_sequence=["#1f77b4"],
        )
        for cutoff, clr, lbl in [
            (75, "#00c853", "Strong Buy ≥75"),
            (60, "#ffd600", "Buy ≥60"),
            (45, "#ff6d00", "Hold ≥45"),
        ]:
            fig_hist.add_vline(
                x=cutoff, line_dash="dash", line_color=clr,
                annotation_text=lbl, annotation_position="top right",
            )
        fig_hist.update_layout(margin=dict(t=50, b=10))
        st.plotly_chart(fig_hist, use_container_width=True)

        # Scoring legend table
        with st.expander("ℹ️ How Scoring Works"):
            st.markdown("""
| Metric | Max Pts | Ideal | Notes |
|--------|---------|-------|-------|
| P/E Ratio | **20** | < 15 | Lower = cheaper relative to earnings |
| P/B Ratio | **15** | < 2 | Measures price vs book value |
| ROE | **20** | > 25% | Capital efficiency |
| Debt / Equity | **15** | < 0.5× | Financial safety; skipped for banks |
| EPS Growth | **15** | > 20% YoY | Earnings momentum |
| Revenue Growth | **10** | > 15% YoY | Business growth |
| Dividend Yield | **5** | > 2% | Income generation |
| **Total** | **100** | | |

**Thresholds:** 🟢 Strong Buy ≥ 75 · 🟡 Buy ≥ 60 · 🟠 Hold ≥ 45 · 🔴 Avoid < 45
            """)

    # ── TAB 2 : SCREENER TABLE ────────────────────────────────────────────────
    with tab2:
        st.subheader(f"Screener Results — {len(df)} stocks")

        DISPLAY_COLS = [
            "Ticker", "Name", "Sector", "Price (₹)", "Cap Bucket",
            "Score", "Recommendation",
            "P/E", "P/B", "ROE", "D/E", "EPS Growth", "Rev Growth", "Div Yield",
            "52W Position",
        ]

        st.dataframe(
            df[DISPLAY_COLS],
            use_container_width=True,
            height=600,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%d"
                ),
                "52W Position": st.column_config.ProgressColumn(
                    "52W Position", min_value=0, max_value=100, format="%.0f%%",
                    help="How close to 52-week high (100% = at 52W high)"
                ),
                "Recommendation": st.column_config.TextColumn("Signal"),
                "Price (₹)": st.column_config.NumberColumn("Price (₹)", format="₹%.2f"),
            },
            hide_index=True,
        )

        # Download
        csv = df[DISPLAY_COLS].to_csv(index=False)
        st.download_button(
            "📥 Download Results as CSV",
            data=csv,
            file_name=f"nse_value_finder_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    # ── TAB 3 : TOP PICKS ─────────────────────────────────────────────────────
    with tab3:
        st.subheader("🏆 Top 20 Value Picks")

        top20 = df_all.sort_values("Score", ascending=False).head(20)

        for _, row in top20.iterrows():
            ca, cb, cc = st.columns([3, 5, 2])
            with ca:
                emoji = REC_EMOJI.get(row["Recommendation"], "")
                st.markdown(f"{emoji} **{row['Name']}**")
                st.caption(f"{row['Ticker']} · {row['Sector']}")

            with cb:
                sc = int(row["Score"])
                clr = row["Colour"]
                st.markdown(
                    f'<div class="bar-wrap">'
                    f'<div class="bar-fill" style="width:{sc}%; background:{clr};">'
                    f"{sc}/100"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

            with cc:
                price = row["Price (₹)"]
                st.markdown(
                    f"**₹{price:,.2f}**" if price else "N/A"
                )
                st.caption(row["Recommendation"])

            st.divider()

    # ── TAB 4 : DEEP DIVE ─────────────────────────────────────────────────────
    with tab4:
        st.subheader("🔍 Stock Deep Dive")

        ticker_list = df_all["Ticker"].tolist()
        selected_base = st.selectbox(
            "Select a stock",
            ticker_list,
            format_func=lambda x: (
                f"{x}  —  {df_all.loc[df_all['Ticker']==x, 'Name'].values[0]}"
            ),
        )

        if selected_base:
            row = df_all[df_all["Ticker"] == selected_base].iloc[0]
            full_ticker = selected_base + ".NS"
            emoji = REC_EMOJI.get(row["Recommendation"], "")

            # Header
            st.markdown(f"## {emoji} {row['Name']}  `{selected_base}`")
            h1, h2, h3, h4, h5 = st.columns(5)
            h1.metric("Price",          f"₹{row['Price (₹)']:,.2f}" if row["Price (₹)"] else "N/A")
            h2.metric("Score",          f"{row['Score']}/100")
            h3.metric("Signal",         row["Recommendation"])
            h4.metric("Sector",         row["Sector"])
            h5.metric("Market Cap",     row["Cap Bucket"])

            st.divider()

            # ── Price chart
            with st.spinner("Loading 1-year price chart…"):
                hist = fetch_price_history(full_ticker)
                if not hist.empty and "Close" in hist.columns:
                    close = hist["Close"].squeeze()
                    ma50  = close.rolling(50).mean()
                    ma20  = close.rolling(20).mean()

                    fig_p = go.Figure()
                    fig_p.add_trace(go.Scatter(
                        x=hist.index, y=close,
                        name="Close", mode="lines",
                        line=dict(color="#4c9be8", width=2),
                    ))
                    fig_p.add_trace(go.Scatter(
                        x=hist.index, y=ma50,
                        name="50-Day MA", mode="lines",
                        line=dict(color="#ffd600", width=1.5, dash="dash"),
                    ))
                    fig_p.add_trace(go.Scatter(
                        x=hist.index, y=ma20,
                        name="20-Day MA", mode="lines",
                        line=dict(color="#ff6d00", width=1.5, dash="dot"),
                    ))
                    fig_p.update_layout(
                        title=f"{row['Name']} — 1 Year Price Chart",
                        xaxis_title="Date",
                        yaxis_title="Price (₹)",
                        hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02),
                        margin=dict(t=60, b=20),
                    )
                    st.plotly_chart(fig_p, use_container_width=True)
                else:
                    st.warning("Price chart not available for this ticker.")

            st.divider()
            left, right = st.columns(2)

            # ── Radar chart
            with left:
                categories = ["P/E", "P/B", "ROE", "D/E", "EPS Growth", "Rev Growth", "Div Yield"]
                scores     = [row["s_PE"], row["s_PB"], row["s_ROE"],
                              row["s_DE"], row["s_EPS"], row["s_Rev"], row["s_Div"]]
                max_pts    = [20, 15, 20, 15, 15, 10, 5]
                pct        = [s / m * 100 for s, m in zip(scores, max_pts)]

                fig_r = go.Figure(go.Scatterpolar(
                    r=pct + [pct[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    fillcolor="rgba(76,155,232,0.25)",
                    line=dict(color="#4c9be8", width=2),
                    name="Score %",
                ))
                fig_r.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    title="Score Breakdown (% of max per metric)",
                    margin=dict(t=60, b=20),
                )
                st.plotly_chart(fig_r, use_container_width=True)

            # ── Metrics table
            with right:
                st.markdown("#### Fundamental Metrics")
                metrics_df = pd.DataFrame({
                    "Metric":     categories,
                    "Value":      [row[c] for c in ["P/E", "P/B", "ROE", "D/E",
                                                     "EPS Growth", "Rev Growth", "Div Yield"]],
                    "Score":      [f"{s}/{m}" for s, m in zip(scores, max_pts)],
                    "Weight":     [f"{m} pts" for m in max_pts],
                })
                st.dataframe(
                    metrics_df,
                    use_container_width=True,
                    hide_index=True,
                    height=280,
                    column_config={
                        "Score": st.column_config.TextColumn("Score"),
                    },
                )

                # 52-week gauge
                if row["52W Position"] is not None:
                    st.markdown("#### 52-Week Price Position")
                    w52 = float(row["52W Position"])
                    fig_g = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=w52,
                        number={"suffix": "%"},
                        gauge={
                            "axis": {"range": [0, 100]},
                            "bar":  {"color": "#4c9be8"},
                            "steps": [
                                {"range": [0,  33], "color": "#00c85340"},
                                {"range": [33, 66], "color": "#ffd60030"},
                                {"range": [66, 100],"color": "#d5000030"},
                            ],
                        },
                        title={"text": "Near 52W Low (0%) → 52W High (100%)"},
                    ))
                    fig_g.update_layout(height=220, margin=dict(t=40, b=10))
                    st.plotly_chart(fig_g, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# PRE-SCAN WELCOME SCREEN
# ─────────────────────────────────────────────────────────────────────────────
else:
    st.info("👈 Select sectors in the sidebar and click **Run Scan** to begin.")

    st.markdown("---")
    cols = st.columns(3)

    with cols[0]:
        st.markdown("### 🎯 What It Does")
        st.markdown("""
- Scans up to **160 Nifty 500 stocks**
- Scores each on **7 fundamental criteria**
- Ranks and recommends: Strong Buy / Buy / Hold / Avoid
- Shows sector-level insights
        """)

    with cols[1]:
        st.markdown("### 📐 Scoring Model")
        st.markdown("""
| Metric | Weight |
|---|---|
| P/E Ratio | 20 pts |
| ROE | 20 pts |
| D/E Ratio | 15 pts |
| P/B Ratio | 15 pts |
| EPS Growth | 15 pts |
| Revenue Growth | 10 pts |
| Dividend Yield | 5 pts |
| **Total** | **100** |
        """)

    with cols[2]:
        st.markdown("### ⏱️ Tips")
        st.markdown("""
- Scanning all 160 stocks takes ~3–4 min
- Use **Sector Filter** to scan a subset quickly
- Results are your **research shortlist**, not buy orders
- Always read the company's annual report before investing
        """)

    st.markdown("---")
    st.markdown(
        '<div class="disclaimer">⚠️ <b>Disclaimer:</b> This tool is for educational '
        "purposes only and does not constitute investment advice. Scores are based on "
        "trailing fundamentals from Yahoo Finance which may be delayed or incomplete. "
        "The developer is not a SEBI-registered advisor. Do your own due diligence.</div>",
        unsafe_allow_html=True,
    )
