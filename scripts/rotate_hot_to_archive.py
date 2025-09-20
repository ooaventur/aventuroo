#!/usr/bin/env python3
"""Utilities for rotating hot shards into the long-term archive.

The script scans ``data/hot`` for ``<parent>/<child>/index.json`` shards,
moves entries that fall outside the configured retention window into
``data/archive/<parent>/<child>/<yyyy>/<mm>/index.json`` buckets, and keeps
lightweight manifests for pagination/summary generation.

Usage:
    python scripts/rotate_hot_to_archive.py [--retention-days 45]

Environment knobs:

``HOT_RETENTION_DAYS``
    Number of days of content that should remain in ``data/hot``. Entries
    older than the window are moved to the archive tree. Defaults to 30 days.

``HOT_PAGINATION_SIZE``
    The page size used when computing pagination counts. Defaults to 12 which
    matches the public site’s page size.

Both values can also be supplied via the CLI flags with the same name. The
script is idempotent, safe to run repeatedly, and keeps JSON as stable as
possible so an automated runner will only produce diffs when content changes.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import gzip
import io
import json
import math
import os
import pathlib
import re
import sys
from collections import defaultdict
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Iterator


DEFAULT_RETENTION_DAYS = 30
DEFAULT_PAGINATION_SIZE = 12

DATE_FIELD_CANDIDATES = (
    "date",
    "published",
    "published_at",
    "publishedAt",
    "updated",
    "updated_at",
    "updatedAt",
)


@dataclasses.dataclass(slots=True)
class ShardTemplate:
    """Remember how a shard was structured when it was read."""

    container: str  # "list" or "dict"
    key: str | None
    raw: Any


@dataclasses.dataclass(slots=True)
class RotationStats:
    """Lightweight telemetry about a rotation run."""

    processed_shards: int
    archived_items: int
    archive_buckets: int
    hot_items_remaining: int


def _env_int(name: str, fallback: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return fallback
    raw = raw.strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        print(f"[rotate] Warning: invalid {name}={raw!r}; using {fallback}", file=sys.stderr)
        return fallback


def _parse_cli_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rotate hot shards into the archive tree.")
    parser.add_argument(
        "--hot-dir",
        default="data/hot",
        type=pathlib.Path,
        help="Path to the hot shards directory (default: data/hot).",
    )
    parser.add_argument(
        "--archive-dir",
        default="data/archive",
        type=pathlib.Path,
        help="Path to the archive directory (default: data/archive).",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Number of days to keep in hot storage before archiving.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=None,
        help="Pagination size used for manifest counts (default: 12).",
    )
    parser.add_argument(
        "--current-date",
        dest="current_date",
        default=None,
        help="Override today when evaluating retention (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect the rotation without writing data back to disk.",
    )
    return parser.parse_args(argv)


def _parse_date_string(value: Any) -> _dt.date | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return _dt.datetime.utcfromtimestamp(value).date()
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    candidate = text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        dt = _dt.datetime.fromisoformat(candidate)
    except ValueError:
        dt = None

    if isinstance(dt, _dt.datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return dt.date()
    if isinstance(dt, _dt.date):
        return dt

    try:
        return _dt.date.fromisoformat(text[:10])
    except ValueError:
        pass

    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        dt = None

    if isinstance(dt, _dt.datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return dt.date()

    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return _dt.date(year, month, day)
        except ValueError:
            return None

    return None


def _item_date(item: Any) -> _dt.date | None:
    if not isinstance(item, dict):
        return None
    for field in DATE_FIELD_CANDIDATES:
        if field in item:
            parsed = _parse_date_string(item[field])
            if parsed:
                return parsed
    return None


def _item_slug(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    slug = item.get("slug") or item.get("id") or item.get("path")
    if slug is None:
        return ""
    return str(slug).strip()


def _dedupe_items(items: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for entry in items:
        slug = _item_slug(entry)
        if not slug:
            key = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        else:
            key = slug
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _sort_items(items: Iterable[Any]) -> list[Any]:
    decorated = []
    for idx, entry in enumerate(items):
        item_date = _item_date(entry) or _dt.date.min
        slug = _item_slug(entry)
        decorated.append((item_date, slug, idx, entry))
    decorated.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    return [row[3] for row in decorated]


def _read_json(path: pathlib.Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        print(f"[rotate] Warning: {path} is not valid JSON ({exc}); ignoring", file=sys.stderr)
        return None


def _read_json_allow_gzip(path: pathlib.Path) -> Any:
    data = _read_json(path)
    if data is not None:
        return data
    gz_path = path.with_suffix(path.suffix + ".gz")
    if not gz_path.exists():
        return None
    try:
        with gzip.open(gz_path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"[rotate] Warning: {gz_path} is not valid JSON ({exc}); ignoring", file=sys.stderr)
        return None


def _extract_items(payload: Any) -> tuple[list[Any], ShardTemplate]:
    if isinstance(payload, list):
        return list(payload), ShardTemplate(container="list", key=None, raw=list(payload))
    if isinstance(payload, dict):
        for key in ("items", "entries", "data", "posts"):
            value = payload.get(key)
            if isinstance(value, list):
                return list(value), ShardTemplate(container="dict", key=key, raw=dict(payload))
        return [], ShardTemplate(container="dict", key="items", raw=dict(payload))
    return [], ShardTemplate(container="list", key=None, raw=[])


def _ensure_parent_dir(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json_if_changed(path: pathlib.Path, data: Any, *, indent: int = 2) -> bool:
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    text_with_newline = text + "\n"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == text_with_newline:
            return False
    _ensure_parent_dir(path)
    path.write_text(text_with_newline, encoding="utf-8")
    return True


def _write_gzip_json(path: pathlib.Path, data: Any) -> None:
    _ensure_parent_dir(path)
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as gz:
        with io.TextIOWrapper(gz, encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)


def _remove_path(path: pathlib.Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _shard_parent_child(rel_parts: tuple[str, ...]) -> tuple[str, str]:
    if len(rel_parts) <= 1:
        return "index", "index"
    parent = rel_parts[0]
    if len(rel_parts) == 2:
        return parent, "index"
    child = "/".join(rel_parts[1:-1])
    return parent, child or "index"


def _bucket_parent_child_year_month(rel_parts: tuple[str, ...]) -> tuple[str, str, int, int]:
    if len(rel_parts) < 4:
        return "index", "index", 1970, 1
    year_raw = rel_parts[-3]
    month_raw = rel_parts[-2]
    child_parts = rel_parts[1:-3]
    try:
        year = int(year_raw)
        month = int(month_raw)
    except ValueError:
        year, month = 1970, 1
    child = "/".join(child_parts) or "index"
    parent = rel_parts[0]
    return parent, child, year, month


def _calc_pages(total: int, per_page: int) -> int:
    if per_page <= 0:
        return total if total else 0
    return math.ceil(total / per_page)


def _update_hot_shard(
    shard_path: pathlib.Path,
    items: list[Any],
    template: ShardTemplate,
    *,
    per_page: int,
    dry_run: bool,
) -> list[Any]:
    cleaned = _dedupe_items(items)
    sorted_items = _sort_items(cleaned)
    dates = [_item_date(entry) for entry in sorted_items if _item_date(entry)]
    latest_date = max(dates) if dates else None

    if template.container == "dict":
        payload = dict(template.raw or {})
        key = template.key or "items"
        payload[key] = sorted_items
        payload["count"] = len(sorted_items)
        payload["updated_at"] = latest_date.isoformat() if latest_date else None
        payload["pagination"] = {
            "total_items": len(sorted_items),
            "per_page": per_page,
            "total_pages": _calc_pages(len(sorted_items), per_page),
        }
    else:
        payload = sorted_items

    if not dry_run:
        _write_json_if_changed(shard_path, payload)
    return sorted_items


def _merge_archive_bucket(
    path: pathlib.Path,
    new_items: list[Any],
    *,
    per_page: int,
    dry_run: bool,
) -> tuple[list[Any], int]:
    existing_payload = _read_json_allow_gzip(path)
    existing_items: list[Any]
    existing_template: ShardTemplate
    if existing_payload is None:
        existing_items = []
        existing_template = ShardTemplate(container="dict", key="items", raw={})
    else:
        existing_items, existing_template = _extract_items(existing_payload)

    combined = list(new_items)
    if existing_items:
        combined.extend(existing_items)

    deduped = _dedupe_items(combined)
    sorted_items = _sort_items(deduped)
    dates = [_item_date(entry) for entry in sorted_items if _item_date(entry)]
    latest_date = max(dates) if dates else None

    if existing_template.container == "dict":
        payload = dict(existing_template.raw or {})
        key = existing_template.key or "items"
        payload[key] = sorted_items
        payload["count"] = len(sorted_items)
        payload["updated_at"] = latest_date.isoformat() if latest_date else None
        payload["pagination"] = {
            "total_items": len(sorted_items),
            "per_page": per_page,
            "total_pages": _calc_pages(len(sorted_items), per_page),
        }
    else:
        payload = sorted_items

    if not sorted_items:
        if not dry_run:
            _remove_path(path)
            _remove_path(path.with_suffix(path.suffix + ".gz"))
        return sorted_items, 0

    added = max(0, len(sorted_items) - len(existing_items))

    if not dry_run:
        changed = _write_json_if_changed(path, payload)
        if changed:
            _write_gzip_json(path.with_suffix(path.suffix + ".gz"), payload)
        else:
            # Ensure gzip exists even if unchanged.
            gz_path = path.with_suffix(path.suffix + ".gz")
            if not gz_path.exists():
                _write_gzip_json(gz_path, payload)
    return sorted_items, added


def _iter_hot_shards(hot_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    if not hot_dir.exists():
        return iter(())
    return (path for path in sorted(hot_dir.rglob("index.json")) if path.is_file())


def _iter_archive_shards(archive_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    if not archive_dir.exists():
        return iter(())
    return (path for path in sorted(archive_dir.rglob("index.json")) if path.is_file())


def _generate_hot_metadata(
    hot_dir: pathlib.Path,
    *,
    per_page: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    shards = []
    parents: dict[str, dict[str, Any]] = defaultdict(lambda: {"items": 0, "children": {}})
    total_items = 0
    latest_seen: _dt.date | None = None

    for shard_path in _iter_hot_shards(hot_dir):
        rel = shard_path.relative_to(hot_dir)
        parts = rel.parts
        parent, child = _shard_parent_child(parts)
        payload = _read_json(shard_path)
        if payload is None:
            items = []
        else:
            items, _ = _extract_items(payload)
        items = _dedupe_items(items)
        items = _sort_items(items)
        count = len(items)
        total_items += count
        dates = [_item_date(entry) for entry in items if _item_date(entry)]
        first_date = min(dates).isoformat() if dates else None
        last_date = max(dates) if dates else None
        if last_date and (latest_seen is None or last_date > latest_seen):
            latest_seen = last_date
        slug = parent if child == "index" else f"{parent}/{child}"
        shards.append(
            {
                "parent": parent,
                "child": child,
                "slug": slug,
                "path": "/".join(rel.parts),
                "items": count,
                "first_date": first_date,
                "last_date": last_date.isoformat() if last_date else None,
                "pages": _calc_pages(count, per_page),
            }
        )

        parent_entry = parents[parent]
        parent_entry["items"] += count
        child_entry = parent_entry["children"].setdefault(child, {"items": 0})
        child_entry["items"] += count

    shards.sort(key=lambda row: (row["parent"], row["child"]))

    manifest = {
        "generated_at": latest_seen.isoformat() if latest_seen else None,
        "per_page": per_page,
        "total_items": total_items,
        "shards": shards,
    }

    summary_parents = []
    for parent_slug, data in sorted(parents.items()):
        children_summary = []
        for child_slug, child_data in sorted(data["children"].items()):
            slug = parent_slug if child_slug == "index" else f"{parent_slug}/{child_slug}"
            children_summary.append(
                {
                    "child": child_slug,
                    "slug": slug,
                    "items": child_data["items"],
                    "pages": _calc_pages(child_data["items"], per_page),
                }
            )
        summary_parents.append(
            {
                "parent": parent_slug,
                "items": data["items"],
                "pages": _calc_pages(data["items"], per_page),
                "children": children_summary,
            }
        )

    summary = {
        "generated_at": latest_seen.isoformat() if latest_seen else None,
        "per_page": per_page,
        "total_items": total_items,
        "parents": summary_parents,
    }

    return manifest, summary


def _generate_archive_metadata(
    archive_dir: pathlib.Path,
    *,
    per_page: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    shards = []
    parents: dict[str, dict[str, Any]] = defaultdict(lambda: {"items": 0, "children": {}})
    total_items = 0
    latest_seen: _dt.date | None = None

    for bucket_path in _iter_archive_shards(archive_dir):
        rel = bucket_path.relative_to(archive_dir)
        parts = rel.parts
        parent, child, year, month = _bucket_parent_child_year_month(parts)
        payload = _read_json_allow_gzip(bucket_path)
        if payload is None:
            items = []
        else:
            items, _ = _extract_items(payload)
        items = _dedupe_items(items)
        items = _sort_items(items)
        count = len(items)
        total_items += count
        dates = [_item_date(entry) for entry in items if _item_date(entry)]
        first_date = min(dates).isoformat() if dates else None
        last_date = max(dates) if dates else None
        if last_date and (latest_seen is None or last_date > latest_seen):
            latest_seen = last_date
        slug = parent if child == "index" else f"{parent}/{child}"
        shards.append(
            {
                "parent": parent,
                "child": child,
                "slug": slug,
                "year": year,
                "month": month,
                "path": "/".join(rel.parts),
                "path_gz": "/".join(rel.with_suffix(rel.suffix + ".gz").parts),
                "items": count,
                "first_date": first_date,
                "last_date": last_date.isoformat() if last_date else None,
                "pages": _calc_pages(count, per_page),
            }
        )

        parent_entry = parents[parent]
        parent_entry["items"] += count
        child_entry = parent_entry["children"].setdefault(
            child,
            {"items": 0, "months": []},
        )
        child_entry["items"] += count
        child_entry["months"].append(
            {
                "year": year,
                "month": month,
                "items": count,
                "pages": _calc_pages(count, per_page),
            }
        )

    shards.sort(key=lambda row: (row["parent"], row["child"], row["year"], row["month"]))

    for data in parents.values():
        for child_data in data["children"].values():
            child_data["months"].sort(key=lambda m: (m["year"], m["month"]), reverse=True)

    manifest = {
        "generated_at": latest_seen.isoformat() if latest_seen else None,
        "per_page": per_page,
        "total_items": total_items,
        "shards": shards,
    }

    summary_parents = []
    for parent_slug, data in sorted(parents.items()):
        children_summary = []
        for child_slug, child_data in sorted(data["children"].items()):
            slug = parent_slug if child_slug == "index" else f"{parent_slug}/{child_slug}"
            children_summary.append(
                {
                    "child": child_slug,
                    "slug": slug,
                    "items": child_data["items"],
                    "pages": _calc_pages(child_data["items"], per_page),
                    "months": child_data["months"],
                }
            )
        summary_parents.append(
            {
                "parent": parent_slug,
                "items": data["items"],
                "pages": _calc_pages(data["items"], per_page),
                "children": children_summary,
            }
        )

    summary = {
        "generated_at": latest_seen.isoformat() if latest_seen else None,
        "per_page": per_page,
        "total_items": total_items,
        "parents": summary_parents,
    }

    return manifest, summary


def rotate(
    *,
    hot_dir: pathlib.Path,
    archive_dir: pathlib.Path,
    retention_days: int,
    per_page: int,
    current_date: _dt.date | None = None,
    dry_run: bool = False,
) -> RotationStats:
    hot_dir = hot_dir.resolve()
    archive_dir = archive_dir.resolve()
    current_date = current_date or _dt.date.today()

    if retention_days < 0:
        raise ValueError("retention_days must be >= 0")
    if per_page <= 0:
        per_page = DEFAULT_PAGINATION_SIZE

    hot_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    cutoff_date = current_date - _dt.timedelta(days=retention_days)

    processed = 0
    archived_total = 0
    archive_buckets_touched: set[pathlib.Path] = set()

    for shard_path in _iter_hot_shards(hot_dir):
        rel_parts = shard_path.relative_to(hot_dir).parts
        if len(rel_parts) < 2:
            continue
        payload = _read_json(shard_path)
        if payload is None:
            items = []
            template = ShardTemplate(container="dict", key="items", raw={})
        else:
            items, template = _extract_items(payload)
        processed += 1

        kept: list[Any] = []
        to_archive: list[tuple[_dt.date, Any]] = []
        for entry in items:
            entry_date = _item_date(entry)
            if entry_date and entry_date < cutoff_date:
                to_archive.append((entry_date, entry))
            else:
                kept.append(entry)

        _update_hot_shard(shard_path, kept, template, per_page=per_page, dry_run=dry_run)

        if not to_archive:
            continue

        archived_total += len(to_archive)
        parent_slug, child_slug = _shard_parent_child(rel_parts)
        grouped: dict[tuple[int, int], list[Any]] = defaultdict(list)
        for entry_date, entry in to_archive:
            year_month = (entry_date.year, entry_date.month)
            grouped[year_month].append(entry)

        for (year, month), grouped_items in grouped.items():
            target_dir = archive_dir / parent_slug / child_slug / f"{year:04d}" / f"{month:02d}"
            target_path = target_dir / "index.json"
            archive_buckets_touched.add(target_path)
            _merge_archive_bucket(
                target_path,
                grouped_items,
                per_page=per_page,
                dry_run=dry_run,
            )

    hot_manifest, hot_summary = _generate_hot_metadata(hot_dir, per_page=per_page)
    archive_manifest, archive_summary = _generate_archive_metadata(archive_dir, per_page=per_page)

    if not dry_run:
        _write_json_if_changed(hot_dir / "manifest.json", hot_manifest)
        _write_json_if_changed(hot_dir / "summary.json", hot_summary)
        _write_json_if_changed(archive_dir / "manifest.json", archive_manifest)
        _write_json_if_changed(archive_dir / "summary.json", archive_summary)

    return RotationStats(
        processed_shards=processed,
        archived_items=archived_total,
        archive_buckets=len(archive_buckets_touched),
        hot_items_remaining=hot_manifest.get("total_items", 0) if isinstance(hot_manifest, dict) else 0,
    )


def main(argv: Iterable[str] | None = None) -> RotationStats:
    args = _parse_cli_args(argv)
    retention_days = args.retention_days
    if retention_days is None:
        retention_days = _env_int("HOT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)
    per_page = args.per_page
    if per_page is None:
        per_page = _env_int("HOT_PAGINATION_SIZE", DEFAULT_PAGINATION_SIZE)

    current_date = None
    if args.current_date:
        parsed = _parse_date_string(args.current_date)
        if not parsed:
            raise SystemExit(f"Invalid --current-date value: {args.current_date!r}")
        current_date = parsed

    stats = rotate(
        hot_dir=args.hot_dir,
        archive_dir=args.archive_dir,
        retention_days=retention_days,
        per_page=per_page,
        current_date=current_date,
        dry_run=args.dry_run,
    )

    print(
        f"[rotate] processed={stats.processed_shards} archived={stats.archived_items} "
        f"buckets={stats.archive_buckets} hot_remaining={stats.hot_items_remaining}",
        file=sys.stderr,
    )
    return stats


if __name__ == "__main__":
    main()
