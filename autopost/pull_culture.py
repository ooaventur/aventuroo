#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AventurOO – Autopost (Culture)
- Lexon vetëm rreshtat "Culture|<RSS>" nga autopost/data/feeds.txt
- Nxjerr trupin e artikullit si HTML të pastër (paragrafe, bold, links, img)
- Preferon trafilatura (HTML), pastaj fallback readability-lxml
- Absolutizon URL-t relative te <a> dhe <img>
- Heq script/style/iframes/embed të panevojshëm
- Shton linkun e burimit në fund
- Shkruan në data/posts.json: {slug,title,category,date,excerpt,cover,source,author,bodyHtml}
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse, urljoin
from xml.etree import ElementTree as ET

# ---------------- Paths & const ----------------
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

CATEGORY = os.getenv("CATEGORY", "Culture").title()

MAX_PER_CAT       = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL         = int(os.getenv("MAX_TOTAL",   "0"))   # 0 = pa limit
SUMMARY_WORDS     = int(os.getenv("SUMMARY_WORDS","1000"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST","400"))
HTTP_TIMEOUT      = int(os.getenv("HTTP_TIMEOUT","18"))
UA                = os.getenv("AP_USER_AGENT","Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER    = os.getenv("FALLBACK_COVER","assets/img/cover-fallback.jpg")

# ---------------- Optional deps ----------------
try:
    import trafilatura
except Exception:
    trafilatura = None

try:
    from readability import Document
except Exception:
    Document = None

# ---------------- Helpers ----------------
def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        raw = r.read()
    for enc in ("utf-8", "utf-16", "iso-8859-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")

def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Fetch error:", url, "->", e)
        return b""

def strip_text(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""

def parse_feed(xml_bytes: bytes):
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
        link  = (it.findtext("link") or "").strip()
        desc  = (it.findtext("description") or "").strip()
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

def find_cover_from_item(it_elem, page_url: str = "") -> str:
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
            html = http_get(page_url)
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if m: return m.group(1)
        except Exception:
            pass
    return ""

def absolutize(html: str, base: str) -> str:
    def rep_href(m):
        url = m.group(1)
        if url.startswith(("http","mailto:","#")):
            return f'href="{url}"'
        return f'href="{urljoin(base, url)}"'
    def rep_src(m):
        url = m.group(1)
        if url.startswith(("http","data:")):
            return f'src="{url}"'
        return f'src="{urljoin(base, url)}"'
    html = re.sub(r'href=["\']([^"\']+)["\']', rep_href, html, flags=re.I)
    html = re.sub(r'src=["\']([^"\']+)["\']',  rep_src,  html, flags=re.I)
    return html

def sanitize_article_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"(?is)<script.*?</script>", "", html)
    html = re.sub(r"(?is)<style.*?</style>",  "", html)
    html = re.sub(r"(?is)<noscript.*?</noscript>", "", html)
    html = re.sub(r"(?is)<iframe.*?</iframe>", "", html)
    # heq disa “aside/figure” promocionale tipike
    html = re.sub(r'(?is)<(aside|figure)[^>]*class="[^"]*(share|related|promo|newsletter)[^"]*"[^>]*>.*?</\1>', "", html)
    return html.strip()

def limit_words_html(html: str, max_words: int) -> str:
    text = strip_text(html)
    words = text.split()
    if len(words) <= max_words:
        return html
    parts = re.findall(r"(?is)<p[^>]*>.*?</p>|<h2[^>]*>.*?</h2>|<h3[^>]*>.*?</h3>|<ul[^>]*>.*?</ul>|<ol[^>]*>.*?</ol>|<blockquote[^>]*>.*?</blockquote>", html)
    out, count = [], 0
    for block in parts:
        w = len(strip_text(block).split())
        if count + w > max_words:
            break
        out.append(block)
        count += w
    if not out:
        trimmed = " ".join(words[:max_words]) + "…"
        return f"<p>{trimmed}</p>"
    return "\n".join(out)

def extract_body_html(url: str) -> tuple[str,str]:
    body_html = ""
    first_img = ""
    # 1) trafilatura → HTML
    if trafilatura is not None:
        try:
            downloaded = trafilatura.fetch_url(url)  # pa user_agent param
            if downloaded:
                th = trafilatura.extract(
                    downloaded, output_format="html",
                    include_images=True, include_links=True, include_formatting=True
                )
                if th:
                    body_html = th
                    m = re.search(r'<img[^>]+src=["\'](http[^"\']+)["\']', th, flags=re.I)
                    if m: first_img = m.group(1)
        except Exception as e:
            print("trafilatura error:", e)
    # 2) readability-lxml
    if not body_html and Document is not None:
        try:
            raw = http_get(url)
            doc = Document(raw)
            body_html = doc.summary(html_partial=True)
            if body_html and not first_img:
                m = re.search(r'<img[^>]+src=["\'](http[^"\']+)["\']', body_html, flags=re.I)
                if m: first_img = m.group(1)
        except Exception as e:
            print("readability error:", e)
    # 3) fallback i fundit – tekst i plotë i pastruar
    if not body_html:
        try:
            raw = http_get(url)
            txt = strip_text(raw)
            return f"<p>{txt}</p>", ""
        except Exception:
            return "", ""
    return body_html, first_img

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

# ---------------- Main ----------------
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
        if not raw or raw.startswith("#"):
            continue
        if "|" not in raw:
            continue
        cat, url = raw.split("|", 1)
        category = (cat or "").strip().title()
        feed_url = (url or "").strip()

        if category != CATEGORY or not feed_url:
            continue
        if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
            break

        xml = fetch_bytes(feed_url)
        if not xml:
            print("Feed empty:", feed_url)
            continue

        for it in parse_feed(xml):
            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break
            if per_cat.get(category, 0) >= MAX_PER_CAT:
                continue

            title = (it.get("title") or "").strip()
            link  = (it.get("link")  or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # body
            body_html, inner_img = extract_body_html(link)
            base = f"{urlparse(link).scheme}://{urlparse(link).netloc}"
            body_html = absolutize(body_html, base)
            body_html = sanitize_article_html(body_html)
            body_html = limit_words_html(body_html, SUMMARY_WORDS)

            # cover
            cover = find_cover_from_item(it.get("element"), link) or inner_img or FALLBACK_COVER

            # excerpt (paragrafin e parë)
            first_p = re.search(r"(?is)<p[^>]*>(.*?)</p>", body_html or "")
            excerpt = strip_text(first_p.group(1)) if first_p else (it.get("summary") or title)
            if len(excerpt) > 280:
                excerpt = excerpt[:277] + "…"

            # autor nga feed (dc:creator / author)
            author = ""
            elem = it.get("element")
            try:
                ns_dc = {"dc":"http://purl.org/dc/elements/1.1/"}
                if elem is not None:
                    dc = elem.find("dc:creator", ns_dc)
                    if dc is not None and (dc.text or "").strip():
                        author = dc.text.strip()
                    if not author:
                        a = elem.find("author")
                        if a is not None and (a.text or "").strip():
                            author = a.text.strip()
            except Exception:
                pass
            if not author:
                author = "AventurOO Editorial"

            # footer i burimit
            body_final = (body_html or "") + f"""
<p class="small text-muted mt-4">
  Source: <a href="{link}" target="_blank" rel="nofollow noopener">Read the full article</a>
</p>
"""

            # entry
            date = today_iso()
            slug = slugify(title)[:70]
            entry = {
                "slug": slug,
                "title": title,
                "category": CATEGORY,
                "date": date,
                "excerpt": excerpt,
                "bodyHtml": body_final,         # ← përdorim body_final
                "cover": cover,
                "source": link,
                "sourceName": domain_of(link),
                "author": author
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "created": date}
            per_cat[category] = per_cat.get(category, 0) + 1
            added_total += 1
            print(f"Added [{CATEGORY}]: {title}")

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
