"""Tasks 6.2, 6.3, 6.5: full text and chunk persistence, idempotent on re-run."""

import os
import sqlite3
import sys
import tempfile
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_artifact_repository import INSERT_BATCH_SIZE, SQLiteArtifactRepository
from ingestion.ingestion_chunking import FixedSizeCharChunker
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput

KB_ID = IngestionConfig().allowed_kb_ids[0]


class TestArtifactRepository(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = os.path.join(directory.name, "artifacts.sqlite3")
        status_repository = SQLiteIngestionStatusRepository(path)
        self.repository = SQLiteArtifactRepository(path)
        entry = IngestionUploadService(status_repository=status_repository).create_upload_request(
            [UploadFileInput("notes.txt", 10, "2026-10-10T12:00:00Z")], KB_ID
        )["files"][0]
        self.document_id = entry["document_id"]
        self.chunker = FixedSizeCharChunker(10, 2)

    def save(self, text, chunker=None, chunks=None):
        chunker = chunker or self.chunker
        if chunks is None:
            chunks = chunker.iter_chunks(text, {"document_id": self.document_id, "kb_id": KB_ID})
        return self.repository.save_document_artifacts(
            self.document_id, KB_ID, text, {"extractor": "txt-decode"}, chunker.name, chunks,
        )

    def test_save_and_read_back(self):
        text = "The quick brown fox jumps over the lazy dog."
        saved = self.save(text)
        stored = self.repository.get_full_text(self.document_id)
        self.assertEqual(stored["full_text"], text)
        self.assertEqual(stored["char_count"], len(text))
        self.assertEqual(stored["kb_id"], KB_ID)
        self.assertEqual(stored["extraction_metadata"], {"extractor": "txt-decode"})
        chunks = self.repository.get_chunks(self.document_id)
        self.assertEqual(len(chunks), saved)
        self.assertEqual([c["chunk_index"] for c in chunks], list(range(saved)))
        for chunk in chunks:
            self.assertEqual(chunk["text"], text[chunk["start_offset"]:chunk["end_offset"]])
            self.assertEqual(chunk["kb_id"], KB_ID)
            self.assertIsNone(chunk["page_start"])

    def test_resave_replaces_instead_of_duplicating(self):
        self.save("a" * 100)
        first = self.repository.count_chunks(document_id=self.document_id)
        self.save("a" * 100)
        self.assertEqual(self.repository.count_chunks(document_id=self.document_id), first)
        self.save("b" * 20)  # shorter text: stale chunks must be removed
        self.assertEqual(self.repository.count_chunks(document_id=self.document_id), 3)  # [0,10) [8,18) [16,20)
        self.assertEqual(self.repository.get_full_text(self.document_id)["full_text"], "b" * 20)

    def test_chunkers_coexist(self):
        class OtherChunker(FixedSizeCharChunker):
            name = "structure-aware-test"

        self.save("c" * 50)
        self.save("c" * 50, chunker=OtherChunker(25, 0))
        self.assertEqual(self.repository.count_chunks(chunker=FixedSizeCharChunker.name), 6)
        self.assertEqual(self.repository.count_chunks(chunker="structure-aware-test"), 2)
        self.assertEqual(self.repository.count_chunks(kb_id=KB_ID), 8)

    def test_failure_mid_stream_rolls_back(self):
        self.save("d" * 30)
        before = self.repository.get_chunks(self.document_id)

        def failing_chunks():
            for chunk in self.chunker.iter_chunks("e" * 10000, {"document_id": self.document_id}):
                if chunk["chunk_index"] == INSERT_BATCH_SIZE + 5:  # after one batch was written
                    raise RuntimeError("chunker crashed")
                yield chunk

        with self.assertRaises(RuntimeError):
            self.save("e" * 10000, chunks=failing_chunks())
        self.assertEqual(self.repository.get_chunks(self.document_id), before)
        self.assertEqual(self.repository.get_full_text(self.document_id)["full_text"], "d" * 30)

    def test_unknown_document_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.save_document_artifacts(
                "doc-missing", KB_ID, "text", {}, self.chunker.name,
                self.chunker.iter_chunks("text", {"document_id": "doc-missing"}),
            )
        self.assertIsNone(self.repository.get_full_text("doc-missing"))

    def test_rejects_in_memory_database(self):
        with self.assertRaises(ValueError):
            SQLiteArtifactRepository(":memory:")


if __name__ == "__main__":
    unittest.main()
