#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RSS → data/posts.json (AventurOO)
# - përdor trafilatura për të nxjerrë trupin real të artikullit (jo nav/footer/skripte)
# - heq çdo "code/script" nga teksti; filtron paragrafët e shkurtër/jo-kuptimplotë
# - shkruan: title, category, date, author, cover, source, excerpt (~450 fjalë), content (tekst i pastër me \n\n)

import os, re, json, hashlib, pathlib
from xml.etree import ElementTree as ET
from .utils import (
    fetch_bytes as fetch,
    http_get as http_get_text,
    strip_html,
    slugify,
    today_iso,
)

# ---- external extractor ----
try:
    import trafilatura
    from trafilatura.settings import use_config
except Exception:
    trafilatura = None

# ---- Paths ----
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = PACKAGE_ROOT / "seen.json"
FEEDS = PACKAGE_ROOT / "data" / "feeds.txt"

# ---- Env / Defaults ----
MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL = int(os.getenv("MAX_TOTAL", "0"))          # 0 = pa limit total / run
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "450"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")

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
        if title and link:
            items.append({"title": title, "link": link, "summary": desc, "element": it})
    # Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for e in root.findall(".//atom:entry", ns):
        title = (e.findtext("atom:title", default="") or "").strip()
        link_el = e.find("atom:link[@rel='alternate']", ns) or e.find("atom:link", ns)
        link = (link_el.attrib.get("href") if link_el is not None else "").strip()
        summary = (
            e.findtext("atom:summary", default="")
            or e.findtext("atom:content", default="")
            or ""
        ).strip()
        if title and link:
            items.append({"title": title, "link": link, "summary": summary, "element": e})
    return items

# ---- utils ----
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
    # og:image nga trafilatura metadata (më poshtë) ose fallback
    return ""

def shorten_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if len(words) <= max_words:
        return (text or "").strip()
    return " ".join(words[:max_words]) + "…"

# ---- anti-script/code cleaner për paragrafë ----
CODE_PATTERNS = [
    r"\bfunction\s*\(", r"\bvar\s+\w+\s*=", r"\blet\s+\w+\s*=", r"\bconst\s+\w+\s*=",
    r"</?\w+[^>]*>", r"[{};<>]{2,}", r"\bconsole\.log\b", r"\$\(", r"document\.querySelector",
    r"<script", r"</script", r"@media", r"window\.", r"import\s+",
]
CODE_RE = re.compile("|".join(CODE_PATTERNS), re.I)

def clean_paragraphs(text: str) -> list:
    """Ndaj në paragrafë, filtro kod/skript/mbishkrime shumë të shkurtra."""
    if not text:
        return []
    # normalizo newline
    t = re.sub(r"\r\n?", "\n", text).strip()
    # ndaj sipas blloqeve
    blocks = [b.strip() for b in re.split(r"\n{2,}", t) if b.strip()]
    cleaned = []
    for b in blocks:
        # hiq rreshta shumë të shkurtër (tituj nav, etj.)
        if len(b) < 30:
            continue
        if CODE_RE.search(b):
            continue
        cleaned.append(b)
    # nëse filtrimi e boshatis, kthehu te versioni para filtrit (por i gjatë)
    if not cleaned and blocks:
        cleaned = [x for x in blocks if len(x) > 30][:10]
    return cleaned

# ---- Trafilatura extract ----
def extract_with_trafilatura(url: str) -> dict:
    """
    Kthen {text, title, author, image, description}
    - text është body i artikullit (plain text, paragrafë me \n)
    """
    if trafilatura is None:
        return {}
    cfg = use_config()
    cfg.set("DEFAULT", "EXTRACTION_TIMEOUT", str(HTTP_TIMEOUT))
    downloaded = trafilatura.fetch_url(url, config=cfg)
    if not downloaded:
        return {}
    result = trafilatura.extract(downloaded, config=cfg, include_comments=False, include_tables=False, include_images=False, with_metadata=True)
    if not result:
        return {}
    # trafilatura kthen një string JSON kur with_metadata=True
    try:
        data = json.loads(result)
    except Exception:
        # në disa versione kthehet tekst i thjeshtë (pa metadata)
        data = {"text": str(result)}
    return {
        "text": data.get("text") or "",
        "title": data.get("title") or "",
        "author": data.get("author") or "",
        "image": data.get("image") or "",
        "description": data.get("description") or "",
    }

