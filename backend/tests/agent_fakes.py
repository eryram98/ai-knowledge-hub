"""Test double for the LLM provider (F4): scripted replies, no network.

FakeLlm returns its replies in order and then repeats the last one. A reply
that is an exception instance is raised instead. Every call is recorded.
"""

import os
import sys
import threading

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from agent.agent_config import KbInfo
from agent.agent_llm import LlmProvider, LlmResponse, check_thinking

FAKE_MODEL = "fake-llm"
FAKE_INPUT_TOKENS = 100
FAKE_OUTPUT_TOKENS = 20

KB_INFOS = {
    "it_policies": KbInfo("it_policies", "IT policies", "public university IT policies and procedures"),
    "hw_datasheets": KbInfo("hw_datasheets", "hardware datasheets",
                            "public hardware datasheets (pinouts, electrical characteristics, dimensions)"),
}


class FakeLlm(LlmProvider):
    """Replies with the scripted texts (or raises the scripted exceptions).

    Records (prompt, system_instruction) in calls and each call's thinking level in thinking_levels.
    """

    model_name = FAKE_MODEL

    def __init__(self, *replies, input_tokens=FAKE_INPUT_TOKENS, output_tokens=FAKE_OUTPUT_TOKENS):
        self.replies = list(replies) or ["fake reply"]
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls = []
        self.thinking_levels = []
        self._lock = threading.Lock()

    def generate(self, prompt, system_instruction=None, thinking=None):
        check_thinking(thinking)
        with self._lock:
            index = min(len(self.calls), len(self.replies) - 1)
            self.calls.append((prompt, system_instruction))
            self.thinking_levels.append(thinking)
        reply = self.replies[index]
        if isinstance(reply, BaseException):
            raise reply
        return LlmResponse(reply, input_tokens=self.input_tokens, output_tokens=self.output_tokens,
                           model=FAKE_MODEL)
