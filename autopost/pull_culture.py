#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pull_culture.py — AventurOO
#
# Qëllimi: Tërheq artikuj "Culture" nga RSS/Atom, nxjerr HTML të pastër (me formatim),
# krijon excerpt, dhe e shton në data/posts.json për t'u lexuar nga article.html.

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse, urljoin
from xml.etree import ElementTree as ET

# deps runtime (trafilatura, lxml)
import trafilatura
from lxml import html, etree

# ------------- Paths / Env -------------
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS_FILE = ROOT / "autopost" / "data" / "feeds_culture.txt"  # opsional

CATEGORY = os.getenv("CATEGORY", "Culture").title()

SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "700"))
MAX_PER_CAT   = int(os.getenv("MAX_PER_CAT", "6"))
HTTP_TIMEOUT  = int(os.getenv("HTTP_TIMEOUT", "15"))
UA            = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))

DEFAULT_FEEDS = [
    # Smithsonian — Culture/Art
    "https://www.smithsonianmag.com/rss/latest_articles/",
    # Hyperallergic — Art & Culture
    "https://hyperallergic.com/feed/",
]

# ------------- Net utils -------------
def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Fetch error:", url, "->", e)
        return b""

def fetch_text(url: str) -> str:
    b = fetch(url)
    if not b:
        return ""
    try:
        return b.decode("utf-8", "ignore")
    except Exception:
        return ""

# ------------- RSS/Atom parsing -------------
def parse_feed(xml_bytes: bytes):
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
        link  = (it.findtext("link") or "").strip()
        desc  = (it.findtext("description") or "").strip()
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

# ------------- Helpers -------------
def strip_html(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def words_excerpt(text: str, max_words: int) -> str:
    text = strip_html(text)
    ws = text.split()
    if len(ws) > max_words:
        return " ".join(ws[:max_words]) + "…"
    return text

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def find_image_from_item(it_elem, page_url: str = "") -> str:
    if it_elem is not None:
        enc = it_elem.find("enclosure")
        if enc is not None and str(enc.attrib.get("type", "")).startswith("image"):
            u = enc.attrib.get("url", "")
            if u: return u
        ns = {"media": "http://search.yahoo.com/mrss/"}
        m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
        if m is not None and m.attrib.get("url"):
            return m.attrib.get("url")
    # og:image fallback
    if page_url:
        html_txt = fetch_text(page_url)
        if html_txt:
            m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html_txt, re.I)
            if m: return m.group(1)
    return ""

def find_meta_author(page_html: str) -> str:
    # meta name=author, article:author, etc.
    for pat in [
        r'<meta[^>]+name=[\'"]author[\'"][^>]+content=[\'"]([^\'"]+)[\'"]',
        r'<meta[^>]+property=[\'"]article:author[\'"][^>]+content=[\'"]([^\'"]+)[\'"]',
        r'<a[^>]+rel=[\'"]author[\'"][^>]*>(.*?)</a>'
    ]:
        m = re.search(pat, page_html, re.I|re.S)
        if m:
            return strip_html(m.group(1))
    return ""

# ------------- Sanitizer (SAFE UNWRAP) -------------
def sanitize_and_normalize_html(raw_html: str, base_url: str) -> str:
    """
    Ruaj p/ul/ol/li/h2/h3/b/strong/em/i/a/img/blockquote/br
    Hiq skript/style/iframes, atributet me 'on*', bëj URL-të absolute.
    """
    if not raw_html:
        return ""

    doc = html.fromstring(raw_html)

    # 1) remove dangerous
    for xp in [
        "//script", "//style", "//noscript", "//iframe", "//form",
        "//object", "//embed", "//canvas", "//svg", "//video", "//audio"
    ]:
        for el in doc.xpath(xp):
            try:
                el.drop_tree()
            except Exception:
                pass

    # 2) allowlist
    allowed = set("p ul ol li h2 h3 strong b em i a img blockquote br".split())
    for el in list(doc.iter()):
        tag = el.tag if isinstance(el.tag, str) else None
        if not tag:
            continue
        if tag not in allowed:
            parent = el.getparent()
            if parent is None:
                try:
                    el.drop_tree()
                except Exception:
                    pass
            else:
                idx = parent.index(el)
                # move children up
                for child in list(el):
                    el.remove(child)
                    parent.insert(idx, child)
                    idx += 1
                # keep text
                if el.text:
                    span = html.Element("span")
                    span.text = el.text
                    parent.insert(idx, span)
                    idx += 1
                # transfer tail
                if el.tail:
                    nxt = el.getnext()
                    if nxt is not None:
                        nxt.tail = (nxt.tail or "") + el.tail
                    else:
                        parent.text = (parent.text or "") + el.tail
                try:
                    parent.remove(el)
                except Exception:
                    try:
                        el.drop_tree()
                    except Exception:
                        pass

    # 3) normalize attributes
    for a in doc.xpath("//a"):
        href = (a.get("href") or "").strip()
        if href:
            a.set("href", urljoin(base_url, href))
            a.set("rel", "noopener nofollow")
            a.set("target", "_blank")
        for att in list(a.attrib):
            if att.lower().startswith("on"):
                del a.attrib[att]

    for img in doc.xpath("//img"):
        src = (img.get("src") or "").strip()
        if src:
            img.set("src", urljoin(base_url, src))
        for att in list(img.attrib):
            if att.lower().startswith("on"):
                del img.attrib[att]
        # hiq atributet e rënda
        for att in ["srcset", "sizes", "loading", "decoding", "width", "height"]:
            if att in img.attrib:
                del img.attrib[att]

    # 4) innerHTML e body/root
    body = doc
    if doc.tag.lower() != "body":
        b = doc.xpath("//body")
        if b:
            body = b[0]

    parts = []
    for node in body:
        parts.append(etree.tostring(node, encoding="unicode", method="html"))
    cleaned_html = "".join(parts)
    cleaned_html = re.sub(r"\n{3,}", "\n\n", cleaned_html).strip()
    return cleaned_html

