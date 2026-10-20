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
    is_valid_ingestion_status,
)

# ... existing code ...
class TestIngestionStatusConstants(unittest.TestCase):
    def test_valid_statuses(self):
        self.assertTrue(is_valid_ingestion_status(INGESTION_STATUS_QUEUED))
# ... existing code ...
if __name__ == "__main__":
    unittest.main()