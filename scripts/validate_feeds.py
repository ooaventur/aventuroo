#!/usr/bin/env python3
"""Validate feed shard JSON files in data directories."""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Sequence

REQUIRED_ROOT_KEYS = ("items", "count", "updated_at", "pagination")
REQUIRED_PAGINATION_KEYS = ("total_items", "per_page", "total_pages")
REQUIRED_ITEM_FIELDS = (
    "slug",
    "title",
    "cover",
    "canonical",
    "excerpt",
    "source",
    "published_at",
    "created_at",
    "contact_url",
)


@dataclass
class ShardResult:
    path: Path
    errors: List[str]


def find_project_root() -> Path:
    """Return the repository root based on this file's location."""
    return Path(__file__).resolve().parents[1]


def iter_shard_files(base_dirs: Sequence[Path]) -> Iterable[Path]:
    """Yield every index.json and index.json.gz file below the given directories."""
    for base in base_dirs:
        if not base.exists():
            continue
        for path in base.rglob("index.json"):
            yield path
        for path in base.rglob("index.json.gz"):
            yield path


def load_json(path: Path):
    """Load JSON from a plain or gzipped shard file."""
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return json.load(handle)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:  # pragma: no cover - surfaced to caller
        raise RuntimeError(f"{path}: failed to load JSON ({exc})") from exc


def parse_iso8601_utc(raw_value: str) -> datetime:
    """Parse an ISO 8601 timestamp ensuring a UTC offset."""
    if not isinstance(raw_value, str):
        raise ValueError("timestamp must be a string")
    value = raw_value.strip()
    if not value:
        raise ValueError("timestamp cannot be empty")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - surfaced in validation
        raise ValueError(str(exc)) from exc
    offset = parsed.utcoffset()
    if offset is None:
        raise ValueError("timestamp must include a timezone offset")
    if offset != timedelta(0):
        raise ValueError("timestamp offset must be UTC")
    return parsed


def validate_root_structure(data, shard_label: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(data, dict):
        return [f"{shard_label}: root JSON structure must be an object"]

    for key in REQUIRED_ROOT_KEYS:
        if key not in data:
            errors.append(f"{shard_label}: missing required key '{key}'")

    items = data.get("items")
    if not isinstance(items, list):
        errors.append(f"{shard_label}: 'items' must be a list")
        items = []

    count = data.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        errors.append(f"{shard_label}: 'count' must be an integer")

    updated_at = data.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at.strip():
        errors.append(f"{shard_label}: 'updated_at' must be a non-empty string")

    pagination = data.get("pagination")
    if not isinstance(pagination, dict):
        errors.append(f"{shard_label}: 'pagination' must be an object")
    else:
        for key in REQUIRED_PAGINATION_KEYS:
            if key not in pagination:
                errors.append(
                    f"{shard_label}: pagination missing required key '{key}'"
                )

    for index, item in enumerate(items):
        item_label = f"{shard_label} -> items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label}: item must be an object")
            continue
        errors.extend(validate_item(item, item_label))

    return errors


def validate_item(item: dict, item_label: str) -> List[str]:
    errors: List[str] = []
    for field in REQUIRED_ITEM_FIELDS:
        if field not in item:
            errors.append(f"{item_label}: missing required field '{field}'")
            continue
        value = item[field]
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"{item_label}: field '{field}' must be a non-empty string"
            )
            continue
        if field in {"published_at", "created_at"}:
            try:
                parse_iso8601_utc(value)
            except ValueError as exc:
                errors.append(
                    f"{item_label}: field '{field}' has invalid timestamp: {exc}"
                )
    return errors


def validate_shard(path: Path, project_root: Path) -> ShardResult:
    try:
        data = load_json(path)
    except RuntimeError as exc:
        return ShardResult(path, [str(exc)])

    relative = path.relative_to(project_root)
    errors = validate_root_structure(data, str(relative))
    return ShardResult(path, errors)


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # currently unused
    project_root = find_project_root()
    targets = [project_root / "data" / "hot", project_root / "data" / "archive"]

    errors: List[str] = []
    for target in targets:
        if not target.exists():
            relative = target.relative_to(project_root)
            errors.append(f"{relative}: directory not found")

    results: List[ShardResult] = []
    for shard_path in iter_shard_files(targets):
        results.append(validate_shard(shard_path, project_root))

    errors.extend(error for result in results for error in result.errors)

    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
