"""Task 3.4: real background-worker batches with file-local failures."""

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

from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput
from ingestion.ingestion_worker import start_background_worker

# First configured KB, so a local .env with real KB IDs does not break tests
KB_ID = IngestionConfig().allowed_kb_ids[0]


class ObservedQueue(InMemoryIngestionJobQueue):
    """Signal completion without an unbounded queue.join() in failing tests."""

    def __init__(self, expected_jobs):
        super(ObservedQueue, self).__init__()
        self.remaining = expected_jobs
        self.completed = Event()

    def task_done(self):
        super(ObservedQueue, self).task_done()
        self.remaining -= 1
        if self.remaining == 0:
            self.completed.set()


class TestIngestionFailureIsolation(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "status.sqlite3")
        self.repository = SQLiteIngestionStatusRepository(self.path)
        service = IngestionUploadService(status_repository=self.repository)
        response = service.create_upload_request([
            UploadFileInput(name, 10, "2026-10-10T12:00:00Z")
            for name in ("first.txt", "broken.txt", "last.txt")
        ], KB_ID)
        self.entries = response["files"]
        self.assertEqual(response["status"], "received")
        self.queue = ObservedQueue(len(self.entries))
        for entry in self.entries:
            self.queue.enqueue(IngestionJob(
                entry["document_id"], entry["metadata"]["original_filename"],
                entry["metadata"],
            ))

    def run_batch(self, processor):
        with self.assertLogs("ingestion.ingestion_worker", level="ERROR") as logs:
            thread, stop = start_background_worker(
                self.queue, processor, status_repository=self.repository,
            )
            try:
                self.assertTrue(self.queue.completed.wait(timeout=5), "Batch stalled")
                self.assertTrue(thread.is_alive(), "Worker exited after a file failure")
            finally:
                stop.set()
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.queue.remaining, 0)
        self.assertIn(self.entries[1]["document_id"], logs.output[0])

    def test_processing_failure_does_not_block_later_file(self):
        attempted = []
        completed = []

        def process(job):
            attempted.append(job.document_id)
            if job.metadata["original_filename"] == "broken.txt":
                raise RuntimeError("Extraction failure for this file")
            completed.append(job.document_id)

        self.run_batch(process)
        ids = [entry["document_id"] for entry in self.entries]
        self.assertEqual(attempted, ids)
        self.assertEqual(completed, [ids[0], ids[2]])
        reopened = SQLiteIngestionStatusRepository(self.path)
        for document_id in ids:
            self.assertEqual(
                [row["status"] for row in reopened.get_status_history(document_id)],
                ["queued", "processing", "failed" if document_id == ids[1] else "success"],
            )

    def test_file_specific_storage_failure_does_not_block_later_file(self):
        broken_id = self.entries[1]["document_id"]
        with closing(sqlite3.connect(self.path)) as connection, connection:
            # Test-only trigger fails this document's processing history insert.
            connection.execute(
                "CREATE TRIGGER reject_one_file BEFORE INSERT ON ingestion_status_history "
                "WHEN NEW.status = 'processing' AND NEW.document_id = '{0}' "
                "BEGIN SELECT RAISE(ABORT, 'test storage failure'); END".format(broken_id)
            )
        completed = []
        self.run_batch(lambda job: completed.append(job.document_id))
        ids = [entry["document_id"] for entry in self.entries]
        self.assertEqual(completed, [ids[0], ids[2]])
        self.assertEqual(self.repository.get_document(broken_id)["ingestion_status"], "queued")
        self.assertEqual(len(self.repository.get_status_history(broken_id)), 1)
        for document_id in (ids[0], ids[2]):
            self.assertEqual(self.repository.get_document(document_id)["ingestion_status"], "success")


if __name__ == "__main__":
    unittest.main()
