"""Plain-language text for the API's canonical error codes and lifecycle states.

The code strings are copied from backend/app/ingestion/ingestion_error_model.py
and ingestion_status_constants.py on purpose: the UI talks to the API over HTTP
only and never imports backend modules. A code missing here falls back to the
message the API sent.
"""

import ui_config
from ui_api_client import KIND_BUSY, KIND_CONNECTION, KIND_TIMEOUT

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"

ERROR_TEXT = {
    "unsupported_format": "This file type isn't supported. Upload a PDF, TXT or MD file.",
    "unreadable_file": "The file couldn't be read. It may be corrupt, empty or password-protected.",
    "extraction_failure": "The text couldn't be extracted from this file.",
    "validation_failed": "The request wasn't valid.",
    "file_too_large": "The file is larger than the upload limit (25 MB by default).",
    "batch_limit_exceeded": "Too many files in one upload. Upload fewer files at a time.",
    "duplicate_blocked": "This file is already in the knowledge base.",
    "internal_failure": "Something went wrong on the server.",
    "unknown_kb": "That knowledge base doesn't exist. Pick one from the list.",
    "empty_content": "The file has no text to index (for example, a scanned PDF without a text layer).",
    "not_found": "The API couldn't find what was requested.",
    "indexing_failure": "The file was read, but indexing it for search failed.",
    "not_implemented": "This step isn't implemented on the server yet.",
    "llm_unavailable": "The language model is busy or rate-limited right now.",
}

# Reasons the server writes without a dedicated code, with a clearer text.
REASON_TEXT = {
    "interrupted by server restart": "Processing stopped because the server restarted. Upload the file again.",
}

STATUS_LABELS = {
    "queued": "⏳ Queued",
    "processing": "⚙️ Processing",
    "success": "✅ Ready",
    "failed": "❌ Failed",
}


def describe_error(code, fallback=None):
    """Plain-language text for a canonical error code, else the fallback (the API's message), else the code."""
    return ERROR_TEXT.get(code) or fallback or code or "Unknown error."


def describe_failure(code, reason):
    """Plain-language text for a failed document's failure_code and failure_reason."""
    if reason in REASON_TEXT:
        return REASON_TEXT[reason]
    return describe_error(code, fallback=reason)


def status_label(status):
    return STATUS_LABELS.get(status, status)


def client_error_text(exc):
    """(level, text) for an ApiClientError: "warning" for a busy LLM, "error" for everything else."""
    if exc.kind == KIND_CONNECTION:
        return LEVEL_ERROR, "{0} Is the API running? Start it from the repo root with:\n\n`{1}`".format(
            exc.message, ui_config.API_START_COMMAND)
    if exc.kind == KIND_TIMEOUT:
        return LEVEL_ERROR, exc.message + " The server may still be working on it. Try again in a moment."
    if exc.kind == KIND_BUSY:
        wait = "about {0} s".format(exc.retry_after) if exc.retry_after else "a minute"
        return LEVEL_WARNING, "The language model is busy or rate-limited right now. Try again in {0}.".format(wait)
    text = describe_error(exc.code, fallback=exc.message)
    if exc.details:
        text += " ({0})".format(exc.details)
    return LEVEL_ERROR, text
