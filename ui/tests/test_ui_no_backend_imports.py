"""The UI is an HTTP-only client: no file under ui/ may import a backend package."""

import ast
import os
import unittest

UI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_PACKAGES = {"ingestion", "agent", "api", "indexing", "retrieval", "backend"}


def imported_top_level_names(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


class NoBackendImportsTest(unittest.TestCase):
    def test_no_ui_module_imports_the_backend(self):
        checked = 0
        for root, _dirs, files in os.walk(UI_DIR):
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(root, name)
                    checked += 1
                    with self.subTest(path=os.path.relpath(path, UI_DIR)):
                        self.assertFalse(set(imported_top_level_names(path)) & BACKEND_PACKAGES)
        self.assertGreater(checked, 5)


if __name__ == "__main__":
    unittest.main()
