"""Read-only, JSON-compatible status responses for future UI/API polling."""

from ingestion.ingestion_status_constants import (
    INGESTION_STATUSES, TERMINAL_INGESTION_STATUSES,
    INGESTION_STATUS_PROCESSING, INGESTION_STATUS_FAILED,
)
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository


class IngestionStatusService(object):
    def __init__(self, status_repository=None):
        self.status_repository = (
            status_repository if status_repository is not None
            else SQLiteIngestionStatusRepository()
        )

    def get_document_status(self, document_id):
        """Return status or None for an unknown ID; invalid IDs raise ValueError."""
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("document_id must be a non-empty string")
        record = self.status_repository.get_status_snapshot(document_id)
        if record is None:
            return None
        return _status_from_record(record)

    def list_documents(self, kb_id=None):
        """Return the inventory, newest first: get_document_status output without history.

        kb_id filters to one KB; validating it against the config is the caller's job.
        """
        documents = []
        for record in self.status_repository.list_documents(kb_id):
            document = _status_from_record(record)
            del document["history"]
            documents.append(document)
        return documents

    def get_batch_status(self, document_ids):
        """Poll explicit accepted document IDs, not an upload-request ID.

        Duplicate IDs count once. Unknown IDs are listed separately and never
        counted as completed. Documents are read individually, so the batch
        summary is an observation rather than an atomic batch snapshot.
        """
        if not isinstance(document_ids, list):
            raise ValueError("document_ids must be a list")
        if any(not isinstance(value, str) or not value.strip() for value in document_ids):
            raise ValueError("Each document ID must be a non-empty string")
        ids = list(dict.fromkeys(document_ids))
        documents = []
        missing = []
        counts = {status: 0 for status in INGESTION_STATUSES}
        for document_id in ids:
            document = self.get_document_status(document_id)
            if document is None:
                missing.append(document_id)
            else:
                documents.append(document)
                counts[document["ingestion_status"]] += 1
        completed = sum(counts[status] for status in TERMINAL_INGESTION_STATUSES)
        return {
            "documents": documents,
            "missing_document_ids": missing,
            "counts": counts,
            "total": len(ids),
            "completed": completed,
            "progress_percent": (100.0 * completed / len(ids)) if ids else 0.0,
            "is_complete": bool(ids) and completed == len(ids),
            "should_poll": any(document["should_poll"] for document in documents),
        }


def _status_from_record(record):
    """Build the JSON-compatible status dict from a repository snapshot record."""
    history = record["history"]
    status = record["ingestion_status"]
    metadata = record["metadata"]
    terminal = status in TERMINAL_INGESTION_STATUSES
    processing = next((item["timestamp"] for item in history
                       if item["status"] == INGESTION_STATUS_PROCESSING), None)
    return {
        "document_id": record["document_id"],
        "kb_id": record["kb_id"],
        "original_filename": metadata["original_filename"],
        "file_type": metadata.get("file_type"),
        "file_size_bytes": metadata.get("file_size_bytes"),
        "ingestion_status": status,
        "upload_timestamp": metadata["upload_timestamp"],
        "queued_at": record["queued_at"],
        "processing_at": processing,
        "completed_at": history[-1]["timestamp"] if terminal else None,
        "updated_at": history[-1]["timestamp"],
        "failure_reason": history[-1]["reason"] if status == INGESTION_STATUS_FAILED else None,
        "failure_code": history[-1]["error_code"] if status == INGESTION_STATUS_FAILED else None,
        "is_terminal": terminal,
        "should_poll": not terminal,
        "history": history,
    }
