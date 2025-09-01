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

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

try:
    import trafilatura
except Exception:
    trafilatura = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"

FEEDS_FILE = os.getenv("FEEDS_FILE", "").strip()
CATEGORY = os.getenv("CATEGORY_NAME", "News").strip().title()
SEEN_DB = pathlib.Path(os.getenv("SEEN_DB", str(ROOT / "autopost" / "seen_generic.json")))
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "450"))
MAX_NEW = int(os.getenv("MAX_NEW", "6"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")

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
    # RSS
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "summary": desc, "element": it})
    # Atom
    ns = {"atom":"http://www.w3.org/2005/Atom"}
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
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def find_image_from_item(it_elem, page_url: str = "") -> str:
    if it_elem is not None:
        enc = it_elem.find("enclosure")
        if enc is not None and str(enc.attrib.get("type","")).startswith("image"):
            u = enc.attrib.get("url", "")
            if u: return u
        ns = {"media":"http://search.yahoo.com/mrss/"}
        m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
        if m is not None and m.attrib.get("url"):
            return m.attrib.get("url")
    # og:image
    if page_url:
        try:
            req = urllib.request.Request(page_url, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if m: return m.group(1)
        except Exception:
            pass
    return ""

def summarize_page(url: str, max_words: int) -> str:
    # provojmë me trafilatura (më e pastër), përndryshe fallback i thjeshtë
    if trafilatura is not None:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False, include_tables=False) or ""
                text = strip_html(text)
                words = text.split()
                if len(words) > max_words:
                    text = " ".join(words[:max_words]) + "…"
                return text
        except Exception:
            pass
    # fallback: hiq HTML nga faqja e plotë
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8", "ignore")
    except Exception:
        return ""
    text = strip_html(html)
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
        # prano edhe formatin "Category|URL": por e injorojmë Category sepse kemi CATEGORY nga env
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
        xml = fetch(feed_url)
        for it in parse(xml):
            if added >= MAX_NEW:
                break
            title = (it.get("title") or "").strip()
            link = (it.get("link") or "").strip()
            if not title or not link:
                continue
            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # përmbledhje e pastër
            summary = summarize_page(link, SUMMARY_WORDS)
            if not summary:
                summary = strip_html(it.get("summary","")) or title

            # imazhi kryesor
            cover = ""
            try:
                cover = find_image_from_item(it.get("element"), link)
            except Exception:
                pass
            if not cover:
                cover = FALLBACK_COVER

            entry = {
                "slug": slugify(title)[:70],
                "title": title,
                "category": CATEGORY,
                "date": today_iso(),
                "excerpt": summary,
                "cover": cover,
                "source": link
            }
            new_entries.append(entry)
            seen[key] = {"url": link, "title": title, "created": today_iso(), "category": CATEGORY}
            added += 1
            print(f"[{CATEGORY}] + {title}")

    if not new_entries:
        print("No new entries.")
        return

    posts_idx = new_entries + posts_idx
    if MAX_POSTS_PERSIST > 0:
        posts_idx = posts_idx[:MAX_POSTS_PERSIST]

    POSTS_JSON.write_text(json.dumps(posts_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Added this run: {len(new_entries)}")

if __name__ == "__main__":
    main()
