#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RSS → HTML posts + posts.json for AventurOO (robust, with original images & extended preview)

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from xml.etree import ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "posts"
POSTS_JSON = ROOT / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

# One post per run; schedule it 10x/day in the workflow → ~10/day total
MAX_PER_RUN = 1
HTTP_TIMEOUT = 15  # seconds
UA = "Mozilla/5.0 (AventurOO Autoposter; +https://example.com)"

# Fallback covers (royalty-free from Unsplash)
COVERS = [
  "https://images.unsplash.com/photo-1521292270410-a8c4d716d518?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1531306728370-e2ebd9d7bb99?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1456926631375-92c8ce872def?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=1600&q=60"
]

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Fetch error:", url, "->", e)
        return b""

def parse(xml_bytes: bytes):
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    items = []

    # RSS 2.0 items
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "summary": desc, "element": it})

    # Atom fallback
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for e in root.findall(".//atom:entry", ns):
        title = (e.findtext("atom:title", default="") or "").strip()
        link_el = e.find("atom:link[@rel='alternate']", ns) or e.find("atom:link", ns)
        link = (link_el.attrib.get("href") if link_el is not None else "").strip()
        summary = (e.findtext("atom:summary", default="") or e.findtext("atom:content", default="") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "summary": summary, "element": e})

    return items

def strip_html(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)  # replace any non-alnum with hyphen
    return s.strip("-") or "post"

def date_today() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def find_image_from_item(it_elem, page_url: str = "") -> str:
    # enclosure
    enc = it_elem.find("enclosure")
    if enc is not None and str(enc.attrib.get("type", "")).startswith("image"):
        url = enc.attrib.get("url", "")
        if url:
            return url

    # media:content / media:thumbnail
    ns = {"media": "http://search.yahoo.com/mrss/"}
    m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
    if m is not None and m.attrib.get("url"):
        return m.attrib.get("url")

    # fallback: og:image from article page
    if page_url:
        try:
            req = urllib.request.Request(page_url, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8", "ignore")
            m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html, re.I)
            if m:
                return m.group(1)
        except Exception:
            pass
    return ""

def extract_preview_paragraphs(page_url: str, max_words: int = 300) -> str:
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8", "ignore")
    except Exception:
        return ""
    # crude text extraction (fair-use: short preview not full-copy)
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]) + "…"
    return text

def main():
    POSTS_DIR.mkdir(exist_ok=True)
    seen = json.loads(SEEN_DB.read_text(encoding="utf-8")) if SEEN_DB.exists() else {}
    posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8")) if POSTS_JSON.exists() else []

    created = 0
    cover_i = 0

    if not FEEDS.exists():
        print("No feeds file found")
        return

    for line in FEEDS.read_text(encoding="utf-8").splitlines():
        if created >= MAX_PER_RUN:
            break
        url = line.strip()
        if not url or url.startswith("#"):
            continue

        xml = fetch(url)
        if not xml:
            print("Feed error:", url, "-> empty response")
            continue

        for it in parse(xml):
            if created >= MAX_PER_RUN:
                break

            title = it.get("title", "").strip()
            link  = it.get("link", "").strip()
            it_elem = it.get("element")

            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            summary = strip_html(it.get("summary", ""))

            # try to extend summary with a short preview from the article page
            extended = extract_preview_paragraphs(link, max_words=300)
            if extended:
                summary = extended

            cover = ""
            try:
                if it_elem is not None:
                    cover = find_image_from_item(it_elem, link)
            except Exception:
                cover = ""
            if not cover:
                cover = COVERS[cover_i % len(COVERS)]
                cover_i += 1

            slug = slugify(title)[:70]
            date = date_today()

            html = f"""<!doctype html>
<html lang='en'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{title} | AventurOO</title>
<meta name='description' content='{summary}'>
<script src='https://cdn.tailwindcss.com'></script>
<link rel='stylesheet' href='../assets/styles.css'>
</head><body class='bg-gray-50 text-gray-900'>
<header class='bg-white border-b'><div class='max-w-5xl mx-auto px-4 py-4 flex items-center justify-between'>
<a href='../index.html' class='font-semibold'>AventurOO</a>
<nav class='text-sm flex gap-4'>
<a href='../index.html#hidden-gems' class='hover:underline'>Hidden Gems</a>
<a href='../index.html#cheap-travel' class='hover:underline'>Cheap Travel</a>
<a href='../index.html#luxury-travel' class='hover:underline'>Luxury</a>
</nav></div></header>
<main class='max-w-3xl mx-auto px-4 py-8'>
<article class='prose prose-stone max-w-none'>
<figure class='post-hero'><img src='{cover}' alt='{title} cover'></figure>
<p class='text-xs text-gray-500'>Image source: <a class='underline' href='{link}' target='_blank' rel='nofollow noopener'>{link}</a></p>
<h1>{title}</h1>
<p class='text-sm text-gray-500'>{date} · Aggregated Preview</p>
<p>{summary}</p>
<p class='text-sm text-gray-600'>Source: <a class='underline' href='{link}' rel='nofollow noopener' target='_blank'>{link}</a></p>
<hr/><p class='text-xs text-gray-500'>Short preview & link for reference. © AventurOO.</p>
</article></main>
<footer class='border-t'><div class='max-w-5xl mx-auto px-4 py-6 text-sm text-gray-500'>
<a href='../index.html' class='hover:underline'>← Back to Home</a>
</div></footer></body></html>"""

            out = POSTS_DIR / f"{slug}.html"
            i = 2
            while out.exists():
                out = POSTS_DIR / f"{slug}-{i}.html"
                i += 1
            out.write_text(html, encoding="utf-8")

            entry = {
              "slug": out.stem,
              "title": title,
              "category": "News",
              "date": date,
              "excerpt": summary,
              "cover": cover
            }
            posts_idx = [entry] + posts_idx
            seen[key] = {"title": title, "file": f"posts/{out.name}", "created": date}
            created += 1
            print("Created:", out.name)

    # keep at most last 200 in posts.json
    POSTS_JSON.write_text(json.dumps(posts_idx[:200], ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("New posts:", created)

if __name__ == "__main__":
    main()