#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RSS → HTML posts + posts.json for AventurOO (robust, full for whitelisted sources, gallery images)

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "posts"
POSTS_JSON = ROOT / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

# 3 postime per run; me schedule çdo 2 orë → ~36/ditë (ndrysho sipas nevojës)
MAX_PER_RUN = 3
HTTP_TIMEOUT = 15  # sec
UA = "Mozilla/5.0 (AventurOO Autoposter; +https://example.com)"

# Burime ku lejohet FULL (Public Domain / CC BY 4.0)
FULL_WHITELIST = {
    "wwwnc.cdc.gov": {
        "license": "Public Domain (U.S. Federal Government)",
        "attr": "CDC Travelers' Health",
        "attr_url": "https://wwwnc.cdc.gov/travel",
        "license_url": "https://www.usa.gov/government-copyright"
    },
    "www.smartraveller.gov.au": {
        "license": "CC BY 4.0",
        "attr": "DFAT Smartraveller",
        "attr_url": "https://www.smartraveller.gov.au",
        "license_url": "https://creativecommons.org/licenses/by/4.0/"
    }
}

# Fallback covers (royalty-free)
COVERS = [
  "https://images.unsplash.com/photo-1521292270410-a8c4d716d518?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1531306728370-e2ebd9d7bb99?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1456926631375-92c8ce872def?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=1600&q=60"
]

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
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"

def date_today() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def find_image_from_item(it_elem, page_url: str = "") -> str:
    # enclosure
    enc = it_elem.find("enclosure")
    if enc is not None and str(enc.attrib.get("type", "")).startswith("image"):
        u = enc.attrib.get("url", "")
        if u: return u
    # media:content / media:thumbnail
    ns = {"media": "http://search.yahoo.com/mrss/"}
    m = it_elem.find("media:content", ns) or it_elem.find("media:thumbnail", ns)
    if m is not None and m.attrib.get("url"):
        return m.attrib.get("url")
    # fallback: og:image
    if page_url:
        try:
            req = urllib.request.Request(page_url, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
            m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html, re.I)
            if m: return m.group(1)
        except Exception:
            pass
    return ""

def extract_preview_paragraphs(page_url: str, max_words: int = 300) -> str:
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8", "ignore")
    except Exception:
        return ""
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]) + "…"
    return text

def extract_all_images(html: str) -> list[str]:
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)
    imgs = re.findall(r'<img[^>]+src=["\'](http[^"\']+)["\']', html, flags=re.I)
    clean = []
    for u in imgs:
        if any(x in u.lower() for x in ["sprite", "icon", "logo", "placeholder", "data:image", ".svg"]):
            continue
        clean.append(u)
    return clean[:15]

def extract_main_html(html: str) -> str:
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)
    m = re.search(r"(?is)<article[^>]*>(.*?)</article>", html)
    if m: return m.group(1)
    m = re.search(r"(?is)<main[^>]*>(.*?)</main>", html)
    if m: return m.group(1)
    body = re.search(r"(?is)<body[^>]*>(.*?)</body>", html)
    if not body: return ""
    keep = re.sub(r"(?is)</?(?!p|h2|h3|ul|ol|li|img)[a-z0-9]+[^>]*>", "", body.group(1))
    return keep

