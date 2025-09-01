#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autopost • Culture → data/posts.json

Qëllimi:
- Tërheq artikujt Culture si HTML i pastruar me formatim (paragrafë, bold/italic, lista, blockquote, linkë).
- Ruaj 'body' (HTML), 'excerpt', 'excerptExtended', 'author', 'cover', 'source', 'sourceName'.
- Trunkim i sigurt i HTML-it sipas numrit të fjalëve pa prishur tagjet.
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse, urljoin
from xml.etree import ElementTree as ET

# Deps për nxjerrje dhe parse HTML
try:
    from readability import Document
    import lxml.html as LH
    import lxml.html.clean as LHC
except Exception as e:
    raise SystemExit("Install deps: pip install readability-lxml lxml")  # workflow duhet t'i ketë

try:
    import trafilatura  # mbetet si fallback
except Exception:
    trafilatura = None

# ====== Parametra / Path ======
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

# Sa fjalë të mbajmë brenda body (HTML) – i gjatë, jo i shkurtër
WORDS_LONG = int(os.getenv("SUMMARY_WORDS", "1000"))
# Sa fjalë për excerpt të shkurtër / të zgjatur (për lista)
WORDS_EXCERPT_SHORT = 70
WORDS_EXCERPT_LONG  = 200

ALLOWED_TAGS = {
    "p","h2","h3","strong","em","b","i","ul","ol","li","blockquote","a","img","figure","figcaption"
}
ALLOWED_ATTRS = {
    "a":   ["href","title","rel","target"],
    "img": ["src","alt","title","loading"]
}

# ====== Helpers HTTP/RSS ======
def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Fetch error:", url, "->", e)
        return b""

def fetch_text(url: str) -> str:
    b = fetch_bytes(url)
    if not b:
        return ""
    try:
        return b.decode("utf-8", "ignore")
    except Exception:
        return b.decode("latin-1", "ignore")

def parse_feed(xml_bytes: bytes):
    if not xml_bytes: return []
    try: root = ET.fromstring(xml_bytes)
    except ET.ParseError: return []
    items = []
    # RSS
    for it in root.findall(".//item"):
        title=(it.findtext("title") or "").strip()
        link =(it.findtext("link") or "").strip()
        desc =(it.findtext("description") or "").strip()
        author=(it.findtext("{http://purl.org/dc/elements/1.1/}creator") or it.findtext("author") or "").strip()
        if title and link:
            items.append({"title":title,"link":link,"summary":desc,"author":author,"element":it})
    # Atom
    ns={"atom":"http://www.w3.org/2005/Atom"}
    for e in root.findall(".//atom:entry", ns):
        title=(e.findtext("atom:title", default="") or "").strip()
        linkEl=e.find("atom:link[@rel='alternate']", ns) or e.find("atom:link", ns)
        link=(linkEl.attrib.get("href") if linkEl is not None else "").strip()
        summary=(e.findtext("atom:summary", default="") or e.findtext("atom:content", default="") or "").strip()
        author=(e.findtext("atom:author/atom:name", default="") or "").strip()
        if title and link:
            items.append({"title":title,"link":link,"summary":summary,"author":author,"element":e})
    return items

# ====== Utilities teksti/HTML ======
def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def domain_of(url: str) -> str:
    try: return urlparse(url).netloc.lower()
    except: return ""

def strip_html(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def og_image(page_url: str) -> str:
    html = fetch_text(page_url)
    if not html: return ""
    m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html, re.I)
    return m.group(1).strip() if m else ""

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

# ====== Readability → main content HTML ======
def extract_main_html_with_readability(page_html: str, base_url: str) -> str:
    try:
        doc = Document(page_html)
        summary_html = doc.summary(html_partial=True)  # HTML i main content
        return summary_html or ""
    except Exception:
        return ""

# ====== Pastrim me lxml, ruaj formatimin & linkët ======
def sanitize_and_normalize_html(html: str, base_url: str) -> str:
    """
    - Parse me lxml
    - Heq tagje të padëshiruara
    - Lejon vetëm tagjet/attributet e ALLOWED_*
    - Kthen href/src në absolute dhe vendos rel/target te <a>
    """
    if not html:
        return ""

    # parse si fragment (jo <html> e plotë)
    try:
        root = LH.fragment_fromstring(html, create_parent=True)  # <div> parent
    except Exception:
        # nëse dështon, kthe si paragraf tekst i pastër
        txt = strip_html(html)
        return f"<p>{LH.escape(txt)}</p>"

    # hiq <script>, <style>, komente
    LH.etree.strip_elements(root, LH.etree.Comment, "script", "style", with_tail=False)

    # shëtit elementët dhe filtro
    for el in list(root.iter()):
        tag = el.tag.lower() if isinstance(el.tag, str) else None
        if not tag:
            continue
        if tag not in ALLOWED_TAGS:
            el.drop_tag()  # ruaj tekstin e brendshëm, hiq tagun
            continue

        # lejo vetëm atributet e caktuara
        attrs = dict(el.attrib)
        for k in list(attrs.keys()):
            allowed = ALLOWED_ATTRS.get(tag, [])
            if k not in allowed:
                del el.attrib[k]

        # normalizo linkët
        if tag == "a" and "href" in el.attrib:
            href = el.attrib["href"].strip()
            el.attrib["href"] = urljoin(base_url, href)
            el.attrib["rel"] = "nofollow noopener"
            el.attrib["target"] = "_blank"

        if tag == "img" and "src" in el.attrib:
            src = el.attrib["src"].strip()
            el.attrib["src"] = urljoin(base_url, src)
            if "loading" not in el.attrib:
                el.attrib["loading"] = "lazy"
            # mbaj vetëm jpg/png/webp/gif tipikë (opsionale)
            # nëse s'do filtrim të imazheve, hiqe bllokun poshtë
            # if not re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', el.attrib["src"], re.I):
            #     el.drop_tree()

    # hiq <p> bosh
    for p in list(root.findall(".//p")):
        txt = (p.text_content() or "").strip()
        if not txt and len(p) == 0:
            p.drop_tree()

    html_clean = LH.tostring(root, method="html", encoding="unicode")
    # heq parent-in e jashtëm <div> nëse ekziston
    if html_clean.lower().startswith("<div") and html_clean.lower().endswith("</div>"):
        # merr përmbajtjen e brendshme
        inner = re.sub(r"^<div[^>]*>", "", html_clean, flags=re.I|re.S)
        inner = re.sub(r"</div>\s*$", "", inner, flags=re.I|re.S)
        html_clean = inner.strip()
    return html_clean

