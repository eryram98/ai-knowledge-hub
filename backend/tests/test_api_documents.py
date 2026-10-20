"""HTTP API (F1) through FastAPI's TestClient: upload, worker, status, inventory, errors, lifespan."""

import json
import os
import sys
import tempfile
import threading
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
from pdf_fixtures import HAS_PYPDF, build_pdf

from api.api_app import create_app
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput

KB_IDS = ("it_policies", "hw_datasheets")
POLL_INTERVAL_SECONDS = 0.05
POLL_TIMEOUT_SECONDS = 10.0
TXT = b"Plain text knowledge about the acceptable use policy. " * 5
MD = b"# Password policy\n\nPasswords must be rotated every **90 days**.\n"
PDF_PAGES = ["First page of the datasheet", "Second page lists the operating voltage"]


def make_config():
    """Real IngestionConfig with fixed values, so a local .env can't change the tests."""
    config = IngestionConfig()
    config.allowed_kb_ids = KB_IDS
    config.allowed_extensions = (".pdf", ".txt", ".md")
    config.max_file_size_mb = 1
    config.max_files_per_batch = 4
    return config


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = directory.name
        self.upload_dir = os.path.join(self.tmp, "uploads")
        self.status_repository = SQLiteIngestionStatusRepository(os.path.join(self.tmp, "api.sqlite3"))
        self.config = make_config()
        # Fake embedder and in-memory Chroma: otherwise the app would load bge-small and
        # write to backend/instance/chroma/.
        self.embedder = FakeEmbedder()
        self.vector_index = ephemeral_vector_index(self)
        self.app = create_app(
            config=self.config, status_repository=self.status_repository, upload_dir=self.upload_dir,
            embedder=self.embedder, vector_index=self.vector_index,
        )
        self.responses = []

    def client(self, **kwargs):
        return TestClient(self.app, **kwargs)

    def call(self, client, method, url, **kwargs):
        response = client.request(method, url, **kwargs)
        self.responses.append(response)
        return response

    def upload(self, client, files, kb_id=KB_IDS[0]):
        """files: list of (name, bytes). Returns the response."""
        parts = [("files", (name, content, "application/octet-stream")) for name, content in files]
        return self.call(client, "POST", "/documents", data={"kb_id": kb_id}, files=parts)

    def wait_for_terminal(self, client, document_ids):
        """Poll GET /documents/{id} until every document is terminal, or fail after the timeout."""
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        while True:
            statuses = {
                document_id: self.call(client, "GET", "/documents/{0}".format(document_id)).json()
                for document_id in document_ids
            }
            if all(status["is_terminal"] for status in statuses.values()):
                return statuses
            if time.monotonic() > deadline:
                self.fail("Documents not terminal after {0} s: {1}".format(
                    POLL_TIMEOUT_SECONDS, {k: v["ingestion_status"] for k, v in statuses.items()}))
            time.sleep(POLL_INTERVAL_SECONDS)

    def assert_canonical_error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.text)
        body = response.json()
        self.assertEqual(body["code"], code)
        self.assertIsInstance(body["message"], str)
        self.assertIn("details", body)
        self.assertNotIn("Traceback", response.text)
        return body

    def stored_files(self):
        """Every file under the temp dir, relative to it, excluding the database."""
        found = []
        for root, _dirs, names in os.walk(self.tmp):
            for name in names:
                if not name.startswith("api.sqlite3"):
                    found.append(os.path.relpath(os.path.join(root, name), self.tmp))
        return sorted(found)


