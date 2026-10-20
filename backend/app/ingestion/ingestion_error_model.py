"""
Standardized ingestion error model and messages.
Python 3.6 compatible.
"""

# Canonical error codes
ERROR_UNSUPPORTED_FORMAT = "unsupported_format"
ERROR_UNREADABLE_FILE = "unreadable_file"
ERROR_EXTRACTION_FAILURE = "extraction_failure"
ERROR_VALIDATION_FAILED = "validation_failed"
ERROR_FILE_TOO_LARGE = "file_too_large"
ERROR_BATCH_LIMIT_EXCEEDED = "batch_limit_exceeded"
ERROR_DUPLICATE_BLOCKED = "duplicate_blocked"
ERROR_INTERNAL_FAILURE = "internal_failure"
ERROR_UNKNOWN_KB = "unknown_kb"
ERROR_EMPTY_CONTENT = "empty_content"
ERROR_NOT_FOUND = "not_found"

INGESTION_ERROR_CODES = (
    ERROR_UNSUPPORTED_FORMAT,
    ERROR_UNREADABLE_FILE,
    ERROR_EXTRACTION_FAILURE,
    ERROR_VALIDATION_FAILED,
    ERROR_FILE_TOO_LARGE,
    ERROR_BATCH_LIMIT_EXCEEDED,
    ERROR_DUPLICATE_BLOCKED,
    ERROR_INTERNAL_FAILURE,
    ERROR_UNKNOWN_KB,
    ERROR_EMPTY_CONTENT,
    ERROR_NOT_FOUND,
)

DEFAULT_ERROR_MESSAGES = {
    ERROR_UNSUPPORTED_FORMAT: "Unsupported file format. Allowed formats are: PDF, TXT, MD.",
    ERROR_UNREADABLE_FILE: "File could not be read. The file may be corrupt or inaccessible.",
    ERROR_EXTRACTION_FAILURE: "Content extraction failed for this file.",
    ERROR_VALIDATION_FAILED: "File validation failed.",
    ERROR_FILE_TOO_LARGE: "File exceeds the maximum allowed size.",
    ERROR_BATCH_LIMIT_EXCEEDED: "Upload batch exceeds the maximum allowed number of files.",
    ERROR_DUPLICATE_BLOCKED: "Duplicate file blocked by the active duplicate policy.",
    ERROR_INTERNAL_FAILURE: "An internal error occurred during ingestion.",
    ERROR_UNKNOWN_KB: "Unknown knowledge base. Choose one of the configured KBs.",
    ERROR_EMPTY_CONTENT: "The document contains no text to index.",
    ERROR_NOT_FOUND: "The requested resource was not found.",
}


class IngestionStageError(Exception):
    """
    Base for pipeline stage errors that carry a canonical error code.

    str(exc) is the human-readable detail; the worker stores error_code
    alongside the failure reason in the status history.
    """

    def __init__(self, error_code, details):
        # type: (str, str) -> None
        super(IngestionStageError, self).__init__(details)
        self.error_code = error_code
        self.details = details


def is_valid_error_code(error_code):
    # type: (str) -> bool
    """Return True if error_code is a recognized ingestion error code."""
    return error_code in INGESTION_ERROR_CODES


def get_error_message(error_code, fallback_message=None):
    # type: (str, str) -> str
    """
    Resolve user-facing error message for an error code.
    If code is unknown, uses fallback_message or generic message.
    """
    if error_code in DEFAULT_ERROR_MESSAGES:
        return DEFAULT_ERROR_MESSAGES[error_code]
    if fallback_message:
        return fallback_message
    return "Unknown ingestion error."


def build_ingestion_error(error_code, details=None, file_name=None, field=None, fallback_message=None):
    # type: (str, str, str, str, str) -> dict
    """
    Build standardized error payload for API/service responses.
    """
    normalized_code = error_code if is_valid_error_code(error_code) else ERROR_INTERNAL_FAILURE
    message = get_error_message(normalized_code, fallback_message=fallback_message)

    payload = {
        "code": normalized_code,
        "message": message,
    }

    if details:
        payload["details"] = details
    if file_name:
        payload["file_name"] = file_name
    if field:
        payload["field"] = field

    return payload