# ------------- Extractors -------------
def build_body_html(url: str) -> tuple[str, str]:
    """
    Kthen (body_html, author).
    Përdor trafilatura për HTML me paragrafë/formatim; sanitize + normalizim.
    """
    downloaded = trafilatura.fetch_url(
    url,
    config=TRAFI_CFG,   # KALON UA përmes config-ut
    no_ssl=True,
    timeout=HTTP_TIMEOUT
)
    if not downloaded:
        return "", ""

    # përpiqu të marrësh edhe HTML-in e plotë për meta author në fallback
    full_html = downloaded if downloaded else fetch_text(url)

    # prefero HTML (jo vetëm tekst)
    h = trafilatura.extract(downloaded, output="xml", include_links=True, include_images=True)  # XHTML-like
    if not h:
        # fallback: plain text në p paragrafe
        txt = trafilatura.extract(downloaded, output="txt")
        if not txt:
            return "", find_meta_author(full_html or "")
        paras = [f"<p>{html.escape(p.strip())}</p>" for p in re.split(r"\n{2,}", txt) if p.strip()]
        body = "\n".join(paras)
    else:
        # 'h' është XHTML; sanitize
        body = sanitize_and_normalize_html(h, url)

    author = find_meta_author(full_html or "")
    return body, author

def build_excerpt(body_html: str, fallback_summary: str) -> str:
    if body_html:
        # hiq tag-et për excerpt
        return words_excerpt(body_html, SUMMARY_WORDS)
    return words_excerpt(fallback_summary, SUMMARY_WORDS)

# ------------- Main -------------
def read_json_safe(path: pathlib.Path, default):
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, type(default)) else default
        except json.JSONDecodeError:
            return default
    return default

def load_feeds() -> list[str]:
    if FEEDS_FILE.exists():
        urls = []
        for line in FEEDS_FILE.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"): 
                continue
            if "|" in s:
                _, u = s.split("|", 1)
                urls.append(u.strip())
            else:
                urls.append(s)
        return urls or DEFAULT_FEEDS
    return DEFAULT_FEEDS

def main():
    DATA_DIR.mkdir(exist_ok=True)
    (ROOT / "autopost").mkdir(exist_ok=True)

    posts = read_json_safe(POSTS_JSON, [])
    seen  = read_json_safe(SEEN_DB, {})

    feeds = load_feeds()
    added = 0
    new_entries = []

    for f in feeds:
        if added >= MAX_PER_CAT:
            break
        feed_xml = fetch(f)
        items = parse_feed(feed_xml)
        if not items:
            print("No items:", f)
            continue

        for it in items:
            if added >= MAX_PER_CAT:
                break

            title = (it.get("title") or "").strip()
            link  = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # Body + Author
            body_html, author = build_body_html(link)

            # Excerpt (nga body ose summary)
            fallback_sum = it.get("summary", "")
            excerpt = build_excerpt(body_html, fallback_sum)

            # Cover
            cover = find_image_from_item(it.get("element"), link) or FALLBACK_COVER

            date = today_iso()
            slug = slugify(title)[:70]

            attribution_html = f"""<div class="small text-muted mt-4">
Source: <a href="{link}" rel="nofollow noopener" target="_blank">{urlparse(link).netloc}</a>.
All rights belong to the original publisher. This is a preview with attribution.
</div>"""

            entry = {
                "slug": slug,
                "title": title,
                "category": CATEGORY,
                "date": date,
                "excerpt": excerpt,
                "cover": cover,
                "author": author or "AventurOO Editorial",
                "source": link,
                "body": body_html,                  # KY perdoret nga article.html
                "attribution_html": attribution_html
            }

            new_entries.append(entry)
            seen[key] = {"title": title, "url": link, "created": date, "category": CATEGORY}
            added += 1
            print(f"Added [{CATEGORY}]: {title}")

    if not new_entries:
        print("New posts this run: 0")
        return

    # prepend të rejat
    posts = new_entries + posts
    if MAX_POSTS_PERSIST > 0:
        posts = posts[:MAX_POSTS_PERSIST]

    POSTS_JSON.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("New posts this run:", len(new_entries))

if __name__ == "__main__":
    main()
