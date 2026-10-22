"""Seed the dev knowledge hub from data/corpus/<kb_id>/ through the HTTP API (F6).

Wipes backend/instance/ (SQLite DB, Chroma, uploads) after asking, starts the API
as a child process, uploads every file of each KB folder, waits until every
accepted document is success or failed, prints a summary and stops the API.

    .venv\\Scripts\\python scripts\\seed_corpus.py            (asks before wiping)
    .venv\\Scripts\\python scripts\\seed_corpus.py --no-wipe --api-url http://127.0.0.1:8000
        (seed an API that is already running, without wiping or starting anything)

Exit code 1 when a document ends `failed`, the API can't be reached, or you decline the wipe.
A file the API rejects (for example one over the size limit) is listed but doesn't fail the run.
"""

import argparse
import mimetypes
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo_common
from demo_common import ApiClient, ApiClientError

ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md")
POLL_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 900.0
API_START_TIMEOUT_SECONDS = 60.0
DB_FILE_NAMES = ("ingestion.sqlite3", "ingestion.sqlite3-wal", "ingestion.sqlite3-shm")


def discover_corpus(corpus_dir):
    """{kb_id: [absolute file paths]} for every subfolder, files sorted by name; other extensions skipped."""
    corpus = {}
    for kb_id in sorted(os.listdir(corpus_dir)):
        kb_dir = os.path.join(corpus_dir, kb_id)
        if not os.path.isdir(kb_dir):
            continue
        names = [name for name in sorted(os.listdir(kb_dir))
                 if os.path.isfile(os.path.join(kb_dir, name)) and name.lower().endswith(ALLOWED_EXTENSIONS)]
        corpus[kb_id] = [os.path.join(kb_dir, name) for name in names]
    return corpus


def api_is_up(client):
    try:
        client.list_kbs()
        return True
    except ApiClientError as exc:
        return exc.kind not in ("connection", "timeout")


