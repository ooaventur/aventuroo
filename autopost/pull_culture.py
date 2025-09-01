#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autopost • Culture → data/posts.json
- Merr artikuj nga feeds culture
- Nxjerr tekst të pastër (jo HTML) dhe krijon excerptExtended (~550 fjalë)
- Ruaj: slug,title,category,date,excerpt,excerptExtended,cover,source,sourceName,author
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

try:
    import trafilatura  # për ekstraktim teksti
except Exception:
    trafilatura = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"

FEEDS = [
    "https://hyperallergic.com/feed/",
    "https://www.smithsonianmag.com/rss/latest_articles/",
]

CATEGORY = "Culture"
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")
MAX_NEW = int(os.getenv("MAX_PER_CAT", "6"))
WORDS_LONG = int(os.getenv("SUMMARY_WORDS", "550"))  # ~450–600

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Fetch error:", url, "->", e)
        return b""

def parse(xml_bytes: bytes):
    if not xml_bytes: return []
    try: root = ET.fromstring(xml_bytes)
    except ET.ParseError: return []
    items=[]
    for it in root.findall(".//item"):
        title=(it.findtext("title") or "").strip()
        link=(it.findtext("link") or "").strip()
        desc=(it.findtext("description") or "").strip()
        author=(it.findtext("{http://purl.org/dc/elements/1.1/}creator") or it.findtext("author") or "").strip()
        if title and link: items.append({"title":title,"link":link,"summary":desc,"author":author,"element":it})
    ns={"atom":"http://www.w3.org/2005/Atom"}
    for e in root.findall(".//atom:entry", ns):
        title=(e.findtext("atom:title", default="") or "").strip()
        linkEl=e.find("atom:link[@rel='alternate']", ns) or e.find("atom:link", ns)
        link=(linkEl.attrib.get("href") if linkEl is not None else "").strip()
        summary=(e.findtext("atom:summary", default="") or e.findtext("atom:content", default="") or "").strip()
        author=(e.findtext("atom:author/atom:name", default="") or "").strip()
        if title and link: items.append({"title":title,"link":link,"summary":summary,"author":author,"element":e})
    return items

def strip_html(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def plain_from_url(url: str) -> str:
    """Kthen tekst të pastër nga faqja (pa HTML)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
    except Exception:
        html=""
    if trafilatura and html:
        try:
            out = trafilatura.extract(html, url=url, include_formatting=False, include_links=False, include_images=False)
            if out: return strip_html(out)
        except Exception:
            pass
    return strip_html(html)

def og_image(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
        m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html, re.I)
        return m.group(1) if m else ""
    except Exception:
        return ""

def find_image_from_item(el, page_url: str) -> str:
    if el is not None:
        enc = el.find("enclosure")
        if enc is not None and str(enc.attrib.get("type","")).startswith("image"):
            u=enc.attrib.get("url",""); 
            if u: return u
        ns={"media":"http://search.yahoo.com/mrss/"}
        m = el.find("media:content", ns) or el.find("media:thumbnail", ns)
        if m is not None and m.attrib.get("url"): return m.attrib.get("url")
    return og_image(page_url) or ""

def slugify(s: str) -> str:
    s=s.lower(); s=re.sub(r"[^a-z0-9]+","-",s); return s.strip("-") or "post"

def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def domain_of(url: str) -> str:
    try: return urlparse(url).netloc.lower()
    except: return ""

def load_json_safe(p: pathlib.Path, default):
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError: return default
    return default

def save_json(p: pathlib.Path, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    DATA_DIR.mkdir(exist_ok=True)
    seen  = load_json_safe(SEEN_DB, {})
    posts = load_json_safe(POSTS_JSON, [])

    added=0
    new=[]

    for feed in FEEDS:
        if added>=MAX_NEW: break
        xml = fetch(feed)
        if not xml: continue
        for it in parse(xml):
            if added>=MAX_NEW: break
            title=(it.get("title") or "").strip()
            link =(it.get("link") or "").strip()
            if not title or not link: continue
            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen: continue

            # tekst i gjatë (preview)
            full_text = plain_from_url(link)
            words = full_text.split()
            long = " ".join(words[:WORDS_LONG]) + ("…" if len(words)>WORDS_LONG else "")
            # excerpt i shkurtër për listime
            short = " ".join(words[:70]) + ("…" if len(words)>70 else "")

            cover = find_image_from_item(it.get("element"), link) or FALLBACK_COVER

            entry = {
                "slug": slugify(title)[:70],
                "title": title,
                "category": CATEGORY,
                "date": today_iso(),
                "excerpt": short,
                "excerptExtended": long,
                "cover": cover,
                "source": link,
                "sourceName": domain_of(link).replace("www.",""),
                "author": it.get("author") or ""
            }
            new.append(entry)
            seen[key] = {"title":title,"url":link,"created":today_iso()}
            added += 1
            print("Added:", title)

    if not new:
        print("New posts: 0"); return

    posts = new + posts
    posts = posts[:200]
    save_json(POSTS_JSON, posts)
    save_json(SEEN_DB, seen)
    print("New posts:", len(new))

if __name__ == "__main__":
    main()
