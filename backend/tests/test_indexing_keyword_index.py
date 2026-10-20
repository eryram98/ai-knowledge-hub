"""BM25KeywordIndex over chunks in a temp SQLite database (F2)."""

from contextlib import closing
import os
import sqlite3
import sys
import tempfile
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from indexing.indexing_keyword_index import BM25KeywordIndex
from ingestion.ingestion_artifact_repository import SQLiteArtifactRepository
from ingestion.ingestion_chunking import make_chunk_id
from ingestion.ingestion_metadata_contract import create_metadata_record
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository

KB_A = "hw_datasheets"
KB_B = "it_policies"
CHUNKER = "fixed-size-char-baseline"
OTHER_CHUNKER = "table-safe"


class KeywordIndexTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = os.path.join(directory.name, "kw.sqlite3")
        self.status_repository = SQLiteIngestionStatusRepository(self.db_path)
        self.artifact_repository = SQLiteArtifactRepository(self.db_path)
        self.index = BM25KeywordIndex(self.artifact_repository)

    def add_document(self, kb_id, texts, chunker=CHUNKER, finish=True, file_name="doc.txt"):
        """Register a document, store its chunks, and (by default) mark it success. Returns its ID."""
        self.counter = getattr(self, "counter", 0) + 1
        document_id = "doc-{0:03d}".format(self.counter)
        metadata = create_metadata_record(file_name, "txt", 10, "2026-10-20T12:00:00Z", kb_id=kb_id,
                                          document_id=document_id)
        self.status_repository.create_queued(metadata)
        chunks = [
            {"chunk_id": make_chunk_id(document_id, chunker, i), "chunk_index": i, "text": text,
             "start": 0, "end": len(text)}
            for i, text in enumerate(texts)
        ]
        self.artifact_repository.save_document_artifacts(document_id, kb_id, " ".join(texts), {}, chunker, chunks)
        if finish:
            self.status_repository.mark_processing(document_id)
            self.status_repository.mark_success(document_id)
        return document_id


class TestBM25KeywordIndex(KeywordIndexTestCase):
    def test_identifier_query_ranks_the_matching_chunk_first(self):
        doc = self.add_document(KB_A, [
            "The RP2040 has dual Cortex-M0+ cores.",
            "GPIO17 is UART0 RX on the Pico.",
            "Supply voltage is 3.3V; do not exceed it.",
            "The board measures 51 by 21 mm.",
        ])
        hits = self.index.query(KB_A, "Which function does gpio17 have?", CHUNKER, top_k=3)
        self.assertEqual(hits[0][0], make_chunk_id(doc, CHUNKER, 1))
        self.assertEqual(self.index.query(KB_A, "3.3v", CHUNKER, top_k=3)[0][0], make_chunk_id(doc, CHUNKER, 2))
        self.assertEqual(self.index.query(KB_A, "rp2040", CHUNKER, top_k=3)[0][0], make_chunk_id(doc, CHUNKER, 0))

    def test_results_are_ordered_capped_and_only_matches(self):
        self.add_document(KB_A, ["gpio gpio gpio", "gpio pins", "unrelated text", "another gpio"])
        hits = self.index.query(KB_A, "gpio", CHUNKER, top_k=2)
        self.assertEqual(len(hits), 2)
        self.assertGreaterEqual(hits[0][1], hits[1][1])
        all_hits = self.index.query(KB_A, "gpio", CHUNKER, top_k=10)
        self.assertEqual(len(all_hits), 3)
        self.assertEqual(self.index.query(KB_A, "nothing matches", CHUNKER, top_k=5), [])
        self.assertEqual(self.index.query(KB_A, "gpio", CHUNKER, top_k=0), [])

    def test_single_chunk_kb_still_matches(self):
        # BM25Okapi gives a term found in every chunk a negative IDF; it must still be a hit.
        doc = self.add_document(KB_A, ["only chunk about gpio17"])
        self.assertEqual([h[0] for h in self.index.query(KB_A, "gpio17", CHUNKER, top_k=5)],
                         [make_chunk_id(doc, CHUNKER, 0)])

    def test_chunker_filter(self):
        doc = self.add_document(KB_A, ["gpio17 in baseline"])
        self.artifact_repository.save_document_artifacts(doc, KB_A, "x", {}, OTHER_CHUNKER, [
            {"chunk_id": make_chunk_id(doc, OTHER_CHUNKER, 0), "chunk_index": 0, "text": "gpio17 in table chunk",
             "start": 0, "end": 1},
        ])
        self.assertEqual([h[0] for h in self.index.query(KB_A, "gpio17", CHUNKER, 5)], [make_chunk_id(doc, CHUNKER, 0)])
        self.assertEqual([h[0] for h in self.index.query(KB_A, "gpio17", OTHER_CHUNKER, 5)],
                         [make_chunk_id(doc, OTHER_CHUNKER, 0)])

    def test_kbs_are_isolated(self):
        self.add_document(KB_A, ["gpio17 datasheet"])
        self.assertEqual(self.index.query(KB_B, "gpio17", CHUNKER, 5), [])

    def test_only_documents_in_success_are_searchable(self):
        pending = self.add_document(KB_A, ["gpio17 while processing"], finish=False)
        self.assertEqual(self.index.query(KB_A, "gpio17", CHUNKER, 5), [])
        self.status_repository.mark_processing(pending)
        self.status_repository.mark_success(pending)
        # Cached until invalidated.
        self.assertEqual(self.index.query(KB_A, "gpio17", CHUNKER, 5), [])
        self.index.invalidate(KB_A)
        self.assertEqual(len(self.index.query(KB_A, "gpio17", CHUNKER, 5)), 1)

    def test_invalidate_drops_every_chunker_of_that_kb_only(self):
        self.add_document(KB_A, ["alpha"])
        self.add_document(KB_B, ["alpha"])
        self.index.query(KB_A, "alpha", CHUNKER, 5)
        self.index.query(KB_A, "alpha", OTHER_CHUNKER, 5)
        self.index.query(KB_B, "alpha", CHUNKER, 5)
        self.index.invalidate(KB_A)
        self.assertEqual(set(self.index._indexes), {(KB_B, CHUNKER)})

    def test_empty_corpus_and_tokenless_corpus(self):
        self.assertEqual(self.index.query(KB_A, "gpio", CHUNKER, 5), [])
        self.add_document(KB_B, ["...", "--"])
        self.assertEqual(self.index.query(KB_B, "gpio", CHUNKER, 5), [])
        self.assertEqual(self.index.query(KB_A, "", CHUNKER, 5), [])


class TestListKbChunks(KeywordIndexTestCase):
    def test_returns_success_chunks_of_one_kb_and_chunker_in_order(self):
        first = self.add_document(KB_A, ["a0", "a1"])
        self.add_document(KB_A, ["pending"], finish=False)
        failed = self.add_document(KB_A, ["failed"], finish=False)
        self.status_repository.mark_processing(failed)
        self.status_repository.mark_failed(failed, "boom")
        second = self.add_document(KB_A, ["b0"])
        self.add_document(KB_B, ["other kb"])
        self.assertEqual(self.artifact_repository.list_kb_chunks(KB_A, CHUNKER), [
            (make_chunk_id(first, CHUNKER, 0), "a0"),
            (make_chunk_id(first, CHUNKER, 1), "a1"),
            (make_chunk_id(second, CHUNKER, 0), "b0"),
        ])
        self.assertEqual(self.artifact_repository.list_kb_chunks(KB_A, OTHER_CHUNKER), [])
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            total = connection.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
        self.assertEqual(total, 6)


if __name__ == "__main__":
    unittest.main()
