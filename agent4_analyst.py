import streamlit as st
import pandas as pd
import requests
import re
import os
import io
import contextlib
import traceback
import uuid
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from report_export import generate_docx, generate_pdf

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

CHARTS_DIR = "charts"
os.makedirs(CHARTS_DIR, exist_ok=True)

# Restricted set of builtins available to LLM-generated code during execution
SAFE_BUILTINS = {
    "len": len, "range": range, "print": print, "sum": sum, "min": min, "max": max,
    "round": round, "sorted": sorted, "list": list, "dict": dict, "set": set,
    "tuple": tuple, "str": str, "int": int, "float": float, "bool": bool,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "abs": abs, "all": all, "any": any, "reversed": reversed, "type": type,
    "isinstance": isinstance,
}

# Only these modules can be imported by generated code
ALLOWED_MODULES = {
    "pandas", "numpy", "matplotlib", "scipy", "seaborn",
    "sklearn", "statsmodels",
}


# ---------- Sandbox: safe code execution ----------
# Runs LLM-generated pandas/matplotlib code with a restricted builtins set
# and a module allowlist, captures printed output, and saves any charts
def run_code(code: str, df: pd.DataFrame) -> dict:
    plt.close("all")
    local_ns = {"df": df, "pd": pd, "plt": plt}
    stdout_buffer = io.StringIO()
    charts = []

    def safe_import(name, *args, **kwargs):
        if name.split(".")[0] not in ALLOWED_MODULES:
            raise ImportError(f"Import of '{name}' is not allowed")
        return __import__(name, *args, **kwargs)

    exec_builtins = dict(SAFE_BUILTINS)
    exec_builtins["__import__"] = safe_import

    try:
        with contextlib.redirect_stdout(stdout_buffer):
            exec(code, {"__builtins__": exec_builtins}, local_ns)

        for num in plt.get_fignums():
            fig = plt.figure(num)
            filename = f"{CHARTS_DIR}/chart_{uuid.uuid4().hex[:8]}.png"
            fig.savefig(filename, bbox_inches="tight")
            charts.append(filename)
        plt.close("all")

        return {"success": True, "output": stdout_buffer.getvalue(), "error": "", "charts": charts}

    except Exception:
        return {
            "success": False,
            "output": stdout_buffer.getvalue(),
            "error": traceback.format_exc(limit=2),
            "charts": [],
        }


# ---------- LLM calls ----------
# Sends a prompt to Groq and returns raw text (used for both code and report generation)
def call_llm(prompt: str) -> str:
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"},
        json={"model": GROQ_MODEL, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]},
    )
    data = response.json()
    if "choices" not in data:
        raise RuntimeError(f"Groq API error: {data.get('error', {}).get('message', str(data))}")
    return data["choices"][0]["message"]["content"]


# Builds the prompt asking the LLM to write pandas/matplotlib code for the user's question
def build_code_prompt(df: pd.DataFrame, user_question: str) -> str:
    schema = df.dtypes.astype(str).to_dict()
    sample = df.head(3).to_dict(orient="records")
    return f"""You are a data analyst agent. Given this dataframe schema and sample rows,
write ONLY Python pandas/matplotlib code (no explanation, no markdown fences) that
answers the user's request. The dataframe is already loaded as `df`.
If a chart is relevant, create it with matplotlib (plt). Use print() for any
numeric/text findings.

You may ONLY import from these libraries: pandas (pd), numpy, matplotlib (plt),
scipy, seaborn, sklearn, statsmodels. Do not import any other library — if the
analysis doesn't strictly need one of these, use plain pandas/numpy instead.

Schema: {schema}
Sample rows: {sample}

User request: {user_question}

Return ONLY executable Python code.
"""


