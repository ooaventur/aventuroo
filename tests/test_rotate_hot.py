import datetime
import gzip
import json
import math
import pathlib
import tempfile
import unittest

from autopost import rotate_hot


class RotateHotTests(unittest.TestCase):
    def _write_hot(self, base: pathlib.Path, relative: str, items: list[dict]) -> pathlib.Path:
        shard_dir = base / relative
        shard_dir.mkdir(parents=True, exist_ok=True)
        per_page = 12
        payload = {
            "items": items,
            "count": len(items),
            "updated_at": "2024-05-01",
            "pagination": {
                "total_items": len(items),
                "per_page": per_page,
                "total_pages": math.ceil(len(items) / per_page) if per_page else 0,
            },
        }
        shard_path = shard_dir / "index.json"
        shard_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return shard_path

    def _write_archive(self, base: pathlib.Path, relative: str, year: int, month: int, items: list[dict]) -> pathlib.Path:
        bucket_dir = base / relative / f"{year:04d}" / f"{month:02d}"
        bucket_dir.mkdir(parents=True, exist_ok=True)
        per_page = 12
        payload = {
            "items": items,
            "count": len(items),
            "updated_at": f"{year:04d}-{month:02d}-01",
            "pagination": {
                "total_items": len(items),
                "per_page": per_page,
                "total_pages": math.ceil(len(items) / per_page) if per_page else 0,
            },
        }
        bucket_path = bucket_dir / "index.json"
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        bucket_path.write_text(text, encoding="utf-8")
        with gzip.open(bucket_path.with_suffix(".json.gz"), "wt", encoding="utf-8") as fh:
            fh.write(text)
        return bucket_path

    def _read_json(self, path: pathlib.Path) -> dict:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_rotation_moves_old_entries_and_compresses_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            hot_dir = root / "data" / "hot"
            archive_dir = root / "data" / "archive"

            self._write_hot(
                hot_dir,
                "news/general",
                [
                    {"slug": "recent", "published_at": "2024-05-08"},
                    {"slug": "also-recent", "published_at": "2024-05-07"},
                    {"slug": "old", "published_at": "2024-05-01"},
                    {"slug": "older", "published_at": "2024-04-30"},
                    {"slug": "no-date", "title": "Fallback"},
                ],
            )

            stats = rotate_hot.rotate(
                hot_dir=hot_dir,
                archive_dir=archive_dir,
                retention_days=5,
                current_date=datetime.date(2024, 5, 8),
            )

            self.assertEqual(stats.processed_shards, 1)
            self.assertEqual(stats.archived_items, 2)
            self.assertEqual(stats.hot_items_remaining, 3)

            hot_payload = self._read_json(hot_dir / "news" / "general" / "index.json")
            self.assertEqual([item["slug"] for item in hot_payload["items"]], ["recent", "also-recent", "no-date"])
            self.assertEqual(hot_payload["count"], 3)
            self.assertEqual(hot_payload["pagination"]["total_items"], 3)
            self.assertEqual(hot_payload["pagination"]["total_pages"], 1)

            may_bucket = archive_dir / "news" / "general" / "2024" / "05" / "index.json"
            april_bucket = archive_dir / "news" / "general" / "2024" / "04" / "index.json"
            self.assertTrue(may_bucket.exists())
            self.assertTrue(april_bucket.exists())

            may_payload = self._read_json(may_bucket)
            self.assertEqual([item["slug"] for item in may_payload["items"]], ["old"])

            gz_path = may_bucket.with_suffix(".json.gz")
            self.assertTrue(gz_path.exists(), "Missing gzip archive copy")
            with gzip.open(gz_path, "rt", encoding="utf-8") as fh:
                gz_payload = json.load(fh)
            self.assertEqual(gz_payload, may_payload)

            april_payload = self._read_json(april_bucket)
            self.assertEqual([item["slug"] for item in april_payload["items"]], ["older"])

    def test_rotation_preserves_order_and_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            hot_dir = root / "data" / "hot"
            archive_dir = root / "data" / "archive"

            self._write_hot(
                hot_dir,
                "news/general",
                [
                    {"slug": "keep", "published_at": "2024-05-09"},
                    {"slug": "newer", "published_at": "2024-05-03"},
                    {"slug": "newer", "published_at": "2024-05-03"},
                    {"slug": "older", "published_at": "2024-05-01"},
                    {"slug": "april", "published_at": "2024-04-30"},
                ],
            )

            self._write_archive(
                archive_dir,
                "news/general",
                2024,
                5,
                [{"slug": "older", "published_at": "2024-05-01"}],
            )

            stats = rotate_hot.rotate(
                hot_dir=hot_dir,
                archive_dir=archive_dir,
                retention_days=5,
                current_date=datetime.date(2024, 5, 10),
            )

            self.assertEqual(stats.archived_items, 2)
            self.assertEqual(stats.hot_items_remaining, 1)

            hot_payload = self._read_json(hot_dir / "news" / "general" / "index.json")
            self.assertEqual([item["slug"] for item in hot_payload["items"]], ["keep"])

            may_bucket = archive_dir / "news" / "general" / "2024" / "05" / "index.json"
            may_payload = self._read_json(may_bucket)
            self.assertEqual(
                [item["slug"] for item in may_payload["items"]],
                ["newer", "older"],
            )

            with gzip.open(may_bucket.with_suffix(".json.gz"), "rt", encoding="utf-8") as fh:
                gz_payload = json.load(fh)
            self.assertEqual(gz_payload, may_payload)

            april_bucket = archive_dir / "news" / "general" / "2024" / "04" / "index.json"
            april_payload = self._read_json(april_bucket)
            self.assertEqual([item["slug"] for item in april_payload["items"]], ["april"])


if __name__ == "__main__":
    unittest.main()
