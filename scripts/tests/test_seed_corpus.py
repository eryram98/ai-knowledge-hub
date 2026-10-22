"""seed_corpus: corpus discovery, the wipe, upload results, polling and the refusal paths. No network, no API."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import demo_common
import seed_corpus
from demo_common import ApiClientError


def touch(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(content)


class FakeClient:
    def __init__(self, batches=None, reject=()):
        self.uploads = []
        self.batches = list(batches or [])
        self.reject = set(reject)
        self.polls = 0

    def upload(self, kb_id, files):
        self.uploads.append((kb_id, [name for name, _c, _m in files]))
        entries = []
        for name, _content, _mime in files:
            if name in self.reject:
                entries.append({"status": "rejected", "document_id": None,
                                "error": {"code": "file_too_large", "message": "too big"}})
            else:
                entries.append({"status": "accepted", "document_id": "doc-" + name})
        return {"files": entries}

    def document_statuses(self, ids):
        self.polls += 1
        pick = self.batches.pop(0) if len(self.batches) > 1 else self.batches[0]
        return pick(ids)


def batch(ids, status="success", complete=True):
    failed = status == "failed"
    documents = [{"document_id": i, "ingestion_status": status,
                  "failure_code": "indexing_failure" if failed else None,
                  "failure_reason": "boom" if failed else None} for i in ids]
    return {"documents": documents, "total": len(ids), "completed": len(ids) if complete else 0,
            "is_complete": complete}


class DiscoverCorpusTest(unittest.TestCase):
    def test_groups_by_kb_and_skips_other_files(self):
        with tempfile.TemporaryDirectory() as root:
            touch(os.path.join(root, "hw", "b.pdf"))
            touch(os.path.join(root, "hw", "a.pdf"))
            touch(os.path.join(root, "hw", "notes.docx"))
            touch(os.path.join(root, "it", "p.md"))
            touch(os.path.join(root, "MANIFEST.md"))
            corpus = seed_corpus.discover_corpus(root)
        self.assertEqual(["hw", "it"], list(corpus))
        self.assertEqual(["a.pdf", "b.pdf"], [os.path.basename(p) for p in corpus["hw"]])
        self.assertEqual(["p.md"], [os.path.basename(p) for p in corpus["it"]])


class WipeInstanceTest(unittest.TestCase):
    def test_removes_db_chroma_and_uploads_only(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("ingestion.sqlite3", "ingestion.sqlite3-wal", "keep.txt"):
                touch(os.path.join(root, name))
            touch(os.path.join(root, "chroma", "a.bin"))
            touch(os.path.join(root, "uploads", "doc", "f.pdf"))
            removed = seed_corpus.wipe_instance(root)
            left = sorted(os.listdir(root))
        self.assertEqual(["keep.txt"], left)
        self.assertEqual({"ingestion.sqlite3", "ingestion.sqlite3-wal", "chroma/", "uploads/"}, set(removed))

    def test_nothing_to_remove_is_fine(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual([], seed_corpus.wipe_instance(root))


class UploadAndWaitTest(unittest.TestCase):
    def test_upload_kb_maps_accepted_and_rejected_in_order(self):
        with tempfile.TemporaryDirectory() as root:
            ok, big = os.path.join(root, "ok.pdf"), os.path.join(root, "big.pdf")
            touch(ok)
            touch(big)
            results = seed_corpus.upload_kb(FakeClient(reject=["big.pdf"]), "kb", [ok, big])
        self.assertEqual(("ok.pdf", "doc-ok.pdf", None), results[0])
        self.assertEqual("big.pdf", results[1][0])
        self.assertIsNone(results[1][1])
        self.assertIn("file_too_large", results[1][2])

    def test_wait_polls_until_complete(self):
        client = FakeClient(batches=[lambda ids: batch(ids, "processing", False), lambda ids: batch(ids)])
        ticks = []
        done = seed_corpus.wait_for_documents(client, ["a"], 100, 1, sleep=ticks.append)
        self.assertEqual(2, client.polls)
        self.assertEqual([1], ticks)
        self.assertEqual("success", done["a"]["ingestion_status"])

    def test_wait_times_out(self):
        client = FakeClient(batches=[lambda ids: batch(ids, "processing", False)])
        now = iter([0, 5, 11, 20])
        with self.assertRaises(TimeoutError):
            seed_corpus.wait_for_documents(client, ["a"], 10, 1, sleep=lambda _s: None, clock=lambda: next(now))

    def test_nothing_to_wait_for_makes_no_call(self):
        client = FakeClient(batches=[lambda ids: batch(ids)])
        self.assertEqual({}, seed_corpus.wait_for_documents(client, []))
        self.assertEqual(0, client.polls)


class SeedTest(unittest.TestCase):
    def run_seed(self, client, names_by_kb):
        lines = []
        with tempfile.TemporaryDirectory() as root:
            corpus = {}
            for kb_id, names in names_by_kb.items():
                corpus[kb_id] = []
                for name in names:
                    path = os.path.join(root, kb_id, name)
                    touch(path)
                    corpus[kb_id].append(path)
            rows = seed_corpus.seed(client, corpus, 10, 0, out=lines.append)
        return rows, lines

    def test_summary_lists_each_file_and_kb_counts(self):
        client = FakeClient(batches=[lambda ids: batch(ids)], reject=["big.pdf"])
        rows, lines = self.run_seed(client, {"hw": ["a.pdf", "big.pdf"], "it": ["p.pdf"]})
        self.assertEqual(["success", "rejected", "success"], [r["status"] for r in rows])
        text = "\n".join(lines)
        self.assertIn("hw: 1 of 2 indexed", text)
        self.assertIn("it: 1 of 1 indexed", text)
        self.assertIn("file_too_large", text)
        self.assertEqual(0, seed_corpus.exit_code(rows))

    def test_a_failed_document_is_reported_and_fails_the_run(self):
        client = FakeClient(batches=[lambda ids: batch(ids, "failed")])
        rows, lines = self.run_seed(client, {"hw": ["a.pdf"]})
        self.assertEqual("failed", rows[0]["status"])
        self.assertIn("indexing_failure: boom", "\n".join(lines))
        self.assertEqual(1, seed_corpus.exit_code(rows))


class MainRefusalTest(unittest.TestCase):
    def test_refuses_to_wipe_while_the_api_is_up(self):
        with tempfile.TemporaryDirectory() as root:
            touch(os.path.join(root, "kb", "a.pdf"))
            with mock.patch.object(demo_common, "CORPUS_DIR", root), \
                    mock.patch.object(seed_corpus, "api_is_up", return_value=True), \
                    mock.patch.object(seed_corpus, "wipe_instance") as wipe:
                self.assertEqual(1, seed_corpus.main(["--yes"]))
        wipe.assert_not_called()

    def test_declining_the_prompt_wipes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            touch(os.path.join(root, "kb", "a.pdf"))
            with mock.patch.object(demo_common, "CORPUS_DIR", root), \
                    mock.patch.object(seed_corpus, "api_is_up", return_value=False), \
                    mock.patch.object(seed_corpus, "wipe_instance") as wipe, \
                    mock.patch("builtins.input", return_value="n"):
                self.assertEqual(1, seed_corpus.main([]))
        wipe.assert_not_called()

    def test_empty_corpus_stops_before_anything_else(self):
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(demo_common, "CORPUS_DIR", root), \
                mock.patch.object(seed_corpus, "wipe_instance") as wipe:
            self.assertEqual(1, seed_corpus.main(["--yes"]))
        wipe.assert_not_called()

    def test_api_is_up_treats_an_error_response_as_up_and_a_refused_connection_as_down(self):
        class Client:
            def __init__(self, error):
                self.error = error

            def list_kbs(self):
                if self.error:
                    raise self.error
                return []
        self.assertTrue(seed_corpus.api_is_up(Client(None)))
        self.assertTrue(seed_corpus.api_is_up(Client(ApiClientError("api", "x", status_code=500))))
        self.assertFalse(seed_corpus.api_is_up(Client(ApiClientError("connection", "x"))))


if __name__ == "__main__":
    unittest.main()
