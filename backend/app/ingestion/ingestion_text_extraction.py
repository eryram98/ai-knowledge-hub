"""
Format-specific text extraction (tasks 4.1-4.6).
Python 3.6 compatible.

Entry point: TextExtractionDispatcher, which implements the ExtractionStage
contract (extract_text(file_path, file_type) -> {"full_text", "metadata"}).

Scope notes:
  - PDF extraction is plain text only (pypdf). It does NOT preserve table
    structure and does NOT run OCR. It is the naive baseline that the
    table-aware method (Table Challenge) will be measured against, so keep it
    available even after a table-aware extractor is added.
  - Markdown is returned raw (headings, pipe tables and code fences intact).
"""

import io
import os
import re
import unicodedata

from ingestion.ingestion_error_model import (
    ERROR_EXTRACTION_FAILURE,
    ERROR_INTERNAL_FAILURE,
    ERROR_UNREADABLE_FILE,
    ERROR_UNSUPPORTED_FORMAT,
    build_ingestion_error,
)
from ingestion.ingestion_stage_contracts import ExtractionStage


# ---------------------------------------------------------------------------
# Errors (4.6)
# ---------------------------------------------------------------------------

class ExtractionError(Exception):
    """
    Raised by extractors with a canonical ingestion error code.

    str(exc) is the human-readable detail, so the worker's failure reason
    ("ExtractionError: <detail>") stays readable in the status history.
    """

    def __init__(self, error_code, details):
        # type: (str, str) -> None
        super(ExtractionError, self).__init__(details)
        self.error_code = error_code
        self.details = details


def map_extraction_exception(exc, file_name=None):
    # type: (Exception, str) -> dict
    """Map any exception raised during extraction to a standardized error payload."""
    if isinstance(exc, ExtractionError):
        return build_ingestion_error(exc.error_code, details=exc.details, file_name=file_name)
    if isinstance(exc, (IOError, OSError)):
        return build_ingestion_error(ERROR_UNREADABLE_FILE, details=str(exc), file_name=file_name)
    if isinstance(exc, (UnicodeError, ValueError)):
        return build_ingestion_error(ERROR_EXTRACTION_FAILURE, details=str(exc), file_name=file_name)
    return build_ingestion_error(
        ERROR_INTERNAL_FAILURE,
        details="{0}: {1}".format(type(exc).__name__, exc),
        file_name=file_name,
    )


# ---------------------------------------------------------------------------
# Normalization (4.5)
# ---------------------------------------------------------------------------

_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")
_INNER_SPACES = re.compile(r"[ \t]{2,}")


def normalize_text(text, preserve_layout=False):
    # type: (str, bool) -> str
    """
    Normalize extracted text into a consistent payload.

    Always: Unicode NFC, \\r\\n and \\r -> \\n, NUL and BOM characters removed.
    Unless preserve_layout: runs of spaces/tabs collapsed to one space, trailing
    spaces stripped, and runs of 3+ newlines
    collapsed to one blank line. Markdown uses preserve_layout=True because
    trailing double spaces are significant line breaks in Markdown.
    """
    if text is None:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "").replace("﻿", "")
    if not preserve_layout:
        text = _INNER_SPACES.sub(" ", text)
        text = _TRAILING_SPACES.sub("\n", text)
        text = _EXCESS_BLANK_LINES.sub("\n\n", text)
        text = text.strip()
    return text


def _base_metadata(file_type, extractor_name, full_text):
    # type: (str, str, str) -> dict
    return {
        "file_type": file_type,
        "extractor": extractor_name,
        "char_count": len(full_text),
        "line_count": full_text.count("\n") + 1 if full_text else 0,
        "is_empty": len(full_text.strip()) == 0,
    }


def _read_bytes(file_path):
    # type: (str) -> bytes
    if not file_path or not os.path.isfile(file_path):
        raise ExtractionError(ERROR_UNREADABLE_FILE, "File not found: {0}".format(file_path))
    try:
        with open(file_path, "rb") as handle:
            return handle.read()
    except (IOError, OSError) as exc:
        raise ExtractionError(ERROR_UNREADABLE_FILE, "File could not be opened: {0}".format(exc))


# ---------------------------------------------------------------------------
# Encoding-safe decoding (4.2)
# ---------------------------------------------------------------------------

_BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)
# Order matters: strict UTF-8 first, then Windows-1252 (common for docs saved
# on Windows), then latin-1, which decodes any byte sequence and so never fails.
_FALLBACK_ENCODINGS = ("utf-8", "cp1252", "latin-1")


def decode_bytes(raw):
    # type: (bytes) -> tuple
    """Decode bytes to text. Returns (text, encoding_used)."""
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            try:
                return raw.decode(encoding), encoding
            except UnicodeDecodeError:
                break
    for encoding in _FALLBACK_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    # Unreachable in practice (latin-1 accepts all bytes); kept for safety.
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


# ---------------------------------------------------------------------------
# Extractors (4.2, 4.3, 4.4)
# ---------------------------------------------------------------------------

class PlainTextExtractor(ExtractionStage):
    """TXT extraction with encoding detection."""

    name = "txt-decode"

    def extract_text(self, file_path, file_type=".txt"):
        # type: (str, str) -> dict
        text, encoding = decode_bytes(_read_bytes(file_path))
        full_text = normalize_text(text)
        metadata = _base_metadata(".txt", self.name, full_text)
        metadata["encoding"] = encoding
        return {"full_text": full_text, "metadata": metadata}


