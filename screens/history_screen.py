def run():
    import pandas as pd
    import streamlit as st

    from core.scan_history import delete_scan_run, get_scan_run, init_db, list_scan_runs, load_scan_results
    from core.timeutil import parse_timestamp
    from screens.components import page_setup, render_results, result_filters, sidebar_disclaimer, styled

    def fmt_created(value) -> str:
        ts = parse_timestamp(value)
        return f"{ts:%d %b %Y %H:%M}" if ts else str(value)

    page_setup("History", "Scan history")
    init_db()

    st.title("Scan History")
    st.caption("Every completed scan is stored locally. Select a scan to review it.")

    history = list_scan_runs(limit=500)
    if history.empty:
        st.info("No scans yet. Run a scan from the Screener page first.")
        sidebar_disclaimer()
        st.stop()

    legacy = history["total_disqualified"].isna()
    table = pd.DataFrame({
        "Scan ID": history["scan_id"],
        "Type": history["scan_type"],
        "Created At": history["created_at"].map(fmt_created),
        # Older versions stored the scored count as "in scope", so it is not shown for them.
        "In Scope": history["total_in_scope"].where(~legacy),
        "Scored": history["total_scored"],
        "Disqualified": history["total_disqualified"],
        "Data Unavailable": history["total_unavailable"],
        "Sectors": history["sector_count"],
    })

    scan_ids = table["Scan ID"].tolist()
    if st.session_state.get("history_selected_scan_id") not in scan_ids:
        st.session_state.history_selected_scan_id = scan_ids[0]

    event = st.dataframe(
        styled(table, missing_text="Not recorded"),
        width="stretch",
        hide_index=True,
        height=300,
        on_select="rerun",
        selection_mode="single-row",
        key="history_scan_table",
    )
    if event and event.selection and event.selection.rows:
        st.session_state.history_selected_scan_id = table.iloc[event.selection.rows[0]]["Scan ID"]
    selected = st.session_state.history_selected_scan_id

    meta = get_scan_run(selected)
    if not meta:
        st.error(f"Scan {selected} could not be loaded.")
        st.stop()
    results = load_scan_results(selected)

    st.divider()
    st.subheader(f"Scan {selected}")
    c = st.columns(4)
    c[0].metric("Type", meta["scan_type"])
    c[1].metric("Created", fmt_created(meta["created_at"]))
    c[2].metric("Scored", int(meta["total_scored"]))
    c[3].metric("Sectors", len(meta["selected_sectors"]))
    if meta["selected_sectors"]:
        with st.expander("Sectors in this scan"):
            st.write(", ".join(meta["selected_sectors"]))

    if meta["is_legacy"]:
        st.warning(
            "This scan was saved by an earlier version of the app. That version scored missing data as 0 points, "
            "gave financial-sector stocks an assumed D/E score, did not record disqualified stocks or download "
            "failures, and did not record which settings were used. Its scores are not directly comparable with "
            "newer scans."
        )

    a, b, _ = st.columns([1, 1, 2])
    with a:
        if st.button("Verify accuracy", type="primary", width="stretch"):
            st.session_state.accuracy_scan_id = selected
            st.switch_page("pages/Accuracy_Verification.py")
    with b:
        if st.button("Delete this scan", width="stretch"):
            st.session_state.confirm_delete = selected
    if st.session_state.get("confirm_delete") == selected:
        st.warning(f"Permanently delete scan {selected}?")
        y, n, _ = st.columns([1, 1, 4])
        if y.button("Yes, delete"):
            delete_scan_run(selected)
            st.session_state.pop("confirm_delete", None)
            st.session_state.pop("history_selected_scan_id", None)
            st.rerun()
        if n.button("Cancel"):
            st.session_state.pop("confirm_delete", None)
            st.rerun()

    if results.empty and meta["disqualified"].empty:
        st.warning("This scan has no saved stock results.")
    else:
        with st.sidebar:
            st.subheader("Result filters")
            min_score, rec_filter = result_filters("hist")
        render_results(
            results,
            meta["disqualified"],
            meta["unavailable"],
            None if meta["is_legacy"] else meta["total_in_scope"],
            meta["config"],
            min_score,
            rec_filter,
            key_prefix=f"hist_{selected}",
        )

    sidebar_disclaimer()


if __name__ == "__main__":
    run()
