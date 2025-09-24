#!/usr/bin/env python3
"""Generate a lightweight posts index from hot shards.

The script scans ``data/hot`` for ``index.json`` payloads, normalises the
entries and writes ``data/posts.json`` limited to the newest 500 posts.  It is
intended as a quick aggregation step for environments where the heavy
``pull_*`` autopost jobs are not available.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
from typing import Any, Iterable

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
HOT_DIR = DATA_DIR / "hot"
OUTPUT_PATH = DATA_DIR / "posts.json"
TAXONOMY_PATH = DATA_DIR / "taxonomy.json"
ALIASES_PATH = HOT_DIR / "category_aliases.json"

DEFAULT_LIMIT = 500

DATE_FIELDS = (
    "published_at",
    "publishedAt",
    "date",
    "updated_at",
    "updatedAt",
    "updated",
    "created_at",
    "createdAt",
    "created",
)


def _coerce_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        text = str(value)
    except Exception:
        return ""
    return text.strip()


def _first_string(item: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        if key not in item:
            continue
        text = _coerce_string(item.get(key))
        if text:
            return text
    return ""


def _looks_like_date_only(text: str) -> bool:
    if len(text) != 10:
        return False
    if text[4] != "-" or text[7] != "-":
        return False
    return all(part.isdigit() for part in (text[:4], text[5:7], text[8:10]))


def _parse_datetime(value: Any) -> _dt.datetime | None:
    if value is None:
        return None

    if isinstance(value, _dt.datetime):
        dt = value
    elif isinstance(value, _dt.date):
        dt = _dt.datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            timestamp = float(value)
            if timestamp > 1_000_000_000_000:  # likely milliseconds
                timestamp /= 1000.0
            dt = _dt.datetime.fromtimestamp(timestamp, tz=_dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = _coerce_string(value)
        if not text:
            return None
        iso_candidate = text
        if iso_candidate.endswith("Z"):
            iso_candidate = iso_candidate[:-1] + "+00:00"
        try:
            dt = _dt.datetime.fromisoformat(iso_candidate)
        except ValueError:
            dt = None
        if dt is None:
            try:
                from email.utils import parsedate_to_datetime

                dt = parsedate_to_datetime(text)
            except Exception:
                dt = None
        if dt is None:
            for fmt in (
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%d %b %Y",
                "%d %B %Y",
                "%b %d, %Y",
                "%B %d, %Y",
            ):
                try:
                    dt = _dt.datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return None

    if isinstance(dt, _dt.datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return dt

    if isinstance(dt, _dt.date):
        return _dt.datetime(dt.year, dt.month, dt.day)

    return None


def _format_datetime(dt: _dt.datetime | None, original: Any = None) -> str:
    if dt is None:
        return _coerce_string(original)

    dt = dt.replace(microsecond=0)
    original_text = _coerce_string(original)
    if original_text and _looks_like_date_only(original_text):
        return dt.date().isoformat()

    iso = dt.isoformat()
    if original_text.endswith("Z") and not iso.endswith("Z"):
        iso = f"{iso}Z"
    return iso


def _load_taxonomy_labels(path: pathlib.Path | None) -> dict[str, str]:
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    categories = data.get("categories")
    if not isinstance(categories, list):
        return {}

    labels: dict[str, str] = {}
    for entry in categories:
        if not isinstance(entry, dict):
            continue
        slug = _coerce_string(entry.get("slug"))
        title = _coerce_string(entry.get("title"))
        if slug and title:
            labels[slug] = title
    return labels


def _load_alias_config(path: pathlib.Path | None) -> tuple[str, dict[str, str]]:
    standard_child = "general"
    aliases: dict[str, str] = {}
    if not path:
        return standard_child, aliases

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return standard_child, aliases

    standard_child = _coerce_string(data.get("standard_child")) or "general"

    raw_aliases = data.get("aliases")
    if isinstance(raw_aliases, dict):
        for raw_key, raw_value in raw_aliases.items():
            key = _coerce_string(raw_key).strip("/")
            value = _coerce_string(raw_value).strip("/")
            if key and value:
                aliases[key] = value

    return standard_child, aliases


def _scope_from_path(path: pathlib.Path, hot_dir: pathlib.Path) -> tuple[str, str]:
    try:
        relative = path.relative_to(hot_dir)
    except ValueError:
        return "", ""

    parts = list(relative.parts)
    if len(parts) < 2:
        return "", ""

    parent_slug = _coerce_string(parts[0])
    if not parent_slug:
        return "", ""

    if len(parts) == 2:
        child_slug = "index"
    else:
        child_slug = _coerce_string(parts[-2]) or "index"

    return parent_slug, child_slug


def _apply_alias(
    parent_slug: str,
    child_slug: str,
    standard_child: str,
    aliases: dict[str, str],
) -> tuple[str, str]:
    parent = _coerce_string(parent_slug)
    child = _coerce_string(child_slug) or "index"

    key = f"{parent}/{child}" if parent else child
    alias_value = aliases.get(key)
    if alias_value:
        alias_value = alias_value.strip("/")
        if alias_value:
            parts = alias_value.split("/")
            parent = parts[0] or parent
            child = "/".join(parts[1:]) if len(parts) > 1 else ""
    elif child == "index" and standard_child:
        child = standard_child
    elif not child and standard_child:
        child = standard_child

    return parent, child


def _resolve_category_labels(
    parent_slug: str,
    child_slug: str,
    taxonomy_labels: dict[str, str],
) -> tuple[str, str]:
    parent_slug = _coerce_string(parent_slug)
    child_slug = _coerce_string(child_slug)

    parent_label = taxonomy_labels.get(parent_slug, parent_slug)
    child_label = taxonomy_labels.get(child_slug, child_slug)

    if not child_slug:
        child_label = ""

    if child_label and child_label == parent_label:
        child_label = ""

    if (not parent_label or parent_label == parent_slug) and parent_slug == "index" and child_label:
        parent_label = child_label
        child_label = ""

    return parent_label, child_label


def _scope_weight(parent_slug: str, child_slug: str) -> int:
    parent = _coerce_string(parent_slug).lower()
    child = _coerce_string(child_slug).lower()

    weight = 0
    if parent and parent != "index":
        weight += 2
    if child and child not in {"index", "general"}:
        weight += 1
    return weight


def _load_hot_items(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    candidates: Iterable[Any]
    if isinstance(payload, dict):
        for key in ("items", "posts", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
        else:
            candidates = []
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []

    normalized: list[dict[str, Any]] = []
    for entry in candidates:
        if isinstance(entry, dict):
            normalized.append(entry)
    return normalized


def _extract_published_at(item: dict[str, Any]) -> tuple[_dt.datetime | None, str]:
    fallback_text = ""
    for field in DATE_FIELDS:
        if field not in item:
            continue
        raw_value = item.get(field)
        parsed = _parse_datetime(raw_value)
        if parsed is not None:
            return parsed, _format_datetime(parsed, raw_value)
        if not fallback_text:
            fallback_text = _coerce_string(raw_value)
    return None, fallback_text


def _normalize_hot_item(
    item: dict[str, Any],
    parent_slug: str,
    child_slug: str,
    taxonomy_labels: dict[str, str],
) -> tuple[dict[str, str], _dt.datetime, int] | None:
    post_id = _first_string(item, ("slug", "id", "guid", "url", "canonical", "source"))
    if not post_id:
        return None

    title = _first_string(item, ("title", "name", "headline"))
    if not title:
        return None

    url = _first_string(item, ("canonical", "url", "permalink", "link"))
    if not url:
        url = _first_string(item, ("source",))
    if not url:
        return None

    source = _first_string(item, ("source", "original", "url", "link")) or url
    excerpt = _first_string(item, ("excerpt", "summary", "description", "subtitle", "dek"))
    thumbnail = _first_string(
        item,
        ("thumbnail", "cover", "image", "img", "picture", "image_url", "cover_image"),
    )

    published_dt, published_text = _extract_published_at(item)
    if published_dt is None:
        published_dt = _dt.datetime.min

    category_label, subcategory_label = _resolve_category_labels(
        parent_slug, child_slug, taxonomy_labels
    )

    entry = {
        "id": post_id,
        "title": title,
        "url": url,
        "category": category_label,
        "subcategory": subcategory_label,
        "source": source,
        "published_at": published_text,
        "excerpt": excerpt,
        "thumbnail": thumbnail,
    }

    weight = _scope_weight(parent_slug, child_slug)
    return entry, published_dt, weight


def build_posts(
    *,
    hot_dir: pathlib.Path,
    taxonomy_path: pathlib.Path | None = None,
    alias_path: pathlib.Path | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, str]]:
    hot_dir = hot_dir.expanduser()
    if not hot_dir.exists():
        return []

    taxonomy_labels = _load_taxonomy_labels(taxonomy_path)
    standard_child, aliases = _load_alias_config(alias_path)

    best_by_id: dict[str, tuple[int, _dt.datetime, dict[str, str]]] = {}

    for path in sorted(hot_dir.rglob("index.json")):
        if not path.is_file():
            continue
        parent_slug, child_slug = _scope_from_path(path, hot_dir)
        if not parent_slug and not child_slug:
            continue
        parent_slug, child_slug = _apply_alias(parent_slug, child_slug, standard_child, aliases)
        items = _load_hot_items(path)
        for raw_item in items:
            normalized = _normalize_hot_item(raw_item, parent_slug, child_slug, taxonomy_labels)
            if not normalized:
                continue
            entry, sort_dt, weight = normalized
            post_id = entry["id"]
            current = best_by_id.get(post_id)
            if current is None:
                best_by_id[post_id] = (weight, sort_dt, entry)
            else:
                current_weight, current_dt, _ = current
                if weight > current_weight or (weight == current_weight and sort_dt > current_dt):
                    best_by_id[post_id] = (weight, sort_dt, entry)

    if not best_by_id:
        return []

    sorted_records = sorted(
        best_by_id.values(),
        key=lambda record: (record[1], record[2].get("title", "")),
        reverse=True,
    )

    posts = [record[2] for record in sorted_records]
    if limit and limit > 0:
        posts = posts[:limit]
    return posts


def _positive_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return parsed if parsed > 0 else DEFAULT_LIMIT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build data/posts.json from hot shards.")
    parser.add_argument("--hot-dir", type=pathlib.Path, default=HOT_DIR, help="Directory containing hot shards")
    parser.add_argument("--taxonomy", type=pathlib.Path, default=TAXONOMY_PATH, help="Path to taxonomy.json")
    parser.add_argument("--aliases", type=pathlib.Path, default=ALIASES_PATH, help="Path to category_aliases.json")
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT_PATH, help="Where to write posts.json")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum number of posts to keep")

    args = parser.parse_args(argv)

    limit = args.limit if args.limit > 0 else DEFAULT_LIMIT

    posts = build_posts(
        hot_dir=args.hot_dir,
        taxonomy_path=args.taxonomy if args.taxonomy.exists() else None,
        alias_path=args.aliases if args.aliases.exists() else None,
        limit=limit,
    )

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(posts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(posts)} posts to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
