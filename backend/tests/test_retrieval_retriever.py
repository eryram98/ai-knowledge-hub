"""Retriever (F3): two separate ranked lists per KB, success documents only, text and metadata from SQLite."""

import os
import sys
import tempfile
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from indexing_fakes import FakeEmbedder, ephemeral_vector_index

from indexing.indexing_keyword_index import BM25KeywordIndex
from ingestion.ingestion_artifact_repository import SQLiteArtifactRepository
from ingestion.ingestion_chunking import make_chunk_id
from ingestion.ingestion_error_model import ERROR_INDEXING_FAILURE
from ingestion.ingestion_metadata_contract import create_metadata_record
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from retrieval.retrieval_retriever import BASELINE_CHUNKER, SOURCE_KEYWORD, SOURCE_VECTOR, Retriever

KB_A = "hw_datasheets"
KB_B = "it_policies"
HIT_FIELDS = {"chunk_id", "rank", "score", "source", "text", "document_id", "original_filename",
              "page_start", "page_end", "kb_id"}


class RetrievalTestCase(unittest.TestCase):
    """Temp SQLite, in-memory Chroma and a fake embedder; documents are added directly, not through the worker."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_path = os.path.join(directory.name, "retrieval.sqlite3")
        self.status_repository = SQLiteIngestionStatusRepository(db_path)
        self.artifact_repository = SQLiteArtifactRepository(db_path)
        self.embedder = FakeEmbedder()
        self.embedder.fail_with = AssertionError("retrieval must never call embed_documents")
        self.vector_index = ephemeral_vector_index(self)
        self.keyword_index = BM25KeywordIndex(self.artifact_repository)
        self.retriever = Retriever(self.embedder, self.vector_index, self.keyword_index, self.artifact_repository,
                                   top_k=20)
        self.counter = 0

    def add_document(self, kb_id, texts, status="success", file_name="datasheet.pdf", pages=True,
                     chunker=BASELINE_CHUNKER):
        """Store chunks in SQLite and vectors in Chroma, then move the document to status. Returns its ID."""
        self.counter += 1
        document_id = "doc-{0:03d}".format(self.counter)
        file_type = file_name.rsplit(".", 1)[-1]
        self.status_repository.create_queued(create_metadata_record(
            file_name, file_type, 10, "2026-10-20T12:00:00Z", kb_id=kb_id, document_id=document_id))
        chunks = [
            {"chunk_id": make_chunk_id(document_id, chunker, i), "chunk_index": i, "text": text,
             "start": 0, "end": len(text), "page_start": i + 1 if pages else None,
             "page_end": i + 2 if pages else None}
            for i, text in enumerate(texts)
        ]
        self.artifact_repository.save_document_artifacts(document_id, kb_id, " ".join(texts), {}, chunker, chunks)
        self.vector_index.replace_document(kb_id, document_id, chunker, chunks,
                                           [FakeEmbedder.vector(text) for text in texts],
                                           original_filename=file_name)
        if status != "queued":
            self.status_repository.mark_processing(document_id)
        if status == "success":
            self.status_repository.mark_success(document_id)
        elif status == "failed":
            self.status_repository.mark_failed(document_id, "indexing broke", ERROR_INDEXING_FAILURE)
        self.keyword_index.invalidate(kb_id)
        return document_id


class TestRetriever(RetrievalTestCase):
    def test_returns_two_separate_ranked_lists_with_text_and_metadata(self):
        document_id = self.add_document(KB_A, ["gpio17 is a uart pin", "power supply input voltage",
                                               "board dimensions in mm"])
        result = self.retriever.retrieve(KB_A, "gpio17 uart")
        self.assertEqual(set(result), {SOURCE_VECTOR, SOURCE_KEYWORD})
        vector, keyword = result[SOURCE_VECTOR], result[SOURCE_KEYWORD]
        self.assertEqual(len(vector), 3)  # vector search returns the nearest chunks, matching or not
        self.assertEqual([hit["chunk_id"] for hit in keyword], [make_chunk_id(document_id, BASELINE_CHUNKER, 0)])
        for hits, source in ((vector, SOURCE_VECTOR), (keyword, SOURCE_KEYWORD)):
            self.assertEqual([hit["rank"] for hit in hits], list(range(1, len(hits) + 1)))
            scores = [hit["score"] for hit in hits]
            self.assertEqual(scores, sorted(scores, reverse=True))
            for hit in hits:
                self.assertEqual(set(hit), HIT_FIELDS)
                self.assertEqual(hit["source"], source)
                self.assertEqual(hit["kb_id"], KB_A)
                self.assertEqual(hit["document_id"], document_id)
                self.assertEqual(hit["original_filename"], "datasheet.pdf")
                self.assertIsInstance(hit["score"], float)
        top = vector[0]
        self.assertEqual(top["chunk_id"], make_chunk_id(document_id, BASELINE_CHUNKER, 0))
        self.assertEqual(top["text"], "gpio17 is a uart pin")
        self.assertEqual((top["page_start"], top["page_end"]), (1, 2))
        self.assertEqual(keyword[0]["text"], "gpio17 is a uart pin")

    def test_query_is_embedded_once_with_embed_query(self):
        self.add_document(KB_A, ["gpio17 pin"])
        self.add_document(KB_B, ["password policy"])
        self.retriever.retrieve_many([KB_A, KB_B], "gpio17 password")
        self.assertEqual(self.embedder.query_calls, ["gpio17 password"])
        self.assertEqual(self.embedder.document_calls, [])

    def test_failed_document_vectors_are_excluded_and_top_k_still_filled(self):
        # The failed document matches the query best; its vectors were never removed.
        self.add_document(KB_A, ["gpio17 uart pin", "gpio17 uart pin header"], status="failed")
        good = self.add_document(KB_A, ["gpio17 header", "uart pin", "power supply"])
        result = self.retriever.retrieve(KB_A, "gpio17 uart pin", top_k=2)
        self.assertEqual(len(result[SOURCE_VECTOR]), 2)
        self.assertEqual({hit["document_id"] for hit in result[SOURCE_VECTOR]}, {good})
        self.assertEqual({hit["document_id"] for hit in result[SOURCE_KEYWORD]}, {good})

    def test_processing_and_queued_documents_are_excluded(self):
        self.add_document(KB_A, ["gpio17 uart pin"], status="processing")
        self.add_document(KB_A, ["gpio17 uart pin"], status="queued")
        result = self.retriever.retrieve(KB_A, "gpio17 uart pin")
        self.assertEqual(result, {SOURCE_VECTOR: [], SOURCE_KEYWORD: []})

    def test_vector_hit_without_a_sqlite_chunk_is_dropped_and_ranks_stay_contiguous(self):
        document_id = self.add_document(KB_A, ["gpio17 uart pin", "power supply"])
        # A stale vector whose chunk row no longer exists (for example after re-chunking).
        stale = {"chunk_id": make_chunk_id(document_id, BASELINE_CHUNKER, 99), "chunk_index": 99,
                 "text": "gpio17 uart pin"}
        collection = self.vector_index._collection(KB_A)
        collection.add(ids=[stale["chunk_id"]], embeddings=[FakeEmbedder.vector(stale["text"])],
                       metadatas=[{"document_id": document_id, "kb_id": KB_A, "chunker": BASELINE_CHUNKER,
                                   "chunk_index": 99}])
        vector = self.retriever.retrieve(KB_A, "gpio17 uart pin")[SOURCE_VECTOR]
        self.assertNotIn(stale["chunk_id"], [hit["chunk_id"] for hit in vector])
        self.assertEqual([hit["rank"] for hit in vector], [1, 2])

    def test_top_k_per_list(self):
        self.add_document(KB_A, ["gpio{0} pin".format(i) for i in range(6)])
        result = self.retriever.retrieve(KB_A, "pin", top_k=4)
        self.assertEqual(len(result[SOURCE_VECTOR]), 4)
        self.assertEqual(len(result[SOURCE_KEYWORD]), 4)
        default = self.retriever.retrieve(KB_A, "pin")
        self.assertEqual(len(default[SOURCE_KEYWORD]), 6)
        small = Retriever(self.embedder, self.vector_index, self.keyword_index, self.artifact_repository, top_k=2)
        self.assertEqual(len(small.retrieve(KB_A, "pin")[SOURCE_VECTOR]), 2)

    def test_kbs_are_isolated(self):
        doc_a = self.add_document(KB_A, ["gpio17 pin"])
        doc_b = self.add_document(KB_B, ["gpio17 policy"], file_name="policy.md", pages=False)
        results = self.retriever.retrieve_many([KB_A, KB_B], "gpio17")
        self.assertEqual(set(results), {KB_A, KB_B})
        for kb_id, document_id in ((KB_A, doc_a), (KB_B, doc_b)):
            for source in (SOURCE_VECTOR, SOURCE_KEYWORD):
                hits = results[kb_id][source]
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["document_id"], document_id)
                self.assertEqual(hits[0]["kb_id"], kb_id)

    def test_empty_kb_returns_empty_lists(self):
        self.add_document(KB_A, ["gpio17 pin"])
        self.assertEqual(self.retriever.retrieve(KB_B, "gpio17"), {SOURCE_VECTOR: [], SOURCE_KEYWORD: []})

    def test_txt_chunks_have_no_pages(self):
        self.add_document(KB_B, ["acceptable use policy"], file_name="policy.txt", pages=False)
        result = self.retriever.retrieve(KB_B, "acceptable use")
        for source in (SOURCE_VECTOR, SOURCE_KEYWORD):
            hit = result[source][0]
            self.assertIsNone(hit["page_start"])
            self.assertIsNone(hit["page_end"])
            self.assertEqual(hit["original_filename"], "policy.txt")

    def test_other_chunker_is_searched_separately(self):
        self.add_document(KB_A, ["gpio17 pin"])
        other = self.add_document(KB_A, ["gpio17 table row"], chunker="table-safe")
        result = self.retriever.retrieve(KB_A, "gpio17", chunker="table-safe")
        self.assertEqual([hit["document_id"] for hit in result[SOURCE_VECTOR]], [other])
        self.assertEqual([hit["document_id"] for hit in result[SOURCE_KEYWORD]], [other])


class TestArtifactRepositoryRetrievalLookups(RetrievalTestCase):
    def test_list_success_document_ids(self):
        first = self.add_document(KB_A, ["a"])
        self.add_document(KB_A, ["b"], status="failed")
        self.add_document(KB_A, ["c"], status="processing")
        third = self.add_document(KB_A, ["d"])
        self.add_document(KB_B, ["e"])
        self.assertEqual(self.artifact_repository.list_success_document_ids(KB_A), [first, third])
        self.assertEqual(self.artifact_repository.list_success_document_ids("unknown_kb"), [])

    def test_get_chunk_hits_returns_success_chunks_with_source_metadata(self):
        good = self.add_document(KB_A, ["gpio17 pin", "power"])
        failed = self.add_document(KB_A, ["gpio17 pin"], status="failed")
        good_id = make_chunk_id(good, BASELINE_CHUNKER, 1)
        failed_id = make_chunk_id(failed, BASELINE_CHUNKER, 0)
        hits = self.artifact_repository.get_chunk_hits([good_id, failed_id, "missing", good_id])
        self.assertEqual(hits, {good_id: {
            "chunk_id": good_id, "text": "power", "document_id": good, "kb_id": KB_A,
            "page_start": 2, "page_end": 3, "original_filename": "datasheet.pdf",
        }})
        self.assertEqual(self.artifact_repository.get_chunk_hits([]), {})


if __name__ == "__main__":
    unittest.main()
