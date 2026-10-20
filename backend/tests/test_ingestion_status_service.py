import json
import os
import sys
import tempfile
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_status_service import IngestionStatusService
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput

# First configured KB, so a local .env with real KB IDs does not break tests
KB_ID = IngestionConfig().allowed_kb_ids[0]


class TestIngestionStatusService(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "status.sqlite3")
        self.repository = SQLiteIngestionStatusRepository(self.path)
        self.service = IngestionStatusService(self.repository)
        response = IngestionUploadService(status_repository=self.repository).create_upload_request([
            UploadFileInput(name, 10, "2026-10-10T12:00:00Z")
            for name in ("one.txt", "two.md", "three.pdf")
        ], KB_ID)
        self.ids = [entry["document_id"] for entry in response["files"]]

    def test_polling_tracks_lifecycle_and_timestamps(self):
        document_id = self.ids[0]
        queued = self.service.get_document_status(document_id)
        self.assertEqual(queued["ingestion_status"], "queued")
        self.assertTrue(queued["should_poll"])
        self.assertIsNone(queued["processing_at"])
        self.assertIsNone(queued["completed_at"])
        self.repository.mark_processing(document_id)
        processing = self.service.get_document_status(document_id)
        self.assertEqual(processing["ingestion_status"], "processing")
        self.assertIsNotNone(processing["processing_at"])
        self.repository.mark_success(document_id)
        finished = self.service.get_document_status(document_id)
        self.assertFalse(finished["should_poll"])
        self.assertTrue(finished["is_terminal"])
        self.assertEqual(finished["completed_at"], finished["history"][-1]["timestamp"])
        self.assertIsNone(finished["failure_reason"])
        self.assertNotIn("temp_file_path", finished)
        json.dumps(finished)

    def test_failure_reason_after_restart(self):
        self.repository.mark_processing(self.ids[0])
        self.repository.mark_failed(self.ids[0], "Extraction failed")
        reopened = IngestionStatusService(SQLiteIngestionStatusRepository(self.path))
        result = reopened.get_document_status(self.ids[0])
        self.assertEqual(result["failure_reason"], "Extraction failed")
        self.assertFalse(result["should_poll"])

    def test_mixed_batch_counts_and_progress(self):
        for document_id in self.ids[:2]:
            self.repository.mark_processing(document_id)
        self.repository.mark_success(self.ids[0])
        self.repository.mark_failed(self.ids[1], "Failed")
        batch = self.service.get_batch_status(self.ids + [self.ids[0]])
        self.assertEqual(batch["total"], 3)
        self.assertEqual(batch["completed"], 2)
        self.assertAlmostEqual(batch["progress_percent"], 200.0 / 3)
        self.assertEqual(batch["counts"], {"queued": 1, "processing": 0, "success": 1, "failed": 1})
        self.assertTrue(batch["should_poll"])
        self.assertFalse(batch["is_complete"])
        self.repository.mark_processing(self.ids[2])
        self.repository.mark_success(self.ids[2])
        batch = self.service.get_batch_status(self.ids)
        self.assertTrue(batch["is_complete"])
        self.assertFalse(batch["should_poll"])
        self.assertEqual(batch["progress_percent"], 100.0)

    def test_unknown_ids_are_explicit(self):
        self.assertIsNone(self.service.get_document_status("unknown"))
        result = self.service.get_batch_status(["unknown"])
        self.assertEqual(result["missing_document_ids"], ["unknown"])
        self.assertEqual(result["completed"], 0)
        self.assertFalse(result["is_complete"])
        self.assertFalse(result["should_poll"])

    def test_empty_batch(self):
        result = self.service.get_batch_status([])
        self.assertEqual(result["progress_percent"], 0)
        self.assertFalse(result["is_complete"])
        self.assertFalse(result["should_poll"])

    def test_invalid_inputs(self):
        for value in (None, "", " ", 42):
            with self.assertRaises(ValueError):
                self.service.get_document_status(value)
        for value in (None, "doc", [None], [" "]):
            with self.assertRaises(ValueError):
                self.service.get_batch_status(value)

    def test_queries_do_not_change_status_history(self):
        before = self.repository.get_status_history(self.ids[0])
        self.service.get_document_status(self.ids[0])
        self.service.get_batch_status(self.ids)
        self.assertEqual(self.repository.get_status_history(self.ids[0]), before)


if __name__ == "__main__":
    unittest.main()