@unittest.skipUnless(HAS_PYPDF, "pypdf not installed")
class TestUploadEndToEnd(ApiTestCase):
    def test_txt_md_pdf_reach_success_and_show_in_inventory_and_kbs(self):
        with self.client() as client:
            response = self.upload(client, [
                ("policy.txt", TXT), ("passwords.md", MD), ("datasheet.pdf", build_pdf(PDF_PAGES)),
            ])
            self.assertEqual(response.status_code, 202, response.text)
            body = response.json()
            self.assertEqual(body["status"], "received")
            self.assertEqual([f["status"] for f in body["files"]], ["accepted"] * 3)
            ids = {f["metadata"]["original_filename"]: f["document_id"] for f in body["files"]}

            statuses = self.wait_for_terminal(client, ids.values())
            for name, document_id in ids.items():
                status = statuses[document_id]
                self.assertEqual(status["ingestion_status"], "success", (name, status))
                self.assertEqual(status["kb_id"], KB_IDS[0])
                self.assertEqual(status["original_filename"], name)
                self.assertEqual([h["status"] for h in status["history"]], ["queued", "processing", "success"])
                self.assertIsNone(status["failure_code"])
                self.assertIsNone(status["failure_reason"])
                self.assertTrue(os.path.isfile(os.path.join(self.upload_dir, document_id, name)))
                chunk_count = self.app.state.artifact_repository.count_chunks(document_id=document_id)
                self.assertGreater(chunk_count, 0)
                self.assertEqual(self.vector_index.count(KB_IDS[0], document_id=document_id), chunk_count)

            inventory = self.call(client, "GET", "/documents").json()["documents"]
            self.assertEqual(sorted(d["document_id"] for d in inventory), sorted(ids.values()))
            self.assertTrue(all("history" not in d for d in inventory))
            self.assertEqual({d["ingestion_status"] for d in inventory}, {"success"})
            in_kb = self.call(client, "GET", "/documents", params={"kb_id": KB_IDS[0].upper()}).json()
            self.assertEqual(len(in_kb["documents"]), 3)
            self.assertEqual(self.call(client, "GET", "/documents", params={"kb_id": KB_IDS[1]}).json(),
                             {"documents": []})

            kbs = self.call(client, "GET", "/kbs").json()["kbs"]
            self.assertEqual([kb["kb_id"] for kb in kbs], list(KB_IDS))
            self.assertEqual(kbs[0]["counts"], {"queued": 0, "processing": 0, "success": 3, "failed": 0})
            self.assertEqual(kbs[0]["total"], 3)
            self.assertEqual(kbs[1]["total"], 0)

            batch = self.call(client, "GET", "/documents/status",
                              params={"document_id": list(ids.values()) + ["doc-missing"]}).json()
            self.assertEqual(batch["counts"]["success"], 3)
            self.assertEqual(batch["missing_document_ids"], ["doc-missing"])
            # An unknown ID never counts as completed, so the batch is not complete.
            self.assertEqual((batch["total"], batch["completed"], batch["is_complete"]), (4, 3, False))

    def test_failed_document_reports_failure_code_and_reason(self):
        with self.client() as client, self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            body = self.upload(client, [("empty.txt", b"   \n")]).json()
            document_id = body["files"][0]["document_id"]
            status = self.wait_for_terminal(client, [document_id])[document_id]
        self.assertEqual(status["ingestion_status"], "failed")
        self.assertEqual(status["failure_code"], "empty_content")
        self.assertTrue(status["failure_reason"])


