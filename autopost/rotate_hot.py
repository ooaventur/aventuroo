#!/usr/bin/env python3
"""Rotate hot shards into the monthly archive.

The script scans ``data/hot`` for ``*/index.json`` payloads, keeps only the
entries that fall within the configured retention window, and moves the rest
into ``data/archive`` buckets grouped by year/month.  Archive buckets are
written alongside a ``.json.gz`` sibling for downstream tooling that expects a
compressed copy of the payload.

The implementation purposefully mirrors the lightweight JSON structure already
present in the repository so that automated runs produce minimal diffs: item
ordering is preserved, duplicates are skipped, and metadata such as ``count``
and ``pagination`` are kept in sync with the final item list.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import gzip
import json
import math
import pathlib
from collections import defaultdict
from typing import Iterable, Iterator


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


DEFAULT_RETENTION_DAYS = 5
DEFAULT_PER_PAGE = 12

DATE_FIELDS = (
    "published_at",
    "publishedAt",
    "published",
    "date",
    "updated_at",
    "updatedAt",
    "updated",
)


@dataclasses.dataclass(slots=True)
class RotationStats:
    """Simple bookkeeping for a rotation run."""

    processed_shards: int = 0
    archived_items: int = 0
    hot_items_remaining: int = 0


def _iter_hot_shards(hot_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Yield ``index.json`` payloads contained in ``hot_dir``."""

    if not hot_dir.exists():
        return iter(())

    # ``sorted`` ensures deterministic behaviour which keeps tests happy and
    # avoids jitter when the script runs in automation.
    return iter(sorted(hot_dir.rglob("index.json")))


