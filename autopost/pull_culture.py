#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autopost • Culture → data/posts.json
- Merr artikuj nga feeds culture
- Nxjerr HTML të pastruar me formatim (bold/italic/blockquote/lista) & paragrafë si origjinali
- Inkorporon linkët brenda tekstit (markdown-style dhe URL të zhveshura)
- Kufizon në preview (~650 fjalë)
- Ruaj: slug,title,category,date,excerpt,excerptExtended,body,cover,source,sourceName,author
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

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
WORDS_LONG = int(os.getenv("SUMMARY_WORDS", "650"))

ALLOWED_TAGS = {"p","h2","h3","strong","em","b","i","ul","ol","li","blockquote","a","img"}

try:
    import trafilatura
except Exception:
    trafilatura = None

# ---------- helpers ----------
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
    items = []
    for it in root.findall(".//item"):
        title=(it.findtext("title") or "").strip()
        link =(it.findtext("link") or "").strip()
        desc =(it.findtext("description") or "").strip()
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

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def domain_of(url: str) -> str:
    try: return urlparse(url).netloc.lower()
    except: return ""

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
        try: return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError: return default
    return default

def save_json(p: pathlib.Path, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------- pastrim/inkorporim i HTML ----------
def clean_html_keep_basic(html: str) -> str:
    if not html: return ""
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)

    def sanitize_attrs(tag, attrs):
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
            return ""  # hiq tagun
        if closing:
            return f"</{tag}>"
        allowed = sanitize_attrs(tag, attrs)
        if tag == "a" and "href" in allowed:
            return f'<a href="{allowed["href"]}" rel="nofollow noopener" target="_blank">'
        if tag == "img" and "src" in allowed:
            return f'<img src="{allowed["src"]}" loading="lazy" alt="">'
        return f"<{tag}>"

    html = re.sub(r"</?([a-zA-Z0-9]+)(\s[^>]*)?>", repl, html)
    html = re.sub(r"\n{2,}", "\n", html).strip()
    return html

def inlineify_links(html: str) -> str:
    """Kthen formatet e zakonshme të linkeve në <a> inline dhe linkon URL-të e zhveshura."""
    if not html: return ""

    # 1) Markdown: [text](https://url)
    html = re.sub(
        r"\[([^\]]{2,})\]\((https?://[^)]+)\)",
        r'<a href="\2" rel="nofollow noopener" target="_blank">\1</a>',
        html
    )

    # 2) Pattern 'text (https://url)' → 'text' bëhet link (vetëm kur () janë në fund fjalisë ose para pikës)
    def paren_link(m):
        text = m.group(1).strip()
        url  = m.group(2).strip()
        # shmang rastet ku 'text (' është pjesë e emrash/etiketave
        if len(text) >= 3:
            return f'<a href="{url}" rel="nofollow noopener" target="_blank">{text}</a>'
        return m.group(0)
    html = re.sub(r"([A-Za-zËÇÇëç0-9 ,;:'\"-]{3,})\s*\((https?://[^)]+)\)", paren_link, html)

    # 3) Linko URL të zhveshura që nuk janë tashmë në href
    html = re.sub(
        r'(?<!href=")(https?://[^\s<>"\')]+)',
        r'<a href="\1" rel="nofollow noopener" target="_blank">\1</a>',
        html
    )

    return html

def limit_words_html(html: str, max_words: int) -> str:
    text = strip_html(html)
    words = text.split()
    if len(words) <= max_words:
        return html
    short = " ".join(words[:max_words]) + "…"
    parts = [p.strip() for p in re.split(r"(?<=[\.\!\?])\s+(?=[A-ZËÇ])", short) if p.strip()]
    return "\n".join([f"<p>{p}</p>" for p in parts]) or f"<p>{short}</p>"

