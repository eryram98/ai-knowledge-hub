"""SQLite storage for initial ingestion status (Python 3.6+)."""

import json
import os
import sqlite3
from datetime import datetime, timezone

from ingestion.ingestion_error_model import ERROR_INTERNAL_FAILURE, is_valid_error_code
from ingestion.ingestion_metadata_contract import META_KB_ID, validate_metadata_contract
from ingestion.ingestion_status_constants import (
    INGESTION_STATUS_QUEUED, INGESTION_STATUS_PROCESSING,
    INGESTION_STATUS_SUCCESS, INGESTION_STATUS_FAILED,
)


DEFAULT_DATABASE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "instance", "ingestion.sqlite3",
)


class SQLiteIngestionStatusRepository(object):
    """Each operation owns its connection, allowing use from worker threads.

    Supply a file path for isolated tests or a different storage location.
    An existing document ID is rejected rather than resetting its lifecycle.
    """

    def __init__(self, database_path=DEFAULT_DATABASE_PATH):
        if not database_path or database_path == ":memory:":
            raise ValueError("database_path must be a persistent file path")
        self.database_path = os.path.abspath(database_path)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        connection = self._connect()
        try:
            # WAL is stored in the database file, so every later connection uses it.
            # It lets status polling read while the worker writes.
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS ingestion_documents (
                    document_id TEXT PRIMARY KEY,
                    kb_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    temp_file_path TEXT,
                    ingestion_status TEXT NOT NULL,
                    queued_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ingestion_documents_kb_id
                    ON ingestion_documents(kb_id);
                CREATE TABLE IF NOT EXISTS ingestion_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL REFERENCES ingestion_documents(document_id),
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    reason TEXT,
                    error_code TEXT
                );
            """)
        finally:
            connection.close()

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_queued(self, metadata, temp_file_path=None):
        """Atomically save document metadata and its first history entry."""
        valid, errors = validate_metadata_contract(metadata)
        if not valid:
            raise ValueError("Invalid metadata: {0}".format("; ".join(errors)))
        document_id = metadata.get("document_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("document_id must be a non-empty string")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT INTO ingestion_documents "
                    "(document_id, kb_id, metadata_json, temp_file_path, ingestion_status, queued_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (document_id, metadata[META_KB_ID], json.dumps(metadata), temp_file_path,
                     INGESTION_STATUS_QUEUED, timestamp),
                )
                connection.execute(
                    "INSERT INTO ingestion_status_history "
                    "(document_id, status, timestamp, reason) VALUES (?, ?, ?, ?)",
                    (document_id, INGESTION_STATUS_QUEUED, timestamp, None),
                )
        finally:
            connection.close()

    def mark_processing(self, document_id):
        """Claim a queued document atomically; return False if already claimed.

        Unknown IDs raise KeyError. The status update and history insert share
        a transaction, so a history failure leaves the document queued.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        connection = self._connect()
        try:
            with connection:
                changed = connection.execute(
                    "UPDATE ingestion_documents SET ingestion_status = ? "
                    "WHERE document_id = ? AND ingestion_status = ?",
                    (INGESTION_STATUS_PROCESSING, document_id, INGESTION_STATUS_QUEUED),
                ).rowcount
                if not changed:
                    exists = connection.execute(
                        "SELECT 1 FROM ingestion_documents WHERE document_id = ?",
                        (document_id,),
                    ).fetchone()
                    if exists is None:
                        raise KeyError("Unknown document: {0}".format(document_id))
                    return False
                connection.execute(
                    "INSERT INTO ingestion_status_history "
                    "(document_id, status, timestamp, reason) VALUES (?, ?, ?, ?)",
                    (document_id, INGESTION_STATUS_PROCESSING, timestamp, None),
                )
            return True
        finally:
            connection.close()

    def mark_success(self, document_id):
        return self._finish(document_id, INGESTION_STATUS_SUCCESS, None, None)

    def mark_failed(self, document_id, reason, error_code=ERROR_INTERNAL_FAILURE):
        """Unknown error codes are stored as internal_failure."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Failure reason must be a non-empty string")
        if not is_valid_error_code(error_code):
            error_code = ERROR_INTERNAL_FAILURE
        return self._finish(document_id, INGESTION_STATUS_FAILED, reason.strip(), error_code)

    def _finish(self, document_id, status, reason, error_code):
        """Finish processing atomically; identical terminal calls are idempotent.

        A queued or terminal document cannot be changed to another terminal
        state. Failure reasons live in the append-only status history.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        connection = self._connect()
        try:
            with connection:
                changed = connection.execute(
                    "UPDATE ingestion_documents SET ingestion_status = ? "
                    "WHERE document_id = ? AND ingestion_status = ?",
                    (status, document_id, INGESTION_STATUS_PROCESSING),
                ).rowcount
                if not changed:
                    row = connection.execute(
                        "SELECT ingestion_status FROM ingestion_documents WHERE document_id = ?",
                        (document_id,),
                    ).fetchone()
                    if row is None:
                        raise KeyError("Unknown document: {0}".format(document_id))
                    if row["ingestion_status"] == status:
                        return False
                    raise ValueError("Cannot transition {0} to {1}".format(row["ingestion_status"], status))
                connection.execute(
                    "INSERT INTO ingestion_status_history "
                    "(document_id, status, timestamp, reason, error_code) VALUES (?, ?, ?, ?, ?)",
                    (document_id, status, timestamp, reason, error_code),
                )
            return True
        finally:
            connection.close()

    def get_document(self, document_id):
        """Return stored status/metadata, or None for an unknown document."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM ingestion_documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["metadata"] = json.loads(result.pop("metadata_json"))
            return result
        finally:
            connection.close()

    def get_status_snapshot(self, document_id):
        """Read current status and history from one consistent SQLite snapshot."""
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT * FROM ingestion_documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            if row is None:
                return None
            history = connection.execute(
                "SELECT document_id, status, timestamp, reason, error_code "
                "FROM ingestion_status_history WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()
            result = dict(row)
            result["metadata"] = json.loads(result.pop("metadata_json"))
            result["history"] = [dict(item) for item in history]
            return result
        finally:
            connection.close()

    def get_status_history(self, document_id):
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT document_id, status, timestamp, reason, error_code "
                "FROM ingestion_status_history WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()