class MarkdownExtractor(ExtractionStage):
    """MD extraction that keeps raw Markdown so structure is available downstream."""

    name = "md-raw"

    def extract_text(self, file_path, file_type=".md"):
        # type: (str, str) -> dict
        text, encoding = decode_bytes(_read_bytes(file_path))
        full_text = normalize_text(text, preserve_layout=True)
        metadata = _base_metadata(".md", self.name, full_text)
        metadata["encoding"] = encoding
        # Cheap structural signals for the strategy-recommendation step.
        metadata["heading_count"] = len(re.findall(r"(?m)^#{1,6}\s", full_text))
        metadata["pipe_table_rows"] = len(re.findall(r"(?m)^\s*\|.*\|\s*$", full_text))
        return {"full_text": full_text, "metadata": metadata}


class PdfTextExtractor(ExtractionStage):
    """
    Text-layer PDF extraction with pypdf. No OCR, no table structure.

    Pages are joined with a blank line. metadata["page_spans"] maps each page
    to its [start, end) character offsets in full_text, so chunks can later be
    cited by page number.
    """

    name = "pdf-pypdf-text"
    PAGE_SEPARATOR = "\n\n"

    def extract_text(self, file_path, file_type=".pdf"):
        # type: (str, str) -> dict
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError:
            raise ExtractionError(
                ERROR_EXTRACTION_FAILURE,
                "PDF support is not installed. Run: pip install -r requirements.txt",
            )

        raw = _read_bytes(file_path)
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise ExtractionError(
                    ERROR_EXTRACTION_FAILURE, "Encrypted PDFs are not supported."
                )
            pages = list(reader.pages)
        except ExtractionError:
            raise
        except PdfReadError as exc:
            raise ExtractionError(ERROR_UNREADABLE_FILE, "Invalid or corrupt PDF: {0}".format(exc))

        parts = []
        page_spans = []
        cursor = 0
        empty_pages = 0
        for page_number, page in enumerate(pages, start=1):
            try:
                page_text = normalize_text(page.extract_text() or "")
            except Exception as exc:  # pypdf raises varied errors on malformed pages
                raise ExtractionError(
                    ERROR_EXTRACTION_FAILURE,
                    "Text extraction failed on page {0}: {1}".format(page_number, exc),
                )
            if not page_text:
                empty_pages += 1
            if parts:
                cursor += len(self.PAGE_SEPARATOR)
            page_spans.append({"page": page_number, "start": cursor, "end": cursor + len(page_text)})
            parts.append(page_text)
            cursor += len(page_text)

        full_text = self.PAGE_SEPARATOR.join(parts)
        if pages and not full_text.strip():
            raise ExtractionError(
                ERROR_EXTRACTION_FAILURE,
                "PDF has no extractable text layer (likely scanned). OCR is not supported.",
            )

        metadata = _base_metadata(".pdf", self.name, full_text)
        metadata["page_count"] = len(pages)
        metadata["empty_page_count"] = empty_pages
        metadata["page_spans"] = page_spans
        return {"full_text": full_text, "metadata": metadata}


# ---------------------------------------------------------------------------
# Dispatcher (4.1)
# ---------------------------------------------------------------------------

def normalize_file_type(file_type):
    # type: (str) -> str
    """'.PDF', 'pdf', ' .pdf ' -> '.pdf'."""
    cleaned = (file_type or "").strip().lower()
    if cleaned and not cleaned.startswith("."):
        cleaned = "." + cleaned
    return cleaned


class TextExtractionDispatcher(ExtractionStage):
    """
    Routes a file to the extractor registered for its extension.

    Register a different extractor for an extension (for example a
    table-aware PDF extractor) without touching callers:
        dispatcher.register(".pdf", MyTableAwarePdfExtractor())
    """

    def __init__(self, extractors=None):
        # type: (dict) -> None
        self._extractors = {}
        defaults = {
            ".txt": PlainTextExtractor(),
            ".md": MarkdownExtractor(),
            ".pdf": PdfTextExtractor(),
        }
        for file_type, extractor in (extractors or defaults).items():
            self.register(file_type, extractor)

    def register(self, file_type, extractor):
        # type: (str, ExtractionStage) -> None
        if not callable(getattr(extractor, "extract_text", None)):
            raise TypeError("extractor must implement extract_text(file_path, file_type)")
        self._extractors[normalize_file_type(file_type)] = extractor

    def supported_types(self):
        # type: () -> tuple
        return tuple(sorted(self._extractors))

    def extract_text(self, file_path, file_type):
        # type: (str, str) -> dict
        """
        Extract and normalize text. Raises ExtractionError with a canonical
        error code on any failure; use map_extraction_exception() to turn it
        into an API/status payload.
        """
        normalized_type = normalize_file_type(file_type)
        extractor = self._extractors.get(normalized_type)
        if extractor is None:
            raise ExtractionError(
                ERROR_UNSUPPORTED_FORMAT,
                "No extractor registered for '{0}'. Supported: {1}".format(
                    normalized_type or "<none>", ", ".join(self.supported_types())
                ),
            )
        try:
            result = extractor.extract_text(file_path, normalized_type)
        except ExtractionError:
            raise
        except (IOError, OSError) as exc:
            raise ExtractionError(ERROR_UNREADABLE_FILE, str(exc))
        except Exception as exc:
            raise ExtractionError(
                ERROR_EXTRACTION_FAILURE, "{0}: {1}".format(type(exc).__name__, exc)
            )

        if not isinstance(result, dict) or not isinstance(result.get("full_text"), str):
            raise ExtractionError(
                ERROR_EXTRACTION_FAILURE,
                "Extractor returned an invalid payload for '{0}'".format(normalized_type),
            )
        result.setdefault("metadata", {})
        return result
