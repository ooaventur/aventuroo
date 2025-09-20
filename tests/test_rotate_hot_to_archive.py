import datetime
import gzip
import json
import pathlib
import tempfile
import unittest

from scripts import rotate_hot_to_archive


class RotateHotToArchiveTests(unittest.TestCase):
    def _write_hot_shard(self, base: pathlib.Path, relative: str, items: list[dict[str, object]]) -> pathlib.Path:
        shard_dir = base / relative
        shard_dir.mkdir(parents=True, exist_ok=True)
        payload = {"items": items, "count": len(items)}
        shard_path = shard_dir / "index.json"
        shard_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return shard_path

    def _read_json(self, path: pathlib.Path) -> dict:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_rotation_moves_entries_and_updates_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            hot_dir = root / "data" / "hot"
            archive_dir = root / "data" / "archive"

            self._write_hot_shard(
                hot_dir,
                "news",
                [
                    {"slug": "recent", "date": "2024-05-18", "title": "Recent"},
                    {"slug": "april", "date": "2024-04-10", "title": "April"},
                    {"slug": "march", "date": "2024-03-05", "title": "March"},
                    {"slug": "no-date", "title": "Fallback"},
                ],
            )

            stats = rotate_hot_to_archive.rotate(
                hot_dir=hot_dir,
                archive_dir=archive_dir,
                retention_days=30,
                per_page=5,
                current_date=datetime.date(2024, 5, 20),
            )

            self.assertEqual(stats.processed_shards, 1)
            self.assertEqual(stats.archived_items, 2)
            self.assertEqual(stats.hot_items_remaining, 2)

            hot_payload = self._read_json(hot_dir / "news" / "index.json")
            hot_items = hot_payload["items"]
            self.assertEqual({item["slug"] for item in hot_items}, {"recent", "no-date"})
            self.assertEqual(hot_payload["count"], 2)

            april_bucket = archive_dir / "news" / "index" / "2024" / "04" / "index.json"
            march_bucket = archive_dir / "news" / "index" / "2024" / "03" / "index.json"
            self.assertTrue(april_bucket.exists(), "April archive bucket missing")
            self.assertTrue(march_bucket.exists(), "March archive bucket missing")

            april_payload = self._read_json(april_bucket)
            april_items = april_payload["items"]
            self.assertEqual([item["slug"] for item in april_items], ["april"])
            april_gzip = april_bucket.with_suffix(".json.gz")
            self.assertTrue(april_gzip.exists())
            with gzip.open(april_gzip, "rt", encoding="utf-8") as fh:
                gz_payload = json.load(fh)
            self.assertEqual(gz_payload, april_payload)

            hot_manifest = self._read_json(hot_dir / "manifest.json")
            self.assertEqual(hot_manifest["total_items"], 2)
            self.assertEqual(hot_manifest["per_page"], 5)
            hot_slugs = {entry["slug"] for entry in hot_manifest["shards"]}
            self.assertIn("news", hot_slugs)

            archive_manifest = self._read_json(archive_dir / "manifest.json")
            self.assertEqual(archive_manifest["total_items"], 2)
            archive_slugs = {(entry["slug"], entry["year"], entry["month"]) for entry in archive_manifest["shards"]}
            self.assertIn(("news", 2024, 4), archive_slugs)
            self.assertIn(("news", 2024, 3), archive_slugs)

            archive_summary = self._read_json(archive_dir / "summary.json")
            news_summary = next(item for item in archive_summary["parents"] if item["parent"] == "news")
            self.assertEqual(news_summary["items"], 2)
            months = news_summary["children"][0]["months"]
            self.assertEqual([(m["year"], m["month"]) for m in months], [(2024, 4), (2024, 3)])

    def test_rotation_is_idempotent_for_existing_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            hot_dir = root / "data" / "hot"
            archive_dir = root / "data" / "archive"

            self._write_hot_shard(
                hot_dir,
                "news/world",
                [
                    {"slug": "world-old", "date": "2024-02-01", "title": "Old"},
                    {"slug": "world-older", "date": "2024-01-15", "title": "Older"},
                ],
            )

            rotate_hot_to_archive.rotate(
                hot_dir=hot_dir,
                archive_dir=archive_dir,
                retention_days=30,
                per_page=12,
                current_date=datetime.date(2024, 3, 5),
            )

            second_stats = rotate_hot_to_archive.rotate(
                hot_dir=hot_dir,
                archive_dir=archive_dir,
                retention_days=30,
                per_page=12,
                current_date=datetime.date(2024, 3, 6),
            )

            self.assertEqual(second_stats.archived_items, 0)
            world_manifest = self._read_json(archive_dir / "manifest.json")
            shards = {(entry["slug"], entry["year"], entry["month"]) for entry in world_manifest["shards"]}
            self.assertEqual(shards, {("news/world", 2024, 2), ("news/world", 2024, 1)})

    def test_rotation_handles_empty_hot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            hot_dir = root / "data" / "hot"
            archive_dir = root / "data" / "archive"

            stats = rotate_hot_to_archive.rotate(
                hot_dir=hot_dir,
                archive_dir=archive_dir,
                retention_days=45,
                per_page=12,
                current_date=datetime.date(2024, 7, 1),
            )

            self.assertEqual(stats.processed_shards, 0)
            self.assertTrue((hot_dir / "manifest.json").exists())
            manifest = self._read_json(hot_dir / "manifest.json")
            self.assertEqual(manifest["total_items"], 0)
            archive_manifest = self._read_json(archive_dir / "manifest.json")
            self.assertEqual(archive_manifest["total_items"], 0)


if __name__ == "__main__":
    unittest.main()
