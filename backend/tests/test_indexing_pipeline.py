"""Worker pipeline with indexing (F2): extract -> chunk -> persist -> embed -> index, then success."""

import os
import sys
import tempfile
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from indexing_fakes import FakeEmbedder, make_indexer

from indexing.indexing_service import IndexingError
from ingestion.ingestion_artifact_repository import SQLiteArtifactRepository
from ingestion.ingestion_chunking import FixedSizeCharChunker
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_error_model import ERROR_INDEXING_FAILURE
from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_pipeline import DocumentProcessor
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput
from ingestion.ingestion_worker import start_background_worker

KB_ID = IngestionConfig().allowed_kb_ids[0]
CHUNKER = FixedSizeCharChunker.name
TXT = "The RP2040 exposes gpio17 as UART0 RX. Supply is 3.3V. " * 4


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = directory.name
        db_path = os.path.join(self.dir, "pipeline.sqlite3")
        self.status_repository = SQLiteIngestionStatusRepository(db_path)
        self.artifact_repository = SQLiteArtifactRepository(db_path)
        self.upload_service = IngestionUploadService(status_repository=self.status_repository)
        self.embedder = FakeEmbedder()
        self.indexer = make_indexer(self, self.artifact_repository, self.embedder)
        self.vector_index = self.indexer.vector_index
        self.keyword_index = self.indexer.keyword_index
        self.processor = DocumentProcessor(
            self.status_repository, self.artifact_repository, chunker=FixedSizeCharChunker(60, 10),
            indexer=self.indexer,
        )

    def upload(self, name="pico.txt", content=TXT):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        response = self.upload_service.create_upload_request(
            [UploadFileInput(name, os.path.getsize(path), "2026-10-20T12:00:00Z", temp_file_path=path)], KB_ID,
        )
        entry = response["files"][0]
        return IngestionJob(entry["document_id"], entry["temp_file_path"], entry["metadata"])

    def run_worker(self, jobs, on_finished=None):
        queue = InMemoryIngestionJobQueue()
        for job in jobs:
            queue.enqueue(job)
        thread, stop = start_background_worker(queue, self.processor, status_repository=self.status_repository,
                                               on_finished=on_finished)
        try:
            queue.join()
        finally:
            stop.set()
            thread.join()

    def status(self, job):
        return self.status_repository.get_document(job.document_id)["ingestion_status"]

    def failure_code(self, job):
        return self.status_repository.get_status_history(job.document_id)[-1]["error_code"]


class TestPipelineIndexing(PipelineTestCase):
    def test_success_only_after_indexing_and_counts_match(self):
        job = self.upload()
        seen = []
        original = self.indexer.index_document

        def spy(document, chunker_name, chunks):
            seen.append(self.status(job))
            return original(document, chunker_name, chunks)

        self.indexer.index_document = spy
        self.run_worker([job])
        self.assertEqual(seen, ["processing"])
        self.assertEqual(self.status(job), "success")
        sqlite_count = self.artifact_repository.count_chunks(document_id=job.document_id, chunker=CHUNKER)
        self.assertGreater(sqlite_count, 1)
        self.assertEqual(self.vector_index.count(KB_ID, document_id=job.document_id, chunker=CHUNKER), sqlite_count)
        self.assertEqual(sum(len(batch) for batch in self.embedder.document_calls), sqlite_count)

    def test_indexes_persisted_chunk_ids_and_pages(self):
        job = self.upload()
        self.run_worker([job])
        chunk_ids = [c["chunk_id"] for c in self.artifact_repository.get_chunks(job.document_id, CHUNKER)]
        hits = self.vector_index.query(KB_ID, FakeEmbedder.vector(TXT[:60]), CHUNKER, top_k=len(chunk_ids) + 5)
        self.assertEqual(sorted(h[0] for h in hits), sorted(chunk_ids))

    def test_reprocessing_leaves_no_duplicates(self):
        job = self.upload()
        first = self.processor(job)
        second = self.processor(job)
        self.assertEqual(first, second)
        self.assertEqual(self.vector_index.count(KB_ID), first)

    def test_embedder_failure_marks_failed_with_indexing_failure_and_leaves_no_vectors(self):
        job = self.upload()
        self.processor(job)  # an earlier successful run left vectors behind
        self.assertGreater(self.vector_index.count(KB_ID, document_id=job.document_id), 0)
        self.embedder.fail_with = RuntimeError("model crashed")
        with self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            self.run_worker([job])
        self.assertEqual(self.status(job), "failed")
        self.assertEqual(self.failure_code(job), ERROR_INDEXING_FAILURE)
        reason = self.status_repository.get_status_history(job.document_id)[-1]["reason"]
        self.assertIn("RuntimeError: model crashed", reason)
        self.assertEqual(self.vector_index.count(KB_ID, document_id=job.document_id), 0)

    def test_chroma_failure_after_partial_write_leaves_no_vectors(self):
        job = self.upload()
        original = self.vector_index.replace_document

        def write_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("disk full")

        self.vector_index.replace_document = write_then_fail
        with self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            self.run_worker([job])
        self.assertEqual((self.status(job), self.failure_code(job)), ("failed", ERROR_INDEXING_FAILURE))
        self.assertEqual(self.vector_index.count(KB_ID), 0)

    def test_count_mismatch_is_an_indexing_error(self):
        job = self.upload()
        document = self.status_repository.get_document(job.document_id)
        chunks = [{"chunk_id": "c1", "chunk_index": 0, "text": "a"}]
        self.vector_index.count = lambda *args, **kwargs: 7
        with self.assertRaises(IndexingError) as caught:
            self.indexer.index_document(document, CHUNKER, chunks)
        self.assertEqual(caught.exception.error_code, ERROR_INDEXING_FAILURE)
        self.assertIn("Indexed 7 vectors for 1 chunks", str(caught.exception))

    def test_bm25_sees_a_document_only_after_it_finishes(self):
        job = self.upload()
        observed = []

        def on_finished(finished_job, status):
            observed.append((status, self.status(finished_job)))
            self.keyword_index.invalidate(KB_ID)

        # Warm the cache while the KB is empty, then index the document while
        # it is still processing: neither may expose it.
        self.assertEqual(self.keyword_index.query(KB_ID, "gpio17", CHUNKER, 5), [])
        original = self.indexer.index_document

        def query_during_processing(document, chunker_name, chunks):
            indexed = original(document, chunker_name, chunks)
            observed.append(("during", self.keyword_index.query(KB_ID, "gpio17", CHUNKER, 5)))
            return indexed

        self.indexer.index_document = query_during_processing
        self.run_worker([job], on_finished=on_finished)
        self.assertEqual(observed, [("during", []), ("success", "success")])
        hits = self.keyword_index.query(KB_ID, "gpio17", CHUNKER, 5)
        self.assertTrue(hits)
        self.assertTrue(all(chunk_id.startswith(job.document_id) for chunk_id, _score in hits))


if __name__ == "__main__":
    unittest.main()
