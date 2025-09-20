import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from autopost.common import limit_words_html


class LimitWordsHtmlTests(unittest.TestCase):
    def test_html_blocks_preserved_with_ellipsis(self):
        html = (
            "<p>One two three four five six seven eight nine ten.</p>\n"
            "<p>Eleven twelve thirteen fourteen fifteen sixteen.</p>\n"
            "<p>Seventeen eighteen nineteen twenty.</p>"
        )

        result = limit_words_html(html, max_words=16)

        self.assertEqual(
            result,
            (
                "<p>One two three four five six seven eight nine ten.</p>\n"
                "<p>Eleven twelve thirteen fourteen fifteen sixteen.</p>\n"
                "<p><em>…</em></p>"
            ),
        )

    def test_plaintext_paragraphs_trimmed_with_ellipsis(self):
        text = (
            "First paragraph has exactly eight distinct words here.\n\n"
            "Second paragraph comes next with several extra words included."
        )

        result = limit_words_html(text, max_words=10)

        self.assertEqual(
            result,
            "First paragraph has exactly eight distinct words here.\n\n…",
        )


if __name__ == "__main__":
    unittest.main()
