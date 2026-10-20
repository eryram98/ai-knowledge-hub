# backend/app/ingestion/config.py
"""
Ingestion configuration settings.
Python 3.6 compatible.
"""

import logging
import os

LOGGER = logging.getLogger(__name__)

# Load the repo-root .env once. Real environment variables take precedence.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(REPO_ROOT, ".env"), override=False)
except ImportError:
    pass


# Default values (can be overridden via environment variables)
DEFAULT_ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md")
# KB IDs for the demo topics (docs/SPEC.md, section 2). Topics pending PM
# confirmation, so they stay config-driven through INGESTION_ALLOWED_KB_IDS.
DEFAULT_ALLOWED_KB_IDS = ("it_policies", "hw_datasheets")
DEFAULT_MAX_FILE_SIZE_MB = 25
DEFAULT_MAX_FILES_PER_BATCH = 20
DEFAULT_DUPLICATE_POLICY = "allow"  # allow | block_exact | version
# Chunk size and overlap are measured in characters, not tokens: no tokenizer
# is chosen yet (it depends on the embedding model decision).
DEFAULT_CHUNK_SIZE_CHARS = 1000
DEFAULT_CHUNK_OVERLAP_CHARS = 200

ALLOWED_DUPLICATE_POLICIES = (
    "allow",
    "block_exact",
    "version",
)


def _to_int(value, default_value):
    # type: (str, int) -> int
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


def _split_csv(raw_value):
    # type: (str) -> list
    """
    Split a comma-separated value into stripped, lowercased, de-duplicated
    parts, preserving order: ' A, b,a ' -> ['a', 'b']
    """
    deduped = []
    seen = set()
    for part in (raw_value or "").split(","):
        cleaned = part.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _normalize_extensions(raw_extensions):
    # type: (str) -> tuple
    """
    Convert comma-separated extensions into normalized tuple:
    '.pdf,.txt,.md' -> ('.pdf', '.txt', '.md')
    """
    parts = []
    for ext in _split_csv(raw_extensions):
        if not ext.startswith("."):
            ext = "." + ext
        if ext not in parts:
            parts.append(ext)

    return tuple(parts) if parts else DEFAULT_ALLOWED_EXTENSIONS


def _normalize_kb_ids(raw_kb_ids):
    # type: (str) -> tuple
    """
    Convert comma-separated KB IDs into normalized tuple:
    'KB_A, kb_b' -> ('kb_a', 'kb_b')
    """
    parts = _split_csv(raw_kb_ids)
    return tuple(parts) if parts else DEFAULT_ALLOWED_KB_IDS


def _resolve_chunking(raw_size, raw_overlap):
    # type: (str, str) -> tuple
    """
    Return (chunk_size, overlap) in characters. A size <= 0 falls back to the
    default. An overlap < 0 or >= size falls back to size // 5 with a warning,
    so a typo in .env does not silently change chunking.
    """
    size = _to_int(raw_size, DEFAULT_CHUNK_SIZE_CHARS)
    if size <= 0:
        size = DEFAULT_CHUNK_SIZE_CHARS
    overlap = _to_int(raw_overlap, DEFAULT_CHUNK_OVERLAP_CHARS)
    if overlap < 0 or overlap >= size:
        fallback = size // 5
        LOGGER.warning(
            "INGESTION_CHUNK_OVERLAP_CHARS=%r is invalid for chunk size %d; using %d",
            raw_overlap, size, fallback,
        )
        overlap = fallback
    return size, overlap


class IngestionConfig(object):
    """
    Runtime ingestion config object.
    Environment variables:
      - INGESTION_ALLOWED_EXTENSIONS
      - INGESTION_MAX_FILE_SIZE_MB
      - INGESTION_MAX_FILES_PER_BATCH
      - INGESTION_DUPLICATE_POLICY
      - INGESTION_ALLOWED_KB_IDS
      - INGESTION_CHUNK_SIZE_CHARS
      - INGESTION_CHUNK_OVERLAP_CHARS
    """

    def __init__(self):
        raw_extensions = os.getenv("INGESTION_ALLOWED_EXTENSIONS", "")
        self.allowed_extensions = _normalize_extensions(raw_extensions)

        raw_max_file_size = os.getenv("INGESTION_MAX_FILE_SIZE_MB", "")
        self.max_file_size_mb = _to_int(raw_max_file_size, DEFAULT_MAX_FILE_SIZE_MB)

        raw_max_batch = os.getenv("INGESTION_MAX_FILES_PER_BATCH", "")
        self.max_files_per_batch = _to_int(raw_max_batch, DEFAULT_MAX_FILES_PER_BATCH)

        raw_policy = os.getenv("INGESTION_DUPLICATE_POLICY", DEFAULT_DUPLICATE_POLICY)
        policy = (raw_policy or "").strip().lower()
        if policy not in ALLOWED_DUPLICATE_POLICIES:
            policy = DEFAULT_DUPLICATE_POLICY
        self.duplicate_policy = policy

        raw_kb_ids = os.getenv("INGESTION_ALLOWED_KB_IDS", "")
        self.allowed_kb_ids = _normalize_kb_ids(raw_kb_ids)

        self.chunk_size_chars, self.chunk_overlap_chars = _resolve_chunking(
            os.getenv("INGESTION_CHUNK_SIZE_CHARS", ""),
            os.getenv("INGESTION_CHUNK_OVERLAP_CHARS", ""),
        )

    @property
    def max_file_size_bytes(self):
        # type: () -> int
        return self.max_file_size_mb * 1024 * 1024

    def as_dict(self):
        # type: () -> dict
        return {
            "allowed_extensions": self.allowed_extensions,
            "max_file_size_mb": self.max_file_size_mb,
            "max_file_size_bytes": self.max_file_size_bytes,
            "max_files_per_batch": self.max_files_per_batch,
            "duplicate_policy": self.duplicate_policy,
            "allowed_kb_ids": self.allowed_kb_ids,
            "chunk_size_chars": self.chunk_size_chars,
            "chunk_overlap_chars": self.chunk_overlap_chars,
        }