def _item_key(item: dict) -> str:
    """Return a stable identifier for an item to support deduplication."""

    identifier = item.get("id")
    if identifier is not None:
        text = str(identifier).strip()
        if text:
            return f"id::{text.lower()}"

    slug = item.get("slug")
    if isinstance(slug, str):
        text = slug.strip()
        if text:
            return f"slug::{text.lower()}"

    for field in ("canonical", "url"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()

    title = item.get("title")
    if isinstance(title, str) and title.strip():
        return f"title::{title.strip()}"

    # As a last resort fall back to the JSON representation.  This is only
    # triggered for extremely sparse payloads and keeps the implementation
    # robust when unexpected data sneaks in.
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def _parse_date(value: object) -> _dt.date | None:
    """Convert ``value`` into a :class:`datetime.date` when possible."""

    if value is None:
        return None

    if isinstance(value, _dt.date):
        return value

    if isinstance(value, (int, float)):
        try:
            return _dt.datetime.utcfromtimestamp(float(value)).date()
        except (OverflowError, OSError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    # ``fromisoformat`` handles the vast majority of cases.  When the string
    # contains timezone information the conversion to ``datetime`` is required
    # before dropping down to ``date``.
    try:
        return _dt.date.fromisoformat(raw[:10])
    except ValueError:
        try:
            return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass

    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(raw).date()
    except Exception:
        return None


def _item_date(item: dict) -> _dt.date | None:
    for field in DATE_FIELDS:
        value = item.get(field)
        date = _parse_date(value)
        if date is not None:
            return date
    return None


def _coerce_positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value > 0 else default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            parsed = int(stripped)
        except ValueError:
            return default
        return parsed if parsed > 0 else default
    return default


def _pagination_settings(payload: dict, fallback: int = DEFAULT_PER_PAGE) -> int:
    pagination = payload.get("pagination")
    if isinstance(pagination, dict):
        return _coerce_positive_int(pagination.get("per_page"), fallback)
    return fallback


def _write_json(path: pathlib.Path, payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def _write_gzip(source_path: pathlib.Path, text: str) -> None:
    gz_path = source_path.with_suffix(".json.gz")
    gz_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gz_path, "wt", encoding="utf-8") as fh:
        fh.write(text)


def _insert_sorted(items: list[dict], item: dict) -> None:
    """Insert ``item`` into ``items`` keeping a descending date order."""

    target_date = _item_date(item)
    if target_date is None:
        items.append(item)
        return

    for idx, existing in enumerate(items):
        existing_date = _item_date(existing)
        if existing_date is None:
            items.insert(idx, item)
            return
        if target_date > existing_date:
            items.insert(idx, item)
            return
    items.append(item)


def _update_archive(
    archive_path: pathlib.Path,
    new_items: Iterable[dict],
    current_date: _dt.date,
) -> int:
    """Append ``new_items`` into ``archive_path`` and return insert count."""

    archive_path.parent.mkdir(parents=True, exist_ok=True)

    inserted = 0
    if archive_path.exists():
        try:
            existing = json.loads(archive_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    else:
        existing = {}

    items = list(existing.get("items", []))
    per_page = _pagination_settings(existing)

    seen = {_item_key(entry) for entry in items}
    for entry in new_items:
        key = _item_key(entry)
        if key in seen:
            continue
        _insert_sorted(items, entry)
        seen.add(key)
        inserted += 1

    if inserted == 0 and archive_path.exists():
        return 0

    payload = dict(existing)
    payload["items"] = items
    payload["count"] = len(items)
    payload["updated_at"] = current_date.isoformat()
    total = len(items)
    per_page = per_page if per_page > 0 else DEFAULT_PER_PAGE
    payload["pagination"] = {
        "total_items": total,
        "per_page": per_page,
        "total_pages": math.ceil(total / per_page) if per_page else 0,
    }

    text = _write_json(archive_path, payload)
    _write_gzip(archive_path, text)
    return inserted


def _process_shard(
    shard_path: pathlib.Path,
    hot_dir: pathlib.Path,
    archive_dir: pathlib.Path,
    retention_days: int,
    current_date: _dt.date,
) -> tuple[int, int]:
    """Process a single hot shard and return ``(archived, remaining)``."""

    try:
        payload = json.loads(shard_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return (0, 0)

    items = payload.get("items")
    if not isinstance(items, list):
        return (0, 0)

    seen: set[str] = set()
    keep: list[dict] = []
    archive_candidates: list[tuple[_dt.date, dict]] = []

    retention_days = max(retention_days, 0)

    cutoff_date = current_date - _dt.timedelta(days=retention_days)

    for entry in items:
        key = _item_key(entry)
        if key in seen:
            continue
        seen.add(key)

        entry_date = _item_date(entry)
        if entry_date is None:
            keep.append(entry)
            continue

        if entry_date < cutoff_date:
            archive_candidates.append((entry_date, entry))
        else:
            keep.append(entry)

    if keep != items:
        payload = dict(payload)
        payload["items"] = keep
        payload["count"] = len(keep)
        payload["updated_at"] = current_date.isoformat()
        per_page = _pagination_settings(payload)
        total = len(keep)
        payload["pagination"] = {
            "total_items": total,
            "per_page": per_page,
            "total_pages": math.ceil(total / per_page) if per_page else 0,
        }
        _write_json(shard_path, payload)

    archive_total = 0
    if archive_candidates:
        groups: dict[tuple[tuple[str, ...], int, int], list[dict]] = defaultdict(list)
        shard_rel = shard_path.relative_to(hot_dir).parent
        relative_parts = tuple(part for part in shard_rel.parts if part and part != ".")
        for entry_date, entry in archive_candidates:
            groups[(relative_parts, entry_date.year, entry_date.month)].append(entry)

        for (parts, year, month), grouped_items in groups.items():
            archive_base = archive_dir.joinpath(*parts) if parts else archive_dir
            archive_path = archive_base / f"{year:04d}" / f"{month:02d}" / "index.json"
            inserted = _update_archive(archive_path, grouped_items, current_date)
            archive_total += inserted

    return (archive_total, len(keep))


def rotate(
    hot_dir: pathlib.Path | str,
    archive_dir: pathlib.Path | str,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    current_date: _dt.date | None = None,
) -> RotationStats:
    """Rotate hot shards located under ``hot_dir`` into ``archive_dir``."""

    hot_path = pathlib.Path(hot_dir)
    archive_path = pathlib.Path(archive_dir)
    current = current_date or _dt.date.today()

    stats = RotationStats()
    for shard in _iter_hot_shards(hot_path):
        stats.processed_shards += 1
        archived, remaining = _process_shard(
            shard,
            hot_path,
            archive_path,
            retention_days,
            current,
        )
        stats.archived_items += archived
        stats.hot_items_remaining += remaining

    return stats


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rotate hot shards into the archive")
    parser.add_argument(
        "--hot-dir",
        default=PROJECT_ROOT / "data" / "hot",
        type=pathlib.Path,
        help="Directory containing hot shards (default: data/hot)",
    )
    parser.add_argument(
        "--archive-dir",
        default=PROJECT_ROOT / "data" / "archive",
        type=pathlib.Path,
        help="Directory where archive buckets are stored (default: data/archive)",
    )
    parser.add_argument(
        "--retention-days",
        default=DEFAULT_RETENTION_DAYS,
        type=int,
        help="Number of days to keep in hot shards (default: 5)",
    )
    parser.add_argument(
        "--current-date",
        type=str,
        help="Override the date used for retention calculations (YYYY-MM-DD)",
    )
    return parser


def _parse_date_arg(raw: str | None) -> _dt.date | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return _dt.date.fromisoformat(raw)
    except ValueError:
        msg = f"Invalid --current-date value: {raw!r}; expected YYYY-MM-DD"
        raise SystemExit(msg) from None


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    current = _parse_date_arg(args.current_date)

    stats = rotate(
        hot_dir=args.hot_dir,
        archive_dir=args.archive_dir,
        retention_days=args.retention_days,
        current_date=current,
    )

    print(
        "Rotated", stats.processed_shards, "shards;",
        stats.archived_items, "items archived;",
        stats.hot_items_remaining, "items remain in hot shards",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
