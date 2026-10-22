"""Run the evaluation set through POST /ask and report routing accuracy and hit@5 (F6).

    .venv\\Scripts\\python scripts\\run_eval.py            (API must be running; asks before the LLM calls)

Per question it prints the routed KBs against the expected ones, whether the expected source
document is among the first 5 sources, the latency and the tokens. The run is saved under
data/eval/runs/ (git-ignored) and one row is added to the Evaluation table in docs/PROGRESS.md.
Metrics follow docs/SPEC.md section 5.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo_common
from demo_common import ApiClient, ApiClientError

HIT_AT = 5
NO_KB = "none"
ROUTE_CALLS_PER_QUESTION = 1
ANSWER_CALLS_PER_ON_TOPIC_QUESTION = 1
TABLE_PLACEHOLDER_PREFIX = "| | | | | | | No runs yet"


def load_eval_set(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def expected_kbs(item):
    """The expected KB set: {} for "none", else a set of KB ids."""
    expected = item["expected_kb"]
    if expected == NO_KB:
        return set()
    return {expected} if isinstance(expected, str) else set(expected)


def expected_sources(item):
    source = item.get("expected_source")
    if source is None:
        return []
    return [source] if isinstance(source, str) else list(source)


def estimate_llm_calls(items):
    """Upper bound without retries: one routing call each, plus one answer call per on-topic question."""
    return sum(ROUTE_CALLS_PER_QUESTION + (ANSWER_CALLS_PER_ON_TOPIC_QUESTION if expected_kbs(i) else 0)
               for i in items)


def routing_correct(item, response):
    """The routed KB set equals the expected one. A fallback to every KB only counts if that is the expectation."""
    return set(response["kb_ids"]) == expected_kbs(item)


def hit_at_k(item, response, k=HIT_AT):
    """None for off-topic questions; else True when every expected source is among the first k sources."""
    wanted = expected_sources(item)
    if not wanted:
        return None
    found = {source["document"] for source in response["sources"][:k]}
    return all(name in found for name in wanted)


def total_tokens(response):
    usage = response.get("usage") or {}
    return (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)


def evaluate(client, items, clock=time.monotonic, out=print, now=datetime.now):
    """Ask every question once. Returns one result dict per question (errors are recorded, not raised)."""
    results = []
    for item in items:
        started = clock()
        result = {"id": item["id"], "question": item["question"], "expected_kb": item["expected_kb"],
                  "expected_source": item.get("expected_source"), "error": None,
                  "asked_at": now().strftime("%H:%M:%S")}
        try:
            response = client.ask(item["question"])
        except ApiClientError as exc:
            result.update(error="{0}: {1}".format(exc.code or exc.kind, exc.message), routed_kb=None,
                          routing_correct=False, hit=None if not expected_sources(item) else False, tokens=0,
                          latency_seconds=clock() - started, routing_fallback=False, no_answer=None, answer=None,
                          source_documents=[], models=[])
        else:
            result.update(
                routed_kb=response["kb_ids"], routing_correct=routing_correct(item, response),
                hit=hit_at_k(item, response), tokens=total_tokens(response), latency_seconds=clock() - started,
                routing_fallback=response["routing_fallback"], no_answer=response["no_answer"],
                answer=response["answer"], source_documents=[s["document"] for s in response["sources"][:HIT_AT]],
                models=sorted({c["model"] for c in (response.get("usage") or {}).get("calls", [])}))
        results.append(result)
        out(format_row(result))
    return results


def format_row(result):
    routed = "error" if result["routed_kb"] is None else ("+".join(result["routed_kb"]) or "none")
    hit = {None: "n/a", True: "hit", False: "MISS"}[result["hit"]]
    return "{0} {8}  route {1:<4} ({2:<28}) hit@{3} {4:<4} {5:>5.1f} s {6:>6} tok{7}".format(
        result["id"], "ok" if result["routing_correct"] else "WRONG", routed, HIT_AT, hit,
        result["latency_seconds"], result["tokens"], "  ERROR " + result["error"] if result["error"] else "",
        result["asked_at"])


def summarize(results):
    on_topic = [r for r in results if r["hit"] is not None]
    latencies = [r["latency_seconds"] for r in results]
    return {
        "questions": len(results),
        "routing_correct": sum(r["routing_correct"] for r in results),
        "routing_accuracy": sum(r["routing_correct"] for r in results) / len(results),
        "on_topic": len(on_topic),
        "hits": sum(1 for r in on_topic if r["hit"]),
        "hit_at_5": (sum(1 for r in on_topic if r["hit"]) / len(on_topic)) if on_topic else None,
        "total_tokens": sum(r["tokens"] for r in results),
        "median_latency_seconds": statistics.median(latencies),
        "max_latency_seconds": max(latencies),
        "errors": sum(1 for r in results if r["error"]),
        "first_asked_at": results[0]["asked_at"],
        "last_asked_at": results[-1]["asked_at"],
    }


def progress_row(summary, run_date, commit):
    hit = "n/a" if summary["hit_at_5"] is None else "{0:.0%} ({1}/{2})".format(
        summary["hit_at_5"], summary["hits"], summary["on_topic"])
    notes = "{0} tokens; latency median {1:.1f} s, max {2:.1f} s; asked {4}-{5} local{3}".format(
        summary["total_tokens"], summary["median_latency_seconds"], summary["max_latency_seconds"],
        "; {0} question(s) errored".format(summary["errors"]) if summary["errors"] else "",
        summary["first_asked_at"], summary["last_asked_at"])
    return "| {0} | {1} | {2} | {3:.0%} ({4}/{5}) | {6} | not run | {7} |".format(
        run_date, commit, summary["questions"], summary["routing_accuracy"], summary["routing_correct"],
        summary["questions"], hit, notes)


def add_progress_row(progress_text, row):
    """Insert row under the Evaluation numbers table header (newest first), dropping the 'No runs yet' line."""
    lines = progress_text.split("\n")
    header = next(i for i, line in enumerate(lines) if line.startswith("| Date | Commit | Eval set size"))
    lines = [line for line in lines if not line.startswith(TABLE_PLACEHOLDER_PREFIX)]
    lines.insert(header + 2, row)
    return "\n".join(lines)


def git_commit_label(repo_root=demo_common.REPO_ROOT):
    """Short HEAD hash, with -dirty when tracked files have uncommitted changes."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, capture_output=True,
                              text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return head + ("-dirty" if dirty else "")


