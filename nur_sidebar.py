"""Render Nur's Neat RSS headlines as a safe, static sidebar box.

Called when Kuriosity Kronicles is built in GitHub Actions. No browser fetch,
no API key, and no AI tokens are needed.
"""

from html import escape
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

FEED_URL = "https://neat.stoat.fans/feed.xml"
SITE_URL = "https://neat.stoat.fans/"


def parse_headlines(feed_xml, limit=5):
    """Extract only text headlines and safe HTTPS URLs from an RSS 2.0 feed."""
    root = ET.fromstring(feed_xml)
    headlines = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        parsed = urlsplit(link)
        if not title or parsed.scheme != "https" or not parsed.netloc:
            continue
        headlines.append((title, link))
        if len(headlines) >= limit:
            break
    return headlines


def render_nur_sidebar():
    """Fetch during the GitHub build, but never break publication on failure."""
    headlines = []
    try:
        request = Request(FEED_URL, headers={"User-Agent": "KuriosityKronicles/1.0 (RSS sidebar)"})
        with urlopen(request, timeout=8) as response:
            if response.status != 200:
                raise ValueError(f"RSS returned HTTP {response.status}")
            payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise ValueError("RSS feed exceeded 1 MB")
        headlines = parse_headlines(payload)
        print(f"Nur's Neat sidebar: loaded {len(headlines)} headlines")
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"Nur's Neat sidebar: RSS unavailable ({exc}); showing website link")

    rows = "".join(
        f'<li style="margin-bottom:7px"><a href="{escape(url, quote=True)}" '
        f'target="_blank" rel="noopener noreferrer">{escape(title)}</a></li>'
        for title, url in headlines
    )
    content = f'<ul>{rows}</ul>' if rows else '<p style="margin:0">Visit Nur’s Neat for the latest stories.</p>'
    return (
        '<div class="box"><h3>From Nur’s Neat</h3><div>'
        + content
        + f'<p style="margin:9px 0 0"><a href="{SITE_URL}" target="_blank" '
          'rel="noopener noreferrer">Visit Neat</a></p>'
        + '</div></div>'
    )
