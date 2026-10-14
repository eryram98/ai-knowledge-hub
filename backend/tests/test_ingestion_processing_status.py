"""Task 3.3: atomic claims and persistence before worker processing."""

import os
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput
from ingestion.ingestion_worker import run_worker
from threading import Event


class TestProcessingStatus(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "status.sqlite3")
        self.repository = SQLiteIngestionStatusRepository(self.path)
        service = IngestionUploadService(status_repository=self.repository)
        self.entry = service.create_upload_request([
            UploadFileInput("notes.txt", 10, "2026-10-10T12:00:00Z")
        ])["files"][0]
        self.document_id = self.entry["document_id"]

    def test_processing_survives_restart_and_duplicate_claim(self):
        self.assertTrue(self.repository.mark_processing(self.document_id))
        reopened = SQLiteIngestionStatusRepository(self.path)
        self.assertEqual(reopened.get_document(self.document_id)["ingestion_status"], "processing")
        self.assertFalse(reopened.mark_processing(self.document_id))
        history = reopened.get_status_history(self.document_id)
        self.assertEqual([row["status"] for row in history], ["queued", "processing"])
        self.assertIsNone(history[1]["reason"])
        self.assertTrue(history[1]["timestamp"].endswith("Z"))

    def test_concurrent_claims_only_one_wins(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.repository.mark_processing, [self.document_id] * 2))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(self.repository.get_status_history(self.document_id)), 2)

    def test_unknown_document_rejected(self):
        with self.assertRaises(KeyError):
            self.repository.mark_processing("missing")

    def test_history_failure_rolls_back_processing(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TRIGGER reject_processing BEFORE INSERT ON ingestion_status_history WHEN NEW.status = 'processing' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.mark_processing(self.document_id)
        self.assertEqual(self.repository.get_document(self.document_id)["ingestion_status"], "queued")
        self.assertEqual(len(self.repository.get_status_history(self.document_id)), 1)

    def test_worker_persists_before_callback_and_skips_duplicate(self):
        queue = InMemoryIngestionJobQueue()
        queue.enqueue(IngestionJob(self.document_id, "notes.txt"))
        queue.enqueue(IngestionJob(self.document_id, "notes.txt"))
        stop = Event()
        statuses = []

        def process(job):
            statuses.append(self.repository.get_document(job.document_id)["ingestion_status"])

        # Stop only after both jobs have been acknowledged; no timed sleeps.
        original_done = queue.task_done
        done = []

        def task_done():
            original_done()
            done.append(True)
            if len(done) == 2:
                stop.set()

        queue.task_done = task_done
        with self.assertLogs("ingestion.ingestion_worker", level="WARNING"):
            run_worker(queue, process, stop, status_repository=self.repository)
        self.assertEqual(statuses, ["processing"])
        queue.join()

    def test_worker_does_not_process_when_status_save_fails(self):
        queue = InMemoryIngestionJobQueue()
        queue.enqueue(IngestionJob("missing", "notes.txt"))
        stop = Event()
        calls = []
        original_done = queue.task_done

        def task_done():
            original_done()
            stop.set()

        queue.task_done = task_done
        with self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            run_worker(queue, calls.append, stop, status_repository=self.repository)
        self.assertEqual(calls, [])
        queue.join()


if __name__ == "__main__":
    unittest.main()
