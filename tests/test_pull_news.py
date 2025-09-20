import contextlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from autopost import pull_news


class ResolveCoverUrlTests(unittest.TestCase):
    def test_empty_cover_uses_fallback(self):
        fallback = pull_news.sanitize_img_url(pull_news.FALLBACK_COVER)
        self.assertTrue(fallback)
        self.assertEqual(pull_news.resolve_cover_url(""), fallback)

    def test_data_url_uses_fallback(self):
        fallback = pull_news.sanitize_img_url(pull_news.FALLBACK_COVER)
        self.assertEqual(
            pull_news.resolve_cover_url("data:image/png;base64,AAAA"),
            fallback,
        )

    def test_https_cover_kept(self):
        cover = "https://example.com/image.jpg"
        self.assertEqual(
            pull_news.resolve_cover_url(cover),
            pull_news.sanitize_img_url(cover),
        )
    def test_wordpress_date_path_unchanged(self):
        url = "https://example.com/2023/09/01/photo.jpg"
        self.assertEqual(pull_news.sanitize_img_url(url), url)


class FeedUrlParsingTests(unittest.TestCase):
    def test_inline_comment_in_feed_url_stripped(self):
        original_feeds = pull_news.FEEDS
        original_posts_json = pull_news.POSTS_JSON
        original_seen_db = pull_news.SEEN_DB
        original_data_dir = pull_news.DATA_DIR

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = pathlib.Path(tmpdir)
                feed_file = tmp_path / "feeds.txt"
                feed_file.write_text(
                    "Test|Sub|https://example.com/feed/   # comment\n",
                    encoding="utf-8",
                )

                pull_news.FEEDS = feed_file
                pull_news.DATA_DIR = tmp_path
                pull_news.POSTS_JSON = tmp_path / "posts.json"
                pull_news.SEEN_DB = tmp_path / "seen.json"

                fetched_urls = []

                def fake_fetch_bytes(url):
                    fetched_urls.append(url)
                    return b"<xml>"

                patchers = [
                    mock.patch.object(pull_news, "fetch_bytes", side_effect=fake_fetch_bytes),
                    mock.patch.object(pull_news, "parse_feed", return_value=[]),
                ]

                with contextlib.ExitStack() as stack:
                    for patcher in patchers:
                        stack.enter_context(patcher)
                    pull_news.main()

                self.assertEqual(fetched_urls, ["https://example.com/feed/"])
        finally:
            pull_news.FEEDS = original_feeds
            pull_news.POSTS_JSON = original_posts_json
            pull_news.SEEN_DB = original_seen_db
            pull_news.DATA_DIR = original_data_dir


class MaxPerFeedLimitTests(unittest.TestCase):
    def test_max_per_feed_limit(self):
        items = [
            {"title": f"Item {idx}", "link": f"https://example.com/article-{idx}", "summary": "", "element": None}
            for idx in range(3)
        ]

        original_feeds = pull_news.FEEDS
        original_posts_json = pull_news.POSTS_JSON
        original_seen_db = pull_news.SEEN_DB
        original_data_dir = pull_news.DATA_DIR
        original_max_per_feed = pull_news.MAX_PER_FEED
        original_hot_max_items = pull_news.HOT_MAX_ITEMS
        original_hot_page_size = pull_news.HOT_PAGE_SIZE

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = pathlib.Path(tmpdir)
                feed_file = tmp_path / "feeds.txt"
                feed_file.write_text("Test|Sub|https://example.com/feed\n", encoding="utf-8")

                pull_news.FEEDS = feed_file
                pull_news.DATA_DIR = tmp_path
                pull_news.POSTS_JSON = tmp_path / "posts.json"
                pull_news.SEEN_DB = tmp_path / "seen.json"
                pull_news.MAX_PER_FEED = 2
                pull_news.HOT_MAX_ITEMS = 10
                pull_news.HOT_PAGE_SIZE = 5

                patchers = [
                    mock.patch.object(pull_news, "fetch_bytes", return_value=b"<xml>"),
                    mock.patch.object(pull_news, "parse_feed", return_value=items),
                    mock.patch.object(pull_news, "extract_body_html", return_value=("<p>Body</p>", "")),
                    mock.patch.object(pull_news, "find_cover_from_item", return_value=""),
                ]
                with contextlib.ExitStack() as stack:
                    for patcher in patchers:
                        stack.enter_context(patcher)
                    pull_news.main()

                data = json.loads(pull_news.POSTS_JSON.read_text(encoding="utf-8"))
                self.assertEqual(len(data), 2)

                hot_path = tmp_path / "hot" / "test" / "sub" / "index.json"
                self.assertTrue(hot_path.exists())
                hot_payload = json.loads(hot_path.read_text(encoding="utf-8"))
                self.assertEqual(hot_payload["count"], 2)
                self.assertEqual(len(hot_payload["items"]), 2)
                slugs = [item["slug"] for item in hot_payload["items"]]
                self.assertEqual(len(slugs), len(set(slugs)))
                self.assertEqual(hot_payload["pagination"], {
                    "total_items": 2,
                    "per_page": 5,
                    "total_pages": 1,
                })
        finally:
            pull_news.FEEDS = original_feeds
            pull_news.POSTS_JSON = original_posts_json
            pull_news.SEEN_DB = original_seen_db
            pull_news.DATA_DIR = original_data_dir
            pull_news.MAX_PER_FEED = original_max_per_feed
            pull_news.HOT_MAX_ITEMS = original_hot_max_items
            pull_news.HOT_PAGE_SIZE = original_hot_page_size

if __name__ == "__main__":
    unittest.main()
