#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AventurOO – Autopost (Culture only)
- Lexon autopost/data/feeds.txt dhe merr vetem rreshtat me kategori "Culture"
- Shkarkon artikujt me trafilatura (output HTML te pastruar)
- Ndan ne paragrafë; nuk përdor "lorem ipsum"
- Respekton limit fjalësh (SUMMARY_WORDS) duke ruajtur paragrafët origjinalë
- Gjen imazhin kryesor (enclosure/media/og:image ose i pari <img> nga HTML)
- Shton link te burimi ne fund ("Read the full article")
- Shkruan ne data/posts.json, me fusha: slug, title, category, date, excerpt, cover, source, author, body (HTML)
- Ruajtur/lexuar seen.json ne menyre te sigurt
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# ---- Konfigurime & Path-e ----
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

# Env
MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL   = int(os.getenv("MAX_TOTAL", "0"))          # 0 = pa limit
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "450"))  # rreth 450 fjalë
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")
DEFAULT_AUTHOR = os.getenv("DEFAULT_AUTHOR", "AventurOO Editorial")

# Trafilatura (opsionale por e rekomanduar)
try:
    import trafilatura  # noqa
except Exception:
    trafilatura = None

# ---- Helpers ----
def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Fetch error:", url, "->", e)
        return b""

def strip_html(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_feed(xml_bytes: bytes):
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

def find_cover_from_item(it_elem, page_url: str = "") -> str:
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

def summarize_html(url: str, max_words: int):
    """
    Merr HTML të pastruar nga trafilatura dhe kthen:
    - summary_html: paragrafë <p>…</p> deri ~max_words
    - first_img: i pari <img> … në përmbajtjen e pastër (për cover fallback)
    """
    summary_html, first_img = "", ""

    if trafilatura is not None:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                clean_html = trafilatura.extract(
                    downloaded,
                    output_format="html",
                    include_links=True,
                    include_images=True,
                    include_formatting=True
                )
                if clean_html:
                    # gjej të parin <img> si kandidat cover
                    mimg = re.search(r'<img[^>]+src=["\'](http[^"\']+)["\']', clean_html, flags=re.I)
                    if mimg:
                        first_img = mimg.group(1)

                    # mblidh paragrafët pa prishur HTML-në
                    parts = re.findall(r"(?is)<p[^>]*>.*?</p>", clean_html)
                    out = []
                    wc = 0
                    for phtml in parts:
                        text = strip_html(phtml)
                        w = len(text.split())
                        if wc + w > max_words:
                            break
                        out.append(phtml)
                        wc += w
                    summary_html = "\n".join(out)
        except Exception as e:
            print("Trafilatura HTML error:", e)

    # fallback: tekst i thjeshtë
    if not summary_html:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
        except Exception:
            return "", ""
        text = strip_html(html)
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]) + "…"
        summary_html = f"<p>{text}</p>"

    return summary_html, first_img

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

# ---- MAIN ----
def main():
    # seen.json (safe)
    if SEEN_DB.exists():
        try:
            seen = json.loads(SEEN_DB.read_text(encoding="utf-8"))
            if not isinstance(seen, dict): seen = {}
        except json.JSONDecodeError:
            seen = {}
    else:
        seen = {}

    # data/posts.json (safe)
    if POSTS_JSON.exists():
        try:
            posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
            if not isinstance(posts_idx, list): posts_idx = []
        except json.JSONDecodeError:
            posts_idx = []
    else:
        posts_idx = []

    if not FEEDS.exists():
        print("ERROR: feeds.txt NOT FOUND:", FEEDS)
        return

    added_total = 0
    per_cat_counter = {}
    new_entries = []

    # lexon vetem rreshtat me kategori "Culture"
    for raw in FEEDS.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"): continue

        if "|" in raw:
            cat, url = raw.split("|", 1)
            category = (cat or "").strip().title()
            feed_url = (url or "").strip()
        else:
            # nese mungon, e injorojme (ky workflow eshte vetem per Culture)
            continue

        if category != "Culture":
            # ky script merret vetem me Culture
            continue
        if not feed_url:
            continue

        if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
            break

        xml = fetch(feed_url)
        if not xml:
            print("Feed empty:", feed_url)
            continue

        items = parse_feed(xml)
        if not items:
            print("No items in feed:", feed_url)
            continue

        for it in items:
            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break

            if per_cat_counter.get(category, 0) >= MAX_PER_CAT:
                continue

            title = (it.get("title") or "").strip()
            link  = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # përmbajtje + imazh i mundshëm nga html i pastër
            body_html, inner_img = summarize_html(link, SUMMARY_WORDS)

            # cover: enclosure/media/og:image → pastaj i pari <img> nga body → fallback
            cover = find_cover_from_item(it.get("element"), link)
            if not cover and inner_img:
                cover = inner_img
            if not cover:
                cover = FALLBACK_COVER

            # excerpt = paragrafi i parë i trupit (pa etiketa)
            excerpt = strip_html(re.sub(r"(?is)<[^>]+>", " ", body_html)).split(". ")
            excerpt = (excerpt[0] if excerpt else title)
            if len(excerpt) > 280:  # mos e bej shume te gjate
                excerpt = excerpt[:277] + "…"

            date = today_iso()
            slug = slugify(title)[:70]

            # shto linkun e burimit ne fund
            body_final = body_html + f"""
<p class="small text-muted mt-4">
  Source: <a href="{link}" target="_blank" rel="nofollow noopener">Read the full article at Smithsonian Magazine</a>
</p>
"""

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
            per_cat_counter[category] = per_cat_counter.get(category, 0) + 1
            added_total += 1

            print(f"Added [Culture]: {title}")

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
