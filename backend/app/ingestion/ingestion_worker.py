"""Background worker entrypoint. Actual document processing is injected."""

import argparse
import logging
from threading import Event, Thread

from ingestion.ingestion_job_queue import IngestionJob, InMemoryIngestionJobQueue

LOGGER = logging.getLogger(__name__)


def run_worker(job_queue, process_job, stop_event, poll_interval=0.1, status_repository=None):
    """Consume jobs until stopped; finish any job already in progress.

    A processing failure is logged and does not stop subsequent jobs. This
    persists processing status when a repository is supplied. Queue-only demos
    may omit it. Normal callback return means success; callbacks must raise
    an exception on failure. Automatic retries are not implemented.
    """
    if not callable(process_job):
        raise TypeError("process_job must be callable")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")
    while not stop_event.is_set():
        job = job_queue.dequeue(timeout=poll_interval)
        if job is None:
            continue
        try:
            if status_repository is not None:
                if not status_repository.mark_processing(job.document_id):
                    LOGGER.warning("Skipping already claimed document: %s", job.document_id)
                    continue
            try:
                process_job(job)
            except Exception as exc:
                LOGGER.exception("Document processing failed: %s", job.document_id)
                if status_repository is not None:
                    reason = "{0}: {1}".format(type(exc).__name__, str(exc) or "Processing failed")
                    status_repository.mark_failed(job.document_id, reason)
            else:
                if status_repository is not None:
                    status_repository.mark_success(job.document_id)
        except Exception:
            LOGGER.exception("Ingestion job failed: %s", job.document_id)
        finally:
            job_queue.task_done()


def start_background_worker(job_queue, process_job, stop_event=None, status_repository=None):
    """Return (thread, stop_event). Caller owns shutdown and thread.join().

    For application jobs, pass the upload service's status_repository so both
    components use the same database. Omitting it enables queue-only operation.
    """
    if not callable(process_job):
        raise TypeError("process_job must be callable")
    if stop_event is None:
        stop_event = Event()
    thread = Thread(
        target=run_worker,
        args=(job_queue, process_job, stop_event),
        kwargs={"status_repository": status_repository},
        name="ingestion-worker",
    )
    thread.start()
    return thread, stop_event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Run a queue demo; no file ingestion")
    args = parser.parse_args()
    if not args.demo:
        parser.error("Use --demo; application processing is not implemented yet")
    job_queue = InMemoryIngestionJobQueue()

    def show_job(job):
        print("Queue demo handled {0}; no extraction performed".format(job.document_id))

    thread, stop_event = start_background_worker(job_queue, show_job)
    try:
        job_queue.enqueue(IngestionJob("demo-document", "demo.txt"))
        job_queue.join()
    finally:
        stop_event.set()
        thread.join()


if __name__ == "__main__":
    main()
