#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for autopost scripts."""

import os
import re
import datetime
import urllib.request
import urllib.error
import socket
from html import unescape
from urllib.parse import urljoin
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from xml.etree import ElementTree as ET

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "18"))
UA = os.getenv("AP_USER_AGENT", "Mozilla/5.0 (AventurOO Autoposter)")

try:
    import trafilatura
except Exception:
    trafilatura = None

try:
    from readability import Document
except Exception:
    Document = None


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


_BLOCK_PATTERN = re.compile(
    r"(?is)"
    r"<p[^>]*>.*?</p>|"
    r"<h2[^>]*>.*?</h2>|"
    r"<h3[^>]*>.*?</h3>|"
    r"<ul[^>]*>.*?</ul>|"
    r"<ol[^>]*>.*?</ol>|"
    r"<blockquote[^>]*>.*?</blockquote>"
)


def limit_words_html(html: str, max_words: int) -> str:
    """Return ``html`` trimmed to ``max_words`` words, keeping full blocks when possible."""

    if not html:
        return ""

    words = strip_text(html).split()
    if max_words <= 0 or len(words) <= max_words:
        return html

    blocks = _BLOCK_PATTERN.findall(html or "")
    if blocks:
        kept: list[str] = []
        word_count = 0
        truncated = False

        for block in blocks:
            block_words = strip_text(block).split()
            block_word_count = len(block_words)
            if block_word_count == 0:
                kept.append(block)
                continue
            if word_count + block_word_count > max_words:
                truncated = True
                break
            kept.append(block)
            word_count += block_word_count

        if kept:
            if truncated or len(kept) < len(blocks):
                kept.append("<p><em>…</em></p>")
            return "\n".join(kept)

    # Fallback: treat as plain text (no HTML blocks matched or first block too large)
    trimmed_words = words[:max_words]
    trimmed_text = " ".join(trimmed_words).strip()

    if "<" in html and ">" in html:
        return f"<p>{trimmed_text}…</p>"

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", html) if p.strip()]
    if paragraphs:
        kept_plain: list[str] = []
        word_count = 0
        truncated = False
        for para in paragraphs:
            para_words = para.split()
            para_word_count = len(para_words)
            if para_word_count == 0:
                continue
            if word_count + para_word_count > max_words:
                truncated = True
                break
            kept_plain.append(para)
            word_count += para_word_count
        if kept_plain:
            result = "\n\n".join(kept_plain)
            if truncated or len(kept_plain) < len(paragraphs):
                result += "\n\n…"
            return result

    return trimmed_text + "…"


def parse_feed(xml_bytes: bytes):
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    items = []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "summary": desc, "element": it})
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
    TARGET_WIDTH = 1200

    def _parse_int(val) -> int:
        try:
            return int(float(str(val).strip()))
        except (TypeError, ValueError):
            return 0

    def _upgrade_size_in_url(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return url
        try:
            parsed = urlparse(url)
        except Exception:
            return url

        # Upgrade common size query params (?width=240 → ?width=1200)
        query_changed = False
        if parsed.query:
            params = parse_qsl(parsed.query, keep_blank_values=True)
            new_params = []
            for k, v in params:
                lv = str(v)
                key = (k or "").lower()
                if key in {"width", "w"} and lv.isdigit():
                    num = int(lv)
                    if num and num < TARGET_WIDTH:
                        v = str(TARGET_WIDTH)
                        query_changed = True
                new_params.append((k, v))
            if query_changed:
                parsed = parsed._replace(query=urlencode(new_params, doseq=True))

        # Upgrade path segments like /240/ when they likely encode size.
        path = parsed.path or ""
        segments = path.split("/")
        path_changed = False
        size_keywords = {"img", "image", "images", "thumb", "thumbnail", "resize", "resized", "size", "sizes", "width", "w", "crop"}
        for idx, seg in enumerate(segments):
            if not re.fullmatch(r"\d{2,4}", seg):
                continue
            value = int(seg)
            if value >= TARGET_WIDTH or value == 0:
                continue
            prev_seg = segments[idx - 1].lower() if idx > 0 else ""
            next_seg = segments[idx + 1].lower() if idx + 1 < len(segments) else ""
            looks_like_size = False
            if any(key in prev_seg for key in size_keywords) or any(key in next_seg for key in size_keywords):
                looks_like_size = True
            if re.search(r"\.(jpe?g|png|gif|webp|avif)", next_seg):
                looks_like_size = True
            if looks_like_size:
                segments[idx] = str(TARGET_WIDTH)
                path_changed = True
        if path_changed:
            parsed = parsed._replace(path="/".join(segments))

        if not (query_changed or path_changed):
            return url
        return urlunparse(parsed)

    def _score_candidate(width: int, height: int, fallback: int = 0) -> int:
        if width and height:
            return width * height
        if width or height:
            return max(width, height)
        return fallback

    def _consider(url: str, width: int = 0, height: int = 0, fallback: int = 0):
        nonlocal best_url, best_score
        if not url:
            return
        upgraded = _upgrade_size_in_url(url)
        score = _score_candidate(width, height, fallback)
        if upgraded and score > best_score:
            best_url = upgraded
            best_score = score

    best_url, best_score = "", -1
    if it_elem is not None:
        for enc in it_elem.findall("enclosure"):
            enc_type = (enc.attrib.get("type") or "").lower()
            if enc_type and not enc_type.startswith("image"):
                continue
            url = (enc.attrib.get("url") or "").strip()
            if not url:
                continue
            w = _parse_int(enc.attrib.get("width"))
            h = _parse_int(enc.attrib.get("height"))
            size_hint = _parse_int(enc.attrib.get("length"))
            _consider(url, w, h, size_hint)

        ns = {"media": "http://search.yahoo.com/mrss/"}
        for tag in it_elem.findall(".//media:content", ns) + it_elem.findall(".//media:thumbnail", ns):
            url = (tag.attrib.get("url") or "").strip()
            if not url:
                continue
            w = _parse_int(tag.attrib.get("width"))
            h = _parse_int(tag.attrib.get("height"))
            size_hint = _parse_int(tag.attrib.get("fileSize")) or _parse_int(tag.attrib.get("filesize"))
            _consider(url, w, h, size_hint)

    if best_url:
        return best_url

    if page_url:
        try:
            html = http_get(page_url)
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if m:
                return _upgrade_size_in_url(m.group(1))
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


def sanitize_article_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"(?is)<script.*?</script>", "", html)
    html = re.sub(r"(?is)<style.*?</style>", "", html)
    html = re.sub(r"(?is)<noscript.*?</noscript>", "", html)
    html = re.sub(r"(?is)<iframe.*?</iframe>", "", html)
    html = re.sub(r'(?is)<(aside|figure)[^>]*class="[^"]*(share|related|promo|newsletter)[^"]*"[^>]*>.*?</\1>', "", html)
    return html.strip()

def extract_body_html(url: str) -> tuple[str, str]:
    body_html = ""
    first_img = ""
    if trafilatura is not None:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                th = trafilatura.extract(
                    downloaded,
                    output_format="html",
                    include_images=True,
                    include_links=True,
                    include_formatting=True,
                )
                if th:
                    body_html = th
                    m = re.search(r'<img[^>]+src=["\'](http[^"\']+)["\']', th, flags=re.I)
                    if m:
                        first_img = m.group(1)
        except Exception as e:
            print("trafilatura error:", e)
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
