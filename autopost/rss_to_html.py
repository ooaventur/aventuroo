#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RSS → data/posts.json (AventurOO)
# - lexon feeds.txt (format: kategori|URL)
# - nxjerr trupin e artikullit (article/main/JSON-LD, ose blloku më i gjatë i paragrafëve)
# - krijon 'content' (paragrafë) + 'excerpt' (~450 fjalë)
# - merr author, cover, source
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
MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL = int(os.getenv("MAX_TOTAL", "0"))              # 0 = pa limit total / run
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "450"))     # për excerpt
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")

# ---- Helpers ----
def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        raw = r.read()
    # dekodim tolerant
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("iso-8859-1")
        except Exception:
            return raw.decode("utf-8", "ignore")

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
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def html_paragraphs(s: str) -> list[str]:
    """Kthen listë paragrafësh (tekst) nga HTML (vetëm <p>), të pastruar."""
    if not s:
        return []
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", s)
    # mer vetëm <p>…</p>
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", s)
    clean = []
    for p in paras:
        t = strip_html(p)
        if len(t) < 30:  # filtro titra/mbishkrime shumë të shkurtra
            continue
        clean.append(t)
    return clean

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def find_og_content(html: str, prop: str) -> str:
    m = re.search(rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    return m.group(1).strip() if m else ""

def find_image_from_item(it_elem, page_url: str = "") -> str:
    """Kërkon imazh nga <enclosure>, <media:content>/<media:thumbnail>, ose og:image."""
    if it_elem is not None:
        enc = it_elem.find("enclosure")
        if enc is not None and str(enc.attrib.get("type", "")).startswith("image"):
            u = enc.attrib.get("url", "")
            if u: return u
        ns = {"media": "http://search.yahoo.com/mrss/"}
        m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
        if m is not None and m.attrib.get("url"):
            return m.attrib.get("url")
    if page_url:
        try:
            html = http_get(page_url)
            og = find_og_content(html, "og:image")
            if og: return og
        except Exception:
            pass
    return ""

def shorten_words(text: str, max_words: int) -> str:
    w = (text or "").split()
    if len(w) <= max_words:
        return (text or "").strip()
    return " ".join(w[:max_words]) + "…"

# ----------- EXTRACT MAIN ARTICLE TEXT -----------
def extract_article_text(page_html: str, title_hint: str = "") -> str:
    """
    Heuristikë:
      1) JSON-LD articleBody
      2) <article>…</article>
      3) <main>…</main>
      4) Blloku më i gjatë i paragrafëve (sidomos pas titullit)
      5) og:description si fallback
    Kthen tekst të pastër me \n\n si ndarje paragrafësh.
    """
    if not page_html:
        return ""

    html = page_html

    # 1) JSON-LD articleBody
    for m in re.finditer(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        # JSON-LD mund të jetë listë ose objekt
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            # shume faqe kanë "@type": "NewsArticle"/"Article"/"BlogPosting"
            atype = obj.get("@type", "")
            if isinstance(atype, list):
                atype = " ".join(atype)
            body = obj.get("articleBody") or obj.get("description") or ""
            if body and ("Article" in str(atype) or "Blog" in str(atype) or "News" in str(atype)):
                body = strip_html(body)
                # ktheje në paragrafë sipas pikësimit nëse s’ka \n
                if "\n" not in body:
                    body = re.sub(r"([.!?])\s+", r"\1\n\n", body)
                return "\n\n".join([p.strip() for p in body.splitlines() if p.strip()])

    # 2) <article>
    m = re.search(r"(?is)<article\b[^>]*>(.*?)</article>", html)
    if m:
        paras = html_paragraphs(m.group(1))
        if paras:
            return "\n\n".join(paras)

    # 3) <main>
    m = re.search(r"(?is)<main\b[^>]*>(.*?)</main>", html)
    if m:
        paras = html_paragraphs(m.group(1))
        if paras:
            return "\n\n".join(paras)

    # 4) Blloku më i gjatë i <p> paragrafëve (pas titullit nëse gjendet)
    start_idx = 0
    if title_hint:
        t = re.escape(title_hint.strip())
        mtitle = re.search(t, html, re.I)
        if mtitle:
            start_idx = mtitle.end()
    chunk = html[start_idx:] if start_idx > 0 else html
    # marrim deri para footer/aside/related që shpesh sjellin zhurmë
    chunk = re.split(r"(?is)<footer\b|<aside\b|<section[^>]+related", chunk)[0]
    paras = html_paragraphs(chunk)
    if not paras:
        # gjithë faqja si fallback
        paras = html_paragraphs(html)
    if paras:
        # zgjidh 12-25 paragrafët e parë më kuptimplotë
        joined = "\n\n".join(paras[:25])
        return joined

    # 5) og:description
    ogd = find_og_content(html, "og:description")
    return ogd or ""

def extract_from_url(url: str, title_hint: str, max_words: int) -> tuple[str, str]:
    """
    Kthen (content_text, excerpt_text) nga URL:
    - content_text: paragrafë me \n\n
    - excerpt_text: version i shkurtuar ~max_words
    """
    try:
        html = http_get(url)
    except Exception:
        return ("", "")

    content = extract_article_text(html, title_hint=title_hint)
    content = content.strip()
    excerpt = shorten_words(content if content else strip_html(html), max_words)
    return (content, excerpt)

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

            # --- Author nga feed ---
            author = ""
            it_elem = it.get("element")
            try:
                # DC creator
                ns_dc = {"dc": "http://purl.org/dc/elements/1.1/"}
                dc = it_elem.find("dc:creator", ns_dc) if it_elem is not None else None
                if dc is not None and (dc.text or "").strip():
                    author = dc.text.strip()
                # RSS <author>
                if not author and it_elem is not None:
                    a = it_elem.find("author")
                    if a is not None and (a.text or "").strip():
                        author = a.text.strip()
                # Atom <author><name>
                if not author and it_elem is not None:
                    ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
                    an = it_elem.find("atom:author/atom:name", ns_atom)
                    if an is not None and (an.text or "").strip():
                        author = an.text.strip()
            except Exception:
                author = ""
            if not author:
                author = "AventurOO Editorial"

            # --- Content + Excerpt (nga faqja, jo gjithë sajti) ---
            content_text, excerpt_text = extract_from_url(link, title, SUMMARY_WORDS)
            # nqs prapë nuk arriti dot, provo dhe summary nga feed
            if not excerpt_text:
                excerpt_text = strip_html(it.get("summary", "")) or title

            # Imazhi
            cover = ""
            try:
                cover = find_image_from_item(it_elem, link)
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
                "excerpt": excerpt_text,      # ~450 fjalë
                "content": content_text,      # trup i pastruar me \n\n
                "cover": cover,
                "source": link,
                "author": author
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": category, "created": date}
            per_cat_counter[category] = per_cat_counter.get(category, 0) + 1
            added_total += 1

            print(f"Added [{category}]: {title} (by {author})")

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
