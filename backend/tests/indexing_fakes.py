"""Test doubles for F2 indexing: a deterministic embedder and an in-memory Chroma client.

No model download and no network: FakeEmbedder hashes tokens into a small
normalized vector, so texts sharing words get similar vectors.
"""

import hashlib
import math
import os
import sys
import threading

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from indexing.indexing_embedder import Embedder
from indexing.indexing_keyword_index import tokenize

FAKE_DIMENSION = 16


class FakeEmbedder(Embedder):
    """Hashed bag of tokens -> normalized 16-dim vector. Records calls; can be told to fail."""

    model_name = "fake-hashed-bag-16"
    dimension = FAKE_DIMENSION

    def __init__(self):
        self.document_calls = []
        self.query_calls = []
        self.fail_with = None  # an exception instance to raise from embed_documents
        self._lock = threading.Lock()

    @staticmethod
    def vector(text):
        values = [0.0] * FAKE_DIMENSION
        for token in tokenize(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            values[digest[0] % FAKE_DIMENSION] += 1.0
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0:
            values[0], norm = 1.0, 1.0
        return [value / norm for value in values]

    def embed_documents(self, texts):
        texts = list(texts)
        with self._lock:
            self.document_calls.append(texts)
        if self.fail_with is not None:
            raise self.fail_with
        return [self.vector(text) for text in texts]

    def embed_query(self, text):
        with self._lock:
            self.query_calls.append(text)
        return self.vector(text)


def ephemeral_vector_index(test_case, embedding_model=FakeEmbedder.model_name):
    """A ChromaVectorIndex on Chroma's in-memory store, emptied before and after the test.

    Every in-memory Chroma client in a process shares one store, and creating
    one with different settings raises, so all tests go through this helper.
    """
    import chromadb

    from indexing.indexing_vector_index import ChromaVectorIndex, chroma_settings

    client = chromadb.EphemeralClient(settings=chroma_settings(allow_reset=True))
    client.reset()
    test_case.addCleanup(client.reset)
    return ChromaVectorIndex(client, embedding_model=embedding_model)


def make_indexer(test_case, artifact_repository, embedder=None):
    """DocumentIndexer with a FakeEmbedder, in-memory Chroma and a BM25 index over artifact_repository."""
    from indexing.indexing_keyword_index import BM25KeywordIndex
    from indexing.indexing_service import DocumentIndexer

    embedder = embedder if embedder is not None else FakeEmbedder()
    vector_index = ephemeral_vector_index(test_case, embedder.model_name)
    return DocumentIndexer(embedder, vector_index, BM25KeywordIndex(artifact_repository))
