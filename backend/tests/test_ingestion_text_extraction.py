import os
import shutil
import sys
import tempfile
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
APP_DIR = os.path.join(BACKEND_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ingestion.ingestion_error_model import (
    ERROR_EXTRACTION_FAILURE,
    ERROR_INTERNAL_FAILURE,
    ERROR_UNREADABLE_FILE,
    ERROR_UNSUPPORTED_FORMAT,
)
from ingestion.ingestion_stage_contracts import (
    EXTRACTION_REQUIRED_METHODS,
    ensure_contract_implemented,
)
from ingestion.ingestion_text_extraction import (
    ExtractionError,
    TextExtractionDispatcher,
    decode_bytes,
    map_extraction_exception,
    normalize_file_type,
    normalize_text,
)

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from pdf_fixtures import HAS_PYPDF, build_pdf


class TextExtractionTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.dispatcher = TextExtractionDispatcher()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def write(self, name, data):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path


class TestDispatcher(TextExtractionTestBase):
    def test_dispatcher_satisfies_extraction_contract(self):
        is_valid, errors = ensure_contract_implemented(self.dispatcher, EXTRACTION_REQUIRED_METHODS)
        self.assertTrue(is_valid, errors)

    def test_file_type_normalization(self):
        for raw in (".PDF", "pdf", " .pdf "):
            self.assertEqual(normalize_file_type(raw), ".pdf")
        self.assertEqual(normalize_file_type(None), "")

    def test_routes_by_extension_case_insensitive(self):
        path = self.write("a.txt", b"hello")
        result = self.dispatcher.extract_text(path, "TXT")
        self.assertEqual(result["full_text"], "hello")
        self.assertEqual(result["metadata"]["extractor"], "txt-decode")

    def test_unsupported_type_raises_canonical_code(self):
        path = self.write("a.docx", b"x")
        with self.assertRaises(ExtractionError) as ctx:
            self.dispatcher.extract_text(path, ".docx")
        self.assertEqual(ctx.exception.error_code, ERROR_UNSUPPORTED_FORMAT)

    def test_missing_file_is_unreadable(self):
        with self.assertRaises(ExtractionError) as ctx:
            self.dispatcher.extract_text(os.path.join(self.tmp_dir, "nope.txt"), ".txt")
        self.assertEqual(ctx.exception.error_code, ERROR_UNREADABLE_FILE)

    def test_register_replaces_extractor(self):
        class Fake(object):
            def extract_text(self, file_path, file_type):
                return {"full_text": "fake", "metadata": {"extractor": "fake"}}

        self.dispatcher.register("pdf", Fake())
        result = self.dispatcher.extract_text("ignored.pdf", ".pdf")
        self.assertEqual(result["full_text"], "fake")

    def test_register_rejects_non_extractor(self):
        with self.assertRaises(TypeError):
            self.dispatcher.register(".txt", object())

    def test_unexpected_extractor_exception_is_wrapped(self):
        class Broken(object):
            def extract_text(self, file_path, file_type):
                raise RuntimeError("boom")

        self.dispatcher.register(".txt", Broken())
        with self.assertRaises(ExtractionError) as ctx:
            self.dispatcher.extract_text("x.txt", ".txt")
        self.assertEqual(ctx.exception.error_code, ERROR_EXTRACTION_FAILURE)
        self.assertIn("boom", str(ctx.exception))

    def test_invalid_payload_rejected(self):
        class BadPayload(object):
            def extract_text(self, file_path, file_type):
                return {"text": "wrong key"}

        self.dispatcher.register(".txt", BadPayload())
        with self.assertRaises(ExtractionError):
            self.dispatcher.extract_text("x.txt", ".txt")


class TestTxtExtraction(TextExtractionTestBase):
    def test_utf8(self):
        path = self.write("u.txt", u"café – résumé".encode("utf-8"))
        result = self.dispatcher.extract_text(path, ".txt")
        self.assertEqual(result["full_text"], u"café – résumé")
        self.assertEqual(result["metadata"]["encoding"], "utf-8")

    def test_utf8_bom_removed(self):
        path = self.write("b.txt", b"\xef\xbb\xbfhello")
        result = self.dispatcher.extract_text(path, ".txt")
        self.assertEqual(result["full_text"], "hello")
        self.assertEqual(result["metadata"]["encoding"], "utf-8-sig")

    def test_utf16_with_bom(self):
        path = self.write("w.txt", u"hello world".encode("utf-16"))
        result = self.dispatcher.extract_text(path, ".txt")
        self.assertEqual(result["full_text"], "hello world")

    def test_windows_1252_fallback(self):
        path = self.write("c.txt", b"smart \x93quotes\x94")
        result = self.dispatcher.extract_text(path, ".txt")
        self.assertEqual(result["full_text"], u"smart “quotes”")
        self.assertEqual(result["metadata"]["encoding"], "cp1252")

    def test_empty_file_succeeds_and_is_flagged(self):
        path = self.write("e.txt", b"")
        result = self.dispatcher.extract_text(path, ".txt")
        self.assertEqual(result["full_text"], "")
        self.assertTrue(result["metadata"]["is_empty"])

    def test_decode_never_fails(self):
        text, encoding = decode_bytes(bytes(bytearray(range(256))))
        self.assertTrue(isinstance(text, str))
        self.assertIn(encoding, ("cp1252", "latin-1"))


class TestMarkdownExtraction(TextExtractionTestBase):
    MD = (
        "# Title\r\n\r\nLine with hard break  \r\nnext\r\n\r\n\r\n\r\n"
        "| Supplier | Price |\r\n|---|---|\r\n| A | $10 |\r\n"
    )

    def test_raw_markdown_preserved(self):
        path = self.write("d.md", self.MD.encode("utf-8"))
        result = self.dispatcher.extract_text(path, ".md")
        text = result["full_text"]
        self.assertIn("# Title", text)
        self.assertIn("| A | $10 |", text)
        self.assertIn("hard break  \n", text)  # trailing double space kept
        self.assertNotIn("\r", text)
        self.assertEqual(result["metadata"]["heading_count"], 1)
        self.assertEqual(result["metadata"]["pipe_table_rows"], 3)


@unittest.skipUnless(HAS_PYPDF, "pypdf not installed")
class TestPdfExtraction(TextExtractionTestBase):
    def test_multi_page_text_and_page_spans(self):
        path = self.write("p.pdf", build_pdf(["First page text", "Second page text"]))
        result = self.dispatcher.extract_text(path, ".pdf")
        text = result["full_text"]
        meta = result["metadata"]
        self.assertEqual(meta["page_count"], 2)
        spans = meta["page_spans"]
        self.assertEqual(text[spans[0]["start"]:spans[0]["end"]], "First page text")
        self.assertEqual(text[spans[1]["start"]:spans[1]["end"]], "Second page text")

    def test_blank_page_counted(self):
        path = self.write("p.pdf", build_pdf(["Has text", ""]))
        result = self.dispatcher.extract_text(path, ".pdf")
        self.assertEqual(result["metadata"]["empty_page_count"], 1)

    def test_no_text_layer_fails_with_ocr_message(self):
        path = self.write("scan.pdf", build_pdf(["", ""]))
        with self.assertRaises(ExtractionError) as ctx:
            self.dispatcher.extract_text(path, ".pdf")
        self.assertEqual(ctx.exception.error_code, ERROR_EXTRACTION_FAILURE)
        self.assertIn("OCR", str(ctx.exception))

    def test_corrupt_pdf_is_unreadable(self):
        path = self.write("bad.pdf", b"this is not a pdf")
        with self.assertRaises(ExtractionError) as ctx:
            self.dispatcher.extract_text(path, ".pdf")
        self.assertIn(ctx.exception.error_code, (ERROR_UNREADABLE_FILE, ERROR_EXTRACTION_FAILURE))


class TestNormalizationAndErrorMapping(unittest.TestCase):
    def test_normalize_text(self):
        raw = u"a  \r\nb\x00\r\n\r\n\r\n\r\ncé"
        self.assertEqual(normalize_text(raw), u"a\nb\n\ncé")

    def test_normalize_collapses_inner_spaces(self):
        self.assertEqual(normalize_text(u"two  words\tand\t\ttabs"), u"two words\tand tabs")

    def test_normalize_none(self):
        self.assertEqual(normalize_text(None), "")

    def test_map_extraction_error(self):
        payload = map_extraction_exception(ExtractionError(ERROR_UNSUPPORTED_FORMAT, "nope"), file_name="x.doc")
        self.assertEqual(payload["code"], ERROR_UNSUPPORTED_FORMAT)
        self.assertEqual(payload["details"], "nope")
        self.assertEqual(payload["file_name"], "x.doc")

    def test_map_os_error(self):
        self.assertEqual(map_extraction_exception(OSError("denied"))["code"], ERROR_UNREADABLE_FILE)

    def test_map_unknown_error(self):
        self.assertEqual(map_extraction_exception(KeyError("k"))["code"], ERROR_INTERNAL_FAILURE)


if __name__ == "__main__":
    unittest.main()
