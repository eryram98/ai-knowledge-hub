"""route() (F4): the routing contract, with a scripted FakeLlm.

Coach mode: Ethan writes route(); Claude wrote these tests against its
docstring. Every test is marked expectedFailure until route() exists. Remove
the decorators once it does.

Every scripted LLM reply goes through routing_reply(). It is Ethan's to
change so it produces the reply format his router asks the model for.
"""

import json
import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from agent_fakes import KB_INFOS, FakeLlm

from agent.agent_config import kb_descriptions
from agent.agent_llm import LlmUnavailableError
from agent.agent_router import route

KB_DESCRIPTIONS = kb_descriptions(KB_INFOS)
CONFIGURED = set(KB_DESCRIPTIONS)

DATASHEET_QUESTION = "What is the input voltage range of the Raspberry Pi Pico?"
POLICY_QUESTION = "Am I allowed to share my university account password with a classmate?"
BOTH_QUESTION = ("Does the IT policy allow connecting a Raspberry Pi Pico to the campus network, "
                 "and what voltage does it need?")
OFF_TOPIC_QUESTION = "Who won the 1998 FIFA World Cup?"


def routing_reply(kb_ids, reason):
    """The LLM reply text that says "route to kb_ids because reason"."""
    return json.dumps({"kb_ids": list(kb_ids), "reason": reason})


class RouterTestCase(unittest.TestCase):
    def route_with(self, question, *replies):
        result = route(question, KB_DESCRIPTIONS, FakeLlm(*replies))
        self.assertEqual(set(result), {"kb_ids", "reason", "fallback"})
        self.assertIsInstance(result["kb_ids"], list)
        self.assertIsInstance(result["reason"], str)
        self.assertTrue(result["reason"].strip())
        self.assertIsInstance(result["fallback"], bool)
        return result

    def assertFallback(self, result):
        self.assertTrue(result["fallback"])
        self.assertEqual(sorted(result["kb_ids"]), sorted(CONFIGURED))
        self.assertIn("fail", result["reason"].lower())


class TestRoute(RouterTestCase):
    @unittest.expectedFailure
    def test_datasheet_question_routes_to_hw_datasheets(self):
        result = self.route_with(DATASHEET_QUESTION, routing_reply(["hw_datasheets"], "a hardware spec question"))
        self.assertEqual(result["kb_ids"], ["hw_datasheets"])
        self.assertFalse(result["fallback"])

    @unittest.expectedFailure
    def test_policy_question_routes_to_it_policies(self):
        result = self.route_with(POLICY_QUESTION, routing_reply(["it_policies"], "an account policy question"))
        self.assertEqual(result["kb_ids"], ["it_policies"])
        self.assertFalse(result["fallback"])

    @unittest.expectedFailure
    def test_question_spanning_both_kbs_routes_to_both(self):
        result = self.route_with(BOTH_QUESTION, routing_reply(["it_policies", "hw_datasheets"], "policy and hardware"))
        self.assertEqual(sorted(result["kb_ids"]), sorted(CONFIGURED))
        self.assertFalse(result["fallback"])

    @unittest.expectedFailure
    def test_off_topic_question_routes_to_no_kb(self):
        result = self.route_with(OFF_TOPIC_QUESTION, routing_reply([], "sports trivia, not covered"))
        self.assertEqual(result["kb_ids"], [])
        self.assertFalse(result["fallback"])

    @unittest.expectedFailure
    def test_unknown_kb_id_in_reply_falls_back_to_every_kb(self):
        result = self.route_with(DATASHEET_QUESTION, routing_reply(["hr_handbook"], "made-up KB"))
        self.assertFallback(result)

    @unittest.expectedFailure
    def test_unparseable_reply_falls_back_to_every_kb(self):
        for reply in ("I think the datasheets one, probably?", ""):
            with self.subTest(reply=reply):
                self.assertFallback(self.route_with(DATASHEET_QUESTION, reply))

    @unittest.expectedFailure
    def test_llm_unavailable_propagates(self):
        with self.assertRaises(LlmUnavailableError):
            route(DATASHEET_QUESTION, KB_DESCRIPTIONS, FakeLlm(LlmUnavailableError("rate limited")))

    @unittest.expectedFailure
    def test_kb_ids_are_always_a_subset_of_the_configured_kbs(self):
        replies = (
            routing_reply(["hw_datasheets"], "valid"),
            routing_reply(["it_policies", "hw_datasheets"], "valid pair"),
            routing_reply([], "off-topic"),
            routing_reply(["hw_datasheets", "made_up"], "one unknown"),
            routing_reply(["hw_datasheets", "hw_datasheets"], "duplicate"),
            "not a routing reply at all",
        )
        for reply in replies:
            with self.subTest(reply=reply):
                kb_ids = self.route_with(DATASHEET_QUESTION, reply)["kb_ids"]
                self.assertLessEqual(set(kb_ids), CONFIGURED)
                self.assertEqual(len(kb_ids), len(set(kb_ids)))
                self.assertLessEqual(len(kb_ids), 2)


if __name__ == "__main__":
    unittest.main()
