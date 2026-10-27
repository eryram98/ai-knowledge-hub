"""The Documents and Ask pages through Streamlit's AppTest, with the API client patched to a fake."""

import logging
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from streamlit.testing.v1 import AppTest

import ui_api_client
import ui_messages
from ui_api_client import KIND_BUSY, KIND_CONNECTION, ApiClientError
from ui_fakes import FakeClient, ask_result, document

UI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.join(UI_DIR, "app.py")
DOCUMENTS_PATH = os.path.join(UI_DIR, "views", "documents.py")
ASK_PATH = os.path.join(UI_DIR, "views", "ask.py")
TIMEOUT_SECONDS = 30

# AppTest runs pages without a browser session; Streamlit warns about that on every run.
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)


def all_text(at):
    """Every markdown, caption, alert and expander label on the page, joined."""
    parts = []
    for elements in (at.markdown, at.caption, at.info, at.warning, at.error, at.subheader, at.title):
        parts.extend(str(element.value) for element in elements)
    parts.extend(expander.label for expander in at.expander)
    return "\n".join(parts)


def dataframe_rows(at, index):
    return at.dataframe[index].value.to_dict("records")


class PageTestCase(unittest.TestCase):
    def run_page(self, path, client, session_state=None):
        patcher = mock.patch.object(ui_api_client, "get_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        at = AppTest.from_file(path, default_timeout=TIMEOUT_SECONDS)
        for key, value in (session_state or {}).items():
            at.session_state[key] = value
        at.run()
        self.assertFalse(at.exception, [getattr(e, "value", e) for e in at.exception])
        return at


class AppEntryTest(PageTestCase):
    def test_app_runs_the_documents_page_by_default(self):
        at = self.run_page(APP_PATH, FakeClient())
        self.assertIn("Documents", [title.value for title in at.title])
        self.assertIn("API: ", "\n".join(caption.value for caption in at.sidebar.caption))


class DocumentsPageTest(PageTestCase):
    def test_kb_overview_and_picker_show_names_and_descriptions(self):
        at = self.run_page(DOCUMENTS_PATH, FakeClient())
        overview = dataframe_rows(at, 0)
        self.assertEqual([row["Knowledge base"] for row in overview], ["IT policies", "Hardware datasheets"])
        self.assertEqual(overview[0]["Failed"], 1)
        self.assertEqual(overview[1]["Queued"], 1)
        picker = at.selectbox(key="docs_kb_id")
        self.assertEqual(picker.value, "it_policies")
        self.assertEqual(picker.format_func("hw_datasheets"), "Hardware datasheets")
        self.assertIn("University IT policies and procedures.", all_text(at))

    def test_status_table_shows_plain_language_failures(self):
        client = FakeClient(documents=[
            document("ok.pdf", "success"),
            document("scan.pdf", "failed", "empty_content", "Extracted text is empty"),
            document("old.pdf", "failed", "internal_failure", "interrupted by server restart"),
        ])
        at = self.run_page(DOCUMENTS_PATH, client)
        rows = dataframe_rows(at, 1)
        self.assertEqual([row["File"] for row in rows], ["ok.pdf", "scan.pdf", "old.pdf"])
        self.assertEqual(rows[0]["Status"], ui_messages.status_label("success"))
        self.assertEqual(rows[0]["Problem"], "")
        self.assertEqual(rows[1]["Problem"], ui_messages.ERROR_TEXT["empty_content"])
        self.assertEqual(rows[1]["Code"], "empty_content")
        self.assertIn("Upload the file again", rows[2]["Problem"])
        self.assertEqual(rows[0]["Uploaded"], "2026-10-22 10:00:00 UTC")
        self.assertIn(("list_documents", "it_policies"), client.calls)

    def test_polling_is_on_while_a_document_is_queued(self):
        at = self.run_page(DOCUMENTS_PATH, FakeClient(documents=[document("new.pdf", "queued")]))
        self.assertTrue(at.session_state["docs_polling"])
        self.assertIn("Refreshing every 2 s", all_text(at))

    def test_polling_turns_off_when_everything_is_terminal(self):
        at = self.run_page(DOCUMENTS_PATH, FakeClient(documents=[document("done.pdf", "success")]),
                           session_state={"docs_polling": True})
        self.assertFalse(at.session_state["docs_polling"])
        self.assertNotIn("Refreshing every", all_text(at))

    def test_empty_kb_has_an_empty_state(self):
        at = self.run_page(DOCUMENTS_PATH, FakeClient())
        self.assertIn("No documents in this knowledge base yet", all_text(at))

    def test_upload_shows_per_file_results_and_starts_polling(self):
        upload_response = {"files": [
            {"status": "accepted", "document_id": "d1", "metadata": {"original_filename": "a.txt"}, "error": None},
            {"status": "rejected", "document_id": None, "metadata": {"original_filename": "b.txt"},
             "error": {"code": "unreadable_file", "message": "File could not be read."}},
        ], "errors": []}
        client = FakeClient(upload_response=upload_response)
        at = self.run_page(DOCUMENTS_PATH, client)
        client.documents = [document("a.txt", "queued")]
        at.file_uploader[0].set_value([("a.txt", b"alpha", "text/plain"), ("b.txt", b"", "text/plain")])
        at.button[0].click()
        at.run()
        self.assertFalse(at.exception)
        upload_calls = [call for call in client.calls if call[0] == "upload"]
        self.assertEqual(len(upload_calls), 1)
        self.assertEqual(upload_calls[0][1], "it_policies")
        self.assertEqual([name for name, _content, _mime in upload_calls[0][2]], ["a.txt", "b.txt"])
        results = at.session_state["docs_upload_result"]["rows"]
        self.assertEqual([row["Result"] for row in results], ["✅ Accepted", "❌ Rejected"])
        self.assertEqual(results[1]["Reason"], ui_messages.ERROR_TEXT["unreadable_file"])
        self.assertIn("Last upload to IT policies", all_text(at))
        self.assertTrue(at.session_state["docs_polling"])

    def test_upload_without_files_warns(self):
        client = FakeClient()
        at = self.run_page(DOCUMENTS_PATH, client)
        at.button[0].click()
        at.run()
        self.assertIn("Choose at least one file first.", all_text(at))
        self.assertNotIn("upload", [call[0] for call in client.calls])

    def test_request_level_upload_error_is_shown(self):
        error = ApiClientError("api", "Upload batch exceeds the limit.", code="batch_limit_exceeded")
        at = self.run_page(DOCUMENTS_PATH, FakeClient(errors={"upload": error}))
        at.file_uploader[0].set_value(("a.txt", b"alpha", "text/plain"))
        at.button[0].click()
        at.run()
        self.assertIn(ui_messages.ERROR_TEXT["batch_limit_exceeded"], all_text(at))

    def delete_button(self, at):
        return next(button for button in at.button if button.label == "Delete document")

    def test_delete_needs_the_confirmation_then_calls_the_api(self):
        client = FakeClient(documents=[document("a.pdf", "success"), document("b.pdf", "success")])
        at = self.run_page(DOCUMENTS_PATH, client)
        self.assertTrue(self.delete_button(at).disabled)
        self.assertEqual(at.selectbox[1].options[0], "a.pdf (✅ Ready, uploaded 2026-10-22 10:00:00 UTC)")
        at.selectbox[1].select("doc-b.pdf")
        at.run()
        at.checkbox[0].check()
        at.run()
        self.assertFalse(self.delete_button(at).disabled)
        self.assertNotIn("delete_document", [call[0] for call in client.calls])
        self.delete_button(at).click()
        at.run()
        self.assertFalse(at.exception)
        self.assertIn(("delete_document", "it_policies", "doc-b.pdf"), client.calls)
        self.assertIn("Deleted b.pdf.", [success.value for success in at.success])
        self.assertFalse(at.checkbox[0].value)
        self.assertTrue(self.delete_button(at).disabled)
        self.assertEqual(at.selectbox[1].options, [at.selectbox[1].options[0]])

    def test_queued_or_processing_document_cannot_be_deleted(self):
        at = self.run_page(DOCUMENTS_PATH, FakeClient(documents=[document("a.pdf", "processing")]))
        self.assertIn("still processing", all_text(at))
        self.assertTrue(at.checkbox[0].disabled)
        self.assertTrue(self.delete_button(at).disabled)

    def test_nothing_to_delete_in_an_empty_kb(self):
        at = self.run_page(DOCUMENTS_PATH, FakeClient())
        self.assertIn("Nothing to delete in IT policies.", all_text(at))
        self.assertEqual([b.label for b in at.button if b.label == "Delete document"], [])

    def test_delete_errors_are_shown_in_plain_language(self):
        cases = (
            ("document_busy", 409, ui_messages.ERROR_TEXT["document_busy"], "error"),
            ("not_found", 404, "no longer exists", "info"),
        )
        for code, status_code, expected, level in cases:
            with self.subTest(code=code):
                error = ApiClientError("api", "api message", code=code, status_code=status_code)
                client = FakeClient(documents=[document("a.pdf", "success")], errors={"delete_document": error})
                at = self.run_page(DOCUMENTS_PATH, client)
                at.checkbox[0].check()
                at.run()
                self.delete_button(at).click()
                at.run()
                self.assertFalse(at.exception)
                shown = " ".join(str(element.value) for element in (at.error if level == "error" else at.info))
                self.assertIn(expected, shown)

    def test_api_down_shows_the_start_command(self):
        error = ApiClientError(KIND_CONNECTION, "Can't reach the API at http://127.0.0.1:8000.")
        at = self.run_page(DOCUMENTS_PATH, FakeClient(errors={"list_kbs": error}))
        self.assertIn("uvicorn", "\n".join(e.value for e in at.error))


class AskPageTest(PageTestCase):
    def ask(self, client, question="What are the board dimensions of the Pico?"):
        at = self.run_page(ASK_PATH, client)
        at.text_area[0].input(question)
        at.button[0].click()
        at.run()
        self.assertFalse(at.exception, [getattr(e, "value", e) for e in at.exception])
        return at

    def test_empty_state_names_the_kbs(self):
        at = self.run_page(ASK_PATH, FakeClient())
        self.assertIn("IT policies and Hardware datasheets", all_text(at))

    def test_answer_with_routing_sources_latency_and_usage(self):
        client = FakeClient(ask_response=ask_result())
        at = self.ask(client)
        text = all_text(at)
        self.assertIn(("ask", "What are the board dimensions of the Pico?"), client.calls)
        self.assertIn("Routed to Hardware datasheets", text)
        self.assertIn("Board dimensions are in hardware datasheets.", text)
        self.assertIn("The board is 51 × 21 mm [2].", text)
        self.assertNotIn("Off-topic", text)
        self.assertNotIn("fell back", text)
        labels = [expander.label for expander in at.expander]
        self.assertEqual(labels, [
            "[2] pico-datasheet.pdf · p. 6–7 · Hardware datasheets · Cited",
            "[1] pico-datasheet.pdf · p. 4 · Hardware datasheets · Not cited",
        ])
        self.assertIn("51 × 21 mm PCB", text)
        metrics = {metric.label: metric.value for metric in at.metric}
        self.assertTrue(metrics["Latency"].endswith(" s"))
        self.assertEqual(metrics["Input tokens"], "3,593")
        self.assertEqual(metrics["LLM calls"], "2")
        usage_rows = dataframe_rows(at, 0)
        self.assertEqual([row["Step"] for row in usage_rows], ["route", "answer"])

    def test_off_topic_badge(self):
        result = ask_result(off_topic=True, no_answer=True, kb_ids=[], sources=[],
                            route_reason="Sports aren't covered.", answer="I can answer questions about ...")
        result["usage"]["calls"] = result["usage"]["calls"][:1]
        text = all_text(self.ask(FakeClient(ask_response=result), "Who won the 1998 World Cup?"))
        self.assertIn("Off-topic", text)
        self.assertIn("Routed to no knowledge base", text)
        self.assertNotIn("No answer in the knowledge base", text)

    def test_fallback_and_no_answer_badges(self):
        result = ask_result(routing_fallback=True, no_answer=True, kb_ids=["it_policies", "hw_datasheets"])
        text = all_text(self.ask(FakeClient(ask_response=result)))
        self.assertIn("Routing fell back to all KBs", text)
        self.assertIn("No answer in the knowledge base", text)
        self.assertIn("Routed to IT policies, Hardware datasheets", text)

    def test_dollar_signs_stay_literal(self):
        result = ask_result(answer="It costs $4 or $5.")
        self.assertIn("It costs \\$4 or \\$5.", all_text(self.ask(FakeClient(ask_response=result))))

    def test_busy_llm_shows_a_try_again_warning(self):
        error = ApiClientError(KIND_BUSY, "busy", code="llm_unavailable", retry_after=30)
        at = self.ask(FakeClient(errors={"ask": error}))
        self.assertIn("Try again in about 30 s", "\n".join(w.value for w in at.warning))

    def test_connection_error_is_shown(self):
        error = ApiClientError(KIND_CONNECTION, "Can't reach the API at http://127.0.0.1:8000.")
        at = self.ask(FakeClient(errors={"ask": error, "list_kbs": error}))
        self.assertIn("uvicorn", "\n".join(e.value for e in at.error))

    def test_blank_question_warns_without_calling_the_api(self):
        client = FakeClient()
        at = self.ask(client, "   ")
        self.assertIn("Type a question first.", all_text(at))
        self.assertNotIn("ask", [call[0] for call in client.calls])


if __name__ == "__main__":
    unittest.main()
