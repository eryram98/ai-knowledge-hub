"""LLM provider plumbing (F4): UsageRecorder, build_llm and the FakeLlm test double."""

import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from agent_fakes import FakeLlm

from agent.agent_config import AgentConfig
from agent.agent_gemini import GeminiLlm
from agent.agent_llm import LlmError, LlmUnavailableError, UsageRecorder, build_llm


class TestUsageRecorder(unittest.TestCase):
    def test_records_each_call_under_its_step_and_sums_usage(self):
        llm = FakeLlm("one", "two", input_tokens=10, output_tokens=3)
        recorder = UsageRecorder(llm)
        recorder.step = "route"
        self.assertEqual(recorder.generate("p1").text, "one")
        recorder.step = "answer"
        self.assertEqual(recorder.generate("p2", system_instruction="sys").text, "two")
        self.assertEqual(llm.calls, [("p1", None), ("p2", "sys")])
        self.assertEqual(recorder.usage(), {
            "input_tokens": 20, "output_tokens": 6,
            "calls": [
                {"step": "route", "model": "fake-llm", "input_tokens": 10, "output_tokens": 3},
                {"step": "answer", "model": "fake-llm", "input_tokens": 10, "output_tokens": 3},
            ],
        })

    def test_thinking_level_is_forwarded(self):
        llm = FakeLlm("one", "two")
        recorder = UsageRecorder(llm)
        recorder.generate("p1", thinking="minimal")
        recorder.generate("p2")
        self.assertEqual(llm.thinking_levels, ["minimal", None])

    def test_no_calls_means_zero_usage(self):
        self.assertEqual(UsageRecorder(FakeLlm()).usage(), {"input_tokens": 0, "output_tokens": 0, "calls": []})

    def test_errors_propagate_and_record_nothing(self):
        recorder = UsageRecorder(FakeLlm(LlmUnavailableError("busy")))
        with self.assertRaises(LlmUnavailableError):
            recorder.generate("p")
        self.assertEqual(recorder.usage()["calls"], [])

    def test_unavailable_is_an_llm_error(self):
        self.assertTrue(issubclass(LlmUnavailableError, LlmError))


class TestFakeLlm(unittest.TestCase):
    def test_replies_in_order_then_repeats_the_last(self):
        llm = FakeLlm("a", "b")
        self.assertEqual([llm.generate("q").text for _ in range(3)], ["a", "b", "b"])


class TestBuildLlm(unittest.TestCase):
    def make_config(self, provider):
        config = AgentConfig()
        config.llm_provider = provider
        config.gemini_api_key = None
        config.gemini_model = "gemini-test"
        config.max_retries = 2
        config.timeout_seconds = 7.5
        return config

    def test_gemini_is_built_without_a_network_call_or_key(self):
        llm = build_llm(self.make_config("gemini"))
        self.assertIsInstance(llm, GeminiLlm)
        self.assertEqual(llm.model_name, "gemini-test")
        self.assertEqual(llm.max_retries, 2)
        self.assertEqual(llm.timeout_seconds, 7.5)
        self.assertIsNone(llm._client)

    def test_unknown_provider_is_a_startup_error(self):
        with self.assertRaises(ValueError) as caught:
            build_llm(self.make_config("ollama"))
        self.assertIn("ollama", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
