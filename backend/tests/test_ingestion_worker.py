import os
import sys
import unittest
from threading import Event

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_worker import start_background_worker


class TestIngestionQueueAndWorker(unittest.TestCase):
    def test_queue_fifo_and_timeout(self):
        queue = InMemoryIngestionJobQueue()
        self.assertIsNone(queue.dequeue(timeout=0))
        first = IngestionJob("first", "first.txt")
        second = IngestionJob("second", "second.md")
        queue.enqueue(first)
        queue.enqueue(second)
        self.assertIs(queue.dequeue(timeout=0), first)
        queue.task_done()
        self.assertIs(queue.dequeue(timeout=0), second)
        queue.task_done()
        queue.join()

    def test_invalid_jobs_are_rejected(self):
        with self.assertRaises(ValueError):
            IngestionJob("", "file.txt")
        with self.assertRaises(ValueError):
            IngestionJob("doc", "")
        with self.assertRaises(TypeError):
            InMemoryIngestionJobQueue().enqueue({})

    def test_worker_handles_jobs_in_background_and_survives_failure(self):
        queue = InMemoryIngestionJobQueue()
        handled = []
        completed = Event()

        def process(job):
            handled.append(job.document_id)
            if job.document_id == "bad":
                raise RuntimeError("test failure")
            completed.set()

        queue.enqueue(IngestionJob("bad", "bad.txt"))
        queue.enqueue(IngestionJob("good", "good.txt"))
        with self.assertLogs("ingestion.ingestion_worker", level="ERROR") as logs:
            thread, stop = start_background_worker(queue, process)
            try:
                self.assertTrue(completed.wait(timeout=2))
            finally:
                stop.set()
                thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(handled, ["bad", "good"])
        self.assertIn("bad", logs.output[0])
        self.assertEqual(queue._queue.unfinished_tasks, 0)

    def test_idle_worker_stops(self):
        thread, stop = start_background_worker(InMemoryIngestionJobQueue(), lambda job: None)
        stop.set()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_invalid_processor_is_rejected_before_start(self):
        with self.assertRaises(TypeError):
            start_background_worker(InMemoryIngestionJobQueue(), None)


if __name__ == "__main__":
    unittest.main()
