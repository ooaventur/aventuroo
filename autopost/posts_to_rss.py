#!/usr/bin/env python3
"""Generate rss.xml from data/posts.json"""

import json
import datetime
import xml.etree.ElementTree as ET
ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
ET.register_namespace("media", "http://search.yahoo.com/mrss/")

BASE_URL = "https://aventuroo.netlify.app"
RSS_FILE = "rss.xml"
POSTS_FILE = "data/posts.json"


def format_date(date_str: str) -> str:
    """Return RFC 822 formatted date for RSS."""
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%a, %d %b %Y 00:00:00 GMT")
    except Exception:
        return date_str


def load_posts(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    posts = load_posts(POSTS_FILE)
    tree = ET.parse(RSS_FILE)
    root = tree.getroot()
    root.set("xmlns:media", "http://search.yahoo.com/mrss/")
    channel = root.find("channel")
    if channel is None:
        raise SystemExit("No <channel> element found in rss.xml")

    # remove existing items
    for item in channel.findall("item"):
        channel.remove(item)

    for p in posts:
        slug = p.get("slug", "")
        title = p.get("title", "")
        date = p.get("date", "")
        desc = p.get("excerpt", "")
        link = f"{BASE_URL}/article.html?slug={slug}"

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link
        guid = ET.SubElement(item, "guid")
        guid.set("isPermaLink", "false")
        guid.text = slug
        ET.SubElement(item, "pubDate").text = format_date(date)
        ET.SubElement(item, "description").text = desc

    # prettify
    ET.indent(tree, space="  ")
    tree.write(RSS_FILE, encoding="utf-8", xml_declaration=True)
    with open(RSS_FILE, "a", encoding="utf-8") as f:
        f.write("\n")


if __name__ == "__main__":
    main()
