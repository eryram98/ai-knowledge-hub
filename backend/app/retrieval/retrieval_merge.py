"""Hybrid merge of ranked retrieval lists with Reciprocal Rank Fusion (F3, coach mode: Ethan implements)."""

DEFAULT_RRF_K = 60
DEFAULT_TOP_N = 10


def merge_ranked_lists(ranked_lists, k=DEFAULT_RRF_K, top_n=DEFAULT_TOP_N):
    """Fuse several ranked lists of hits into one list ordered by Reciprocal Rank Fusion score.

    Args:
        ranked_lists: a list of ranked lists. Each ranked list is a list of hit
            dicts as returned by Retriever (retrieval_retriever.py), for example
            the vector list and the keyword list of one or more KBs:
                {
                    "chunk_id": str,           # unique across KBs
                    "rank": int,               # 1-based position in its own list
                    "score": float,            # raw score from that list's retriever
                    "source": str,             # "vector" or "keyword"
                    "text": str,
                    "document_id": str,
                    "original_filename": str | None,
                    "page_start": int | None,
                    "page_end": int | None,
                    "kb_id": str,
                }
            A list may be empty, and ranked_lists itself may be empty. A chunk
            appears at most once within one list, but may appear in several
            lists.
        k: the RRF smoothing constant (Cormack et al., 2009 use 60). A
            positive number.
        top_n: the maximum number of fused hits to return. A positive integer.

    Returns:
        A list of at most top_n fused hit dicts, one per distinct chunk_id
        across all input lists:
            {
                "chunk_id": str,
                "fused_score": float,      # the chunk's RRF score over all lists
                "sources": [               # one entry per input list the chunk
                    {                      # appeared in, in input-list order
                        "source": str,     # that list's "source"
                        "kb_id": str,
                        "rank": int,       # the chunk's rank in that list
                        "score": float,    # the chunk's raw score in that list
                    },
                    ...
                ],
                "text": str,
                "document_id": str,
                "original_filename": str | None,
                "page_start": int | None,
                "page_end": int | None,
                "kb_id": str,
            }
        Sorted by fused_score, highest first. Hits with equal fused_score are
        ordered by chunk_id ascending, so the output is deterministic. Empty
        input (no lists, or only empty lists) returns [].

    Reference:
        G. V. Cormack, C. L. A. Clarke and S. Büttcher, "Reciprocal Rank Fusion
        outperforms Condorcet and individual Rank Learning Methods", SIGIR 2009.
    """
    raise NotImplementedError("merge_ranked_lists is not implemented yet")
