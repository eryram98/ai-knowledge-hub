"""ApiClient against httpx.MockTransport: success paths and every failure kind."""

import json
import os
import sys
import unittest

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui_api_client import (
    KIND_API,
    KIND_BUSY,
    KIND_CONNECTION,
    KIND_TIMEOUT,
    ApiClient,
    ApiClientError,
)

BASE_URL = "http://api.test"


def client_with(handler):
    return ApiClient(BASE_URL + "/", transport=httpx.MockTransport(handler))


def canonical(status_code, code, message, details=None, headers=None):
    body = {"code": code, "message": message, "details": details}
    return httpx.Response(status_code, json=body, headers=headers)


class ApiClientSuccessTest(unittest.TestCase):
    def test_list_kbs_returns_the_kbs_list(self):
        seen = []

        def handler(request):
            seen.append((request.method, str(request.url)))
            return httpx.Response(200, json={"kbs": [{"kb_id": "it_policies"}]})

        self.assertEqual(client_with(handler).list_kbs(), [{"kb_id": "it_policies"}])
        self.assertEqual(seen, [("GET", BASE_URL + "/kbs")])

    def test_list_documents_filters_by_kb(self):
        seen = []

        def handler(request):
            seen.append(request.url.params.get("kb_id"))
            return httpx.Response(200, json={"documents": []})

        self.assertEqual(client_with(handler).list_documents("hw_datasheets"), [])
        self.assertEqual(seen, ["hw_datasheets"])

    def test_document_statuses_repeats_document_id(self):
        seen = []

        def handler(request):
            seen.append((request.url.path, request.url.params.get_list("document_id")))
            return httpx.Response(200, json={"documents": [], "is_complete": True})

        self.assertTrue(client_with(handler).document_statuses(["a", "b"])["is_complete"])
        self.assertEqual(seen, [("/documents/status", ["a", "b"])])

    def test_upload_sends_kb_id_and_every_file_as_multipart(self):
        bodies = []

        def handler(request):
            bodies.append((request.headers["content-type"], request.read()))
            return httpx.Response(202, json={"files": [], "errors": []})

        client_with(handler).upload("it_policies", [("a.txt", b"alpha", "text/plain"), ("b.md", b"beta", None)])
        content_type, body = bodies[0]
        self.assertTrue(content_type.startswith("multipart/form-data"))
        self.assertIn(b'name="kb_id"', body)
        self.assertIn(b"it_policies", body)
        self.assertEqual(body.count(b'name="files"'), 2)
        self.assertIn(b'filename="a.txt"', body)
        self.assertIn(b'filename="b.md"', body)
        self.assertIn(b"alpha", body)

    def test_ask_posts_the_question_as_json(self):
        bodies = []

        def handler(request):
            bodies.append(json.loads(request.read()))
            return httpx.Response(200, json={"answer": "42"})

        self.assertEqual(client_with(handler).ask("why?"), {"answer": "42"})
        self.assertEqual(bodies, [{"question": "why?"}])


class ApiClientFailureTest(unittest.TestCase):
    def assert_raises_kind(self, handler, kind, call=lambda client: client.list_kbs()):
        with self.assertRaises(ApiClientError) as caught:
            call(client_with(handler))
        self.assertEqual(caught.exception.kind, kind)
        return caught.exception

    def test_llm_unavailable_is_busy_with_retry_after(self):
        def handler(request):
            return canonical(503, "llm_unavailable", "busy", headers={"Retry-After": "30"})

        error = self.assert_raises_kind(handler, KIND_BUSY, call=lambda client: client.ask("q"))
        self.assertEqual(error.retry_after, 30)
        self.assertEqual(error.status_code, 503)

    def test_unparseable_retry_after_is_none(self):
        def handler(request):
            return canonical(503, "llm_unavailable", "busy", headers={"Retry-After": "soon"})

        self.assertIsNone(self.assert_raises_kind(handler, KIND_BUSY).retry_after)

    def test_connection_error(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        error = self.assert_raises_kind(handler, KIND_CONNECTION)
        self.assertIn(BASE_URL, error.message)

    def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        self.assert_raises_kind(handler, KIND_TIMEOUT, call=lambda client: client.ask("q"))

    def test_canonical_errors_are_parsed(self):
        for status_code, code in ((400, "unknown_kb"), (413, "file_too_large"), (500, "internal_failure")):
            with self.subTest(code=code):
                def handler(request, status_code=status_code, code=code):
                    return canonical(status_code, code, "msg " + code, details="detail")

                error = self.assert_raises_kind(handler, KIND_API)
                self.assertEqual((error.code, error.message, error.details, error.status_code),
                                 (code, "msg " + code, "detail", status_code))

    def test_non_json_error_body_falls_back(self):
        def handler(request):
            return httpx.Response(502, text="Bad Gateway")

        error = self.assert_raises_kind(handler, KIND_API)
        self.assertIsNone(error.code)
        self.assertIn("502", error.message)

    def test_non_json_success_body_is_an_error(self):
        def handler(request):
            return httpx.Response(200, text="<html>")

        self.assert_raises_kind(handler, KIND_API)


if __name__ == "__main__":
    unittest.main()
