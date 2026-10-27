"""DELETE /kbs/{kb_id}/documents/{document_id}: SQLite, Chroma, BM25 and upload cleanup, errors, repeat safety."""

from contextlib import closing
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi.testclient import TestClient

from indexing_fakes import FakeEmbedder, ephemeral_vector_index

from api.api_app import create_app
from ingestion.ingestion_artifact_repository import SQLiteArtifactRepository
from ingestion.ingestion_chunking import FixedSizeCharChunker
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_status_repository import (
    DELETE_BUSY,
    DELETE_DELETED,
    DELETE_NOT_FOUND,
    SQLiteIngestionStatusRepository,
)
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput
from retrieval.retrieval_retriever import BASELINE_CHUNKER

KB_A, KB_B = "it_policies", "hw_datasheets"
POLL_INTERVAL_SECONDS = 0.05
POLL_TIMEOUT_SECONDS = 10.0
POLICY_TXT = b"The acceptable use policy forbids sharing passwords. Report phishing to the help desk."
DATASHEET_MD = b"# GPIO\n\nGPIO17 doubles as a UART pin. The input voltage range is 1.8 to 5.5 V.\n"
OTHER_DATASHEET_MD = b"# Power\n\nThe regulator accepts 5 V on VSYS and delivers 3.3 V to the core.\n"


def make_config():
    config = IngestionConfig()
    config.allowed_kb_ids = (KB_A, KB_B)
    config.allowed_extensions = (".pdf", ".txt", ".md")
    config.max_file_size_mb = 1
    config.max_files_per_batch = 4
    return config


class DeleteApiTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.upload_dir = os.path.join(directory.name, "uploads")
        self.status_repository = SQLiteIngestionStatusRepository(os.path.join(directory.name, "api.sqlite3"))
        self.vector_index = ephemeral_vector_index(self)
        self.app = create_app(
            config=make_config(), status_repository=self.status_repository, upload_dir=self.upload_dir,
            embedder=FakeEmbedder(), vector_index=self.vector_index,
        )
        self.artifacts = self.app.state.artifact_repository
        self.keyword_index = self.app.state.keyword_index

    def upload(self, client, kb_id, name, content):
        response = client.post("/documents", data={"kb_id": kb_id},
                               files=[("files", (name, content, "application/octet-stream"))])
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()["files"][0]["document_id"]

    def ingest(self, client, kb_id, name, content):
        """Upload one file and wait until the worker marks it success. Returns its document ID."""
        document_id = self.upload(client, kb_id, name, content)
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        while True:
            status = client.get("/documents/{0}".format(document_id)).json()
            if status["is_terminal"]:
                self.assertEqual(status["ingestion_status"], "success", status)
                return document_id
            if time.monotonic() > deadline:
                self.fail("Document not terminal after {0} s".format(POLL_TIMEOUT_SECONDS))
            time.sleep(POLL_INTERVAL_SECONDS)

    def delete(self, client, kb_id, document_id):
        return client.delete("/kbs/{0}/documents/{1}".format(kb_id, document_id))

    def assert_error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.text)
        self.assertEqual(response.json()["code"], code)
        self.assertIn("details", response.json())

    def keyword_hits(self, kb_id, query):
        return self.keyword_index.query(kb_id, query, BASELINE_CHUNKER, 10)


