"""
Ingestion metadata contract and persistence expectations.
Python 3.6 compatible.
"""

from datetime import datetime


# Canonical metadata keys
META_DOCUMENT_ID = "document_id"
META_ORIGINAL_FILENAME = "original_filename"
META_FILE_TYPE = "file_type"
META_FILE_SIZE_BYTES = "file_size_bytes"
META_UPLOAD_TIMESTAMP = "upload_timestamp"
META_INGESTION_SOURCE = "ingestion_source"

# Required v1 metadata fields from PRD
REQUIRED_METADATA_FIELDS = (
    META_ORIGINAL_FILENAME,
    META_FILE_TYPE,
    META_FILE_SIZE_BYTES,
    META_UPLOAD_TIMESTAMP,
    META_INGESTION_SOURCE,
)

# v1 source
INGESTION_SOURCE_UI = "UI"
ALLOWED_INGESTION_SOURCES = (
    INGESTION_SOURCE_UI,
)

# Persistence expectations (high-level contract for repository layer)
PERSISTENCE_EXPECTATIONS = {
    "files_table": {
        "required_fields": REQUIRED_METADATA_FIELDS + (META_DOCUMENT_ID,),
        "notes": "One record per uploaded file with immutable source metadata.",
    },
    "status_history": {
        "required_fields": ("document_id", "status", "timestamp", "reason"),
        "notes": "Append-only lifecycle transitions for auditability.",
    },
    "artifacts": {
        "required_fields": ("document_id", "full_text_ref", "chunks_ref", "index_ref", "embedding_ref"),
        "notes": "References to extracted text/chunks/index/embeddings.",
    },
}


def _is_non_empty_string(value):
    # type: (object) -> bool
    return isinstance(value, str) and len(value.strip()) > 0


def _is_positive_int(value):
    # type: (object) -> bool
    return isinstance(value, int) and value >= 0


def _is_iso8601_datetime(value):
    # type: (object) -> bool
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        # Python 3.6: strict fallback format; avoids datetime.fromisoformat (3.7+)
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def validate_metadata_contract(metadata):
    # type: (dict) -> tuple
    """
    Validate metadata against the v1 contract.
    Returns (is_valid, errors)
      - is_valid: bool
      - errors: list[str]
    """
    errors = []

    if not isinstance(metadata, dict):
        return False, ["metadata must be a dictionary"]

    for field_name in REQUIRED_METADATA_FIELDS:
        if field_name not in metadata:
            errors.append("missing required field: {0}".format(field_name))

    if errors:
        return False, errors

    if not _is_non_empty_string(metadata.get(META_ORIGINAL_FILENAME)):
        errors.append("original_filename must be a non-empty string")

    if not _is_non_empty_string(metadata.get(META_FILE_TYPE)):
        errors.append("file_type must be a non-empty string")

    if not _is_positive_int(metadata.get(META_FILE_SIZE_BYTES)):
        errors.append("file_size_bytes must be a non-negative integer")

    if not _is_iso8601_datetime(metadata.get(META_UPLOAD_TIMESTAMP)):
        errors.append("upload_timestamp must be UTC ISO-8601 format: YYYY-MM-DDTHH:MM:SSZ")

    source = metadata.get(META_INGESTION_SOURCE)
    if source not in ALLOWED_INGESTION_SOURCES:
        errors.append("ingestion_source must be one of: {0}".format(", ".join(ALLOWED_INGESTION_SOURCES)))

    return len(errors) == 0, errors


def create_metadata_record(
    original_filename,
    file_type,
    file_size_bytes,
    upload_timestamp,
    ingestion_source=INGESTION_SOURCE_UI,
    document_id=None
):
    # type: (str, str, int, str, str, str) -> dict
    """
    Build metadata record in canonical format.
    """
    record = {
        META_ORIGINAL_FILENAME: original_filename,
        META_FILE_TYPE: file_type,
        META_FILE_SIZE_BYTES: file_size_bytes,
        META_UPLOAD_TIMESTAMP: upload_timestamp,
        META_INGESTION_SOURCE: ingestion_source,
    }
    if document_id is not None:
        record[META_DOCUMENT_ID] = document_id
    return record
