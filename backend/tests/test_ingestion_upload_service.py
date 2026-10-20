from contextlib import closing
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

# Make backend/app importable when running from project root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
APP_DIR = os.path.join(BACKEND_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_status_constants import INGESTION_STATUS_QUEUED
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_upload_service import (
    IngestionUploadService,
    UploadFileInput,
)

# First configured KB, so a local .env with real KB IDs does not break tests
KB_ID = IngestionConfig().allowed_kb_ids[0]

class SmallLimitConfig(IngestionConfig):
    def __init__(self):
        self.allowed_extensions = (".pdf", ".txt", ".md")
        self.max_file_size_mb = 1
        self.max_files_per_batch = 2
        self.duplicate_policy = "allow"
        self.allowed_kb_ids = (KB_ID,)

    @property
    def max_file_size_bytes(self):
        return self.max_file_size_mb * 1024 * 1024

class TempRepositoryTestCase(unittest.TestCase):
    """Gives each test its own SQLite file so the real instance DB is never touched."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repository = SQLiteIngestionStatusRepository(
            os.path.join(self.directory.name, "ingestion.sqlite3")
        )

    def make_service(self, config=None):
        return IngestionUploadService(config=config, status_repository=self.repository)


class TestIngestionUploadServiceSingleFile(TempRepositoryTestCase):
    def test_create_upload_request_with_single_file(self):
        service = self.make_service()
        file_input = UploadFileInput(
            original_filename="example.pdf",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input], KB_ID)

        self.assertEqual(result["status"], "received")
        self.assertIn("upload_request_id", result)
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "accepted")
        self.assertEqual(result["files"][0]["ingestion_status"], INGESTION_STATUS_QUEUED)
        self.assertEqual(result["files"][0]["metadata"]["original_filename"], "example.pdf")
        self.assertEqual(result["files"][0]["metadata"]["file_type"], ".pdf")
        self.assertIsNone(result["files"][0]["error"])
        self.assertEqual(result["errors"], [])

class TestIngestionUploadService(TempRepositoryTestCase):
    def test_create_upload_request_with_single_file(self):
        service = self.make_service()
        file_input = UploadFileInput(
            original_filename="example.pdf",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input], KB_ID)

        self.assertEqual(result["status"], "received")
        self.assertIn("upload_request_id", result)
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "accepted")
        self.assertEqual(result["files"][0]["ingestion_status"], INGESTION_STATUS_QUEUED)
        self.assertEqual(result["files"][0]["metadata"]["original_filename"], "example.pdf")
        self.assertEqual(result["files"][0]["metadata"]["file_type"], ".pdf")
        self.assertEqual(result["errors"], [])

    def test_create_upload_request_accepts_supported_file_types(self):
        service = self.make_service()
        files = [
            UploadFileInput(
                original_filename="example.pdf",
                file_size_bytes=1024,
                upload_timestamp="2026-10-10T12:00:00Z",
            ),
            UploadFileInput(
                original_filename="notes.txt",
                file_size_bytes=512,
                upload_timestamp="2026-10-10T12:01:00Z",
            ),
            UploadFileInput(
                original_filename="readme.md",
                file_size_bytes=128,
                upload_timestamp="2026-10-10T12:02:00Z",
            ),
        ]

        result = service.create_upload_request(files, KB_ID)

        self.assertEqual(result["status"], "received")
        self.assertEqual(len(result["files"]), 3)
        self.assertEqual(result["errors"], [])

    def test_create_upload_request_rejects_unsupported_file_type(self):
        service = self.make_service()
        file_input = UploadFileInput(
            original_filename="document.docx",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input], KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "unsupported_format")
        self.assertEqual(result["errors"][0]["file_name"], "document.docx")

    def test_create_upload_request_partially_accepts_when_some_file_types_are_supported(self):
        service = self.make_service()
        files = [
            UploadFileInput(
                original_filename="valid.pdf",
                file_size_bytes=1024,
                upload_timestamp="2026-10-10T12:00:00Z",
            ),
            UploadFileInput(
                original_filename="invalid.docx",
                file_size_bytes=2048,
                upload_timestamp="2026-10-10T12:01:00Z",
            ),
        ]

        result = service.create_upload_request(files, KB_ID)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["files"]), 2)
        self.assertEqual(result["files"][0]["status"], "accepted")
        self.assertEqual(result["files"][1]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["files"][0]["metadata"]["original_filename"], "valid.pdf")
        self.assertEqual(result["errors"][0]["code"], "unsupported_format")

    def test_create_upload_request_rejects_missing_file_extension(self):
        service = self.make_service()
        file_input = UploadFileInput(
            original_filename="no_extension",
            file_size_bytes=100,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input], KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "unsupported_format")

    def test_create_upload_request_with_multiple_files(self):
        service = self.make_service()
        files = [
            UploadFileInput(
                original_filename="example.pdf",
                file_size_bytes=1024,
                upload_timestamp="2026-10-10T12:00:00Z",
            ),
            UploadFileInput(
                original_filename="notes.md",
                file_size_bytes=512,
                upload_timestamp="2026-10-10T12:01:00Z",
            ),
        ]

        result = service.create_upload_request(files, KB_ID)

        self.assertEqual(result["status"], "received")
        self.assertEqual(len(result["files"]), 2)
        self.assertEqual(result["files"][0]["metadata"]["file_type"], ".pdf")
        self.assertEqual(result["files"][1]["metadata"]["file_type"], ".md")

    def test_create_upload_request_rejects_none_files(self):
        service = self.make_service()

        result = service.create_upload_request(None, KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "validation_failed")

    def test_create_upload_request_rejects_non_list_files(self):
        service = self.make_service()

        result = service.create_upload_request("not-a-list", KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "validation_failed")

    def test_create_upload_request_rejects_file_over_size_limit(self):
        service = self.make_service(SmallLimitConfig())
        file_input = UploadFileInput(
            original_filename="large.pdf",
            file_size_bytes=(2 * 1024 * 1024),
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input], KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "file_too_large")
        self.assertEqual(result["errors"][0]["file_name"], "large.pdf")
        self.assertEqual(result["errors"][0]["field"], "file_size_bytes")

    def test_create_upload_request_rejects_invalid_file_size(self):
        service = self.make_service(SmallLimitConfig())
        file_input = UploadFileInput(
            original_filename="bad-size.pdf",
            file_size_bytes=-1,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input], KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "validation_failed")
        self.assertEqual(result["errors"][0]["file_name"], "bad-size.pdf")
        self.assertEqual(result["errors"][0]["field"], "file_size_bytes")

    def test_create_upload_request_accepts_readable_temp_file_path(self):
        service = self.make_service(SmallLimitConfig())
        temp_dir = tempfile.mkdtemp()
        try:
            temp_path = os.path.join(temp_dir, "readable.pdf")
            with open(temp_path, "wb") as temp_file:
                temp_file.write(b"sample")

            file_input = UploadFileInput(
                original_filename="readable.pdf",
                file_size_bytes=6,
                upload_timestamp="2026-10-10T12:00:00Z",
                temp_file_path=temp_path,
            )

            result = service.create_upload_request([file_input], KB_ID)

            self.assertEqual(result["status"], "received")
            self.assertEqual(len(result["files"]), 1)
            self.assertEqual(result["errors"], [])
        finally:
            shutil.rmtree(temp_dir)

    def test_create_upload_request_rejects_missing_temp_file_path(self):
        service = self.make_service(SmallLimitConfig())
        file_input = UploadFileInput(
            original_filename="missing.pdf",
            file_size_bytes=100,
            upload_timestamp="2026-10-10T12:00:00Z",
            temp_file_path="path/does/not/exist/missing.pdf",
        )

        result = service.create_upload_request([file_input], KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "unreadable_file")
        self.assertEqual(result["errors"][0]["field"], "temp_file_path")

    def test_create_upload_request_rejects_directory_temp_file_path(self):
        service = self.make_service(SmallLimitConfig())
        temp_dir = tempfile.mkdtemp()
        try:
            file_input = UploadFileInput(
                original_filename="directory.pdf",
                file_size_bytes=100,
                upload_timestamp="2026-10-10T12:00:00Z",
                temp_file_path=temp_dir,
            )

            result = service.create_upload_request([file_input], KB_ID)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(result["files"]), 1)
            self.assertEqual(result["files"][0]["status"], "rejected")
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(result["errors"][0]["code"], "unreadable_file")
            self.assertEqual(result["errors"][0]["field"], "temp_file_path")
        finally:
            shutil.rmtree(temp_dir)

    def test_create_upload_request_rejects_batch_over_limit(self):
        service = self.make_service(SmallLimitConfig())
        files = [
            UploadFileInput(
                original_filename="one.pdf",
                file_size_bytes=100,
                upload_timestamp="2026-10-10T12:00:00Z",
            ),
            UploadFileInput(
                original_filename="two.txt",
                file_size_bytes=100,
                upload_timestamp="2026-10-10T12:01:00Z",
            ),
            UploadFileInput(
                original_filename="three.md",
                file_size_bytes=100,
                upload_timestamp="2026-10-10T12:02:00Z",
            ),
        ]

        result = service.create_upload_request(files, KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "batch_limit_exceeded")
        self.assertEqual(result["errors"][0]["field"], "files")

    def test_create_upload_request_rejected_file_contains_error(self):
        service = self.make_service()
        file_input = UploadFileInput(
            original_filename="document.docx",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input], KB_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertIsNone(result["files"][0]["document_id"])
        self.assertIsNone(result["files"][0]["ingestion_status"])
        self.assertEqual(result["files"][0]["metadata"]["original_filename"], "document.docx")
        self.assertEqual(result["files"][0]["metadata"]["file_type"], ".docx")
        self.assertEqual(result["files"][0]["error"]["code"], "unsupported_format")
        self.assertEqual(len(result["errors"]), 1)

    def test_create_upload_request_partial_includes_accepted_and_rejected_file_results(self):
        service = self.make_service()
        files = [
            UploadFileInput(
                original_filename="valid.pdf",
                file_size_bytes=1024,
                upload_timestamp="2026-10-10T12:00:00Z",
            ),
            UploadFileInput(
                original_filename="invalid.docx",
                file_size_bytes=2048,
                upload_timestamp="2026-10-10T12:01:00Z",
            ),
        ]

        result = service.create_upload_request(files, KB_ID)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["files"]), 2)
        self.assertEqual(result["files"][0]["status"], "accepted")
        self.assertEqual(result["files"][0]["ingestion_status"], INGESTION_STATUS_QUEUED)
        self.assertEqual(result["files"][1]["status"], "rejected")
        self.assertEqual(result["files"][1]["error"]["code"], "unsupported_format")
        self.assertEqual(len(result["errors"]), 1)

class TestUploadKnowledgeBase(TempRepositoryTestCase):
    def file_input(self):
        return UploadFileInput("notes.txt", 10, "2026-10-10T12:00:00Z")

    def assert_nothing_persisted(self):
        with closing(sqlite3.connect(self.repository.database_path)) as connection, connection:
            count = connection.execute("SELECT COUNT(*) FROM ingestion_documents").fetchone()[0]
        self.assertEqual(count, 0)

    def test_known_kb_is_accepted_and_persisted(self):
        result = self.make_service().create_upload_request([self.file_input()], KB_ID)
        entry = result["files"][0]
        self.assertEqual(result["status"], "received")
        self.assertEqual(entry["kb_id"], KB_ID)
        self.assertEqual(entry["metadata"]["kb_id"], KB_ID)
        self.assertEqual(self.repository.get_document(entry["document_id"])["kb_id"], KB_ID)

    def test_kb_id_is_normalized(self):
        result = self.make_service().create_upload_request([self.file_input()], "  " + KB_ID.upper() + " ")
        self.assertEqual(result["status"], "received")
        self.assertEqual(result["files"][0]["kb_id"], KB_ID)

    def test_unknown_missing_or_blank_kb_fails_whole_request(self):
        for bad_kb_id in ("kb_does_not_exist", "", "   ", None, 42):
            result = self.make_service().create_upload_request([self.file_input(), self.file_input()], bad_kb_id)
            self.assertEqual(result["status"], "failed", bad_kb_id)
            self.assertEqual(result["files"], [])
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(result["errors"][0]["code"], "unknown_kb")
            self.assertEqual(result["errors"][0]["field"], "kb_id")
            self.assertIn(KB_ID, result["errors"][0]["details"])
        self.assert_nothing_persisted()

    def test_rejected_file_entry_has_no_kb_id(self):
        result = self.make_service().create_upload_request(
            [UploadFileInput("bad.exe", 10, "2026-10-10T12:00:00Z")], KB_ID
        )
        self.assertIsNone(result["files"][0]["kb_id"])


if __name__ == "__main__":
    unittest.main()
