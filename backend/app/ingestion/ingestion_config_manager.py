# backend/app/ingestion/config.py
"""
Ingestion configuration settings.
Python 3.6 compatible.
"""

import os


# Default values (can be overridden via environment variables)
DEFAULT_ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md")
DEFAULT_MAX_FILE_SIZE_MB = 25
DEFAULT_MAX_FILES_PER_BATCH = 20
DEFAULT_DUPLICATE_POLICY = "allow"  # allow | block_exact | version

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


def _normalize_extensions(raw_extensions):
    # type: (str) -> tuple
    """
    Convert comma-separated extensions into normalized tuple:
    '.pdf,.txt,.md' -> ('.pdf', '.txt', '.md')
    """
    if not raw_extensions:
        return DEFAULT_ALLOWED_EXTENSIONS

    parts = []
    for part in raw_extensions.split(","):
        cleaned = part.strip().lower()
        if not cleaned:
            continue
        if not cleaned.startswith("."):
            cleaned = "." + cleaned
        parts.append(cleaned)

    # Remove duplicates while preserving order
    deduped = []
    seen = set()
    for ext in parts:
        if ext not in seen:
            seen.add(ext)
            deduped.append(ext)

    return tuple(deduped) if deduped else DEFAULT_ALLOWED_EXTENSIONS


class IngestionConfig(object):
    """
    Runtime ingestion config object.
    Environment variables:
      - INGESTION_ALLOWED_EXTENSIONS
      - INGESTION_MAX_FILE_SIZE_MB
      - INGESTION_MAX_FILES_PER_BATCH
      - INGESTION_DUPLICATE_POLICY
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
        }