# ====== Trunkim i HTML-it sipas fjalëve (pa prishur tagjet) ======
def truncate_html_by_words(html: str, max_words: int) -> str:
    """Shkurton HTML-in duke ruajtur strukturën; numëron fjalët në text nodes."""
    if max_words <= 0:
        return html

    root = LH.fragment_fromstring(f"<div>{html}</div>", create_parent=False)

    words_used = 0
    stop = False

    def count_words(s: str) -> int:
        return len((s or "").split())

    def walker(node):
        nonlocal words_used, stop
        if stop:
            node.drop_tree()
            return

        # përpunon tekstin e node
        if node.text and not stop:
            w = count_words(node.text)
            if words_used + w > max_words:
                # prite text-in në limit
                remain = max_words - words_used
                node.text = " ".join(node.text.split()[:remain]) + "…"
                # hiq gjithë fëmijët
                for c in list(node):
                    c.drop_tree()
                stop = True
                return
            words_used += w

        # fëmijët
        for child in list(node):
            if stop:
                child.drop_tree()
                continue
            walker(child)

        # tail (teksti pas node-it)
        if node.tail and not stop:
            w = count_words(node.tail)
            if words_used + w > max_words:
                remain = max_words - words_used
                node.tail = " ".join(node.tail.split()[:remain]) + "…"
                stop = True
            else:
                words_used += w

    walker(root)

    out = LH.tostring(root, method="html", encoding="unicode")
    # heq wrapper <div>
    out = re.sub(r"^<div[^>]*>", "", out, flags=re.I|re.S)
    out = re.sub(r"</div>\s*$", "", out, flags=re.I|re.S)
    return out.strip()

# ====== Pipeline për një URL ======
def build_body_html(page_url: str) -> str:
    html = fetch_text(page_url)
    base = page_url

    # 1) Merr main content me Readability
    summary = extract_main_html_with_readability(html, base)

    # 2) Nëse bosh, provo trafilatura (si fallback)
    if (not summary) and trafilatura:
        try:
            alt = trafilatura.extract(html, url=base, include_formatting=True, include_links=True, include_images=True)
            if alt:
                summary = alt
        except Exception:
            summary = ""

    # 3) Nëse prapë bosh, rikthe si paragraf tekst i pastër
    if not summary:
        txt = strip_html(html)
        parts = [p.strip() for p in re.split(r"(?<=[\.\!\?])\s+(?=[A-ZËÇ])", txt) if p.strip()]
        summary = "\n".join([f"<p>{p}</p>" for p in parts]) or f"<p>{LH.escape(txt)}</p>"

    # 4) Pastrim dhe normalizim (lejo tagje bazë + href/src absolute)
    cleaned = sanitize_and_normalize_html(summary, base)

    # 5) Trunkim HTML (gjatë, p.sh. 1000 fjalë)
    limited = truncate_html_by_words(cleaned, WORDS_LONG)

    return limited

# ====== Main ======
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

    added = 0
    new_entries = []

    for feed in FEEDS:
        if added >= MAX_NEW:
            break
        xml = fetch_bytes(feed)
        if not xml: 
            print("Feed empty:", feed)
            continue

        for it in parse_feed(xml):
            if added >= MAX_NEW:
                break

            title = (it.get("title") or "").strip()
            link  = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # Body HTML me formatime + trunkim
            body_html = build_body_html(link)

            # Excerpts nga body_html i pastruar
            plain = strip_html(body_html)
            words = plain.split()
            excerpt = " ".join(words[:WORDS_EXCERPT_SHORT]) + ("…" if len(words) > WORDS_EXCERPT_SHORT else "")
            excerpt_ext = " ".join(words[:WORDS_EXCERPT_LONG]) + ("…" if len(words) > WORDS_EXCERPT_LONG else "")

            cover = find_image_from_item(it.get("element"), link) or FALLBACK_COVER

            # Atribut autor/burim – shtohet NË FUND të body_html
            author = (it.get("author") or "").strip()
            source_name = domain_of(link).replace("www.","")
            attribution = f"""
<hr class="my-4">
<div class="small text-muted">
  {(f'By <span class="fw-semibold">{LH.escape(author)}</span>. ' if author else '')}
  Source: <a href="{link}" rel="nofollow noopener" target="_blank">{LH.escape(source_name or 'original')}</a>.
  <a class="btn btn-sm btn-outline-brand ms-2" href="{link}" target="_blank" rel="nofollow noopener">Lexo artikullin origjinal →</a>
</div>
""".strip()

            body_final = f"{body_html}\n{attribution}"

            entry = {
                "slug": slugify(title)[:70],
                "title": title,
                "category": CATEGORY,
                "date": today_iso(),
                "excerpt": excerpt,
                "excerptExtended": excerpt_ext,
                "body": body_final,
                "cover": cover,
                "source": link,
                "sourceName": source_name,
                "author": author
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
