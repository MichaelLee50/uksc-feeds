
#!/usr/bin/env python3
"""
Generates two RSS feeds for the UK Supreme Court:
 - latest-judgments.xml
 - future-judgments.xml

Sources (live, non-test):
- Latest judgments page: https://www.supremecourt.uk/news/latest-judgments
- News hub (for Future judgments category): https://www.supremecourt.uk/news

Notes:
- We avoid the Azure 'test' domain. The Court’s email signup only covers general
  News and doesn’t filter to judgments, hence these custom feeds. Sources:
  https://www.supremecourt.uk/news (updates) and the Latest judgments page above.  # [2](https://www.supremecourt.gov/oral_arguments/argument_audio.aspx)[1](https://repository.law.uic.edu/abapreview/announcements.html)
"""

import datetime as dt
import hashlib
import re
import sys
from typing import List, Dict, Tuple
import requests
from bs4 import BeautifulSoup

BASE = "https://www.supremecourt.uk"
NOW = dt.datetime.utcnow()

HEADERS = {
    "User-Agent": "uksc-feeds/1.0 (+https://github.com/your-org/uksc-feeds)"
}

def fetch(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    # Try lxml first for robustness
    return BeautifulSoup(r.text, "lxml")

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def build_rss(items: List[Dict], title: str, feed_link: str, site_link: str, description: str) -> str:
    """
    Build simple RSS 2.0 XML.
    Items must have: title, link, pubDate (RFC 2822), guid, description.
    """
    rss_items = []
    for it in items:
        rss_items.append(f"""
  <item>
    <title>{escape_xml(it['title'])}</title>
    <link>{escape_xml(it['link'])}</link>
    <guid isPermaLink="false">{escape_xml(it['guid'])}</guid>
    <pubDate>{escape_xml(it['pubDate'])}</pubDate>
    <description><![CDATA[{it['description']}]]></description>
  </item>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{escape_xml(title)}</title>
  <link>{escape_xml(site_link)}</link>
  <description>{escape_xml(description)}</description>
  <lastBuildDate>{NOW.strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
  <docs>https://validator.w3.org/feed/docs/rss2.html</docs>
  <generator>uksc-feeds</generator>
  {''.join(rss_items)}
</channel>
</rss>"""
    return xml.strip()

def escape_xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def rfc2822(dt_obj: dt.datetime) -> str:
    return dt_obj.strftime("%a, %d %b %Y %H:%M:%S +0000")

def hash_guid(*parts: Tuple[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
    return h.hexdigest()

def parse_latest_judgments() -> List[Dict]:
    """
    Scrape https://www.supremecourt.uk/news/latest-judgments
    The page lists the most recent 'Latest judgments' post(s). We’ll extract:
    - Item title
    - Link to the post
    - Date on the card
    - Short description (category label and any summary text)
    """
    url = f"{BASE}/news/latest-judgments"
    soup = fetch(url)
    # Cards are typically within article/list elements. Select generously:
    cards = soup.select("article, li, div.card, .grid .card")
    items = []
    seen = set()

    for c in cards:
        # Find anchor
        a = c.select_one("a[href]")
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            href = BASE + href

        title = norm_space(a.get_text())
        # Date: find time or date in the card
        date_el = c.select_one("time, .date, .meta time")
        date_txt = norm_space(date_el.get_text()) if date_el else ""
        # Fallback: look for a date pattern in text
        if not date_txt:
            text = norm_space(c.get_text())
            m = re.search(r"(\d{1,2}\s+\w+\s+\d{4})", text)
            date_txt = m.group(1) if m else ""

        # Parse date if possible
        pub = NOW
        try:
            # Accept formats like "15 January 2026"
            pub = dt.datetime.strptime(date_txt, "%d %B %Y")
        except Exception:
            pass

        # Description: category label or brief text
        cat = c.select_one(".category, .meta, .tags")
        desc = norm_space(cat.get_text()) if cat else "Latest judgments"
        if not title:
            # Use a fallback title from context
            title = "Latest judgments"

        guid = hash_guid(href, title, date_txt)
        if guid in seen:
            continue
        seen.add(guid)

        items.append({
            "title": title,
            "link": href,
            "guid": guid,
            "pubDate": rfc2822(pub if isinstance(pub, dt.datetime) else NOW),
            "description": desc
        })

    # keep most recent 25
    return items[:25]

def parse_future_judgments() -> List[Dict]:
    """
    Scrape https://www.supremecourt.uk/news and filter items tagged 'Future judgments'.
    The Court’s live News feed is updated regularly and includes a 'Future judgments' category.  # [2](https://www.supremecourt.gov/oral_arguments/argument_audio.aspx)
    """
    url = f"{BASE}/news"
    soup = fetch(url)
    cards = soup.select("article, li, div.card, .grid .card")
    items = []
    seen = set()

    for c in cards:
        # Look for a category tag that mentions 'Future judgments'
        cat_text = norm_space(c.get_text()).lower()
        if "future judgments" not in cat_text:
            continue

        a = c.select_one("a[href]")
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            href = BASE + href

        title = norm_space(a.get_text()) or "Future judgments"
        # Extract date
        date_el = c.select_one("time, .date, .meta time")
        date_txt = norm_space(date_el.get_text()) if date_el else ""
        pub = NOW
        try:
            pub = dt.datetime.strptime(date_txt, "%d %B %Y")
        except Exception:
            pass

        desc = "Future judgments"
        cat = c.select_one(".category, .meta, .tags")
        if cat:
            desc = norm_space(cat.get_text())

        guid = hash_guid(href, title, date_txt)
        if guid in seen:
            continue
        seen.add(guid)

        items.append({
            "title": title,
            "link": href,
            "guid": guid,
            "pubDate": rfc2822(pub if isinstance(pub, dt.datetime) else NOW),
            "description": desc
        })

    return items[:25]

def write_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    latest = parse_latest_judgments()
    future = parse_future_judgments()

    latest_xml = build_rss(
        latest,
        title="UK Supreme Court – Latest judgments",
        feed_link="latest-judgments.xml",
        site_link=f"{BASE}/news/latest-judgments",
        description="Auto-generated RSS of the Supreme Court's 'Latest judgments' updates.",
    )
    future_xml = build_rss(
        future,
        title="UK Supreme Court – Future judgments",
        feed_link="future-judgments.xml",
        site_link=f"{BASE}/news",
        description="Auto-generated RSS of the Supreme Court's 'Future judgments' updates.",
    )

    write_file("latest-judgments.xml", latest_xml)
    write_file("future-judgments.xml", future_xml)
    print(f"Wrote latest-judgments.xml ({len(latest)} items)")
    print(f"Wrote future-judgments.xml ({len(future)} items)")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
