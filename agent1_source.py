import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from utils import DB_DRIVERS, SAMPLE_DATASETS, suggest_join_key, show_dataset_info


# ---------- Agent 1: Data Source ----------
# Lets the user choose where their data lives (upload, database, or sample),
# walks them through the relevant sub-flow (including multi-table merging),
# and hands off to Agent 2 once a final dataframe is ready in st.session_state.df
def render():
    st.header("Step 1: Where is your data?")

    # ----- Step 1: top-level source choice -----
    if st.session_state.source_substage == "choose_source":
        source_type = st.radio(
            "Choose an option",
            ["Upload a File", "Connect to a Database", "Use Sample Dataset"],
        )
        if st.button("Next →"):
            if source_type == "Upload a File":
                st.session_state.source_substage = "upload_type"
            elif source_type == "Connect to a Database":
                st.session_state.source_substage = "db_type"
            else:
                st.session_state.source_substage = "sample_pick"
            st.rerun()

    # ----- Sample dataset flow -----
    elif st.session_state.source_substage == "sample_pick":
        choice = st.selectbox("Choose a sample dataset", list(SAMPLE_DATASETS.keys()))
        if st.button("Load Sample"):
            st.session_state.df = pd.read_csv(SAMPLE_DATASETS[choice])
        if st.session_state.df is not None:
            show_dataset_info(st.session_state.df, choice)
            if st.button("Continue →", key="sample_continue"):
                st.session_state.stage = "quality_check"
                st.rerun()

    # ----- Upload flow: pick CSV / Excel / multiple files -----
    elif st.session_state.source_substage == "upload_type":
        upload_type = st.radio("Upload type", ["CSV", "Excel", "Multiple Files (select several to merge)"])

        # Single CSV file upload
        if upload_type == "CSV":
            uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])
            if uploaded_file:
                st.session_state.df = pd.read_csv(uploaded_file)
                show_dataset_info(st.session_state.df, uploaded_file.name)
                if st.button("Continue →"):
                    st.session_state.stage = "quality_check"
                    st.rerun()

        # Single Excel file upload
        elif upload_type == "Excel":
            uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])
            if uploaded_file:
                st.session_state.df = pd.read_excel(uploaded_file)
                show_dataset_info(st.session_state.df, uploaded_file.name)
                if st.button("Continue →"):
                    st.session_state.stage = "quality_check"
                    st.rerun()

        # Multiple files: browsers can't expose a real folder picker, so we let
        # the user select several files at once and choose which to merge
        else:
            st.caption("Note: browsers don't support real folder selection, so pick the files directly.")
            uploaded_files = st.file_uploader(
                "Select multiple files",
                type=["csv", "xlsx"],
                accept_multiple_files=True,
            )
            if uploaded_files:
                st.write(f"🔍 Scanning... found {len(uploaded_files)} file(s)")
                discovered = {}
                for f in uploaded_files:
                    try:
                        discovered[f.name] = pd.read_csv(f) if f.name.endswith(".csv") else pd.read_excel(f)
                    except Exception as e:
                        st.warning(f"Could not read {f.name}: {e}")

                if discovered:
                    st.success(f"Discovered {len(discovered)} dataset(s)")
                    for fname, fdf in discovered.items():
                        with st.expander(f"📄 {fname}"):
                            show_dataset_info(fdf, fname)

                    st.write("Select the dataset(s) you want to use:")
                    chosen = [name for name in discovered if st.checkbox(name, key=f"file_{name}")]

                    if chosen and st.button("Load Selected Dataset(s)"):
                        st.session_state.table_dfs = {name: discovered[name] for name in chosen}
                        if len(chosen) == 1:
                            # Single dataset: no merge needed, go straight to info
                            st.session_state.df = st.session_state.table_dfs[chosen[0]]
                            st.session_state.source_substage = "show_info"
                        else:
                            # Multiple datasets: enter the interactive pairwise merge flow
                            st.session_state.merge_pool = dict(st.session_state.table_dfs)
                            st.session_state.source_substage = "merge_pick_pair"
                        st.rerun()

    # ----- Step 2 (DB path): pick database type -----
    elif st.session_state.source_substage == "db_type":
        db_type = st.selectbox("Database Type", list(DB_DRIVERS.keys()))
        if st.button("Next →"):
            st.session_state.db_type = db_type
            st.session_state.source_substage = "db_connect"
            st.rerun()

    # ----- Step 3 (DB path): ask only for connection details -----
    elif st.session_state.source_substage == "db_connect":
        db_type = st.session_state.db_type
        st.write(f"Connecting to **{db_type}**")

        use_windows_auth = False

        if db_type == "SQLite":
            db_path = st.text_input("Path to .db file")
        elif db_type == "SQL Server":
            # SQL Server supports logging in with the current Windows account
            # instead of a SQL username/password (Trusted Connection)
            auth_mode = st.radio(
                "Authentication type",
                ["SQL Server Authentication", "Windows Authentication"],
            )
            use_windows_auth = auth_mode == "Windows Authentication"

            col1, col2 = st.columns(2)
            with col1:
                host = st.text_input("Host", value="localhost")
                port = st.text_input("Port", value=DB_DRIVERS[db_type]["default_port"])
                database = st.text_input("Database name")
            with col2:
                if not use_windows_auth:
                    user = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                else:
                    st.caption("No username/password needed — your Windows login will be used.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                host = st.text_input("Host", value="localhost")
                port = st.text_input("Port", value=DB_DRIVERS[db_type]["default_port"])
                database = st.text_input("Database name")
            with col2:
                user = st.text_input("Username")
                password = st.text_input("Password", type="password")

        if st.button("Connect"):
            try:
                driver = DB_DRIVERS[db_type]["driver"]
                if db_type == "SQLite":
                    conn_str = f"{driver}:///{db_path}"
                elif db_type == "SQL Server" and use_windows_auth:
                    # Trusted_Connection=yes tells the ODBC driver to use the
                    # current Windows session instead of a SQL login
                    conn_str = (
                        f"{driver}://@{host}:{port}/{database}"
                        f"?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
                    )
                else:
                    conn_str = f"{driver}://{user}:{password}@{host}:{port}/{database}"

                engine = create_engine(conn_str)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

                st.session_state.db_engine = engine
                st.session_state.db_tables = inspect(engine).get_table_names()
                st.success(f"Connected. Found {len(st.session_state.db_tables)} table(s).")
                st.session_state.source_substage = "db_pick_tables"
                st.rerun()
            except Exception as e:
                st.error(f"Connection failed: {e}")

    # ----- Step 4 (DB path): show available tables as checkboxes -----
    elif st.session_state.source_substage == "db_pick_tables":
        st.write("Select the table(s) you want to use:")
        selected = [t for t in st.session_state.db_tables if st.checkbox(t, key=f"tbl_{t}")]

        if selected and st.button("Load Selected Table(s)"):
            # Load every selected table into memory, keyed by table name
            st.session_state.table_dfs = {
                t: pd.read_sql(f"SELECT * FROM {t}", st.session_state.db_engine) for t in selected
            }
            if len(selected) == 1:
                # Single table: no merge needed, go straight to info
                st.session_state.df = st.session_state.table_dfs[selected[0]]
                st.session_state.source_substage = "show_info"
            else:
                # Multiple tables: enter the interactive pairwise merge flow
                st.session_state.merge_pool = dict(st.session_state.table_dfs)
                st.session_state.source_substage = "merge_pick_pair"
            st.rerun()

    # ----- Step 4b: pick exactly which two tables to merge together -----
    elif st.session_state.source_substage == "merge_pick_pair":
        pool_names = list(st.session_state.merge_pool.keys())
        st.write("Choose two tables to merge:")
        col1, col2 = st.columns(2)
        with col1:
            left_name = st.selectbox("First table", pool_names, key="merge_left_choice")
        with col2:
            right_options = [n for n in pool_names if n != left_name]
            right_name = st.selectbox("Second table", right_options, key="merge_right_choice")

        if st.button("Next: choose join columns →"):
            st.session_state.merge_left_name = left_name
            st.session_state.merge_right_name = right_name
            st.session_state.source_substage = "merge_pick_columns"
            st.rerun()

        # Let the user skip merging and just proceed with one of the tables as-is
        if st.button("Skip merging — use one table as-is"):
            st.session_state.df = st.session_state.merge_pool[left_name]
            st.session_state.source_substage = "show_info"
            st.rerun()

    # ----- Step 4c: choose join columns for the selected pair -----
    elif st.session_state.source_substage == "merge_pick_columns":
        left_name = st.session_state.merge_left_name
        right_name = st.session_state.merge_right_name
        left_df = st.session_state.merge_pool[left_name]
        right_df = st.session_state.merge_pool[right_name]

        st.write(f"Merging **{left_name}** with **{right_name}**")
        suggested_key = suggest_join_key(left_df, right_df)

        if suggested_key:
            st.caption(f"Matching column found automatically: `{suggested_key}`")
        else:
            st.caption("No matching column name found — choose which column matches on each side.")

        col1, col2, col3 = st.columns(3)
        with col1:
            left_cols = list(left_df.columns)
            left_key = st.selectbox(
                f"Column from {left_name}",
                options=left_cols,
                index=left_cols.index(suggested_key) if suggested_key in left_cols else 0,
            )
        with col2:
            right_cols = list(right_df.columns)
            right_key = st.selectbox(
                f"Column from {right_name}",
                options=right_cols,
                index=right_cols.index(suggested_key) if suggested_key in right_cols else 0,
            )
        with col3:
            join_type = st.selectbox("Join type", ["inner", "left", "right", "outer"])

        if st.button("Merge These Two Tables"):
            try:
                merged = left_df.merge(right_df, left_on=left_key, right_on=right_key, how=join_type)

                # If the join columns had different names, pandas keeps both —
                # drop the right-side one so only the chosen (left) column remains
                if left_key != right_key and right_key in merged.columns:
                    merged = merged.drop(columns=[right_key])

                merged_name = f"({left_name} + {right_name})"

                # Replace the two merged tables in the pool with the new merged result
                del st.session_state.merge_pool[left_name]
                del st.session_state.merge_pool[right_name]
                st.session_state.merge_pool[merged_name] = merged

                st.session_state.df = merged
                st.session_state.source_substage = "merge_continue_prompt"
                st.rerun()
            except Exception as e:
                st.error(f"Merge failed: {e}")

    # ----- Step 4d: after a merge, ask whether to merge another table or move on -----
    elif st.session_state.source_substage == "merge_continue_prompt":
        st.success("Merge complete.")
        show_dataset_info(st.session_state.df, "Merged result")

        # If only one table is left in the pool, there's nothing else to merge with
        if len(st.session_state.merge_pool) > 1:
            want_more = st.radio("Merge with another table?", ["No, continue", "Yes, merge another"])
            if st.button("Confirm"):
                if want_more == "Yes, merge another":
                    st.session_state.source_substage = "merge_pick_pair"
                else:
                    st.session_state.source_substage = "show_info"
                st.rerun()
        else:
            if st.button("Continue →"):
                st.session_state.source_substage = "show_info"
                st.rerun()

    # ----- Step 5: show info about the final chosen/merged dataset -----
    elif st.session_state.source_substage == "show_info":
        show_dataset_info(st.session_state.df)
        if st.button("Continue →"):
            st.session_state.stage = "quality_check"
            st.rerun()
