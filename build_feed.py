#!/usr/bin/env python3
"""Build feed.xml from items.json. Standard library only.

items.json is a list of objects, newest first:
  {
    "id":        "stable unique id (usually the link)",
    "title":     "Item title",
    "link":      "https://...",
    "source":    "Wikipedia",
    "category":  "Birds",
    "dept":      "from the clever-girl dept. (optional)",
    "reasoning": "Why this was picked (2-3 sentences).",
    "summary":   "What it is, in a few sentences.",
    "image":     "https://... (optional)",
    "added":     "2026-11-10T07:00:00-06:00"
  }
"""
import html
import json
import sys
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path

# The GitHub workflow uses Python isolated mode (-I). Explicitly add only this repo.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))

from xml.sax.saxutils import escape

from site_config import SITE_TITLE, SITE_URL, FEED_URL, DESCRIPTION

ROOT = Path(__file__).resolve().parent
MAX_ITEMS = 200            # items kept in the feed; older ones move to archive/
ARCHIVE_DIR = ROOT / "archive"


def item_html(it):
    parts = []
    if it.get("dept"):
        parts.append(f"<p><small>{html.escape(it['dept'])}</small></p>")
    if it.get("reasoning"):
        parts.append(f"<p><em>{html.escape(it['reasoning'])}</em></p>")
    if it.get("image"):
        parts.append(f'<p><img src="{html.escape(it["image"], quote=True)}" alt=""></p>')
    if it.get("summary"):
        parts.append(f"<p>{html.escape(it['summary'])}</p>")
    meta = " · ".join(x for x in (it.get("category"), it.get("source"),
                                  f"submitted by {it['submitted_by']}" if it.get("submitted_by") else None) if x)
    link = html.escape(it["link"], quote=True)
    parts.append(f'<p><a href="{link}">Read it</a>{" · " + html.escape(meta) if meta else ""}</p>')
    return "\n".join(parts)


def archive(overflow):
    """Move items that fell off the feed into archive/YYYY-MM.json (never deleted)."""
    if not overflow:
        return 0
    ARCHIVE_DIR.mkdir(exist_ok=True)
    by_month = {}
    for it in overflow:
        if it.get("category") == "Meta":
            continue
        by_month.setdefault(it["added"][:7], []).append(it)
    moved = 0
    for month, batch in by_month.items():
        path = ARCHIVE_DIR / f"{month}.json"
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        have = {e["id"] for e in existing}
        new = [it for it in batch if it["id"] not in have]
        merged = sorted(existing + new, key=lambda it: it["added"], reverse=True)
        path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        moved += len(new)
    return moved


def main():
    items = json.loads((ROOT / "items.json").read_text(encoding="utf-8"))
    seen_ids = set()
    clean = []
    for it in items:
        for key in ("id", "title", "link", "added"):
            if not it.get(key):
                sys.exit(f"item missing '{key}': {it}")
        if it["id"] in seen_ids:
            continue
        seen_ids.add(it["id"])
        datetime.fromisoformat(it["added"])  # validates the timestamp
        clean.append(it)

    clean.sort(key=lambda it: datetime.fromisoformat(it["added"]), reverse=True)
    archived = archive(clean[MAX_ITEMS:])
    if archived:
        print(f"moved {archived} older item(s) into archive/")
    clean = clean[:MAX_ITEMS]
    (ROOT / "items.json").write_text(
        json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    now = format_datetime(datetime.now().astimezone())
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
        'xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{escape(SITE_TITLE)}</title>",
        f"<link>{SITE_URL}</link>",
        f"<description>{escape(DESCRIPTION)}</description>",
        f'<atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
        f"<lastBuildDate>{now}</lastBuildDate>",
        f"<image><url>{SITE_URL}favicon.svg</url><title>{escape(SITE_TITLE)}</title><link>{SITE_URL}</link></image>",
    ]
    for it in clean:
        pub = format_datetime(datetime.fromisoformat(it["added"]))
        body = item_html(it).replace("]]>", "]]&gt;")
        out += [
            "<item>",
            f"<title>{escape(it['title'])}</title>",
            f"<link>{escape(it['link'])}</link>",
            f'<guid isPermaLink="false">{escape(it["id"])}</guid>',
            f"<pubDate>{pub}</pubDate>",
        ]
        if it.get("category"):
            out.append(f"<category>{escape(it['category'])}</category>")
        if it.get("summary") or it.get("reasoning"):
            out.append(f"<description>{escape(it.get('reasoning') or it.get('summary'))}</description>")
        out += [f"<content:encoded><![CDATA[{body}]]></content:encoded>", "</item>"]
    out += ["</channel>", "</rss>", ""]
    (ROOT / "feed.xml").write_text("\n".join(out), encoding="utf-8")
    print(f"feed.xml written with {len(clean)} items")

    import build_site
    build_site.build(clean)


if __name__ == "__main__":
    main()
