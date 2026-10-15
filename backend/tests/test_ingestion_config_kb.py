import os
import sys
import unittest
from unittest.mock import patch

# Make backend/app importable when running from project root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
APP_DIR = os.path.join(BACKEND_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_config_manager import DEFAULT_ALLOWED_KB_IDS, IngestionConfig


class TestAllowedKbIdsConfig(unittest.TestCase):
    def config_with(self, raw_value):
        with patch.dict(os.environ, {"INGESTION_ALLOWED_KB_IDS": raw_value}):
            return IngestionConfig()

    def test_defaults_are_two_placeholders(self):
        self.assertEqual(DEFAULT_ALLOWED_KB_IDS, ("kb_placeholder_a", "kb_placeholder_b"))
        with patch.dict(os.environ):
            os.environ.pop("INGESTION_ALLOWED_KB_IDS", None)
            self.assertEqual(IngestionConfig().allowed_kb_ids, DEFAULT_ALLOWED_KB_IDS)

    def test_env_overrides_defaults(self):
        self.assertEqual(self.config_with("finance,hr").allowed_kb_ids, ("finance", "hr"))

    def test_env_values_are_normalized_and_deduplicated(self):
        self.assertEqual(
            self.config_with(" Finance , HR,finance,, ").allowed_kb_ids,
            ("finance", "hr"),
        )

    def test_blank_env_value_falls_back_to_defaults(self):
        for raw_value in ("", "  ", " , ,"):
            self.assertEqual(self.config_with(raw_value).allowed_kb_ids, DEFAULT_ALLOWED_KB_IDS)

    def test_as_dict_includes_allowed_kb_ids(self):
        self.assertEqual(self.config_with("a,b").as_dict()["allowed_kb_ids"], ("a", "b"))

    def test_extensions_still_normalized_after_refactor(self):
        with patch.dict(os.environ, {"INGESTION_ALLOWED_EXTENSIONS": "PDF, .txt,pdf"}):
            self.assertEqual(IngestionConfig().allowed_extensions, (".pdf", ".txt"))


if __name__ == "__main__":
    unittest.main()