class TestUploadRejections(ApiTestCase):
    def test_unknown_kb_is_400_and_leaves_nothing_behind(self):
        with self.client() as client:
            response = self.upload(client, [("a.txt", TXT), ("b.md", MD)], kb_id="finance")
            body = self.assert_canonical_error(response, 400, "unknown_kb")
            self.assertEqual(body["field"], "kb_id")
            self.assertEqual(self.call(client, "GET", "/documents").json(), {"documents": []})
        self.assertEqual(self.stored_files(), [])

    def test_unknown_kb_filter_on_inventory_is_400(self):
        with self.client() as client:
            self.assert_canonical_error(self.call(client, "GET", "/documents", params={"kb_id": "nope"}),
                                        400, "unknown_kb")

    def test_batch_over_limit_is_400(self):
        with self.client() as client:
            files = [("f{0}.txt".format(i), TXT) for i in range(self.config.max_files_per_batch + 1)]
            self.assert_canonical_error(self.upload(client, files), 400, "batch_limit_exceeded")
        self.assertEqual(self.stored_files(), [])

    def test_oversize_file_is_rejected_and_not_stored_while_good_file_succeeds(self):
        too_big = b"x" * (self.config.max_file_size_bytes + 1)
        with self.client() as client:
            response = self.upload(client, [("big.txt", too_big), ("good.txt", TXT)])
            self.assertEqual(response.status_code, 202, response.text)
            body = response.json()
            self.assertEqual(body["status"], "partial")
            big, good = body["files"]
            self.assertEqual(big["status"], "rejected")
            self.assertEqual(big["error"]["code"], "file_too_large")
            self.assertEqual(big["error"]["file_name"], "big.txt")
            self.assertIn(str(len(too_big)), big["error"]["details"])
            status = self.wait_for_terminal(client, [good["document_id"]])[good["document_id"]]
            self.assertEqual(status["ingestion_status"], "success")
            inventory = self.call(client, "GET", "/documents").json()["documents"]
        self.assertEqual([d["document_id"] for d in inventory], [good["document_id"]])
        self.assertEqual(self.stored_files(), [os.path.join("uploads", good["document_id"], "good.txt")])

    def test_unsupported_format_is_rejected_per_file_with_202(self):
        with self.client() as client:
            response = self.upload(client, [("tool.exe", b"MZ")])
        self.assertEqual(response.status_code, 202, response.text)
        body = response.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["files"][0]["error"]["code"], "unsupported_format")
        self.assertEqual(self.stored_files(), [])

    def test_request_body_over_cap_is_413_with_content_length(self):
        cap = self.config.max_files_per_batch * self.config.max_file_size_bytes + 1024 * 1024
        with self.client() as client:
            response = self.upload(client, [("huge.txt", b"x" * (cap + 1))])
            self.assert_canonical_error(response, 413, "file_too_large")
            self.assertEqual(self.call(client, "GET", "/documents").json(), {"documents": []})
        self.assertEqual(self.stored_files(), [])

    def test_request_body_over_cap_is_413_when_chunked(self):
        cap = self.config.max_files_per_batch * self.config.max_file_size_bytes + 1024 * 1024
        boundary = "testboundary"
        body = (
            "--{0}\r\nContent-Disposition: form-data; name=\"kb_id\"\r\n\r\n{1}\r\n"
            "--{0}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"huge.txt\"\r\n"
            "Content-Type: text/plain\r\n\r\n".format(boundary, KB_IDS[0]).encode()
            + b"x" * (cap + 1)
            + "\r\n--{0}--\r\n".format(boundary).encode()
        )

        def chunks():
            for start in range(0, len(body), 256 * 1024):
                yield body[start:start + 256 * 1024]

        with self.client() as client:
            response = self.call(client, "POST", "/documents", content=chunks(),
                                 headers={"content-type": "multipart/form-data; boundary=" + boundary})
            self.assertNotIn("content-length", {k.lower() for k in response.request.headers})
            self.assert_canonical_error(response, 413, "file_too_large")
        self.assertEqual(self.stored_files(), [])

    def test_path_traversal_names_are_stored_inside_the_document_directory(self):
        names = ["../../evil1.txt", "..\\..\\evil2.txt", "C:\\Windows\\evil3.txt", "/etc/evil4.md", "..", "CON.txt"]
        with self.client() as client:
            response = self.upload(client, [(name, TXT) for name in names[:4]])
            response_2 = self.upload(client, [(name, TXT) for name in names[4:]])
        self.assertEqual(response.status_code, 202, response.text)
        entries = response.json()["files"] + response_2.json()["files"]
        stored = [entry["metadata"]["original_filename"] for entry in entries]
        self.assertEqual(stored, ["evil1.txt", "evil2.txt", "evil3.txt", "evil4.md", "upload", "_CON.txt"])
        # Every file written lives at uploads/<document_id>/<sanitized name>; nothing escaped.
        for path in self.stored_files():
            parts = path.split(os.sep)
            self.assertEqual(len(parts), 3, path)
            self.assertEqual(parts[0], "uploads", path)
        for entry in entries[:4]:
            name = entry["metadata"]["original_filename"]
            self.assertTrue(os.path.isfile(os.path.join(self.upload_dir, entry["document_id"], name)))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil1.txt")))

    def test_missing_kb_id_or_files_is_400_validation_failed(self):
        with self.client() as client:
            no_kb = self.call(client, "POST", "/documents", files=[("files", ("a.txt", TXT, "text/plain"))])
            body = self.assert_canonical_error(no_kb, 400, "validation_failed")
            self.assertIn("kb_id", body["details"])
            no_files = self.call(client, "POST", "/documents", data={"kb_id": KB_IDS[0]})
            self.assertIn("files", self.assert_canonical_error(no_files, 400, "validation_failed")["details"])
        self.assertEqual(self.stored_files(), [])