def extract_formatted_html(url: str) -> str:
    raw_html = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw_html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
    except Exception:
        raw_html = ""

    body_html = ""
    if trafilatura and raw_html:
        try:
            out = trafilatura.extract(
                raw_html, url=url,
                include_formatting=True,
                include_links=True,
                include_images=True
            )
            if out:
                body_html = out
        except Exception:
            body_html = ""

    if not body_html:
        text = strip_html(raw_html)
        parts = [p.strip() for p in re.split(r"(?<=[\.\!\?])\s+(?=[A-ZËÇ])", text) if p.strip()]
        body_html = "\n".join([f"<p>{p}</p>" for p in parts])

    body_html = clean_html_keep_basic(body_html)
    body_html = inlineify_links(body_html)   # ← inkorporo linkët në tekst
    body_html = limit_words_html(body_html, WORDS_LONG)
    return body_html

# ---------- main ----------
def main():
    DATA_DIR.mkdir(exist_ok=True)
    seen  = load_json_safe(SEEN_DB, {})
    posts = load_json_safe(POSTS_JSON, [])

    added = 0
    new_entries = []

    for feed in FEEDS:
        if added >= MAX_NEW: break
        xml = fetch(feed)
        if not xml: continue

        for it in parse(xml):
            if added >= MAX_NEW: break

            title=(it.get("title") or "").strip()
            link =(it.get("link") or "").strip()
            if not title or not link: continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen: continue

            body_html = extract_formatted_html(link)

            plain = strip_html(body_html)
            words = plain.split()
            excerpt = " ".join(words[:70]) + ("…" if len(words) > 70 else "")
            excerpt_ext = " ".join(words[:min(WORDS_LONG, 650)]) + ("…" if len(words) > WORDS_LONG else "")

            cover = find_image_from_item(it.get("element"), link) or FALLBACK_COVER

            entry = {
                "slug": slugify(title)[:70],
                "title": title,
                "category": CATEGORY,
                "date": today_iso(),
                "excerpt": excerpt,
                "excerptExtended": excerpt_ext,
                "body": body_html,
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
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autopost • Culture → data/posts.json
- Lexon disa RSS burime culture
- Shkarkon faqen e artikullit dhe nxjerr bodyHtml të pastruar (preview)
- Krijon rekord: {slug,title,category,date,excerpt,bodyHtml,cover,source,sourceName,author}
- Nuk përdor lorem; excerpt = tekst i shkurtuar
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# Opsionale: trafilatura për ekstraktim
try:
    import trafilatura  # pip install trafilatura
except Exception:
    trafilatura = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"

# Feeds vetëm për Culture
FEEDS = [
    # Hyperallergic (art news)
    "https://hyperallergic.com/feed/",
    # Smithsonian (latest articles)
    "https://www.smithsonianmag.com/rss/latest_articles/",
]

CATEGORY = "Culture"

SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "700"))   # gjatësia e preview
MAX_NEW = int(os.getenv("MAX_PER_CAT", "6"))             # sa artikuj maksimum për një run
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")

ALLOWED_TAGS = {"p","h2","h3","strong","b","em","i","ul","ol","li","blockquote","a"}

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
    # RSS 2.0
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        author = (it.findtext("{http://purl.org/dc/elements/1.1/}creator") or it.findtext("author") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "summary": desc, "author": author, "element": it})
    # Atom
    ns = {"atom":"http://www.w3.org/2005/Atom"}
    for e in root.findall(".//atom:entry", ns):
        title = (e.findtext("atom:title", default="") or "").strip()
        link_el = e.find("atom:link[@rel='alternate']", ns) or e.find("atom:link", ns)
        link = (link_el.attrib.get("href") if link_el is not None else "").strip()
        summary = (e.findtext("atom:summary", default="") or e.findtext("atom:content", default="") or "").strip()
        author = (e.findtext("atom:author/atom:name", default="") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "summary": summary, "author": author, "element": e})
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
    if m: return m.group(1)
    return ""

def find_image_from_item(it_elem, page_url: str = "") -> str:
    if it_elem is not None:
        enc = it_elem.find("enclosure")
        if enc is not None and str(enc.attrib.get("type", "")).startswith("image"):
            u = enc.attrib.get("url", "")
            if u: return u
        ns = {"media":"http://search.yahoo.com/mrss/"}
        m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
        if m is not None and m.attrib.get("url"):
            return m.attrib.get("url")
    # og:image si fallback
    img = og_image(page_url) if page_url else ""
    return img

