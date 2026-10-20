"""LLM provider interface (F4): one text-in, text-out call that reports token usage.

Gemini is the default implementation (agent_gemini.py), chosen by
LLM_PROVIDER. Tests use FakeLlm (backend/tests/agent_fakes.py); no test makes
a real call.
"""

import threading
from abc import ABC, abstractmethod


class LlmError(Exception):
    """The LLM call failed in a way retrying won't fix (bad request, auth, no key, unknown provider)."""


class LlmUnavailableError(LlmError):
    """The LLM service is rate-limited or unavailable, and the retries ran out. The API maps it to 503."""


class LlmResponse(object):
    """The reply text plus the call's token usage (output includes thinking tokens)."""

    def __init__(self, text, input_tokens=0, output_tokens=0, model=None):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model

    def __repr__(self):
        return "LlmResponse(text={0!r}, input_tokens={1}, output_tokens={2}, model={3!r})".format(
            self.text, self.input_tokens, self.output_tokens, self.model)


class LlmProvider(ABC):
    """A chat model behind one call."""

    model_name = None

    @abstractmethod
    def generate(self, prompt, system_instruction=None):
        """Send one user prompt (plus an optional system instruction) and return an LlmResponse.

        Raises LlmUnavailableError when the service stays rate-limited or
        unavailable, and LlmError for any other failure.
        """


class UsageRecorder(LlmProvider):
    """Wraps a provider and records the usage of every call under the current step label.

    /ask hands the same recorder to the router and the answer step, so the
    token totals cover every call without the router reporting usage itself.
    """

    def __init__(self, llm):
        self.llm = llm
        self.model_name = getattr(llm, "model_name", None)
        self.step = None
        self.calls = []
        self._lock = threading.Lock()

    def generate(self, prompt, system_instruction=None):
        response = self.llm.generate(prompt, system_instruction=system_instruction)
        with self._lock:
            self.calls.append({
                "step": self.step,
                "model": response.model,
                "input_tokens": response.input_tokens or 0,
                "output_tokens": response.output_tokens or 0,
            })
        return response

    def usage(self):
        """{input_tokens, output_tokens, calls: [{step, model, input_tokens, output_tokens}]}."""
        with self._lock:
            calls = [dict(call) for call in self.calls]
        return {
            "input_tokens": sum(call["input_tokens"] for call in calls),
            "output_tokens": sum(call["output_tokens"] for call in calls),
            "calls": calls,
        }


def build_llm(agent_config):
    """The provider named by LLM_PROVIDER; ValueError (a startup error) for any other name. No network call."""
    if agent_config.llm_provider == "gemini":
        from agent.agent_gemini import GeminiLlm
        return GeminiLlm(agent_config.gemini_api_key, agent_config.gemini_model,
                         max_retries=agent_config.max_retries)
    raise ValueError("Unknown LLM_PROVIDER {0!r}; supported: gemini".format(agent_config.llm_provider))
