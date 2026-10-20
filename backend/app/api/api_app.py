"""FastAPI app for the knowledge hub: upload, status and inventory endpoints (F1).

Run from the repo root (one process only; see docs/SPEC.md, section 2):
    .venv\\Scripts\\python -m uvicorn api.api_app:create_app --factory --app-dir backend\\app

The app owns one in-memory job queue and one background worker thread. The
worker starts with the app and stops on shutdown. On startup, documents left
processing by a previous run are marked failed (their vectors removed), and
documents still queued in SQLite are enqueued again.

The worker embeds and indexes each document (F2). The embedder, the Chroma
vector index, the BM25 keyword index, the indexer and the retriever live on
app.state. POST /search (F3) returns the raw vector and keyword lists per KB
and the merged list.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.api_errors import ApiError, install_error_handlers
from api.api_uploads import (
    RequestSizeLimitMiddleware,
    max_request_bytes,
    remove_upload_dir,
    sanitize_filename,
    save_upload,
    upload_path,
)
from indexing.indexing_embedder import BgeSmallEmbedder
from indexing.indexing_keyword_index import BM25KeywordIndex
from indexing.indexing_service import DocumentIndexer
from indexing.indexing_vector_index import ChromaVectorIndex
from ingestion.ingestion_artifact_repository import SQLiteArtifactRepository
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_error_model import (
    ERROR_INTERNAL_FAILURE,
    ERROR_NOT_FOUND,
    ERROR_NOT_IMPLEMENTED,
    ERROR_VALIDATION_FAILED,
    build_ingestion_error,
)
from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_pipeline import DocumentProcessor
from ingestion.ingestion_status_constants import (
    INGESTION_STATUS_PROCESSING,
    INGESTION_STATUS_QUEUED,
    INGESTION_STATUSES,
)
from ingestion.ingestion_status_repository import DEFAULT_DATABASE_PATH, SQLiteIngestionStatusRepository
from ingestion.ingestion_status_service import IngestionStatusService
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput
from ingestion.ingestion_worker import start_background_worker
from retrieval import retrieval_merge
from retrieval.retrieval_config import RetrievalConfig
from retrieval.retrieval_retriever import BASELINE_CHUNKER, SOURCE_KEYWORD, SOURCE_VECTOR, Retriever

LOGGER = logging.getLogger(__name__)

# backend/instance/uploads/, next to the dev database (git-ignored).
DEFAULT_UPLOAD_DIR = os.path.join(os.path.dirname(DEFAULT_DATABASE_PATH), "uploads")
DEFAULT_WORKER_JOIN_TIMEOUT_SECONDS = 10.0
INTERRUPTED_REASON = "interrupted by server restart"

# Kept in the service-layer result for the worker, never sent to clients:
# it is an absolute local path.
PRIVATE_FILE_FIELDS = ("temp_file_path",)

# Bounds for POST /search, so a debug call can't ask for the whole KB.
MAX_SEARCH_TOP_K = 100
MAX_SEARCH_TOP_N = 100


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    kb_ids: Optional[List[str]] = Field(None, description="KBs to search; omitted means every configured KB")
    top_k: Optional[int] = Field(None, ge=1, le=MAX_SEARCH_TOP_K, description="Hits per ranked list")
    top_n: int = Field(retrieval_merge.DEFAULT_TOP_N, ge=1, le=MAX_SEARCH_TOP_N, description="Merged hits")
    chunker: str = BASELINE_CHUNKER


def create_app(config=None, status_repository=None, artifact_repository=None, upload_dir=None,
               worker_join_timeout=DEFAULT_WORKER_JOIN_TIMEOUT_SECONDS, embedder=None, vector_index=None,
               keyword_index=None, retrieval_config=None):
    """Build the API. Every argument is injectable so tests can use a temp DB, upload dir and indexes.

    The artifact repository defaults to the status repository's database file,
    and the Chroma directory to chroma/ beside that file
    (backend/instance/chroma/ for the dev DB). The embedder defaults to
    bge-small, which loads on the first document or search, not at startup.
    """
    config = config if config is not None else IngestionConfig()
    retrieval_config = retrieval_config if retrieval_config is not None else RetrievalConfig()
    status_repository = (
        status_repository if status_repository is not None else SQLiteIngestionStatusRepository()
    )
    artifact_repository = (
        artifact_repository if artifact_repository is not None
        else SQLiteArtifactRepository(status_repository.database_path)
    )
    embedder = embedder if embedder is not None else BgeSmallEmbedder()
    vector_index = (
        vector_index if vector_index is not None
        else ChromaVectorIndex.persistent(os.path.join(os.path.dirname(status_repository.database_path), "chroma"))
    )
    keyword_index = keyword_index if keyword_index is not None else BM25KeywordIndex(artifact_repository)
    indexer = DocumentIndexer(embedder, vector_index, keyword_index)
    retriever = Retriever(embedder, vector_index, keyword_index, artifact_repository, top_k=retrieval_config.top_k)
    upload_root = os.path.abspath(upload_dir if upload_dir is not None else DEFAULT_UPLOAD_DIR)
    os.makedirs(upload_root, exist_ok=True)

    upload_service = IngestionUploadService(config=config, status_repository=status_repository)
    status_service = IngestionStatusService(status_repository)
    job_queue = InMemoryIngestionJobQueue()

    @asynccontextmanager
    async def lifespan(app):
        interrupted = _fail_interrupted_documents(status_repository, vector_index)
        if interrupted:
            LOGGER.warning("Marked %d document(s) failed: still processing when the server stopped", interrupted)
        requeued = _requeue_queued_documents(status_repository, job_queue)
        if requeued:
            LOGGER.info("Re-enqueued %d document(s) still queued from a previous run", requeued)
        processor = DocumentProcessor(status_repository, artifact_repository, config=config, indexer=indexer)

        def refresh_keyword_index(job, _status):
            # BM25 only covers documents in success, so a finished document
            # becomes keyword-searchable on the next query.
            document = status_repository.get_document(job.document_id)
            if document is not None:
                keyword_index.invalidate(document["kb_id"])

        thread, stop_event = start_background_worker(
            job_queue, processor, status_repository=status_repository, on_finished=refresh_keyword_index,
        )
        app.state.worker_thread = thread
        try:
            yield
        finally:
            # The worker finishes the job in progress; jobs not yet picked up stay
            # queued in SQLite and are re-enqueued on the next start.
            stop_event.set()
            await run_in_threadpool(thread.join, worker_join_timeout)
            if thread.is_alive():
                LOGGER.warning("Ingestion worker did not stop within %.1f s", worker_join_timeout)

    app = FastAPI(title="AI Knowledge Hub API", version="0.1.0", lifespan=lifespan)
    app.state.config = config
    app.state.status_repository = status_repository
    app.state.artifact_repository = artifact_repository
    app.state.embedder = embedder
    app.state.vector_index = vector_index
    app.state.keyword_index = keyword_index
    app.state.indexer = indexer
    app.state.retrieval_config = retrieval_config
    app.state.retriever = retriever
    app.state.upload_dir = upload_root
    app.state.job_queue = job_queue
    app.state.worker_thread = None
    install_error_handlers(app)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=max_request_bytes(config))

    @app.post("/documents", status_code=202)
    async def upload_documents(kb_id: str = Form(...), files: List[UploadFile] = File(...)):
        """Store and register one or more files for one KB; enqueue every accepted file.

        Returns 202 with per-file accepted/rejected results whenever the request
        itself is valid, even if every file was rejected. Request-level problems
        (unknown KB, too many files) return the canonical error instead.
        """
        upload_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        document_ids = []
        try:
            inputs = []
            for upload in files:
                document_id = IngestionUploadService.new_document_id()
                file_name = sanitize_filename(upload.filename)
                destination = upload_path(upload_root, document_id, file_name)
                document_ids.append(document_id)
                size, too_large = await save_upload(upload, destination, config.max_file_size_bytes)
                if too_large and upload.size is not None:
                    size = max(size, upload.size)
                inputs.append(UploadFileInput(
                    file_name, size, upload_timestamp,
                    temp_file_path=None if too_large else destination,
                    document_id=document_id,
                ))
            response = await run_in_threadpool(upload_service.create_upload_request, inputs, kb_id)
        except BaseException:
            for document_id in document_ids:
                remove_upload_dir(upload_root, document_id)
            raise

        if not response["files"]:
            for document_id in document_ids:
                remove_upload_dir(upload_root, document_id)
            raise ApiError(response["errors"][0])

        # One result per input, in order (the service appends one entry per file).
        for entry, file_input in zip(response["files"], inputs):
            if entry["status"] == "accepted":
                job_queue.enqueue(IngestionJob(entry["document_id"], entry["temp_file_path"], entry["metadata"]))
            else:
                remove_upload_dir(upload_root, file_input.document_id)
        return _public_upload_response(response)

    @app.get("/documents")
    def list_documents(kb_id: Optional[str] = None):
        """Inventory, newest first, optionally for one KB. Same fields as GET /documents/{id}, no history."""
        if kb_id is not None:
            kb_id, kb_error = upload_service.resolve_kb_id(kb_id)
            if kb_error is not None:
                raise ApiError(kb_error)
        return {"documents": status_service.list_documents(kb_id)}

    # Registered before /documents/{document_id}, so "status" is not taken as an ID.
    @app.get("/documents/status")
    def batch_status(document_id: List[str] = Query(...)):
        """Batch status for repeated ?document_id= values; unknown IDs are listed, not errors."""
        try:
            return status_service.get_batch_status(document_id)
        except ValueError as exc:
            raise ApiError(build_ingestion_error(ERROR_VALIDATION_FAILED, details=str(exc), field="document_id"))

    @app.get("/documents/{document_id}")
    def get_document(document_id: str):
        """Status, history, failure_code and failure_reason for one document."""
        try:
            status = status_service.get_document_status(document_id)
        except ValueError as exc:
            raise ApiError(build_ingestion_error(ERROR_VALIDATION_FAILED, details=str(exc), field="document_id"))
        if status is None:
            raise ApiError(build_ingestion_error(
                ERROR_NOT_FOUND, details="Unknown document: {0}".format(document_id), field="document_id",
            ))
        return status

    @app.get("/kbs")
    def list_kbs():
        """Configured KBs in config order, with document counts for every lifecycle state."""
        counts = status_repository.count_documents_by_kb_and_status()
        kbs = []
        for configured_kb_id in config.allowed_kb_ids:
            kb_counts = counts.get(configured_kb_id, {})
            by_status = {status: kb_counts.get(status, 0) for status in INGESTION_STATUSES}
            kbs.append({"kb_id": configured_kb_id, "counts": by_status, "total": sum(by_status.values())})
        return {"kbs": kbs}

    @app.post("/search")
    def search(request: SearchRequest):
        """Retrieval evidence for a query: per KB, the raw vector and keyword lists, plus the merged list.

        A debug endpoint (no LLM). The merged list comes from
        merge_ranked_lists over every KB's two lists; if the merge fails or is
        not implemented yet, "merged" is null, "merge_error" holds the
        canonical error, and the raw lists are still returned.
        """
        query = request.query.strip()
        if not query:
            raise ApiError(build_ingestion_error(ERROR_VALIDATION_FAILED, details="query must not be blank",
                                                 field="query"))
        if request.kb_ids is None:
            kb_ids = list(config.allowed_kb_ids)
        elif not request.kb_ids:
            raise ApiError(build_ingestion_error(ERROR_VALIDATION_FAILED, details="kb_ids must not be empty",
                                                 field="kb_ids"))
        else:
            kb_ids = []
            for raw_kb_id in request.kb_ids:
                kb_id, kb_error = upload_service.resolve_kb_id(raw_kb_id)
                if kb_error is not None:
                    raise ApiError(dict(kb_error, field="kb_ids"))
                if kb_id not in kb_ids:
                    kb_ids.append(kb_id)
        top_k = request.top_k if request.top_k is not None else retrieval_config.top_k

        results = retriever.retrieve_many(kb_ids, query, chunker=request.chunker, top_k=top_k)
        ranked_lists = []
        for kb_id in kb_ids:
            ranked_lists.append(results[kb_id][SOURCE_VECTOR])
            ranked_lists.append(results[kb_id][SOURCE_KEYWORD])
        merged, merge_error = None, None
        try:
            merged = retrieval_merge.merge_ranked_lists(ranked_lists, top_n=request.top_n)
        except NotImplementedError:
            merge_error = build_ingestion_error(
                ERROR_NOT_IMPLEMENTED, details="merge_ranked_lists (RRF) is not implemented yet")
        except Exception:
            LOGGER.exception("merge_ranked_lists failed for /search")
            merge_error = build_ingestion_error(ERROR_INTERNAL_FAILURE, details="merge_ranked_lists failed")
        if merge_error is not None:
            merge_error.setdefault("details", None)
        return {
            "query": query, "kb_ids": kb_ids, "chunker": request.chunker, "top_k": top_k, "top_n": request.top_n,
            "results": results, "merged": merged, "merge_error": merge_error,
        }

    return app


def _public_upload_response(response):
    """The upload service response without fields that expose local paths."""
    public = dict(response)
    public["files"] = [
        {key: value for key, value in entry.items() if key not in PRIVATE_FILE_FIELDS}
        for entry in response["files"]
    ]
    return public


def _fail_interrupted_documents(status_repository, vector_index):
    """Mark documents left processing by a previous run failed and drop their vectors; return how many.

    The in-memory queue lost their jobs, and the lifecycle has no way back to
    queued. Re-uploading the file processes it again.
    """
    count = 0
    for record in status_repository.list_documents():
        if record["ingestion_status"] != INGESTION_STATUS_PROCESSING:
            continue
        status_repository.mark_failed(record["document_id"], INTERRUPTED_REASON, ERROR_INTERNAL_FAILURE)
        try:
            vector_index.delete_document(record["kb_id"], record["document_id"])
        except Exception:
            LOGGER.exception("Could not remove vectors of interrupted document %s", record["document_id"])
        count += 1
    return count


def _requeue_queued_documents(status_repository, job_queue):
    """Enqueue every document still queued in SQLite, oldest first; return how many."""
    count = 0
    for record in reversed(status_repository.list_documents()):
        if record["ingestion_status"] != INGESTION_STATUS_QUEUED:
            continue
        if not record.get("temp_file_path"):
            LOGGER.warning("Queued document %s has no stored file; not re-enqueued", record["document_id"])
            continue
        job_queue.enqueue(IngestionJob(record["document_id"], record["temp_file_path"], record["metadata"]))
        count += 1
    return count
