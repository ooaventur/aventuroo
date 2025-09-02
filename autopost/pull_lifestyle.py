#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AventurOO – Autopost (Lifestyle)
- Lexon vetem rreshtat "Lifestyle|<RSS>" nga autopost/data/feeds.txt
- Nxjerr trupin e artikullit si HTML te paster (paragrafe, bold, linke, imazhe)
- Preferon trafilatura (HTML), pastaj fallback readability-lxml
- Absolutizon URL-t relative te <a> dhe <img>
- Heq script/style/iframes/embed te panevojshem
- Shton linkun e burimit ne fund
- Shkruan ne data/posts.json: {slug,title,category,date,excerpt,cover,source,author,body}
"""

import urllib.request

def fetch_bytes(url: str) -> bytes:
    """Shkarkon të dhënat bruto nga një URL dhe i kthen si bytes."""
    with urllib.request.urlopen(url, timeout=18) as resp:
        return resp.read()

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse, urljoin
from xml.etree import ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL   = int(os.getenv("MAX_TOTAL", "0"))
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "1000"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "18"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")
DEFAULT_AUTHOR = os.getenv("DEFAULT_AUTHOR", "AventurOO Editorial")

try:
    import trafilatura
except Exception:
    trafilatura = None

try:
    from readability import Document
except Exception:
    Document = None

# ... (funksionet e tjera mbeten te pandryshuara) ...

def main():
    DATA_DIR.mkdir(exist_ok=True)

    # seen
    if SEEN_DB.exists():
        try:
            seen = json.loads(SEEN_DB.read_text(encoding="utf-8"))
            if not isinstance(seen, dict): seen = {}
        except json.JSONDecodeError:
            seen = {}
    else:
        seen = {}

    # posts
    if POSTS_JSON.exists():
        try:
            posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
            if not isinstance(posts_idx, list): posts_idx = []
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
        if not raw or raw.startswith("#"): continue
        if "|" not in raw: continue
        cat, url = raw.split("|", 1)
        category = (cat or "").strip().title()
        feed_url = (url or "").strip()
        if category != "Lifestyle" or not feed_url:
            continue

        if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
            break

        xml = fetch_bytes(feed_url)
        if not xml:
            print("Feed empty:", feed_url); continue

        for it in parse_feed(xml):
            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break
            if per_cat.get(category, 0) >= MAX_PER_CAT:
                continue

            title = (it.get("title") or "").strip()
            link  = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # body html
            body_html, inner_img = extract_body_html(link)
            # absolutize & sanitize
            base = f"{urlparse(link).scheme}://{urlparse(link).netloc}"
            body_html = absolutize(body_html, base)
            body_html = sanitize_article_html(body_html)
            # kufizo ~450 fjale si preview
            body_html = limit_words_html(body_html, SUMMARY_WORDS)

            # cover
            cover = find_cover_from_item(it.get("element"), link) or inner_img or FALLBACK_COVER

            # excerpt = paragrafi i pare pa etiketa
            first_p = re.search(r"(?is)<p[^>]*>(.*?)</p>", body_html or "")
            excerpt = strip_text(first_p.group(1)) if first_p else (it.get("summary") or title)
            if len(excerpt) > 280:
                excerpt = excerpt[:277] + "…"

            # footer i burimit
            body_final = (body_html or "") + f"""
<p class="small text-muted mt-4">
  Source: <a href="{link}" target="_blank" rel="nofollow noopener">Read the full article</a>
</p>"""

            date = today_iso()
            slug = slugify(title)[:70]

            entry = {
                "slug": slug,
                "title": title,
                "category": category,
                "date": date,
                "excerpt": excerpt,
                "cover": cover,
                "source": link,
                "author": DEFAULT_AUTHOR,
                "body": body_final
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": category, "created": date}
            per_cat[category] = per_cat.get(category, 0) + 1
            added_total += 1
            print(f"[Lifestyle] + {title}")

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