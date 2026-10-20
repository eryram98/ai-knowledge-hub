"""Real bge-small model (F2). Skipped unless RUN_MODEL_TESTS=1: downloads ~130 MB once.

Run once by hand (PowerShell, repo root):
    $env:RUN_MODEL_TESTS='1'
    .venv\\Scripts\\python -m unittest discover -s backend\\tests -p test_indexing_model_integration.py
"""

import math
import os
import sys
import tempfile
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from indexing_fakes import ephemeral_vector_index

from indexing.indexing_embedder import BGE_SMALL_DIMENSION, BGE_SMALL_MODEL_NAME, BgeSmallEmbedder
from indexing.indexing_keyword_index import BM25KeywordIndex
from indexing.indexing_service import DocumentIndexer
from ingestion.ingestion_artifact_repository import SQLiteArtifactRepository
from ingestion.ingestion_chunking import FixedSizeCharChunker
from ingestion.ingestion_job_queue import IngestionJob
from ingestion.ingestion_pipeline import DocumentProcessor
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput

RUN_MODEL_TESTS = os.environ.get("RUN_MODEL_TESTS") == "1"
KB_ID = "hw_datasheets"
CHUNKER = FixedSizeCharChunker.name


@unittest.skipUnless(RUN_MODEL_TESTS, "set RUN_MODEL_TESTS=1 to load the real embedding model")
class TestBgeSmallModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedder = BgeSmallEmbedder()

    def test_vectors_are_normalized_and_query_differs_from_passage(self):
        text = "The RP2040 has 30 GPIO pins."
        passage = self.embedder.embed_documents([text])[0]
        query = self.embedder.embed_query(text)
        self.assertEqual(len(passage), BGE_SMALL_DIMENSION)
        self.assertAlmostEqual(math.sqrt(sum(v * v for v in passage)), 1.0, places=4)
        self.assertNotEqual(passage, query)

    def test_relevant_passage_outranks_irrelevant_in_chroma(self):
        index = ephemeral_vector_index(self, BGE_SMALL_MODEL_NAME)
        texts = [
            "Passwords must be changed every 90 days and may not be reused.",
            "The Raspberry Pi Pico runs from a supply voltage between 1.8 V and 5.5 V.",
        ]
        chunks = [{"chunk_id": "doc:{0}".format(i), "chunk_index": i, "text": t} for i, t in enumerate(texts)]
        index.replace_document(KB_ID, "doc", CHUNKER, chunks, self.embedder.embed_documents(texts))
        hits = index.query(KB_ID, self.embedder.embed_query("What input voltage does the Pico accept?"), CHUNKER, 2)
        self.assertEqual(hits[0][0], "doc:1")
        self.assertGreater(hits[0][1], hits[1][1])

    def test_full_document_indexer_run(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_path = os.path.join(directory.name, "model.sqlite3")
        status_repository = SQLiteIngestionStatusRepository(db_path)
        artifact_repository = SQLiteArtifactRepository(db_path)
        vector_index = ephemeral_vector_index(self, BGE_SMALL_MODEL_NAME)
        indexer = DocumentIndexer(self.embedder, vector_index, BM25KeywordIndex(artifact_repository))
        processor = DocumentProcessor(status_repository, artifact_repository,
                                      chunker=FixedSizeCharChunker(200, 40), indexer=indexer)
        path = os.path.join(directory.name, "pico.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("GPIO17 is UART0 RX. The board measures 51 mm by 21 mm. " * 10
                         + "Flash memory is 2 MB of QSPI flash. " * 10)
        entry = IngestionUploadService(status_repository=status_repository).create_upload_request(
            [UploadFileInput("pico.txt", os.path.getsize(path), "2026-10-20T12:00:00Z", temp_file_path=path)],
            KB_ID,
        )["files"][0]
        saved = processor(IngestionJob(entry["document_id"], path))
        self.assertEqual(vector_index.count(KB_ID, document_id=entry["document_id"]), saved)
        hits = vector_index.query(KB_ID, self.embedder.embed_query("How much flash memory?"), CHUNKER, 3)
        self.assertEqual(len(hits), 3)


if __name__ == "__main__":
    unittest.main()
