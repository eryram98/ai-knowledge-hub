import os
import sys
import unittest

# Make backend/app importable when running from project root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
APP_DIR = os.path.join(BACKEND_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_stage_contracts import (
    ChunkingStage,
    EmbeddingStage,
    ExtractionStage,
    IndexingStage,
    ensure_contract_implemented,
    EXTRACTION_REQUIRED_METHODS,
    CHUNKING_REQUIRED_METHODS,
    EMBEDDING_REQUIRED_METHODS,
    INDEXING_REQUIRED_METHODS,
)


class GoodExtractionStage(object):
    def extract_text(self, file_path, file_type):
        return {"full_text": "hello", "metadata": {"file_type": file_type}}


class BadExtractionStage(object):
    pass


class GoodChunkingStage(object):
    def chunk_text(self, full_text, metadata=None):
        return [{"chunk_id": "1", "text": full_text, "start": 0, "end": len(full_text)}]


class GoodEmbeddingStage(object):
    def generate_embeddings(self, chunks):
        return [{"chunk_id": c["chunk_id"], "vector": [0.1, 0.2]} for c in chunks]


class GoodIndexingStage(object):
    def index_document(self, document_id, full_text, chunks, metadata=None):
        return {"index_id": "idx-1", "indexed_chunks": len(chunks)}


class TestIngestionStageContracts(unittest.TestCase):
    def test_extraction_contract_passes(self):
        ok, errors = ensure_contract_implemented(GoodExtractionStage(), EXTRACTION_REQUIRED_METHODS)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_extraction_contract_fails(self):
        ok, errors = ensure_contract_implemented(BadExtractionStage(), EXTRACTION_REQUIRED_METHODS)
        self.assertFalse(ok)
        self.assertTrue(len(errors) > 0)

    def test_chunking_contract_passes(self):
        ok, errors = ensure_contract_implemented(GoodChunkingStage(), CHUNKING_REQUIRED_METHODS)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_embedding_contract_passes(self):
        ok, errors = ensure_contract_implemented(GoodEmbeddingStage(), EMBEDDING_REQUIRED_METHODS)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_indexing_contract_passes(self):
        ok, errors = ensure_contract_implemented(GoodIndexingStage(), INDEXING_REQUIRED_METHODS)
        self.assertTrue(ok)
        self.assertEqual(errors, [])


class TestStageAbstractEnforcement(unittest.TestCase):
    """Stage base classes use metaclass=ABCMeta, so abstract methods are enforced."""

    def test_bare_stages_cannot_be_instantiated(self):
        for stage_class in (ExtractionStage, ChunkingStage, EmbeddingStage, IndexingStage):
            with self.assertRaises(TypeError, msg=stage_class.__name__):
                stage_class()

    def test_subclass_missing_abstract_method_cannot_be_instantiated(self):
        class IncompleteExtractor(ExtractionStage):
            pass

        with self.assertRaises(TypeError):
            IncompleteExtractor()

    def test_subclass_implementing_abstract_method_can_be_instantiated(self):
        class CompleteExtractor(ExtractionStage):
            def extract_text(self, file_path, file_type):
                return {"full_text": "", "metadata": {}}

        self.assertIsInstance(CompleteExtractor(), ExtractionStage)


if __name__ == "__main__":
    unittest.main()