def main():
    POSTS_DIR.mkdir(exist_ok=True)
    seen = json.loads(SEEN_DB.read_text(encoding="utf-8")) if SEEN_DB.exists() else {}
    posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8")) if POSTS_JSON.exists() else []

    created = 0
    cover_i = 0

    if not FEEDS.exists():
        print("No feeds file found")
        return

    for line in FEEDS.read_text(encoding="utf-8").splitlines():
        if created >= MAX_PER_RUN:
            break
        url = line.strip()
        if not url or url.startswith("#"):
            continue

        xml = fetch(url)
        if not xml:
            print("Feed error:", url, "-> empty response")
            continue

        for it in parse(xml):
            if created >= MAX_PER_RUN:
                break

            title = it.get("title", "").strip()
            link  = it.get("link", "").strip()
            it_elem = it.get("element")
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            # Mode: FULL (PD/CC) ose PREVIEW
            dom = domain_of(link)
            is_full = dom in FULL_WHITELIST
            license_block = ""
            content_html = ""
            images = []

            if is_full:
                try:
                    req = urllib.request.Request(link, headers={"User-Agent": UA})
                    page_html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
                    content_html = extract_main_html(page_html)
                    images = extract_all_images(page_html)
                except Exception:
                    is_full = False  # fallback

            extended = extract_preview_paragraphs(link, max_words=1000 if is_full else 300)
            summary = extended or strip_html(it.get("summary", ""))

            cover = ""
            try:
                if it_elem is not None:
                    cover = find_image_from_item(it_elem, link)
            except Exception:
                cover = ""
            if not cover and images:
                cover = images[0]
            if not cover:
                cover = COVERS[cover_i % len(COVERS)]
                cover_i += 1

            if is_full:
                meta = FULL_WHITELIST[dom]
                license_block = f"""
    <div class='text-xs text-gray-500 mt-6'>
      Source: <a class='underline' href='{link}' rel='nofollow noopener' target='_blank'>{meta['attr']}</a>.
      License: <a class='underline' href='{meta['license_url']}' target='_blank'>{meta['license']}</a>.
      Attribution: {meta['attr']} – {meta['attr_url']}.
    </div>
                """

            gallery = ""
            if images:
                gallery_imgs = "".join([f"<img src='{u}' alt='image' class='w-full rounded-xl mb-4'/>" for u in images])
                gallery = f"<section class='mt-6'><h2>Images</h2>{gallery_imgs}</section>"

            body_block = f"<section class='mt-6 prose max-w-none'>{content_html}</section>" if (is_full and content_html) else f"<p>{summary}</p>"

            slug = slugify(title)[:70]
            date = date_today()

            html = f"""<!doctype html>
<html lang='en'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{title} | AventurOO</title>
<meta name='description' content='{strip_html(summary)[:150]}'>
<script src='https://cdn.tailwindcss.com'></script>
<link rel='stylesheet' href='../assets/styles.css'>
</head><body class='bg-gray-50 text-gray-900'>
<header class='bg-white border-b'><div class='max-w-5xl mx-auto px-4 py-4 flex items-center justify-between'>
<a href='../index.html' class='font-semibold'>AventurOO</a>
<nav class='text-sm flex gap-4'>
<a href='../index.html#hidden-gems' class='hover:underline'>Hidden Gems</a>
<a href='../index.html#cheap-travel' class='hover:underline'>Cheap Travel</a>
<a href='../index.html#luxury-travel' class='hover:underline'>Luxury</a>
</nav></div></header>
<main class='max-w-3xl mx-auto px-4 py-8'>
<article class='prose prose-stone max-w-none'>
<figure class='post-hero'><img src='{cover}' alt='{title} cover'></figure>
<p class='text-xs text-gray-500'>Image/source: <a class='underline' href='{link}' target='_blank' rel='nofollow noopener'>{link}</a></p>
<h1>{title}</h1>
<p class='text-sm text-gray-500'>{date} · {'Full article' if is_full else 'Aggregated Preview'}</p>
{body_block}
{gallery}
<hr/>
<p class='text-sm text-gray-600'>Original: <a class='underline' href='{link}' rel='nofollow noopener' target='_blank'>{link}</a></p>
{license_block}
<p class='text-[11px] text-gray-500 mt-2'>This page republishes or previews official travel information with proper attribution/licensing. No affiliation or endorsement implied.</p>
</article></main>
<footer class='border-t'><div class='max-w-5xl mx-auto px-4 py-6 text-sm text-gray-500'>
<a href='../index.html' class='hover:underline'>← Back to Home</a>
</div></footer></body></html>"""

            out = POSTS_DIR / f"{slug}.html"
            i = 2
            while out.exists():
                out = POSTS_DIR / f"{slug}-{i}.html"
                i += 1
            out.write_text(html, encoding="utf-8")

            entry = {
              "slug": out.stem,
              "title": title,
              "category": "News",
              "date": date,
              "excerpt": summary,
              "cover": cover
            }
            posts_idx = [entry] + posts_idx
            seen[key] = {"title": title, "file": f"posts/{out.name}", "created": date}
            created += 1
            print("Created:", out.name)

    POSTS_JSON.write_text(json.dumps(posts_idx[:200], ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("New posts:", created)

if __name__ == "__main__":
    main()