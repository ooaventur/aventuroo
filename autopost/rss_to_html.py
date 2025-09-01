#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RSS → data/posts.json (AventurOO)
# - lexon feeds.txt (format: kategori|URL)
# - përmbledhje e sigurt ~450 fjalë (ndryshohet me env SUMMARY_WORDS)
# - imazhi kryesor nga enclosure/media/og:image ose fallback
# - load/save e sigurt për seen.json dhe data/posts.json

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# ---- Paths ----
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

# ---- Env / Defaults ----
MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))          # maksimalisht artikuj të rinj për kategori / run
MAX_TOTAL = int(os.getenv("MAX_TOTAL", "0"))              # 0 = pa limit total për run
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "450"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")

# ---- Helpers ----
def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Fetch error:", url, "->", e)
        return b""

def parse(xml_bytes: bytes):
    """Kthen listë items me {title, link, summary, element} nga RSS/Atom."""
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    items = []
    # RSS 2.0
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "summary": desc, "element": it})
    # Atom
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

def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def find_image_from_item(it_elem, page_url: str = "") -> str:
    """Kërkon imazh nga <enclosure>, <media:content>/<media:thumbnail>, ose nga faqja (og:image)."""
    if it_elem is not None:
        enc = it_elem.find("enclosure")
        if enc is not None and str(enc.attrib.get("type", "")).startswith("image"):
            u = enc.attrib.get("url", "")
            if u: return u
        ns = {"media": "http://search.yahoo.com/mrss/"}
        m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
        if m is not None and m.attrib.get("url"):
            return m.attrib.get("url")

    # og:image
    if page_url:
        try:
            req = urllib.request.Request(page_url, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
            m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html, re.I)
            if m: return m.group(1)
        except Exception:
            pass
    return ""

def extract_preview(page_url: str, max_words: int) -> str:
    """Shkarkon faqen dhe krijon tekst të pastër të shkurtuar në ~max_words fjalë."""
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8", "ignore")
    except Exception:
        return ""
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = strip_html(text)
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]) + "…"
    return text

# ----------------- MAIN -----------------
def main():
    DATA_DIR.mkdir(exist_ok=True)

    # Load seen database (SAFE)
    if SEEN_DB.exists():
        try:
            seen = json.loads(SEEN_DB.read_text(encoding="utf-8"))
            if not isinstance(seen, dict):
                seen = {}
        except json.JSONDecodeError:
            seen = {}
    else:
        seen = {}

    # Load posts index (SAFE)
    if POSTS_JSON.exists():
        try:
            posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
            if not isinstance(posts_idx, list):
                posts_idx = []
        except json.JSONDecodeError:
            posts_idx = []
    else:
        posts_idx = []

    # Lexo feeds.txt (format: kategori|URL)
    if not FEEDS.exists():
        print("ERROR: feeds.txt NOT FOUND at", FEEDS)
        return

    added_total = 0
    per_cat_counter = {}      # {category: count}
    new_entries = []

    for raw in FEEDS.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        if "|" in raw:
            cat, url = raw.split("|", 1)
            category = (cat or "News").strip().title()
            feed_url = url.strip()
        else:
            category = "News"
            feed_url = raw

        if not feed_url:
            continue

        if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
            break

        xml = fetch(feed_url)
        if not xml:
            print("Feed empty:", feed_url)
            continue

        items = parse(xml)
        if not items:
            print("No items in feed:", feed_url)
            continue

        for it in items:
            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break

            ncat = per_cat_counter.get(category, 0)
            if ncat >= MAX_PER_CAT:
                continue

            title = (it.get("title") or "").strip()
            link = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            preview = extract_preview(link, SUMMARY_WORDS)
            summary = preview or strip_html(it.get("summary", "")) or title

            cover = ""
            try:
                cover = find_image_from_item(it.get("element"), link)
            except Exception:
                cover = ""
            if not cover:
                cover = FALLBACK_COVER

            date = today_iso()
            slug = slugify(title)[:70]

            entry = {
                "slug": slug,
                "title": title,
                "category": category,
                "date": date,
                "excerpt": summary,
                "cover": cover
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": category, "created": date}
            per_cat_counter[category] = per_cat_counter.get(category, 0) + 1
            added_total += 1

            print(f"Added [{category}]: {title}")

    if not new_entries:
        print("New posts this run: 0")
        return

    posts_idx = new_entries + posts_idx
    if MAX_POSTS_PERSIST > 0:
        posts_idx = posts_idx[:MAX_POSTS_PERSIST]

    POSTS_JSON.write_text(json.dumps(posts_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")

    print("New posts this run:", len(new_entries))

if __name__ == "__main__":
    main()