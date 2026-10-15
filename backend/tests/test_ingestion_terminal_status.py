"""Task 3.5: durable terminal states, transition rules, and worker outcomes."""

from contextlib import closing
import os
import sqlite3
import sys
import tempfile
import unittest
from threading import Event

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput
from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_worker import run_worker

# First configured KB, so a local .env with real KB IDs does not break tests
KB_ID = IngestionConfig().allowed_kb_ids[0]


class TestTerminalStatus(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "status.sqlite3")
        self.repository = SQLiteIngestionStatusRepository(self.path)
        entry = IngestionUploadService(status_repository=self.repository).create_upload_request([
            UploadFileInput("notes.txt", 10, "2026-10-10T12:00:00Z")
        ], KB_ID)["files"][0]
        self.document_id = entry["document_id"]

    def test_success_persists_without_duplicate_history(self):
        self.repository.mark_processing(self.document_id)
        self.assertTrue(self.repository.mark_success(self.document_id))
        self.assertFalse(self.repository.mark_success(self.document_id))
        reopened = SQLiteIngestionStatusRepository(self.path)
        self.assertEqual(reopened.get_document(self.document_id)["ingestion_status"], "success")
        history = reopened.get_status_history(self.document_id)
        self.assertEqual([row["status"] for row in history], ["queued", "processing", "success"])
        self.assertIsNone(history[-1]["reason"])

    def test_failure_reason_survives_restart(self):
        self.repository.mark_processing(self.document_id)
        self.repository.mark_failed(self.document_id, "Unreadable document")
        reopened = SQLiteIngestionStatusRepository(self.path)
        self.assertEqual(reopened.get_document(self.document_id)["ingestion_status"], "failed")
        self.assertEqual(reopened.get_status_history(self.document_id)[-1]["reason"], "Unreadable document")
        self.assertFalse(reopened.mark_failed(self.document_id, "Different reason"))
        self.assertEqual(reopened.get_status_history(self.document_id)[-1]["reason"], "Unreadable document")

    def test_invalid_transitions_and_empty_reason(self):
        with self.assertRaises(ValueError):
            self.repository.mark_success(self.document_id)
        with self.assertRaises(ValueError):
            self.repository.mark_failed(self.document_id, " ")
        with self.assertRaises(KeyError):
            self.repository.mark_success("missing")
        self.repository.mark_processing(self.document_id)
        self.repository.mark_success(self.document_id)
        with self.assertRaises(ValueError):
            self.repository.mark_failed(self.document_id, "Cannot overwrite success")
        self.assertEqual(len(self.repository.get_status_history(self.document_id)), 3)

    def test_terminal_history_failure_rolls_back_status(self):
        self.repository.mark_processing(self.document_id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER reject_terminal BEFORE INSERT ON ingestion_status_history WHEN NEW.status IN ('success', 'failed') BEGIN SELECT RAISE(ABORT, 'test storage failure'); END")
        for finish in (lambda: self.repository.mark_success(self.document_id),
                       lambda: self.repository.mark_failed(self.document_id, "Failure")):
            with self.assertRaises(sqlite3.IntegrityError):
                finish()
            self.assertEqual(self.repository.get_document(self.document_id)["ingestion_status"], "processing")
            self.assertEqual(len(self.repository.get_status_history(self.document_id)), 2)

    def run_one(self, processor):
        queue = InMemoryIngestionJobQueue()
        queue.enqueue(IngestionJob(self.document_id, "notes.txt"))
        stop = Event()
        original_done = queue.task_done

        def done():
            original_done()
            stop.set()

        queue.task_done = done
        run_worker(queue, processor, stop, status_repository=self.repository)
        queue.join()

    def test_worker_persists_success(self):
        self.run_one(lambda job: None)
        self.assertEqual(self.repository.get_document(self.document_id)["ingestion_status"], "success")

    def test_worker_persists_failure_reason(self):
        def fail(job):
            raise RuntimeError("Text extraction failed")

        with self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            self.run_one(fail)
        self.assertEqual(self.repository.get_document(self.document_id)["ingestion_status"], "failed")
        self.assertEqual(self.repository.get_status_history(self.document_id)[-1]["reason"], "RuntimeError: Text extraction failed")

    def test_worker_logs_terminal_storage_failure_without_false_success(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER reject_success BEFORE INSERT ON ingestion_status_history WHEN NEW.status = 'success' BEGIN SELECT RAISE(ABORT, 'test storage failure'); END")
        with self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            self.run_one(lambda job: None)
        self.assertEqual(self.repository.get_document(self.document_id)["ingestion_status"], "processing")
        self.assertEqual(len(self.repository.get_status_history(self.document_id)), 2)


if __name__ == "__main__":
    unittest.main()
