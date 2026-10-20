"""End to end: upload -> queue -> worker -> extract -> baseline chunks -> SQLite -> indexes (tasks 5.1-6.5, 8.3, F2)."""

from contextlib import closing
import os
import sqlite3
import sys
import tempfile
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from indexing_fakes import make_indexer
from pdf_fixtures import HAS_PYPDF, build_pdf

from ingestion.ingestion_artifact_repository import SQLiteArtifactRepository
from ingestion.ingestion_chunking import FixedSizeCharChunker
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_error_model import ERROR_EMPTY_CONTENT, ERROR_UNREADABLE_FILE
from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_pipeline import DocumentProcessor
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_status_service import IngestionStatusService
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput
from ingestion.ingestion_worker import start_background_worker

KB_ID = IngestionConfig().allowed_kb_ids[0]
CHUNKER = FixedSizeCharChunker.name
TXT = "Plain text knowledge. " * 10
MD = "# Title\n\n| Year | Revenue |\n|---|---|\n| 2025 | 10 |\n\nSome **markdown** body text.\n"
PDF_PAGES = ["First page of the report with some text", "Second page holds the revenue table"]


@unittest.skipUnless(HAS_PYPDF, "pypdf not installed")
class TestPipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = directory.name
        self.db_path = os.path.join(self.dir, "pipeline.sqlite3")
        self.status_repository = SQLiteIngestionStatusRepository(self.db_path)
        self.artifact_repository = SQLiteArtifactRepository(self.db_path)
        self.upload_service = IngestionUploadService(status_repository=self.status_repository)
        # Fake embedder and in-memory Chroma: no model download (F2).
        self.indexer = make_indexer(self, self.artifact_repository)
        # Small windows so every test document yields several chunks.
        self.processor = DocumentProcessor(
            self.status_repository, self.artifact_repository, chunker=FixedSizeCharChunker(30, 5),
            indexer=self.indexer,
        )

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as handle:
            handle.write(content if isinstance(content, bytes) else content.encode("utf-8"))
        return path

    def upload(self, files):
        inputs = [
            UploadFileInput(name, os.path.getsize(path), "2026-10-15T12:00:00Z", temp_file_path=path)
            for name, path in files
        ]
        response = self.upload_service.create_upload_request(inputs, KB_ID)
        self.assertEqual(response["status"], "received", response["errors"])
        return {entry["metadata"]["original_filename"]: entry for entry in response["files"]}

    def run_worker_on(self, entries):
        queue = InMemoryIngestionJobQueue()
        for entry in entries.values():
            queue.enqueue(IngestionJob(entry["document_id"], entry["temp_file_path"], entry["metadata"]))
        thread, stop = start_background_worker(queue, self.processor, status_repository=self.status_repository)
        try:
            queue.join()
        finally:
            stop.set()
            thread.join()

    def status(self, entry):
        return IngestionStatusService(self.status_repository).get_document_status(entry["document_id"])

    def test_txt_md_pdf_are_chunked_and_persisted(self):
        entries = self.upload([
            ("notes.txt", self.write("notes.txt", TXT)),
            ("readme.md", self.write("readme.md", MD)),
            ("report.pdf", self.write("report.pdf", build_pdf(PDF_PAGES))),
        ])
        self.run_worker_on(entries)

        for name, entry in entries.items():
            document_id = entry["document_id"]
            self.assertEqual(self.status(entry)["ingestion_status"], "success", name)
            text = self.artifact_repository.get_full_text(document_id)
            self.assertIsNotNone(text, name)
            chunks = self.artifact_repository.get_chunks(document_id, CHUNKER)
            self.assertGreater(len(chunks), 1, name)
            self.assertEqual(self.indexer.vector_index.count(KB_ID, document_id=document_id), len(chunks), name)
            for chunk in chunks:
                self.assertEqual(chunk["document_id"], document_id)
                self.assertEqual(chunk["kb_id"], KB_ID)
                self.assertEqual(chunk["text"], text["full_text"][chunk["start_offset"]:chunk["end_offset"]])

        self.assertEqual(self.artifact_repository.get_full_text(entries["readme.md"]["document_id"])["full_text"], MD)
        for name in ("notes.txt", "readme.md"):
            for chunk in self.artifact_repository.get_chunks(entries[name]["document_id"]):
                self.assertIsNone(chunk["page_start"])
                self.assertIsNone(chunk["page_end"])
        pdf_chunks = self.artifact_repository.get_chunks(entries["report.pdf"]["document_id"])
        self.assertEqual(pdf_chunks[0]["page_start"], 1)
        self.assertEqual(pdf_chunks[-1]["page_end"], 2)
        self.assertTrue(all(c["page_start"] in (1, 2) for c in pdf_chunks))

        # Chunks are queryable straight from the database, per KB.
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            rows = connection.execute(
                "SELECT document_id, COUNT(*) FROM document_chunks WHERE kb_id = ? GROUP BY document_id",
                (KB_ID,),
            ).fetchall()
        self.assertEqual({row[0] for row in rows}, {e["document_id"] for e in entries.values()})

    def test_failures_get_canonical_codes_without_blocking_others(self):
        entries = self.upload([
            ("empty.txt", self.write("empty.txt", "  \n\n ")),
            ("broken.pdf", self.write("broken.pdf", b"this is not a pdf")),
            ("good.txt", self.write("good.txt", TXT)),
        ])
        with self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            self.run_worker_on(entries)

        empty = self.status(entries["empty.txt"])
        self.assertEqual((empty["ingestion_status"], empty["failure_code"]), ("failed", ERROR_EMPTY_CONTENT))
        broken = self.status(entries["broken.pdf"])
        self.assertEqual((broken["ingestion_status"], broken["failure_code"]), ("failed", ERROR_UNREADABLE_FILE))
        self.assertEqual(self.status(entries["good.txt"])["ingestion_status"], "success")
        for name in ("empty.txt", "broken.pdf"):
            document_id = entries[name]["document_id"]
            self.assertIsNone(self.artifact_repository.get_full_text(document_id))
            self.assertEqual(self.artifact_repository.count_chunks(document_id=document_id), 0)

    def test_reprocessing_does_not_duplicate_chunks(self):
        entry = self.upload([("notes.txt", self.write("notes.txt", TXT))])["notes.txt"]
        job = IngestionJob(entry["document_id"], entry["temp_file_path"])
        first = self.processor(job)
        second = self.processor(job)
        self.assertEqual(first, second)
        self.assertEqual(self.artifact_repository.count_chunks(document_id=entry["document_id"]), first)
        self.assertEqual(self.indexer.vector_index.count(KB_ID, document_id=entry["document_id"]), first)


if __name__ == "__main__":
    unittest.main()
