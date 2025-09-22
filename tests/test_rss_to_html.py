import importlib
import os
import unittest
from unittest import mock

from autopost import rss_to_html


class FeedResolutionTests(unittest.TestCase):
    def test_default_feeds_file_is_present(self):
        original_env = os.environ.get("FEEDS_FILE")
        module = rss_to_html

        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                module = importlib.reload(module)

            expected = module.ROOT / "autopost" / "feeds_news.txt"
            self.assertEqual(module.FEEDS, expected)
            self.assertTrue(
                module.FEEDS.exists(),
                f"Default feeds file missing: {module.FEEDS}",
            )
        finally:
            if original_env is None:
                os.environ.pop("FEEDS_FILE", None)
            else:
                os.environ["FEEDS_FILE"] = original_env
            importlib.reload(module)


if __name__ == "__main__":
    unittest.main()
