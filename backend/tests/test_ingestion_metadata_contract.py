import os
import sys
import unittest

# Make backend/app importable when running from project root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
APP_DIR = os.path.join(BACKEND_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_metadata_contract import (
    META_ORIGINAL_FILENAME,
    META_FILE_TYPE,
    META_FILE_SIZE_BYTES,
    META_UPLOAD_TIMESTAMP,
    META_INGESTION_SOURCE,
    INGESTION_SOURCE_UI,
    PERSISTENCE_EXPECTATIONS,
    create_metadata_record,
    validate_metadata_contract,
)


class TestIngestionMetadataContract(unittest.TestCase):
    def test_create_metadata_record_defaults(self):
        record = create_metadata_record(
            original_filename="doc.pdf",
            file_type=".pdf",
            file_size_bytes=1024,
            upload_timestamp="2026-10-10T12:00:00Z",
        )
        self.assertEqual(record[META_INGESTION_SOURCE], INGESTION_SOURCE_UI)
        self.assertEqual(record[META_ORIGINAL_FILENAME], "doc.pdf")

    def test_validate_metadata_contract_valid(self):
        metadata = {
            META_ORIGINAL_FILENAME: "notes.md",
            META_FILE_TYPE: ".md",
            META_FILE_SIZE_BYTES: 55,
            META_UPLOAD_TIMESTAMP: "2026-10-10T12:00:00Z",
            META_INGESTION_SOURCE: INGESTION_SOURCE_UI,
        }
        valid, errors = validate_metadata_contract(metadata)
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_validate_metadata_contract_missing_fields(self):
        metadata = {
            META_ORIGINAL_FILENAME: "notes.md",
        }
        valid, errors = validate_metadata_contract(metadata)
        self.assertFalse(valid)
        self.assertTrue(len(errors) > 0)

    def test_validate_metadata_contract_invalid_values(self):
        metadata = {
            META_ORIGINAL_FILENAME: "",
            META_FILE_TYPE: ".md",
            META_FILE_SIZE_BYTES: -1,
            META_UPLOAD_TIMESTAMP: "not-a-date",
            META_INGESTION_SOURCE: "API",
        }
        valid, errors = validate_metadata_contract(metadata)
        self.assertFalse(valid)
        self.assertTrue(any("original_filename" in e for e in errors))
        self.assertTrue(any("file_size_bytes" in e for e in errors))
        self.assertTrue(any("upload_timestamp" in e for e in errors))
        self.assertTrue(any("ingestion_source" in e for e in errors))

    def test_persistence_expectations_shape(self):
        self.assertIn("files_table", PERSISTENCE_EXPECTATIONS)
        self.assertIn("status_history", PERSISTENCE_EXPECTATIONS)
        self.assertIn("artifacts", PERSISTENCE_EXPECTATIONS)


if __name__ == "__main__":
    unittest.main()
