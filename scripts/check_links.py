#!/usr/bin/env python3
"""Check for broken internal links in HTML and JavaScript files."""

from __future__ import annotations

import json
import os
import sys
import difflib
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple

# Directories that are ignored while walking the repository.
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "out",
    "_site",
    "__pycache__",
    ".cache",
    ".venv",
}

ALLOWED_ROOT_PREFIXES = {
    "assets",
    "css",
    "data",
    "fonts",
    "images",
    "js",
    "scripts",
}


class AttributeLinkParser(HTMLParser):
    """Extract attribute values from HTML content."""

    def __init__(self) -> None:
        super().__init__()
        self.links: Set[str] = set()

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        for _name, value in attrs:
            if value:
                self.links.add(value)

    def handle_startendtag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:  # pragma: no cover - HTMLParser hook
        self.handle_starttag(tag, attrs)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def iter_string_literals(text: str) -> Iterable[str]:
    """Yield string literals (single or double quoted) from the provided text."""

    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch in ("'", '"'):
            quote = ch
            i += 1
            escaped = False
            buffer: List[str] = []
            while i < length:
                cur = text[i]
                if escaped:
                    buffer.append(cur)
                    escaped = False
                else:
                    if cur == "\\":
                        escaped = True
                    elif cur == quote:
                        break
                    else:
                        buffer.append(cur)
                i += 1
            else:
                # Unclosed string literal – stop parsing to avoid infinite loop
                break
            literal = "".join(buffer)
            if literal:
                literal = literal.replace("\\/", "/")
                yield literal
            i += 1  # Skip closing quote
        else:
            i += 1


def is_relative_candidate(value: str) -> bool:
    if not value:
        return False
    value = value.strip()
    if not value:
        return False
    if value.startswith(("http://", "https://", "mailto:", "tel:", "data:", "javascript:", "//")):
        return False
    if value.startswith("#"):
        return False
    if any(token in value for token in ("{{", "}}", "{%", "%}", "<", ">")):
        return False
    if value.startswith("?"):
        return False
    # Basic scheme detection (e.g. ftp:, chrome-extension:)
    if ":" in value.split("/")[0]:
        return False
    return value.startswith(("/", "./", "../")) or "/" in value


def sanitize_url(raw: str) -> str:
    url = raw.strip()
    if not url:
        return ""
    for sep in ("#", "?"):
        if sep in url:
            url = url.split(sep, 1)[0]
    return url.strip()


def should_check_path(path: str) -> bool:
    if not path:
        return False
    normalized = path.replace("\\", "/")
    if normalized in {"", "/"}:
        return False
    if any(ch.isspace() for ch in normalized):
        return False
    if any(ch in normalized for ch in ('"', "'", '(', ')', ',', ';')):
        return False
    stripped = normalized.lstrip("/")
    segments = [segment for segment in stripped.split("/") if segment]
    if normalized.startswith("../") or normalized.startswith("./"):
        pass
    elif segments:
        first = segments[0]
        if first not in ALLOWED_ROOT_PREFIXES:
            return False
    else:
        return False

    last_segment = (segments[-1] if segments else "").rstrip()
    if not last_segment:
        return False
    if "." not in last_segment:
        return False
    return True


def join_and_normalize(base: Path, relative: str, repo_root: Path) -> Optional[Path]:
    candidate_str = os.path.normpath(os.path.join(str(base), relative))
    candidate = Path(candidate_str)
    try:
        common = os.path.commonpath([str(repo_root), str(candidate)])
    except ValueError:
        return None
    if common != str(repo_root):
        return None
    return candidate


def gather_candidate_paths(url: str, source_path: Path, repo_root: Path) -> Tuple[str, List[Path]]:
    sanitized = sanitize_url(url)
    sanitized = sanitized.replace("\\", "/")
    if not should_check_path(sanitized):
        return sanitized, []

    candidates: List[Path] = []
    seen: Set[str] = set()
    source_dir = source_path.parent

    def add_candidate(path: Optional[Path]) -> None:
        if path is None:
            return
        abs_path = Path(os.path.abspath(str(path)))
        key = abs_path.as_posix()
        if key in seen:
            return
        try:
            common = os.path.commonpath([str(repo_root), str(abs_path)])
        except ValueError:
            return
        if common != str(repo_root):
            return
        seen.add(key)
        candidates.append(abs_path)

    if sanitized.startswith("/"):
        trimmed = sanitized.lstrip("/")
        target = repo_root / trimmed
        add_candidate(target)
    else:
        add_candidate(join_and_normalize(source_dir, sanitized, repo_root))
        add_candidate(join_and_normalize(repo_root, sanitized, repo_root))

    return sanitized, candidates


