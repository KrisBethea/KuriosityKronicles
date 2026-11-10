#!/usr/bin/env python3
"""Check the items the curator just added. Standard library only, no AI.

Looks at every item in items.json added within the last WINDOW hours (or all items
with --all) and rejects any that:
  - link to something not in candidates.json (unless --manual: a wandering run)
  - repeat a link already in the feed
  - have a missing, too-short or too-long text field
  - have a dept line that doesn't read "from the ... dept."
  - carry a web address inside title, dept, reasoning or summary
  - use a category that isn't in CATEGORIES

With --fix, rejected items are removed from items.json and seen.txt. Without it, the
script only reports and exits 1 if anything was rejected.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
LOCAL_TZ = ZoneInfo("America/Chicago")
WINDOW_HOURS = 3

CATEGORIES = {
    'Astronomy and Space', 'Space Weather and Aurora', 'Astrophotography', 'DotNet and Development', 'AI and Agents', 'Science Fiction', 'Minnesota and Nature', 'Curious Discoveries', 'Wildcard', 'Meta'
}
URL_IN_TEXT = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|org|net|io|co|uk|edu|gov)/)", re.I)
DEPT = re.compile(r"^from the [A-Za-z0-9'’ -]+ dept\.$")
LIMITS = {"title": (5, 200), "source": (2, 80), "dept": (12, 90),
          "reasoning": (40, 900), "summary": (40, 900)}


def norm(url):
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return f"{host}{path}" + (f"?{p.query}" if p.query else "")


def problems(it, pool, earlier_links, pool_images=None):
    out = []
    link = it.get("link") or ""
    if not re.match(r"^https?://", link):
        out.append("link is not a web address")
    elif pool is not None and norm(link) not in pool:
        out.append("link is not in candidates.json")
    if it.get("id") != link:
        out.append("id must equal link")
    if norm(link) in earlier_links:
        out.append("repeat of an earlier item")
    for field, (lo, hi) in LIMITS.items():
        v = it.get(field)
        if not isinstance(v, str) or not lo <= len(v.strip()) <= hi:
            out.append(f"{field} missing or wrong length")
        elif field != "source" and URL_IN_TEXT.search(v):
            out.append(f"web address inside {field}")
    if isinstance(it.get("dept"), str) and not DEPT.match(it["dept"].strip()):
        out.append("dept line has the wrong shape")
    img = it.get("image")
    if img is not None and (not isinstance(img, str) or not img.startswith("https://") or len(img) > 500):
        out.append("image is not an https address")
    elif img and pool_images is not None and pool_images.get(norm(link)) != img:
        out.append("image differs from the candidate's")
    sb = it.get("submitted_by")
    if sb is not None and (not isinstance(sb, str) or not 1 <= len(sb) <= 40 or URL_IN_TEXT.search(sb)):
        out.append("submitted_by is malformed")
    if it.get("category") not in CATEGORIES:
        out.append(f"unknown category {it.get('category')!r}")
    try:
        datetime.fromisoformat(it.get("added", ""))
    except ValueError:
        out.append("added is not an ISO timestamp")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="check every item, not just recent ones")
    ap.add_argument("--manual", action="store_true", help="wandering run: links need not be in the pool")
    ap.add_argument("--fix", action="store_true", help="remove rejected items from items.json and seen.txt")
    args = ap.parse_args()

    items = json.loads((ROOT / "items.json").read_text())
    pool = pool_images = None
    if not args.manual:
        cand = json.loads((ROOT / "candidates.json").read_text())
        pool = {norm(c["link"]) for c in cand["items"]}
        pool_images = {norm(c["link"]): c.get("image") for c in cand["items"]}

    cutoff = datetime.now(LOCAL_TZ) - timedelta(hours=WINDOW_HOURS)
    checked = rejected = 0
    keep, bad_links = [], set()
    # items.json is newest first; walk oldest to newest so repeats blame the later copy
    earlier = set()
    results = []
    for it in reversed(items):
        try:
            recent = datetime.fromisoformat(it.get("added", "")) >= cutoff
        except ValueError:
            recent = True
        if args.all or recent:
            checked += 1
            probs = problems(it, pool, earlier, pool_images)
            if probs:
                rejected += 1
                bad_links.add(it.get("link"))
                print(f"REJECT {it.get('title')!r}: " + "; ".join(probs))
                results.append((it, False))
                continue
        earlier.add(norm(it.get("link") or ""))
        results.append((it, True))

    print(f"checked {checked} item(s), rejected {rejected}")
    if rejected and args.fix:
        keep = [it for it, ok in reversed(results) if ok]
        (ROOT / "items.json").write_text(json.dumps(keep, indent=2, ensure_ascii=False) + "\n")
        seen_path = ROOT / "seen.txt"
        lines = [l for l in seen_path.read_text().splitlines() if l.strip() not in bad_links]
        seen_path.write_text("\n".join(lines) + ("\n" if lines else ""))
        print(f"removed {rejected} item(s) from items.json and seen.txt")
        return
    sys.exit(1 if rejected else 0)


if __name__ == "__main__":
    main()
