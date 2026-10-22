"""Agent settings (F4): LLM provider, model and key from the environment; KB descriptions from JSON.

Importing the ingestion config module loads the repo-root .env, so the
variables below can be set there.
"""

import json
import logging
import os

from agent.agent_answer import ANSWER_THINKING
from agent.agent_llm import THINKING_LEVELS
from agent.agent_router import ROUTER_THINKING
from ingestion.ingestion_config_manager import REPO_ROOT

LOGGER = logging.getLogger(__name__)

DEFAULT_LLM_PROVIDER = "gemini"
# Measured 2026-10-22 on real router and answer prompts: about 1 s per call and correct, while
# gemini-3.8-flash returned 504s and a 503 on all 4 calls. Switch back with GEMINI_MODEL (and
# GEMINI_ROUTER_THINKING / GEMINI_ANSWER_THINKING=low, since gemini-3.8-flash rejects "minimal").
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_LLM_MAX_RETRIES = 3
# Per attempt. Gemini receives it as the request deadline, so a slower call ends as a retried 504.
DEFAULT_GEMINI_TIMEOUT_SECONDS = 20.0
# Committed, so every machine routes with the same descriptions.
DEFAULT_KB_DESCRIPTIONS_PATH = os.path.join(REPO_ROOT, "config", "kb_descriptions.json")


def _resolve_max_retries(raw_value):
    """A non-negative integer, or the default with a warning for a typo (empty means default, silently)."""
    if raw_value is None or not raw_value.strip():
        return DEFAULT_LLM_MAX_RETRIES
    try:
        value = int(raw_value)
    except ValueError:
        value = -1
    if value < 0:
        LOGGER.warning("LLM_MAX_RETRIES=%r is invalid; using %d", raw_value, DEFAULT_LLM_MAX_RETRIES)
        return DEFAULT_LLM_MAX_RETRIES
    return value


def _resolve_thinking(name, raw_value, default):
    """One of THINKING_LEVELS (case-insensitive), or the default with a warning for anything else."""
    value = (raw_value or "").strip().lower()
    if not value:
        return default
    if value not in THINKING_LEVELS:
        LOGGER.warning("%s=%r is not one of %s; using %r", name, raw_value, THINKING_LEVELS, default)
        return default
    return value


def _resolve_timeout(raw_value):
    """A positive number of seconds, or the default with a warning for a typo (empty means default)."""
    if raw_value is None or not raw_value.strip():
        return DEFAULT_GEMINI_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError:
        value = 0.0
    if not value > 0 or value == float("inf"):
        LOGGER.warning("GEMINI_TIMEOUT_SECONDS=%r is invalid; using %s", raw_value, DEFAULT_GEMINI_TIMEOUT_SECONDS)
        return DEFAULT_GEMINI_TIMEOUT_SECONDS
    return value


class AgentConfig(object):
    """
    Environment variables:
      - LLM_PROVIDER: "gemini" (the only provider so far)
      - GEMINI_MODEL: Gemini model name (default gemini-3.5-flash-lite)
      - GEMINI_API_KEY: required for real calls, not for starting the app
      - GEMINI_ROUTER_THINKING, GEMINI_ANSWER_THINKING: thinking level of the routing and answer
        calls, one of minimal/low/medium/high (default minimal for both)
      - GEMINI_TIMEOUT_SECONDS: per-attempt timeout of a Gemini call (default 20)
      - LLM_MAX_RETRIES: retries after a 429, 503 or 504 before giving up (default 3)
      - KB_DESCRIPTIONS_PATH: KB names and descriptions JSON (default config/kb_descriptions.json)
    """

    def __init__(self):
        self.llm_provider = (os.getenv("LLM_PROVIDER", "").strip().lower() or DEFAULT_LLM_PROVIDER)
        self.gemini_model = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip() or None
        self.router_thinking = _resolve_thinking(
            "GEMINI_ROUTER_THINKING", os.getenv("GEMINI_ROUTER_THINKING", ""), ROUTER_THINKING)
        self.answer_thinking = _resolve_thinking(
            "GEMINI_ANSWER_THINKING", os.getenv("GEMINI_ANSWER_THINKING", ""), ANSWER_THINKING)
        self.timeout_seconds = _resolve_timeout(os.getenv("GEMINI_TIMEOUT_SECONDS", ""))
        self.max_retries = _resolve_max_retries(os.getenv("LLM_MAX_RETRIES", ""))
        self.kb_descriptions_path = os.getenv("KB_DESCRIPTIONS_PATH", "").strip() or DEFAULT_KB_DESCRIPTIONS_PATH

    def as_dict(self):
        """Settings without the API key."""
        return {
            "llm_provider": self.llm_provider,
            "gemini_model": self.gemini_model,
            "gemini_api_key_set": self.gemini_api_key is not None,
            "router_thinking": self.router_thinking,
            "answer_thinking": self.answer_thinking,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "kb_descriptions_path": self.kb_descriptions_path,
        }


class KbInfo(object):
    """A configured KB's display name (prompts and UI) and one-line description (router, /kbs)."""

    def __init__(self, kb_id, name, description):
        self.kb_id = kb_id
        self.name = name
        self.description = description

    def __eq__(self, other):
        return isinstance(other, KbInfo) and (self.kb_id, self.name, self.description) == (
            other.kb_id, other.name, other.description)

    def __repr__(self):
        return "KbInfo({0!r}, {1!r}, {2!r})".format(self.kb_id, self.name, self.description)


def load_kb_infos(path, kb_ids):
    """Return {kb_id: KbInfo} for every configured KB, in config order.

    The file maps kb_id to {"name": str, "description": str}. A missing or
    unreadable file, bad JSON, or a configured KB without a non-blank name
    and description raises ValueError: routing on a missing description
    would fail silently. Entries for KBs that aren't configured are ignored.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except OSError as exc:
        raise ValueError("Cannot read KB descriptions file {0}: {1}".format(path, exc))
    except json.JSONDecodeError as exc:
        raise ValueError("KB descriptions file {0} is not valid JSON: {1}".format(path, exc))
    if not isinstance(raw, dict):
        raise ValueError("KB descriptions file {0} must hold a JSON object keyed by kb_id".format(path))
    entries = {str(key).strip().lower(): value for key, value in raw.items()}
    infos = {}
    for kb_id in kb_ids:
        entry = entries.get(kb_id)
        if not isinstance(entry, dict):
            raise ValueError("KB descriptions file {0} has no entry for configured KB {1!r}".format(path, kb_id))
        fields = {}
        for field in ("name", "description"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("KB {0!r} in {1} needs a non-blank {2!r}".format(kb_id, path, field))
            fields[field] = value.strip()
        infos[kb_id] = KbInfo(kb_id, fields["name"], fields["description"])
    return infos


def kb_descriptions(kb_infos):
    """{kb_id: description} in config order: the router's input."""
    return {kb_id: info.description for kb_id, info in kb_infos.items()}
