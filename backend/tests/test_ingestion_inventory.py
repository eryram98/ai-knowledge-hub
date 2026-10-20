"""Inventory queries for F1: repository list and counts, status service list, pre-assigned IDs."""

import os
import sys
import tempfile
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_status_service import IngestionStatusService
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput

KB_A, KB_B = "it_policies", "hw_datasheets"


class TestInventory(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repository = SQLiteIngestionStatusRepository(os.path.join(directory.name, "inventory.sqlite3"))
        config = IngestionConfig()
        config.allowed_kb_ids = (KB_A, KB_B)
        self.intake = IngestionUploadService(config=config, status_repository=self.repository)
        self.service = IngestionStatusService(self.repository)

    def add(self, name, kb_id):
        response = self.intake.create_upload_request([UploadFileInput(name, 10, "2026-10-20T12:00:00Z")], kb_id)
        return response["files"][0]["document_id"]

    def test_list_documents_is_newest_first_with_history(self):
        first, second, third = self.add("1.txt", KB_A), self.add("2.txt", KB_B), self.add("3.txt", KB_A)
        records = self.repository.list_documents()
        self.assertEqual([r["document_id"] for r in records], [third, second, first])
        self.assertEqual(records[0]["metadata"]["original_filename"], "3.txt")
        self.assertEqual([h["status"] for h in records[0]["history"]], ["queued"])
        self.assertEqual([r["document_id"] for r in self.repository.list_documents(KB_A)], [third, first])
        self.assertEqual(self.repository.list_documents("other"), [])

    def test_history_belongs_to_each_document(self):
        first, second = self.add("1.txt", KB_A), self.add("2.txt", KB_A)
        self.repository.mark_processing(first)
        self.repository.mark_failed(first, "broken", "unreadable_file")
        by_id = {r["document_id"]: r for r in self.repository.list_documents(KB_A)}
        self.assertEqual([h["status"] for h in by_id[first]["history"]], ["queued", "processing", "failed"])
        self.assertEqual([h["status"] for h in by_id[second]["history"]], ["queued"])

    def test_counts_by_kb_and_status(self):
        self.assertEqual(self.repository.count_documents_by_kb_and_status(), {})
        done, _queued, _other = self.add("1.txt", KB_A), self.add("2.txt", KB_A), self.add("3.txt", KB_B)
        self.repository.mark_processing(done)
        self.repository.mark_success(done)
        self.assertEqual(self.repository.count_documents_by_kb_and_status(),
                         {KB_A: {"success": 1, "queued": 1}, KB_B: {"queued": 1}})

    def test_service_list_matches_single_status_without_history(self):
        document_id = self.add("1.md", KB_B)
        listed = self.service.list_documents(KB_B)
        single = self.service.get_document_status(document_id)
        self.assertEqual(len(listed), 1)
        self.assertNotIn("history", listed[0])
        single.pop("history")
        self.assertEqual(listed[0], single)
        self.assertEqual((single["kb_id"], single["file_type"], single["file_size_bytes"]), (KB_B, ".md", 10))

    def test_pre_assigned_document_id_is_used(self):
        document_id = IngestionUploadService.new_document_id()
        self.assertTrue(document_id.startswith("doc-"))
        response = self.intake.create_upload_request(
            [UploadFileInput("a.txt", 10, "2026-10-20T12:00:00Z", document_id=document_id)], KB_A,
        )
        self.assertEqual(response["files"][0]["document_id"], document_id)
        self.assertEqual(self.repository.get_document(document_id)["metadata"]["document_id"], document_id)

    def test_resolve_kb_id_normalizes_or_reports_unknown(self):
        self.assertEqual(self.intake.resolve_kb_id("  IT_Policies "), (KB_A, None))
        kb_id, error = self.intake.resolve_kb_id("finance")
        self.assertIsNone(kb_id)
        self.assertEqual(error["code"], "unknown_kb")


if __name__ == "__main__":
    unittest.main()
