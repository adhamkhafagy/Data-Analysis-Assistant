import streamlit as st
import pandas as pd
from utils import show_dataset_info


# ---------- Agent 3: Review & Fix Approval ----------
# Displays every issue Agent 2 found as a checkbox, lets the user pick which
# ones to fix, executes the approved fixes on the dataframe, then hands off
# to Agent 4 (the analyst) with the cleaned dataframe.
def render():
    st.header("Step 3: Review & Fix Data Issues")

    issues = st.session_state.quality_issues

    # Tracks whether fixes have already been applied this round, so the
    # "Continue" button stays visible across reruns instead of disappearing
    # the moment the "Apply" button's one-shot True value resets
    if "fixes_applied" not in st.session_state:
        st.session_state.fixes_applied = False

    # Nothing was found by the scan — nothing to review, move straight on
    if not issues:
        st.success("No data quality issues were found.")
        if st.button("Continue →", key="no_issues_continue"):
            st.session_state.stage = "analyst"
            st.rerun()
        return

    st.write(f"Found **{len(issues)}** issue type(s). Select which ones you'd like to fix:")

    severity_icon = {"high": "🔴", "medium": "🟠", "low": "🟡"}
    selected_indices = []

    # One checkbox + expandable detail per issue, pre-checked by default
    for i, issue in enumerate(issues):
        icon = severity_icon.get(issue.get("severity", "low"), "🟡")
        cols_str = ", ".join(issue.get("affected_columns", [])) or "N/A"
        label = f"{icon} {issue['issue_type']} — {cols_str}"

        checked = st.checkbox(label, value=True, key=f"issue_{i}")
        if checked:
            selected_indices.append(i)

        with st.expander("Details"):
            st.write(issue["explanation"])
            st.code(issue["fix_code"], language="python")

    col1, col2 = st.columns(2)

    # Apply only the fixes the user left checked
    with col1:
        if st.button("✅ Apply Selected Fixes"):
            df = st.session_state.df.copy()
            errors = []
            for i in selected_indices:
                try:
                    # Each fix_code snippet operates on a local variable `df`
                    local_ns = {"df": df, "pd": pd}
                    exec(issues[i]["fix_code"], {"pd": pd}, local_ns)
                    df = local_ns["df"]
                except Exception as e:
                    errors.append(f"{issues[i]['issue_type']}: {e}")

            st.session_state.df = df
            st.session_state.fix_errors = errors
            st.session_state.fixes_applied = True
            st.session_state.data_was_cleaned = True

    # Skip fixing entirely and proceed with the data as-is
    with col2:
        if st.button("⏭️ Skip All Fixes"):
            st.session_state.stage = "analyst"
            st.rerun()

    # Shown after fixes are applied, and stays visible across reruns until
    # the user actually clicks Continue — independent of the Apply button above
    if st.session_state.fixes_applied:
        errors = st.session_state.get("fix_errors", [])
        if errors:
            st.warning("Some fixes could not be applied:\n" + "\n".join(errors))
        else:
            st.success("Fixes applied successfully.")

        show_dataset_info(st.session_state.df, "After Fixes")
        if st.button("Continue →", key="fixed_continue"):
            st.session_state.stage = "analyst"
            st.session_state.fixes_applied = False
            st.rerun()
