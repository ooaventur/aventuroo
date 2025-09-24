#!/usr/bin/env python3
"""Project auditing utility for Aventuroo.

This script inspects the project directory, gathering metadata about files,
listing files that live in legacy directories, and reporting code references to
legacy paths. Only the Python standard library is used, and the script can be
run directly from the command line.

Example usage::

    python scripts/audit_project.py
    python scripts/audit_project.py --root . --output out/custom_audit.json
    python scripts/audit_project.py --exclude "node_modules|dist|tmp"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Dict, Iterator, List, Sequence, Tuple

DEFAULT_EXCLUDE = r"node_modules|dist|\.git|\.cache"
LEGACY_DIRECTORIES: Sequence[Tuple[str, Path]] = (
    ("json/", Path("json")),
    ("feeds/", Path("feeds")),
    ("old_data/", Path("old_data")),
    ("build/json/", Path("build") / "json"),
)
SCAN_EXTENSIONS = {".html", ".htm", ".js", ".css", ".py", ".yml", ".yaml"}
REFERENCE_TARGETS = ("/json/", "/feeds/", "/old_data/", "/build/json/")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the script."""

    parser = argparse.ArgumentParser(
        description="Audit the project tree for legacy assets and references.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent(
            """
            The audit traverses the project root while skipping directories that
            match the exclusion regular expression. Use the --exclude option to
            provide a custom pattern if desired.

            Examples:
              python scripts/audit_project.py
              python scripts/audit_project.py --root . --output out/audit.json
              python scripts/audit_project.py --exclude "node_modules|dist|tmp"
            """
        ),
    )
    default_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--root",
        default=str(default_root),
        help="Path to the project root to audit (defaults to the repository root).",
    )
    parser.add_argument(
        "--exclude",
        default=DEFAULT_EXCLUDE,
        help=(
            "Regular expression matching directories or files to exclude from the walk. "
            "Defaults to 'node_modules|dist|\\.git|\\.cache'."
        ),
    )
    parser.add_argument(
        "--output",
        default="out/audit.json",
        help="Destination JSON file for the audit report (relative to the root by default).",
    )
    return parser.parse_args()


def walk_files(root: Path, exclude_pattern: re.Pattern[str]) -> Iterator[Tuple[Path, Path]]:
    """Yield file paths and their relative paths while respecting exclusions."""

    for current_root, dirs, files in os.walk(root):
        current_root_path = Path(current_root)
        filtered_dirs: List[str] = []
        for directory in dirs:
            dir_path = current_root_path / directory
            rel_dir = dir_path.relative_to(root)
            if exclude_pattern.search(rel_dir.as_posix()):
                continue
            filtered_dirs.append(directory)
        dirs[:] = filtered_dirs

        for file_name in files:
            file_path = current_root_path / file_name
            rel_file = file_path.relative_to(root)
            if exclude_pattern.search(rel_file.as_posix()):
                continue
            yield file_path, rel_file


def is_under(path: Path, prefix: Path) -> bool:
    """Return True if ``path`` is within ``prefix`` (both treated as relative paths)."""

    prefix_parts = prefix.parts
    path_parts = path.parts
    if len(path_parts) < len(prefix_parts):
        return False
    return path_parts[: len(prefix_parts)] == prefix_parts


def file_metadata(file_path: Path) -> Tuple[int, str]:
    """Return a tuple with the file size in bytes and ISO 8601 modified time."""

    stat_result = file_path.stat()
    size_bytes = stat_result.st_size
    modified = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat()
    return size_bytes, modified


def scan_for_references(file_path: Path, rel_path: Path) -> List[Dict[str, object]]:
    """Scan a text file for legacy reference targets."""

    results: List[Dict[str, object]] = []
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                line_content = line.rstrip("\n")
                for target in REFERENCE_TARGETS:
                    start = 0
                    while True:
                        index = line_content.find(target, start)
                        if index == -1:
                            break
                        snippet = line_content.strip()
                        results.append(
                            {
                                "file": rel_path.as_posix(),
                                "line": line_number,
                                "match": target,
                                "snippet": snippet,
                            }
                        )
                        start = index + len(target)
    except OSError as exc:  # pragma: no cover - defensive safeguard
        print(f"Warning: could not read {rel_path.as_posix()}: {exc}", file=sys.stderr)
    return results


