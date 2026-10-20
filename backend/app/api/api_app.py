"""FastAPI app for the knowledge hub: upload, status and inventory endpoints (F1).

Run from the repo root (one process only; see docs/SPEC.md, section 2):
    .venv\\Scripts\\python -m uvicorn api.api_app:create_app --factory --app-dir backend\\app

The app owns one in-memory job queue and one background worker thread. The
worker starts with the app and stops on shutdown. Documents still queued in
SQLite when the app starts (for example after a restart) are enqueued again.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, File, Form, Query, UploadFile
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
from ingestion.ingestion_artifact_repository import SQLiteArtifactRepository
from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_error_model import (
    ERROR_NOT_FOUND,
    ERROR_VALIDATION_FAILED,
    build_ingestion_error,
)
from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_pipeline import DocumentProcessor
from ingestion.ingestion_status_constants import INGESTION_STATUS_QUEUED, INGESTION_STATUSES
from ingestion.ingestion_status_repository import DEFAULT_DATABASE_PATH, SQLiteIngestionStatusRepository
from ingestion.ingestion_status_service import IngestionStatusService
from ingestion.ingestion_upload_service import IngestionUploadService, UploadFileInput
from ingestion.ingestion_worker import start_background_worker

LOGGER = logging.getLogger(__name__)

# backend/instance/uploads/, next to the dev database (git-ignored).
DEFAULT_UPLOAD_DIR = os.path.join(os.path.dirname(DEFAULT_DATABASE_PATH), "uploads")
DEFAULT_WORKER_JOIN_TIMEOUT_SECONDS = 10.0

# Kept in the service-layer result for the worker, never sent to clients:
# it is an absolute local path.
PRIVATE_FILE_FIELDS = ("temp_file_path",)


def create_app(config=None, status_repository=None, artifact_repository=None, upload_dir=None,
               worker_join_timeout=DEFAULT_WORKER_JOIN_TIMEOUT_SECONDS):
    """Build the API. Every argument is injectable so tests can use a temp DB and upload dir.

    The artifact repository defaults to the status repository's database file.
    """
    config = config if config is not None else IngestionConfig()
    status_repository = (
        status_repository if status_repository is not None else SQLiteIngestionStatusRepository()
    )
    artifact_repository = (
        artifact_repository if artifact_repository is not None
        else SQLiteArtifactRepository(status_repository.database_path)
    )
    upload_root = os.path.abspath(upload_dir if upload_dir is not None else DEFAULT_UPLOAD_DIR)
    os.makedirs(upload_root, exist_ok=True)

    upload_service = IngestionUploadService(config=config, status_repository=status_repository)
    status_service = IngestionStatusService(status_repository)
    job_queue = InMemoryIngestionJobQueue()

    @asynccontextmanager
    async def lifespan(app):
        requeued = _requeue_queued_documents(status_repository, job_queue)
        if requeued:
            LOGGER.info("Re-enqueued %d document(s) still queued from a previous run", requeued)
        processor = DocumentProcessor(status_repository, artifact_repository, config=config)
        thread, stop_event = start_background_worker(job_queue, processor, status_repository=status_repository)
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

    return app


def _public_upload_response(response):
    """The upload service response without fields that expose local paths."""
    public = dict(response)
    public["files"] = [
        {key: value for key, value in entry.items() if key not in PRIVATE_FILE_FIELDS}
        for entry in response["files"]
    ]
    return public


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
