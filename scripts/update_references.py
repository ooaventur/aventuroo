#!/usr/bin/env python3
"""Update path references across the repository based on the migration plan.

The script performs safe find/replace operations for the path mappings defined in
``migration/plan.json``. Only text files with a whitelisted extension are
considered. When run without ``--dry-run`` the script will rewrite the affected
files and store a unified diff of all modifications in ``out/replace.diff``.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence, Tuple

ALLOWED_EXTENSIONS = {".html", ".js", ".css", ".py", ".yml", ".yaml", ".md"}
EXCLUDED_DIRECTORIES = {".git", "node_modules", "out", "__pycache__"}
EXCLUDED_FILES = {Path("js/jquery.js"), Path("js/jquery.migrate.js")}


def load_replacements(plan_path: Path) -> List[Tuple[str, str]]:
    """Load the migration plan and return a list of (old, new) replacements."""
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - defensive programming
        raise SystemExit(f"Migration plan not found: {plan_path}") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive programming
        raise SystemExit(f"Migration plan is not valid JSON: {plan_path}\n{exc}") from exc

    replacements: List[Tuple[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        source = entry.get("from")
        target = entry.get("to")
        if isinstance(source, str) and isinstance(target, str) and source != target:
            replacements.append((source, target))

    # Sort by descending length so that longer paths are replaced before their prefixes.
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    return replacements


def iter_candidate_files(root: Path) -> Iterator[Path]:
    """Yield files under ``root`` that match the whitelisted extensions."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prevent ``os.walk`` from recursing into excluded directories.
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRECTORIES]

        current_dir = Path(dirpath)

        for filename in filenames:
            path = current_dir / filename
            if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            rel_path = path.relative_to(root)
            if rel_path in EXCLUDED_FILES:
                continue
            yield path


def apply_replacements(text: str, replacements: Sequence[Tuple[str, str]]) -> str:
    """Apply all replacements to ``text`` and return the modified result."""
    updated = text
    for source, target in replacements:
        if source in updated:
            updated = updated.replace(source, target)
    return updated


def build_diff(original: str, updated: str, file_path: Path, root: Path) -> str:
    """Construct a unified diff for the modified file."""
    rel_path = file_path.relative_to(root)
    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=str(rel_path),
        tofile=str(rel_path),
        lineterm="",
    )
    return "\n".join(diff_lines)


def process_files(
    files: Iterable[Path],
    replacements: Sequence[Tuple[str, str]],
    *,
    root: Path,
) -> Tuple[List[Tuple[Path, str]], List[str]]:
    """Process the files and return modified contents alongside diff chunks."""
    changes: List[Tuple[Path, str]] = []
    diffs: List[str] = []

    for file_path in files:
        try:
            original = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"Skipping non-UTF8 file: {file_path}", file=sys.stderr)
            continue

        updated = apply_replacements(original, replacements)
        if original == updated:
            continue

        diff_text = build_diff(original, updated, file_path, root)
        if diff_text:
            diffs.append(diff_text)
        changes.append((file_path, updated))

    return changes, diffs


def write_changes(changes: Sequence[Tuple[Path, str]]) -> None:
    for file_path, content in changes:
        file_path.write_text(content, encoding="utf-8")


def write_diff(diff_chunks: Sequence[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    diff_text = "\n".join(chunk for chunk in diff_chunks if chunk)
    destination.write_text(diff_text + ("\n" if diff_text and not diff_text.endswith("\n") else ""), encoding="utf-8")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the changes without modifying files or writing the diff file.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    root = Path(__file__).resolve().parents[1]
    plan_path = root / "migration" / "plan.json"
    replacements = load_replacements(plan_path)

    if not replacements:
        print("No replacements defined in migration plan.")
        return 0

    candidate_files = list(iter_candidate_files(root))
    changes, diffs = process_files(candidate_files, replacements, root=root)

    if not changes:
        print("No files require updates.")
        return 0

    if args.dry_run:
        diff_output = "\n\n".join(diff for diff in diffs if diff)
        if diff_output:
            print(diff_output)
        print(f"\nDry run: {len(changes)} file(s) would be updated.")
        return 0

    write_changes(changes)

    diff_path = root / "out" / "replace.diff"
    write_diff(diffs, diff_path)

    print(f"Updated {len(changes)} file(s). Diff written to {diff_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