class TestStatusAndErrors(ApiTestCase):
    def test_unknown_document_is_404_not_found(self):
        with self.client() as client:
            body = self.assert_canonical_error(self.call(client, "GET", "/documents/doc-nope"), 404, "not_found")
        self.assertIn("doc-nope", body["details"])

    def test_unknown_route_and_wrong_method_use_the_canonical_body(self):
        with self.client() as client:
            self.assert_canonical_error(self.call(client, "GET", "/nowhere"), 404, "not_found")
            self.assert_canonical_error(self.call(client, "DELETE", "/kbs"), 405, "validation_failed")

    def test_batch_status_needs_document_ids(self):
        with self.client() as client:
            self.assert_canonical_error(self.call(client, "GET", "/documents/status"), 400, "validation_failed")
            blank = self.call(client, "GET", "/documents/status", params={"document_id": " "})
            self.assert_canonical_error(blank, 400, "validation_failed")

    def test_unexpected_error_is_500_without_internals(self):
        with self.client(raise_server_exceptions=False) as client:
            secret = "secret detail at C:\\private\\path"
            with patch.object(self.status_repository, "list_documents", side_effect=RuntimeError(secret)):
                with self.assertLogs("api.api_errors", level="ERROR"):
                    response = self.call(client, "GET", "/documents")
        body = self.assert_canonical_error(response, 500, "internal_failure")
        self.assertIsNone(body["details"])
        self.assertNotIn("secret", response.text)
        self.assertNotIn("RuntimeError", response.text)

    @unittest.skipUnless(HAS_PYPDF, "pypdf not installed")
    def test_no_response_exposes_temp_file_path_or_local_paths(self):
        with self.client() as client:
            body = self.upload(client, [("a.txt", TXT), ("b.md", MD), ("c.exe", b"MZ"),
                                        ("big.txt", b"x" * (self.config.max_file_size_bytes + 1))]).json()
            accepted = [f["document_id"] for f in body["files"] if f["status"] == "accepted"]
            self.wait_for_terminal(client, accepted)
            self.call(client, "GET", "/documents")
            self.call(client, "GET", "/documents/status", params={"document_id": accepted})
            self.call(client, "GET", "/kbs")
            self.upload(client, [("a.txt", TXT)], kb_id="unknown")
            self.call(client, "GET", "/documents/doc-nope")
        # The service-layer result still carries the path for the worker.
        self.assertTrue(self.status_repository.get_document(accepted[0])["temp_file_path"])
        temp_dir_name = os.path.basename(self.tmp)
        self.assertGreater(len(self.responses), 8)
        for response in self.responses:
            self.assertNotIn("temp_file_path", response.text, response.request.url)
            self.assertNotIn(temp_dir_name, response.text, response.request.url)
            self.assertNotIn(json.dumps(self.upload_dir)[1:-1], response.text, response.request.url)


