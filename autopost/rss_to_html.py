#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RSS → data/posts.json (AventurOO)
# - përdor trafilatura për të nxjerrë trupin real të artikullit (jo nav/footer/skripte)
# - heq çdo "code/script" nga teksti; filtron paragrafët e shkurtër/jo-kuptimplotë
# - shkruan: title, category, date, author, cover, source, excerpt (~450 fjalë), content (tekst i pastër me \n\n)

import os, re, json, hashlib, pathlib

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
)

# ---- Paths ----
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

# ---- Env / Defaults ----
MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL = int(os.getenv("MAX_TOTAL", "0"))          # 0 = pa limit total / run
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "450"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")

# ---- anti-script/code cleaner për paragrafë ----
CODE_PATTERNS = [
    r"\bfunction\s*\(", r"\bvar\s+\w+\s*=", r"\blet\s+\w+\s*=", r"\bconst\s+\w+\s*=",
    r"</?\w+[^>]*>", r"[{};<>]{2,}", r"\bconsole\.log\b", r"\$\(", r"document\.querySelector",
    r"<script", r"</script", r"@media", r"window\.", r"import\s+",
]
CODE_RE = re.compile("|".join(CODE_PATTERNS), re.I)


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

    if not FEEDS.exists():
        print("ERROR: feeds.txt not found:", FEEDS)
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

        xml = fetch_bytes(feed_url)
        if not xml:
            continue

        for it in parse_feed(xml):
            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break
            if per_cat.get(category, 0) >= MAX_PER_CAT:
                continue
            title = (it.get("title") or "").strip()
            link = (it.get("link") or "").strip()
            if not title or not link:
                continue
            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            author = "AventurOO Editorial"
            it_elem = it.get("element")
            try:
                a = it_elem.find("author") if it_elem is not None else None
                if a is not None and (a.text or "").strip():
                    author = a.text.strip()
                if not author and it_elem is not None:
                    ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
                    an = it_elem.find("atom:author/atom:name", ns_atom)
                    if an is not None and (an.text or "").strip():
                        author = an.text.strip()
            except Exception:
                author = ""
            if not author:
                author = "AventurOO Editorial"

            text_raw = ""
            lead_image = ""
            description = ""
            if trafilatura is not None:
                try:
                    ext = extract_with_trafilatura(link)
                    text_raw = ext.get("text") or ""
                    lead_image = ext.get("image") or ""
                    description = ext.get("description") or ""
                    if author == "AventurOO Editorial" and ext.get("author"):
                        author = ext["author"].strip()
                except Exception as e:
                    print("trafilatura error:", e)

            if not text_raw:
                try:
                    html = http_get(link)
                    text_raw = strip_text(html)
                except Exception:
                    text_raw = ""

            paragraphs = clean_paragraphs(text_raw)
            content_text = "\n\n".join(paragraphs).strip()

            base_excerpt = content_text if content_text else (description or (it.get("summary") or ""))
            excerpt_text = shorten_words(strip_text(base_excerpt), SUMMARY_WORDS)

            cover = ""
            if not lead_image:
                try:
                    cover = find_cover_from_item(it_elem, link)
                except Exception:
                    cover = ""
            cover = lead_image or cover or FALLBACK_COVER

            date = today_iso()
            slug = slugify(title)[:70]

            entry = {
                "slug": slug,
                "title": title,
                "category": category,
                "date": date,
                "author": author,
                "source": link,
                "cover": cover,
                "excerpt": excerpt_text,
                "content": content_text,
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": category, "created": date}
            per_cat[category] = per_cat.get(category, 0) + 1
            added_total += 1
            print(f"Added [{category}]: {title} (by {author})")

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