# Builds the prompt asking the LLM to summarize all analysis results into a final report
def build_report_prompt(history: list, language: str) -> str:
    findings = "\n".join(
        f"- Question: {h['question']}\n  Result: {h['result'].get('output', '')}"
        for h in history if h["result"]["success"]
    )

    if language == "Arabic":
        return f"""أنت محلل بيانات. بناءً على نتائج التحليل التالية، اكتب تقريراً مختصراً بالعربية
بصيغة Markdown نظيفة، يتضمن:
## ملخص تنفيذي
جملتين إلى ثلاث جمل.
## أهم النتائج
نقاط قصيرة، كل نقطة رقم أو نتيجة واحدة بوضوح.
## توصيات عملية
نقاط قابلة للتنفيذ.

قواعد مهمة:
- لا تخلط أرقام أو مصطلحات إنجليزية داخل الجملة العربية مباشرة، ضعها بين قوسين أو في سطر منفصل.
- استخدم أرقام عربية عادية (0-9) بشكل واضح ومنفصل عن النص.
- كل نقطة (bullet) تبدأ بجملة عربية كاملة.

النتائج:
{findings}
"""
    else:
        return f"""You are a data analyst. Based on the following analysis results, write a concise
report in clean Markdown format including:
## Executive Summary
2-3 sentences.
## Key Findings
Short bullet points, each stating one clear finding or number.
## Practical Recommendations
Actionable bullet points.

Findings:
{findings}
"""


# ---------- Agent 4: Analyst + Report ----------
# Welcomes the user, takes a natural-language question, generates and runs
# pandas/matplotlib code (with one self-correction retry on failure), shows
# results, and offers a final bilingual report once one or more analyses are done.
def render():
    st.header("Step 4: Ask a question about your data")

    if "analysis_history" not in st.session_state:
        st.session_state.analysis_history = []

    question = st.text_input("What would you like to know? (e.g. Analyze sales over the last 6 months)")

    if st.button("Analyze") and question:
        with st.spinner("The agent is writing and running code..."):
            prompt = build_code_prompt(st.session_state.df, question)
            code = re.sub(r"```python|```", "", call_llm(prompt)).strip()

            result = run_code(code, st.session_state.df)

            # Self-correction loop: retry once if the generated code failed
            if not result["success"]:
                fix_prompt = (
                    prompt
                    + f"\n\nThe previous code failed with this error:\n{result['error']}\n"
                    "Fix it and return ONLY corrected Python code."
                )
                code = re.sub(r"```python|```", "", call_llm(fix_prompt)).strip()
                result = run_code(code, st.session_state.df)

            st.subheader("Executed Code")
            st.code(code, language="python")

            if result["success"]:
                st.subheader("Results")
                if result["output"]:
                    st.text(result["output"])
                for chart_path in result["charts"]:
                    st.image(chart_path)
            else:
                st.error(f"Execution failed:\n{result['error']}")

            st.session_state.analysis_history.append({"question": question, "code": code, "result": result})

    # Once at least one analysis has run, offer a final bilingual report
    if st.session_state.analysis_history:
        st.divider()
        report_lang = st.radio("Report language", ["English", "Arabic"], horizontal=True)
        if st.button("📄 Generate Final Report & Recommendations"):
            with st.spinner("Writing the report..."):
                report = call_llm(build_report_prompt(st.session_state.analysis_history, report_lang)).strip()
                st.session_state.final_report = report
                st.session_state.final_report_lang = report_lang

        # Persisted across reruns so the download buttons below stay usable
        # after the "Generate" button's one-shot True value resets
        if "final_report" in st.session_state:
            report = st.session_state.final_report
            report_lang = st.session_state.final_report_lang

            st.subheader("Final Report")
            if report_lang == "Arabic":
                st.markdown(
                    f'<div dir="rtl" style="text-align:right; font-size:16px; line-height:1.9;">{report}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(report)

            st.divider()
            st.write("Download this report:")
            dl_col1, dl_col2, dl_col3 = st.columns(3)

            with dl_col1:
                st.download_button(
                    "⬇️ Word (.docx)",
                    data=generate_docx(report, report_lang),
                    file_name="analysis_report.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            with dl_col2:
                try:
                    pdf_bytes = generate_pdf(report, report_lang)
                    st.download_button(
                        "⬇️ PDF",
                        data=pdf_bytes,
                        file_name="analysis_report.pdf",
                        mime="application/pdf",
                    )
                except FileNotFoundError as e:
                    st.warning(str(e))

            # Only offer the cleaned dataset if Agent 3 actually applied fixes
            if st.session_state.get("data_was_cleaned"):
                with dl_col3:
                    st.download_button(
                        "⬇️ Cleaned Data (.csv)",
                        data=st.session_state.df.to_csv(index=False).encode("utf-8-sig"),
                        file_name="cleaned_data.csv",
                        mime="text/csv",
                    )
