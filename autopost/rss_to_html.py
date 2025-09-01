#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RSS → data/posts.json for AventurOO
# - outputs only JSON (no standalone HTML pages)
# - supports category per feed line: "category|http://feed-url"
# - safe, skip duplicates, light image picking

import os, re, json, hashlib, datetime, pathlib, urllib.request, urllib.error, socket
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
POSTS_JSON = DATA_DIR / "posts.json"
SEEN_DB = ROOT / "autopost" / "seen.json"
FEEDS = ROOT / "autopost" / "data" / "feeds.txt"

# sa postime të reja për ekzekutim
MAX_PER_RUN = 3
HTTP_TIMEOUT = 15
UA = "Mozilla/5.0 (AventurOO Autoposter)"

# fallback covers (royalty-free)
COVERS = [
  "https://images.unsplash.com/photo-1521292270410-a8c4d716d518?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1531306728370-e2ebd9d7bb99?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1456926631375-92c8ce872def?auto=format&fit=crop&w=1600&q=60",
  "https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=1600&q=60"
]

# ---- helpers ----
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
    pub  = (it.findtext("pubDate") or "").strip()
    if title and link:
      items.append({"title": title, "link": link, "summary": desc, "pub": pub, "element": it})
  # Atom
  ns = {"atom": "http://www.w3.org/2005/Atom"}
  for e in root.findall(".//atom:entry", ns):
    title = (e.findtext("atom:title", default="") or "").strip()
    link_el = e.find("atom:link[@rel='alternate']", ns) or e.find("atom:link", ns)
    link = (link_el.attrib.get("href") if link_el is not None else "").strip()
    summary = (e.findtext("atom:summary", default="") or e.findtext("atom:content", default="") or "").strip()
    pub = (e.findtext("atom:updated", default="") or e.findtext("atom:published", default="")).strip()
    if title and link:
      items.append({"title": title, "link": link, "summary": summary, "pub": pub, "element": e})
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

def iso_today() -> str:
  return datetime.datetime.utcnow().strftime("%Y-%m-%d")

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
  # og:image si fallback i fundit (mund të dështojë, prandaj e lëmë opsional)
  try:
    if page_url:
      req = urllib.request.Request(page_url, headers={"User-Agent": UA})
      html = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("utf-8","ignore")
      m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
      if m: return m.group(1)
  except Exception:
    pass
  return ""

# ---- main ----
def main():
  seen = json.loads(SEEN_DB.read_text(encoding="utf-8")) if SEEN_DB.exists() else {}
  posts = json.loads(POSTS_JSON.read_text(encoding="utf-8")) if POSTS_JSON.exists() else []

  created = 0
  cover_i = 0

  if not FEEDS.exists():
    print("No feeds file found at", FEEDS)
    return

  # formati i rreshtit: "category|URL" (p.sh. travel|https://site.com/feed)
  lines = [l.strip() for l in FEEDS.read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]

  for line in lines:
    if created >= MAX_PER_RUN:
      break
    if "|" in line:
      category, url = [p.strip() for p in line.split("|", 1)]
    else:
      # default nëse mungon kateg.: e përdorim "Travel"
      category, url = "Travel", line

    xml = fetch(url)
    if not xml:
      print("Feed error:", url, "-> empty")
      continue

    for it in parse(xml):
      if created >= MAX_PER_RUN:
        break

      title = it.get("title","").strip()
      link  = it.get("link","").strip()
      if not title or not link: 
        continue

      key = hashlib.sha1(link.encode("utf-8")).hexdigest()
      if key in seen:
        continue

      # përmbledhje e shkurtër
      summary = strip_html(it.get("summary",""))
      if len(summary) > 260:
        summary = summary[:257] + "…"

      # imazhi
      cover = ""
      try:
        elem = it.get("element")
        if elem is not None:
          cover = find_image_from_item(elem, link)
      except Exception:
        cover = ""
      if not cover:
        cover = COVERS[cover_i % len(COVERS)]
        cover_i += 1

      # data (po mbajmë ISO YYYY-MM-DD – faqet tua e shfaqin si string)
      date = iso_today()

      # slug unik (nëse ka konflikt, shto sufiks sipas hash-it)
      base = slugify(title)[:70] or "post"
      slug = base
      if any(p.get("slug") == slug for p in posts):
        slug = f"{base}-{key[:6]}"

      entry = {
        "slug": slug,
        "title": title,
        "category": category.capitalize(),
        "date": date,
        "excerpt": summary,
        "cover": cover
      }

      # fut të renë në fillim të listës
      posts = [entry] + posts
      # ruaj shenjën që e pamë
      seen[key] = {"title": title, "created": date, "category": category}

      created += 1
      print("Added:", title, "->", slug)

  # ruaj max 200 postime
  POSTS_JSON.write_text(json.dumps(posts[:200], ensure_ascii=False, indent=2), encoding="utf-8")
  SEEN_DB.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
  print("New posts this run:", created)

if __name__ == "__main__":
  main()