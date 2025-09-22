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
        original_headline_json = pull_news.HEADLINE_JSON

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
                pull_news.HEADLINE_JSON = tmp_path / "headline.json"

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
                legacy_index = tmp_path / "legacy" / "index.json"
                self.assertTrue(legacy_index.exists())
                payload = json.loads(legacy_index.read_text(encoding="utf-8"))
                self.assertIsInstance(payload.get("items"), (dict, type(None)))
        finally:
            pull_news.FEEDS = original_feeds
            pull_news.POSTS_JSON = original_posts_json
            pull_news.SEEN_DB = original_seen_db
            pull_news.DATA_DIR = original_data_dir
            pull_news.HEADLINE_JSON = original_headline_json


class CategoryFilterNormalizationTests(unittest.TestCase):
    def test_category_filter_accepts_mixed_case_labels(self):
        items = [
            {
                "title": "Crypto Headline",
                "link": "https://example.com/article",
                "summary": "",
                "element": None,
            }
        ]

        original_feeds = pull_news.FEEDS
        original_posts_json = pull_news.POSTS_JSON
        original_seen_db = pull_news.SEEN_DB
        original_data_dir = pull_news.DATA_DIR
        original_category = pull_news.CATEGORY
        original_headline_json = pull_news.HEADLINE_JSON

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = pathlib.Path(tmpdir)
                feed_file = tmp_path / "feeds.txt"
                feed_file.write_text("crypto|https://example.com/feed\n", encoding="utf-8")

                pull_news.FEEDS = feed_file
                pull_news.DATA_DIR = tmp_path
                pull_news.POSTS_JSON = tmp_path / "posts.json"
                pull_news.SEEN_DB = tmp_path / "seen.json"
                pull_news.CATEGORY = "CRYPTO"
                pull_news.HEADLINE_JSON = tmp_path / "headline.json"

                patchers = [
                    mock.patch.object(pull_news, "fetch_bytes", return_value=b"<xml>"),
                    mock.patch.object(pull_news, "parse_feed", return_value=items),
                    mock.patch.object(
                        pull_news,
                        "extract_body_html",
                        return_value=("<p>Body</p>", ""),
                    ),
                    mock.patch.object(pull_news, "pick_largest_media_url", return_value=""),
                    mock.patch.object(pull_news, "find_cover_from_item", return_value=""),
                    mock.patch.object(pull_news, "_update_hot_shards"),
                ]

                with contextlib.ExitStack() as stack:
                    for patcher in patchers:
                        stack.enter_context(patcher)
                    new_entries = pull_news._run_autopost()

                self.assertEqual(len(new_entries), 1)
                self.assertEqual(new_entries[0]["category"], "Crypto")
                legacy_index = tmp_path / "legacy" / "index.json"
                self.assertTrue(legacy_index.exists())
                lookup = json.loads(legacy_index.read_text(encoding="utf-8"))
                self.assertIn(new_entries[0]["slug"], lookup.get("items", {}))
        finally:
            pull_news.FEEDS = original_feeds
            pull_news.POSTS_JSON = original_posts_json
            pull_news.SEEN_DB = original_seen_db
            pull_news.DATA_DIR = original_data_dir
            pull_news.CATEGORY = original_category
            pull_news.HEADLINE_JSON = original_headline_json


