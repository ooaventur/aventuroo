#!/usr/bin/env python3
"""Archive aged feed entries into monthly buckets.

The script scans the category and subcategory feeds produced by
``scripts/build_feeds.py`` (``data/categories/<category>/index.json`` and
``.../subcats/<subcategory>/index.json``). Any entries whose published
timestamps fall outside the configured ``window_days`` are moved to
``data/archive/<category>/<YYYY>/<MM>.json`` or
``data/archive/<category>/subcats/<subcategory>/<YYYY>/<MM>.json``. When run
with ``--dry-run`` the script reports what would happen without writing files.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
CATEGORIES_DIR = DATA_DIR / "categories"
ARCHIVE_DIR = DATA_DIR / "archive"
CONFIG_PATH = ROOT_DIR / "config.json"

DATE_FIELDS: Tuple[str, ...] = (
    "published_at",
    "publishedAt",
    "date",
    "published",
    "updated_at",
    "updatedAt",
    "updated",
)


@dataclass
class IndexTemplate:
    """Remember how a feed file is structured so it can be rewritten."""

    container: str
    key: Optional[str]
    raw: Any


@dataclass
class PostRecord:
    """Metadata for a feed entry used during processing."""

    post: Any
    identity: Optional[str]
    timestamp: Optional[datetime]
    order: int
    priority: int = 0


@dataclass
class ArchiveResult:
    """Summary of an archive bucket merge."""

    added: int
    total: int


@dataclass
class RunStats:
    feeds: int = 0
    skipped: int = 0
    archived: int = 0
    remaining: int = 0
    deduped: int = 0


def _format_relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        print(f"[archive] Warning: failed to read {path}: {exc}", file=sys.stderr)
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"[archive] Warning: invalid JSON in {path}: {exc}", file=sys.stderr)
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = json.dumps(payload, indent=2, ensure_ascii=False)
    path.write_text(serialised + "\n", encoding="utf-8")


def _normalise_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, (int, float)):
        try:
            ts = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            ts = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    ts = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    else:
        return None

    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc)
    return ts.replace(tzinfo=None)


def _extract_timestamp(post: Any) -> Optional[datetime]:
    if not isinstance(post, dict):
        return None
    for field in DATE_FIELDS:
        if field in post:
            ts = _normalise_timestamp(post.get(field))
            if ts is not None:
                return ts
    return None


def _make_identity(post: Any) -> Optional[str]:
    if not isinstance(post, dict):
        return None

    identifier = post.get("id")
    if isinstance(identifier, str):
        stripped = identifier.strip()
        if stripped:
            return f"id:{stripped}"
    elif identifier is not None:
        return f"id:{identifier}"

    slug = post.get("slug")
    if isinstance(slug, str):
        stripped_slug = slug.strip().lower()
        if stripped_slug:
            return f"slug:{stripped_slug}"

    return None


def _prepare_records(posts: Sequence[Any], *, priority: int = 0) -> List[PostRecord]:
    records: List[PostRecord] = []
    for index, post in enumerate(posts):
        identity = _make_identity(post)
        timestamp = _extract_timestamp(post)
        records.append(PostRecord(post=post, identity=identity, timestamp=timestamp, order=index, priority=priority))
    return records


def _dedupe_records(records: Iterable[PostRecord]) -> List[PostRecord]:
    seen: set[str] = set()
    unique: List[PostRecord] = []
    for record in records:
        ident = record.identity
        if ident and ident in seen:
            continue
        unique.append(record)
        if ident:
            seen.add(ident)
    return unique


def _sort_records(records: Iterable[PostRecord]) -> List[PostRecord]:
    prepared = list(records)
    prepared.sort(
        key=lambda rec: (
            rec.timestamp or datetime.min,
            rec.priority,
            -rec.order,
            rec.identity or "",
        ),
        reverse=True,
    )
    return prepared


def _extract_items(payload: Any) -> Optional[Tuple[List[Any], IndexTemplate]]:
    if isinstance(payload, list):
        return list(payload), IndexTemplate(container="list", key=None, raw=None)
    if isinstance(payload, dict):
        for key in ("items", "posts", "entries"):
            items = payload.get(key)
            if isinstance(items, list):
                return list(items), IndexTemplate(container="dict", key=key, raw=payload)
        print(
            f"[archive] Warning: feed payload missing an items list (keys: {', '.join(payload.keys())})",
            file=sys.stderr,
        )
        return None
    print(f"[archive] Warning: unsupported feed structure ({type(payload).__name__})", file=sys.stderr)
    return None


def _render_payload(template: IndexTemplate, posts: Sequence[Any], latest: Optional[datetime]) -> Any:
    if template.container == "list":
        return list(posts)

    raw = copy.deepcopy(template.raw) if template.raw is not None else {}
    key = template.key or "items"
    raw[key] = list(posts)

    raw["count"] = len(posts)
    raw["updated_at"] = latest.isoformat() if latest else None

    pagination = raw.get("pagination")
    if isinstance(pagination, dict):
        pagination = dict(pagination)
        total_items = len(posts)
        pagination["total_items"] = total_items
        per_page = pagination.get("per_page")
        if isinstance(per_page, int) and per_page > 0:
            pagination["total_pages"] = math.ceil(total_items / per_page) if total_items else 0
        else:
            pagination["total_pages"] = total_items if total_items else 0
        raw["pagination"] = pagination

    return raw


def _archive_path(category: str, subcat: Optional[str], year: int, month: int) -> Path:
    if subcat:
        return ARCHIVE_DIR / category / "subcats" / subcat / f"{year:04d}" / f"{month:02d}.json"
    return ARCHIVE_DIR / category / f"{year:04d}" / f"{month:02d}.json"


def _merge_archive_bucket(path: Path, records: Sequence[PostRecord], *, dry_run: bool) -> ArchiveResult:
    existing_payload = _load_json(path)
    if existing_payload is None:
        existing_items: List[Any] = []
        template = IndexTemplate(container="list", key=None, raw=None)
    else:
        extracted = _extract_items(existing_payload)
        if extracted is None:
            existing_items = []
            template = IndexTemplate(container="list", key=None, raw=None)
        else:
            existing_items, template = extracted

    existing_records = _prepare_records(existing_items, priority=0)
    existing_identities = {rec.identity for rec in existing_records if rec.identity}

    added = 0
    for record in records:
        if record.identity:
            if record.identity not in existing_identities:
                added += 1
                existing_identities.add(record.identity)
        else:
            added += 1

    combined: List[PostRecord] = list(records) + existing_records
    combined = _dedupe_records(combined)
    combined = _sort_records(combined)

    posts = [rec.post for rec in combined]
    latest = max((rec.timestamp for rec in combined if rec.timestamp), default=None)
    payload = _render_payload(template, posts, latest)

    if not dry_run:
        if payload != existing_payload:
            _write_json(path, payload)
    return ArchiveResult(added=added, total=len(posts))


def _process_feed(
    category: str,
    subcat: Optional[str],
    path: Path,
    cutoff: datetime,
    *,
    dry_run: bool,
) -> RunStats:
    stats = RunStats()

    if not path.exists():
        stats.skipped += 1
        print(f"[archive] Skipping missing feed { _format_relative(path) }")
        return stats

    payload = _load_json(path)
    if payload is None:
        stats.skipped += 1
        print(f"[archive] Skipping unreadable feed { _format_relative(path) }", file=sys.stderr)
        return stats

    extracted = _extract_items(payload)
    if extracted is None:
        stats.skipped += 1
        print(f"[archive] Skipping unsupported feed { _format_relative(path) }", file=sys.stderr)
        return stats

    items, template = extracted

    records = _prepare_records(items, priority=0)
    deduped = _dedupe_records(records)
    duplicates_removed = len(records) - len(deduped)

    archive_records: List[PostRecord] = []
    remaining_records: List[PostRecord] = []

    for record in deduped:
        if record.timestamp and record.timestamp < cutoff:
            record.priority = 1
            archive_records.append(record)
        else:
            remaining_records.append(record)

    moved = len(archive_records)
    bucket_summaries: List[str] = []

    if archive_records:
        grouped: dict[Tuple[int, int], List[PostRecord]] = defaultdict(list)
        for record in archive_records:
            timestamp = record.timestamp
            if timestamp is None:
                remaining_records.append(record)
                continue
            grouped[(timestamp.year, timestamp.month)].append(record)

        archive_details: List[str] = []
        for (year, month), bucket_records in sorted(grouped.items()):
            archive_path = _archive_path(category, subcat, year, month)
            result = _merge_archive_bucket(archive_path, bucket_records, dry_run=dry_run)
            archive_details.append(
                f"{year:04d}-{month:02d} (+{result.added}/{len(bucket_records)})"
            )
            detail_prefix = "[dry-run] " if dry_run else ""
            print(
                f"{detail_prefix}    -> {_format_relative(archive_path)} : "
                f"moved {len(bucket_records)} (added {result.added}, total {result.total})"
            )
        bucket_summaries = archive_details

    remaining_posts = [record.post for record in remaining_records]
    latest_remaining = max((rec.timestamp for rec in remaining_records if rec.timestamp), default=None)
    new_payload = _render_payload(template, remaining_posts, latest_remaining)

    if not dry_run and new_payload != payload:
        _write_json(path, new_payload)

    prefix = "[dry-run] " if dry_run else ""
    if moved:
        archive_info = ", ".join(bucket_summaries)
        message = (
            f"{prefix}{_format_relative(path)}: archived {moved} posts"
            f" -> {archive_info if archive_info else 'buckets updated'}; {len(remaining_posts)} remain."
        )
    else:
        message = f"{prefix}{_format_relative(path)}: no posts archived; {len(remaining_posts)} remain."

    if duplicates_removed:
        message += f" Removed {duplicates_removed} duplicates."
    print(message)

    stats.feeds += 1
    stats.archived += moved
    stats.remaining += len(remaining_posts)
    stats.deduped += duplicates_removed
    return stats


def _load_config() -> Dict[str, Any]:
    payload = _load_json(CONFIG_PATH)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        print(f"[archive] Warning: configuration root must be an object", file=sys.stderr)
        return {}
    return payload


def _resolve_window_days(config: Dict[str, Any], override: Optional[int]) -> int:
    if override is not None:
        if override < 0:
            raise ValueError("window_days must be >= 0")
        return override

    value = config.get("window_days")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
            if parsed >= 0:
                return parsed
        except ValueError:
            pass
    return 30


def _iter_feed_paths(config: Dict[str, Any]) -> Iterator[Tuple[str, Optional[str], Path]]:
    categories = config.get("categories", {})
    if not isinstance(categories, dict):
        return iter(())

    for category, meta in categories.items():
        if not isinstance(category, str) or not category:
            continue
        yield category, None, CATEGORIES_DIR / category / "index.json"

        subcats: Iterable[Any] = []
        if isinstance(meta, dict):
            raw = meta.get("subcats", [])
            if isinstance(raw, (list, tuple)):
                subcats = raw
        for subcat in subcats:
            if not isinstance(subcat, str) or not subcat:
                continue
            yield category, subcat, CATEGORIES_DIR / category / "subcats" / subcat / "index.json"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Archive aged feed entries into monthly buckets.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files.",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        help="Override the archive window in days (defaults to config).",
    )
    args = parser.parse_args(argv)

    config = _load_config()
    try:
        window_days = _resolve_window_days(config, args.window_days)
    except ValueError as exc:
        parser.error(str(exc))

    if window_days < 0:
        parser.error("window_days must be >= 0")

    cutoff = datetime.utcnow() - timedelta(days=window_days)

    if args.dry_run:
        print("[archive] Dry-run mode enabled; no files will be written.")
    print(f"[archive] Using window_days={window_days}; cutoff={cutoff.isoformat(timespec='seconds')}")

    if not CATEGORIES_DIR.exists():
        print(f"[archive] Category directory {CATEGORIES_DIR} does not exist; nothing to do.")
        return 0

    stats = RunStats()
    for category, subcat, path in _iter_feed_paths(config):
        feed_stats = _process_feed(category, subcat, path, cutoff, dry_run=args.dry_run)
        stats.feeds += feed_stats.feeds
        stats.skipped += feed_stats.skipped
        stats.archived += feed_stats.archived
        stats.remaining += feed_stats.remaining
        stats.deduped += feed_stats.deduped

    if stats.feeds == 0:
        print("[archive] No feeds processed.")
    else:
        print(
            f"[archive] Processed {stats.feeds} feeds: archived {stats.archived} posts; "
            f"{stats.remaining} remain active."
        )
        if stats.deduped:
            print(f"[archive] Removed {stats.deduped} duplicate posts across feeds.")
    if stats.skipped:
        print(f"[archive] Skipped {stats.skipped} feeds due to missing or invalid data.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
