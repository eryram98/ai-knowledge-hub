"""SQLite storage for extracted full text and chunks (tasks 6.2, 6.3, 6.5)."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from itertools import islice

from ingestion.ingestion_status_constants import INGESTION_STATUS_SUCCESS
from ingestion.ingestion_status_repository import DEFAULT_DATABASE_PATH

INSERT_BATCH_SIZE = 500
# Chunk IDs per IN (...) lookup, well under SQLite's bound-parameter limit.
LOOKUP_BATCH_SIZE = 500


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

    def list_kb_chunks(self, kb_id, chunker):
        """Return [(chunk_id, text)] for one KB and chunker, from documents in success only.

        This is the keyword index's corpus (F2): a document becomes searchable
        once the worker has marked it success, never while it is processing.
        Ordered by document insertion, then chunk index, so results are stable.
        """
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT c.chunk_id, c.text FROM document_chunks AS c "
                "JOIN ingestion_documents AS d ON d.document_id = c.document_id "
                "WHERE c.kb_id = ? AND c.chunker = ? AND d.ingestion_status = ? "
                "ORDER BY d.rowid, c.chunk_index",
                (kb_id, chunker, INGESTION_STATUS_SUCCESS),
            ).fetchall()
            return [(row["chunk_id"], row["text"]) for row in rows]
        finally:
            connection.close()

    def list_success_document_ids(self, kb_id):
        """Return the IDs of the KB's documents in success, oldest first (F3's vector filter)."""
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT document_id FROM ingestion_documents WHERE kb_id = ? AND ingestion_status = ? "
                "ORDER BY rowid",
                (kb_id, INGESTION_STATUS_SUCCESS),
            ).fetchall()
            return [row["document_id"] for row in rows]
        finally:
            connection.close()

    def get_chunk_hits(self, chunk_ids):
        """Return {chunk_id: chunk fields + source metadata} for chunks of documents in success.

        Fields: chunk_id, text, document_id, kb_id, page_start, page_end,
        original_filename. Unknown chunk IDs and chunks of documents not in
        success are left out, so a search hit can't cite a processing or failed
        document.
        """
        chunk_ids = list(dict.fromkeys(chunk_ids))
        hits = {}
        if not chunk_ids:
            return hits
        connection = self._connect()
        try:
            for start in range(0, len(chunk_ids), LOOKUP_BATCH_SIZE):
                batch = chunk_ids[start:start + LOOKUP_BATCH_SIZE]
                rows = connection.execute(
                    "SELECT c.chunk_id, c.text, c.document_id, c.kb_id, c.page_start, c.page_end, "
                    "json_extract(d.metadata_json, '$.original_filename') AS original_filename "
                    "FROM document_chunks AS c "
                    "JOIN ingestion_documents AS d ON d.document_id = c.document_id "
                    "WHERE d.ingestion_status = ? AND c.chunk_id IN ({0})".format(", ".join("?" * len(batch))),
                    [INGESTION_STATUS_SUCCESS] + batch,
                ).fetchall()
                for row in rows:
                    hits[row["chunk_id"]] = dict(row)
            return hits
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
