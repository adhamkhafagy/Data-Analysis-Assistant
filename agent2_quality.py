import streamlit as st
import pandas as pd


# ---------- Agent 2 helpers: rule-based data quality detection ----------
# Each detect_* function scans one specific issue type. Kept rule-based
# (no LLM call) so the scan is fast, free, and deterministic.

def detect_missing_values(df: pd.DataFrame) -> dict:
    counts = df.isnull().sum()
    return {col: int(c) for col, c in counts.items() if c > 0}


def detect_duplicates(df: pd.DataFrame) -> int:
    return int(df.duplicated().sum())


def detect_type_issues(df: pd.DataFrame) -> dict:
    issues = {}
    for col in df.select_dtypes(include=["object", "str"]).columns:
        numeric_convertible = pd.to_numeric(df[col], errors="coerce")
        non_numeric_count = numeric_convertible.isnull().sum() - df[col].isnull().sum()
        non_null_count = df[col].notnull().sum()
        if 0 < non_numeric_count < (non_null_count * 0.5):
            issues[col] = int(non_numeric_count)
    return issues


def detect_outliers(df: pd.DataFrame) -> dict:
    report = {}
    for col in df.select_dtypes(include=["number"]).columns:
        q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        count = int(((df[col] < lower) | (df[col] > upper)).sum())
        if count > 0:
            report[col] = count
    return report


def detect_inconsistent_categories(df: pd.DataFrame) -> dict:
    report = {}
    for col in df.select_dtypes(include=["object", "str"]).columns:
        original_unique = df[col].dropna().unique()
        normalized_unique = df[col].dropna().astype(str).str.strip().str.lower().unique()
        if len(normalized_unique) < len(original_unique):
            report[col] = len(original_unique) - len(normalized_unique)
    return report


def detect_whitespace_issues(df: pd.DataFrame) -> dict:
    report = {}
    for col in df.select_dtypes(include=["object", "str"]).columns:
        count = df[col].dropna().apply(lambda x: isinstance(x, str) and x != x.strip()).sum()
        if count > 0:
            report[col] = int(count)
    return report


def detect_negative_values(df: pd.DataFrame) -> dict:
    report = {}
    for col in df.select_dtypes(include=["number"]).columns:
        count = int((df[col] < 0).sum())
        if count > 0:
            report[col] = count
    return report


def detect_constant_columns(df: pd.DataFrame) -> list:
    return [col for col in df.columns if df[col].nunique(dropna=True) == 1]


# Runs every detector and packages the results into a single list of
# structured issues (with severity + a suggested pandas fix) for Agent 3
def run_quality_scan(df: pd.DataFrame) -> list:
    issues = []

    missing = detect_missing_values(df)
    if missing:
        issues.append({
            "issue_type": "Missing Values",
            "severity": "high",
            "explanation": f"{len(missing)} column(s) contain missing values: {', '.join(missing.keys())}.",
            "affected_columns": list(missing.keys()),
            "fix_code": "\n".join(
                f"df['{c}'] = df['{c}'].fillna(df['{c}'].median() if pd.api.types.is_numeric_dtype(df['{c}']) else df['{c}'].mode()[0])"
                for c in missing
            ),
        })

    dup_count = detect_duplicates(df)
    if dup_count > 0:
        issues.append({
            "issue_type": "Duplicate Rows",
            "severity": "medium",
            "explanation": f"{dup_count} fully duplicated row(s) found.",
            "affected_columns": [],
            "fix_code": "df = df.drop_duplicates()",
        })

    type_issues = detect_type_issues(df)
    if type_issues:
        issues.append({
            "issue_type": "Invalid Numeric Values",
            "severity": "high",
            "explanation": f"Column(s) meant to be numeric contain invalid text values: {', '.join(type_issues.keys())}.",
            "affected_columns": list(type_issues.keys()),
            "fix_code": "\n".join(
                f"df['{c}'] = pd.to_numeric(df['{c}'], errors='coerce')" for c in type_issues
            ),
        })

    outliers = detect_outliers(df)
    if outliers:
        issues.append({
            "issue_type": "Outliers",
            "severity": "medium",
            "explanation": f"Statistical outliers detected (IQR method) in: {', '.join(outliers.keys())}.",
            "affected_columns": list(outliers.keys()),
            "fix_code": "\n".join(
                f"q1, q3 = df['{c}'].quantile(0.25), df['{c}'].quantile(0.75)\n"
                f"iqr = q3 - q1\n"
                f"df['{c}'] = df['{c}'].clip(q1 - 1.5*iqr, q3 + 1.5*iqr)"
                for c in outliers
            ),
        })

    inconsistent = detect_inconsistent_categories(df)
    if inconsistent:
        issues.append({
            "issue_type": "Inconsistent Categories",
            "severity": "low",
            "explanation": f"Category values differ only by case or spacing in: {', '.join(inconsistent.keys())}.",
            "affected_columns": list(inconsistent.keys()),
            "fix_code": "\n".join(
                f"df['{c}'] = df['{c}'].astype(str).str.strip().str.lower()" for c in inconsistent
            ),
        })

    whitespace = detect_whitespace_issues(df)
    if whitespace:
        issues.append({
            "issue_type": "Extra Whitespace",
            "severity": "low",
            "explanation": f"Leading/trailing whitespace found in: {', '.join(whitespace.keys())}.",
            "affected_columns": list(whitespace.keys()),
            "fix_code": "\n".join(f"df['{c}'] = df['{c}'].str.strip()" for c in whitespace),
        })

    negatives = detect_negative_values(df)
    if negatives:
        issues.append({
            "issue_type": "Unexpected Negative Values",
            "severity": "medium",
            "explanation": f"Negative values found where they may not make sense: {', '.join(negatives.keys())}.",
            "affected_columns": list(negatives.keys()),
            "fix_code": "\n".join(f"df.loc[df['{c}'] < 0, '{c}'] = None" for c in negatives),
        })

    constants = detect_constant_columns(df)
    if constants:
        issues.append({
            "issue_type": "Constant Columns",
            "severity": "low",
            "explanation": f"Column(s) with a single repeated value (no useful information): {', '.join(constants)}.",
            "affected_columns": constants,
            "fix_code": f"df = df.drop(columns={constants})",
        })

    return issues


# ---------- Agent 2: Data Quality Check ----------
# Asks the user if their data needs cleaning. If yes/unsure, runs the rule-based
# scan above and hands the structured issues to Agent 3 for review and approval.
# If the user says no, the pipeline skips straight to Agent 4 (the analyst).
def render():
    st.header("Step 2: Does this data need cleaning?")
    st.caption("Not sure? Choose 'I don't know' and we'll scan it for you.")

    answer = st.radio("", ["Yes", "No", "I don't know"], label_visibility="collapsed")

    if st.button("Continue →", key="quality_check_continue"):
        if answer == "No":
            st.session_state.stage = "analyst"
        else:
            st.session_state.quality_issues = run_quality_scan(st.session_state.df)
            st.session_state.stage = "quality_fix"
        st.rerun()
