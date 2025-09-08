#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# AventurOO - Autopost per kategori (JSON index)
# Lexon nje skedar feed-esh, nxjerr tekst te paster me trafilatura,
# zgjedh imazh nga enclosure/media/og:image, dhe shton ne data/posts.json.
# Përdor variabla mjedisi:
#  FEEDS_FILE      -> p.sh. autopost/data/feeds.travel.txt
#  CATEGORY_NAME   -> p.sh. Travel
#  SEEN_DB         -> p.sh. autopost/seen_travel.json
#  SUMMARY_WORDS   -> p.sh. 450 (default)
#  MAX_NEW         -> sa artikuj maksimal per kete run (default 6)
#  MAX_POSTS_PERSIST -> keep latest N in data/posts.json (default 200)
#  FALLBACK_COVER  -> assets/img/cover-fallback.jpg (default)

import os, re, json, hashlib, pathlib, urllib.request, urllib.error, socket

from autopost.common import (
    fetch_bytes,
    parse_feed,
    strip_text,
    slugify,
    today_iso,
    find_cover_from_item,
    HTTP_TIMEOUT,
    UA,
    trafilatura,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"

FEEDS_FILE = os.getenv("FEEDS_FILE", "").strip()
CATEGORY = os.getenv("CATEGORY_NAME", "News").strip().title()
SEEN_DB = pathlib.Path(os.getenv("SEEN_DB", str(ROOT / "autopost" / "seen_generic.json")))
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "450"))
MAX_NEW = int(os.getenv("MAX_NEW", "6"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")


def summarize_page(url: str, max_words: int) -> str:
    if trafilatura is not None:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False, include_tables=False) or ""
                text = strip_text(text)
                words = text.split()
                if len(words) > max_words:
                    text = " ".join(words[:max_words]) + "…"
                return text
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8", "ignore")
    except Exception:
        return ""
    text = strip_text(html)
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]) + "…"
    return text


def load_json_safe(path: pathlib.Path, default):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return data


def main():
    if not FEEDS_FILE:
        print("ERROR: FEEDS_FILE environment variable is missing.")
        return
    DATA_DIR.mkdir(exist_ok=True)
    SEEN_DB.parent.mkdir(parents=True, exist_ok=True)
    if not SEEN_DB.exists():
        SEEN_DB.write_text("{}", encoding="utf-8")

    seen = load_json_safe(SEEN_DB, {})
    posts_idx = load_json_safe(POSTS_JSON, [])

    feeds = []
    for line in pathlib.Path(FEEDS_FILE).read_text(encoding="utf-8").splitlines():
        u = line.strip()
        if not u or u.startswith("#"):
            continue
        if "|" in u:
            _, url = u.split("|", 1)
            feeds.append(url.strip())
        else:
            feeds.append(u)

    added = 0
    new_entries = []

    for feed_url in feeds:
        if added >= MAX_NEW:
            break
        xml = fetch_bytes(feed_url)
        for it in parse_feed(xml):
            if added >= MAX_NEW:
                break
            title = (it.get("title") or "").strip()
            link = (it.get("link") or "").strip()
            if not title or not link:
                continue
            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            summary = summarize_page(link, SUMMARY_WORDS)
            if not summary:
                summary = strip_text(it.get("summary", "")) or title

            cover = ""
            try:
                cover = find_cover_from_item(it.get("element"), link)
            except Exception:
                pass
            if not cover:
                cover = FALLBACK_COVER

            date = today_iso()
            slug = slugify(title)[:70]

            entry = {
                "slug": slug,
                "title": title,
                "category": CATEGORY,
                "date": date,
                "excerpt": summary,
                "cover": cover,
                "source": link,
                "author": "AventurOO Editorial",
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": CATEGORY, "created": date}
            added += 1
            print(f"Added [{CATEGORY}]: {title}")

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
