"""SQLite storage for extracted full text and chunks (tasks 6.2, 6.3, 6.5)."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from itertools import islice

from ingestion.ingestion_status_repository import DEFAULT_DATABASE_PATH

INSERT_BATCH_SIZE = 500


class SQLiteArtifactRepository(object):
    """Stores artifacts in the same database file as the status repository.

    Rows reference ingestion_documents, so create the status repository on
    the same path first. Each operation owns its connection, allowing use
    from worker threads. Chunks are keyed by chunker name, so the baseline
    and a structure-aware chunker can store chunks for the same document.
    """

    def __init__(self, database_path=DEFAULT_DATABASE_PATH):
        if not database_path or database_path == ":memory:":
            raise ValueError("database_path must be a persistent file path")
        self.database_path = os.path.abspath(database_path)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS document_texts (
                    document_id TEXT PRIMARY KEY REFERENCES ingestion_documents(document_id),
                    kb_id TEXT NOT NULL,
                    full_text TEXT NOT NULL,
                    char_count INTEGER NOT NULL,
                    extractor TEXT,
                    extraction_metadata_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS document_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES ingestion_documents(document_id),
                    kb_id TEXT NOT NULL,
                    chunker TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    page_start INTEGER,
                    page_end INTEGER,
                    text TEXT NOT NULL,
                    UNIQUE (document_id, chunker, chunk_index)
                );
                CREATE INDEX IF NOT EXISTS idx_document_chunks_kb_id
                    ON document_chunks(kb_id);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
                    ON document_chunks(document_id);
            """)
        finally:
            connection.close()

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def save_document_artifacts(self, document_id, kb_id, full_text, extraction_metadata,
                                chunker_name, chunks):
        """Save full text and replace this chunker's chunks in one transaction.

        chunks may be any iterable (for example a generator); it is consumed
        in batches. Re-running replaces earlier rows instead of duplicating
        them. Any failure, including one raised by the iterable, rolls back
        and leaves earlier artifacts intact. Returns the number of chunks saved.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        metadata = extraction_metadata or {}
        rows = (
            (chunk["chunk_id"], document_id, kb_id, chunker_name, chunk["chunk_index"],
             chunk["start"], chunk["end"], chunk.get("page_start"), chunk.get("page_end"),
             chunk["text"])
            for chunk in chunks
        )
        saved = 0
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT INTO document_texts (document_id, kb_id, full_text, char_count, "
                    "extractor, extraction_metadata_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(document_id) DO UPDATE SET kb_id = excluded.kb_id, "
                    "full_text = excluded.full_text, char_count = excluded.char_count, "
                    "extractor = excluded.extractor, "
                    "extraction_metadata_json = excluded.extraction_metadata_json, "
                    "updated_at = excluded.updated_at",
                    (document_id, kb_id, full_text, len(full_text), metadata.get("extractor"),
                     json.dumps(metadata), timestamp),
                )
                connection.execute(
                    "DELETE FROM document_chunks WHERE document_id = ? AND chunker = ?",
                    (document_id, chunker_name),
                )
                while True:
                    batch = list(islice(rows, INSERT_BATCH_SIZE))
                    if not batch:
                        break
                    connection.executemany(
                        "INSERT INTO document_chunks (chunk_id, document_id, kb_id, chunker, "
                        "chunk_index, start_offset, end_offset, page_start, page_end, text) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        batch,
                    )
                    saved += len(batch)
            return saved
        finally:
            connection.close()

    def get_full_text(self, document_id):
        """Return the stored text record, or None."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM document_texts WHERE document_id = ?", (document_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["extraction_metadata"] = json.loads(result.pop("extraction_metadata_json"))
            return result
        finally:
            connection.close()

    def get_chunks(self, document_id, chunker=None):
        """Return chunks ordered by chunker and chunk index."""
        query = "SELECT * FROM document_chunks WHERE document_id = ?"
        params = [document_id]
        if chunker is not None:
            query += " AND chunker = ?"
            params.append(chunker)
        connection = self._connect()
        try:
            rows = connection.execute(query + " ORDER BY chunker, chunk_index", params).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def count_chunks(self, document_id=None, kb_id=None, chunker=None):
        conditions = []
        params = []
        for column, value in (("document_id", document_id), ("kb_id", kb_id), ("chunker", chunker)):
            if value is not None:
                conditions.append("{0} = ?".format(column))
                params.append(value)
        query = "SELECT COUNT(*) FROM document_chunks"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        connection = self._connect()
        try:
            return connection.execute(query, params).fetchone()[0]
        finally:
            connection.close()
