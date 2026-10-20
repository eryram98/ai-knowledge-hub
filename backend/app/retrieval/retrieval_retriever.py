"""Per-KB vector and keyword search returning two separate ranked lists (F3).

The lists are not merged here: retrieval_merge.merge_ranked_lists does that.
Chunk text and source metadata come from SQLite, and every hit belongs to a
document in success.
"""

from ingestion.ingestion_chunking import FixedSizeCharChunker
from retrieval.retrieval_config import DEFAULT_RETRIEVAL_TOP_K

SOURCE_VECTOR = "vector"
SOURCE_KEYWORD = "keyword"
BASELINE_CHUNKER = FixedSizeCharChunker.name


class Retriever(object):
    """Searches one or more KBs with the vector index and the BM25 index.

    A hit is a dict: chunk_id, rank (1-based, contiguous), score (cosine
    similarity for vector hits, the raw BM25 score for keyword hits), source
    ("vector" or "keyword"), text, document_id, original_filename,
    page_start, page_end (None for TXT and MD), kb_id.
    """

    def __init__(self, embedder, vector_index, keyword_index, artifact_repository, top_k=DEFAULT_RETRIEVAL_TOP_K):
        self.embedder = embedder
        self.vector_index = vector_index
        self.keyword_index = keyword_index
        self.artifact_repository = artifact_repository
        self.top_k = top_k

    def retrieve(self, kb_id, query, chunker=BASELINE_CHUNKER, top_k=None):
        """Return {"vector": [hits], "keyword": [hits]} for one KB."""
        return self.retrieve_many([kb_id], query, chunker=chunker, top_k=top_k)[kb_id]

    def retrieve_many(self, kb_ids, query, chunker=BASELINE_CHUNKER, top_k=None):
        """Return {kb_id: {"vector": [hits], "keyword": [hits]}}; the query is embedded once."""
        top_k = self.top_k if top_k is None else top_k
        # embed_query adds the bge query instruction; passages never get it.
        query_vector = self.embedder.embed_query(query)
        results = {}
        for kb_id in kb_ids:
            success_ids = self.artifact_repository.list_success_document_ids(kb_id)
            vector_pairs = self.vector_index.query(kb_id, query_vector, chunker, top_k, document_ids=success_ids)
            keyword_pairs = self.keyword_index.query(kb_id, query, chunker, top_k)
            results[kb_id] = {
                SOURCE_VECTOR: self._hits(vector_pairs, SOURCE_VECTOR, kb_id),
                SOURCE_KEYWORD: self._hits(keyword_pairs, SOURCE_KEYWORD, kb_id),
            }
        return results

    def _hits(self, pairs, source, kb_id):
        """Attach SQLite text and metadata to [(chunk_id, score)], dropping chunks it can't cite.

        A chunk can vanish or its document leave success between the index
        query and this lookup (re-processing, a failure); such hits are dropped
        and the remaining ones re-ranked 1..n.
        """
        rows = self.artifact_repository.get_chunk_hits([chunk_id for chunk_id, _score in pairs])
        hits = []
        for chunk_id, score in pairs:
            row = rows.get(chunk_id)
            if row is None or row["kb_id"] != kb_id:
                continue
            hits.append({
                "chunk_id": chunk_id,
                "rank": len(hits) + 1,
                "score": score,
                "source": source,
                "text": row["text"],
                "document_id": row["document_id"],
                "original_filename": row["original_filename"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "kb_id": kb_id,
            })
        return hits