def candidate_rel_paths(candidates: Sequence[Path], repo_root: Path) -> List[str]:
    rels: List[str] = []
    for candidate in candidates:
        try:
            rel = os.path.relpath(candidate, repo_root)
        except ValueError:
            continue
        rels.append(rel.replace(os.sep, "/"))
    return rels


def paths_exist(candidates: Sequence[Path]) -> bool:
    for candidate in candidates:
        if candidate.exists():
            return True
    return False


def build_existing_paths(repo_root: Path) -> Tuple[List[str], dict]:
    existing: List[str] = []
    lookup: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        base = Path(dirpath)
        for filename in filenames:
            full_path = base / filename
            try:
                rel = full_path.relative_to(repo_root)
            except ValueError:
                continue
            rel_str = rel.as_posix()
            existing.append(rel_str)
            lookup[rel_str] = full_path
    return existing, lookup


def find_suggestion(
    url: str,
    candidate_rel: Sequence[str],
    existing_rel: Sequence[str],
    existing_lookup: dict,
    source_path: Path,
    repo_root: Path,
) -> Optional[str]:
    if not existing_rel:
        return None
    search_keys: List[str] = []
    url_stripped = url.lstrip("/")
    if url_stripped:
        search_keys.append(url_stripped)

    if url.startswith("./"):
        normalized = url[2:]
        if normalized:
            search_keys.append(normalized)
    elif url.startswith("../"):
        trimmed = url
        while trimmed.startswith("../"):
            trimmed = trimmed[3:]
        if trimmed:
            search_keys.append(trimmed)

    search_keys.extend(candidate_rel)

    for key in search_keys:
        matches = difflib.get_close_matches(key, existing_rel, n=1, cutoff=0.6)
        if not matches:
            continue
        match_rel = matches[0]
        match_path = existing_lookup.get(match_rel)
        if not match_path:
            continue
        if url.startswith("/"):
            return "/" + match_rel
        if url.startswith("./") or url.startswith("../"):
            try:
                rel = os.path.relpath(match_path, source_path.parent)
            except ValueError:
                rel = match_rel
            rel = rel.replace(os.sep, "/")
            if url.startswith("./") and not rel.startswith("."):
                rel = "./" + rel
            return rel
        return match_rel
    return None


def extract_links_from_html(path: Path) -> Set[str]:
    text = read_text(path)
    parser = AttributeLinkParser()
    try:
        parser.feed(text)
    except Exception:
        # HTMLParser can fail on malformed content; ignore and fall back to literals
        parser.close()
    links = set(parser.links)
    for literal in iter_string_literals(text):
        if literal:
            links.add(literal)
    return links


def extract_links_from_js(path: Path) -> Set[str]:
    text = read_text(path)
    return {literal for literal in iter_string_literals(text) if literal}


def walk_source_files(repo_root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for filename in filenames:
            if filename.endswith((".html", ".js")):
                yield Path(dirpath) / filename


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    files = list(walk_source_files(repo_root))
    existing_rel, existing_lookup = build_existing_paths(repo_root)

    broken: List[dict] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    for file_path in files:
        try:
            if file_path.suffix == ".html":
                values = extract_links_from_html(file_path)
            else:
                values = extract_links_from_js(file_path)
        except OSError:
            continue
        source_rel = file_path.relative_to(repo_root).as_posix()
        for value in values:
            if not is_relative_candidate(value):
                continue
            sanitized, candidates = gather_candidate_paths(value, file_path, repo_root)
            if not sanitized or not candidates:
                continue
            if paths_exist(candidates):
                continue
            rel_candidates = candidate_rel_paths(candidates, repo_root)
            key = (source_rel, value)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            suggestion = find_suggestion(sanitized, rel_candidates, existing_rel, existing_lookup, file_path, repo_root)
            broken.append({
                "source_file": source_rel,
                "href": value,
                "suggestion": suggestion,
            })

    broken.sort(key=lambda item: (item["source_file"], item["href"]))

    out_dir = repo_root / "out"
    out_dir.mkdir(exist_ok=True)
    output_path = out_dir / "broken_links.json"
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(broken, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    if broken:
        print(f"Found {len(broken)} broken link(s). Details written to {output_path}.")
        return 1

    print("No broken internal links detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
