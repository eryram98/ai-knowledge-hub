"""Document processing for the worker: extract, chunk, persist (task 8.3, worker half).

Embedding and indexing stages are not wired in yet (tasks 5.3, 5.4, 5.7).
"""

from ingestion.ingestion_chunking import FixedSizeCharChunker
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_metadata_contract import META_FILE_TYPE, META_KB_ID
from ingestion.ingestion_text_extraction import TextExtractionDispatcher


class DocumentProcessor(object):
    """Callable passed to run_worker as process_job.

    Returns normally on success. Raises on any stage failure; stage errors
    carry a canonical error_code, which run_worker stores with the failure.
    Reprocessing a document replaces its text and chunks (no duplicates).
    """

    def __init__(self, status_repository, artifact_repository, extractor=None, chunker=None,
                 config=None):
        self.status_repository = status_repository
        self.artifact_repository = artifact_repository
        self.extractor = extractor if extractor is not None else TextExtractionDispatcher()
        self.chunker = (
            chunker if chunker is not None
            else FixedSizeCharChunker.from_config(config or IngestionConfig())
        )

    def __call__(self, job):
        document = self.status_repository.get_document(job.document_id)
        if document is None:
            raise KeyError("Unknown document: {0}".format(job.document_id))
        kb_id = document["kb_id"]
        file_type = document["metadata"][META_FILE_TYPE]

        extracted = self.extractor.extract_text(job.temp_file_path, file_type)
        full_text = extracted["full_text"]
        extraction_metadata = extracted.get("metadata") or {}

        chunk_metadata = dict(extraction_metadata)
        chunk_metadata.update({"document_id": job.document_id, META_KB_ID: kb_id})
        chunks = self.chunker.iter_chunks(full_text, chunk_metadata)

        return self.artifact_repository.save_document_artifacts(
            job.document_id, kb_id, full_text, extraction_metadata, self.chunker.name, chunks,
        )
