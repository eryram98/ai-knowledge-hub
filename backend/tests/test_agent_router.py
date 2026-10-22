"""route() (F4): the routing contract, with a scripted FakeLlm.

TestRoute checks the docstring contract (written while route() was coach
mode). TestRoutingReply and TestRoutingPrompt check the design Claude
implemented for Ethan on 2026-10-22: a JSON reply, fences allowed, and a
prompt built from the KB descriptions.

Every scripted LLM reply goes through routing_reply(), which builds the
JSON reply format the router asks the model for.
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
from agent.agent_router import ROUTER_THINKING, ROUTING_EXAMPLES, build_routing_instruction, route

KB_DESCRIPTIONS = kb_descriptions(KB_INFOS)
CONFIGURED = set(KB_DESCRIPTIONS)

DATASHEET_QUESTION = "What is the input voltage range of the Raspberry Pi Pico?"
POLICY_QUESTION = "Am I allowed to share my university account password with a classmate?"
BOTH_QUESTION = ("Does the IT policy allow connecting a Raspberry Pi Pico to the campus network, "
                 "and what voltage does it need?")
OFF_TOPIC_QUESTION = "Who won the 1998 FIFA World Cup?"


def routing_reply(kb_ids, reason):
    """The LLM reply text that says "route to kb_ids because reason": {"kb_ids": [...], "reason": "..."}."""
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
    def test_datasheet_question_routes_to_hw_datasheets(self):
        result = self.route_with(DATASHEET_QUESTION, routing_reply(["hw_datasheets"], "a hardware spec question"))
        self.assertEqual(result["kb_ids"], ["hw_datasheets"])
        self.assertFalse(result["fallback"])

    def test_policy_question_routes_to_it_policies(self):
        result = self.route_with(POLICY_QUESTION, routing_reply(["it_policies"], "an account policy question"))
        self.assertEqual(result["kb_ids"], ["it_policies"])
        self.assertFalse(result["fallback"])

    def test_question_spanning_both_kbs_routes_to_both(self):
        result = self.route_with(BOTH_QUESTION, routing_reply(["it_policies", "hw_datasheets"], "policy and hardware"))
        self.assertEqual(sorted(result["kb_ids"]), sorted(CONFIGURED))
        self.assertFalse(result["fallback"])

    def test_off_topic_question_routes_to_no_kb(self):
        result = self.route_with(OFF_TOPIC_QUESTION, routing_reply([], "sports trivia, not covered"))
        self.assertEqual(result["kb_ids"], [])
        self.assertFalse(result["fallback"])

    def test_unknown_kb_id_in_reply_falls_back_to_every_kb(self):
        result = self.route_with(DATASHEET_QUESTION, routing_reply(["hr_handbook"], "made-up KB"))
        self.assertFallback(result)

    def test_unparseable_reply_falls_back_to_every_kb(self):
        for reply in ("I think the datasheets one, probably?", ""):
            with self.subTest(reply=reply):
                self.assertFallback(self.route_with(DATASHEET_QUESTION, reply))

    def test_llm_unavailable_propagates(self):
        with self.assertRaises(LlmUnavailableError):
            route(DATASHEET_QUESTION, KB_DESCRIPTIONS, FakeLlm(LlmUnavailableError("rate limited")))

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


class TestRoutingReply(RouterTestCase):
    def test_reply_in_a_code_fence_is_parsed(self):
        for fence in ("```json\n{0}\n```", "```\n{0}\n```", "  ```json {0} ```  "):
            with self.subTest(fence=fence):
                reply = fence.format(routing_reply(["hw_datasheets"], "a spec question"))
                result = self.route_with(DATASHEET_QUESTION, reply)
                self.assertEqual(result["kb_ids"], ["hw_datasheets"])
                self.assertFalse(result["fallback"])

    def test_wrong_shapes_fall_back_to_every_kb(self):
        replies = (
            json.dumps(["hw_datasheets"]),
            json.dumps({"kb_ids": "hw_datasheets", "reason": "a string, not a list"}),
            json.dumps({"kb_ids": [1], "reason": "not a string id"}),
            json.dumps({"kb_ids": ["hw_datasheets"]}),
            json.dumps({"kb_ids": ["hw_datasheets"], "reason": "  "}),
            json.dumps({"reason": "no kb_ids"}),
            "```json\nnot json\n```",
        )
        for reply in replies:
            with self.subTest(reply=reply):
                self.assertFallback(self.route_with(DATASHEET_QUESTION, reply))

    def test_more_than_two_kbs_falls_back(self):
        descriptions = dict(KB_DESCRIPTIONS, hr_handbook="public HR handbooks")
        reply = routing_reply(["it_policies", "hw_datasheets", "hr_handbook"], "all three")
        result = route(DATASHEET_QUESTION, descriptions, FakeLlm(reply))
        self.assertTrue(result["fallback"])
        self.assertIn("more than 2", result["reason"])

    def test_duplicate_kb_falls_back(self):
        result = self.route_with(DATASHEET_QUESTION, routing_reply(["hw_datasheets", "hw_datasheets"], "twice"))
        self.assertFallback(result)
        self.assertIn("duplicate", result["reason"])

    def test_kb_ids_come_back_in_config_order_and_reason_is_stripped(self):
        result = self.route_with(BOTH_QUESTION, routing_reply(["hw_datasheets", "it_policies"], "  both  "))
        self.assertEqual(result["kb_ids"], list(KB_DESCRIPTIONS))
        self.assertEqual(result["reason"], "both")

    def test_other_llm_errors_propagate(self):
        from agent.agent_llm import LlmError
        with self.assertRaises(LlmError):
            route(DATASHEET_QUESTION, KB_DESCRIPTIONS, FakeLlm(LlmError("bad request")))


class TestRoutingPrompt(unittest.TestCase):
    def test_one_call_with_the_question_the_instruction_and_low_thinking(self):
        llm = FakeLlm(routing_reply(["hw_datasheets"], "spec"))
        route(DATASHEET_QUESTION, KB_DESCRIPTIONS, llm)
        self.assertEqual(len(llm.calls), 1)
        prompt, system_instruction = llm.calls[0]
        self.assertEqual(prompt, "Question: " + DATASHEET_QUESTION)
        self.assertEqual(system_instruction, build_routing_instruction(KB_DESCRIPTIONS))
        self.assertEqual(llm.thinking_levels, [ROUTER_THINKING])
        self.assertEqual(ROUTER_THINKING, "low")

    def test_instruction_lists_every_configured_kb_from_the_descriptions(self):
        descriptions = dict(KB_DESCRIPTIONS, hr_handbook="public HR handbooks and leave rules")
        instruction = build_routing_instruction(descriptions)
        for kb_id, description in descriptions.items():
            self.assertIn("- {0}: {1}".format(kb_id, description), instruction)

    def test_all_four_examples_are_shown_when_both_kbs_are_configured(self):
        instruction = build_routing_instruction(KB_DESCRIPTIONS)
        for question, _, _ in ROUTING_EXAMPLES:
            self.assertIn("Question: " + question, instruction)
        self.assertEqual(len(ROUTING_EXAMPLES), 4)

    def test_examples_naming_an_unconfigured_kb_are_left_out(self):
        instruction = build_routing_instruction({"hw_datasheets": KB_DESCRIPTIONS["hw_datasheets"]})
        self.assertNotIn("it_policies", instruction)
        self.assertIn("pin pitch", instruction)  # the datasheet example
        self.assertIn("banana bread", instruction)  # the off-topic example names no KB

    def test_example_replies_are_valid_routing_replies(self):
        instruction = build_routing_instruction(KB_DESCRIPTIONS)
        for question, kb_ids, reason in ROUTING_EXAMPLES:
            self.assertIn(json.dumps({"kb_ids": kb_ids, "reason": reason}), instruction)
            self.assertLessEqual(set(kb_ids), CONFIGURED)


if __name__ == "__main__":
    unittest.main()