class TestLifespan(ApiTestCase):
    def test_worker_starts_with_the_app_and_stops_cleanly(self):
        with self.client() as client:
            thread = self.app.state.worker_thread
            self.assertIsNotNone(thread)
            self.assertTrue(thread.is_alive())
            self.assertEqual(thread.name, "ingestion-worker")
            self.assertEqual(self.call(client, "GET", "/kbs").status_code, 200)
        self.assertFalse(thread.is_alive())
        self.assertNotIn(thread, threading.enumerate())
        self.assertFalse([t for t in threading.enumerate() if t.name == "ingestion-worker" and t.is_alive()])

    def test_documents_still_queued_at_startup_are_processed(self):
        stored = os.path.join(self.tmp, "left_over.txt")
        with open(stored, "wb") as handle:
            handle.write(TXT)
        intake = IngestionUploadService(config=self.config, status_repository=self.status_repository)
        response = intake.create_upload_request([
            UploadFileInput("left_over.txt", len(TXT), "2026-10-20T12:00:00Z", temp_file_path=stored),
            UploadFileInput("no_file.txt", 10, "2026-10-20T12:00:00Z"),
        ], KB_IDS[0])
        left_over, no_file = (entry["document_id"] for entry in response["files"])

        with self.assertLogs("api.api_app", level="INFO") as logs:
            with self.client() as client:
                status = self.wait_for_terminal(client, [left_over])[left_over]
        self.assertEqual(status["ingestion_status"], "success")
        # A queued row without a stored file can't be processed; it is skipped with a warning.
        self.assertEqual(self.status_repository.get_document(no_file)["ingestion_status"], "queued")
        self.assertTrue(any("Re-enqueued 1 document" in line for line in logs.output), logs.output)
        self.assertTrue(any(no_file in line for line in logs.output), logs.output)

    def test_documents_left_processing_are_failed_and_their_vectors_removed(self):
        stored = os.path.join(self.tmp, "crashed.txt")
        with open(stored, "wb") as handle:
            handle.write(TXT)
        intake = IngestionUploadService(config=self.config, status_repository=self.status_repository)
        response = intake.create_upload_request([
            UploadFileInput("crashed.txt", len(TXT), "2026-10-20T12:00:00Z", temp_file_path=stored),
        ], KB_IDS[0])
        crashed = response["files"][0]["document_id"]
        self.status_repository.mark_processing(crashed)
        self.vector_index.replace_document(
            KB_IDS[0], crashed, "fixed-size-char-baseline",
            [{"chunk_id": crashed + ":c0", "chunk_index": 0}], [FakeEmbedder.vector("half written")],
        )

        with self.assertLogs("api.api_app", level="WARNING") as logs:
            with self.client() as client:
                status = self.call(client, "GET", "/documents/{0}".format(crashed)).json()
        self.assertEqual(status["ingestion_status"], "failed")
        self.assertEqual(status["failure_code"], "internal_failure")
        self.assertEqual(status["failure_reason"], "interrupted by server restart")
        self.assertEqual(self.vector_index.count(KB_IDS[0], document_id=crashed), 0)
        self.assertTrue(any("Marked 1 document(s) failed" in line for line in logs.output), logs.output)


class TestIndexingWiring(ApiTestCase):
    def test_indexing_parts_are_on_app_state(self):
        self.assertIs(self.app.state.embedder, self.embedder)
        self.assertIs(self.app.state.vector_index, self.vector_index)
        self.assertIs(self.app.state.indexer.vector_index, self.vector_index)
        self.assertIs(self.app.state.keyword_index, self.app.state.indexer.keyword_index)

    def test_uploaded_document_is_searchable_by_vector_and_keyword_after_success(self):
        with self.client() as client:
            body = self.upload(client, [("pins.txt", b"GPIO17 is UART0 RX on the RP2040 board. " * 3)],
                               kb_id=KB_IDS[1]).json()
            document_id = body["files"][0]["document_id"]
            status = self.wait_for_terminal(client, [document_id])[document_id]
        self.assertEqual(status["ingestion_status"], "success")
        chunker = "fixed-size-char-baseline"
        keyword_hits = self.app.state.keyword_index.query(KB_IDS[1], "gpio17", chunker, 5)
        self.assertTrue(keyword_hits)
        vector_hits = self.vector_index.query(KB_IDS[1], self.embedder.embed_query("gpio17 uart0"), chunker, 5)
        self.assertTrue(vector_hits)
        self.assertTrue(all(h[0].startswith(document_id) for h in keyword_hits + vector_hits))
        self.assertEqual(self.app.state.keyword_index.query(KB_IDS[0], "gpio17", chunker, 5), [])

    def test_indexing_failure_reports_canonical_code(self):
        self.embedder.fail_with = RuntimeError("model unavailable")
        with self.client() as client, self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            body = self.upload(client, [("a.txt", TXT)]).json()
            document_id = body["files"][0]["document_id"]
            status = self.wait_for_terminal(client, [document_id])[document_id]
        self.assertEqual(status["ingestion_status"], "failed")
        self.assertEqual(status["failure_code"], "indexing_failure")
        self.assertIn("model unavailable", status["failure_reason"])
        self.assertEqual(self.vector_index.count(KB_IDS[0]), 0)


if __name__ == "__main__":
    unittest.main()