def wipe_instance(instance_dir):
    """Delete the dev DB (with its WAL files), the Chroma directory and the uploads. Returns what was removed."""
    removed = []
    for name in DB_FILE_NAMES:
        path = os.path.join(instance_dir, name)
        if os.path.exists(path):
            os.remove(path)
            removed.append(name)
    for name in ("chroma", "uploads"):
        path = os.path.join(instance_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
            removed.append(name + "/")
    return removed


def upload_kb(client, kb_id, paths):
    """Upload one KB's files as a batch. Returns [(file_name, document_id or None, error text or None)]."""
    files = []
    for path in paths:
        with open(path, "rb") as handle:
            files.append((os.path.basename(path), handle.read(), mimetypes.guess_type(path)[0]))
    response = client.upload(kb_id, files)
    results = []
    # The service returns one entry per input, in order; rejected entries carry no file name.
    for (name, _content, _mime), entry in zip(files, response["files"]):
        if entry["status"] == "accepted":
            results.append((name, entry["document_id"], None))
        else:
            error = entry.get("error") or {}
            results.append((name, None, "{0}: {1}".format(error.get("code", "rejected"), error.get("message", ""))))
    return results


def wait_for_documents(client, document_ids, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, poll_seconds=POLL_SECONDS,
                       sleep=time.sleep, clock=time.monotonic):
    """Poll until every document is success or failed. Returns {document_id: status record}. Raises TimeoutError."""
    if not document_ids:
        return {}
    deadline = clock() + timeout_seconds
    while True:
        batch = client.document_statuses(document_ids)
        if batch["is_complete"]:
            return {document["document_id"]: document for document in batch["documents"]}
        if clock() >= deadline:
            raise TimeoutError("{0} of {1} documents still not finished after {2:.0f} s".format(
                batch["total"] - batch["completed"], batch["total"], timeout_seconds))
        sleep(poll_seconds)


def seed(client, corpus, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, poll_seconds=POLL_SECONDS, out=print):
    """Upload every KB's files, wait for each, print a summary. Returns the list of per-file rows."""
    started = time.monotonic()
    rows = []
    for kb_id, paths in corpus.items():
        if not paths:
            out("{0}: no files".format(kb_id))
            continue
        out("{0}: uploading {1} file(s)".format(kb_id, len(paths)))
        for name, document_id, error in upload_kb(client, kb_id, paths):
            rows.append({"kb_id": kb_id, "file": name, "document_id": document_id,
                         "status": "rejected" if error else None, "detail": error})
    accepted = [row["document_id"] for row in rows if row["document_id"]]
    out("waiting for {0} accepted document(s) to finish".format(len(accepted)))
    finished = wait_for_documents(client, accepted, timeout_seconds, poll_seconds)
    for row in rows:
        if row["document_id"]:
            record = finished[row["document_id"]]
            row["status"] = record["ingestion_status"]
            if record["ingestion_status"] != "success":
                row["detail"] = "{0}: {1}".format(record.get("failure_code"), record.get("failure_reason"))
    print_summary(rows, time.monotonic() - started, out)
    return rows


def print_summary(rows, elapsed_seconds, out=print):
    out("")
    out("Seed summary")
    for row in rows:
        line = "  {0:<14} {1:<9} {2}".format(row["kb_id"], row["status"], row["file"])
        out(line + ("  <- " + row["detail"] if row["detail"] else ""))
    for kb_id in sorted({row["kb_id"] for row in rows}):
        kb_rows = [row for row in rows if row["kb_id"] == kb_id]
        indexed = sum(row["status"] == "success" for row in kb_rows)
        out("  {0}: {1} of {2} indexed".format(kb_id, indexed, len(kb_rows)))
    out("  elapsed {0:.0f} s".format(elapsed_seconds))


def exit_code(rows):
    return 1 if any(row["status"] == "failed" for row in rows) else 0


def start_api(port, repo_root=demo_common.REPO_ROOT):
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.api_app:create_app", "--factory",
         "--app-dir", os.path.join("backend", "app"), "--port", str(port), "--log-level", "warning"],
        cwd=repo_root)


def wait_for_api(client, process, timeout_seconds=API_START_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("the API process exited with code {0}".format(process.returncode))
        if api_is_up(client):
            return
        time.sleep(1.0)
    raise TimeoutError("the API did not answer within {0:.0f} s".format(timeout_seconds))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="don't ask before wiping backend/instance/")
    parser.add_argument("--no-wipe", action="store_true",
                        help="seed an already running API at --api-url; wipe nothing and start nothing")
    parser.add_argument("--api-url", default=demo_common.DEFAULT_API_URL)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="seconds to wait for indexing")
    args = parser.parse_args(argv)

    corpus = discover_corpus(demo_common.CORPUS_DIR)
    if not any(corpus.values()):
        print("No files in {0}. Download the corpus first (see data/corpus/MANIFEST.md).".format(
            demo_common.CORPUS_DIR))
        return 1
    client = ApiClient(args.api_url)

    if args.no_wipe:
        if not api_is_up(client):
            print("No API answers at {0}.".format(args.api_url))
            return 1
        return exit_code(seed(client, corpus, args.timeout))

    if api_is_up(client):
        print("An API is already running at {0}. Stop it first: it holds the DB and Chroma open.".format(
            args.api_url))
        return 1
    print("This DELETES the dev DB, Chroma index and uploads in {0}".format(demo_common.INSTANCE_DIR))
    if not demo_common.confirm("Wipe and re-seed?", args.yes):
        print("Cancelled; nothing was changed.")
        return 1
    print("removed: " + (", ".join(wipe_instance(demo_common.INSTANCE_DIR)) or "nothing"))
    process = start_api(int(args.api_url.rsplit(":", 1)[-1]))
    try:
        wait_for_api(client, process)
        rows = seed(client, corpus, args.timeout)
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
    return exit_code(rows)


if __name__ == "__main__":
    sys.exit(main())
