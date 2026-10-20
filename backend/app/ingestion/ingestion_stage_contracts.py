"""
Stage contracts/interfaces for ingestion pipeline components.
Python 3.6 compatible.
"""

from abc import ABCMeta, abstractmethod


class ExtractionStage(metaclass=ABCMeta):
    @abstractmethod
    def extract_text(self, file_path, file_type):
        # type: (str, str) -> dict
        """
        Expected return shape:
        {
            "full_text": str,
            "metadata": dict
        }
        """
        raise NotImplementedError


class ChunkingStage(metaclass=ABCMeta):
    @abstractmethod
    def chunk_text(self, full_text, metadata=None):
        # type: (str, dict) -> list
        """
        Expected return shape:
        [
            {"chunk_id": str, "text": str, "start": int, "end": int}
        ]
        Pipeline chunkers also return document_id, kb_id, chunk_index,
        page_start, page_end (None outside PDFs) and chunker (its name).
        """
        raise NotImplementedError


class EmbeddingStage(metaclass=ABCMeta):
    @abstractmethod
    def generate_embeddings(self, chunks):
        # type: (list) -> list
        """
        Expected return shape:
        [
            {"chunk_id": str, "vector": list}
        ]
        """
        raise NotImplementedError


class IndexingStage(metaclass=ABCMeta):
    @abstractmethod
    def index_document(self, document_id, full_text, chunks, metadata=None):
        # type: (str, str, list, dict) -> dict
        """
        Expected return shape:
        {
            "index_id": str,
            "indexed_chunks": int
        }
        """
        raise NotImplementedError


def ensure_contract_implemented(instance, required_methods):
    # type: (object, tuple) -> tuple
    """
    Runtime helper to validate stage implementation shape.
    Returns (is_valid, errors).
    """
    errors = []

    for method_name in required_methods:
        method_ref = getattr(instance, method_name, None)
        if method_ref is None or not callable(method_ref):
            errors.append("missing callable method: {0}".format(method_name))

    return len(errors) == 0, errors


EXTRACTION_REQUIRED_METHODS = ("extract_text",)
CHUNKING_REQUIRED_METHODS = ("chunk_text",)
EMBEDDING_REQUIRED_METHODS = ("generate_embeddings",)
INDEXING_REQUIRED_METHODS = ("index_document",)
