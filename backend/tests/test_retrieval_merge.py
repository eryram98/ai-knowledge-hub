"""merge_ranked_lists (F3): Reciprocal Rank Fusion of ranked retrieval lists.

Coach mode: Ethan wrote merge_ranked_lists; Claude wrote these tests against
its docstring.

Expected values follow the standard RRF formula from
G. V. Cormack, C. L. A. Clarke and S. Büttcher, "Reciprocal Rank Fusion
outperforms Condorcet and individual Rank Learning Methods", SIGIR 2009:

    RRFscore(d) = sum over input lists r containing d of 1 / (k + r(d))

where r(d) is d's 1-based rank in list r and k = 60 by default.
"""

import os
import sys
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from retrieval.retrieval_merge import merge_ranked_lists

KB_A = "hw_datasheets"
KB_B = "it_policies"
FUSED_FIELDS = {"chunk_id", "fused_score", "sources", "text", "document_id", "original_filename",
                "page_start", "page_end", "kb_id"}


def rrf(*ranks, k=60):
    """Expected fused score of a chunk with these ranks, one per list it appears in."""
    return sum(1.0 / (k + rank) for rank in ranks)


def hit(chunk_id, rank, source, kb_id=KB_A, score=None):
    """A Retriever-shaped hit; the document is the part of chunk_id before ':'."""
    document_id = chunk_id.split(":")[0]
    return {
        "chunk_id": chunk_id, "rank": rank, "score": score if score is not None else 1.0 / rank,
        "source": source, "text": "text of " + chunk_id, "document_id": document_id,
        "original_filename": document_id + ".pdf", "page_start": rank, "page_end": rank, "kb_id": kb_id,
    }


def ranked(source, chunk_ids, kb_id=KB_A):
    """A ranked list in which chunk_ids[i] has rank i + 1."""
    return [hit(chunk_id, i + 1, source, kb_id) for i, chunk_id in enumerate(chunk_ids)]


