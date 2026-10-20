"""RetrievalConfig (F3): RETRIEVAL_TOP_K from the environment, with a safe default."""

import os
import sys
import unittest
from unittest.mock import patch

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from retrieval.retrieval_config import DEFAULT_RETRIEVAL_TOP_K, RetrievalConfig


class TestRetrievalConfig(unittest.TestCase):
    def config_with(self, value):
        with patch.dict(os.environ, {"RETRIEVAL_TOP_K": value}):
            return RetrievalConfig()

    def test_default_is_20(self):
        self.assertEqual(DEFAULT_RETRIEVAL_TOP_K, 20)
        self.assertEqual(self.config_with("").top_k, 20)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(RetrievalConfig().top_k, 20)

    def test_env_override(self):
        self.assertEqual(self.config_with("35").top_k, 35)
        self.assertEqual(self.config_with(" 7 ").top_k, 7)
        self.assertEqual(self.config_with("35").as_dict(), {"top_k": 35})

    def test_invalid_values_fall_back_with_a_warning(self):
        for value in ("abc", "0", "-3", "2.5"):
            with self.subTest(value=value):
                with self.assertLogs("retrieval.retrieval_config", level="WARNING"):
                    self.assertEqual(self.config_with(value).top_k, 20)


if __name__ == "__main__":
    unittest.main()