# ----------------- MAIN -----------------
def main():
    DATA_DIR.mkdir(exist_ok=True)

    # SEEN
    if SEEN_DB.exists():
        try:
            seen = json.loads(SEEN_DB.read_text(encoding="utf-8"))
            if not isinstance(seen, dict):
                seen = {}
        except json.JSONDecodeError:
            seen = {}
    else:
        seen = {}

    # POSTS
    if POSTS_JSON.exists():
        try:
            posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
            if not isinstance(posts_idx, list):
                posts_idx = []
        except json.JSONDecodeError:
            posts_idx = []
    else:
        posts_idx = []

    # feeds
    if not FEEDS.exists():
        print("ERROR: feeds.txt NOT FOUND at", FEEDS)
        return

    added_total = 0
    per_cat = {}
    new_entries = []

    for line in FEEDS.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
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
            print("Feed empty:", feed_url); continue
        items = parse(xml)
        if not items:
            print("No items in feed:", feed_url); continue

        for it in items:
            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break
            if per_cat.get(category, 0) >= MAX_PER_CAT:
                continue

            title = (it.get("title") or "").strip()
            link  = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # ---- author nga feed (dc/author/atom) ----
            author = ""
            it_elem = it.get("element")
            try:
                ns_dc = {"dc": "http://purl.org/dc/elements/1.1/"}
                dc = it_elem.find("dc:creator", ns_dc) if it_elem is not None else None
                if dc is not None and (dc.text or "").strip():
                    author = dc.text.strip()
                if not author and it_elem is not None:
                    a = it_elem.find("author")
                    if a is not None and (a.text or "").strip():
                        author = a.text.strip()
                if not author and it_elem is not None:
                    ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
                    an = it_elem.find("atom:author/atom:name", ns_atom)
                    if an is not None and (an.text or "").strip():
                        author = an.text.strip()
            except Exception:
                author = ""
            if not author:
                author = "AventurOO Editorial"

            # ---- ekstrakt me trafilatura ----
            text_raw = ""
            lead_image = ""
            description = ""
            if trafilatura is not None:
                try:
                    ext = extract_with_trafilatura(link)
                    text_raw = ext.get("text") or ""
                    lead_image = ext.get("image") or ""
                    description = ext.get("description") or ""
                    # autor nga metadata nëse s'erdhi nga RSS
                    if author == "AventurOO Editorial" and ext.get("author"):
                        author = ext["author"].strip()
                except Exception as e:
                    print("trafilatura error:", e)

            # fallback nëse s'ka tekst
            if not text_raw:
                try:
                    html = http_get_text(link)
                    text_raw = strip_html(html)
                except Exception:
                    text_raw = ""

            # pastro paragrafët (hiq code/script), strukturo
            paragraphs = clean_paragraphs(text_raw)
            content_text = "\n\n".join(paragraphs).strip()

            # excerpt
            base_excerpt = content_text if content_text else (description or (it.get("summary") or ""))
            excerpt_text = shorten_words(strip_html(base_excerpt), SUMMARY_WORDS)

            # cover
            cover = ""
            if not lead_image:
                try:
                    cover = find_image_from_item(it_elem, link)
                except Exception:
                    cover = ""
            cover = lead_image or cover or FALLBACK_COVER

            date = today_iso()
            slug = slugify(title)[:70]

            entry = {
                "slug": slug,
                "title": title,
                "category": category,
                "date": date,
                "author": author,
                "source": link,
                "cover": cover,
                "excerpt": excerpt_text,   # ~450 fjalë, për listime
                "content": content_text    # body i pastruar, paragrafë me \n\n
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": category, "created": date}
            per_cat[category] = per_cat.get(category, 0) + 1
            added_total += 1
            print(f"Added [{category}]: {title} (by {author})")

    if not new_entries:
        print("New posts this run: 0"); return

    posts_idx = new_entries + posts_idx
    if MAX_POSTS_PERSIST > 0:
        posts_idx = posts_idx[:MAX_POSTS_PERSIST]

    POSTS_JSON.write_text(json.dumps(posts_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("New posts this run:", len(new_entries))

if __name__ == "__main__":
    main()
