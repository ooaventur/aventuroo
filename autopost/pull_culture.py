#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autopost • Culture → data/posts.json
- Merr artikuj nga feeds culture
- Nxjerr HTML të pastruar me formatim (bold/italic/blockquote/lista) & paragrafë si origjinali
- Kufizon në preview (~650 fjalë) për siguri ligjore
- Ruaj: slug,title,category,date,excerpt,excerptExtended,body,cover,source,sourceName,author
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# ====== Parametra ======
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"

# Burimet Culture (shto/ndrysho sipas dëshirës)
FEEDS = [
    "https://hyperallergic.com/feed/",
    "https://www.smithsonianmag.com/rss/latest_articles/",
]

CATEGORY = "Culture"
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")
MAX_NEW = int(os.getenv("MAX_PER_CAT", "6"))
WORDS_LONG = int(os.getenv("SUMMARY_WORDS", "650"))  # ~450–700 sipas kërkesës

ALLOWED_TAGS = {"p","h2","h3","strong","em","b","i","ul","ol","li","blockquote","a","img"}

# ====== Deps opsionale ======
try:
    import trafilatura  # pip install trafilatura
except Exception:
    trafilatura = None

# ====== Helpers ======
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
        link  = (it.findtext("link") or "").strip()
        desc  = (it.findtext("description") or "").strip()
        author= (it.findtext("{http://purl.org/dc/elements/1.1/}creator") or it.findtext("author") or "").strip()
        if title and link:
            items.append({"title":title,"link":link,"summary":desc,"author":author,"element":it})
    # Atom
    ns={"atom":"http://www.w3.org/2005/Atom"}
    for e in root.findall(".//atom:entry", ns):
        title = (e.findtext("atom:title", default="") or "").strip()
        link_el = e.find("atom:link[@rel='alternate']", ns) or e.find("atom:link", ns)
        link  = (link_el.attrib.get("href") if link_el is not None else "").strip()
        summary = (e.findtext("atom:summary", default="") or e.findtext("atom:content", default="") or "").strip()
        author = (e.findtext("atom:author/atom:name", default="") or "").strip()
        if title and link:
            items.append({"title":title,"link":link,"summary":summary,"author":author,"element":e})
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

def og_image(page_url: str) -> str:
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
    except Exception:
        return ""
    m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html, re.I)
    return m.group(1) if m else ""

def find_image_from_item(it_elem, page_url: str = "") -> str:
    if it_elem is not None:
        enc = it_elem.find("enclosure")
        if enc is not None and str(enc.attrib.get("type","")).startswith("image"):
            u = enc.attrib.get("url","")
            if u: return u
        ns={"media":"http://search.yahoo.com/mrss/"}
        m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
        if m is not None and m.attrib.get("url"):
            return m.attrib.get("url")
    return og_image(page_url) or ""

def load_json_safe(p: pathlib.Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default

def save_json(p: pathlib.Path, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# === Pastrim i HTML-it (lejo vetëm tagjet bazike + href/src të sigurta) ===
def clean_html_keep_basic(html: str) -> str:
    if not html:
        return ""
    # hiq skript/style
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)

    # normalizo <br> në newline për të ruajtur ndjesinë e paragrafëve te disa burime
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)

    # hiq atributet e rrezikshme; lejo vetëm href/src (sanitizim i thjeshtë)
    def sanitize_attrs(tag, attrs):
        # lejo vetëm href për <a> dhe src për <img>
        allowed = {}
        if tag == "a":
            href = re.search(r'href\s*=\s*["\']([^"\']+)["\']', attrs or "", re.I)
            if href:
                val = href.group(1).strip()
                if val.startswith("http"):
                    allowed["href"] = val
        if tag == "img":
            src = re.search(r'src\s*=\s*["\']([^"\']+)["\']', attrs or "", re.I)
            if src:
                val = src.group(1).strip()
                if val.startswith("http"):
                    allowed["src"] = val
        return allowed

    def repl(m):
        closing = m.group(0).startswith("</")
        tag = m.group(1).lower()
        attrs = m.group(2) or ""
        if tag not in ALLOWED_TAGS:
            return ""  # hiq tagjet e tjerë
        if closing:
            return f"</{tag}>"
        allowed = sanitize_attrs(tag, attrs)
        if tag == "a" and "href" in allowed:
            return f'<a href="{allowed["href"]}" rel="nofollow noopener" target="_blank">'
        if tag == "img" and "src" in allowed:
            return f'<img src="{allowed["src"]}" loading="lazy" alt="">'
        # tagje të thjeshta pa atribute
        return f"<{tag}>"

    html = re.sub(r"</?([a-zA-Z0-9]+)(\s[^>]*)?>", repl, html)
    # hiq boshllëqe të tepërta
    html = re.sub(r"\n{2,}", "\n", html).strip()
    return html

