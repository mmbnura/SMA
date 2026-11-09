def run():
    import json

    import pandas as pd
    import streamlit as st

    from core.screening_logic import (
        METRIC_DEFINITIONS,
        SCREENING_CONFIG_PATH,
        get_default_config,
        load_screening_config,
        metric_lookup,
        save_screening_config,
        validate_thresholds,
    )
    from screens.components import page_setup, sidebar_disclaimer

    page_setup("Screening Logic", "Screening logic")

    def seed(config: dict) -> None:
        lookup = metric_lookup(config)
        for metric in METRIC_DEFINITIONS:
            item = lookup.get(metric["id"], {})
            st.session_state[f"logic_enabled_{metric['id']}"] = bool(item.get("enabled", True))
            st.session_state[f"logic_weight_{metric['id']}"] = float(item.get("weight", metric["base_max"]))
        for key, value in config["recommendation_thresholds"].items():
            st.session_state[f"logic_thr_{key}"] = int(value)
        st.session_state["logic_min_cov"] = int(config["min_data_coverage"])
        st.session_state.logic_seeded = True

    # Streamlit drops widget keys after navigating to another page, so re-seed if any are gone.
    widget_keys = [f"logic_{kind}_{m['id']}" for m in METRIC_DEFINITIONS for kind in ("enabled", "weight")]
    widget_keys += ["logic_thr_strong_buy", "logic_thr_buy", "logic_thr_hold", "logic_min_cov"]
    if not st.session_state.get("logic_seeded") or any(k not in st.session_state for k in widget_keys):
        seed(load_screening_config())

    st.title("Screening Logic")
    st.caption(
        "Weights are relative: the final score is points earned divided by the weight of the metrics that have data, "
        "scaled to 100. Changes apply to the next scan; saved scans keep the settings they were run with."
    )
    if st.session_state.pop("logic_flash", None):
        st.success(st.session_state.pop("logic_flash_msg", "Saved."))

    st.subheader("Metrics")
    header = st.columns([2.2, 1, 1.4, 1.2, 1])
    for col, text in zip(header, ["Metric", "Enabled", "Weight", "Share of score", "Default"]):
        col.markdown(f"**{text}**")

    total = sum(
        st.session_state[f"logic_weight_{m['id']}"]
        for m in METRIC_DEFINITIONS
        if st.session_state[f"logic_enabled_{m['id']}"]
    )
    for metric in METRIC_DEFINITIONS:
        mid = metric["id"]
        row = st.columns([2.2, 1, 1.4, 1.2, 1])
        with row[0]:
            st.markdown(f"**{metric['label']}**", help=f"{metric['description']}\n\nScoring: {metric['good_range']}\n\nSource: {metric['source']}")
        row[1].checkbox("Enabled", key=f"logic_enabled_{mid}", label_visibility="collapsed")
        row[2].number_input(
            "Weight", min_value=0.0, max_value=100.0, step=0.5,
            key=f"logic_weight_{mid}", label_visibility="collapsed",
        )
        enabled = st.session_state[f"logic_enabled_{mid}"]
        weight = st.session_state[f"logic_weight_{mid}"]
        share = weight / total * 100 if enabled and total > 0 else 0
        row[3].write(f"{share:.1f}%" if enabled else "Disabled")
        row[4].write(f"{metric['base_max']:g}")

    if total <= 0:
        st.error("All metrics are disabled or have zero weight. Every stock would be rated Insufficient Data.")

    with st.expander("How each metric is scored and where the data comes from"):
        st.dataframe(
            pd.DataFrame([
                {"Metric": m["label"], "Scoring": m["good_range"], "Source": m["source"], "Description": m["description"]}
                for m in METRIC_DEFINITIONS
            ]),
            width="stretch", hide_index=True,
        )

    st.subheader("Recommendation thresholds")
    t = st.columns(3)
    t[0].number_input("Strong Buy at or above", 0, 100, step=1, key="logic_thr_strong_buy")
    t[1].number_input("Buy at or above", 0, 100, step=1, key="logic_thr_buy")
    t[2].number_input("Hold at or above", 0, 100, step=1, key="logic_thr_hold")
    thresholds = {k: st.session_state[f"logic_thr_{k}"] for k in ("strong_buy", "buy", "hold")}
    _, thr_error = validate_thresholds(thresholds)
    if thr_error:
        st.error(thr_error)
    else:
        st.caption(f"Scores below {thresholds['hold']} are rated Avoid.")

    st.subheader("Minimum data coverage")
    st.slider(
        "Rate a stock only if at least this share of the scoring weight has real data (%)",
        0, 100, step=5, key="logic_min_cov",
    )
    st.caption(
        "Stocks below this coverage are labelled 'Insufficient Data' instead of receiving a recommendation. "
        "Their partial score is still shown."
    )

    st.divider()
    b = st.columns(2)
    with b[0]:
        if st.button("Save", type="primary", width="stretch", disabled=bool(thr_error)):
            config = {
                "metrics": [
                    {
                        "id": m["id"],
                        "enabled": st.session_state[f"logic_enabled_{m['id']}"],
                        "weight": st.session_state[f"logic_weight_{m['id']}"],
                    }
                    for m in METRIC_DEFINITIONS
                ],
                "recommendation_thresholds": thresholds,
                "min_data_coverage": st.session_state["logic_min_cov"],
            }
            save_screening_config(config)
            st.session_state.logic_flash = True
            st.session_state.logic_flash_msg = f"Saved to {SCREENING_CONFIG_PATH.name}."
            st.session_state.logic_seeded = False
            st.rerun()
    with b[1]:
        if st.button("Reset to defaults", width="stretch"):
            save_screening_config(get_default_config())
            st.session_state.logic_flash = True
            st.session_state.logic_flash_msg = "Default screening logic restored."
            st.session_state.logic_seeded = False
            st.rerun()

    with st.expander("Saved configuration (JSON)"):
        st.caption(f"Path: {SCREENING_CONFIG_PATH}")
        st.code(json.dumps(load_screening_config(), indent=2), language="json")

    sidebar_disclaimer()


if __name__ == "__main__":
    run()
