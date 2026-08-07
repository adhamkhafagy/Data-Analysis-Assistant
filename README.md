# 🤖 Data Analysis Multi-Agent System

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B.svg)](https://streamlit.io/)
[![Groq](https://img.shields.io/badge/LLM-Groq%20Llama%203.3-orange.svg)](https://groq.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A four-agent pipeline that walks a user from raw data to a finished analysis report — end to end, through a single conversational Streamlit interface. Each agent is a separate, focused module with one responsibility, connected by a shared orchestrator.

## Table of Contents
- [Overview](#overview)
- [Pipeline Architecture](#pipeline-architecture)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Safety Design](#safety-design)
- [License](#license)

## Overview

Instead of a single monolithic chatbot, this project splits the data analysis workflow into four independent agents, each handling one stage of the process and handing off to the next:

1. **Source Agent** — connects to the user's data, wherever it lives
2. **Quality Scanner** — detects data quality issues
3. **Fix Approval Agent** — lets the user choose which issues to fix, then applies them
4. **Analyst Agent** — answers natural-language questions about the data and produces a final report

A central orchestrator (`main_app.py`) tracks which stage the pipeline is in and routes to the right agent, with full back-navigation support so the user can revisit and change any earlier step.

## Pipeline Architecture

```
Agent 1 — Source
  → Upload a file (CSV / Excel / multiple files) OR connect to a database
    (PostgreSQL, MySQL, SQL Server, SQLite, Oracle — incl. Windows Authentication)
    OR use a built-in sample dataset
  → Interactive table merging: pick any two tables, auto-suggested join column
    (editable), choose join type, repeat as needed
        ↓
Agent 2 — Quality Scanner
  → Asks whether the data needs cleaning (Yes / No / Not sure)
  → If yes/unsure: runs a rule-based scan (missing values, duplicates, invalid
    numeric values, outliers, inconsistent categories, whitespace, negative
    values, constant columns)
  → "No" skips straight to Agent 4
        ↓
Agent 3 — Fix Approval
  → Shows every detected issue with an explanation and the exact pandas fix
  → User checks which fixes to apply (all pre-checked by default)
  → Applies only the approved fixes to the dataframe
        ↓
Agent 4 — Analyst & Report
  → Natural-language question → LLM-generated pandas/matplotlib code
  → Code runs in a sandboxed executor, with one self-correction retry on failure
  → Repeatable: ask as many questions as needed
  → Generates a final report (English or Arabic, proper RTL) with an executive
    summary, key findings, and recommendations
  → Download the report as Word or PDF, and the cleaned dataset as CSV
```

## Features

- **Any data source** — file upload, live database connection, or sample data
- **Interactive, editable table merging** — no forced auto-merge; the user picks table pairs and join columns, with automatic suggestions
- **Rule-based quality scanning** — fast, free, deterministic (no LLM call needed for detection)
- **Human-in-the-loop fixes** — nothing is changed without explicit approval
- **Self-correcting code generation** — failed analysis code is automatically retried with the error fed back to the LLM
- **Bilingual reporting** — English or Arabic, with correct right-to-left rendering in both the UI and exported files
- **Export to Word & PDF** — including proper Arabic shaping and RTL layout in both formats
- **Full back-navigation** — every step (including sub-steps like table merging) can be revisited and changed
- **Free, sandboxed LLM inference** — powered by Groq's Llama 3.3 70B, no paid API required

## Installation

```bash
git clone https://github.com/adhamkhafagy/data-analysis-multi-agent.git
cd data-analysis-multi-agent
pip install -r requirements.txt
```

Create a `.env` file in the project root with a free Groq API key:

```
GROQ_API_KEY=your_key_here
```

**Database connections** additionally require the relevant driver installed at the OS level:
- SQL Server: [ODBC Driver 17/18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Other databases: their respective client libraries (handled automatically for PostgreSQL/MySQL via the Python drivers in `requirements.txt`)

## Usage

```bash
streamlit run main_app.py
```

Then simply follow the on-screen steps — each agent guides you through its stage, and the **⬅️ Back** button lets you revisit and change any previous choice at any time.

## Project Structure

```
├── main_app.py          # Orchestrator — routes to the active agent based on pipeline stage
├── utils.py              # Shared helpers: session state, dataset info display, navigation history
├── agent1_source.py      # Data source selection, connection, and interactive table merging
├── agent2_quality.py     # Rule-based data quality scanning
├── agent3_fix.py         # Issue review, approval, and fix execution
├── agent4_analyst.py     # Natural-language analysis, self-correcting code execution, reporting
├── report_export.py      # Word/PDF report generation with Arabic RTL support
├── fonts/
│   └── Amiri-Regular.ttf # Arabic-capable font, required for PDF export
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

## Safety Design

LLM-generated analysis code never runs unrestricted:
- `exec()` runs with a minimal `__builtins__` whitelist (safe built-in functions only — no `open`, `eval`, `input`, etc.)
- A custom `__import__` only allows `pandas`, `numpy`, and `matplotlib`
- All output is captured (stdout + generated figures) rather than allowing arbitrary file/system access
- Database credentials are entered per-session and never persisted to disk

## License

MIT — see [LICENSE](LICENSE).
