def run():
    import json
    
    import streamlit as st
    
    from core.screening_logic import (
        METRIC_DEFINITIONS,
        SCREENING_CONFIG_PATH,
        get_default_config,
        load_screening_config,
        metric_lookup,
        save_screening_config,
    )
    
    
    def _build_updated_config() -> dict:
        current = load_screening_config()
        current_lookup = metric_lookup(current)
    
        updated_metrics = []
        for metric in METRIC_DEFINITIONS:
            metric_id = metric["id"]
            metric_state = current_lookup.get(metric_id, {})
            updated_metrics.append(
                {
                    "id": metric_id,
                    "label": metric["label"],
                    "enabled": st.session_state.get(f"logic_enabled_{metric_id}", metric_state.get("enabled", True)),
                    "weight": float(
                        st.session_state.get(
                            f"logic_weight_{metric_id}",
                            metric_state.get("weight", float(metric["base_max"])),
                        )
                    ),
                    "base_max": float(metric["base_max"]),
                }
            )
    
        return {
            "version": current.get("version", 1),
            "metrics": updated_metrics,
            "recommendation_thresholds": current.get("recommendation_thresholds", {}),
        }
    
    
    def _seed_widgets_from_config(config: dict) -> None:
        config_lookup = metric_lookup(config)
        for metric in METRIC_DEFINITIONS:
            metric_id = metric["id"]
            item = config_lookup.get(metric_id, {})
            st.session_state[f"logic_enabled_{metric_id}"] = bool(item.get("enabled", True))
            st.session_state[f"logic_weight_{metric_id}"] = float(item.get("weight", float(metric["base_max"])))
    
    
    st.set_page_config(
        page_title="BAC SMA - Screening Logic",
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
        st.caption("Screening Logic")
        st.page_link("app.py", label="Screener")
        st.page_link("pages/History.py", label="History")
        st.page_link("pages/Screening_Logic.py", label="Screening Logic")
    
    current_config = load_screening_config()
    
    if "logic_widgets_seeded" not in st.session_state:
        _seed_widgets_from_config(current_config)
        st.session_state.logic_widgets_seeded = True
    
    st.title("Screening Logic Settings")
    st.caption("Enable or disable each parameter and adjust its weight. Settings are saved to JSON.")
    if st.session_state.pop("logic_reset_done", False):
        st.success("Default screening logic restored.")
    
    st.subheader("Parameter Controls")
    for metric in METRIC_DEFINITIONS:
        metric_id = metric["id"]
        base_max = float(metric["base_max"])
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            st.checkbox(metric["label"], key=f"logic_enabled_{metric_id}")
        with c2:
            st.number_input(
                f"Weight - {metric['label']}",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                key=f"logic_weight_{metric_id}",
                help="Higher weight gives this metric more influence in the final score.",
            )
        with c3:
            st.caption(f"Default weight: {base_max:g}")
        st.divider()
    
    btn_col1, btn_col2 = st.columns([2, 2])
    with btn_col1:
        if st.button("Save Screening Logic", type="primary", use_container_width=True):
            save_screening_config(_build_updated_config())
            st.success(f"Saved to {SCREENING_CONFIG_PATH.name}")
    
    with btn_col2:
        if st.button("Reset to Default", use_container_width=True):
            save_screening_config(get_default_config())
            st.session_state.logic_widgets_seeded = False
            st.session_state.logic_reset_done = True
            st.rerun()
    
    st.subheader("Current JSON")
    st.caption(f"Path: {SCREENING_CONFIG_PATH}")
    st.code(json.dumps(load_screening_config(), indent=2), language="json")
    
    

if __name__ == '__main__':
    run()

