#!/usr/bin/env python3
"""Validate archive structure files for Aventuroo."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = REPO_ROOT / "data" / "archive"
MANIFEST_PATH = ARCHIVE_DIR / "manifest.json"
SUMMARY_PATH = ARCHIVE_DIR / "summary.json"

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PATH_PATTERN = re.compile(
    r"^(?P<category>[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"(?P<subcategory>[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"(?P<year>\d{4})/(?P<month>\d{2})/index\.json$"
)
PATH_GZ_PATTERN = re.compile(
    r"^(?P<category>[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"(?P<subcategory>[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"(?P<year>\d{4})/(?P<month>\d{2})/index\.json\.gz$"
)


@dataclass(frozen=True)
class ArchiveKey:
    category: str
    subcategory: str
    year: str
    month: str


class ValidationError(Exception):
    """Raised when archive validation fails."""


def load_json(path: Path) -> Dict[str, object]:
    """Load a JSON file and return its contents."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - handled upstream
        raise ValidationError(f"Required file missing: {path.as_posix()}") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValidationError(f"Invalid JSON in {path.as_posix()}: {exc}") from exc


def ensure_slug(value: str, label: str, errors: List[str]) -> None:
    """Ensure ``value`` adheres to the kebab-case slug format."""

    if not SLUG_PATTERN.fullmatch(value):
        errors.append(f"{label} '{value}' is not kebab-case")


def build_manifest_index(manifest: Dict[str, object], errors: List[str]) -> Dict[ArchiveKey, Dict[str, str]]:
    """Return an index of manifest entries keyed by their archive coordinates."""

    shards = manifest.get("shards")
    if not isinstance(shards, list):
        raise ValidationError("Manifest JSON must contain a list under 'shards'.")

    index: Dict[ArchiveKey, Dict[str, str]] = {}
    for shard in shards:
        if not isinstance(shard, dict):
            errors.append("Manifest shard entry is not an object; skipping entry.")
            continue

        path = shard.get("path")
        match = PATH_PATTERN.fullmatch(path or "")
        if not match:
            errors.append(f"Manifest path is invalid: {path!r}")
            continue

        key = ArchiveKey(
            category=match.group("category"),
            subcategory=match.group("subcategory"),
            year=match.group("year"),
            month=match.group("month"),
        )

        path_gz = shard.get("path_gz")
        gz_match = PATH_GZ_PATTERN.fullmatch(path_gz or "")
        if not gz_match:
            errors.append(f"Manifest gzip path is invalid: {path_gz!r}")
        elif gz_match.groupdict() != match.groupdict():
            errors.append(
                "Manifest gzip path does not match JSON path for "
                f"{key.category}/{key.subcategory} {key.year}-{key.month}: {path_gz!r}"
            )

        ensure_slug(key.category, "Category", errors)
        ensure_slug(key.subcategory, "Subcategory", errors)

        if key in index:
            errors.append(
                "Duplicate manifest entry for "
                f"{key.category}/{key.subcategory} {key.year}-{key.month}"
            )
        else:
            index[key] = {"path": path, "path_gz": path_gz or ""}

    return index


def validate_summary(summary: Dict[str, object], index: Dict[ArchiveKey, Dict[str, str]], errors: List[str]) -> None:
    """Validate that the summary references manifest entries for every subcategory."""

    parents = summary.get("parents")
    if not isinstance(parents, list):
        raise ValidationError("Summary JSON must contain a list under 'parents'.")

    for parent in parents:
        if not isinstance(parent, dict):
            errors.append("Summary parent entry is not an object; skipping entry.")
            continue

        parent_slug = parent.get("parent")
        if not isinstance(parent_slug, str):
            errors.append("Summary parent entry missing 'parent' slug; skipping children.")
            continue
        ensure_slug(parent_slug, "Category", errors)

        children = parent.get("children")
        if not isinstance(children, list):
            errors.append(f"Children listing for category '{parent_slug}' is not a list.")
            continue

        for child in children:
            if not isinstance(child, dict):
                errors.append(
                    f"Child entry within category '{parent_slug}' is not an object; skipping."
                )
                continue

            sub_slug = child.get("child")
            if not isinstance(sub_slug, str):
                errors.append(
                    f"Child entry within category '{parent_slug}' missing 'child' slug."
                )
                continue
            ensure_slug(sub_slug, "Subcategory", errors)

            months = child.get("months")
            if not isinstance(months, list):
                errors.append(
                    f"Months listing for {parent_slug}/{sub_slug} is not a list."
                )
                continue

            if not months:
                errors.append(
                    f"Subcategory {parent_slug}/{sub_slug} has no months in summary."
                )
                continue

            for month_entry in months:
                if not isinstance(month_entry, dict):
                    errors.append(
                        f"Month entry for {parent_slug}/{sub_slug} is not an object."
                    )
                    continue

                year = month_entry.get("year")
                month = month_entry.get("month")
                if not isinstance(year, int) or not isinstance(month, int):
                    errors.append(
                        f"Month entry for {parent_slug}/{sub_slug} lacks numeric year/month."
                    )
                    continue

                year_str = f"{year:04d}"
                month_str = f"{month:02d}"
                key = ArchiveKey(parent_slug, sub_slug, year_str, month_str)

                if key not in index:
                    errors.append(
                        "Missing index.json for "
                        f"{parent_slug}/{sub_slug} {year_str}-{month_str}"
                    )


def main() -> int:
    try:
        manifest = load_json(MANIFEST_PATH)
        summary = load_json(SUMMARY_PATH)
    except ValidationError as exc:
        print(exc, file=sys.stderr)
        return 1

    errors: List[str] = []
    try:
        index = build_manifest_index(manifest, errors)
        validate_summary(summary, index, errors)
    except ValidationError as exc:
        print(exc, file=sys.stderr)
        return 1

    if errors:
        print("Archive validation failed:")
        for issue in errors:
            print(f"- {issue}")
        return 1

    print("Archive structure validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
