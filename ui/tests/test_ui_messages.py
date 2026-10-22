"""Plain-language texts for error codes, failure reasons and client errors."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui_messages
from ui_api_client import KIND_API, KIND_BUSY, KIND_CONNECTION, KIND_TIMEOUT, ApiClientError

# Every canonical code in backend/app/ingestion/ingestion_error_model.py (copied: the UI never imports the backend).
CANONICAL_CODES = (
    "unsupported_format", "unreadable_file", "extraction_failure", "validation_failed", "file_too_large",
    "batch_limit_exceeded", "duplicate_blocked", "internal_failure", "unknown_kb", "empty_content", "not_found",
    "indexing_failure", "not_implemented", "llm_unavailable",
)


class DescribeErrorTest(unittest.TestCase):
    def test_every_canonical_code_has_text(self):
        for code in CANONICAL_CODES:
            with self.subTest(code=code):
                self.assertIn(code, ui_messages.ERROR_TEXT)
                self.assertNotEqual(ui_messages.describe_error(code), code)

    def test_unknown_code_falls_back_to_the_api_message_then_the_code(self):
        self.assertEqual(ui_messages.describe_error("new_code", fallback="API says"), "API says")
        self.assertEqual(ui_messages.describe_error("new_code"), "new_code")
        self.assertEqual(ui_messages.describe_error(None), "Unknown error.")

    def test_interrupted_reason_gets_its_own_text(self):
        text = ui_messages.describe_failure("internal_failure", "interrupted by server restart")
        self.assertIn("Upload the file again", text)

    def test_failure_uses_the_code_text(self):
        self.assertEqual(ui_messages.describe_failure("empty_content", "no text"),
                         ui_messages.ERROR_TEXT["empty_content"])

    def test_status_labels(self):
        for status in ("queued", "processing", "success", "failed"):
            self.assertNotEqual(ui_messages.status_label(status), status)
        self.assertEqual(ui_messages.status_label("other"), "other")


class ClientErrorTextTest(unittest.TestCase):
    def test_connection_error_names_the_start_command(self):
        level, text = ui_messages.client_error_text(ApiClientError(KIND_CONNECTION, "Can't reach the API."))
        self.assertEqual(level, ui_messages.LEVEL_ERROR)
        self.assertIn("uvicorn", text)

    def test_timeout_is_an_error(self):
        level, text = ui_messages.client_error_text(ApiClientError(KIND_TIMEOUT, "Too slow."))
        self.assertEqual(level, ui_messages.LEVEL_ERROR)
        self.assertIn("Too slow.", text)

    def test_busy_is_a_warning_with_the_wait(self):
        level, text = ui_messages.client_error_text(ApiClientError(KIND_BUSY, "busy", retry_after=30))
        self.assertEqual(level, ui_messages.LEVEL_WARNING)
        self.assertIn("about 30 s", text)
        _, text = ui_messages.client_error_text(ApiClientError(KIND_BUSY, "busy"))
        self.assertIn("a minute", text)

    def test_api_error_uses_plain_text_and_details(self):
        exc = ApiClientError(KIND_API, "Unknown knowledge base.", code="unknown_kb", details="nope")
        level, text = ui_messages.client_error_text(exc)
        self.assertEqual(level, ui_messages.LEVEL_ERROR)
        self.assertEqual(text, ui_messages.ERROR_TEXT["unknown_kb"] + " (nope)")


if __name__ == "__main__":
    unittest.main()
