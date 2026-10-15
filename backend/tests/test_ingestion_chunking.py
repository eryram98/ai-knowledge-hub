"""Tasks 5.1, 5.2: fixed-size character chunker (Table Challenge baseline)."""

import os
import sys
import time
import types
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_chunking import ChunkingError, FixedSizeCharChunker, make_chunk_id
from ingestion.ingestion_error_model import ERROR_EMPTY_CONTENT
from ingestion.ingestion_stage_contracts import (
    CHUNKING_REQUIRED_METHODS, ChunkingStage, ensure_contract_implemented,
)
from ingestion.ingestion_text_extraction import PdfTextExtractor

META = {"document_id": "doc-1", "kb_id": "kb_a"}


def page_spans(page_texts):
    """Build page_spans exactly as PdfTextExtractor does."""
    spans, cursor = [], 0
    for number, text in enumerate(page_texts, start=1):
        if spans:
            cursor += len(PdfTextExtractor.PAGE_SEPARATOR)
        spans.append({"page": number, "start": cursor, "end": cursor + len(text)})
        cursor += len(text)
    return PdfTextExtractor.PAGE_SEPARATOR.join(page_texts), spans


class TestFixedSizeCharChunker(unittest.TestCase):
    def test_contract_and_name(self):
        chunker = FixedSizeCharChunker(10, 2)
        self.assertIsInstance(chunker, ChunkingStage)
        self.assertTrue(ensure_contract_implemented(chunker, CHUNKING_REQUIRED_METHODS)[0])
        self.assertEqual(chunker.name, "fixed-size-char-baseline")

    def test_short_text_is_one_chunk(self):
        chunks = FixedSizeCharChunker(100, 20).chunk_text("short text", META)
        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual((chunk["start"], chunk["end"], chunk["text"]), (0, 10, "short text"))
        self.assertEqual((chunk["document_id"], chunk["kb_id"], chunk["chunk_index"]), ("doc-1", "kb_a", 0))
        self.assertEqual(chunk["chunk_id"], make_chunk_id("doc-1", FixedSizeCharChunker.name, 0))

    def test_windows_overlap_and_match_offsets(self):
        text = "".join(chr(ord("a") + i % 26) for i in range(95))
        chunks = FixedSizeCharChunker(20, 5).chunk_text(text, META)
        self.assertEqual([c["start"] for c in chunks], [0, 15, 30, 45, 60, 75])
        self.assertEqual(chunks[-1]["end"], 95)
        for chunk in chunks:
            self.assertEqual(chunk["text"], text[chunk["start"]:chunk["end"]])
            self.assertLessEqual(len(chunk["text"]), 20)
        for previous, current in zip(chunks, chunks[1:]):
            self.assertEqual(previous["end"] - current["start"], 5)
        self.assertEqual([c["chunk_index"] for c in chunks], list(range(6)))

    def test_no_redundant_tail_chunk(self):
        # The window [15, 35) reaches the end, so nothing starts at 30.
        chunks = FixedSizeCharChunker(20, 5).chunk_text("x" * 35, META)
        self.assertEqual([(c["start"], c["end"]) for c in chunks], [(0, 20), (15, 35)])

    def test_zero_overlap(self):
        chunks = FixedSizeCharChunker(10, 0).chunk_text("y" * 30, META)
        self.assertEqual([(c["start"], c["end"]) for c in chunks], [(0, 10), (10, 20), (20, 30)])

    def test_empty_and_whitespace_text_fail_with_empty_content(self):
        chunker = FixedSizeCharChunker(10, 2)
        for text in ("", "   \n\t ", None):
            with self.assertRaises(ChunkingError) as ctx:
                chunker.iter_chunks(text, META)  # raised eagerly, before iteration
            self.assertEqual(ctx.exception.error_code, ERROR_EMPTY_CONTENT)

    def test_invalid_parameters(self):
        for size, overlap in ((0, 0), (-5, 0), (10, 10), (10, 11), (10, -1), ("10", 2)):
            with self.assertRaises(ValueError):
                FixedSizeCharChunker(size, overlap)

    def test_non_pdf_chunks_have_no_pages(self):
        chunk = FixedSizeCharChunker(10, 2).chunk_text("plain text file", META)[0]
        self.assertIsNone(chunk["page_start"])
        self.assertIsNone(chunk["page_end"])

    def test_pdf_page_mapping(self):
        # Page 1 = [0, 10), separator [10, 12), page 2 = [12, 22), separator, page 3 = [24, 34)
        text, spans = page_spans(["A" * 10, "B" * 10, "C" * 10])
        metadata = dict(META, page_spans=spans)
        chunks = FixedSizeCharChunker(8, 0).chunk_text(text, metadata)
        pages = [(c["start"], c["page_start"], c["page_end"]) for c in chunks]
        self.assertEqual(pages, [(0, 1, 1), (8, 1, 2), (16, 2, 2), (24, 3, 3), (32, 3, 3)])
        # [0, 11) ends inside the separator: previous page.
        # [11, 22) starts inside the separator: next page.
        chunks = FixedSizeCharChunker(11, 0).chunk_text(text, metadata)
        self.assertEqual((chunks[0]["end"], chunks[0]["page_end"]), (11, 1))
        self.assertEqual((chunks[1]["start"], chunks[1]["page_start"]), (11, 2))

    def test_empty_pdf_page_is_skipped_in_page_mapping(self):
        # Page 1 = [0, 10), empty page 2 = [12, 12), page 3 = [14, 24)
        text, spans = page_spans(["A" * 10, "", "C" * 10])
        metadata = dict(META, page_spans=spans)
        chunks = FixedSizeCharChunker(10, 0).chunk_text(text, metadata)
        self.assertEqual((chunks[0]["page_start"], chunks[0]["page_end"]), (1, 1))
        self.assertEqual((chunks[1]["start"], chunks[1]["page_start"]), (10, 3))
        # [0, 13) ends in the separator after the empty page: last non-empty page is 1.
        chunk = FixedSizeCharChunker(13, 0).chunk_text(text, metadata)[0]
        self.assertEqual(chunk["page_end"], 1)

    def test_long_text_streams_quickly(self):
        text = "abcdefghij" * 100000  # 1M characters
        chunker = FixedSizeCharChunker(1000, 200)
        started = time.perf_counter()
        chunks = chunker.iter_chunks(text, META)
        self.assertIsInstance(chunks, types.GeneratorType)
        count = 0
        last_end = 0
        for chunk in chunks:
            count += 1
            last_end = chunk["end"]
        elapsed = time.perf_counter() - started
        self.assertEqual(count, 1250)  # ceil((1,000,000 - 1000) / 800) + 1
        self.assertEqual(last_end, len(text))
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
