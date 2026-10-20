"""POST /search (F3) through TestClient: raw lists per KB, merged list, merge-not-implemented path, validation.

Documents go through the real upload endpoint and worker (fake embedder,
in-memory Chroma), so the search runs against what ingestion really indexed.
"""

import os
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
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from retrieval.retrieval_config import RetrievalConfig

KB_IDS = ("it_policies", "hw_datasheets")
POLL_INTERVAL_SECONDS = 0.05
POLL_TIMEOUT_SECONDS = 10.0
POLICY_TXT = b"The acceptable use policy forbids sharing passwords. Report phishing to the help desk."
DATASHEET_MD = b"# GPIO\n\nGPIO17 doubles as a UART pin. The input voltage range is 1.8 to 5.5 V.\n"


def make_config():
    """Real IngestionConfig with fixed values, so a local .env can't change the tests."""
    config = IngestionConfig()
    config.allowed_kb_ids = KB_IDS
    config.allowed_extensions = (".pdf", ".txt", ".md")
    config.max_file_size_mb = 1
    config.max_files_per_batch = 4
    return config


def make_retrieval_config(top_k=20):
    retrieval_config = RetrievalConfig()
    retrieval_config.top_k = top_k
    return retrieval_config


class SearchApiTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.status_repository = SQLiteIngestionStatusRepository(os.path.join(directory.name, "api.sqlite3"))
        self.embedder = FakeEmbedder()
        self.app = create_app(
            config=make_config(), status_repository=self.status_repository,
            upload_dir=os.path.join(directory.name, "uploads"), embedder=self.embedder,
            vector_index=ephemeral_vector_index(self), retrieval_config=make_retrieval_config(),
        )

    def ingest(self, client, kb_id, name, content):
        """Upload one file and wait until the worker marks it success. Returns its document ID."""
        response = client.post("/documents", data={"kb_id": kb_id},
                               files=[("files", (name, content, "application/octet-stream"))])
        self.assertEqual(response.status_code, 202, response.text)
        document_id = response.json()["files"][0]["document_id"]
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        while True:
            status = client.get("/documents/{0}".format(document_id)).json()
            if status["is_terminal"]:
                self.assertEqual(status["ingestion_status"], "success", status)
                return document_id
            if time.monotonic() > deadline:
                self.fail("Document not terminal after {0} s".format(POLL_TIMEOUT_SECONDS))
            time.sleep(POLL_INTERVAL_SECONDS)

    def ingest_both(self, client):
        return (self.ingest(client, "it_policies", "policy.txt", POLICY_TXT),
                self.ingest(client, "hw_datasheets", "gpio.md", DATASHEET_MD))