class TestMergeRankedLists(unittest.TestCase):
    def assertScores(self, merged, expected):
        """expected: [(chunk_id, fused_score)] in output order."""
        self.assertEqual([item["chunk_id"] for item in merged], [chunk_id for chunk_id, _score in expected])
        for item, (_chunk_id, score) in zip(merged, expected):
            self.assertAlmostEqual(item["fused_score"], score, places=12)

    def test_chunk_in_both_lists_outranks_chunks_in_one_list(self):
        vector = ranked("vector", ["d1:v1", "d1:both", "d1:v3"])
        keyword = ranked("keyword", ["d1:k1", "d1:k2", "d1:both"])
        merged = merge_ranked_lists([vector, keyword])
        # d1:both is only 2nd and 3rd in its lists, but 1/62 + 1/63 > 1/61.
        self.assertScores(merged, [
            ("d1:both", rrf(2, 3)),
            ("d1:k1", rrf(1)),  # ties with d1:v1; chunk_id ascending breaks the tie
            ("d1:v1", rrf(1)),
            ("d1:k2", rrf(2)),
            ("d1:v3", rrf(3)),
        ])

    def test_chunk_in_only_one_list_is_included(self):
        vector = ranked("vector", ["d1:a", "d1:shared"])
        keyword = ranked("keyword", ["d1:shared"])
        merged = merge_ranked_lists([vector, keyword])
        self.assertScores(merged, [("d1:shared", rrf(2, 1)), ("d1:a", rrf(1))])
        only_vector = merged[1]
        self.assertEqual(only_vector["sources"], [{"source": "vector", "kb_id": KB_A, "rank": 1, "score": 1.0}])

    def test_duplicates_merge_into_one_result_recording_both_sources(self):
        vector = [hit("d1:x", 1, "vector", score=0.91), hit("d1:y", 2, "vector", score=0.80)]
        keyword = [hit("d1:y", 1, "keyword", score=7.5), hit("d1:x", 4, "keyword", score=2.25)]
        merged = merge_ranked_lists([vector, keyword])
        self.assertEqual(len(merged), 2)
        self.assertEqual(len({item["chunk_id"] for item in merged}), 2)
        by_id = {item["chunk_id"]: item for item in merged}
        self.assertEqual(by_id["d1:x"]["sources"], [
            {"source": "vector", "kb_id": KB_A, "rank": 1, "score": 0.91},
            {"source": "keyword", "kb_id": KB_A, "rank": 4, "score": 2.25},
        ])
        self.assertEqual(by_id["d1:y"]["sources"], [
            {"source": "vector", "kb_id": KB_A, "rank": 2, "score": 0.80},
            {"source": "keyword", "kb_id": KB_A, "rank": 1, "score": 7.5},
        ])
        self.assertAlmostEqual(by_id["d1:x"]["fused_score"], rrf(1, 4), places=12)
        self.assertAlmostEqual(by_id["d1:y"]["fused_score"], rrf(2, 1), places=12)
        # The chunk fields are carried over unchanged.
        x = by_id["d1:x"]
        self.assertEqual(set(x), FUSED_FIELDS)
        self.assertEqual((x["text"], x["document_id"], x["original_filename"], x["kb_id"]),
                         ("text of d1:x", "d1", "d1.pdf", KB_A))
        self.assertEqual((x["page_start"], x["page_end"]), (1, 1))

    def test_sorted_by_fused_score_with_chunk_id_tie_break(self):
        vector = ranked("vector", ["d2:zeta", "d1:mid", "d1:alpha"])
        keyword = ranked("keyword", ["d1:alpha", "d2:beta"])
        merged = merge_ranked_lists([vector, keyword])
        self.assertScores(merged, [
            ("d1:alpha", rrf(3, 1)),
            ("d2:zeta", rrf(1)),
            ("d1:mid", rrf(2)),  # ties with d2:beta at 1/62
            ("d2:beta", rrf(2)),
        ])
        scores = [item["fused_score"] for item in merged]
        self.assertEqual(scores, sorted(scores, reverse=True))
        # Same input in the other list order: same output order.
        self.assertEqual([item["chunk_id"] for item in merge_ranked_lists([keyword, vector])],
                         [item["chunk_id"] for item in merged])

    def test_top_n_is_respected(self):
        vector = ranked("vector", ["d1:a", "d1:b", "d1:c", "d1:d"])
        keyword = ranked("keyword", ["d1:e", "d1:a"])
        merged = merge_ranked_lists([vector, keyword], top_n=3)
        self.assertScores(merged, [("d1:a", rrf(1, 2)), ("d1:e", rrf(1)), ("d1:b", rrf(2))])
        self.assertEqual(len(merge_ranked_lists([vector, keyword], top_n=10)), 5)
        self.assertEqual(len(merge_ranked_lists([vector, keyword])), 5)  # default top_n=10
        many = ranked("vector", ["d1:{0:02d}".format(i) for i in range(15)])
        self.assertEqual(len(merge_ranked_lists([many])), 10)

    def test_empty_lists(self):
        self.assertEqual(merge_ranked_lists([]), [])
        self.assertEqual(merge_ranked_lists([[], []]), [])
        merged = merge_ranked_lists([[], ranked("keyword", ["d1:a"])])
        self.assertScores(merged, [("d1:a", rrf(1))])

    def test_lists_from_two_kbs(self):
        lists = [
            ranked("vector", ["it:policy", "it:vpn"], kb_id=KB_B),
            ranked("keyword", ["it:policy"], kb_id=KB_B),
            ranked("vector", ["hw:gpio", "hw:power"], kb_id=KB_A),
            ranked("keyword", ["hw:power", "hw:gpio"], kb_id=KB_A),
        ]
        merged = merge_ranked_lists(lists)
        self.assertScores(merged, [
            ("it:policy", rrf(1, 1)),
            ("hw:gpio", rrf(1, 2)),  # ties with hw:power; "hw:gpio" < "hw:power"
            ("hw:power", rrf(2, 1)),
            ("it:vpn", rrf(2)),
        ])
        by_id = {item["chunk_id"]: item for item in merged}
        for chunk_id, kb_id in (("it:policy", KB_B), ("it:vpn", KB_B), ("hw:gpio", KB_A), ("hw:power", KB_A)):
            self.assertEqual(by_id[chunk_id]["kb_id"], kb_id)
            self.assertEqual({source["kb_id"] for source in by_id[chunk_id]["sources"]}, {kb_id})
        self.assertEqual([(s["source"], s["rank"]) for s in by_id["hw:power"]["sources"]],
                         [("vector", 2), ("keyword", 1)])

    def test_k_changes_scores_as_the_formula_says(self):
        vector = ranked("vector", ["d1:a", "d1:b"])
        keyword = ranked("keyword", ["d1:b"])
        self.assertScores(merge_ranked_lists([vector, keyword], k=1),
                          [("d1:b", rrf(2, 1, k=1)), ("d1:a", rrf(1, k=1))])
        self.assertScores(merge_ranked_lists([vector, keyword]),
                          [("d1:b", rrf(2, 1)), ("d1:a", rrf(1))])


class TestMergeArgumentValidation(unittest.TestCase):
    def setUp(self):
        self.lists = [ranked("vector", ["d1:a", "d1:b"]), ranked("keyword", ["d1:b"])]

    def test_k_must_be_positive(self):
        for k in (0, 0.0, -1, -0.5, None, "abc"):
            with self.subTest(k=k):
                with self.assertRaises(ValueError):
                    merge_ranked_lists(self.lists, k=k)
                with self.assertRaises(ValueError):
                    merge_ranked_lists([], k=k)  # checked even when there is nothing to merge
        merged = merge_ranked_lists(self.lists, k=0.5)  # a positive non-integer k is allowed
        self.assertEqual([item["chunk_id"] for item in merged], ["d1:b", "d1:a"])
        self.assertAlmostEqual(merged[0]["fused_score"], rrf(2, 1, k=0.5), places=12)

    def test_top_n_must_be_positive(self):
        for top_n in (0, -1, -10, None, "ten"):
            with self.subTest(top_n=top_n):
                with self.assertRaises(ValueError):
                    merge_ranked_lists(self.lists, top_n=top_n)
                with self.assertRaises(ValueError):
                    merge_ranked_lists([], top_n=top_n)
        self.assertEqual(len(merge_ranked_lists(self.lists, top_n=1)), 1)

    def test_top_n_must_be_an_integer(self):
        # The docstring says "a positive integer": a float, a numeric string or a bool is
        # rejected, not truncated or converted.
        for top_n in (2.5, "3", True):
            with self.subTest(top_n=top_n):
                with self.assertRaises(ValueError):
                    merge_ranked_lists(self.lists, top_n=top_n)


if __name__ == "__main__":
    unittest.main()