class TestDeleteRemovesEverywhere(DeleteApiTestCase):
    def test_delete_removes_sqlite_chroma_bm25_search_results_and_upload(self):
        with TestClient(self.app) as client:
            doomed = self.ingest(client, KB_B, "gpio.md", DATASHEET_MD)
            kept = self.ingest(client, KB_B, "power.md", OTHER_DATASHEET_MD)
            chunk_ids = [chunk["chunk_id"] for chunk in self.artifacts.get_chunks(doomed)]
            self.assertTrue(chunk_ids)
            # This query builds and caches the KB's BM25 index, so the delete must invalidate it.
            self.assertEqual({chunk_id for chunk_id, _ in self.keyword_hits(KB_B, "gpio17")}, set(chunk_ids))
            self.assertTrue(os.path.isdir(os.path.join(self.upload_dir, doomed)))

            response = self.delete(client, KB_B, doomed)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"document_id": doomed, "kb_id": KB_B, "deleted": True})

            self.assertIsNone(self.status_repository.get_document(doomed))
            self.assertEqual(self.status_repository.get_status_history(doomed), [])
            self.assertEqual(self.artifacts.count_chunks(document_id=doomed), 0)
            self.assertIsNone(self.artifacts.get_full_text(doomed))
            self.assertEqual(self.vector_index.count(KB_B, document_id=doomed), 0)
            self.assertFalse(os.path.exists(os.path.join(self.upload_dir, doomed)))
            self.assertEqual(client.get("/documents/{0}".format(doomed)).status_code, 404)
            listed = [d["document_id"] for d in client.get("/documents", params={"kb_id": KB_B}).json()["documents"]]
            self.assertEqual(listed, [kept])
            self.assertEqual(client.get("/kbs").json()["kbs"][1]["counts"]["success"], 1)

            # BM25 rebuilt from SQLite on the next query: the deleted chunks are gone, the other document stays.
            self.assertEqual(self.keyword_hits(KB_B, "gpio17"), [])
            self.assertTrue(self.keyword_hits(KB_B, "regulator"))
            search = client.post("/search", json={"query": "gpio17 uart pin", "kb_ids": [KB_B]}).json()
            lists = search["results"][KB_B]
            for source in ("vector", "keyword"):
                self.assertNotIn(doomed, {hit["document_id"] for hit in lists[source]}, source)
            self.assertIn(kept, {hit["document_id"] for hit in lists["vector"]})

            # The other document's files and vectors are untouched.
            self.assertTrue(os.path.isdir(os.path.join(self.upload_dir, kept)))
            self.assertGreater(self.vector_index.count(KB_B, document_id=kept), 0)

    def test_failed_document_can_be_deleted(self):
        with TestClient(self.app) as client:
            response = client.post("/documents", data={"kb_id": KB_A},
                                   files=[("files", ("empty.txt", b"   ", "text/plain"))])
            entries = response.json()["files"]
            document_id = entries[0].get("document_id")
            if entries[0]["status"] != "accepted":
                self.skipTest("empty file rejected at intake")
            deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
            while not client.get("/documents/{0}".format(document_id)).json()["is_terminal"]:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(POLL_INTERVAL_SECONDS)
            self.assertEqual(client.get("/documents/{0}".format(document_id)).json()["ingestion_status"], "failed")
            self.assertEqual(self.delete(client, KB_A, document_id).status_code, 200)
            self.assertIsNone(self.status_repository.get_document(document_id))