def collect_audit_data(root: Path, exclude_regex: str) -> Tuple[Dict[str, object], Dict[str, List[Dict[str, object]]], List[Dict[str, object]]]:
    """Collect metadata, legacy listings, and reference matches for the project."""

    pattern = re.compile(exclude_regex)
    files: List[Dict[str, object]] = []
    legacy: Dict[str, List[Dict[str, object]]] = {name: [] for name, _ in LEGACY_DIRECTORIES}
    matches: List[Dict[str, object]] = []

    for file_path, rel_path in walk_files(root, pattern):
        size_bytes, modified = file_metadata(file_path)
        entry = {
            "path": rel_path.as_posix(),
            "size_bytes": size_bytes,
            "modified": modified,
        }
        files.append(entry)

        for legacy_name, legacy_path in LEGACY_DIRECTORIES:
            if is_under(rel_path, legacy_path):
                legacy[legacy_name].append(entry)

        if rel_path.suffix.lower() in SCAN_EXTENSIONS:
            matches.extend(scan_for_references(file_path, rel_path))

    files.sort(key=lambda item: item["path"])
    for name in legacy:
        legacy[name] = sorted(legacy[name], key=lambda item: item["path"])
    matches.sort(key=lambda item: (item["file"], item["line"], item["match"]))

    return files, legacy, matches


def build_report(root: Path, files: Sequence[Dict[str, object]], legacy: Dict[str, Sequence[Dict[str, object]]], matches: Sequence[Dict[str, object]]) -> Dict[str, object]:
    """Assemble the final JSON-serialisable report object."""

    total_size = sum(item["size_bytes"] for item in files)
    legacy_counts = {name: len(entries) for name, entries in legacy.items()}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": root.as_posix(),
        "summary": {
            "total_files": len(files),
            "total_size_bytes": total_size,
            "legacy_counts": legacy_counts,
            "reference_match_count": len(matches),
        },
        "files": list(files),
        "legacy_files": {name: list(entries) for name, entries in legacy.items()},
        "reference_matches": list(matches),
    }
    return report


def print_summary_table(report: Dict[str, object], output_path: Path) -> None:
    """Print an ASCII table summarising the report totals."""

    summary = report["summary"]
    rows = [
        ("Root", report["root"]),
        ("Total files", summary["total_files"]),
        ("Total size (bytes)", summary["total_size_bytes"]),
    ]
    for legacy_name, count in summary["legacy_counts"].items():
        rows.append((f"Legacy {legacy_name} files", count))
    rows.append(("Reference matches", summary["reference_match_count"]))
    rows.append(("Report file", output_path.as_posix()))

    header = ("Metric", "Value")
    col1_width = max(len(str(row[0])) for row in [header] + rows)
    col2_width = max(len(str(row[1])) for row in [header] + rows)

    def border(char: str = "-") -> str:
        return f"+{char * (col1_width + 2)}+{char * (col2_width + 2)}+"

    print(border("-"))
    print(f"| {header[0].ljust(col1_width)} | {header[1].ljust(col2_width)} |")
    print(border("="))
    for metric, value in rows:
        print(f"| {str(metric).ljust(col1_width)} | {str(value).ljust(col2_width)} |")
    print(border("-"))


def main() -> None:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        print(f"Error: root path {root} does not exist.", file=sys.stderr)
        sys.exit(1)
    if not root.is_dir():
        print(f"Error: root path {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path

    files, legacy, matches = collect_audit_data(root, args.exclude)
    report = build_report(root, files, legacy, matches)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print_summary_table(report, output_path)


if __name__ == "__main__":
    main()
