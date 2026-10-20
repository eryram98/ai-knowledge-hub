"""Retrieval settings from the environment (F3).

Kept apart from IngestionConfig. Importing the ingestion config module loads
the repo-root .env, so RETRIEVAL_* values set there apply here too.
"""

import logging
import os

import ingestion.ingestion_config_manager  # noqa: F401  (loads the repo-root .env)

LOGGER = logging.getLogger(__name__)

# Hits per ranked list (vector and keyword), per KB.
DEFAULT_RETRIEVAL_TOP_K = 20


def _resolve_top_k(raw_value):
    """A positive integer, or the default with a warning for a typo (empty means default, silently)."""
    if raw_value is None or not raw_value.strip():
        return DEFAULT_RETRIEVAL_TOP_K
    try:
        value = int(raw_value)
    except ValueError:
        value = 0
    if value <= 0:
        LOGGER.warning("RETRIEVAL_TOP_K=%r is invalid; using %d", raw_value, DEFAULT_RETRIEVAL_TOP_K)
        return DEFAULT_RETRIEVAL_TOP_K
    return value


class RetrievalConfig(object):
    """
    Environment variables:
      - RETRIEVAL_TOP_K: hits per ranked list (default 20)
    """

    def __init__(self):
        self.top_k = _resolve_top_k(os.getenv("RETRIEVAL_TOP_K", ""))

    def as_dict(self):
        return {"top_k": self.top_k}
