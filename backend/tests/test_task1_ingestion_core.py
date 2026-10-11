import os
import sys
import unittest

# Make backend/app importable when running from project root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
APP_DIR = os.path.join(BACKEND_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_status_constants import (
    INGESTION_STATUS_QUEUED,
    INGESTION_STATUS_PROCESSING,
    INGESTION_STATUS_SUCCESS,
    INGESTION_STATUS_FAILED,
    is_valid_ingestion_status,
    can_transition_ingestion_status,
)
from ingestion.ingestion_config_manager import (
    IngestionConfig,
    DEFAULT_ALLOWED_EXTENSIONS,
    DEFAULT_MAX_FILE_SIZE_MB,
    DEFAULT_MAX_FILES_PER_BATCH,
    DEFAULT_DUPLICATE_POLICY,
)

# ... existing code ...
class TestIngestionStatusConstants(unittest.TestCase):
    def test_valid_statuses(self):
        self.assertTrue(is_valid_ingestion_status(INGESTION_STATUS_QUEUED))
# ... existing code ...
if __name__ == "__main__":
    unittest.main()