from contextlib import closing
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput


class TestQueuedPersistence(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "ingestion.sqlite3")
        self.repository = SQLiteIngestionStatusRepository(self.path)
        self.service = IngestionUploadService(status_repository=self.repository)

    def file_input(self, filename="notes.txt"):
        return UploadFileInput(filename, 10, "2026-10-10T12:00:00Z")

    def test_accepted_status_and_history_survive_repository_restart(self):
        entry = self.service.create_upload_request([self.file_input()])["files"][0]
        reopened = SQLiteIngestionStatusRepository(self.path)
        saved = reopened.get_document(entry["document_id"])
        self.assertEqual(entry["ingestion_status"], "queued")
        self.assertEqual(saved["ingestion_status"], "queued")
        self.assertEqual(saved["metadata"], entry["metadata"])
        history = reopened.get_status_history(entry["document_id"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "queued")
        self.assertEqual(history[0]["timestamp"], saved["queued_at"])
        self.assertIsNone(history[0]["reason"])

    def test_rejected_file_is_not_persisted(self):
        response = self.service.create_upload_request([self.file_input("bad.exe")])
        self.assertEqual(response["files"][0]["status"], "rejected")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ingestion_documents").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ingestion_status_history").fetchone()[0], 0)

    def test_storage_failure_rejects_file(self):
        repository = Mock()
        repository.create_queued.side_effect = sqlite3.OperationalError("storage unavailable")
        response = IngestionUploadService(status_repository=repository).create_upload_request([self.file_input()])
        entry = response["files"][0]
        self.assertEqual(response["status"], "failed")
        self.assertEqual(entry["status"], "rejected")
        self.assertIsNone(entry["ingestion_status"])
        self.assertEqual(entry["error"]["code"], "internal_failure")

    def test_duplicate_document_does_not_reset_history(self):
        entry = self.service.create_upload_request([self.file_input()])["files"][0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create_queued(entry["metadata"])
        self.assertEqual(len(self.repository.get_status_history(entry["document_id"])), 1)

    def test_history_failure_rolls_back_document(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER reject_history BEFORE INSERT ON ingestion_status_history BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        entry = self.service.create_upload_request([self.file_input()])["files"][0]
        self.assertEqual(entry["status"], "rejected")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ingestion_documents").fetchone()[0], 0)

    def test_partial_batch_persists_only_accepted_files(self):
        response = self.service.create_upload_request([self.file_input(), self.file_input("bad.exe")])
        self.assertEqual(response["status"], "partial")
        self.assertIsNotNone(self.repository.get_document(response["files"][0]["document_id"]))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ingestion_documents").fetchone()[0], 1)

    def test_unknown_document(self):
        self.assertIsNone(self.repository.get_document("unknown"))
        self.assertEqual(self.repository.get_status_history("unknown"), [])


if __name__ == "__main__":
    unittest.main()
