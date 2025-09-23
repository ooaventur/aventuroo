#!/usr/bin/env python3
"""Generate category and subcategory feed files from raw inputs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

# Resolve the important project directories relative to this script location.
ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config.json"
RAW_DIR = ROOT_DIR / "out" / "raw"
DATA_DIR = ROOT_DIR / "data"


def load_json_array(path: Path) -> List[Dict[str, object]]:
    """Load a JSON array from *path*, returning an empty list if it is missing."""
    # Early return when the source file is not available so processing can continue.
    if not path.exists():
        return []

    try:
        # Raw files are expected to contain a JSON list of post dictionaries.
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic aid.
        raise ValueError(f"Invalid JSON payload in {path}: {exc}") from exc

    # Guard against misconfigured payloads to keep downstream logic predictable.
    if not isinstance(data, list):
        raise ValueError(f"Expected an array in {path}, got {type(data).__name__}")

    return data


def normalise_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Convert an ISO 8601 timestamp string to a naive UTC datetime."""
    if not value:
        return None

    timestamp = value.strip()
    # Python does not recognise the trailing "Z" suffix, so translate it to an offset.
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None

    # Ensure the datetime is timezone-aware so we can safely convert to UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    # Drop the timezone information after conversion to make comparisons trivial.
    return parsed.replace(tzinfo=None)


def make_post_key(post: Dict[str, object]) -> Optional[str]:
    """Build a stable identifier for a post to prevent duplicates when merging."""
    # Prefer strong identifiers when available to avoid relying on the whole payload.
    for key in ("id", "slug", "url", "link"):
        value = post.get(key)
        if isinstance(value, str) and value:
            return f"{key}:{value}"

    # Fall back to the title field if it is the only meaningful attribute present.
    title = post.get("title")
    if isinstance(title, str) and title:
        return f"title:{title}"

    return None


def merge_posts(base_posts: Sequence[Dict[str, object]], extra_sets: Iterable[Sequence[Dict[str, object]]]) -> List[Dict[str, object]]:
    """Combine category level posts with any additional subcategory entries."""
    merged: List[Dict[str, object]] = list(base_posts)
    # Track the keys we have already seen to prevent duplicate entries in the output.
    seen_keys = {make_post_key(post) for post in merged}

    for posts in extra_sets:
        for post in posts:
            key = make_post_key(post)
            # Only append new posts that have not been observed previously.
            if key and key in seen_keys:
                continue

            merged.append(post)
            if key:
                seen_keys.add(key)

    return merged


def filter_recent(posts: Sequence[Dict[str, object]], cutoff: datetime) -> List[Dict[str, object]]:
    """Select posts with a ``published_at`` newer than the supplied cutoff."""
    filtered: List[Dict[str, object]] = []
    for post in posts:
        # Normalise each timestamp so we can compare the values reliably.
        published = normalise_timestamp(post.get("published_at"))  # type: ignore[arg-type]
        if published and published >= cutoff:
            filtered.append(post)
    return filtered


def write_json(path: Path, payload: object) -> None:
    """Write *payload* to *path* as formatted JSON, creating directories as needed."""
    # Ensure the destination folder exists before writing the output file.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    """Build category and subcategory feeds using the configured window."""
    # Load the configuration so we know which categories and subcategories to process.
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    window_days = int(config.get("window_days", 0))
    categories: Dict[str, Dict[str, object]] = config.get("categories", {})

    # Derive the cutoff that defines the time window for valid posts.
    cutoff = datetime.utcnow() - timedelta(days=window_days)

    generated_paths: List[str] = []
    category_count = 0
    subcategory_count = 0

    # Walk through each category defined in the configuration file.
    for category, meta in categories.items():
        base_posts = load_json_array(RAW_DIR / f"{category}.json")
        subcats: Sequence[str] = meta.get("subcats", [])  # type: ignore[assignment]

        # Build a mapping of subcategory name to its list of posts.
        subcategory_posts: Dict[str, List[Dict[str, object]]] = {}
        for subcat in subcats:
            raw_path = RAW_DIR / category / f"{subcat}.json"
            posts = load_json_array(raw_path)

            if not posts and base_posts:
                # When a dedicated subcategory file is missing, filter the category data.
                posts = [post for post in base_posts if post.get("subcategory") == subcat]

            subcategory_posts[subcat] = posts

        # Merge all posts so the category feed includes any subcategory-specific items.
        combined_posts = merge_posts(base_posts, subcategory_posts.values())
        recent_category_posts = filter_recent(combined_posts, cutoff)

        # Always write the category feed, even if it ends up empty after filtering.
        category_output = DATA_DIR / "categories" / category / "index.json"
        write_json(category_output, recent_category_posts)
        generated_paths.append(str(category_output.relative_to(DATA_DIR)))
        category_count += 1

        # Write feeds for subcategories that still contain posts after filtering.
        for subcat, posts in subcategory_posts.items():
            recent_posts = filter_recent(posts, cutoff)
            if not recent_posts:
                continue

            subcat_output = DATA_DIR / "categories" / category / "subcats" / subcat / "index.json"
            write_json(subcat_output, recent_posts)
            generated_paths.append(str(subcat_output.relative_to(DATA_DIR)))
            subcategory_count += 1

    # Store a manifest containing every generated feed path (relative to the data folder).
    index_path = DATA_DIR / "index.json"
    write_json(index_path, sorted(generated_paths))

    # Provide a short summary so the operator knows what has been produced.
    print(f"Generated feeds for {category_count} categories / {subcategory_count} subcategories.")
    print("Feed build complete.")


if __name__ == "__main__":
    main()
