"""Streamlit UI for the AI Knowledge Hub (F5): Documents and Ask pages.

A pure HTTP client of the FastAPI backend (API_BASE_URL in .env, default
http://127.0.0.1:8000). It never imports backend modules. Run from the repo root,
with the API already running:
    .venv\\Scripts\\python -m streamlit run ui\\app.py
"""

import streamlit as st

import ui_config

st.set_page_config(page_title="AI Knowledge Hub", page_icon=":material/hub:", layout="wide")

navigation = st.navigation([
    st.Page("views/documents.py", title="Documents", icon=":material/description:", default=True),
    st.Page("views/ask.py", title="Ask", icon=":material/question_answer:", url_path="ask"),
])
st.sidebar.caption("API: {0}".format(ui_config.load_config().api_base_url))
navigation.run()
