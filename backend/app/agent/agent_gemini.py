"""Gemini implementation of the LLM provider (F4), through the google-genai SDK.

The SDK's own retries are off (its default), so this class owns them: a 429
(rate limit), a 503 (model overloaded), a 504 (DEADLINE_EXCEEDED on Gemini's
side) or a network error is retried with exponential backoff and jitter, up to
max_retries times, and then raised as LlmUnavailableError. Any other API error
is an LlmError at once.

The client is created on the first call, so the app and /search start
without GEMINI_API_KEY.
"""

import logging
import random
import threading
import time

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from agent.agent_llm import LlmError, LlmProvider, LlmResponse, LlmUnavailableError, check_thinking

LOGGER = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = (429, 503, 504)
DEFAULT_BASE_DELAY_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 60.0


class GeminiLlm(LlmProvider):
    """Gemini via google-genai, temperature 0. Delays are base_delay * 2**retry plus up to 1 s of jitter."""

    def __init__(self, api_key, model_name, max_retries=3, client=None, sleep=time.sleep,
                 base_delay=DEFAULT_BASE_DELAY_SECONDS, timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                 jitter=random.random):
        self.api_key = api_key
        self.model_name = model_name
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._sleep = sleep
        self._jitter = jitter
        self._lock = threading.Lock()

    def _get_client(self):
        with self._lock:
            if self._client is None:
                if not self.api_key:
                    raise LlmError("GEMINI_API_KEY is not set")
                self._client = genai.Client(
                    api_key=self.api_key,
                    http_options=genai_types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
                )
            return self._client

    def generate(self, prompt, system_instruction=None, thinking=None):
        thinking = check_thinking(thinking)
        client = self._get_client()
        # No tools are passed, so automatic function calling is off (it also silences the SDK's AFC notice).
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction, temperature=0.0,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )
        if thinking is not None:
            config.thinking_config = genai_types.ThinkingConfig(thinking_level=thinking.upper())
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                response = client.models.generate_content(model=self.model_name, contents=prompt, config=config)
            except genai_errors.APIError as exc:
                if exc.code not in RETRYABLE_STATUS_CODES:
                    raise LlmError("Gemini request failed: {0} {1}".format(exc.code, exc.status)) from exc
                problem = "{0} {1}".format(exc.code, exc.status)
                last_error = exc
            except httpx.TransportError as exc:
                problem = "network error ({0})".format(type(exc).__name__)
                last_error = exc
            else:
                return self._to_response(response)
            if attempt + 1 < attempts:
                delay = self.base_delay * (2 ** attempt) + self._jitter()
                LOGGER.warning("Gemini %s; retry %d of %d in %.1f s", problem, attempt + 1, self.max_retries, delay)
                self._sleep(delay)
        raise LlmUnavailableError("Gemini still unavailable after {0} attempt(s): {1}".format(
            attempts, problem)) from last_error

    def _to_response(self, response):
        text = response.text
        if text is None:
            reason = None
            if response.candidates:
                reason = response.candidates[0].finish_reason
            raise LlmError("Gemini returned no text (finish reason: {0})".format(reason))
        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage is not None else 0
        output_tokens = 0
        if usage is not None:
            # Thinking tokens are billed as output.
            output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        return LlmResponse(text, input_tokens=input_tokens, output_tokens=output_tokens, model=self.model_name)
