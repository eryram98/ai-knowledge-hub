"""BgeSmallEmbedder with a mocked SentenceTransformer: prefixes, normalization, lazy single load."""

import os
import sys
import threading
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from indexing.indexing_embedder import (
    BGE_QUERY_PREFIX,
    BGE_SMALL_DIMENSION,
    BGE_SMALL_MODEL_NAME,
    BgeSmallEmbedder,
)


class FakeModel(object):
    """Records encode calls; fails if two calls overlap."""

    def __init__(self):
        self.calls = []
        self._busy = threading.Lock()

    def encode(self, texts, **kwargs):
        if not self._busy.acquire(blocking=False):
            raise RuntimeError("Already borrowed")
        try:
            self.calls.append((list(texts), kwargs))
            return [[float(len(text)), 0.0] for text in texts]
        finally:
            self._busy.release()


class CountingFactory(object):
    def __init__(self, delay_event=None):
        self.loads = []
        self.model = FakeModel()
        self.delay_event = delay_event

    def __call__(self, model_name):
        if self.delay_event is not None:
            self.delay_event.wait(2)
        self.loads.append(model_name)
        return self.model


class TestBgeSmallEmbedder(unittest.TestCase):
    def test_constants(self):
        embedder = BgeSmallEmbedder(model_factory=CountingFactory())
        self.assertEqual(embedder.model_name, BGE_SMALL_MODEL_NAME)
        self.assertEqual(embedder.dimension, BGE_SMALL_DIMENSION)

    def test_prefix_on_queries_only(self):
        factory = CountingFactory()
        embedder = BgeSmallEmbedder(model_factory=factory)
        embedder.embed_documents(["passage one", "passage two"])
        embedder.embed_query("what is gpio17")
        (passages, _), (queries, _) = factory.model.calls
        self.assertEqual(passages, ["passage one", "passage two"])
        self.assertEqual(queries, [BGE_QUERY_PREFIX + "what is gpio17"])

    def test_normalize_embeddings_is_passed(self):
        factory = CountingFactory()
        embedder = BgeSmallEmbedder(model_factory=factory)
        embedder.embed_documents(["a"])
        embedder.embed_query("b")
        for _texts, kwargs in factory.model.calls:
            self.assertIs(kwargs.get("normalize_embeddings"), True)

    def test_returns_plain_float_lists_in_order(self):
        embedder = BgeSmallEmbedder(model_factory=CountingFactory())
        self.assertEqual(embedder.embed_documents(["ab", "abcd"]), [[2.0, 0.0], [4.0, 0.0]])
        self.assertEqual(embedder.embed_documents([]), [])

    def test_no_load_at_construction(self):
        factory = CountingFactory()
        BgeSmallEmbedder(model_factory=factory)
        self.assertEqual(factory.loads, [])

    def test_one_load_and_no_overlapping_encodes_under_concurrency(self):
        release = threading.Event()
        factory = CountingFactory(delay_event=release)
        embedder = BgeSmallEmbedder(model_factory=factory)
        errors = []

        def work(i):
            try:
                embedder.embed_query("query {0}".format(i))
                embedder.embed_documents(["passage {0}".format(i)])
            except Exception as exc:  # collected and asserted below
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(errors, [])
        self.assertEqual(factory.loads, [BGE_SMALL_MODEL_NAME])
        self.assertEqual(len(factory.model.calls), 16)


if __name__ == "__main__":
    unittest.main()
