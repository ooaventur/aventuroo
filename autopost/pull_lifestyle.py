#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AventurOO – Autopost (Lifestyle)
- Lexon vetem rreshtat "Lifestyle|<RSS>" nga autopost/data/feeds.txt
- Nxjerr trupin e artikullit si HTML te paster (paragrafe, bold, linke, pa imazhe)
- Preferon trafilatura (HTML), pastaj fallback readability-lxml
- Absolutizon URL-t relative te <a> dhe <img> (edhe pse <img> hiqen me pas)
- Heq script/style/iframes/embed te panevojshem
- Rrit cilësinë e imazheve (srcset → më i madhi, Guardian width=1600) vetëm për 'cover'
- Zgjidh 'mixed content' me https ose proxy opsional për 'cover'
- Shton linkun e burimit ne fund
- Shkruan ne data/posts.json: {slug,title,category,date,excerpt,cover,source,author,body}
"""

import os, re, json, hashlib, pathlib
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

from autopost.common import (
    fetch_bytes,
    strip_text,
    parse_feed,
    find_cover_from_item,
    absolutize,
    sanitize_article_html,
    limit_words_html,
    extract_body_html,
    slugify,
    today_iso,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

CATEGORY = "Lifestyle"
SEEN_DB = ROOT / "autopost" / f"seen_{CATEGORY.lower()}.json"

MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL   = int(os.getenv("MAX_TOTAL", "0"))
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "1000"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")
DEFAULT_AUTHOR = os.getenv("DEFAULT_AUTHOR", "AventurOO Editorial")

IMG_TARGET_WIDTH = int(os.getenv("IMG_TARGET_WIDTH", "1600"))
IMG_PROXY = os.getenv("IMG_PROXY", "https://images.weserv.nl/?url=")
FORCE_PROXY = os.getenv("FORCE_PROXY", "0")


def guardian_upscale_url(u: str, target=IMG_TARGET_WIDTH) -> str:
    try:
        pr = urlparse(u)
        if "i.guim.co.uk" not in pr.netloc:
            return u
        q = dict(parse_qsl(pr.query, keep_blank_values=True))
        q["width"] = str(max(int(q.get("width", "0") or 0), target))
        q.setdefault("quality", "85")
        q.setdefault("auto", "format")
        q.setdefault("fit", "max")
        pr = pr._replace(query=urlencode(q))
        return urlunparse(pr)
    except Exception:
        return u


def pick_largest_media_url(it_elem) -> str:
    if it_elem is None:
        return ""
    best_url, best_score = "", -1
    ns = {"media": "http://search.yahoo.com/mrss/"}
    for tag in it_elem.findall(".//media:content", ns) + it_elem.findall(".//media:thumbnail", ns):
        u = (tag.attrib.get("url") or "").strip()
        if not u:
            continue
        w = int(tag.attrib.get("width", "0") or 0)
        h = int(tag.attrib.get("height", "0") or 0)
        score = (w*h) if (w and h) else w or h or 0
        if score > best_score:
            best_url, best_score = u, score
    enc = it_elem.find("enclosure")
    if enc is not None and str(enc.attrib.get("type", "")).startswith("image"):
        u = (enc.attrib.get("url") or "").strip()
        if u and best_score < 0:
            best_url = u
    return best_url or ""


def _to_https(u: str) -> str:
    if not u:
        return u
    u = u.strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http://"):
        return "https://" + u[len("http://"):]
    return u


def _proxy_if_mixed(u: str) -> str:
    if not u:
        return u
    if u.startswith("http://") and IMG_PROXY:
        base = u[len("http://"):]
        return f"{IMG_PROXY}{base}"
    return u


def sanitize_img_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return u
    if FORCE_PROXY == "1" and IMG_PROXY:
        u2 = u.replace("https://", "").replace("http://", "")
        return f"{IMG_PROXY}{u2}"
    u = _to_https(u)
    u = guardian_upscale_url(u)
    if u.startswith("http://"):
        u = _proxy_if_mixed(u)
    return u


def main():
    DATA_DIR.mkdir(exist_ok=True)

    if SEEN_DB.exists():
        try:
            seen = json.loads(SEEN_DB.read_text(encoding="utf-8"))
            if not isinstance(seen, dict):
                seen = {}
        except json.JSONDecodeError:
            seen = {}
    else:
        seen = {}

    if POSTS_JSON.exists():
        try:
            posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
            if not isinstance(posts_idx, list):
                posts_idx = []
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
@@ -341,98 +166,88 @@ def main():

        if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
            break

        print(f"[FEED] {feed_url}")
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
            link  = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                continue

            body_html, inner_img = extract_body_html(link)

            parsed = urlparse(link)
            base = f"{parsed.scheme}://{parsed.netloc}"
            body_html = absolutize(body_html, base)
            body_html = sanitize_article_html(body_html)
            body_html = limit_words_html(body_html, SUMMARY_WORDS)

            cover = (
                pick_largest_media_url(it.get("element"))
                or find_cover_from_item(it.get("element"), link)
                or inner_img
                or FALLBACK_COVER
            )
            cover = sanitize_img_url(cover)

            first_p = re.search(r"(?is)<p[^>]*>(.*?)</p>", body_html or "")
            excerpt = strip_text(first_p.group(1)) if first_p else (it.get("summary") or title)
            if len(excerpt) > 280:
                excerpt = excerpt[:277] + "…"

            body_html = re.sub(r'<img\b[^>]*>', '', body_html or "", flags=re.I)

            body_final = (body_html or "") + f"""
<p class="small text-muted mt-4">
  Source: <a href="{link}" target="_blank" rel="nofollow noopener">Read the full article</a>
</p>"""

            date = today_iso()
            slug = slugify(title)[:70]

            entry = {
                "slug": slug,
                "title": title,
                "category": category,
                "date": date,
                "excerpt": excerpt,
                "cover": cover,
                "source": link,
                "author": DEFAULT_AUTHOR,
                "body": body_final,
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": category, "created": date}
            per_cat[category] = per_cat.get(category, 0) + 1
            added_total += 1
            print(f"[{CATEGORY}] + {title}")

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

