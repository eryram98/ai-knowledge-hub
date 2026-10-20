import os
import sys
import unittest

# Make backend/app importable when running from project root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
APP_DIR = os.path.join(BACKEND_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_error_model import (
    ERROR_UNSUPPORTED_FORMAT,
    ERROR_UNREADABLE_FILE,
    ERROR_EXTRACTION_FAILURE,
    ERROR_VALIDATION_FAILED,
    ERROR_INTERNAL_FAILURE,
    ERROR_UNKNOWN_KB,
    ERROR_INDEXING_FAILURE,
    ERROR_NOT_IMPLEMENTED,
    is_valid_error_code,
    get_error_message,
    build_ingestion_error,
)


class TestIngestionErrorModel(unittest.TestCase):
    def test_is_valid_error_code(self):
        self.assertTrue(is_valid_error_code(ERROR_UNSUPPORTED_FORMAT))
        self.assertTrue(is_valid_error_code(ERROR_UNREADABLE_FILE))
        self.assertFalse(is_valid_error_code("not_a_real_code"))

    def test_unknown_kb_is_canonical(self):
        self.assertEqual(ERROR_UNKNOWN_KB, "unknown_kb")
        self.assertTrue(is_valid_error_code(ERROR_UNKNOWN_KB))
        err = build_ingestion_error(ERROR_UNKNOWN_KB, field="kb_id")
        self.assertEqual(err["code"], "unknown_kb")
        self.assertIn("knowledge base", err["message"].lower())

    def test_indexing_failure_is_canonical(self):
        self.assertEqual(ERROR_INDEXING_FAILURE, "indexing_failure")
        self.assertTrue(is_valid_error_code(ERROR_INDEXING_FAILURE))
        self.assertEqual(get_error_message(ERROR_INDEXING_FAILURE), "Embedding or indexing failed for this document.")

    def test_not_implemented_is_canonical(self):
        self.assertEqual(ERROR_NOT_IMPLEMENTED, "not_implemented")
        self.assertTrue(is_valid_error_code(ERROR_NOT_IMPLEMENTED))
        self.assertEqual(build_ingestion_error(ERROR_NOT_IMPLEMENTED)["code"], "not_implemented")

    def test_get_error_message_known(self):
        message = get_error_message(ERROR_EXTRACTION_FAILURE)
        self.assertTrue(isinstance(message, str))
        self.assertTrue(len(message) > 0)

    def test_get_error_message_unknown_with_fallback(self):
        message = get_error_message("bad_code", fallback_message="Fallback message")
        self.assertEqual(message, "Fallback message")

    def test_build_ingestion_error_known_code(self):
        err = build_ingestion_error(
            error_code=ERROR_VALIDATION_FAILED,
            details="Missing extension",
            file_name="input.unknown",
            field="extension",
        )
        self.assertEqual(err["code"], ERROR_VALIDATION_FAILED)
        self.assertIn("message", err)
        self.assertEqual(err["details"], "Missing extension")
        self.assertEqual(err["file_name"], "input.unknown")
        self.assertEqual(err["field"], "extension")

    def test_build_ingestion_error_unknown_code_normalized(self):
        err = build_ingestion_error(error_code="bad_code")
        self.assertEqual(err["code"], ERROR_INTERNAL_FAILURE)
        self.assertIn("message", err)


if __name__ == "__main__":
    unittest.main()
