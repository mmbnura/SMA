def run():
    import pandas as pd
    import streamlit as st
    
    from core.scan_history import get_scan_run, init_db, list_scan_runs, load_scan_results
    
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
    
    
    st.set_page_config(
        page_title="BAC SMA - History",
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
    
    init_db()
    
    with st.sidebar:
        st.title("BAC SMA")
        st.caption("Scan History")
        st.page_link("app.py", label="Screener")
        st.page_link("pages/History.py", label="History")
        st.page_link("pages/Screening_Logic.py", label="Screening Logic")
    st.title("Scan History")
    st.caption("Browse previous scans saved in the local database.")
    
    history_df = list_scan_runs(limit=500)
    if history_df.empty:
        st.info("No scan history found yet. Run a scan from the Screener page first.")
        st.stop()
    
    list_df = history_df[
        ["scan_id", "scan_type", "created_at", "total_scored", "total_in_scope", "sector_count"]
    ].rename(
        columns={
            "scan_id": "Scan ID",
            "scan_type": "Type",
            "created_at": "Created At",
            "total_scored": "Scored",
            "total_in_scope": "In Scope",
            "sector_count": "Sector Count",
        }
    )
    
    st.subheader("Previous Scans")
    scan_ids = history_df["scan_id"].tolist()
    
    if "history_selected_scan_id" not in st.session_state:
        st.session_state.history_selected_scan_id = scan_ids[0]
    elif st.session_state.history_selected_scan_id not in scan_ids:
        st.session_state.history_selected_scan_id = scan_ids[0]
    
    selected_scan_id = st.session_state.history_selected_scan_id
    
    try:
        table_event = st.dataframe(
            list_df,
            use_container_width=True,
            hide_index=True,
            height=300,
            on_select="rerun",
            selection_mode="single-row",
            key="history_scan_table",
        )
        selected_rows = table_event.selection.rows if table_event and table_event.selection else []
        if selected_rows:
            selected_scan_id = list_df.iloc[selected_rows[0]]["Scan ID"]
            st.session_state.history_selected_scan_id = selected_scan_id
    except TypeError:
        st.dataframe(list_df, use_container_width=True, hide_index=True, height=300)
        selected_scan_id = st.selectbox(
            "Select a scan",
            scan_ids,
            index=scan_ids.index(st.session_state.history_selected_scan_id),
        )
        st.session_state.history_selected_scan_id = selected_scan_id
    
    meta = get_scan_run(selected_scan_id)
    results_df = normalize_columns(load_scan_results(selected_scan_id))
    
    if meta:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Scan Type", meta["scan_type"])
        c2.metric("Created At", meta["created_at"])
        c3.metric("Scored", int(meta["total_scored"]))
        c4.metric("In Scope", int(meta["total_in_scope"]))
        if meta["selected_sectors"]:
            st.caption("Sectors: " + ", ".join(meta["selected_sectors"]))
    
    st.divider()
    st.subheader(f"Results for {selected_scan_id}")
    
    if results_df.empty:
        st.warning("This scan has no saved stock results.")
    else:
        min_score = st.slider("Min Score", 0, 100, 0, step=5, key="hist_min_score")
        rec_filter = st.multiselect(
            "Recommendation",
            ["Strong Buy", "Buy", "Hold", "Avoid"],
            default=["Strong Buy", "Buy", "Hold", "Avoid"],
            key="hist_rec_filter",
        )
        filtered_df = results_df[
            (results_df["Score"] >= min_score) & (results_df["Recommendation"].isin(rec_filter))
        ].sort_values("Score", ascending=False)
    
        st.dataframe(
            filtered_df[DISPLAY_COLS],
            use_container_width=True,
            hide_index=True,
            height=600,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
                "52W Position": st.column_config.ProgressColumn(
                    "52W Position", min_value=0, max_value=100, format="%.0f%%"
                ),
                "Price (Rs)": st.column_config.NumberColumn("Price (Rs)", format="%.2f"),
            },
        )
    
    

if __name__ == '__main__':
    run()

