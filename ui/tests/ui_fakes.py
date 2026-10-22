"""A fake API client and sample API responses for the UI tests (no network)."""

import os
import sys

UI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if UI_DIR not in sys.path:
    sys.path.insert(0, UI_DIR)

KBS = [
    {"kb_id": "it_policies", "name": "IT policies", "description": "University IT policies and procedures.",
     "counts": {"queued": 0, "processing": 0, "success": 3, "failed": 1}, "total": 4},
    {"kb_id": "hw_datasheets", "name": "Hardware datasheets", "description": "Public hardware datasheets.",
     "counts": {"queued": 1, "processing": 0, "success": 4, "failed": 0}, "total": 5},
]


def document(name, status, failure_code=None, failure_reason=None, kb_id="it_policies"):
    terminal = status in ("success", "failed")
    return {
        "document_id": "doc-" + name, "kb_id": kb_id, "original_filename": name, "file_type": ".pdf",
        "file_size_bytes": 100, "ingestion_status": status, "upload_timestamp": "2026-10-22T10:00:00Z",
        "queued_at": "2026-10-22T10:00:00Z", "processing_at": None, "completed_at": None,
        "updated_at": "2026-10-22T10:00:05Z", "failure_reason": failure_reason, "failure_code": failure_code,
        "is_terminal": terminal, "should_poll": not terminal,
    }


def ask_result(**overrides):
    result = {
        "question": "What are the board dimensions of the Pico?",
        "answer": "The board is 51 × 21 mm [2].",
        "no_answer": False,
        "off_topic": False,
        "sources": [
            {"number": 1, "chunk_id": "c1", "document_id": "d1", "document": "pico-datasheet.pdf",
             "page_start": 4, "page_end": 4, "kb_id": "hw_datasheets", "snippet": "GPIO overview", "cited": False},
            {"number": 2, "chunk_id": "c2", "document_id": "d1", "document": "pico-datasheet.pdf",
             "page_start": 6, "page_end": 7, "kb_id": "hw_datasheets", "snippet": "51 × 21 mm PCB", "cited": True},
        ],
        "kb_ids": ["hw_datasheets"],
        "route_reason": "Board dimensions are in hardware datasheets.",
        "routing_fallback": False,
        "usage": {"input_tokens": 3593, "output_tokens": 56, "calls": [
            {"step": "route", "model": "gemini-3.5-flash-lite", "input_tokens": 363, "output_tokens": 28},
            {"step": "answer", "model": "gemini-3.5-flash-lite", "input_tokens": 3230, "output_tokens": 28},
        ]},
    }
    result.update(overrides)
    return result


class FakeClient:
    """Answers like ApiClient. errors maps a method name to the ApiClientError it raises."""

    def __init__(self, kbs=None, documents=None, upload_response=None, ask_response=None, errors=None):
        self.kbs = KBS if kbs is None else kbs
        self.documents = [] if documents is None else documents
        self.upload_response = upload_response
        self.ask_response = ask_response
        self.errors = errors or {}
        self.calls = []

    def _call(self, name, *args):
        self.calls.append((name,) + args)
        if name in self.errors:
            raise self.errors[name]

    def list_kbs(self):
        self._call("list_kbs")
        return self.kbs

    def list_documents(self, kb_id=None):
        self._call("list_documents", kb_id)
        return self.documents

    def upload(self, kb_id, files):
        self._call("upload", kb_id, files)
        return self.upload_response

    def ask(self, question):
        self._call("ask", question)
        return self.ask_response
