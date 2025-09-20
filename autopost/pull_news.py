#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AventurOO – Autopost

Reads feeds in the form:
    category|subcategory|url
(also supports legacy cat|url or cat/sub|url)

• Extracts and sanitizes article HTML (trafilatura → readability → fallback text).
• Keeps roughly TARGET_WORDS words by whole paragraph/heading/blockquote/list blocks.
• Strips ads/widgets (scripts, iframes, common ad/related/newsletter blocks).
• Picks a clear cover image (largest media/proper https/proxy/fallback).
• Writes data/posts.json items with:
  {slug,title,category,subcategory,date,excerpt,cover,source,source_domain,source_name,author,rights,body}
• Applies per-(Category/Subcategory) limits.

Run:
  python3 "autopost/pull_news.py"
Env knobs (optional):
  MAX_PER_CAT, MAX_PER_FEED, MAX_TOTAL, MAX_POSTS_PERSIST, HTTP_TIMEOUT, FALLBACK_COVER, DEFAULT_AUTHOR
  IMG_TARGET_WIDTH, IMG_PROXY, FORCE_PROXY, TARGET_WORDS, HOT_MAX_ITEMS, HOT_PAGINATION_SIZE
"""

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket, sys, math
from html import unescape, escape
from html.parser import HTMLParser
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, urljoin, urlunparse, parse_qsl, urlencode
from xml.etree import ElementTree as ET
from collections import defaultdict

if __package__ in (None, ""):
    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from autopost import SEEN_DB_FILENAME
from autopost.common import limit_words_html

def _env_int(name: str, default: int) -> int:
    """Return an integer from the environment or ``default`` on failure."""

    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[WARN] Invalid {name}={raw!r}; falling back to {default}")
        return default

# ------------------ Config ------------------
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_JSON = DATA_DIR / "posts.json"
# Use your uploaded feeds file:
FEEDS = pathlib.Path(
    os.getenv("FEEDS_FILE") or (ROOT / "autopost" / "feeds_news.txt")
)

# Accept all categories by default (set CATEGORY env if you want to filter)
CATEGORY = os.getenv("CATEGORY", "").strip()
SEEN_DB = ROOT / "autopost" / SEEN_DB_FILENAME
# All autopost runs share the same "seen" store to prevent duplicates across jobs.


MAX_PER_FEED = _env_int("MAX_PER_FEED", 5)
MAX_PER_CAT = _env_int("MAX_PER_CAT", 5)
MAX_TOTAL   = _env_int("MAX_TOTAL", 0)
SUMMARY_WORDS = _env_int("SUMMARY_WORDS", 900)  # kept for compatibility
TARGET_WORDS = _env_int("TARGET_WORDS", SUMMARY_WORDS)
MAX_POSTS_PERSIST = _env_int("MAX_POSTS_PERSIST", 3000)
HTTP_TIMEOUT = _env_int("HTTP_TIMEOUT", 18)
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")
FALLBACK_COVER = os.getenv("FALLBACK_COVER", "assets/img/cover-fallback.jpg")
DEFAULT_AUTHOR = os.getenv("DEFAULT_AUTHOR", "AventurOO Editorial")
ARCHIVE_BASE_URL = os.getenv("ARCHIVE_BASE_URL", "https://archive.aventuroo.com").strip()

HOT_ENTRY_FIELDS = ("slug", "title", "date", "cover", "canonical", "excerpt", "source")
HOT_DEFAULT_PARENT_SLUG = "general"
HOT_DEFAULT_CHILD_SLUG = "index"
HOT_MAX_ITEMS = _env_int("HOT_MAX_ITEMS", 240)
HOT_PAGE_SIZE = _env_int("HOT_PAGINATION_SIZE", 12)

TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAM_NAMES = {
    "fbclid",
    "gclid",
    "dclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "oly_anon_id",
    "oly_enc_id",
    "vero_conv",
    "vero_id",
    "yclid",
    "gbraid",
    "wbraid",
}

# Image options (for cover only)
IMG_TARGET_WIDTH = int(os.getenv("IMG_TARGET_WIDTH", "1600"))
IMG_PROXY = os.getenv("IMG_PROXY", "https://images.weserv.nl/?url=")  # "" if you don’t want a proxy
FORCE_PROXY = os.getenv("FORCE_PROXY", "0")  # "1" => route every cover via proxy

try:
    # Prefer importlib so we don't crash on import-time issues in some environments.
    import importlib
    trafilatura = importlib.import_module("trafilatura")
except Exception:
    trafilatura = None
    print("[WARN] Optional package 'trafilatura' not available. Install with: pip install trafilatura")

try:
    # importlib already imported above for trafilatura; reuse it
    import importlib
    _readability_mod = importlib.import_module("readability")
    Document = getattr(_readability_mod, "Document", None)
except Exception:
    Document = None
    print("[WARN] Optional package 'readability-lxml' not available. Install with: pip install readability-lxml")

# ------------------ HTTP/HTML utils ------------------
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
    # og:image as fallback
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
        if url.startswith(("http://", "https://", "mailto:", "#", "//")):
            return f'href="{url}"'
        return f'href="{urljoin(base, url)}"'
    def rep_src(m):
        url = m.group(1)
        if url.startswith(("http://", "https://", "data:", "//")):
            return f'src="{url}"'
        return f'src="{urljoin(base, url)}"'
    html = re.sub(r'href=["\']([^"\']+)["\']', rep_href, html, flags=re.I)
    html = re.sub(r'src=["\']([^"\']+)["\']', rep_src, html, flags=re.I)
    return html
IMG_ALLOWED_ATTRS = {
    "src",
    "alt",
    "title",
    "width",
    "height",
    "srcset",
    "sizes",
    "loading",
    "decoding",
}


class _ImgTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attrs = []
        self.self_closing = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            self.attrs = attrs

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "img":
            self.attrs = attrs
            self.self_closing = True


def _sanitize_img_tag(match: re.Match) -> str:
    raw = match.group(0)
    parser = _ImgTagParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return ""

    sanitized_attrs = []
    has_src = False
    for name, value in parser.attrs:
        if not name:
            continue
        lname = name.lower()
        if lname.startswith("on"):
            continue
        if lname not in IMG_ALLOWED_ATTRS:
            continue
        value = (value or "").strip()
        if lname == "src":
            if not value:
                return ""
            lower_value = value.lower()
            if lower_value.startswith("javascript:"):
                return ""
            if lower_value.startswith("data:") and not lower_value.startswith("data:image/"):
                return ""
            has_src = True
        sanitized_attrs.append((lname, value))

    if not has_src:
        return ""

    attr_str = "".join(
        f' {name}="{escape(val, quote=True)}"'
        for name, val in sanitized_attrs
    )
    closing = " />" if parser.self_closing or raw.rstrip().endswith("/>") else ">"
    return f"<img{attr_str}{closing}"

def sanitize_article_html(html: str) -> str:
    if not html:
        return ""
    # Remove scripts/styles/iframes/noscript
    html = re.sub(r"(?is)<script.*?</script>", "", html)
    html = re.sub(r"(?is)<style.*?</style>", "", html)
    html = re.sub(r"(?is)<noscript.*?</noscript>", "", html)
    html = re.sub(r"(?is)<iframe.*?</iframe>", "", html)
    # Remove common ad/sponsored/related/newsletter blocks
    BAD = r"(share|related|promo|newsletter|advert|ads?|sponsor(ed)?|outbrain|taboola|recirculation|recommend(ed)?)"
    html = re.sub(rf'(?is)<(aside|figure|div|section)[^>]*class="[^"]*{BAD}[^"]*"[^>]*>.*?</\1>', "", html)
    html = re.sub(rf'(?is)<(div|section)[^>]*(id|data-)[^>]*{BAD}[^>]*>.*?</\1>', "", html)
    html = re.sub(r"(?is)<img\b[^>]*>", _sanitize_img_tag, html)
    return html.strip()

# ---- Link normalization helpers ----

def is_tracking_param(name: str) -> bool:
    if not name:
        return False
    lower = name.lower()
    if any(lower.startswith(prefix) for prefix in TRACKING_PARAM_PREFIXES):
        return True
    return lower in TRACKING_PARAM_NAMES


def _normalized_netloc(parsed) -> str:
    if not parsed.netloc:
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return parsed.netloc.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    try:
        port = parsed.port
    except ValueError:
        port = None
    port_str = f":{port}" if port else ""
    return f"{userinfo}{host}{port_str}"


def normalize_link(link: str) -> str:
    link = (link or "").strip()
    if not link:
        return ""
    parsed = urlparse(link)
    scheme = parsed.scheme.lower()
    netloc = _normalized_netloc(parsed)
    path = (parsed.path or "").rstrip("/")
    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_params = [
        (k, v) for k, v in query_params if not is_tracking_param(k)
    ]
    query = urlencode(filtered_params, doseq=True)
    normalized = urlunparse(
        parsed._replace(scheme=scheme, netloc=netloc, path=path, query=query)
    )
    return normalized


def link_hash(link: str) -> str:
    normalized = normalize_link(link)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

# ---- Image helpers for 'cover' ----
def guardian_upscale_url(u: str, target=IMG_TARGET_WIDTH) -> str:
    try:
        from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
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
def _remove_wp_size_suffix(u: str) -> str:
    """
    Heq sufiksin WordPress -{w}x{h} para prapashtesës, p.sh.
    example-800x600.jpg -> example.jpg
    """
    m = re.search(r'(?i)(.+?)-\d{2,4}x\d{2,4}(\.[a-z]{3,4})(\?.*)?$', u)
    if m:
        return (m.group(1) + m.group(2) + (m.group(3) or ''))
    return u

def _bump_width_query(u: str, target: int) -> str:
    """
    Nëse URL ka parametra si w, width, maxwidth, px, sz, i çon ≥ target.
    """
    try:
        pr = urlparse(u)
        q = dict(parse_qsl(pr.query, keep_blank_values=True))
        updated = False
        for k in ('w', 'width', 'maxwidth', 'px', 'sz', 's'):
            if k in q:
                try:
                    # kap numrin e parë në vlerë (p.sh. '800', '800px', etj.)
                    import re as _re
                    m = _re.search(r'\d+', str(q[k]))
                    v = int(m.group(0)) if m else 0
                except Exception:
                    v = 0
                if v < target:
                    val = str(q[k])
                    if m:
                        start, end = m.span()
                        q[k] = f"{val[:start]}{target}{val[end:]}"
                    else:
                        q[k] = str(target)
                    updated = True
        if updated:
            pr = pr._replace(query=urlencode(q))
            u = urlunparse(pr)
        return u
    except Exception:
        return u


def pick_largest_media_url(it_elem) -> str:
    if it_elem is None:
        return ""
    best_url, best_score = "", -1
    ns = {"media":"http://search.yahoo.com/mrss/"}
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
    if enc is not None and str(enc.attrib.get("type","")).startswith("image"):
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
def _bump_path_width(u: str, target: int) -> str:
    """Upgrade numeric path segments that likely encode the image width."""
    try:
        parsed = urlparse(u)
    except Exception:
        return u

    path = parsed.path or ""
    if not path:
        return u

    segments = path.split("/")
    size_keywords = {
        "img",
        "image",
        "images",
        "media",
        "thumb",
        "thumbnail",
        "resize",
        "resized",
        "size",
        "sizes",
        "standard",
        "width",
        "w",
        "crop",
        "quality",
    }
    changed = False

    for idx, seg in enumerate(segments):
        if not re.fullmatch(r"\d{2,4}", seg or ""):
            continue
        try:
            value = int(seg)
        except ValueError:
            continue
        if value >= target or value == 0:
            continue

        prev_raw = segments[idx - 1] if idx > 0 else ""
        next_raw = segments[idx + 1] if idx + 1 < len(segments) else ""
        prev_prev_raw = segments[idx - 2] if idx > 1 else ""

        if prev_raw and re.fullmatch(r"\d{4}", prev_raw):
            try:
                year_val = int(prev_raw)
            except ValueError:
                year_val = 0
            if 1900 <= year_val <= 2100 and 1 <= value <= 12:
                continue

        if (
            prev_raw
            and re.fullmatch(r"\d{2}", prev_raw)
            and prev_prev_raw
            and re.fullmatch(r"\d{4}", prev_prev_raw)
        ):
            try:
                month_val = int(prev_raw)
                year_val = int(prev_prev_raw)
            except ValueError:
                month_val = 0
                year_val = 0
            if 1900 <= year_val <= 2100 and 1 <= month_val <= 12 and 1 <= value <= 31:
                continue

        prev_seg = (prev_raw or "").lower()
        next_seg = (next_raw or "").lower()
        next_next = (
            segments[idx + 2].lower() if idx + 2 < len(segments) else ""
        )

        looks_like_size = False
        if any(key in prev_seg for key in size_keywords) or any(
            key in next_seg for key in size_keywords
        ):
            looks_like_size = True
        image_pattern = r"\.(?:jpe?g|png|gif|webp|avif)(?:\?.*)?$"
        if re.search(image_pattern, next_seg) or re.search(image_pattern, next_next):
            looks_like_size = True

        if not looks_like_size:
            continue

        segments[idx] = str(target)
        changed = True

    if not changed:
        return u

    new_path = "/".join(segments)
    if path.startswith("/") and not new_path.startswith("/"):
        new_path = "/" + new_path

    parsed = parsed._replace(path=new_path)
    return urlunparse(parsed)


def sanitize_img_url(u: str) -> str:
    """Sanitize cover URL: https → (opt.) proxy → upscale (Guardian & common CMS)."""
    u = (u or "").strip()
    if not u:
        return u
    if FORCE_PROXY == "1" and IMG_PROXY:
        u2 = u.replace("https://", "").replace("http://", "")
        return f"{IMG_PROXY}{u2}"
    u = _to_https(u)
    # Rregullime specifike
    u = guardian_upscale_url(u, target=IMG_TARGET_WIDTH)
    # Rregullime të përgjithshme (WP/Shopify/Cloudinary query width)
    u = _remove_wp_size_suffix(u)
    u = _bump_path_width(u, IMG_TARGET_WIDTH)
    u = _bump_width_query(u, IMG_TARGET_WIDTH)
    if u.startswith("http://"):
        u = _proxy_if_mixed(u)
    return u
    
def resolve_cover_url(u: str) -> str:
    """Return a sanitized HTTPS cover URL or the configured fallback."""

    sanitized = sanitize_img_url(u)
    sanitized = (sanitized or "").strip()
    if not sanitized:
        return FALLBACK_COVER

    lowered = sanitized.lower()
    if lowered.startswith("data:"):
        return FALLBACK_COVER

    if lowered.startswith("http://"):
        sanitized = _to_https(sanitized)
        lowered = sanitized.lower()

    if not lowered.startswith("https://"):
        return FALLBACK_COVER

    return sanitized
    
# ---- Body extractors ----
def extract_body_html(url: str) -> tuple[str, str]:
    """Return (body_html, first_img_in_body) trying trafilatura → readability → fallback text."""
    body_html = ""
    first_img = ""
    # 1) trafilatura
    if trafilatura is not None:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                th = trafilatura.extract(
                    downloaded,
                    output_format="html",
                    include_images=True,
                    include_links=True,
                    include_formatting=True
                )
                if th:
                    body_html = th
                    m = re.search(r'<img[^>]+src=["\'](http[^"\']+)["\']', th, flags=re.I)
                    if m:
                        first_img = m.group(1)
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
                if m:
                    first_img = m.group(1)
        except Exception as e:
            print("readability error:", e)
    # 3) Fallback total
    if not body_html:
        try:
            raw = http_get(url)
            txt = strip_text(raw)
            return f"<p>{txt}</p>", ""
        except Exception:
            return "", ""
    return body_html, first_img

def slugify(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "post"


def slugify_taxonomy(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def slug_to_label(slug: str) -> str:
    slug = (slug or "").strip()
    if not slug:
        return ""
    slug = slug.replace("_", " ").replace("-", " ")
    slug = re.sub(r"\s+", " ", slug)
    return slug.strip().title()


TAXONOMY_FILE = DATA_DIR / "taxonomy.json"
CATEGORY_TITLES: dict[str, str] = {}
SUBCATEGORY_TITLES: dict[str, dict[str, str]] = {}


def _load_taxonomy_lookup() -> None:
    CATEGORY_TITLES.clear()
    SUBCATEGORY_TITLES.clear()

    try:
        raw = TAXONOMY_FILE.read_text(encoding="utf-8")
    except OSError:
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    entries = []
    if isinstance(data, dict):
        entries = data.get("categories", [])
    elif isinstance(data, list):
        entries = data
    if not isinstance(entries, list):
        return

    def ensure_title(slug_value: str, title_value: str) -> str:
        slug_norm = slugify_taxonomy(slug_value)
        if not slug_norm:
            return ""
        clean_title = (title_value or "").strip()
        if not clean_title:
            clean_title = CATEGORY_TITLES.get(slug_norm) or slug_to_label(slug_norm)
        CATEGORY_TITLES[slug_norm] = clean_title
        return clean_title

    def register_parent_child(parent_value: str, child_value: str, child_title: str) -> None:
        parent_norm = slugify_taxonomy(parent_value)
        child_norm = slugify_taxonomy(child_value)
        if not parent_norm or not child_norm:
            return
        if parent_norm not in CATEGORY_TITLES:
            CATEGORY_TITLES[parent_norm] = slug_to_label(parent_norm)
        title_final = ensure_title(child_norm, child_title)
        if not title_final:
            title_final = slug_to_label(child_norm)
            CATEGORY_TITLES[child_norm] = title_final
        SUBCATEGORY_TITLES.setdefault(parent_norm, {})[child_norm] = title_final

    def walk(node, parent_slug: str = "") -> None:
        if not isinstance(node, dict):
            return
        slug_value = node.get("slug")
        if not slug_value:
            return
        title_value = (node.get("title") or "").strip()
        slug_norm = slugify_taxonomy(slug_value)
        if not slug_norm:
            return
        ensure_title(slug_norm, title_value)
        if parent_slug:
            register_parent_child(parent_slug, slug_norm, title_value)
        group_value = node.get("group")
        if isinstance(group_value, str):
            register_parent_child(group_value, slug_norm, title_value)
        elif isinstance(group_value, list):
            for g in group_value:
                if isinstance(g, str):
                    register_parent_child(g, slug_norm, title_value)
        subs_value = node.get("subs")
        if isinstance(subs_value, list):
            for sub_node in subs_value:
                walk(sub_node, slug_norm)

    for entry in entries:
        walk(entry)


_load_taxonomy_lookup()


def taxonomy_title_for_slug(slug: str) -> str:
    slug_norm = slugify_taxonomy(slug)
    if not slug_norm:
        return ""
    return CATEGORY_TITLES.get(slug_norm) or slug_to_label(slug_norm)


def category_label_from_slug(slug: str) -> str:
    slug = (slug or "").strip().strip("/")
    if not slug:
        return ""
    segments = [seg for seg in slug.split("/") if seg]
    if not segments:
        return ""
    cat_slug = slugify_taxonomy(segments[0])
    if not cat_slug:
        return ""
    return taxonomy_title_for_slug(cat_slug)


def subcategory_label_from_slug(slug: str, parent_slug: str = "") -> str:
    slug = (slug or "").strip().strip("/")
    if not slug:
        return ""
    segments = [seg for seg in slug.split("/") if seg]
    if not segments:
        return ""
    parent_norm = slugify_taxonomy(parent_slug)
    child_norm = slugify_taxonomy(segments[-1])
    if parent_norm and child_norm:
        label = SUBCATEGORY_TITLES.get(parent_norm, {}).get(child_norm)
        if label:
            return label
    if len(segments) > 1:
        chosen_parent = ""
        chosen_child = ""
        for idx in range(len(segments) - 1):
            candidate_parent = slugify_taxonomy(segments[idx])
            candidate_child = slugify_taxonomy(segments[idx + 1])
            if SUBCATEGORY_TITLES.get(candidate_parent, {}).get(candidate_child):
                chosen_parent = candidate_parent
                chosen_child = candidate_child
        if chosen_parent and chosen_child:
            label = SUBCATEGORY_TITLES.get(chosen_parent, {}).get(chosen_child)
            if label:
                return label
    return taxonomy_title_for_slug(child_norm)


def split_category_slug(slug: str) -> tuple[str, str]:
    slug = (slug or "").strip().strip("/")
    if not slug:
        return "", ""
    segments = [slugify_taxonomy(seg) for seg in slug.split("/") if slugify_taxonomy(seg)]
    if not segments:
        return "", ""
    cat_slug = segments[0]
    sub_slug = ""
    if len(segments) > 1:
        chosen_parent = ""
        chosen_child = ""
        for idx in range(len(segments) - 1):
            parent_candidate = segments[idx]
            child_candidate = segments[idx + 1]
            if SUBCATEGORY_TITLES.get(parent_candidate, {}).get(child_candidate):
                chosen_parent = parent_candidate
                chosen_child = child_candidate
        if chosen_parent and chosen_child:
            cat_slug = chosen_parent
            sub_slug = chosen_child
        else:
            sub_slug = segments[-1]
    return cat_slug, sub_slug


def _normalize_label_from_slug(label: str, slug: str, parent_slug: str = "") -> str:
    slug_norm = slugify_taxonomy(slug)
    label = (label or "").strip()
    if not slug_norm:
        return label
    curated = (
        subcategory_label_from_slug(slug_norm, parent_slug)
        if parent_slug
        else category_label_from_slug(slug_norm)
    )
    if curated:
        return curated
    if not label or slugify_taxonomy(label) == slug_norm:
        return slug_to_label(slug_norm)
    return label


def _normalize_post_entry(entry):
    if not isinstance(entry, dict):
        return None

    normalized = dict(entry)

    category = (normalized.get("category") or "").strip()
    subcategory = (normalized.get("subcategory") or "").strip()
    category_slug = (normalized.get("category_slug") or "").strip().strip("/")

    if category and "/" in category:
        parts = [p.strip() for p in category.split("/") if p.strip()]
        if parts:
            if len(parts) > 1 and not subcategory:
                subcategory = parts[-1]
            category = parts[0]

    derived_cat_slug = ""
    derived_sub_slug = ""
    if category_slug:
        derived_cat_slug, derived_sub_slug = split_category_slug(category_slug)

    cat_slug = derived_cat_slug or slugify_taxonomy(category)
    sub_slug = derived_sub_slug or slugify_taxonomy(subcategory)

    if not cat_slug and category:
        cat_slug = slugify_taxonomy(category)
    if not sub_slug and subcategory:
        sub_slug = slugify_taxonomy(subcategory)

    if not category and cat_slug:
        category = category_label_from_slug(cat_slug)
    if not subcategory and sub_slug:
        subcategory = subcategory_label_from_slug(sub_slug, cat_slug)

    category = _normalize_label_from_slug(category, cat_slug)
    if sub_slug:
        subcategory = _normalize_label_from_slug(subcategory, sub_slug, cat_slug)
    else:
        subcategory = (subcategory or "").strip()

    slug_parts = []
    if cat_slug:
        slug_parts.append(cat_slug)
    if sub_slug:
        slug_parts.append(sub_slug)
    category_slug = "/".join(slug_parts)

    normalized["category"] = category
    normalized["subcategory"] = subcategory
    if category_slug:
        normalized["category_slug"] = category_slug
    else:
        normalized.pop("category_slug", None)

    return normalized


def _normalize_hot_entry(entry):
    # keep this function compatible with older Python versions
    if not isinstance(entry, dict):
        return None

    slug_value = (entry.get("slug") or "").strip()
    if not slug_value:
        return None

    normalized = {"slug": slug_value}

    for key in HOT_ENTRY_FIELDS:
        if key == "slug":
            continue
        value = entry.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if key == "date":
            value = _normalize_date_string(str(value)) or today_iso()
        normalized[key] = value

    if "date" not in normalized:
        normalized["date"] = today_iso()

    return normalized


def _normalize_date_string(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value)

    dt = None

    iso_candidate = value
    if iso_candidate.endswith("Z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(iso_candidate)
    except ValueError:
        dt = None

    if dt is None:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            dt = None

    if dt is None:
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d, %Y",
            "%B %d, %Y",
        ):
            try:
                dt = datetime.datetime.strptime(value, fmt)
                break
            except ValueError:
                continue

    if dt is None:
        return ""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    return dt.astimezone(datetime.timezone.utc).date().isoformat()


def parse_item_date(it_elem) -> str:
    if it_elem is None:
        return today_iso()

    candidates = []
    def _append_candidate(value):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                candidates.append(stripped)

    for tag in ("pubDate", "published", "updated"):
        _append_candidate(it_elem.findtext(tag))

    ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
    for tag in ("published", "updated"):
        _append_candidate(it_elem.findtext(f"atom:{tag}", default="", namespaces=ns_atom))

    ns_dc = {"dc": "http://purl.org/dc/elements/1.1/"}
    _append_candidate(it_elem.findtext("dc:date", default="", namespaces=ns_dc))


    for candidate in candidates:
        normalized = _normalize_date_string(candidate)
        if normalized:
            return normalized

    return today_iso()


def _entry_sort_key(entry) -> str:
    if not isinstance(entry, dict):
        return ""
    raw = entry.get("date")
    raw_str = str(raw or "").strip()
    normalized = _normalize_date_string(raw_str)
    return normalized or raw_str


def today_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")
 
def _determine_bucket_slugs(entry: dict) -> tuple[str, str]:
    if not isinstance(entry, dict):
        return HOT_DEFAULT_PARENT_SLUG, ""

    raw_category_slug = (entry.get("category_slug") or "").strip()
    cat_slug = ""
    sub_slug = ""
    if raw_category_slug:
        cat_slug, sub_slug = split_category_slug(raw_category_slug)

    if not cat_slug:
        cat_slug = slugify_taxonomy(entry.get("category"))
    if not sub_slug:
        sub_slug = slugify_taxonomy(entry.get("subcategory"))

    cat_slug = cat_slug or HOT_DEFAULT_PARENT_SLUG
    sub_slug = sub_slug or ""
    return cat_slug, sub_slug


def _hot_bucket_path(base_dir: pathlib.Path, parent_slug: str, child_slug: str) -> pathlib.Path:
    parent = slugify_taxonomy(parent_slug) or HOT_DEFAULT_PARENT_SLUG
    child = slugify_taxonomy(child_slug) or HOT_DEFAULT_CHILD_SLUG
    if child == HOT_DEFAULT_CHILD_SLUG:
        return base_dir / "hot" / parent / "index.json"
    return base_dir / "hot" / parent / child / "index.json"


def _load_hot_entries(path: pathlib.Path):
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(raw, dict):
        raw_items = raw.get("items", [])
    elif isinstance(raw, list):
        raw_items = raw
    else:
        return []
    normalized = []
    for item in raw_items:
        normalized_item = _normalize_hot_entry(item)
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


def _calc_pages(total: int, per_page: int) -> int:
    if per_page <= 0:
        return total if total > 0 else 0
    return math.ceil(total / per_page)


def _merge_hot_entries(existing: list[dict], new_entries: list[dict], *, max_items: int) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()

    for item in new_entries + existing:
        if not isinstance(item, dict):
            continue
        slug = (item.get("slug") or "").strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        merged.append(item)

    merged.sort(key=_entry_sort_key, reverse=True)
    if max_items > 0:
        merged = merged[:max_items]
    return merged


def _update_hot_shards(
    entries: list[dict],
    *,
    base_dir: pathlib.Path,
    max_items: int,
    per_page: int,
) -> None:
    if not entries:
        return

    buckets: dict[pathlib.Path, list[dict]] = defaultdict(list)

    for entry in entries:
        parent_slug, child_slug = _determine_bucket_slugs(entry)
        hot_entry = _normalize_hot_entry(entry)
        if hot_entry is None:
            continue
        bucket_path = _hot_bucket_path(base_dir, parent_slug, child_slug)
        buckets[bucket_path].append(hot_entry)

    for path, new_items in buckets.items():
        existing_items = _load_hot_entries(path)
        merged_items = _merge_hot_entries(existing_items, new_items, max_items=max_items)
        payload = {
            "items": merged_items,
            "count": len(merged_items),
            "updated_at": today_iso(),
            "pagination": {
                "total_items": len(merged_items),
                "per_page": per_page,
                "total_pages": _calc_pages(len(merged_items), per_page),
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_archive_canonical(slug: str, parent_slug: str, child_slug: str) -> str:
    base = ARCHIVE_BASE_URL.rstrip("/")
    if not base:
        return ""

    slug_clean = (slug or "").strip().strip("/")
    parent_clean = slugify_taxonomy(parent_slug)
    child_clean = slugify_taxonomy(child_slug)

    parts = [base]
    if parent_clean:
        parts.append(parent_clean)
    if child_clean:
        parts.append(child_clean)
    if slug_clean:
        parts.append(slug_clean)

    url = "/".join(parts)
    if slug_clean:
        url += "/"
    return url
# ------------------ Main ------------------
def main():
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    SEEN_DB.parent.mkdir(exist_ok=True, parents=True)

    # seen
    if SEEN_DB.exists():
        try:
            seen = json.loads(SEEN_DB.read_text(encoding="utf-8"))
            if not isinstance(seen, dict):
                seen = {}
        except json.JSONDecodeError:
            seen = {}
    else:
        seen = {}

    # posts index
    if POSTS_JSON.exists():
        try:
            posts_idx = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
            if not isinstance(posts_idx, list):
                posts_idx = []
        except json.JSONDecodeError:
            posts_idx = []
    else:
        posts_idx = []

    # Maintain posts.json for legacy clients; hot shards are updated alongside it.

    if not FEEDS.exists():
        print("ERROR: feeds file not found:", FEEDS)
        return

    added_total = 0
    target_words = globals().get("TARGET_WORDS")
    if not isinstance(target_words, int) or target_words <= 0:
        target_words = SUMMARY_WORDS
    per_cat = {}
    per_feed_counts = {}
    new_entries = []

    current_sub_label = ""
    current_sub_slug = ""

    for raw in FEEDS.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("#"):
            # Support comments like: # === NEWS / POLITICS ===
            m = re.search(r"#\s*===\s*[^/]+/\s*(.+?)\s*===", raw, flags=re.I)
            if m:
                current_sub_label = m.group(1).strip().title()
                current_sub_slug = slugify_taxonomy(current_sub_label)
            continue

        if "|" not in raw:
            continue
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        if len(parts) < 2:
            continue

        feed_url = ""
        category_label = ""
        subcategory_label = ""
        category_slug_value = ""

        # Support: category|subcategory|url OR legacy: category|url OR category/sub|url
        if len(parts) == 3:
            category_label = parts[0]
            subcategory_label = parts[1]
            feed_url = parts[2]
        else:
            cat_str = parts[0]
            feed_url = parts[1]
            segments = [seg.strip() for seg in cat_str.split("/") if seg.strip()]
            if segments:
                category_label = segments[0]
                if len(segments) > 1:
                    subcategory_label = segments[-1]
                slug_parts = [slugify_taxonomy(seg) for seg in segments if slugify_taxonomy(seg)]
                if slug_parts:
                    category_slug_value = "/".join(slug_parts)
            else:
                category_label = cat_str

        category_label = (category_label or "").strip()
        subcategory_label = (subcategory_label or "").strip()
        feed_url = (feed_url or "").strip()
        feed_url = re.split(r"\s+#", feed_url, 1)[0].strip()
        if not feed_url:
            continue

        derived_cat_slug = ""
        derived_sub_slug = ""
        if category_slug_value:
            derived_cat_slug, derived_sub_slug = split_category_slug(category_slug_value)

        cat_slug = derived_cat_slug or slugify_taxonomy(category_label)
        sub_slug = derived_sub_slug or slugify_taxonomy(subcategory_label)

        if not subcategory_label and current_sub_label:
            subcategory_label = current_sub_label
            sub_slug = sub_slug or current_sub_slug or slugify_taxonomy(subcategory_label)

        if not category_label and cat_slug:
            category_label = category_label_from_slug(cat_slug)
        if not subcategory_label and sub_slug:
            subcategory_label = subcategory_label_from_slug(sub_slug, cat_slug)
        else:
            subcategory_label = (subcategory_label or "").strip()

        category_label = _normalize_label_from_slug(category_label, cat_slug)
        if sub_slug:
            subcategory_label = _normalize_label_from_slug(subcategory_label, sub_slug, cat_slug)
        else:
            subcategory_label = (subcategory_label or "").strip()

        slug_parts = [p for p in (cat_slug, sub_slug) if p]
        if slug_parts:
            category_slug_value = "/".join(slug_parts)
        else:
            category_slug_value = (category_slug_value or "").strip().strip("/")

        # Optional filter by env CATEGORY (leave empty to accept all)
        if CATEGORY and category_label != CATEGORY:
            continue

        print(f"[FEED] {category_label} / {subcategory_label or '-'} -> {feed_url}")
        xml = fetch_bytes(feed_url)
        per_feed_counts[feed_url] = 0
        if not xml:
            print("Feed empty:", feed_url)
            continue

        for it in parse_feed(xml):
            # enforce per-feed limit
            if MAX_PER_FEED > 0 and per_feed_counts.get(feed_url, 0) >= MAX_PER_FEED:
                break

            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break

            key_limit = category_slug_value or cat_slug or (category_label or "_")
            if per_cat.get(key_limit, 0) >= MAX_PER_CAT:
                continue

            title = (it.get("title") or "").strip()
            link = (it.get("link") or "").strip()
            if not title or not link:
                continue

            key = link_hash(link)
            if key in seen:
                continue

            # 1) Body HTML
            body_html, inner_img = extract_body_html(link)

            # Skip unavailable content (simple heuristics)
            body_text = strip_text(body_html).lower()
            if "there was an error" in body_text or "this content is not available" in body_text:
                print(f"[SKIP] {link} -> unavailable content")
                continue

            # 2) Absolutize & sanitize
            parsed = urlparse(link)
            base = f"{parsed.scheme}://{parsed.netloc}"
            body_html = absolutize(body_html, base)
            body_html = sanitize_article_html(body_html)

            # 3) Trim to target word count while keeping whole blocks when possible
            try:
                body_html = limit_words_html(body_html, target_words)
            except Exception:
                body_html = body_html or ""

            # 4) Cover image
            it_elem = it.get("element")
            cover_candidate = ""
            try:
                cover_candidate = pick_largest_media_url(it_elem) or find_cover_from_item(it_elem, link) or inner_img or ""
            except Exception:
                cover_candidate = inner_img or ""
            cover = resolve_cover_url(cover_candidate)

            # 5) Excerpt
            first_p = re.search(r"(?is)<p[^>]*>(.*?)</p>", body_html or "")
            excerpt = strip_text(first_p.group(1)) if first_p else (it.get("summary") or title)
            if isinstance(excerpt, str) and len(excerpt) > 280:
                excerpt = excerpt[:277] + "…"

            # 6) Date
            date = parse_item_date(it_elem)

            # 7) Author & rights (best-effort fallbacks)
            author = DEFAULT_AUTHOR
            rights = "Unknown"
            try:
                ns_dc = {"dc": "http://purl.org/dc/elements/1.1/"}
                c = it_elem.find("dc:creator", ns_dc) if it_elem is not None else None
                if c is not None and (c.text or "").strip():
                    author = c.text.strip()
                else:
                    a = it_elem.find("author") if it_elem is not None else None
                    if a is not None and (a.text or "").strip():
                        author = a.text.strip()
                r = it_elem.find("dc:rights", ns_dc) if it_elem is not None else None
                if r is not None and (r.text or "").strip():
                    rights = r.text.strip()
            except Exception:
                pass

            # 8) Build entry
            slug_base = slugify(f"{title}-{date}")
            entry = {
                "slug": slug_base,
                "title": title,
                "category": category_label,
                "subcategory": subcategory_label,
                "category_slug": category_slug_value or ("/".join(p for p in (cat_slug, sub_slug) if p) or ""),
                "date": date,
                "excerpt": excerpt,
                "cover": cover,
                "source": link,
                "source_domain": (urlparse(link).hostname or "").lower().replace("www.", ""),
                "source_name": category_label,
                "author": author,
                "rights": rights,
                "body": body_html,
                "canonical": _build_archive_canonical(slug_base, cat_slug, sub_slug),
            }

            # record seen and counters
            seen[key] = {"url": link, "title": title, "date": date}
            per_feed_counts[feed_url] = per_feed_counts.get(feed_url, 0) + 1
            per_cat[key_limit] = per_cat.get(key_limit, 0) + 1
            added_total += 1

            print(f"[{category_label}/{subcategory_label or '-'}] + {title}")
            new_entries.append(entry)

            if MAX_TOTAL > 0 and added_total >= MAX_TOTAL:
                break

    # Merge new entries into posts index (new first), normalize and persist
    if new_entries:
        new_norm = []
        for e in new_entries:
            ne = _normalize_post_entry(e)
            if ne is not None:
                new_norm.append(ne)

        if new_norm:
            _update_hot_shards(
                new_norm,
                base_dir=DATA_DIR,
                max_items=HOT_MAX_ITEMS,
                per_page=HOT_PAGE_SIZE,
            )

        posts_idx = new_norm + posts_idx
        posts_idx = [p for p in posts_idx if p]  # drop any None
        posts_idx.sort(key=_entry_sort_key, reverse=True)
        if MAX_POSTS_PERSIST > 0:
            posts_idx = posts_idx[:MAX_POSTS_PERSIST]

    # Persist seen and posts
    try:
        SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print("Failed to write seen DB:", exc)
    try:
        POSTS_JSON.write_text(json.dumps(posts_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print("Failed to write posts index:", exc)

    print("New posts this run:", len(new_entries))


if __name__ == "__main__":
    main()
