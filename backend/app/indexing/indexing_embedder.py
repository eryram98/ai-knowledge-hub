"""Text embeddings for indexing and retrieval (F2): bge-small through sentence-transformers.

The model loads lazily on first use, so importing this module or starting the
API never loads torch. Tests inject a fake model factory and never download
the model.
"""

import threading
from abc import ABC, abstractmethod

# Code constants, not .env: changing the model means rebuilding every Chroma
# collection (the vector index refuses to mix models).
BGE_SMALL_MODEL_NAME = "BAAI/bge-small-en-v1.5"
BGE_SMALL_DIMENSION = 384
# bge v1.5 retrieval instruction. It goes on queries only, never on passages.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DEFAULT_ENCODE_BATCH_SIZE = 32


class Embedder(ABC):
    """Turns passages and queries into vectors of one fixed dimension."""

    model_name = None
    dimension = None

    @abstractmethod
    def embed_documents(self, texts):
        """Return one vector (list of floats) per passage, in order."""

    @abstractmethod
    def embed_query(self, text):
        """Return one vector (list of floats) for a search query."""


def _load_sentence_transformer(model_name):
    # Imported here so torch only loads when the model is first needed.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device="cpu")


class BgeSmallEmbedder(Embedder):
    """BAAI/bge-small-en-v1.5 on CPU, with normalized vectors (cosine = dot product).

    One instance is shared by the worker thread and API threads. The model is
    loaded once behind a lock, and encode calls are serialized because Hugging
    Face fast tokenizers raise "Already borrowed" when used concurrently.
    """

    model_name = BGE_SMALL_MODEL_NAME
    dimension = BGE_SMALL_DIMENSION

    def __init__(self, model_factory=None, batch_size=DEFAULT_ENCODE_BATCH_SIZE):
        self._model_factory = model_factory if model_factory is not None else _load_sentence_transformer
        self._batch_size = batch_size
        self._model = None
        self._load_lock = threading.Lock()
        self._encode_lock = threading.Lock()

    def _get_model(self):
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    self._model = self._model_factory(self.model_name)
        return self._model

    def _encode(self, texts):
        model = self._get_model()
        with self._encode_lock:
            vectors = model.encode(
                list(texts), batch_size=self._batch_size, normalize_embeddings=True,
                convert_to_numpy=True, show_progress_bar=False,
            )
        return [[float(value) for value in vector] for vector in vectors]

    def embed_documents(self, texts):
        texts = list(texts)
        if not texts:
            return []
        return self._encode(texts)

    def embed_query(self, text):
        return self._encode([BGE_QUERY_PREFIX + text])[0]