class TestSearchEndpoint(SearchApiTestCase):
    def search_datasheets(self):
        """Ingest one document per KB, then search hw_datasheets only. Returns (policy_id, datasheet_id, body)."""
        with TestClient(self.app) as client:
            policy_id, datasheet_id = self.ingest_both(client)
            response = client.post("/search", json={"query": "gpio17 uart pin", "kb_ids": ["hw_datasheets"]})
        self.assertEqual(response.status_code, 200, response.text)
        return policy_id, datasheet_id, response.json()

    def assertRawDatasheetLists(self, body, policy_id, datasheet_id):
        self.assertEqual(body["kb_ids"], ["hw_datasheets"])
        self.assertEqual(body["top_k"], 20)
        self.assertEqual(list(body["results"]), ["hw_datasheets"])
        lists = body["results"]["hw_datasheets"]
        self.assertEqual(set(lists), {"vector", "keyword"})
        for source in ("vector", "keyword"):
            hits = lists[source]
            self.assertTrue(hits, source)
            top = hits[0]
            self.assertEqual(top["rank"], 1)
            self.assertEqual(top["source"], source)
            self.assertEqual(top["document_id"], datasheet_id)
            self.assertEqual(top["original_filename"], "gpio.md")
            self.assertEqual(top["kb_id"], "hw_datasheets")
            self.assertIn("GPIO17", top["text"])
            self.assertIsNone(top["page_start"])
        self.assertNotIn(policy_id, str(body["results"]))

    def test_returns_raw_lists_per_kb_and_merged_list(self):
        policy_id, datasheet_id, body = self.search_datasheets()
        self.assertRawDatasheetLists(body, policy_id, datasheet_id)
        self.assertIsNone(body["merge_error"])
        merged = body["merged"]
        self.assertIsInstance(merged, list)
        self.assertTrue(merged)
        self.assertLessEqual(len(merged), 10)  # default top_n
        lists = body["results"]["hw_datasheets"]
        raw_ids = {hit["chunk_id"] for source in ("vector", "keyword") for hit in lists[source]}
        for item in merged:
            self.assertIn(item["chunk_id"], raw_ids)
            self.assertIsInstance(item["fused_score"], float)
            self.assertGreater(item["fused_score"], 0.0)
            self.assertTrue(item["sources"])
            for source in item["sources"]:
                self.assertIn(source["source"], ("vector", "keyword"))
                self.assertEqual(source["kb_id"], "hw_datasheets")
            self.assertEqual(item["document_id"], datasheet_id)
        scores = [item["fused_score"] for item in merged]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_merge_not_implemented_returns_raw_lists_and_merge_error(self):
        with patch("retrieval.retrieval_merge.merge_ranked_lists",
                   side_effect=NotImplementedError("merge_ranked_lists is not implemented yet")):
            policy_id, datasheet_id, body = self.search_datasheets()
        self.assertRawDatasheetLists(body, policy_id, datasheet_id)
        self.assertIsNone(body["merged"])
        self.assertEqual(body["merge_error"]["code"], "not_implemented")
        self.assertIn("not implemented", body["merge_error"]["message"].lower())
        self.assertIn("details", body["merge_error"])

    def test_merge_gets_both_lists_of_every_kb_and_its_output_is_returned(self):
        calls = []

        def fake_merge(ranked_lists, k=60, top_n=10):
            calls.append((ranked_lists, top_n))
            return [{"chunk_id": "fused", "fused_score": 1.0, "sources": []}]

        with TestClient(self.app) as client:
            self.ingest_both(client)
            with patch("retrieval.retrieval_merge.merge_ranked_lists", side_effect=fake_merge):
                response = client.post("/search", json={"query": "gpio17 password", "top_n": 3})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["merged"], [{"chunk_id": "fused", "fused_score": 1.0, "sources": []}])
        self.assertIsNone(body["merge_error"])
        self.assertEqual(len(calls), 1)
        ranked_lists, top_n = calls[0]
        self.assertEqual(top_n, 3)
        # Request KB order (all configured KBs by default), vector then keyword for each.
        self.assertEqual(body["kb_ids"], list(KB_IDS))
        self.assertEqual(len(ranked_lists), 4)
        expected = [(kb_id, source) for kb_id in KB_IDS for source in ("vector", "keyword")]
        for hits, (kb_id, source) in zip(ranked_lists, expected):
            self.assertEqual(hits, body["results"][kb_id][source])
            self.assertTrue(all(hit["kb_id"] == kb_id and hit["source"] == source for hit in hits))

    def test_query_is_embedded_once_with_embed_query(self):
        with TestClient(self.app) as client:
            self.ingest_both(client)
            document_calls = len(self.embedder.document_calls)
            client.post("/search", json={"query": "gpio17"})
        self.assertEqual(self.embedder.query_calls, ["gpio17"])
        self.assertEqual(len(self.embedder.document_calls), document_calls)

    def test_top_k_from_request_and_from_config(self):
        with TestClient(self.app) as client:
            self.ingest(client, "hw_datasheets", "pins.txt",
                        b" ".join(b"pin%d is a gpio pin." % i for i in range(400)))
            limited = client.post("/search", json={"query": "gpio pin", "kb_ids": ["hw_datasheets"], "top_k": 2})
            default = client.post("/search", json={"query": "gpio pin", "kb_ids": ["hw_datasheets"]})
        self.assertEqual(limited.json()["top_k"], 2)
        for source in ("vector", "keyword"):
            self.assertEqual(len(limited.json()["results"]["hw_datasheets"][source]), 2)
        chunks = len(default.json()["results"]["hw_datasheets"]["keyword"])
        self.assertGreater(chunks, 2)
        self.assertLessEqual(chunks, 20)

    def test_other_merge_error_still_returns_raw_lists(self):
        with TestClient(self.app) as client:
            self.ingest_both(client)
            with patch("retrieval.retrieval_merge.merge_ranked_lists", side_effect=KeyError("rank")):
                with self.assertLogs("api.api_app", level="ERROR"):
                    response = client.post("/search", json={"query": "gpio17"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["merged"])
        self.assertEqual(body["merge_error"]["code"], "internal_failure")
        self.assertTrue(body["results"]["hw_datasheets"]["keyword"])

    def test_kb_ids_are_normalized_and_deduplicated(self):
        with TestClient(self.app) as client:
            response = client.post("/search", json={"query": "x", "kb_ids": [" HW_Datasheets", "hw_datasheets"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["kb_ids"], ["hw_datasheets"])
        self.assertEqual(response.json()["results"], {"hw_datasheets": {"vector": [], "keyword": []}})


class TestSearchValidation(SearchApiTestCase):
    def post(self, body):
        with TestClient(self.app) as client:
            return client.post("/search", json=body)

    def assertError(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.text)
        self.assertEqual(response.json()["code"], code)
        self.assertIn("details", response.json())

    def test_blank_or_missing_query(self):
        self.assertError(self.post({"query": "   "}), 400, "validation_failed")
        self.assertEqual(self.post({"query": "  "}).json()["field"], "query")
        self.assertError(self.post({}), 400, "validation_failed")

    def test_unknown_kb(self):
        response = self.post({"query": "gpio", "kb_ids": ["hw_datasheets", "hr_files"]})
        self.assertError(response, 400, "unknown_kb")
        self.assertEqual(response.json()["field"], "kb_ids")
        self.assertIn("hr_files", response.json()["details"])

    def test_empty_kb_list(self):
        self.assertError(self.post({"query": "gpio", "kb_ids": []}), 400, "validation_failed")

    def test_top_k_and_top_n_out_of_range(self):
        for body in ({"query": "gpio", "top_k": 0}, {"query": "gpio", "top_k": 101},
                     {"query": "gpio", "top_n": 0}, {"query": "gpio", "top_k": "many"}):
            with self.subTest(body=body):
                self.assertError(self.post(body), 400, "validation_failed")
        self.assertEqual(self.post({"query": "gpio", "top_k": 100}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
