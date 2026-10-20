"""
Fixed-size chunking: the Table Challenge baseline (tasks 5.1, 5.2).
Python 3.6 compatible.

FixedSizeCharChunker cuts text into exact character windows with a fixed
overlap. It ignores words, paragraphs and table rows on purpose: it is the
naive baseline (with PdfTextExtractor) that the table-aware method is measured
against. A structure-aware chunker (task 5.6) will be added beside it, not
instead of it; chunks are stored per chunker name so both can coexist.

Sizes are characters, not tokens, because no tokenizer is chosen yet (it
depends on the embedding model decision).
"""

from bisect import bisect_right

from ingestion.ingestion_error_model import ERROR_EMPTY_CONTENT, IngestionStageError
from ingestion.ingestion_stage_contracts import ChunkingStage


class ChunkingError(IngestionStageError):
    """Raised by chunkers with a canonical ingestion error code."""


def make_chunk_id(document_id, chunker_name, chunk_index):
    # type: (str, str, int) -> str
    """Deterministic, so reprocessing a document produces the same IDs."""
    return "{0}:{1}:{2:05d}".format(document_id, chunker_name, chunk_index)


class _PageLocator(object):
    """Maps character offsets to 1-based PDF page numbers using page_spans."""

    def __init__(self, page_spans):
        # type: (list) -> None
        self._spans = sorted(page_spans, key=lambda span: span["start"])
        self._starts = [span["start"] for span in self._spans]

    def first_page(self, offset):
        # type: (int) -> int
        """Page containing offset; an offset in a page separator maps to the next non-empty page."""
        i = max(bisect_right(self._starts, offset) - 1, 0)
        while i + 1 < len(self._spans) and (
            offset >= self._spans[i]["end"] or self._spans[i]["start"] == self._spans[i]["end"]
        ):
            i += 1
        return self._spans[i]["page"]

    def last_page(self, offset):
        # type: (int) -> int
        """Page containing offset; an offset in a page separator maps to the previous page."""
        i = max(bisect_right(self._starts, offset) - 1, 0)
        while i > 0 and self._spans[i]["start"] == self._spans[i]["end"]:
            i -= 1  # skip empty pages
        return self._spans[i]["page"]


class FixedSizeCharChunker(ChunkingStage):
    """
    Baseline chunker: exact windows of chunk_size characters, each starting
    chunk_size - overlap characters after the previous one.

    Chunk shape:
    {
        "chunk_id": str, "document_id": str, "kb_id": str, "chunk_index": int,
        "text": str, "start": int, "end": int,
        "page_start": int|None, "page_end": int|None, "chunker": str
    }
    start/end are [start, end) offsets into full_text. Pages are set only when
    metadata carries PDF page_spans.
    """

    name = "fixed-size-char-baseline"

    def __init__(self, chunk_size, overlap):
        # type: (int, int) -> None
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        if not isinstance(overlap, int) or overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be an integer >= 0 and < chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    @classmethod
    def from_config(cls, config):
        return cls(config.chunk_size_chars, config.chunk_overlap_chars)

    def chunk_text(self, full_text, metadata=None):
        # type: (str, dict) -> list
        return list(self.iter_chunks(full_text, metadata))

    def iter_chunks(self, full_text, metadata=None):
        """
        Validate eagerly, then return a generator of chunks.

        Chunks are produced one at a time so long documents are never held as
        a full list of chunks; persistence consumes them in batches.
        """
        if not isinstance(full_text, str) or not full_text.strip():
            raise ChunkingError(ERROR_EMPTY_CONTENT, "Document has no text to chunk.")
        metadata = metadata or {}
        page_spans = metadata.get("page_spans")
        locator = _PageLocator(page_spans) if page_spans else None
        return self._generate(full_text, metadata.get("document_id"), metadata.get("kb_id"), locator)

    def _generate(self, full_text, document_id, kb_id, locator):
        step = self.chunk_size - self.overlap
        length = len(full_text)
        start = 0
        index = 0
        while True:
            end = min(start + self.chunk_size, length)
            yield {
                "chunk_id": make_chunk_id(document_id, self.name, index),
                "document_id": document_id,
                "kb_id": kb_id,
                "chunk_index": index,
                "text": full_text[start:end],
                "start": start,
                "end": end,
                "page_start": locator.first_page(start) if locator else None,
                "page_end": locator.last_page(end - 1) if locator else None,
                "chunker": self.name,
            }
            if end >= length:
                return
            start += step
            index += 1