def clean_html_keep_basic(html: str) -> str:
    """Heq çdo tag jashtë ALLOWED_TAGS; lejon <a href> me rel, heq atributet tjera."""
    if not html:
        return ""
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)
    # thjeshtim: kthe <br> në fund fjalishë
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)

    # heq tagjet por mban allowed
    def repl_tag(m):
        tag = m.group(1).lower()
        closing = m.group(0).startswith("</")
        if tag in ALLOWED_TAGS:
            # lejo vetëm <a href="">
            if tag == "a":
                href = re.search(r'href=["\']([^"\']+)["\']', m.group(0), re.I)
                h = href.group(1) if href else "#"
                return f'<{" /" if closing else ""}a href="{h}" rel="nofollow noopener" target="_blank">'.replace(' /a', '/a')
            return f"<{'/' if closing else ''}{tag}>"
        return ""  # hiq tagje të tjerë

    # zëvendëso të gjitha tagjet me një version të filtruar
    html = re.sub(r"</?([a-zA-Z0-9]+)(\s[^>]*)?>", repl_tag, html)
    # normalizo boshllëqet
    html = re.sub(r"\n{2,}", "\n", html)
    return html

def extract_body_html(url: str) -> (str, str):
    """Kthen (bodyHtml, excerpt) si preview i pastruar dhe i shkurtuar."""
    html = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
    except Exception:
        html = ""

    # Trafilatura (nëse ekziston) – jep HTML të pastër
    body_html = ""
    if trafilatura and html:
        try:
            downloaded = trafilatura.bare_extraction(html, url=url, with_metadata=True)
            if downloaded and downloaded.get("text"):
                # tekst i plotë në plain
                full_text = downloaded["text"]
                words = full_text.split()
                if len(words) > SUMMARY_WORDS:
                    full_text = " ".join(words[:SUMMARY_WORDS]) + "…"

                # ktheje në paragrafë <p>
                paras = [f"<p>{p.strip()}</p>" for p in re.split(r"\n{2,}", full_text) if p.strip()]
                body_html = "\n".join(paras)
        except Exception:
            body_html = ""

    # fallback: përdor plain nga faqa, shkurto, nda në paragrafë
    if not body_html:
        text = strip_html(html)
        words = text.split()
        if len(words) > SUMMARY_WORDS:
            text = " ".join(words[:SUMMARY_WORDS]) + "…"
        parts = [p.strip() for p in re.split(r"(?<=[\.\!\?])\s+(?=[A-ZËÇ])", text) if p.strip()]
        body_html = "\n".join([f"<p>{p}</p>" for p in parts])

    # excerpt = 1-2 paragrafët e parë, për listime
    excerpt = strip_html(body_html)
    ex_words = excerpt.split()
    if len(ex_words) > 70:
        excerpt = " ".join(ex_words[:70]) + "…"

    # pastrim përfundimtar (lejo vetë disa tagje)
    body_html = clean_html_keep_basic(body_html)
    return body_html, excerpt

def load_json_safe(p: pathlib.Path, default):
    if p.exists():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            return obj
        except json.JSONDecodeError:
            return default
    return default

def save_json(p: pathlib.Path, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    DATA_DIR.mkdir(exist_ok=True)
    seen = load_json_safe(SEEN_DB, {})
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

            # body + excerpt
            body_html, excerpt = extract_body_html(link)

            # cover
            cover = find_image_from_item(it.get("element"), link) or FALLBACK_COVER

            entry = {
                "slug": slugify(title)[:70],
                "title": title,
                "category": CATEGORY,
                "date": today_iso(),
                "excerpt": excerpt,
                "bodyHtml": body_html,       # ← do ta lexojë article.html
                "cover": cover,
                "source": link,
                "sourceName": domain_of(link).replace("www.",""),
                "author": it.get("author") or ""
            }
            new_entries.append(entry)
            seen[key] = {"title": title, "url": link, "created": today_iso()}
            added += 1
            print("Added:", title)

    if not new_entries:
        print("New posts: 0")
        return

    posts = new_entries + posts
    posts = posts[:200]  # mbaj maksimumi 200
    save_json(POSTS_JSON, posts)
    save_json(SEEN_DB, seen)
    print("New posts:", len(new_entries))

if __name__ == "__main__":
    main()
