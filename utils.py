import streamlit as st
import pandas as pd

# Maps each database type to its SQLAlchemy driver string and default port.
# Shared by Agent 1 (connection form) — kept here so other agents could
# reuse it later without importing Agent 1's file directly.
DB_DRIVERS = {
    "PostgreSQL": {"driver": "postgresql+psycopg2", "default_port": "5432"},
    "MySQL": {"driver": "mysql+pymysql", "default_port": "3306"},
    "SQL Server": {"driver": "mssql+pyodbc", "default_port": "1433"},
    "SQLite": {"driver": "sqlite", "default_port": ""},
    "Oracle": {"driver": "oracle+cx_oracle", "default_port": "1521"},
}

# Built-in sample datasets so the user can try the pipeline without their own data
SAMPLE_DATASETS = {
    "Titanic (passenger survival)": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/titanic.csv",
    "Iris (flower measurements)": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv",
    "Tips (restaurant bills)": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv",
}


# Suggests the most likely join column between two tables by looking for
# shared column names, preferring ones that look like id/key columns
def suggest_join_key(df_left: pd.DataFrame, df_right: pd.DataFrame):
    shared = [c for c in df_left.columns if c in df_right.columns]
    if not shared:
        return None
    id_like = [c for c in shared if "id" in c.lower() or "key" in c.lower()]
    return id_like[0] if id_like else shared[0]


# Shows row/column count, dtypes, and a preview for a chosen dataframe.
# Used by every agent whenever a dataset needs to be displayed to the user.
def show_dataset_info(df: pd.DataFrame, name: str = ""):
    st.subheader(f"Dataset Info {f'— {name}' if name else ''}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Rows", df.shape[0])
    col2.metric("Columns", df.shape[1])
    col3.metric("Missing Cells", int(df.isnull().sum().sum()))
    st.dataframe(df.head())
    with st.expander("Column data types"):
        st.write(df.dtypes.astype(str))


# Initializes every session_state key used across the pipeline in one place,
# so each agent file can assume these keys already exist
def init_session_state():
    defaults = {
        "df": None,
        "stage": "source",
        "source_substage": "choose_source",
        "db_engine": None,
        "db_tables": [],
        "table_dfs": {},
        "merge_pool": {},
        "quality_issues": [],
        "data_was_cleaned": False,
        "nav_history": [],
        "_last_checkpoint": None,
        "_skip_history_push": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# Records the current (stage, source_substage) checkpoint into nav_history
# whenever it changes going forward, so the Back button can restore it later.
# Must be called once per run, before any agent renders its UI.
def track_navigation():
    checkpoint = (st.session_state.stage, st.session_state.source_substage)

    if st.session_state._last_checkpoint is None:
        st.session_state._last_checkpoint = checkpoint
        return

    if checkpoint != st.session_state._last_checkpoint:
        if not st.session_state._skip_history_push:
            st.session_state.nav_history.append(st.session_state._last_checkpoint)
        st.session_state._skip_history_push = False
        st.session_state._last_checkpoint = checkpoint


# Renders the "⬅️ Back" button (only if there's somewhere to go back to)
# and restores the previous checkpoint when clicked
def render_back_button():
    if st.session_state.nav_history:
        if st.button("⬅️ Back"):
            prev_stage, prev_substage = st.session_state.nav_history.pop()
            st.session_state.stage = prev_stage
            st.session_state.source_substage = prev_substage
            st.session_state._skip_history_push = True
            st.rerun()
