"""BM25 keyword index per (KB, chunker), built from the chunks in SQLite (F2).

SQLite is the source of truth, so nothing is persisted here: each index is
built lazily on first query and cached until invalidate(kb_id). The corpus is
the chunks of documents in success only (SQLiteArtifactRepository.list_kb_chunks).
"""

import re
import threading

from rank_bm25 import BM25Okapi

# Letters/digits, joined by internal ".", "-" or "_": keeps gpio17, ac-2, 3.3v,
# rp2040 and uart_tx whole, and drops punctuation around a token ("(gpio17)," -> gpio17).
_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[.\-_][^\W_]+)*")


def tokenize(text):
    """Lowercased tokens that keep technical identifiers intact."""
    if not text:
        return []
    return _TOKEN_PATTERN.findall(text.lower())


class _KbIndex(object):
    def __init__(self, chunk_ids, token_sets, bm25):
        self.chunk_ids = chunk_ids
        self.token_sets = token_sets
        self.bm25 = bm25  # None when the corpus has no tokens


class BM25KeywordIndex(object):
    """Lazily built, cached BM25 indexes. Safe to share between threads."""

    def __init__(self, chunk_source):
        # chunk_source.list_kb_chunks(kb_id, chunker) -> [(chunk_id, text)]
        self._chunk_source = chunk_source
        self._indexes = {}
        self._lock = threading.Lock()

    def invalidate(self, kb_id):
        """Drop every chunker's index for this KB; the next query rebuilds it."""
        with self._lock:
            for key in [key for key in self._indexes if key[0] == kb_id]:
                del self._indexes[key]

    def _get_index(self, kb_id, chunker):
        # Built under the lock, so an invalidate() during a build can't be lost.
        with self._lock:
            index = self._indexes.get((kb_id, chunker))
            if index is None:
                rows = self._chunk_source.list_kb_chunks(kb_id, chunker)
                tokenized = [tokenize(text) for _chunk_id, text in rows]
                # BM25Okapi divides by the corpus size and the average length.
                has_tokens = any(tokenized)
                index = _KbIndex(
                    [chunk_id for chunk_id, _text in rows],
                    [frozenset(tokens) for tokens in tokenized],
                    BM25Okapi(tokenized) if has_tokens else None,
                )
                self._indexes[(kb_id, chunker)] = index
            return index

    def query(self, kb_id, text, chunker, top_k):
        """Return up to top_k [(chunk_id, score)], best first. Chunks with no query term are left out.

        Matches are decided by term overlap, not score > 0: BM25Okapi's IDF is
        negative for a term in most chunks of a small KB, so a real match can
        score below zero.
        """
        if top_k <= 0:
            return []
        tokens = tokenize(text)
        index = self._get_index(kb_id, chunker)
        if not tokens or index.bm25 is None:
            return []
        query_terms = frozenset(tokens)
        scores = index.bm25.get_scores(tokens)
        ranked = sorted(
            (i for i, terms in enumerate(index.token_sets) if terms & query_terms),
            key=lambda i: (-scores[i], i),
        )
        return [(index.chunk_ids[i], float(scores[i])) for i in ranked[:top_k]]
