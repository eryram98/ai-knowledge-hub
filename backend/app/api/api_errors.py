"""Canonical error responses for the HTTP API.

Every error body is build_ingestion_error output, {code, message, details, ...},
with "details" always present (null when there is none). Stack traces are
logged on the server and never sent to the client.
"""

import logging

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ingestion.ingestion_error_model import (
    ERROR_BATCH_LIMIT_EXCEEDED,
    ERROR_DOCUMENT_BUSY,
    ERROR_DUPLICATE_BLOCKED,
    ERROR_FILE_TOO_LARGE,
    ERROR_INTERNAL_FAILURE,
    ERROR_LLM_UNAVAILABLE,
    ERROR_NOT_FOUND,
    ERROR_NOT_IMPLEMENTED,
    ERROR_UNKNOWN_KB,
    ERROR_UNREADABLE_FILE,
    ERROR_UNSUPPORTED_FORMAT,
    ERROR_VALIDATION_FAILED,
    build_ingestion_error,
)

LOGGER = logging.getLogger(__name__)

# Codes not listed here (including internal_failure) map to 500.
HTTP_STATUS_BY_CODE = {
    ERROR_VALIDATION_FAILED: 400,
    ERROR_UNKNOWN_KB: 400,
    ERROR_BATCH_LIMIT_EXCEEDED: 400,
    ERROR_UNSUPPORTED_FORMAT: 400,
    ERROR_UNREADABLE_FILE: 400,
    ERROR_NOT_FOUND: 404,
    ERROR_DUPLICATE_BLOCKED: 409,
    ERROR_DOCUMENT_BUSY: 409,
    ERROR_FILE_TOO_LARGE: 413,
    ERROR_NOT_IMPLEMENTED: 501,
    ERROR_LLM_UNAVAILABLE: 503,
}

# Framework HTTP errors (unknown route, wrong method, oversize body) keep their
# status; this picks the canonical code. Other 4xx are validation_failed.
CODE_BY_HTTP_STATUS = {
    404: ERROR_NOT_FOUND,
    413: ERROR_FILE_TOO_LARGE,
}


# Clients wait this long before retrying an llm_unavailable (503) response.
LLM_RETRY_AFTER_SECONDS = 30


def http_status_for(error_code):
    return HTTP_STATUS_BY_CODE.get(error_code, 500)


class ApiError(Exception):
    """Raise from a route with a canonical error dict; the handler sends it."""

    def __init__(self, error, status_code=None, headers=None):
        super(ApiError, self).__init__(error.get("details") or error["code"])
        self.error = error
        self.status_code = status_code if status_code is not None else http_status_for(error["code"])
        self.headers = headers


def error_response(error, status_code=None, headers=None):
    """JSONResponse for a canonical error dict, with "details" always present."""
    body = dict(error)
    body.setdefault("details", None)
    if status_code is None:
        status_code = http_status_for(body["code"])
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def _api_error_handler(request, exc):
    return error_response(exc.error, exc.status_code, exc.headers)


def _http_exception_handler(request, exc):
    status_code = exc.status_code
    if status_code >= 500:
        code = ERROR_INTERNAL_FAILURE
    else:
        code = CODE_BY_HTTP_STATUS.get(status_code, ERROR_VALIDATION_FAILED)
    details = exc.detail if isinstance(exc.detail, str) else None
    return error_response(build_ingestion_error(code, details=details), status_code, getattr(exc, "headers", None))


def _validation_error_handler(request, exc):
    # Field and message only; the rejected input is never echoed back.
    problems = []
    for item in exc.errors():
        location = [str(part) for part in item.get("loc", ()) if part not in ("body", "query", "path")]
        problems.append("{0}: {1}".format(".".join(location) or "request", item.get("msg", "invalid")))
    return error_response(build_ingestion_error(ERROR_VALIDATION_FAILED, details="; ".join(problems) or None))


def _unhandled_exception_handler(request, exc):
    LOGGER.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(build_ingestion_error(ERROR_INTERNAL_FAILURE))


def install_error_handlers(app):
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
