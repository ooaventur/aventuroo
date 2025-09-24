#!/usr/bin/env python3
"""Detect and optionally remove duplicate images in the repository.

The script scans ``images/`` and ``assets/images/`` directories, computes an
MD5 hash for each image file and identifies duplicates. When run with
``--apply`` it removes redundant copies and rewrites references in HTML and JS
files so that only the retained image path remains referenced. Running with
``--dry-run`` (the default) keeps the filesystem untouched and only reports what
would change. A JSON log with the findings is stored in ``out/image_dedupe.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Sequence

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".bmp",
    ".tiff",
}
TEXT_EXTENSIONS = {".html", ".js"}
EXCLUDED_DIRECTORIES = {".git", "node_modules", "out", "__pycache__"}
LOG_PATH = Path("out/image_dedupe.json")


@dataclass(frozen=True)
class ReplacementSpec:
    """Specification of a string replacement in repository files."""

    source: str
    target: str
    duplicate_rel: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the duplicates without modifying the filesystem (default).",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite references and delete redundant files.",
    )
    return parser.parse_args(argv)


def iter_image_files(directories: Iterable[Path]) -> Iterator[Path]:
    """Yield image files residing under the provided directories."""

    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                yield path


def compute_md5(path: Path) -> str:
    """Return the MD5 hash of the file at ``path``."""

    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def group_by_hash(paths: Sequence[Path]) -> Dict[str, List[Path]]:
    """Group ``paths`` by their MD5 hash."""

    groups: Dict[str, List[Path]] = {}
    for path in paths:
        hash_value = compute_md5(path)
        groups.setdefault(hash_value, []).append(path)
    return groups


def choose_canonical(paths: Sequence[Path], root: Path) -> Path:
    """Choose which path should be retained from duplicate candidates."""

    def sort_key(path: Path) -> tuple[int, int, str]:
        rel = to_repo_relative(path, root)
        priority = 0 if rel.startswith("images/") else 1
        return (priority, len(rel), rel)

    return sorted(paths, key=sort_key)[0]


def to_repo_relative(path: Path, root: Path) -> str:
    """Return ``path`` as a POSIX-style string relative to ``root``."""

    return path.relative_to(root).as_posix()


def iter_text_files(root: Path) -> Iterator[Path]:
    """Yield HTML and JS files that may reference images."""

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRECTORIES]
        current_dir = Path(dirpath)
        for filename in filenames:
            path = current_dir / filename
            if path.suffix.lower() in TEXT_EXTENSIONS:
                yield path


def build_replacements(
    duplicate_groups: Dict[str, List[Path]],
    root: Path,
) -> tuple[List[ReplacementSpec], Dict[str, str]]:
    """Create replacement specifications for duplicate images.

    Returns a tuple with:
        * A list of ``ReplacementSpec`` entries for applying replacements.
        * A mapping of duplicate file (repo-relative) -> canonical file.
    """

    replacements: List[ReplacementSpec] = []
    duplicate_to_canonical: Dict[str, str] = {}

    for _hash_value, paths in duplicate_groups.items():
        canonical = choose_canonical(paths, root)
        canonical_rel = to_repo_relative(canonical, root)
        ordered_paths = sorted(paths, key=lambda p: to_repo_relative(p, root))
        for duplicate in ordered_paths:
            if duplicate == canonical:
                continue
            duplicate_rel = to_repo_relative(duplicate, root)
            duplicate_to_canonical[duplicate_rel] = canonical_rel
            replacements.append(
                ReplacementSpec(source=duplicate_rel, target=canonical_rel, duplicate_rel=duplicate_rel)
            )
            replacements.append(
                ReplacementSpec(
                    source=f"/{duplicate_rel}",
                    target=f"/{canonical_rel}",
                    duplicate_rel=duplicate_rel,
                )
            )
    replacements.sort(key=lambda spec: len(spec.source), reverse=True)
    return replacements, duplicate_to_canonical


def apply_replacements(
    replacements: Sequence[ReplacementSpec],
    root: Path,
) -> tuple[List[tuple[Path, str]], Dict[str, List[str]]]:
    """Apply replacements to HTML/JS files and return the modifications.

    The second return value maps duplicate image paths to the list of files where
    their references were updated.
    """

    changes: List[tuple[Path, str]] = []
    usage: Dict[str, List[str]] = {}

    if not replacements:
        return changes, usage

    for file_path in iter_text_files(root):
        try:
            original = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        updated = original
        applied_duplicates: set[str] = set()
        for spec in replacements:
            if spec.source in updated:
                updated = updated.replace(spec.source, spec.target)
                applied_duplicates.add(spec.duplicate_rel)

        if updated != original:
            changes.append((file_path, updated))
            rel_file = to_repo_relative(file_path, root)
            for duplicate_rel in applied_duplicates:
                usage.setdefault(duplicate_rel, []).append(rel_file)

    return changes, usage


def write_changes(changes: Sequence[tuple[Path, str]]) -> None:
    for file_path, content in changes:
        file_path.write_text(content, encoding="utf-8")


def remove_files(paths: Iterable[Path], root: Path) -> tuple[List[str], Dict[str, str]]:
    """Delete files and return a list of removed paths and any errors."""

    removed: List[str] = []
    errors: Dict[str, str] = {}
    for path in paths:
        try:
            rel_path = path.relative_to(root).as_posix()
        except ValueError:
            rel_path = path.as_posix()
        try:
            path.unlink()
            removed.append(rel_path)
        except FileNotFoundError:
            removed.append(rel_path)
        except OSError as exc:
            errors[rel_path] = str(exc)
    return removed, errors


def build_log(
    *,
    mode: str,
    total_images: int,
    duplicate_groups: Dict[str, List[Path]],
    canonical_map: Dict[str, str],
    replacements_usage: Dict[str, List[str]],
    removed_files: List[str],
    removal_errors: Dict[str, str],
    root: Path,
) -> Dict[str, object]:
    """Construct the JSON log payload."""

    duplicate_entries: List[Dict[str, object]] = []
    removed_set = set(removed_files)
    for hash_value, paths in sorted(duplicate_groups.items(), key=lambda item: item[0]):
        canonical = choose_canonical(paths, root)
        canonical_rel = to_repo_relative(canonical, root)
        duplicates_info: List[Dict[str, object]] = []
        for path in sorted(paths, key=lambda p: to_repo_relative(p, root)):
            rel_path = to_repo_relative(path, root)
            if rel_path == canonical_rel:
                status = "kept"
            elif rel_path in removed_set:
                status = "removed"
            else:
                status = "pending" if mode == "dry-run" else "error"
            duplicates_info.append(
                {
                    "path": rel_path,
                    "status": status,
                    "references_updated_in": sorted(set(replacements_usage.get(rel_path, []))),
                    "canonical_target": canonical_map.get(rel_path, canonical_rel),
                }
            )

        duplicate_entries.append(
            {
                "hash": hash_value,
                "kept": canonical_rel,
                "duplicates": duplicates_info,
            }
        )

    summary = {
        "mode": mode,
        "total_images_scanned": total_images,
        "duplicate_sets": len(duplicate_entries),
        "files_with_reference_updates": sorted(
            {file for files in replacements_usage.values() for file in files}
        ),
        "removed_files": sorted(removed_set),
    }
    if removal_errors:
        summary["removal_errors"] = removal_errors

    return {"summary": summary, "duplicates": duplicate_entries}


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or [])
    mode = "apply" if args.apply else "dry-run"

    root = Path(__file__).resolve().parents[1]
    image_directories = [root / "images", root / "assets" / "images"]

    image_files = list(iter_image_files(image_directories))
    hash_groups = group_by_hash(image_files)
    duplicate_groups = {hash_value: paths for hash_value, paths in hash_groups.items() if len(paths) > 1}

    replacements, duplicate_map = build_replacements(duplicate_groups, root)
    changes, replacements_usage = apply_replacements(replacements, root)

    if args.apply and changes:
        write_changes(changes)

    files_to_remove = [root / rel for rel in duplicate_map] if args.apply else []
    removed_files, removal_errors = ([], {})
    if args.apply and files_to_remove:
        removed_files, removal_errors = remove_files(files_to_remove, root)

    log_payload = build_log(
        mode=mode,
        total_images=len(image_files),
        duplicate_groups=duplicate_groups,
        canonical_map=duplicate_map,
        replacements_usage=replacements_usage,
        removed_files=removed_files,
        removal_errors=removal_errors,
        root=root,
    )

    log_path = root / LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log_payload, indent=2) + "\n", encoding="utf-8")

    if not duplicate_groups:
        print("No duplicate images found.")
        return 0

    if args.apply:
        print(
            f"Removed {len(removed_files)} duplicate file(s) and updated {len(changes)} referencing file(s)."
        )
    else:
        print(
            f"Dry run: {len(duplicate_groups)} duplicate set(s) detected. "
            f"{len(changes)} file(s) would be updated."
        )

    if removal_errors:
        print("Encountered errors while deleting files:")
        for path, error in removal_errors.items():
            print(f"  {path}: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
