"""Upload storage helpers for the HTTP API: filename sanitizer, safe paths, size-limited copy."""

import asyncio
import io
import os
import sys
import tempfile
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from starlette.datastructures import UploadFile

from api.api_uploads import (
    FALLBACK_FILENAME,
    MAX_FILENAME_CHARS,
    remove_upload_dir,
    sanitize_filename,
    save_upload,
    upload_path,
)


class TestSanitizeFilename(unittest.TestCase):
    def test_directory_parts_are_dropped(self):
        cases = {
            "../../etc/passwd.txt": "passwd.txt",
            "..\\..\\boot.ini.md": "boot.ini.md",
            "C:\\Windows\\System32\\evil.pdf": "evil.pdf",
            "/abs/path/report.pdf": "report.pdf",
            "dir/sub\\mixed.txt": "mixed.txt",
        }
        for raw, expected in cases.items():
            self.assertEqual(sanitize_filename(raw), expected, raw)

    def test_plain_names_are_kept(self):
        for name in ("report.pdf", "Q3 results v2.md", "naïve-notes.txt"):
            self.assertEqual(sanitize_filename(name), name)

    def test_unsafe_and_control_characters_are_replaced(self):
        self.assertEqual(sanitize_filename('a<b>c:"d|e?f*.txt'), "a_b_c__d_e_f_.txt")
        self.assertEqual(sanitize_filename("tab\there\x00.txt"), "tab_here_.txt")
        self.assertEqual(sanitize_filename("file.txt:stream"), "file.txt_stream")

    def test_leading_and_trailing_dots_and_spaces_are_stripped(self):
        self.assertEqual(sanitize_filename("  notes.txt. . "), "notes.txt")
        self.assertEqual(sanitize_filename(".hidden.md"), "hidden.md")

    def test_empty_or_dot_only_names_fall_back(self):
        for raw in ("", "   ", ".", "..", "../..", "/", None, 42):
            self.assertEqual(sanitize_filename(raw), FALLBACK_FILENAME, repr(raw))

    def test_windows_device_names_are_prefixed(self):
        self.assertEqual(sanitize_filename("CON.txt"), "_CON.txt")
        self.assertEqual(sanitize_filename("nul"), "_nul")
        self.assertEqual(sanitize_filename("com1.tar.md"), "_com1.tar.md")
        self.assertEqual(sanitize_filename("console.txt"), "console.txt")

    def test_long_names_are_capped_and_keep_the_extension(self):
        name = sanitize_filename("a" * 400 + ".pdf")
        self.assertEqual(len(name), MAX_FILENAME_CHARS)
        self.assertTrue(name.endswith(".pdf"))
        self.assertLessEqual(len(sanitize_filename("b." + "c" * 400)), MAX_FILENAME_CHARS)


class TestUploadPath(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = directory.name

    def test_path_is_root_document_file(self):
        path = upload_path(self.root, "doc-1", "a.txt")
        self.assertEqual(path, os.path.join(os.path.realpath(self.root), "doc-1", "a.txt"))

    def test_escaping_paths_are_refused(self):
        for document_id, file_name in (("..", "a.txt"), ("doc-1", "../a.txt"), ("doc-1", "sub/a.txt")):
            with self.assertRaises(ValueError, msg=(document_id, file_name)):
                upload_path(self.root, document_id, file_name)


class TestSaveUpload(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = directory.name

    def save(self, content, max_bytes):
        destination = os.path.join(self.root, "doc-1", "a.txt")
        upload = UploadFile(io.BytesIO(content), filename="a.txt")
        return destination, asyncio.run(save_upload(upload, destination, max_bytes))

    def test_file_at_the_limit_is_copied(self):
        destination, (size, too_large) = self.save(b"x" * 100, 100)
        self.assertEqual((size, too_large), (100, False))
        with open(destination, "rb") as handle:
            self.assertEqual(handle.read(), b"x" * 100)

    def test_file_over_the_limit_is_deleted(self):
        destination, (size, too_large) = self.save(b"x" * 101, 100)
        self.assertTrue(too_large)
        self.assertGreater(size, 100)
        self.assertFalse(os.path.exists(destination))

    def test_remove_upload_dir_deletes_and_ignores_missing(self):
        destination, _ = self.save(b"abc", 10)
        remove_upload_dir(self.root, "doc-1")
        self.assertFalse(os.path.exists(os.path.dirname(destination)))
        remove_upload_dir(self.root, "doc-1")


if __name__ == "__main__":
    unittest.main()