class TestDeleteErrors(DeleteApiTestCase):
    def test_unknown_document_is_404(self):
        with TestClient(self.app) as client:
            body = self.delete(client, KB_A, "doc-" + "0" * 32)
            self.assert_error(body, 404, "not_found")

    def test_unknown_kb_and_malformed_id_are_400(self):
        with TestClient(self.app) as client:
            self.assert_error(self.delete(client, "nope", "doc-" + "0" * 32), 400, "unknown_kb")
            self.assert_error(self.delete(client, KB_A, "bad.id"), 400, "validation_failed")

    def test_queued_document_is_409_and_untouched(self):
        # No `with`: the lifespan (and so the worker) never starts, so the upload stays queued.
        client = TestClient(self.app)
        document_id = self.upload(client, KB_A, "policy.txt", POLICY_TXT)
        self.assert_error(self.delete(client, KB_A, document_id), 409, "document_busy")
        self.assertEqual(self.status_repository.get_document(document_id)["ingestion_status"], "queued")
        self.assertTrue(os.path.isdir(os.path.join(self.upload_dir, document_id)))

    def test_processing_document_is_409_and_untouched(self):
        client = TestClient(self.app)
        document_id = self.upload(client, KB_A, "policy.txt", POLICY_TXT)
        self.assertTrue(self.status_repository.mark_processing(document_id))
        self.assert_error(self.delete(client, KB_A, document_id), 409, "document_busy")
        self.assertEqual(self.status_repository.get_document(document_id)["ingestion_status"], "processing")
        self.assertTrue(os.path.isdir(os.path.join(self.upload_dir, document_id)))

    def test_document_in_another_kb_is_404_and_nothing_is_touched(self):
        with TestClient(self.app) as client:
            document_id = self.ingest(client, KB_B, "gpio.md", DATASHEET_MD)
            chunk_count = self.artifacts.count_chunks(document_id=document_id)
            with patch.object(self.vector_index, "delete_document") as vectors, \
                    patch.object(self.keyword_index, "invalidate") as invalidate:
                self.assert_error(self.delete(client, KB_A, document_id), 404, "not_found")
            vectors.assert_not_called()
            invalidate.assert_not_called()
            self.assertIsNotNone(self.status_repository.get_document(document_id))
            self.assertEqual(self.artifacts.count_chunks(document_id=document_id), chunk_count)
            self.assertEqual(self.vector_index.count(KB_B, document_id=document_id), chunk_count)
            self.assertTrue(os.path.isdir(os.path.join(self.upload_dir, document_id)))


class TestDeleteTwiceAndCleanup(DeleteApiTestCase):
    def test_deleting_twice_is_safe(self):
        with TestClient(self.app) as client:
            document_id = self.ingest(client, KB_A, "policy.txt", POLICY_TXT)
            self.assertEqual(self.delete(client, KB_A, document_id).status_code, 200)
            self.assert_error(self.delete(client, KB_A, document_id), 404, "not_found")
            self.assertEqual(client.get("/kbs").json()["kbs"][0]["total"], 0)

    def test_true_orphan_is_cleaned_before_the_404(self):
        """An ID in no KB (an interrupted delete) still has its leftover vectors and upload removed."""
        with TestClient(self.app) as client:
            document_id = self.ingest(client, KB_A, "policy.txt", POLICY_TXT)
            # Simulate a crash after the SQLite step: row gone, vectors and file left behind.
            self.assertEqual(self.status_repository.delete_document(document_id), DELETE_DELETED)
            self.assertGreater(self.vector_index.count(KB_A, document_id=document_id), 0)
            self.assertTrue(os.path.isdir(os.path.join(self.upload_dir, document_id)))
            self.assert_error(self.delete(client, KB_A, document_id), 404, "not_found")
            self.assertEqual(self.vector_index.count(KB_A, document_id=document_id), 0)
            self.assertFalse(os.path.exists(os.path.join(self.upload_dir, document_id)))
            self.assert_error(self.delete(client, KB_A, document_id), 404, "not_found")

    def test_cleanup_failure_is_reported_runs_every_step_and_a_retry_finishes_it(self):
        with TestClient(self.app) as client:
            document_id = self.ingest(client, KB_A, "policy.txt", POLICY_TXT)
            with patch.object(self.vector_index, "delete_document", side_effect=RuntimeError("chroma down")), \
                    patch.object(self.keyword_index, "invalidate", wraps=self.keyword_index.invalidate) as invalidate:
                response = self.delete(client, KB_A, document_id)
            self.assert_error(response, 500, "internal_failure")
            self.assertIn("vectors", response.json()["details"])
            self.assertNotIn("chroma down", response.text)
            # (The worker's own post-job invalidate may also land in this window.)
            invalidate.assert_any_call(KB_A)
            self.assertIsNone(self.status_repository.get_document(document_id))
            self.assertFalse(os.path.exists(os.path.join(self.upload_dir, document_id)))
            self.assertGreater(self.vector_index.count(KB_A, document_id=document_id), 0)

            self.assert_error(self.delete(client, KB_A, document_id), 404, "not_found")
            self.assertEqual(self.vector_index.count(KB_A, document_id=document_id), 0)


