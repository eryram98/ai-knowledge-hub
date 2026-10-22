"""GeminiLlm (F4) against a fake google-genai client: retries, typed errors, usage. No network."""

import os
import sys
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import httpx
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from agent.agent_gemini import GeminiLlm
from agent.agent_llm import LlmError, LlmUnavailableError


def api_error(code, status):
    error_class = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return error_class(code, {"error": {"code": code, "status": status, "message": "test"}})


def gemini_response(text="hello", prompt_tokens=12, candidate_tokens=5, thought_tokens=None):
    return genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=genai_types.Content(
            role="model", parts=[genai_types.Part(text=text)] if text is not None else []))],
        usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt_tokens, candidates_token_count=candidate_tokens,
            thoughts_token_count=thought_tokens),
    )


class FakeModels(object):
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient(object):
    def __init__(self, *outcomes):
        self.models = FakeModels(outcomes)


class GeminiTestCase(unittest.TestCase):
    def make_llm(self, *outcomes, max_retries=3):
        self.client = FakeClient(*outcomes)
        self.sleeps = []
        return GeminiLlm("test-key", "gemini-test", max_retries=max_retries, client=self.client,
                         sleep=self.sleeps.append, base_delay=2.0, jitter=lambda: 0.5)


class TestGeminiCall(GeminiTestCase):
    def test_sends_prompt_system_instruction_and_temperature_zero(self):
        llm = self.make_llm(gemini_response("hi"))
        response = llm.generate("the prompt", system_instruction="be grounded")
        self.assertEqual(response.text, "hi")
        call = self.client.models.calls[0]
        self.assertEqual(call["model"], "gemini-test")
        self.assertEqual(call["contents"], "the prompt")
        self.assertEqual(call["config"].system_instruction, "be grounded")
        self.assertEqual(call["config"].temperature, 0.0)
        self.assertTrue(call["config"].automatic_function_calling.disable)
        self.assertIsNone(call["config"].thinking_config)  # no thinking argument: the model's default
        self.assertEqual(self.sleeps, [])

    def test_thinking_level_is_sent_as_the_thinking_config(self):
        for level, expected in (("minimal", genai_types.ThinkingLevel.MINIMAL),
                                ("high", genai_types.ThinkingLevel.HIGH)):
            with self.subTest(level=level):
                llm = self.make_llm(gemini_response("hi"))
                llm.generate("p", thinking=level)
                self.assertEqual(self.client.models.calls[0]["config"].thinking_config.thinking_level, expected)

    def test_unknown_thinking_level_is_a_value_error_without_a_call(self):
        for level in ("none", "MINIMAL", 0, 1024):
            with self.subTest(level=level):
                llm = self.make_llm(gemini_response("hi"))
                with self.assertRaises(ValueError):
                    llm.generate("p", thinking=level)
                self.assertEqual(self.client.models.calls, [])

    def test_usage_counts_thinking_tokens_as_output(self):
        response = self.make_llm(gemini_response(prompt_tokens=40, candidate_tokens=7, thought_tokens=30)).generate("p")
        self.assertEqual((response.input_tokens, response.output_tokens, response.model), (40, 37, "gemini-test"))

    def test_missing_usage_counts_are_zero(self):
        llm = self.make_llm(gemini_response(prompt_tokens=None, candidate_tokens=None))
        response = llm.generate("p")
        self.assertEqual((response.input_tokens, response.output_tokens), (0, 0))

    def test_no_text_is_an_llm_error(self):
        with self.assertRaises(LlmError) as caught:
            self.make_llm(gemini_response(text=None)).generate("p")
        self.assertNotIsInstance(caught.exception, LlmUnavailableError)


class TestGeminiRetries(GeminiTestCase):
    def test_429_then_success_retries_with_backoff(self):
        llm = self.make_llm(api_error(429, "RESOURCE_EXHAUSTED"), api_error(503, "UNAVAILABLE"),
                            gemini_response("ok"))
        with self.assertLogs("agent.agent_gemini", level="WARNING"):
            self.assertEqual(llm.generate("p").text, "ok")
        self.assertEqual(self.sleeps, [2.5, 4.5])
        self.assertEqual(len(self.client.models.calls), 3)

    def test_429_every_time_raises_unavailable_after_the_retries(self):
        llm = self.make_llm(*[api_error(429, "RESOURCE_EXHAUSTED")] * 4, max_retries=3)
        with self.assertLogs("agent.agent_gemini", level="WARNING"):
            with self.assertRaises(LlmUnavailableError) as caught:
                llm.generate("p")
        self.assertEqual(len(self.client.models.calls), 4)
        self.assertEqual(self.sleeps, [2.5, 4.5, 8.5])  # no sleep after the last attempt
        self.assertIn("429", str(caught.exception))

    def test_504_deadline_exceeded_then_success_is_retried(self):
        llm = self.make_llm(api_error(504, "DEADLINE_EXCEEDED"), gemini_response("ok"))
        with self.assertLogs("agent.agent_gemini", level="WARNING"):
            self.assertEqual(llm.generate("p").text, "ok")
        self.assertEqual(self.sleeps, [2.5])
        self.assertEqual(len(self.client.models.calls), 2)

    def test_504_every_time_raises_unavailable_after_the_retries(self):
        llm = self.make_llm(*[api_error(504, "DEADLINE_EXCEEDED")] * 4, max_retries=3)
        with self.assertLogs("agent.agent_gemini", level="WARNING"):
            with self.assertRaises(LlmUnavailableError) as caught:
                llm.generate("p")
        self.assertEqual(len(self.client.models.calls), 4)
        self.assertIn("504 DEADLINE_EXCEEDED", str(caught.exception))

    def test_network_error_is_retried_then_unavailable(self):
        llm = self.make_llm(httpx.ConnectError("down"), httpx.ReadTimeout("slow"), max_retries=1)
        with self.assertLogs("agent.agent_gemini", level="WARNING"):
            with self.assertRaises(LlmUnavailableError):
                llm.generate("p")
        self.assertEqual(self.sleeps, [2.5])

    def test_zero_retries_means_one_attempt(self):
        llm = self.make_llm(api_error(429, "RESOURCE_EXHAUSTED"), max_retries=0)
        with self.assertRaises(LlmUnavailableError):
            llm.generate("p")
        self.assertEqual(self.sleeps, [])

    def test_other_api_errors_are_not_retried(self):
        for code, status in ((400, "INVALID_ARGUMENT"), (403, "PERMISSION_DENIED"), (500, "INTERNAL")):
            with self.subTest(code=code):
                llm = self.make_llm(api_error(code, status))
                with self.assertRaises(LlmError) as caught:
                    llm.generate("p")
                self.assertNotIsInstance(caught.exception, LlmUnavailableError)
                self.assertEqual(len(self.client.models.calls), 1)
                self.assertEqual(self.sleeps, [])


class TestGeminiClient(unittest.TestCase):
    def test_client_is_not_created_until_the_first_call(self):
        llm = GeminiLlm("test-key", "gemini-test")
        self.assertIsNone(llm._client)

    def test_missing_key_is_an_llm_error_on_the_first_call(self):
        llm = GeminiLlm(None, "gemini-test")
        with self.assertRaises(LlmError) as caught:
            llm.generate("p")
        self.assertNotIsInstance(caught.exception, LlmUnavailableError)
        self.assertIn("GEMINI_API_KEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
