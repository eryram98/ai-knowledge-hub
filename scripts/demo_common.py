"""Shared helpers for the demo scripts: paths, the API client and a small yes/no prompt."""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "ui"))

from ui_api_client import ApiClient, ApiClientError  # noqa: F401

CORPUS_DIR = os.path.join(REPO_ROOT, "data", "corpus")
EVAL_SET_PATH = os.path.join(REPO_ROOT, "data", "eval", "eval_set.jsonl")
EVAL_RUNS_DIR = os.path.join(REPO_ROOT, "data", "eval", "runs")
PROGRESS_PATH = os.path.join(REPO_ROOT, "docs", "PROGRESS.md")
INSTANCE_DIR = os.path.join(REPO_ROOT, "backend", "instance")
DEFAULT_API_URL = "http://127.0.0.1:8000"


def confirm(prompt, assume_yes=False, input_fn=input):
    """True when the user answers y or yes (or assume_yes is set). Anything else, including EOF, is no."""
    if assume_yes:
        return True
    try:
        return input_fn(prompt + " [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False
