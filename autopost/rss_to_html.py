#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# AventurOO Autopost → data/posts.json
# Modeli: përmbledhje (~450 fjalë) + imazh kryesor nga FEED (ose og:image) + fallback vendor
# - lexon feeds "category|URL"
# - deduplikon me seen.json
# - datë nga pubDate/updated (fallback sot, format YYYY-MM-DD)
# - ruan uniformitetin me sajtin: slug, title, category, date, excerpt, cover (+ source, original)

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket, email.utils
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# --- paths ---
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

# --- env-config ---
HTTP_TIMEOUT      = int(os.environ.get("HTTP_TIMEOUT", "15"))
UA                = os.environ.get("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
MAX_PER_CAT       = int(os.environ.get("MAX_PER_CAT", "8"))       # max artikuj të rinj / kategori / run
MAX_TOTAL         = int(os.environ.get("MAX_TOTAL", "0"))         # 0 = pa limit global
SUMMARY_WORDS     = int(os.environ.get("SUMMARY_WORDS", "450"))   # ~450 fjalë
MAX_POSTS_PERSIST = int(os.environ.get("MAX_POSTS_PERSIST", "200"))
FALLBACK_COVER    = os.environ.get("FALLBACK_COVER", "assets/img/cover-fallback.jpg")

# ---------- helpers ----------
def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Fetch error:", url, "->", e)
        return b""

def fetch_text(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        return urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
    except Exception:
        return ""

def parse_feed(xml_bytes: bytes):
    if not xml_bytes: return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    items = []
    # RSS 2.0
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link  = (it.findtext("link") or "").strip()
        if not title or not link: 
            continue
        items.append({
            "title": title,
            "link": link,
            "summary": (it.findtext("description") or "").strip(),
            "pub": (it.findtext("pubDate") or "").strip(),
            "element": it
        })
    # Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for e in root.findall(".//atom:entry", ns):
        title  = (e.findtext("atom:title", default="") or "").strip()
        linkEl = e.find("atom:link[@rel='alternate']", ns) or e.find("atom:link", ns)
        link   = (linkEl.attrib.get("href") if linkEl is not None else "").strip()
        if not title or not link:
            continue
        items.append({
            "title": title,
            "link": link,
            "summary": (e.findtext("atom:summary", default="") or e.findtext("atom:content", default="") or "").strip(),
            "pub": (e.findtext("atom:updated", default="") or e.findtext("atom:published", default="")).strip(),
            "element": e
        })
    # Rendit sipas dates nëse mundemi (të rejat në krye)
    def _dt(x):
        return parsed_pubdate(x.get("pub","")) or datetime.datetime.min.replace(tzinfo=None)
    items.sort(key=_dt, reverse=True)
    return items

def strip_html(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def summarize_from_page(html: str, words: int) -> str:
    if not html: return ""
    m = re.search(r"(?is)<article[^>]*>(.*?)</article>", html) or re.search(r"(?is)<main[^>]*>(.*?)</main>", html)
    chunk = m.group(1) if m else html
    text = strip_html(chunk)
    toks = text.split()
    if len(toks) <= words:
        return text
    return " ".join(toks[:words]) + "…"

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def iso_today() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.lower()
        return d.replace("www.", "")
    except:
        return ""

def parsed_pubdate(s: str):
    """Kthen datetime naive (UTC) nga pubDate/updated ose None."""
    if not s: return None
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt is None: return None
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        # prova e dytë: ISO-8601 e thjeshtë
        try:
            dt = datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return None

# --- imazhi kryesor: nga FEED → og:image → fallback ---
def pick_feed_image(it_elem) -> str:
    ns = {"media": "http://search.yahoo.com/mrss/"}
    m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
    if m is not None and m.attrib.get("url"):
        return m.attrib.get("url")
    enc = it_elem.find("enclosure")
    if enc is not None and str(enc.attrib.get("type","")).startswith("image"):
        u = enc.attrib.get("url")
        if u: return u
    return ""

def og_image(html: str) -> str:
    if not html: return ""
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    return m.group(1) if m else ""

# ---------- main ----------
def main():
    seen  = json.loads(SEEN_DB.read_text(encoding="utf-8")) if SEEN_DB.exists() else {}
    posts = json.loads(POSTS_JSON.read_text(encoding="utf-8")) if POSTS_JSON.exists() else []

    if not FEEDS.exists():
        print("No feeds file:", FEEDS)
        return

    # leximi i feeds.txt: "category|URL"
    lines = [l.strip() for l in FEEDS.read_text(encoding="utf-8").splitlines()]
    feeds_by_cat = {}
    for line in lines:
        if not line or line.startswith("#"): 
            continue
        if "|" in line:
            cat, url = [p.strip() for p in line.split("|", 1)]
        else:
            cat, url = "Travel", line
        if not url: 
            continue
        feeds_by_cat.setdefault(cat.lower(), []).append(url)

    total_added = 0

    for cat, urls in feeds_by_cat.items():
        added_this_cat = 0
        for url in urls:
            if (MAX_TOTAL and total_added >= MAX_TOTAL) or added_this_cat >= MAX_PER_CAT:
                break

            xml = fetch(url)
            if not xml:
                print("Feed error:", url, "-> empty")
                continue

            for it in parse_feed(xml):
                if (MAX_TOTAL and total_added >= MAX_TOTAL) or added_this_cat >= MAX_PER_CAT:
                    break

                title = it["title"].strip()
                link  = it["link"].strip()
                if not title or not link:
                    continue

                key = hashlib.sha1(link.encode("utf-8")).hexdigest()
                if key in seen:
                    continue

                # përmbledhje (~450 fjalë): nga faqa; nëse jo, nga feed
                page_html = fetch_text(link)
                summary = summarize_from_page(page_html, SUMMARY_WORDS) or strip_html(it.get("summary",""))
                if len(summary.split()) < 40:
                    s2 = strip_html(it.get("summary",""))
                    if len(s2) > len(summary): 
                        summary = s2
                if len(summary) > 1200:
                    summary = " ".join(summary.split()[:SUMMARY_WORDS]) + "…"

                # imazh
                cover = ""
                try:
                    elem = it.get("element")
                    if elem is not None:
                        cover = pick_feed_image(elem)
                except Exception:
                    pass
                if not cover:
                    og = og_image(page_html)
                    if og: cover = og
                if not cover:
                    cover = FALLBACK_COVER

                # datë
                dt = parsed_pubdate(it.get("pub",""))
                date_str = (dt or datetime.datetime.utcnow()).strftime("%Y-%m-%d")

                # JSON entry uniform
                base = slugify(title)[:70] or "post"
                slug = base if not any(p.get("slug")==base for p in posts) else f"{base}-{key[:6]}"

                entry = {
                    "slug": slug,
                    "title": title,
                    "category": cat.capitalize(),
                    "date": date_str,
                    "excerpt": summary,
                    "cover": cover,
                    "source": domain(link),   # opsionale për UI
                    "original": link
                }

                posts = [entry] + posts
                seen[key] = {"title": title, "created": iso_today(), "category": cat}
                added_this_cat += 1
                total_added += 1
                print(f"Added [{cat}]: {title}")

    POSTS_JSON.write_text(json.dumps(posts[:MAX_POSTS_PERSIST], ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"New posts this run: {total_added}")

if __name__ == "__main__":
    main()