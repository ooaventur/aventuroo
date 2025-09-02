#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AventurOO – Autopost (Lifestyle)
- Lexon vetem rreshtat "Lifestyle|<RSS>" nga autopost/data/feeds.txt
- Nxjerr trupin e artikullit si HTML te paster (paragrafe, bold, linke, imazhe)
- Preferon trafilatura (HTML), pastaj fallback readability-lxml
- Absolutizon URL-t relative te <a> dhe <img>
- Heq script/style/iframes/embed te panevojshem
- Shton linkun e burimit ne fund
- Shkruan ne data/posts.json: {slug,title,category,date,excerpt,cover,source,author,body}
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse, urljoin
from xml.etree import ElementTree as ET
import ssl, time
import certifi

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

MAX_PER_CAT = int(os.getenv("MAX_PER_CAT", "6"))
MAX_TOTAL   = int(os.getenv("MAX_TOTAL", "0"))
SUMMARY_WORDS = int(os.getenv("SUMMARY_WORDS", "1000"))
MAX_POSTS_PERSIST = int(os.getenv("MAX_POSTS_PERSIST", "200"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "18"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")
DEFAULT_AUTHOR = os.getenv("DEFAULT_AUTHOR", "AventurOO Editorial")

# LOG: kalova në .txt që të mos bllokohet nga .gitignore (*.log)
DEBUG_LOG = (DATA_DIR / "debug_lifestyle.txt")
def dlog(msg: str):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    try:
        DATA_DIR.mkdir(exist_ok=True)
        with DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

try:
    import trafilatura
except Exception:
    trafilatura = None

try:
    from readability import Document
except Exception:
    Document = None

# -------------------- fetch_bytes --------------------
def fetch_bytes(url: str, timeout: int | None = None, retries: int = 3) -> bytes:
    """
    Merr bytes nga URL me headers dhe retry/backoff.
    Kthen b"" nëse dështon pas retry-ve (që feed-i të anashkalohet).
    """
    timeout = timeout or HTTP_TIMEOUT
    headers = {
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, text/html;q=0.7, */*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }
    ctx = ssl.create_default_context(cafile=certifi.where())
    backoff = 1.0

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.read()

        except urllib.error.HTTPError as e:
            dlog(f"[fetch_bytes][HTTP {e.code}] {url}")
            if e.code == 403 and "Chrome" not in headers["User-Agent"]:
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
                time.sleep(1.0); continue
            if 500 <= e.code < 600 and attempt < retries:
                time.sleep(backoff); backoff = min(backoff * 2, 8.0); continue
            return b""

        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            dlog(f"[fetch_bytes][NET] {url} -> {e}")
            if attempt < retries:
                time.sleep(backoff); backoff = min(backoff * 2, 8.0); continue
            return b""

        except Exception as e:
            dlog(f"[fetch_bytes][ERR] {url} -> {e}")
            return b""

    return b""
# ----------------------------------------------------

# -------------------- parse_feed --------------------
def parse_feed(xml_bytes: bytes):
    """
    Pranon RSS/Atom (bytes) dhe kthen listë item-esh:
    {title, link, summary, element}
    """
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        dlog(f"[parse_feed][XML_PARSE_ERR] {e}")
        return out

    tag = root.tag.lower()

    # RSS: <rss><channel><item>...</item></channel></rss>
    if "rss" in tag or root.find("./channel") is not None:
        channel = root.find("./channel") or root
        for item in channel.findall("./item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not link:
                # disa RSS përdorin <guid isPermaLink="true">
                guid = item.findtext("guid") or ""
                if "://" in guid:
                    link = guid.strip()
            summary = (item.findtext("description") or "").strip()
            out.append({"title": title, "link": link, "summary": summary, "element": item})
        return out

    # Atom: <feed><entry>...</entry></feed>
    # namespaces të zakonshme
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//a:entry", ns) or root.findall(".//entry")
    if entries:
        for entry in entries:
            title = (entry.findtext("a:title", namespaces=ns) or entry.findtext("title") or "").strip()
            link_el = entry.find("a:link[@rel='alternate']", ns) or entry.find("a:link", ns) or entry.find("link")
            link = ""
            if link_el is not None:
                link = (link_el.get("href") or link_el.text or "").strip()
            summary = (entry.findtext("a:summary", namespaces=ns) or entry.findtext("summary") or
                       entry.findtext("a:content", namespaces=ns) or entry.findtext("content") or "").strip()
            out.append({"title": title, "link": link, "summary": summary, "element": entry})
        return out

    # Fallback: kërko <item> ose <entry> pa u bazuar te rrënja
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        summary = (item.findtext("description") or "").strip()
        out.append({"title": title, "link": link, "summary": summary, "element": item})
    if out:
        return out

    for entry in root.findall(".//entry"):
        title = (entry.findtext("title") or "").strip()
        link_el = entry.find("link")
        link = (link_el.get("href") if link_el is not None else (link_el.text if link_el is not None else "")) or ""
        summary = (entry.findtext("summary") or entry.findtext("content") or "").strip()
        out.append({"title": title, "link": link, "summary": summary, "element": entry})

    return out
# ----------------------------------------------------

# ... (funksionet e tjera mbeten te pandryshuara) ...

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
        if not raw or raw.startswith("#"): continue
        if "|" not in raw: continue
        cat, url = raw.split("|", 1)
        category = (cat or "").strip().title()
        feed_url = (url or "").strip()
        if category != "Lifestyle" or not feed_url:
            continue

        if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
            dlog(f"[SKIP][MAX_TOTAL_REACHED]")
            break

        dlog(f"[FEED] {feed_url}")
        try:
            xml = fetch_bytes(feed_url)
        except Exception as e:
            dlog(f"[FEED][FAIL] {feed_url} -> {e}")
            continue
        if not xml:
            dlog(f"[FEED][SKIP_EMPTY] {feed_url}")
            continue

        for it in parse_feed(xml):
            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                dlog(f"[SKIP][MAX_TOTAL] {feed_url}")
                break
            if per_cat.get(category, 0) >= MAX_PER_CAT:
                dlog(f"[SKIP][PER_CAT_CAP] {category} {feed_url}")
                continue

            title = (it.get("title") or "").strip()
            link  = (it.get("link") or "").strip()
            if not title or not link:
                dlog(f"[SKIP][MISSING] title/link -> {feed_url}")
                continue

            key = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if key in seen:
                dlog(f"[SKIP][SEEN] {title} -> {link}")
                continue

            # body html
            body_html, inner_img = extract_body_html(link)
            base = f"{urlparse(link).scheme}://{urlparse(link).netloc}"
            body_html = absolutize(body_html, base)
            body_html = sanitize_article_html(body_html)
            body_html = limit_words_html(body_html, SUMMARY_WORDS)

            # cover
            cover = find_cover_from_item(it.get("element"), link) or inner_img or FALLBACK_COVER

            # excerpt
            first_p = re.search(r"(?is)<p[^>]*>(.*?)</p>", body_html or "")
            excerpt = strip_text(first_p.group(1)) if first_p else (it.get("summary") or title)
            if len(excerpt) > 280:
                excerpt = excerpt[:277] + "…"

            # footer i burimit
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
                "body": body_final
            }
            new_entries.append(entry)

            seen[key] = {"title": title, "url": link, "category": category, "created": date}
            per_cat[category] = per_cat.get(category, 0) + 1
            added_total += 1
            dlog(f"[ADD] {title} -> {link}")

    if not new_entries:
        print("New posts this run: 0")
        dlog(f"[SUMMARY] new=0 total_seen={len(seen)} per_cat={per_cat}")
        dlog(f"[LOG] Shiko {DEBUG_LOG} për detaje.")
        return

    posts_idx = new_entries + posts_idx
    if MAX_POSTS_PERSIST > 0:
        posts_idx = posts_idx[:MAX_POSTS_PERSIST]

    POSTS_JSON.write_text(json.dumps(posts_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("New posts this run:", len(new_entries))
    dlog(f"[SUMMARY] new={len(new_entries)} total_seen={len(seen)} per_cat={per_cat}")
    dlog(f"[LOG] Shiko {DEBUG_LOG} për detaje.")

if __name__ == "__main__":
    main()