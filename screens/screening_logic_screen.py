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
            st.session_state[f"logic_select_{metric_id}"] = False
    
    
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
    st.caption("Select rows to edit parameters, adjust weights, and enable/disable metrics. Settings are saved to JSON.")
    if st.session_state.pop("logic_reset_done", False):
        st.success("Default screening logic restored.")
    
    # Build table data
    config_lookup = metric_lookup(current_config)
    table_data = []
    for metric in METRIC_DEFINITIONS:
        metric_id = metric["id"]
        item = config_lookup.get(metric_id, {})
        table_data.append({
            "metric_id": metric_id,
            "Parameter": metric["label"],
            "Default Value": f"{metric['base_max']}",
            "Current Weight": float(item.get("weight", float(metric["base_max"]))),
            "Explanation": metric.get('description', 'N/A'),
            "Good Range": metric.get('good_range', 'N/A'),
            "Enabled": bool(item.get("enabled", True)),
        })
    
    st.subheader("Parameters Table")
    
    # Display table with selection and editing
    col_select, col_param, col_default, col_weight, col_enabled = st.columns([0.5, 1.5, 1, 1.5, 1])
    
    with col_select:
        st.write("**Select**")
    with col_param:
        st.write("**Parameter**")
    with col_default:
        st.write("**Default**")
    with col_weight:
        st.write("**Current Weight**")
    with col_enabled:
        st.write("**Enabled**")
    
    st.divider()
    
    for row in table_data:
        metric_id = row["metric_id"]
        col_select, col_param, col_default, col_weight, col_enabled = st.columns([0.5, 1.5, 1, 1.5, 1])
        
        with col_select:
            st.checkbox(
                "Select",
                key=f"logic_select_{metric_id}",
                label_visibility="collapsed"
            )
        
        with col_param:
            st.write(row["Parameter"])
        
        with col_default:
            st.write(row["Default Value"])
        
        with col_weight:
            st.number_input(
                "Weight",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                key=f"logic_weight_{metric_id}",
                label_visibility="collapsed",
            )
        
        with col_enabled:
            st.checkbox(
                "Enabled",
                key=f"logic_enabled_{metric_id}",
                label_visibility="collapsed"
            )
    
    st.divider()
    
    # Show details for selected rows
    selected_metrics = [
        row for row in table_data 
        if st.session_state.get(f"logic_select_{row['metric_id']}", False)
    ]
    
    if selected_metrics:
        st.subheader(f"Edit Selected Rows ({len(selected_metrics)} selected)")
        
        for row in selected_metrics:
            metric_id = row["metric_id"]
            with st.expander(f"📝 {row['Parameter']}"):
                st.write(f"**Explanation:** {row['Explanation']}")
                st.write(f"**Good Range:** {row['Good Range']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    new_weight = st.number_input(
                        f"Update Weight for {row['Parameter']}",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.5,
                        value=st.session_state.get(f"logic_weight_{metric_id}", row["Current Weight"]),
                        key=f"edit_weight_{metric_id}",
                        help="Higher weight gives this metric more influence in the final score."
                    )
                    # Sync back to main table
                    st.session_state[f"logic_weight_{metric_id}"] = new_weight
                
                with col2:
                    enabled = st.checkbox(
                        f"Enable {row['Parameter']}",
                        value=st.session_state.get(f"logic_enabled_{metric_id}", row["Enabled"]),
                        key=f"edit_enabled_{metric_id}",
                    )
                    # Sync back to main table
                    st.session_state[f"logic_enabled_{metric_id}"] = enabled
    
    st.divider()
    
    # Action buttons
    btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 2])
    
    with btn_col1:
        if st.button("💾 Save Screening Logic", type="primary", use_container_width=True):
            save_screening_config(_build_updated_config())
            st.success(f"✅ Saved to {SCREENING_CONFIG_PATH.name}")
    
    with btn_col2:
        if st.button("🔄 Reset to Default", use_container_width=True):
            save_screening_config(get_default_config())
            st.session_state.logic_widgets_seeded = False
            st.session_state.logic_reset_done = True
            st.rerun()
    
    with btn_col3:
        if st.button("✨ Clear Selection", use_container_width=True):
            for metric in METRIC_DEFINITIONS:
                st.session_state[f"logic_select_{metric['id']}"] = False
            st.rerun()
    
    st.subheader("Current Configuration (JSON)")
    st.caption(f"Path: {SCREENING_CONFIG_PATH}")
    st.code(json.dumps(load_screening_config(), indent=2), language="json")
    
    

if __name__ == '__main__':
    run()