class EmptyBodySkipTests(unittest.TestCase):
    def test_empty_body_item_skipped_without_touching_posts_index(self):
        items = [
            {
                "title": "Empty Body",
                "link": "https://example.com/article-empty",
                "summary": "",
                "element": None,
            }
        ]

        existing_entry = {
            "slug": "existing-entry",
            "title": "Existing Story",
            "category": "Existing",
            "subcategory": "Existing Sub",
            "category_slug": "existing/existing-sub",
            "date": "2024-01-01T00:00:00Z",
            "excerpt": "Existing excerpt",
            "cover": "",
            "source": "https://example.com/original",
            "source_domain": "example.com",
            "source_name": "Existing",
            "author": "Author",
            "rights": "All rights reserved",
            "body": "<p>Existing body</p>",
            "canonical": "https://archive.example/existing-entry/",
        }

        original_feeds = pull_news.FEEDS
        original_posts_json = pull_news.POSTS_JSON
        original_seen_db = pull_news.SEEN_DB
        original_data_dir = pull_news.DATA_DIR
        original_headline_json = pull_news.HEADLINE_JSON

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = pathlib.Path(tmpdir)
                feed_file = tmp_path / "feeds.txt"
                feed_file.write_text("Test|Sub|https://example.com/feed\n", encoding="utf-8")

                pull_news.FEEDS = feed_file
                pull_news.DATA_DIR = tmp_path
                pull_news.POSTS_JSON = tmp_path / "posts.json"
                pull_news.SEEN_DB = tmp_path / "seen.json"
                pull_news.HEADLINE_JSON = tmp_path / "headline.json"

                pull_news.POSTS_JSON.write_text(
                    json.dumps([existing_entry], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                patchers = [
                    mock.patch.object(pull_news, "fetch_bytes", return_value=b"<xml>"),
                    mock.patch.object(pull_news, "parse_feed", return_value=items),
                    mock.patch.object(pull_news, "extract_body_html", return_value=("", "")),
                ]

                with contextlib.ExitStack() as stack:
                    for patcher in patchers:
                        stack.enter_context(patcher)
                    before = pull_news.POSTS_JSON.read_text(encoding="utf-8")
                    new_entries = pull_news._run_autopost()
                    after = pull_news.POSTS_JSON.read_text(encoding="utf-8")

                self.assertEqual(new_entries, [])
                self.assertEqual(after, before)
                self.assertEqual(json.loads(after), [existing_entry])
        finally:
            pull_news.FEEDS = original_feeds
            pull_news.POSTS_JSON = original_posts_json
            pull_news.SEEN_DB = original_seen_db
            pull_news.DATA_DIR = original_data_dir
            pull_news.HEADLINE_JSON = original_headline_json


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
        original_headline_json = pull_news.HEADLINE_JSON

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
                pull_news.HEADLINE_JSON = tmp_path / "headline.json"

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
                legacy_index = tmp_path / "legacy" / "index.json"
                self.assertTrue(legacy_index.exists())
                lookup = json.loads(legacy_index.read_text(encoding="utf-8"))
                items_lookup = lookup.get("items", {})
                self.assertEqual(len(items_lookup), 2)
                self.assertEqual(lookup.get("count"), len(items_lookup))
                self.assertTrue(items_lookup)
                for record in items_lookup.values():
                    self.assertIn("canonical", record)
                    self.assertIn("archive_path", record)
                    self.assertIn("parent", record)
                    self.assertIn("child", record)

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

                headline_path = tmp_path / "headline.json"
                self.assertTrue(headline_path.exists())
                headline_payload = json.loads(headline_path.read_text(encoding="utf-8"))
                self.assertEqual(len(headline_payload), 2)
                self.assertEqual(
                    [item["slug"] for item in headline_payload],
                    [item["slug"] for item in data[:2]],
                )
                for entry in headline_payload:
                    self.assertEqual(
                        ["category", "cover", "date", "slug", "title"],
                        sorted(entry.keys()),
                    )
        finally:
            pull_news.FEEDS = original_feeds
            pull_news.POSTS_JSON = original_posts_json
            pull_news.SEEN_DB = original_seen_db
            pull_news.DATA_DIR = original_data_dir
            pull_news.MAX_PER_FEED = original_max_per_feed
            pull_news.HOT_MAX_ITEMS = original_hot_max_items
            pull_news.HOT_PAGE_SIZE = original_hot_page_size
            pull_news.HEADLINE_JSON = original_headline_json

if __name__ == "__main__":
    unittest.main()
