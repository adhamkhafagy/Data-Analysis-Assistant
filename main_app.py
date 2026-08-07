import streamlit as st
from utils import init_session_state, track_navigation, render_back_button
import agent1_source
import agent2_quality
import agent3_fix
import agent4_analyst

# Page configuration and title for the multi-agent Streamlit app
st.set_page_config(page_title="Data Analysis Multi-Agent System", layout="wide")
st.title("🤖 Data Analysis Assistant")

# Set up all shared session_state keys used across the pipeline
init_session_state()

# Record the current checkpoint (for the Back button) and draw it if available.
# Must run before any agent renders, so a checkpoint always exists to return to.
track_navigation()
render_back_button()

# ---------- Orchestration ----------
# Each stage maps to exactly one agent module's render() function.
# Agents move the pipeline forward by setting st.session_state.stage
# themselves and calling st.rerun() — this dispatcher just picks which
# agent's UI to draw on each run.
if st.session_state.stage == "source":
    agent1_source.render()

elif st.session_state.stage == "quality_check":
    agent2_quality.render()

elif st.session_state.stage == "quality_fix":
    agent3_fix.render()

elif st.session_state.stage == "analyst":
    agent4_analyst.render()
