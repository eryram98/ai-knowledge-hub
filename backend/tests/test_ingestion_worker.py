import os
import sys
import unittest
from threading import Event

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue
from ingestion.ingestion_worker import run_worker, start_background_worker


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


class RecordingStatusRepository(object):
    """Stands in for the SQLite repository; records status changes in order."""

    def __init__(self, events):
        self.events = events

    def mark_processing(self, document_id):
        self.events.append(("processing", document_id))
        return True

    def mark_success(self, document_id):
        self.events.append(("success", document_id))

    def mark_failed(self, document_id, reason, error_code):
        self.events.append(("failed", document_id))


class TestOnFinishedHook(unittest.TestCase):
    def run_jobs(self, process, on_finished, events, document_ids):
        queue = InMemoryIngestionJobQueue()
        for document_id in document_ids:
            queue.enqueue(IngestionJob(document_id, document_id + ".txt"))
        thread, stop = start_background_worker(
            queue, process, status_repository=RecordingStatusRepository(events), on_finished=on_finished,
        )
        try:
            queue.join()
        finally:
            stop.set()
            thread.join(timeout=2)

    def test_runs_after_the_status_change_for_success_and_failure(self):
        events = []

        def process(job):
            if job.document_id == "bad":
                raise RuntimeError("boom")

        def on_finished(job, status):
            events.append(("hook", job.document_id, status))

        with self.assertLogs("ingestion.ingestion_worker", level="ERROR"):
            self.run_jobs(process, on_finished, events, ["good", "bad"])
        self.assertEqual(events, [
            ("processing", "good"), ("success", "good"), ("hook", "good", "success"),
            ("processing", "bad"), ("failed", "bad"), ("hook", "bad", "failed"),
        ])

    def test_hook_error_is_logged_and_isolated(self):
        events = []

        def on_finished(job, status):
            events.append(("hook", job.document_id))
            raise RuntimeError("hook broke")

        with self.assertLogs("ingestion.ingestion_worker", level="ERROR") as logs:
            self.run_jobs(lambda job: None, on_finished, events, ["first", "second"])
        self.assertEqual([e for e in events if e[0] == "success"], [("success", "first"), ("success", "second")])
        self.assertEqual([e for e in events if e[0] == "hook"], [("hook", "first"), ("hook", "second")])
        self.assertTrue(any("on_finished hook failed: first" in line for line in logs.output), logs.output)
        # A hook error is not a processing failure.
        self.assertNotIn(("failed", "first"), events)

    def test_non_callable_hook_is_rejected(self):
        with self.assertRaises(TypeError):
            run_worker(InMemoryIngestionJobQueue(), lambda job: None, Event(), on_finished="nope")


if __name__ == "__main__":
    unittest.main()
