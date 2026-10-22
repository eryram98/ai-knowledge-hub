"""POST /ask (F4) through TestClient: route -> retrieve -> merge -> grounded answer, plus /kbs descriptions.

Most tests patch route() with scripted routers, so they check /ask's own
wiring; one test runs the real route() end to end with a FakeLlm JSON reply.
Documents go through the real upload endpoint and worker (fake embedder,
in-memory Chroma). The LLM is always a FakeLlm.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "app")
for path in (APP_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi.testclient import TestClient

from agent_fakes import KB_INFOS, FakeLlm
from indexing_fakes import FakeEmbedder, ephemeral_vector_index
from test_agent_gemini import FakeClient, api_error
from test_api_search import KB_IDS, SearchApiTestCase, make_config, make_retrieval_config

from agent.agent_answer import ANSWER_SYSTEM_INSTRUCTION, NO_ANSWER_SENTENCE
from agent.agent_config import AgentConfig, KbInfo
from agent.agent_gemini import GeminiLlm
from agent.agent_llm import LlmError, LlmUnavailableError
from api.api_app import create_app
from ingestion.ingestion_status_repository import SQLiteIngestionStatusRepository

DATASHEET_QUESTION = "Which pin doubles as a UART pin?"
OFF_TOPIC_MESSAGE = (
    "That question is outside what the knowledge bases cover. They cover: public university IT policies and "
    "procedures; public hardware datasheets (pinouts, electrical characteristics, dimensions)."
)


def scripted_router(kb_ids, reason="scripted", fallback=False, calls_llm=True, record=None):
    """A stand-in for route(): optionally makes one LLM call (so usage covers it), then returns the given result."""
    def fake_route(question, kb_descriptions, llm, thinking=None):
        if record is not None:
            record.append((question, kb_descriptions))
        if calls_llm:
            llm.generate("route: " + question)
        return {"kb_ids": list(kb_ids), "reason": reason, "fallback": fallback}
    return fake_route


class AskApiTestCase(SearchApiTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name
        self.status_repository = SQLiteIngestionStatusRepository(os.path.join(directory.name, "api.sqlite3"))
        self.embedder = FakeEmbedder()
        self.llm = FakeLlm("route reply", "GPIO17 doubles as a UART pin [1].")
        self.app = create_app(
            config=make_config(), status_repository=self.status_repository,
            upload_dir=os.path.join(directory.name, "uploads"), embedder=self.embedder,
            vector_index=ephemeral_vector_index(self), retrieval_config=make_retrieval_config(),
            llm=self.llm, kb_infos=KB_INFOS,
        )

    def ask(self, router, question=DATASHEET_QUESTION, ingest=True):
        """Optionally ingest one document per KB, then POST /ask with route() replaced by router."""
        with TestClient(self.app) as client:
            if ingest:
                self.ingest_both(client)
            with patch("agent.agent_router.route", side_effect=router):
                return client.post("/ask", json={"question": question})

    def assertCanonicalError(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.text)
        body = response.json()
        self.assertEqual(body["code"], code)
        self.assertIn("message", body)
        self.assertIn("details", body)
        return body


class TestAskAnswers(AskApiTestCase):
    def test_on_topic_question_is_answered_from_the_routed_kb_with_sources_and_usage(self):
        record = []
        response = self.ask(scripted_router(["hw_datasheets"], "a pinout question", record=record))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(record, [(DATASHEET_QUESTION, {kb_id: info.description
                                                        for kb_id, info in KB_INFOS.items()})])
        self.assertEqual(body["question"], DATASHEET_QUESTION)
        self.assertEqual(body["answer"], "GPIO17 doubles as a UART pin [1].")
        self.assertFalse(body["no_answer"])
        self.assertFalse(body["off_topic"])
        self.assertEqual(body["kb_ids"], ["hw_datasheets"])
        self.assertEqual(body["route_reason"], "a pinout question")
        self.assertFalse(body["routing_fallback"])

        self.assertTrue(body["sources"])
        first = body["sources"][0]
        self.assertEqual(first["number"], 1)
        self.assertEqual(first["document"], "gpio.md")
        self.assertEqual(first["kb_id"], "hw_datasheets")
        self.assertIsNone(first["page_start"])
        self.assertIn("GPIO17", first["snippet"])
        self.assertTrue(first["cited"])
        self.assertEqual({source["kb_id"] for source in body["sources"]}, {"hw_datasheets"})
        self.assertLessEqual(len(body["sources"]), 10)

        self.assertEqual(body["usage"]["input_tokens"], 200)
        self.assertEqual(body["usage"]["output_tokens"], 40)
        self.assertEqual([call["step"] for call in body["usage"]["calls"]], ["route", "answer"])

        prompt, system_instruction = self.llm.calls[1]
        self.assertEqual(system_instruction, ANSWER_SYSTEM_INSTRUCTION)
        self.assertIn("knowledge base: hardware datasheets", prompt)
        self.assertNotIn("passwords", prompt)  # the policy KB wasn't routed
        self.assertTrue(prompt.endswith("Question: " + DATASHEET_QUESTION))

    def test_real_router_routes_from_a_json_reply_with_minimal_thinking(self):
        self.llm.replies = ['{"kb_ids": ["hw_datasheets"], "reason": "A pinout question."}',
                            "GPIO17 doubles as a UART pin [1]."]
        with TestClient(self.app) as client:
            self.ingest_both(client)
            response = client.post("/ask", json={"question": DATASHEET_QUESTION})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["kb_ids"], ["hw_datasheets"])
        self.assertEqual(body["route_reason"], "A pinout question.")
        self.assertFalse(body["routing_fallback"])
        self.assertEqual(body["answer"], "GPIO17 doubles as a UART pin [1].")
        self.assertEqual([call["step"] for call in body["usage"]["calls"]], ["route", "answer"])
        self.assertEqual(self.llm.thinking_levels, ["minimal", "minimal"])

    def test_thinking_levels_come_from_the_agent_config(self):
        with patch.dict(os.environ, {"GEMINI_ROUTER_THINKING": "low", "GEMINI_ANSWER_THINKING": "high"}):
            agent_config = AgentConfig()
        self.app = create_app(
            config=make_config(), status_repository=self.status_repository,
            upload_dir=os.path.join(self.directory, "uploads"), embedder=self.embedder,
            vector_index=self.app.state.vector_index, retrieval_config=make_retrieval_config(),
            llm=self.llm, agent_config=agent_config, kb_infos=KB_INFOS,
        )
        self.llm.replies = ['{"kb_ids": ["hw_datasheets"], "reason": "A pinout question."}',
                            "GPIO17 doubles as a UART pin [1]."]
        with TestClient(self.app) as client:
            self.ingest_both(client)
            response = client.post("/ask", json={"question": DATASHEET_QUESTION})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.llm.thinking_levels, ["low", "high"])

    def test_off_topic_question_lists_what_the_kbs_cover_without_retrieval_or_answer_call(self):
        with TestClient(self.app) as client:
            self.ingest_both(client)
            query_calls = len(self.embedder.query_calls)
            with patch("agent.agent_router.route", side_effect=scripted_router([], "sports trivia")):
                response = client.post("/ask", json={"question": "Who won the 1998 World Cup?"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["answer"], OFF_TOPIC_MESSAGE)
        self.assertTrue(body["no_answer"])
        self.assertTrue(body["off_topic"])
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["kb_ids"], [])
        self.assertEqual(body["route_reason"], "sports trivia")
        self.assertEqual(len(self.embedder.query_calls), query_calls)
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual([call["step"] for call in body["usage"]["calls"]], ["route"])

    def test_routing_fallback_searches_every_kb_and_is_flagged(self):
        response = self.ask(scripted_router(list(KB_IDS), "routing failed: bad reply", fallback=True))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["routing_fallback"])
        self.assertFalse(body["off_topic"])
        self.assertEqual(body["kb_ids"], list(KB_IDS))
        self.assertEqual({source["kb_id"] for source in body["sources"]}, set(KB_IDS))
        prompt = self.llm.calls[1][0]
        self.assertIn("knowledge base: IT policies", prompt)
        self.assertIn("knowledge base: hardware datasheets", prompt)

    def test_routed_kb_without_documents_gives_the_no_answer_reply_without_an_answer_call(self):
        response = self.ask(scripted_router(["hw_datasheets"]), ingest=False)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["no_answer"])
        self.assertFalse(body["off_topic"])
        self.assertEqual(body["answer"], NO_ANSWER_SENTENCE)
        self.assertEqual(body["sources"], [])
        self.assertEqual(len(self.llm.calls), 1)

    def test_no_answer_reply_from_the_llm_sets_the_flag(self):
        self.llm.replies = ["route reply", "The knowledge base doesn't contain this."]
        body = self.ask(scripted_router(["hw_datasheets"])).json()
        self.assertTrue(body["no_answer"])
        self.assertEqual(body["answer"], NO_ANSWER_SENTENCE)
        self.assertTrue(body["sources"])
        self.assertFalse(any(source["cited"] for source in body["sources"]))


class TestAskErrors(AskApiTestCase):
    def test_router_not_implemented_is_501_without_an_llm_call(self):
        # route() exists now, so a stand-in raises NotImplementedError to keep the 501 mapping covered.
        def not_implemented(question, kb_descriptions, llm, thinking=None):
            raise NotImplementedError("route() is not implemented yet")
        response = self.ask(not_implemented, ingest=False)
        body = self.assertCanonicalError(response, 501, "not_implemented")
        self.assertIn("route()", body["details"])
        self.assertEqual(self.llm.calls, [])

    def test_llm_unavailable_in_the_router_is_503_with_retry_after(self):
        self.llm.replies = [LlmUnavailableError("Gemini still unavailable after 4 attempt(s): 429")]
        with self.assertLogs("api.api_app", level="WARNING"):
            response = self.ask(scripted_router(["hw_datasheets"]), ingest=False)
        body = self.assertCanonicalError(response, 503, "llm_unavailable")
        self.assertIn("busy", body["message"])
        self.assertIn("try again", body["message"])
        self.assertEqual(response.headers["retry-after"], "30")

    def test_llm_unavailable_in_the_answer_step_is_503(self):
        self.llm.replies = ["route reply", LlmUnavailableError("busy")]
        with self.assertLogs("api.api_app", level="WARNING"):
            response = self.ask(scripted_router(["hw_datasheets"]))
        self.assertCanonicalError(response, 503, "llm_unavailable")

    def test_gemini_504_is_503_with_retry_after(self):
        # The real provider against a fake client: a 504 DEADLINE_EXCEEDED must reach /ask as "busy", not a 500.
        client = FakeClient(api_error(504, "DEADLINE_EXCEEDED"))
        self.app = create_app(
            config=make_config(), status_repository=self.status_repository,
            upload_dir=os.path.join(self.directory, "uploads"), embedder=self.embedder,
            vector_index=self.app.state.vector_index, retrieval_config=make_retrieval_config(),
            llm=GeminiLlm("test-key", "gemini-test", max_retries=0, client=client, sleep=lambda delay: None),
            kb_infos=KB_INFOS,
        )
        with self.assertLogs("api.api_app", level="WARNING"):
            response = self.ask(scripted_router(["hw_datasheets"]), ingest=False)
        self.assertCanonicalError(response, 503, "llm_unavailable")
        self.assertEqual(response.headers["retry-after"], "30")
        self.assertEqual(len(client.models.calls), 1)

    def test_other_llm_error_is_500(self):
        self.llm.replies = ["route reply", LlmError("Gemini request failed: 400 INVALID_ARGUMENT")]
        with self.assertLogs("api.api_app", level="ERROR"):
            response = self.ask(scripted_router(["hw_datasheets"]))
        body = self.assertCanonicalError(response, 500, "internal_failure")
        self.assertNotIn("INVALID_ARGUMENT", response.text)
        self.assertEqual(body["details"], "The language model call failed")

    def test_router_result_that_breaks_the_contract_is_500(self):
        broken_results = {
            "not a dict": ["hw_datasheets"],
            "unknown KB": {"kb_ids": ["hr_handbook"], "reason": "r", "fallback": False},
            "three KBs": {"kb_ids": ["it_policies", "hw_datasheets", "it_policies"], "reason": "r", "fallback": False},
            "duplicates": {"kb_ids": ["hw_datasheets", "hw_datasheets"], "reason": "r", "fallback": False},
            "kb_ids a string": {"kb_ids": "hw_datasheets", "reason": "r", "fallback": False},
            "missing reason": {"kb_ids": ["hw_datasheets"], "fallback": False},
            "fallback not bool": {"kb_ids": ["hw_datasheets"], "reason": "r", "fallback": "no"},
        }
        with TestClient(self.app) as client:
            for label, result in broken_results.items():
                with self.subTest(label):
                    with patch("agent.agent_router.route", return_value=result):
                        with self.assertLogs("api.api_app", level="ERROR"):
                            response = client.post("/ask", json={"question": DATASHEET_QUESTION})
                    body = self.assertCanonicalError(response, 500, "internal_failure")
                    self.assertIn("route() returned an invalid result", body["details"])

    def test_question_validation(self):
        with TestClient(self.app) as client:
            for payload in ({"question": "   "}, {}, {"question": "x" * 2001}):
                with self.subTest(payload=str(payload)[:40]):
                    self.assertCanonicalError(client.post("/ask", json=payload), 400, "validation_failed")
        self.assertEqual(self.llm.calls, [])


class TestKbDescriptions(AskApiTestCase):
    def test_kbs_lists_name_and_description(self):
        with TestClient(self.app) as client:
            kbs = client.get("/kbs").json()["kbs"]
        self.assertEqual([(kb["kb_id"], kb["name"], kb["description"]) for kb in kbs],
                         [(kb_id, KB_INFOS[kb_id].name, KB_INFOS[kb_id].description) for kb_id in KB_IDS])

    def test_default_descriptions_come_from_the_committed_file(self):
        app = create_app(
            config=make_config(), status_repository=self.status_repository,
            upload_dir=os.path.join(self.directory, "uploads2"), embedder=self.embedder,
            vector_index=self.app.state.vector_index, llm=self.llm,
        )
        self.assertEqual(app.state.kb_infos, KB_INFOS)

    def test_configured_kb_without_a_description_refuses_to_start(self):
        config = make_config()
        config.allowed_kb_ids = KB_IDS + ("hr_handbook",)
        with self.assertRaises(ValueError) as caught:
            create_app(config=config, status_repository=self.status_repository,
                       upload_dir=os.path.join(self.directory, "uploads3"), embedder=self.embedder,
                       vector_index=self.app.state.vector_index, llm=self.llm)
        self.assertIn("hr_handbook", str(caught.exception))

    def test_injected_kb_infos_are_used(self):
        infos = {"it_policies": KbInfo("it_policies", "Policies", "rules"),
                 "hw_datasheets": KbInfo("hw_datasheets", "Chips", "specs")}
        app = create_app(config=make_config(), status_repository=self.status_repository,
                         upload_dir=os.path.join(self.directory, "uploads4"), embedder=self.embedder,
                         vector_index=self.app.state.vector_index, llm=self.llm, kb_infos=infos)
        with TestClient(app) as client:
            kbs = client.get("/kbs").json()["kbs"]
        self.assertEqual([kb["description"] for kb in kbs], ["rules", "specs"])


if __name__ == "__main__":
    unittest.main()
