#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RSS → ``data/posts.json`` autoposter for AventurOO.

The script reads feed specifications from the ``FEEDS_FILE`` environment
variable when provided, otherwise it falls back to the repository default
``autopost/feeds_news.txt``. Each line should follow ``Category|URL`` format
and the resolved file must exist before running the job.

- përdor trafilatura për të nxjerrë trupin real të artikullit (jo nav/footer/skripte)
- heq çdo "code/script" nga teksti; filtron paragrafët e shkurtër/jo-kuptimplotë
- shkruan: title, category, date, author, cover, source, excerpt (~450 fjalë), content (tekst i pastër me \n\n)
"""

import datetime
import os, re, json, hashlib, pathlib, sys
from email.utils import parsedate_to_datetime

if __package__ in (None, ""):
    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from autopost.common import (
    fetch_bytes,
    http_get,
    parse_feed,
    strip_text,
    slugify,
    today_iso,
    find_cover_from_item,
    trafilatura,
    HTTP_TIMEOUT,
    limit_words_html,
    extract_body_html,
)
from autopost import SEEN_DB_FILENAME

# ---- Paths ----
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / SEEN_DB_FILENAME
FEEDS = pathlib.Path(
    os.getenv("FEEDS_FILE") or (ROOT / "autopost" / "feeds_news.txt")
)

# ---- Env / Defaults ----
MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL = int(os.getenv("MAX_TOTAL", "0"))          # 0 = pa limit total / run
TARGET_WORDS = int(os.getenv("TARGET_WORDS", "1500"))
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", str(TARGET_WORDS)))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))

DEFAULT_AUTHOR = os.getenv("DEFAULT_AUTHOR", "AventurOO Editorial")

# ---- anti-script/code cleaner për paragrafë ----
CODE_PATTERNS = [
    r"\bfunction\s*\(", r"\bvar\s+\w+\s*=", r"\blet\s+\w+\s*=", r"\bconst\s+\w+\s*=",
    r"</?\w+[^>]*>", r"[{};<>]{2,}", r"\bconsole\.log\b", r"\$\(", r"document\.querySelector",
    r"<script", r"</script", r"@media", r"window\.", r"import\s+",
]
CODE_RE = re.compile("|".join(CODE_PATTERNS), re.I)

def _normalize_date_string(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value)

    dt = None

    iso_candidate = value
    if iso_candidate.endswith("Z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(iso_candidate)
    except ValueError:
        dt = None

    if dt is None:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
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
                dt = datetime.datetime.strptime(value, fmt)
                break
            except ValueError:
                continue

    if dt is None:
        return ""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    return dt.astimezone(datetime.timezone.utc).date().isoformat()


def parse_item_date(it_elem) -> str:
    if it_elem is None:
        return today_iso()

    candidates = []
    for tag in ("pubDate", "published", "updated"):
        text = it_elem.findtext(tag)
        if text and text.strip():
            candidates.append(text.strip())

    ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
    for tag in ("published", "updated"):
        text = it_elem.findtext(f"atom:{tag}", ns_atom)
        if text and text.strip():
            candidates.append(text.strip())

    ns_dc = {"dc": "http://purl.org/dc/elements/1.1/"}
    text = it_elem.findtext("dc:date", ns_dc)
    if text and text.strip():
        candidates.append(text.strip())

    for candidate in candidates:
        normalized = _normalize_date_string(candidate)
        if normalized:
            return normalized

    return today_iso()



def clean_paragraphs(text: str) -> list:
    if not text:
        return []
    t = re.sub(r"\r\n?", "\n", text).strip()
    blocks = [b.strip() for b in re.split(r"\n{2,}", t) if b.strip()]
    cleaned = []
    for b in blocks:
        if len(b) < 30:
            continue
        if CODE_RE.search(b):
            continue
        cleaned.append(b)
    if not cleaned and blocks:
        cleaned = [x for x in blocks if len(x) > 30][:10]
    return cleaned


def extract_with_trafilatura(url: str) -> dict:
    if trafilatura is None:
        return {}
    from trafilatura.settings import use_config
    cfg = use_config()
    cfg.set("DEFAULT", "EXTRACTION_TIMEOUT", str(HTTP_TIMEOUT))
    downloaded = trafilatura.fetch_url(url, config=cfg)
    if not downloaded:
        return {}
    result = trafilatura.extract(
        downloaded,
        config=cfg,
        include_comments=False,
        include_tables=False,
        include_images=False,
        with_metadata=True,
    )
    if not result:
        return {}
    try:
        data = json.loads(result)
    except Exception:
        data = {"text": str(result)}
    return {
        "text": data.get("text") or "",
        "title": data.get("title") or "",
        "author": data.get("author") or "",
        "image": data.get("image") or "",
        "description": data.get("description") or "",
    }


def shorten_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if len(words) <= max_words:
        return (text or "").strip()
    return " ".join(words[:max_words]) + "…"


def ensure_unique_slug(slug: str, existing_slugs: set[str], max_length: int = 70) -> str:
    """Return a slug that is unique within ``existing_slugs``.

    The original ``slug`` is used when possible; otherwise a numeric suffix is
    appended while respecting the ``max_length`` constraint. The chosen slug is
    added to ``existing_slugs``.
    """

    cleaned = (slug or "").strip()
    if not cleaned:
        cleaned = "post"
    cleaned = cleaned[:max_length].rstrip("-")
    if not cleaned:
        cleaned = "post"

    candidate = cleaned
    if candidate not in existing_slugs:
        existing_slugs.add(candidate)
        return candidate

    suffix = 2
    while True:
        suffix_str = str(suffix)
        base_length = max_length - len(suffix_str) - 1
        base = cleaned[:base_length].rstrip("-") if base_length > 0 else ""
        if base:
            candidate = f"{base}-{suffix_str}"
        else:
            candidate = suffix_str[-max_length:]
        if candidate not in existing_slugs:
            existing_slugs.add(candidate)
            return candidate
        suffix += 1


def main():
    DATA_DIR.mkdir(exist_ok=True)

    if SEEN_DB.exists():
        try:
            seen = json.loads(SEEN_DB.read_text(encoding="utf-8"))
            if not isinstance(seen, dict):
                seen = {}
        except json.JSONDecodeError:
            seen = {}
    else:
        seen = {}

    if POSTS_JSON.exists():
        try:
            posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
            if not isinstance(posts_idx, list):
                posts_idx = []
        except json.JSONDecodeError:
            posts_idx = []
    else:
        posts_idx = []

    existing_slugs = {
        str(p.get("slug")).strip()
        for p in posts_idx
        if isinstance(p, dict) and p.get("slug")
    }
    if not FEEDS.exists():
        print("ERROR: feeds file not found:", FEEDS)
        return

    added_total = 0
    per_cat = {}
    new_entries = []

    for raw in FEEDS.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        if "|" not in raw:
            continue
        cat, url = raw.split("|", 1)
        category = (cat or "").strip().title()
        feed_url = (url or "").strip()
        if not category or not feed_url:
            continue
        if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
            break
        if MAX_PER_CAT > 0 and per_cat.get(category, 0) >= MAX_PER_CAT:
            continue

        xml = fetch_bytes(feed_url)
        if not xml:
            continue

        items = parse_feed(xml)

        for it in items:
            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break

            if MAX_PER_CAT > 0 and per_cat.get(category, 0) >= MAX_PER_CAT:
                break

            title = (it.get("title") or "").strip()
            link = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            description = (it.get("summary") or "").strip()
            it_elem = it.get("element")
            lead_image = ""
            author = ""
            rights = ""
            if it_elem is not None:
                try:
                    lead_image = find_cover_from_item(it_elem, link)
                except Exception:
                    lead_image = ""

                author_el = it_elem.find("author")
                if author_el is not None and (author_el.text or "").strip():
                    author = author_el.text.strip()

                if not author:
                    ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
                    atom_author = it_elem.find("atom:author/atom:name", ns_atom)
                    if atom_author is not None and (atom_author.text or "").strip():
                        author = atom_author.text.strip()

                ns_dc = {"dc": "http://purl.org/dc/elements/1.1/"}
                if not author:
                    creator = it_elem.find("dc:creator", ns_dc)
                    if creator is not None and (creator.text or "").strip():
                        author = creator.text.strip()

                rights_el = it_elem.find("dc:rights", ns_dc)
                if rights_el is not None and (rights_el.text or "").strip():
                    rights = rights_el.text.strip()
                if not rights:
                    rights_el = it_elem.find("rights")
                    if rights_el is not None and (rights_el.text or "").strip():
                        rights = rights_el.text.strip()

            author = author or DEFAULT_AUTHOR
            rights = rights or "Unknown"

            try:
                body_html, first_body_image = extract_body_html(link)
            except Exception:
                body_html, first_body_image = "", ""

            article_text = strip_text(body_html)
            if not article_text:
                article_text = strip_text(description)

            paragraphs = clean_paragraphs(article_text)
            content_text = "\n\n".join(paragraphs).strip()
            if not content_text:
                content_text = article_text
            content_text = limit_words_html(content_text, TARGET_WORDS)
           
            base_excerpt = content_text or strip_text(description) or title
            excerpt_text = shorten_words(base_excerpt, SUMMARY_WORDS)

            cover = (lead_image or first_body_image or "").strip()
            if cover and not cover.lower().startswith(("http://", "https://")):
                cover = ""

            date = parse_item_date(it_elem)
            slug = ensure_unique_slug(slugify(title)[:70], existing_slugs)

            entry = {
                "slug": slug,
                "title": title,
                "category": category,
                "date": date,
                "author": author,
                "rights": rights,
                "source": link,
                "excerpt": excerpt_text,
                "body": content_text,
            }
            if cover:
                entry["cover"] = cover

            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": category, "created": date}
            per_cat[category] = per_cat.get(category, 0) + 1
            added_total += 1
            print(f"Added [{category}]: {title} (by {author})")

        if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
            break

    if not new_entries:
        print("New posts this run: 0"); return

    posts_idx = new_entries + posts_idx
    if MAX_POSTS_PERSIST > 0:
        posts_idx = posts_idx[:MAX_POSTS_PERSIST]

    POSTS_JSON.write_text(json.dumps(posts_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("New posts this run:", len(new_entries))

if __name__ == "__main__":
    main()
