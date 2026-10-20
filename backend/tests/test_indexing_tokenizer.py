"""BM25 tokenizer (F2): lowercases but keeps technical identifiers whole."""

import os
import sys
import unittest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from indexing.indexing_keyword_index import tokenize


class TestTokenize(unittest.TestCase):
    def test_identifiers_stay_whole(self):
        self.assertEqual(tokenize("gpio17 ac-2 3.3v rp2040 uart_tx"), ["gpio17", "ac-2", "3.3v", "rp2040", "uart_tx"])

    def test_lowercases(self):
        self.assertEqual(tokenize("GPIO17 on the RP2040"), ["gpio17", "on", "the", "rp2040"])

    def test_strips_surrounding_punctuation(self):
        self.assertEqual(tokenize("(gpio17), ac-2. 3.3v; rp2040! \"quoted\""),
                         ["gpio17", "ac-2", "3.3v", "rp2040", "quoted"])

    def test_sentence_end_dot_and_dash_are_not_part_of_the_token(self):
        self.assertEqual(tokenize("Pin 3.3v. Then - next -dash"), ["pin", "3.3v", "then", "next", "dash"])

    def test_no_split_on_internal_dot_or_dash(self):
        self.assertEqual(tokenize("v1.5.2 ac-2-b"), ["v1.5.2", "ac-2-b"])

    def test_empty_and_punctuation_only(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(None), [])
        self.assertEqual(tokenize(" ... -- !! "), [])


if __name__ == "__main__":
    unittest.main()
