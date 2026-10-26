"""run_eval: the metrics (routing accuracy, hit@5), call estimate, PROGRESS row and the ask-first path. No LLM."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import demo_common
import run_eval
from demo_common import ApiClientError

SINGLE = {"id": "q1", "question": "?", "expected_kb": "hw", "expected_source": "a.pdf", "expected_answer": "x"}
BOTH = {"id": "q2", "question": "?", "expected_kb": ["it", "hw"], "expected_source": ["p.pdf", "a.pdf"],
        "expected_answer": "x"}
OFF = {"id": "q3", "question": "?", "expected_kb": "none", "expected_source": None, "expected_answer": "x"}


def response(kb_ids, documents=(), fallback=False, tokens=(10, 5)):
    return {"kb_ids": list(kb_ids), "routing_fallback": fallback, "no_answer": False, "answer": "a",
            "sources": [{"number": n, "document": d} for n, d in enumerate(documents, start=1)],
            "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1],
                      "calls": [{"step": "route", "model": "m", "input_tokens": 1, "output_tokens": 1}]}}


class MetricsTest(unittest.TestCase):
    def test_routing_is_set_equality(self):
        self.assertTrue(run_eval.routing_correct(SINGLE, response(["hw"])))
        self.assertFalse(run_eval.routing_correct(SINGLE, response(["hw", "it"])))
        self.assertTrue(run_eval.routing_correct(BOTH, response(["hw", "it"])))
        self.assertFalse(run_eval.routing_correct(BOTH, response(["hw"])))

    def test_off_topic_expects_an_empty_route_and_a_fallback_is_wrong(self):
        self.assertTrue(run_eval.routing_correct(OFF, response([])))
        self.assertFalse(run_eval.routing_correct(OFF, response(["it", "hw"], fallback=True)))

    def test_hit_looks_only_at_the_first_five_sources(self):
        self.assertTrue(run_eval.hit_at_k(SINGLE, response(["hw"], ["x", "x", "x", "x", "a.pdf", "x"])))
        self.assertFalse(run_eval.hit_at_k(SINGLE, response(["hw"], ["x", "x", "x", "x", "x", "a.pdf"])))

    def test_hit_for_two_sources_needs_both(self):
        self.assertTrue(run_eval.hit_at_k(BOTH, response(["it", "hw"], ["p.pdf", "a.pdf"])))
        self.assertFalse(run_eval.hit_at_k(BOTH, response(["it", "hw"], ["p.pdf", "x"])))

    def test_off_topic_has_no_hit_value(self):
        self.assertIsNone(run_eval.hit_at_k(OFF, response([])))

    def test_call_estimate_counts_one_call_for_off_topic(self):
        self.assertEqual(5, run_eval.estimate_llm_calls([SINGLE, BOTH, OFF]))

    def test_eval_set_file_is_valid(self):
        items = run_eval.load_eval_set(demo_common.EVAL_SET_PATH)
        self.assertEqual(8, len(items))
        self.assertEqual(len(items), len({i["id"] for i in items}))
        self.assertEqual(1, sum(1 for i in items if i["expected_kb"] == "none"))
        self.assertEqual(1, sum(1 for i in items if isinstance(i["expected_kb"], list)))
        self.assertEqual(15, run_eval.estimate_llm_calls(items))
        for item in items:
            self.assertEqual({"id", "question", "expected_kb", "expected_source", "expected_answer"}, set(item))


class EvaluateTest(unittest.TestCase):
    class Client:
        def __init__(self, outcomes):
            self.outcomes = outcomes

        def ask(self, question):
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    def test_results_and_summary(self):
        client = self.Client([response(["hw"], ["a.pdf"], tokens=(100, 20)), response(["hw"], ["x"]),
                              response([], tokens=(7, 3))])
        lines = []
        results = run_eval.evaluate(client, [SINGLE, SINGLE, OFF], out=lines.append,
                                   now=lambda: datetime(2026, 10, 23, 9, 30, 0))
        summary = run_eval.summarize(results)
        self.assertEqual(3, len(lines))
        self.assertEqual(3, summary["routing_correct"])
        self.assertEqual(0.5, summary["hit_at_5"])
        self.assertEqual(2, summary["on_topic"])
        self.assertEqual(145, summary["total_tokens"])
        self.assertEqual("09:30:00", results[0]["asked_at"])
        self.assertEqual("09:30:00", summary["first_asked_at"])

    def test_an_api_error_is_recorded_not_raised(self):
        client = self.Client([ApiClientError("busy", "rate limited", code="llm_unavailable")])
        results = run_eval.evaluate(client, [SINGLE], out=lambda _l: None)
        self.assertIn("llm_unavailable", results[0]["error"])
        self.assertFalse(results[0]["routing_correct"])
        self.assertFalse(results[0]["hit"])
        self.assertEqual(1, run_eval.summarize(results)["errors"])


class ProgressRowTest(unittest.TestCase):
    TEXT = ("## Evaluation numbers\n\n"
            "| Date | Commit | Eval set size | Routing accuracy | Hit@5 | Faithfulness | Notes |\n"
            "|---|---|---|---|---|---|---|\n"
            "| | | | | | | No runs yet. The first run is in F6. |\n\n## AI-written code\n")

    def summary(self):
        return {"questions": 8, "routing_correct": 7, "routing_accuracy": 0.875, "on_topic": 7, "hits": 6,
                "hit_at_5": 6 / 7, "total_tokens": 9000, "median_latency_seconds": 2.5,
                "max_latency_seconds": 8.0, "errors": 0, "first_asked_at": "14:05:01", "last_asked_at": "14:09:30"}

    def test_row_replaces_the_placeholder_and_keeps_the_rest(self):
        row = run_eval.progress_row(self.summary(), "2026-10-23", "abc123")
        self.assertIn("88% (7/8)", row)
        self.assertIn("86% (6/7)", row)
        self.assertIn("asked 14:05:01-14:09:30 local", row)
        updated = run_eval.add_progress_row(self.TEXT, row)
        self.assertNotIn("No runs yet", updated)
        lines = updated.split("\n")
        self.assertTrue(lines[4].startswith("| 2026-10-23 | abc123 | 8 |"))
        self.assertIn("## AI-written code", updated)

    def test_second_row_goes_above_the_first(self):
        first = run_eval.add_progress_row(self.TEXT, "| first |")
        second = run_eval.add_progress_row(first, "| second |")
        self.assertLess(second.index("| second |"), second.index("| first |"))


class MainTest(unittest.TestCase):
    def test_declining_makes_no_ask_calls(self):
        with mock.patch.object(run_eval, "ApiClient") as client_class, \
                mock.patch("builtins.input", return_value="n"):
            client_class.return_value.list_kbs.return_value = []
            self.assertEqual(1, run_eval.main(["--no-progress"]))
        client_class.return_value.ask.assert_not_called()

    def test_an_unreachable_api_stops_before_asking(self):
        with mock.patch.object(run_eval, "ApiClient") as client_class:
            client_class.return_value.list_kbs.side_effect = ApiClientError("connection", "no api")
            self.assertEqual(1, run_eval.main(["--yes"]))
        client_class.return_value.ask.assert_not_called()

    def test_full_run_saves_the_run_and_can_skip_progress(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "set.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(SINGLE) + "\n")
            runs = os.path.join(root, "runs")
            with mock.patch.object(run_eval, "ApiClient") as client_class, \
                    mock.patch.object(demo_common, "EVAL_RUNS_DIR", runs), \
                    mock.patch.object(run_eval, "git_commit_label", return_value="abc"):
                client_class.return_value.list_kbs.return_value = []
                client_class.return_value.ask.return_value = response(["hw"], ["a.pdf"])
                code = run_eval.main(["--yes", "--no-progress", "--eval-set", path])
            saved = os.listdir(runs) if os.path.isdir(runs) else []
        self.assertEqual(0, code)
        self.assertEqual(1, len(saved))


if __name__ == "__main__":
    unittest.main()
