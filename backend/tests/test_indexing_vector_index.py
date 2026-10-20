"""ChromaVectorIndex on in-memory Chroma (F2): metadata, replace, filters, KB isolation, model guard."""

import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from indexing_fakes import FakeEmbedder, ephemeral_vector_index

from indexing.indexing_vector_index import ChromaVectorIndex, EmbeddingModelMismatchError, collection_name

KB_A = "hw_datasheets"
KB_B = "it_policies"
BASE = "fixed-size-char-baseline"
OTHER = "table-safe"


def chunks_for(document_id, chunker, texts, pages=True):
    return [
        {"chunk_id": "{0}:{1}:{2:05d}".format(document_id, chunker, i), "chunk_index": i, "text": text,
         "page_start": i + 1 if pages else None, "page_end": i + 1 if pages else None}
        for i, text in enumerate(texts)
    ]


class TestChromaVectorIndex(unittest.TestCase):
    def setUp(self):
        self.index = ephemeral_vector_index(self)

    def add(self, kb_id, document_id, chunker, texts, pages=True, original_filename="doc.pdf"):
        chunks = chunks_for(document_id, chunker, texts, pages)
        vectors = [FakeEmbedder.vector(text) for text in texts]
        self.index.replace_document(kb_id, document_id, chunker, chunks, vectors, original_filename=original_filename)
        return chunks

    def stored(self, kb_id, ids):
        return self.index.client.get_collection(collection_name(kb_id)).get(ids=ids, include=["metadatas", "documents"])

    def test_metadata_fields_and_no_text(self):
        chunks = self.add(KB_A, "doc-1", BASE, ["gpio17 pin", "power supply"])
        self.add(KB_A, "doc-2", BASE, ["plain text"], pages=False, original_filename="notes.txt")
        result = self.stored(KB_A, [chunks[1]["chunk_id"]])
        self.assertEqual(result["metadatas"][0], {
            "document_id": "doc-1", "kb_id": KB_A, "chunker": BASE, "chunk_index": 1,
            "page_start": 2, "page_end": 2, "original_filename": "doc.pdf",
        })
        self.assertEqual(result["documents"], [None])
        no_pages = self.stored(KB_A, ["doc-2:{0}:00000".format(BASE)])["metadatas"][0]
        self.assertNotIn("page_start", no_pages)
        self.assertEqual(no_pages["original_filename"], "notes.txt")

    def test_collection_is_cosine_named_per_kb_and_records_the_model(self):
        self.add(KB_A, "doc-1", BASE, ["a"])
        collection = self.index.client.get_collection(collection_name(KB_A))
        self.assertEqual(collection.name, "kb_hw_datasheets")
        self.assertEqual(collection.metadata["embedding_model"], FakeEmbedder.model_name)
        self.assertEqual(collection.configuration_json["hnsw"]["space"], "cosine")

    def test_reindex_replaces_only_that_chunker(self):
        self.add(KB_A, "doc-1", BASE, ["a", "b", "c"])
        self.add(KB_A, "doc-1", OTHER, ["t1", "t2"])
        self.add(KB_A, "doc-2", BASE, ["x"])
        self.add(KB_A, "doc-1", BASE, ["a2", "b2"])
        self.assertEqual(self.index.count(KB_A, document_id="doc-1", chunker=BASE), 2)
        self.assertEqual(self.index.count(KB_A, document_id="doc-1", chunker=OTHER), 2)
        self.assertEqual(self.index.count(KB_A, document_id="doc-2"), 1)
        self.assertEqual(self.index.count(KB_A), 5)

    def test_query_ranks_by_similarity_and_filters_chunker(self):
        self.add(KB_A, "doc-1", BASE, ["gpio17 uart pin", "board dimensions mm", "flash memory size"])
        self.add(KB_A, "doc-1", OTHER, ["gpio17 uart pin"])
        hits = self.index.query(KB_A, FakeEmbedder.vector("gpio17 uart pin"), BASE, top_k=2)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0][0], "doc-1:{0}:00000".format(BASE))
        self.assertAlmostEqual(hits[0][1], 1.0, places=5)
        self.assertGreaterEqual(hits[0][1], hits[1][1])
        other = self.index.query(KB_A, FakeEmbedder.vector("gpio17 uart pin"), OTHER, top_k=5)
        self.assertEqual([h[0] for h in other], ["doc-1:{0}:00000".format(OTHER)])
        self.assertEqual(self.index.query(KB_A, FakeEmbedder.vector("x"), "unknown-chunker", 5), [])
        self.assertEqual(self.index.query(KB_A, FakeEmbedder.vector("x"), BASE, 0), [])

    def test_kbs_are_isolated(self):
        self.add(KB_A, "doc-1", BASE, ["gpio17"])
        self.assertEqual(self.index.query(KB_B, FakeEmbedder.vector("gpio17"), BASE, 5), [])
        self.assertEqual(self.index.count(KB_B), 0)
        self.assertEqual(self.index.count(KB_A), 1)

    def test_delete_document(self):
        self.add(KB_A, "doc-1", BASE, ["a", "b"])
        self.add(KB_A, "doc-1", OTHER, ["t"])
        self.add(KB_A, "doc-2", BASE, ["c"])
        self.index.delete_document(KB_A, "doc-1", chunker=OTHER)
        self.assertEqual(self.index.count(KB_A, document_id="doc-1"), 2)
        self.index.delete_document(KB_A, "doc-1")
        self.assertEqual(self.index.count(KB_A, document_id="doc-1"), 0)
        self.assertEqual(self.index.count(KB_A), 1)
        self.index.delete_document(KB_A, "doc-missing")

    def test_model_mismatch_is_refused(self):
        self.add(KB_A, "doc-1", BASE, ["a"])
        other_model = ChromaVectorIndex(self.index.client, embedding_model="another-model")
        with self.assertRaises(EmbeddingModelMismatchError) as caught:
            other_model.count(KB_A)
        self.assertIn(FakeEmbedder.model_name, str(caught.exception))
        self.assertEqual(self.index.count(KB_A), 1)

    def test_mismatched_lengths_are_refused(self):
        with self.assertRaises(ValueError):
            self.index.replace_document(KB_A, "doc-1", BASE, chunks_for("doc-1", BASE, ["a", "b"]),
                                        [FakeEmbedder.vector("a")])


if __name__ == "__main__":
    unittest.main()
