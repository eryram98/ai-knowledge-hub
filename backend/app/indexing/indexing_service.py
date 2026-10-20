"""Embed a document's persisted chunks and write them to the KB's vector and keyword indexes (F2)."""

import logging

from ingestion.ingestion_error_model import ERROR_INDEXING_FAILURE, IngestionStageError
from ingestion.ingestion_metadata_contract import META_ORIGINAL_FILENAME

LOGGER = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


class IndexingError(IngestionStageError):
    """Raised when embedding or indexing fails; the worker stores indexing_failure."""


class DocumentIndexer(object):
    """Called by DocumentProcessor after the chunks are persisted in SQLite.

    A failure leaves no vectors for that document and chunker: the indexer
    deletes them (best effort) before raising IndexingError.
    """

    def __init__(self, embedder, vector_index, keyword_index, batch_size=EMBED_BATCH_SIZE):
        self.embedder = embedder
        self.vector_index = vector_index
        self.keyword_index = keyword_index
        self.batch_size = batch_size

    def index_document(self, document, chunker_name, chunks):
        """Replace this document's vectors for chunker_name; return the number indexed.

        document is the status repository record (document_id, kb_id, metadata).
        chunks are the persisted chunk rows (chunk_id, chunk_index, text, page_start, page_end).
        """
        document_id = document["document_id"]
        kb_id = document["kb_id"]
        try:
            chunks = list(chunks)
            vectors = []
            for start in range(0, len(chunks), self.batch_size):
                batch = chunks[start:start + self.batch_size]
                batch_vectors = self.embedder.embed_documents([chunk["text"] for chunk in batch])
                if len(batch_vectors) != len(batch):
                    raise ValueError("Embedder returned {0} vectors for {1} chunks".format(
                        len(batch_vectors), len(batch)))
                vectors.extend(batch_vectors)
            self.vector_index.replace_document(
                kb_id, document_id, chunker_name, chunks, vectors,
                original_filename=(document.get("metadata") or {}).get(META_ORIGINAL_FILENAME),
            )
            indexed = self.vector_index.count(kb_id, document_id=document_id, chunker=chunker_name)
            if indexed != len(chunks):
                raise ValueError("Indexed {0} vectors for {1} chunks".format(indexed, len(chunks)))
        except Exception as exc:
            self._delete_quietly(kb_id, document_id, chunker_name)
            raise IndexingError(ERROR_INDEXING_FAILURE, "{0}: {1}".format(type(exc).__name__, exc)) from exc
        self.keyword_index.invalidate(kb_id)
        return indexed

    def _delete_quietly(self, kb_id, document_id, chunker_name):
        try:
            self.vector_index.delete_document(kb_id, document_id, chunker=chunker_name)
        except Exception:
            LOGGER.exception("Could not remove vectors of failed document %s", document_id)
