"""AgentConfig and the KB descriptions file (F4)."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from agent.agent_config import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_TIMEOUT_SECONDS,
    DEFAULT_KB_DESCRIPTIONS_PATH,
    DEFAULT_LLM_MAX_RETRIES,
    AgentConfig,
    KbInfo,
    kb_descriptions,
    load_kb_infos,
)

KB_IDS = ("it_policies", "hw_datasheets")
AGENT_ENV = ("LLM_PROVIDER", "GEMINI_MODEL", "GEMINI_API_KEY", "LLM_MAX_RETRIES", "KB_DESCRIPTIONS_PATH",
             "GEMINI_ROUTER_THINKING", "GEMINI_ANSWER_THINKING", "GEMINI_TIMEOUT_SECONDS")


class TestAgentConfig(unittest.TestCase):
    def config_with(self, **values):
        environment = {name: "" for name in AGENT_ENV}
        environment.update(values)
        with patch.dict(os.environ, environment):
            return AgentConfig()

    def test_defaults(self):
        config = self.config_with()
        self.assertEqual(config.llm_provider, "gemini")
        self.assertEqual(config.gemini_model, DEFAULT_GEMINI_MODEL)
        self.assertIsNone(config.gemini_api_key)
        self.assertEqual(config.max_retries, DEFAULT_LLM_MAX_RETRIES)
        self.assertEqual(config.kb_descriptions_path, DEFAULT_KB_DESCRIPTIONS_PATH)
        self.assertEqual(DEFAULT_GEMINI_MODEL, "gemini-3.5-flash-lite")
        self.assertEqual((config.router_thinking, config.answer_thinking), ("minimal", "minimal"))
        self.assertEqual(config.timeout_seconds, DEFAULT_GEMINI_TIMEOUT_SECONDS)
        self.assertEqual(DEFAULT_GEMINI_TIMEOUT_SECONDS, 20.0)

    def test_thinking_and_timeout_overrides(self):
        config = self.config_with(GEMINI_ROUTER_THINKING=" Low ", GEMINI_ANSWER_THINKING="high",
                                  GEMINI_TIMEOUT_SECONDS="7.5")
        self.assertEqual((config.router_thinking, config.answer_thinking, config.timeout_seconds),
                         ("low", "high", 7.5))

    def test_invalid_thinking_falls_back_with_a_warning(self):
        for raw in ("none", "off", "0"):
            with self.subTest(raw=raw):
                with self.assertLogs("agent.agent_config", level="WARNING"):
                    config = self.config_with(GEMINI_ROUTER_THINKING=raw, GEMINI_ANSWER_THINKING=raw)
                self.assertEqual((config.router_thinking, config.answer_thinking), ("minimal", "minimal"))

    def test_invalid_timeout_falls_back_with_a_warning(self):
        for raw in ("0", "-5", "soon", "inf", "nan"):
            with self.subTest(raw=raw):
                with self.assertLogs("agent.agent_config", level="WARNING"):
                    self.assertEqual(self.config_with(GEMINI_TIMEOUT_SECONDS=raw).timeout_seconds,
                                     DEFAULT_GEMINI_TIMEOUT_SECONDS)

    def test_environment_overrides(self):
        config = self.config_with(LLM_PROVIDER=" Gemini ", GEMINI_MODEL="gemini-x", GEMINI_API_KEY=" k ",
                                  LLM_MAX_RETRIES="0", KB_DESCRIPTIONS_PATH="other.json")
        self.assertEqual((config.llm_provider, config.gemini_model, config.gemini_api_key, config.max_retries,
                          config.kb_descriptions_path), ("gemini", "gemini-x", "k", 0, "other.json"))

    def test_invalid_retries_fall_back_with_a_warning(self):
        for raw in ("-1", "three"):
            with self.subTest(raw=raw):
                with self.assertLogs("agent.agent_config", level="WARNING"):
                    self.assertEqual(self.config_with(LLM_MAX_RETRIES=raw).max_retries, DEFAULT_LLM_MAX_RETRIES)

    def test_as_dict_never_contains_the_key(self):
        settings = self.config_with(GEMINI_API_KEY="secret-key").as_dict()
        self.assertTrue(settings["gemini_api_key_set"])
        self.assertNotIn("secret-key", str(settings))


class TestLoadKbInfos(unittest.TestCase):
    def write(self, content):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = os.path.join(directory.name, "kbs.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content if isinstance(content, str) else json.dumps(content))
        return path

    def test_committed_file_covers_the_default_kbs(self):
        infos = load_kb_infos(DEFAULT_KB_DESCRIPTIONS_PATH, KB_IDS)
        self.assertEqual(list(infos), list(KB_IDS))
        self.assertEqual(infos["it_policies"].name, "IT policies")
        self.assertEqual(infos["hw_datasheets"].name, "hardware datasheets")
        self.assertEqual(infos["it_policies"].description, "public university IT policies and procedures")
        self.assertEqual(infos["hw_datasheets"].description,
                         "public hardware datasheets (pinouts, electrical characteristics, dimensions)")

    def test_config_order_stripped_values_and_extra_entries_ignored(self):
        path = self.write({
            "HW_Datasheets": {"name": " hw ", "description": " chips "},
            "it_policies": {"name": "it", "description": "rules"},
            "unused": {"name": "x", "description": "y"},
        })
        infos = load_kb_infos(path, KB_IDS)
        self.assertEqual(infos, {"it_policies": KbInfo("it_policies", "it", "rules"),
                                 "hw_datasheets": KbInfo("hw_datasheets", "hw", "chips")})
        self.assertEqual(list(infos), list(KB_IDS))
        self.assertEqual(kb_descriptions(infos), {"it_policies": "rules", "hw_datasheets": "chips"})

    def test_problems_are_value_errors(self):
        cases = {
            "missing KB": {"it_policies": {"name": "it", "description": "rules"}},
            "blank description": {"it_policies": {"name": "it", "description": " "},
                                  "hw_datasheets": {"name": "hw", "description": "chips"}},
            "missing name": {"it_policies": {"description": "rules"},
                             "hw_datasheets": {"name": "hw", "description": "chips"}},
            "string entry": {"it_policies": "rules", "hw_datasheets": {"name": "hw", "description": "chips"}},
            "not an object": ["it_policies"],
            "bad json": "{not json",
        }
        for label, content in cases.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    load_kb_infos(self.write(content), KB_IDS)

    def test_missing_file_is_a_value_error(self):
        with self.assertRaises(ValueError):
            load_kb_infos(os.path.join(tempfile.gettempdir(), "no-such-kb-file.json"), KB_IDS)


if __name__ == "__main__":
    unittest.main()
