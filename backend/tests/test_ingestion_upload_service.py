import os
import shutil
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
from ingestion.ingestion_upload_service import (
    IngestionUploadService,
    UploadFileInput,
)

class SmallLimitConfig(IngestionConfig):
    def __init__(self):
        self.allowed_extensions = (".pdf", ".txt", ".md")
        self.max_file_size_mb = 1
        self.max_files_per_batch = 2
        self.duplicate_policy = "allow"

    @property
    def max_file_size_bytes(self):
        return self.max_file_size_mb * 1024 * 1024

class TestIngestionUploadService(unittest.TestCase):
    def test_create_upload_request_with_single_file(self):
        service = IngestionUploadService()
        file_input = UploadFileInput(
            original_filename="example.pdf",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input])

        self.assertEqual(result["status"], "received")
        self.assertIn("upload_request_id", result)
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "accepted")
        self.assertEqual(result["files"][0]["ingestion_status"], INGESTION_STATUS_QUEUED)
        self.assertEqual(result["files"][0]["metadata"]["original_filename"], "example.pdf")
        self.assertEqual(result["files"][0]["metadata"]["file_type"], ".pdf")
        self.assertIsNone(result["files"][0]["error"])
        self.assertEqual(result["errors"], [])

class TestIngestionUploadService(unittest.TestCase):
    def test_create_upload_request_with_single_file(self):
        service = IngestionUploadService()
        file_input = UploadFileInput(
            original_filename="example.pdf",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input])

        self.assertEqual(result["status"], "received")
        self.assertIn("upload_request_id", result)
        self.assertEqual(len(result["files"]), 1)
        result["files"][0]["status"] == "accepted"
        result["files"][0]["ingestion_status"] == INGESTION_STATUS_QUEUED
        self.assertEqual(result["files"][0]["metadata"]["original_filename"], "example.pdf")
        self.assertEqual(result["files"][0]["metadata"]["file_type"], ".pdf")
        self.assertEqual(result["errors"], [])

    def test_create_upload_request_accepts_supported_file_types(self):
        service = IngestionUploadService()
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

        result = service.create_upload_request(files)

        self.assertEqual(result["status"], "received")
        self.assertEqual(len(result["files"]), 3)
        self.assertEqual(result["errors"], [])

    def test_create_upload_request_rejects_unsupported_file_type(self):
        service = IngestionUploadService()
        file_input = UploadFileInput(
            original_filename="document.docx",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "unsupported_format")
        self.assertEqual(result["errors"][0]["file_name"], "document.docx")

    def test_create_upload_request_partially_accepts_when_some_file_types_are_supported(self):
        service = IngestionUploadService()
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

        result = service.create_upload_request(files)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["files"]), 2)
        self.assertEqual(result["files"][0]["status"], "accepted")
        self.assertEqual(result["files"][1]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["files"][0]["metadata"]["original_filename"], "valid.pdf")
        self.assertEqual(result["errors"][0]["code"], "unsupported_format")

    def test_create_upload_request_rejects_missing_file_extension(self):
        service = IngestionUploadService()
        file_input = UploadFileInput(
            original_filename="no_extension",
            file_size_bytes=100,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "unsupported_format")

    def test_create_upload_request_with_multiple_files(self):
        service = IngestionUploadService()
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

        result = service.create_upload_request(files)

        self.assertEqual(result["status"], "received")
        self.assertEqual(len(result["files"]), 2)
        self.assertEqual(result["files"][0]["metadata"]["file_type"], ".pdf")
        self.assertEqual(result["files"][1]["metadata"]["file_type"], ".md")

    def test_create_upload_request_rejects_none_files(self):
        service = IngestionUploadService()

        result = service.create_upload_request(None)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "validation_failed")

    def test_create_upload_request_rejects_non_list_files(self):
        service = IngestionUploadService()

        result = service.create_upload_request("not-a-list")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "validation_failed")

    def test_create_upload_request_rejects_file_over_size_limit(self):
        service = IngestionUploadService(config=SmallLimitConfig())
        file_input = UploadFileInput(
            original_filename="large.pdf",
            file_size_bytes=(2 * 1024 * 1024),
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "file_too_large")
        self.assertEqual(result["errors"][0]["file_name"], "large.pdf")
        self.assertEqual(result["errors"][0]["field"], "file_size_bytes")

    def test_create_upload_request_rejects_invalid_file_size(self):
        service = IngestionUploadService(config=SmallLimitConfig())
        file_input = UploadFileInput(
            original_filename="bad-size.pdf",
            file_size_bytes=-1,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "validation_failed")
        self.assertEqual(result["errors"][0]["file_name"], "bad-size.pdf")
        self.assertEqual(result["errors"][0]["field"], "file_size_bytes")

    def test_create_upload_request_accepts_readable_temp_file_path(self):
        service = IngestionUploadService(config=SmallLimitConfig())
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

            result = service.create_upload_request([file_input])

            self.assertEqual(result["status"], "received")
            self.assertEqual(len(result["files"]), 1)
            self.assertEqual(result["errors"], [])
        finally:
            shutil.rmtree(temp_dir)

    def test_create_upload_request_rejects_missing_temp_file_path(self):
        service = IngestionUploadService(config=SmallLimitConfig())
        file_input = UploadFileInput(
            original_filename="missing.pdf",
            file_size_bytes=100,
            upload_timestamp="2026-10-10T12:00:00Z",
            temp_file_path="path/does/not/exist/missing.pdf",
        )

        result = service.create_upload_request([file_input])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["status"], "rejected")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "unreadable_file")
        self.assertEqual(result["errors"][0]["field"], "temp_file_path")

    def test_create_upload_request_rejects_directory_temp_file_path(self):
        service = IngestionUploadService(config=SmallLimitConfig())
        temp_dir = tempfile.mkdtemp()
        try:
            file_input = UploadFileInput(
                original_filename="directory.pdf",
                file_size_bytes=100,
                upload_timestamp="2026-10-10T12:00:00Z",
                temp_file_path=temp_dir,
            )

            result = service.create_upload_request([file_input])

            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(result["files"]), 1)
            self.assertEqual(result["files"][0]["status"], "rejected")
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(result["errors"][0]["code"], "unreadable_file")
            self.assertEqual(result["errors"][0]["field"], "temp_file_path")
        finally:
            shutil.rmtree(temp_dir)

    def test_create_upload_request_rejects_batch_over_limit(self):
        service = IngestionUploadService(config=SmallLimitConfig())
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

        result = service.create_upload_request(files)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["files"]), 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "batch_limit_exceeded")
        self.assertEqual(result["errors"][0]["field"], "files")

    def test_create_upload_request_rejected_file_contains_error(self):
        service = IngestionUploadService()
        file_input = UploadFileInput(
            original_filename="document.docx",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )

        result = service.create_upload_request([file_input])

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
        service = IngestionUploadService()
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

        result = service.create_upload_request(files)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["files"]), 2)
        self.assertEqual(result["files"][0]["status"], "accepted")
        self.assertEqual(result["files"][0]["ingestion_status"], INGESTION_STATUS_QUEUED)
        self.assertEqual(result["files"][1]["status"], "rejected")
        self.assertEqual(result["files"][1]["error"]["code"], "unsupported_format")
        self.assertEqual(len(result["errors"]), 1)

if __name__ == "__main__":
    unittest.main()
