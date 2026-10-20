"""Upload storage for the HTTP API: safe file names, size-limited copies, a request-size guard.

Starlette spools each multipart file part to a temporary file (up to 1 MB in
memory, the rest on disk) before a route runs. So the per-file limit here is
enforced while copying into the upload directory, which guarantees no
oversize bytes land there. RequestSizeLimitMiddleware is the guard that runs
while the body is still arriving, for the request as a whole.
"""

import logging
import os
import re
import shutil
import unicodedata

from starlette.exceptions import HTTPException

from api.api_errors import error_response
from ingestion.ingestion_error_model import ERROR_FILE_TOO_LARGE, build_ingestion_error

LOGGER = logging.getLogger(__name__)

COPY_CHUNK_BYTES = 1024 * 1024
# Allowance on top of the file bytes for multipart boundaries, part headers and kb_id.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024
MAX_FILENAME_CHARS = 150
FALLBACK_FILENAME = "upload"

# Path separators, characters Windows forbids in names, and control characters.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + ["COM{0}".format(n) for n in range(1, 10)]
    + ["LPT{0}".format(n) for n in range(1, 10)]
)


def sanitize_filename(raw_name):
    """Return a safe base file name for storage and display.

    Drops any directory part (both / and \\ count, so "../../x.txt" and
    "C:\\x\\y.txt" keep only the last part), replaces unsafe characters with
    "_", strips leading dots and spaces and trailing ones (Windows drops
    those), prefixes Windows device names ("CON.txt" -> "_CON.txt") and caps
    the length while keeping the extension. Never returns an empty name.
    """
    name = unicodedata.normalize("NFC", raw_name if isinstance(raw_name, str) else "")
    name = re.split(r"[\\/]", name)[-1]
    name = _UNSAFE_CHARS.sub("_", name).strip(" .")
    if not name:
        return FALLBACK_FILENAME
    if name.split(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
        name = "_" + name
    if len(name) > MAX_FILENAME_CHARS:
        stem, extension = os.path.splitext(name)
        if len(extension) >= MAX_FILENAME_CHARS:
            extension = ""
        name = stem[:MAX_FILENAME_CHARS - len(extension)].rstrip(" .") + extension
    return name


def upload_path(upload_root, document_id, file_name):
    """Return upload_root/document_id/file_name, refusing any path that escapes upload_root."""
    root = os.path.realpath(upload_root)
    path = os.path.realpath(os.path.join(root, document_id, file_name))
    if os.path.commonpath([root, path]) != root or os.path.dirname(os.path.dirname(path)) != root:
        raise ValueError("Upload path escapes the upload directory")
    return path


async def save_upload(upload, destination, max_bytes):
    """Copy an UploadFile to destination in chunks, stopping once it passes max_bytes.

    Returns (bytes_seen, too_large). A too-large file's partial copy is
    deleted, so no oversize bytes stay on disk. bytes_seen is a lower bound
    for a too-large file, because copying stops early.
    """
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    seen = 0
    too_large = False
    with open(destination, "xb") as handle:
        while True:
            chunk = await upload.read(COPY_CHUNK_BYTES)
            if not chunk:
                break
            seen += len(chunk)
            if seen > max_bytes:
                too_large = True
                break
            handle.write(chunk)
    if too_large:
        os.remove(destination)
    return seen, too_large


def remove_upload_dir(upload_root, document_id):
    """Delete one document's upload directory; log, don't raise, if Windows holds a lock."""
    directory = os.path.join(upload_root, document_id)
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        pass
    except OSError:
        LOGGER.warning("Could not remove upload directory %s", directory, exc_info=True)


def max_request_bytes(config):
    """Largest request body the API reads: a full batch of maximum-size files plus overhead."""
    return config.max_files_per_batch * config.max_file_size_bytes + MULTIPART_OVERHEAD_BYTES


class RequestSizeLimitMiddleware(object):
    """Reject request bodies over max_bytes with 413 file_too_large, while they stream in.

    A declared Content-Length over the limit is rejected before any body is
    read. Without one (chunked transfer), bytes are counted as they arrive and
    the request fails as soon as the count passes the limit.
    """

    def __init__(self, app, max_bytes):
        self.app = app
        self.max_bytes = max_bytes

    def _too_large_details(self):
        return "Request body exceeds the maximum of {0} bytes.".format(self.max_bytes)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            response = error_response(build_ingestion_error(ERROR_FILE_TOO_LARGE, details=self._too_large_details()))
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # FastAPI re-raises HTTPException from body parsing; the
                    # API's handler turns it into the canonical 413 body.
                    raise HTTPException(status_code=413, detail=self._too_large_details())
            return message

        await self.app(scope, limited_receive, send)


def _content_length(scope):
    for name, value in scope.get("headers", ()):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
