"""HTTP client for the knowledge hub API, used by every Streamlit page.

Every failure is raised as ApiClientError with a kind the pages can show in
plain language:
- "connection": the API isn't reachable (not started, wrong API_BASE_URL)
- "timeout": the API didn't answer in time
- "busy": 503 llm_unavailable, the LLM stayed rate-limited or overloaded
- "api": any other error response, with the canonical {code, message, details}
"""

from urllib.parse import quote

import httpx

import ui_config

KIND_CONNECTION = "connection"
KIND_TIMEOUT = "timeout"
KIND_BUSY = "busy"
KIND_API = "api"

LLM_UNAVAILABLE_CODE = "llm_unavailable"


class ApiClientError(Exception):
    def __init__(self, kind, message, code=None, details=None, status_code=None, retry_after=None):
        super(ApiClientError, self).__init__(message)
        self.kind = kind
        self.message = message
        self.code = code
        self.details = details
        self.status_code = status_code
        self.retry_after = retry_after


class ApiClient:
    """One short-lived httpx.Client per call; Streamlit reruns the page script often."""

    def __init__(self, base_url, transport=None):
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    def list_kbs(self):
        return self._request("GET", "/kbs", ui_config.DEFAULT_TIMEOUT_SECONDS)["kbs"]

    def list_documents(self, kb_id=None):
        params = {"kb_id": kb_id} if kb_id else None
        return self._request("GET", "/documents", ui_config.DEFAULT_TIMEOUT_SECONDS, params=params)["documents"]

    def upload(self, kb_id, files):
        """files: (file_name, content_bytes, mime_type) tuples. Returns the per-file upload response."""
        multipart = [("files", (name, content, mime or "application/octet-stream")) for name, content, mime in files]
        return self._request("POST", "/documents", ui_config.UPLOAD_TIMEOUT_SECONDS,
                             data={"kb_id": kb_id}, files=multipart)

    def document_statuses(self, document_ids):
        """Batch status for the given document IDs (counts, per-document status, is_complete)."""
        params = [("document_id", document_id) for document_id in document_ids]
        return self._request("GET", "/documents/status", ui_config.DEFAULT_TIMEOUT_SECONDS, params=params)

    def delete_document(self, kb_id, document_id):
        """Hard-delete one document of a KB. 404 not_found if it is gone, 409 document_busy while it is processing."""
        path = "/kbs/{0}/documents/{1}".format(quote(kb_id, safe=""), quote(document_id, safe=""))
        return self._request("DELETE", path, ui_config.DEFAULT_TIMEOUT_SECONDS)

    def ask(self, question):
        return self._request("POST", "/ask", ui_config.ASK_TIMEOUT_SECONDS, json={"question": question})

    def _request(self, method, path, timeout, **kwargs):
        url = self.base_url + path
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                response = client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            raise ApiClientError(KIND_TIMEOUT, "The API at {0} did not answer within {1:.0f} s.".format(
                self.base_url, timeout))
        except httpx.TransportError:
            raise ApiClientError(KIND_CONNECTION, "Can't reach the API at {0}.".format(self.base_url))
        if response.is_success:
            try:
                return response.json()
            except ValueError:
                raise ApiClientError(KIND_API, "The API returned a response that isn't JSON.",
                                     status_code=response.status_code)
        raise _error_from_response(response)


def _error_from_response(response):
    """ApiClientError from a canonical {code, message, details} body, or a generic one if the body isn't that."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or "code" not in body:
        return ApiClientError(KIND_API, "The API returned HTTP {0}.".format(response.status_code),
                              status_code=response.status_code)
    code = body.get("code")
    kind = KIND_BUSY if code == LLM_UNAVAILABLE_CODE else KIND_API
    return ApiClientError(
        kind, body.get("message") or code, code=code, details=body.get("details"),
        status_code=response.status_code, retry_after=_retry_after_seconds(response),
    )


def _retry_after_seconds(response):
    value = response.headers.get("Retry-After")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def get_client():
    """The client for the configured API. Tests patch this to return a fake."""
    return ApiClient(ui_config.load_config().api_base_url)