class TestKeywordIndexAfterDelete(DeleteApiTestCase):
    def test_invalidate_makes_the_next_query_rebuild_from_sqlite(self):
        # Stored by hand, with no app lifespan: the worker's own invalidate can't disturb the cache.
        service = IngestionUploadService(config=make_config(), status_repository=self.status_repository)
        document_id = service.create_upload_request(
            [UploadFileInput("gpio.md", 10, "2026-10-10T12:00:00Z")], KB_B)["files"][0]["document_id"]
        self.status_repository.mark_processing(document_id)
        text = DATASHEET_MD.decode("utf-8")
        chunker = FixedSizeCharChunker(chunk_size=200, overlap=20)
        self.artifacts.save_document_artifacts(
            document_id, KB_B, text, {"extractor": "txt-decode"}, BASELINE_CHUNKER,
            chunker.iter_chunks(text, {"document_id": document_id, "kb_id": KB_B}))
        self.status_repository.mark_success(document_id)

        self.assertTrue(self.keyword_hits(KB_B, "gpio17"))  # cached now
        # Remove the rows without telling the index: the stale cache still answers.
        self.assertEqual(self.status_repository.delete_document(document_id), DELETE_DELETED)
        self.assertTrue(self.keyword_hits(KB_B, "gpio17"))
        self.keyword_index.invalidate(KB_B)
        self.assertEqual(self.keyword_hits(KB_B, "gpio17"), [])


class TestRepositoryDelete(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "r.sqlite3")
        self.repository = SQLiteIngestionStatusRepository(self.path)
        self.service = IngestionUploadService(config=make_config(), status_repository=self.repository)

    def queue(self, name="notes.txt"):
        entry = self.service.create_upload_request([UploadFileInput(name, 10, "2026-10-10T12:00:00Z")], KB_A)
        return entry["files"][0]["document_id"]

    def history_rows(self, document_id):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(
                "SELECT COUNT(*) FROM ingestion_status_history WHERE document_id = ?", (document_id,)).fetchone()[0]

    def test_unknown_document_is_not_found(self):
        self.assertEqual(self.repository.delete_document("doc-missing"), DELETE_NOT_FOUND)

    def test_queued_and_processing_are_busy_and_unchanged(self):
        document_id = self.queue()
        self.assertEqual(self.repository.delete_document(document_id), DELETE_BUSY)
        self.repository.mark_processing(document_id)
        self.assertEqual(self.repository.delete_document(document_id), DELETE_BUSY)
        self.assertEqual(self.repository.get_document(document_id)["ingestion_status"], "processing")
        self.assertEqual(self.history_rows(document_id), 2)

    def test_terminal_document_is_deleted_without_artifact_tables(self):
        document_id = self.queue()
        self.repository.mark_processing(document_id)
        self.repository.mark_success(document_id)
        self.assertEqual(self.repository.delete_document(document_id), DELETE_DELETED)
        self.assertIsNone(self.repository.get_document(document_id))
        self.assertEqual(self.history_rows(document_id), 0)
        self.assertEqual(self.repository.delete_document(document_id), DELETE_NOT_FOUND)

    def test_chunks_and_text_are_deleted_with_the_document(self):
        artifacts = SQLiteArtifactRepository(self.path)
        document_id = self.queue()
        self.repository.mark_processing(document_id)
        text = "Some policy text to chunk."
        chunker = FixedSizeCharChunker(chunk_size=10, overlap=2)
        artifacts.save_document_artifacts(
            document_id, KB_A, text, {"extractor": "txt-decode"}, chunker.name,
            chunker.iter_chunks(text, {"document_id": document_id, "kb_id": KB_A}))
        self.repository.mark_success(document_id)
        self.assertGreater(artifacts.count_chunks(document_id=document_id), 0)
        self.assertEqual(self.repository.delete_document(document_id), DELETE_DELETED)
        self.assertEqual(artifacts.count_chunks(document_id=document_id), 0)
        self.assertIsNone(artifacts.get_full_text(document_id))


if __name__ == "__main__":
    unittest.main()
