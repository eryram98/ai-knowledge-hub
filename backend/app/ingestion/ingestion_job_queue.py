"""Queue contract and a thread-safe, process-local implementation (Python 3.6+)."""

from abc import ABC, abstractmethod
from queue import Empty, Queue


class IngestionJob(object):
    """One document's work; document_id comes from the upload intake service."""

    def __init__(self, document_id, temp_file_path, metadata=None):
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("document_id must be a non-empty string")
        if not isinstance(temp_file_path, str) or not temp_file_path.strip():
            raise ValueError("temp_file_path must be a non-empty string")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")
        self.document_id = document_id
        self.temp_file_path = temp_file_path
        self.metadata = dict(metadata or {})


class IngestionJobQueue(ABC):
    """Implementations must support timed reads and completion accounting."""

    @abstractmethod
    def enqueue(self, job):
        raise NotImplementedError

    @abstractmethod
    def dequeue(self, timeout=0.1):
        """Return a job, or None if no job arrives before the timeout."""
        raise NotImplementedError

    @abstractmethod
    def task_done(self):
        """Mark a previously dequeued job as finished, including failed work."""
        raise NotImplementedError

    @abstractmethod
    def join(self):
        """Wait until all submitted jobs have finished."""
        raise NotImplementedError


class InMemoryIngestionJobQueue(IngestionJobQueue):
    """FIFO queue shared by threads, not by separate processes; not durable."""

    def __init__(self):
        self._queue = Queue()

    def enqueue(self, job):
        if not isinstance(job, IngestionJob):
            raise TypeError("job must be an IngestionJob")
        self._queue.put(job)

    def dequeue(self, timeout=0.1):
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def task_done(self):
        self._queue.task_done()

    def join(self):
        self._queue.join()
