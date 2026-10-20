"""Task 5.1: chunk size and overlap configuration (characters, not tokens)."""

import os
import sys
import unittest
from unittest import mock

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_chunking import FixedSizeCharChunker
from ingestion.ingestion_config_manager import (
    DEFAULT_CHUNK_OVERLAP_CHARS, DEFAULT_CHUNK_SIZE_CHARS, IngestionConfig,
)

LOGGER_NAME = "ingestion.ingestion_config_manager"


def config_with(size, overlap):
    env = {"INGESTION_CHUNK_SIZE_CHARS": size, "INGESTION_CHUNK_OVERLAP_CHARS": overlap}
    with mock.patch.dict(os.environ, env):
        return IngestionConfig()


class TestChunkingConfig(unittest.TestCase):
    def test_reads_environment(self):
        config = config_with("500", "50")
        self.assertEqual((config.chunk_size_chars, config.chunk_overlap_chars), (500, 50))
        self.assertEqual(config.as_dict()["chunk_size_chars"], 500)
        self.assertEqual(config.as_dict()["chunk_overlap_chars"], 50)
        chunker = FixedSizeCharChunker.from_config(config)
        self.assertEqual((chunker.chunk_size, chunker.overlap), (500, 50))

    def test_blank_values_use_defaults(self):
        config = config_with("", "")
        self.assertEqual(
            (config.chunk_size_chars, config.chunk_overlap_chars),
            (DEFAULT_CHUNK_SIZE_CHARS, DEFAULT_CHUNK_OVERLAP_CHARS),
        )

    def test_invalid_size_uses_default(self):
        for raw in ("0", "-10", "abc"):
            self.assertEqual(config_with(raw, "100").chunk_size_chars, DEFAULT_CHUNK_SIZE_CHARS)

    def test_bad_overlap_falls_back_with_warning(self):
        for raw in ("500", "900", "-1"):
            with self.assertLogs(LOGGER_NAME, level="WARNING") as logs:
                config = config_with("500", raw)
            self.assertEqual(config.chunk_overlap_chars, 100)  # 500 // 5
            self.assertIn(repr(raw), logs.output[0])

    def test_valid_overlap_logs_nothing(self):
        with mock.patch("ingestion.ingestion_config_manager.LOGGER") as logger:
            config_with("500", "0")
        logger.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
