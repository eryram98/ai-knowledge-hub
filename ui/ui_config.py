"""Settings for the Streamlit UI, read from the repo-root .env (real environment variables win).

The UI is a pure HTTP client of the FastAPI backend, so it only needs to know
where the API lives and how long to wait for it.
"""

import os
from dataclasses import dataclass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(REPO_ROOT, ".env"), override=False)
except ImportError:
    pass

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
# Plain reads (KBs, inventory) should answer at once; an upload copies files to disk.
DEFAULT_TIMEOUT_SECONDS = 15.0
UPLOAD_TIMEOUT_SECONDS = 120.0
# /ask makes two LLM calls (route + answer). Each attempt times out after 20 s and
# is retried up to 3 times with 2/4/8 s backoff, so a slow /ask can take minutes.
ASK_TIMEOUT_SECONDS = 180.0

API_START_COMMAND = (
    r".venv\Scripts\python -m uvicorn api.api_app:create_app --factory --app-dir backend\app --port 8000"
)


@dataclass(frozen=True)
class UiConfig:
    api_base_url: str


def load_config():
    """API_BASE_URL from the environment; empty or unset means the local default."""
    base_url = (os.environ.get("API_BASE_URL") or "").strip() or DEFAULT_API_BASE_URL
    return UiConfig(api_base_url=base_url.rstrip("/"))