def limit_words_html(html: str, max_words: int) -> str:
    """
    Kufizon numrin e fjalëve në HTML duke ruajtur më së miri tagjet bazike.
    Strategji e thjeshtë: hiq tagjet → numëro fjalët → prite në tekst → rikthe në <p> paragrafë.
    """
    text = strip_html(html)
    words = text.split()
    if len(words) <= max_words:
        return html
    short = " ".join(words[:max_words]) + "…"
    # rikthe si paragrafë
    parts = [p.strip() for p in re.split(r"(?<=[\.\!\?])\s+(?=[A-ZËÇ])", short) if p.strip()]
    return "\n".join([f"<p>{p}</p>" for p in parts]) or f"<p>{short}</p>"

def extract_formatted_html(url: str) -> str:
    """Merr HTML të pastruar me formatim bazik nga faqa (preferohet trafilatura)."""
    raw_html = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw_html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
    except Exception:
        raw_html = ""

    body_html = ""
    if trafilatura and raw_html:
        try:
            # Kjo kthen HTML të thjeshtuar me paragrafë dhe theksime
            out = trafilatura.extract(
                raw_html, url=url,
                include_formatting=True,
                include_links=True,
                include_images=True  # do filtrohen me clean_html_keep_basic
            )
            if out:
                body_html = out
        except Exception:
            body_html = ""

    if not body_html:
        # fallback: tekst i thjeshtë në paragrafë
        text = strip_html(raw_html)
        parts = [p.strip() for p in re.split(r"(?<=[\.\!\?])\s+(?=[A-ZËÇ])", text) if p.strip()]
        body_html = "\n".join([f"<p>{p}</p>" for p in parts])

    # pastrim & kufizim
    body_html = clean_html_keep_basic(body_html)
    body_html = limit_words_html(body_html, WORDS_LONG)
    return body_html

# ====== Main ======
def main():
    DATA_DIR.mkdir(exist_ok=True)
    seen  = load_json_safe(SEEN_DB, {})
    posts = load_json_safe(POSTS_JSON, [])

    added = 0
    new_entries = []

    for feed in FEEDS:
        if added >= MAX_NEW:
            break
        xml = fetch(feed)
        if not xml:
            continue
        for it in parse(xml):
            if added >= MAX_NEW:
                break

            title = (it.get("title") or "").strip()
            link  = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # Krijo body (HTML me formatim bazik) + excerpt/extended
            body_html = extract_formatted_html(link)

            # excerpt i shkurtër (për listime)
            plain = strip_html(body_html)
            words = plain.split()
            excerpt = " ".join(words[:70]) + ("…" if len(words) > 70 else "")
            excerpt_ext = " ".join(words[:min(WORDS_LONG, 650)]) + ("…" if len(words) > WORDS_LONG else "")

            # cover
            cover = find_image_from_item(it.get("element"), link) or FALLBACK_COVER

            entry = {
                "slug": slugify(title)[:70],
                "title": title,
                "category": CATEGORY,
                "date": today_iso(),
                "excerpt": excerpt,
                "excerptExtended": excerpt_ext,
                "body": body_html,  # ← article.html do e përdorë direkt
                "cover": cover,
                "source": link,
                "sourceName": domain_of(link).replace("www.",""),
                "author": it.get("author") or ""
            }

            new_entries.append(entry)
            seen[key] = {"title": title, "url": link, "created": today_iso()}
            added += 1
            print(f"[Culture] + {title}")

    if not new_entries:
        print("New posts: 0"); return

    posts = new_entries + posts
    posts = posts[:200]
    save_json(POSTS_JSON, posts)
    save_json(SEEN_DB, seen)
    print("New posts:", len(new_entries))

if __name__ == "__main__":
    main()
