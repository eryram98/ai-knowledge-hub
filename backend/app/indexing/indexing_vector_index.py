"""Chroma vector index: one collection per KB, vectors computed by our embedder (F2).

Chunk text is not stored in Chroma; SQLite holds it (F3 reads it from there).
Each entry's ID is our chunk_id, and its metadata links it back to the
document, KB, chunker and pages.
"""

import os

import chromadb
from chromadb.config import Settings

from indexing.indexing_embedder import BGE_SMALL_MODEL_NAME
from ingestion.ingestion_status_repository import DEFAULT_DATABASE_PATH

# backend/instance/chroma/, beside the dev database (git-ignored).
DEFAULT_CHROMA_PATH = os.path.join(os.path.dirname(DEFAULT_DATABASE_PATH), "chroma")
COLLECTION_PREFIX = "kb_"
EMBEDDING_MODEL_KEY = "embedding_model"


def chroma_settings(**overrides):
    """Telemetry off for every client we create."""
    return Settings(anonymized_telemetry=False, **overrides)


def collection_name(kb_id):
    return COLLECTION_PREFIX + kb_id


class EmbeddingModelMismatchError(Exception):
    """A KB collection was built with a different embedding model."""


class ChromaVectorIndex(object):
    """Per-KB Chroma collections with cosine distance and no Chroma-side embedder.

    embedding_model is recorded on every collection; using a collection built
    with another model raises EmbeddingModelMismatchError instead of mixing
    vectors from two models.
    """

    def __init__(self, client, embedding_model=BGE_SMALL_MODEL_NAME):
        self.client = client
        self.embedding_model = embedding_model

    @classmethod
    def persistent(cls, path=DEFAULT_CHROMA_PATH, embedding_model=BGE_SMALL_MODEL_NAME):
        os.makedirs(path, exist_ok=True)
        return cls(chromadb.PersistentClient(path=path, settings=chroma_settings()), embedding_model)

    def _collection(self, kb_id):
        collection = self.client.get_or_create_collection(
            collection_name(kb_id),
            embedding_function=None,  # we pass vectors; never load Chroma's default ONNX model
            metadata={EMBEDDING_MODEL_KEY: self.embedding_model},
            configuration={"hnsw": {"space": "cosine"}},
        )
        built_with = (collection.metadata or {}).get(EMBEDDING_MODEL_KEY)
        if built_with != self.embedding_model:
            raise EmbeddingModelMismatchError(
                "Collection {0} was built with {1}, not {2}. Delete backend/instance/chroma/ "
                "and re-process the documents.".format(collection_name(kb_id), built_with, self.embedding_model))
        return collection

    @staticmethod
    def _where(document_id=None, chunker=None):
        conditions = [{key: value} for key, value in (("document_id", document_id), ("chunker", chunker))
                      if value is not None]
        if not conditions:
            return None
        return conditions[0] if len(conditions) == 1 else {"$and": conditions}

    def replace_document(self, kb_id, document_id, chunker, chunks, vectors, original_filename=None):
        """Delete this document's entries for this chunker, then add one entry per chunk."""
        if len(chunks) != len(vectors):
            raise ValueError("Got {0} vectors for {1} chunks".format(len(vectors), len(chunks)))
        collection = self._collection(kb_id)
        collection.delete(where=self._where(document_id, chunker))
        if not chunks:
            return
        metadatas = []
        for chunk in chunks:
            metadata = {"document_id": document_id, "kb_id": kb_id, "chunker": chunker,
                        "chunk_index": chunk["chunk_index"]}
            # Chroma metadata can't hold None: TXT and MD chunks have no pages.
            for key in ("page_start", "page_end"):
                if chunk.get(key) is not None:
                    metadata[key] = chunk[key]
            if original_filename:
                metadata["original_filename"] = original_filename
            metadatas.append(metadata)
        max_batch = self.client.get_max_batch_size()
        for start in range(0, len(chunks), max_batch):
            end = start + max_batch
            collection.add(
                ids=[chunk["chunk_id"] for chunk in chunks[start:end]],
                embeddings=vectors[start:end],
                metadatas=metadatas[start:end],
            )

    def delete_document(self, kb_id, document_id, chunker=None):
        """Delete a document's entries (one chunker, or all when chunker is None)."""
        self._collection(kb_id).delete(where=self._where(document_id, chunker))

    def query(self, kb_id, query_vector, chunker, top_k):
        """Return up to top_k [(chunk_id, score)], best first; score is cosine similarity (1 - distance)."""
        if top_k <= 0:
            return []
        collection = self._collection(kb_id)
        if collection.count() == 0:
            return []
        result = collection.query(
            query_embeddings=[list(query_vector)], n_results=top_k,
            where=self._where(chunker=chunker), include=["distances"],
        )
        return [(chunk_id, 1.0 - float(distance))
                for chunk_id, distance in zip(result["ids"][0], result["distances"][0])]

    def count(self, kb_id, document_id=None, chunker=None):
        """Number of entries in a KB, optionally for one document and/or chunker."""
        collection = self._collection(kb_id)
        where = self._where(document_id, chunker)
        if where is None:
            return collection.count()
        return len(collection.get(where=where, include=[])["ids"])