def save_run(results, summary, commit, runs_dir=demo_common.EVAL_RUNS_DIR):
    os.makedirs(runs_dir, exist_ok=True)
    path = os.path.join(runs_dir, "eval_{0}.json".format(datetime.now().strftime("%Y%m%d_%H%M%S")))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"commit": commit, "summary": summary, "results": results}, handle, indent=2, ensure_ascii=False)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="don't ask before making the LLM calls")
    parser.add_argument("--api-url", default=demo_common.DEFAULT_API_URL)
    parser.add_argument("--eval-set", default=demo_common.EVAL_SET_PATH)
    parser.add_argument("--no-progress", action="store_true", help="don't add a row to docs/PROGRESS.md")
    args = parser.parse_args(argv)

    items = load_eval_set(args.eval_set)
    client = ApiClient(args.api_url)
    try:
        client.list_kbs()
    except ApiClientError as exc:
        print("The API at {0} didn't answer: {1}".format(args.api_url, exc.message))
        return 1
    calls = estimate_llm_calls(items)
    print("{0} questions through POST /ask: about {1} LLM calls (more if the provider retries).".format(
        len(items), calls))
    if not demo_common.confirm("Run?", args.yes):
        print("Cancelled; no LLM calls were made.")
        return 1

    results = evaluate(client, items)
    summary = summarize(results)
    commit = git_commit_label()
    print("")
    print("Routing accuracy: {0:.0%} ({1}/{2})".format(
        summary["routing_accuracy"], summary["routing_correct"], summary["questions"]))
    if summary["hit_at_5"] is not None:
        print("Hit@{0}: {1:.0%} ({2}/{3} on-topic questions)".format(
            HIT_AT, summary["hit_at_5"], summary["hits"], summary["on_topic"]))
    print("Total tokens: {0}; latency median {1:.1f} s, max {2:.1f} s".format(
        summary["total_tokens"], summary["median_latency_seconds"], summary["max_latency_seconds"]))
    print("Saved " + save_run(results, summary, commit, demo_common.EVAL_RUNS_DIR))
    if not args.no_progress:
        with open(demo_common.PROGRESS_PATH, encoding="utf-8", newline="") as handle:
            text = handle.read()
        newline = "\r\n" if "\r\n" in text else "\n"
        updated = add_progress_row(text.replace("\r\n", "\n"), progress_row(summary, date.today().isoformat(), commit))
        with open(demo_common.PROGRESS_PATH, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated.replace("\n", newline))
        print("Added a row to docs/PROGRESS.md")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
