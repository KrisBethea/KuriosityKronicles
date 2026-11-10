#!/usr/bin/env python3
"""Neat feed collector. Standard library only, no AI involved.

Pulls every feed in collector/sources.txt (RSS 2.0, RSS 1.0 or Atom), normalises
the entries, drops what the profile rules out, and writes candidates.json. The
curator picks only from that file, so it never has to fetch anything itself.

Dropped: links already in seen.txt; entries older
than MAX_AGE_DAYS; duplicates. Per-source entries are capped at MAX_PER_SOURCE.

Usage: python3 collector/collect.py [--sources FILE] [--out FILE] [--quiet]
Exit code is 0 even if some feeds fail; failures are listed in the output file.
"""
import argparse
import html
import json
import random
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
LOCAL_TZ = ZoneInfo("America/Chicago")

OWNER = "Kris"   # the name shown on items submitted through submit.txt
USER_AGENT = "Mozilla/5.0 (compatible; NeatCollector/1.0) personal RSS reader"
TIMEOUT = 25
MAX_AGE_DAYS = 10
MAX_PER_SOURCE = 20
SUMMARY_CHARS = 700
PAGE_CHARS = 1800          # text pulled from the article itself, for 'fulltext' sources
PAGE_MAX_BYTES = 2_000_000
PAGE_TIMEOUT = 15
BLOCK_RUST = False  # Personal preference; change to True to block Rust topics.
RUST = re.compile(r"\bRust\b", re.I)
# Title shapes that are almost always drama rather than a neat thing (for 'nodrama' sources).
DRAMA = re.compile(
    r"\b(layoffs?|laid off|lawsuit|sues?|sued|suing|settlement|antitrust|regulators?|subpoena|indicted|fined|"
    r"ceo|cto|founder|resigns?|resigned|steps? down|fired|quits?|i'?m leaving|why i left|"
    r"acquires?|acquired|acquisition|merger|valuation|ipo|funding|raises? \$|series [abc]\b|"
    r"shuts? down|shutting down|discontinued|banned|bans?|boycott|backlash|outrage|controvers\w*|"
    r"drama|scandal|apolog\w*|rant|hot take|unpopular opinion|is dead|is dying|considered harmful|"
    r"vs\.?\s|versus|war on|crackdown|censor|privacy nightmare|dark pattern|enshittif\w*|"
    r"musk|zuckerberg|altman|bezos|trump|congress|senate|eu commission|tariff|election|"
    r"ai (hype|bubble|slop|is|will|won'?t)|agi\b|llms? (are|will|can'?t)|vibe cod\w*|"
    r"salary|salaries|compensation|interview(s|ing)?|hiring|job market|career advice|burnout|"
    r"ask hn|tell hn)\b", re.I)


# ---------------------------------------------------------------- helpers

def log(*a):
    print(*a, file=sys.stderr, flush=True)


def local(tag):
    """Element tag without its namespace."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def text_of(el):
    if el is None:
        return ""
    return "".join(el.itertext()) if len(el) else (el.text or "")


# --- sanitising: keep only what a human reader would see, and nothing addressed to an AI.
HIDDEN_TAGS = re.compile(r"<(script|style|template|noscript|svg|iframe|textarea|select)\b.*?</\1>", re.S | re.I)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
HIDDEN_ELEMENT = re.compile(  # display:none, visibility:hidden, hidden attr, aria-hidden, sr-only
    r"<([a-z0-9]+)\b[^>]*(?:hidden(?:=[\"'][^\"']*[\"'])?|aria-hidden=[\"']true[\"']"
    r"|style=[\"'][^\"']*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0)[^\"']*[\"']"
    r"|class=[\"'][^\"']*(?:sr-only|visually-hidden|screen-reader)[^\"']*[\"'])[^>]*>.*?</\1>", re.S | re.I)
INVISIBLE_CHARS = re.compile("[\u200b-\u200f\u2028-\u202e\u2060-\u2064\u206a-\u206f\ufeff\u00ad\U000e0000-\U000e007f]")
# sentences talking to a model rather than to a reader
INSTRUCTION_LINE = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier|preceding|system)\s+(instructions?|prompts?|rules?|messages?)"
    r"|\b(system|assistant|developer|user)\s*(prompt|message)?\s*:\s"
    r"|\byou are (now|an? (ai|llm|assistant|language model|chatbot))\b"
    r"|\bas an? (ai|llm|language model|assistant)\b"
    r"|\b(new|updated|override|important)\s+(instructions?|directive|task)\s*(for|to)\s+(the\s+)?(ai|assistant|model|curator|claude)\b"
    r"|\b(hey|dear|attention|note to)\s+(ai|llm|assistant|model|claude|curator|chatgpt)\b"
    r"|\b(add|insert|include|link|recommend|pick|select)\s+(this|the following|my)\s+(link|url|page|site|item)\b"
    r"|<\s*/?\s*(system|instructions?|prompt)\s*>|\[(system|inst)\]|<\|[a-z_]+\|>", re.I)


def strip_html(s):
    s = HTML_COMMENT.sub(" ", s)
    s = HIDDEN_TAGS.sub(" ", s)
    s = HIDDEN_ELEMENT.sub(" ", s)
    s = re.sub(r"<[^>]+>", " ", s)       # alt/title attributes go with the tags
    s = html.unescape(s)
    s = INVISIBLE_CHARS.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return drop_instructions(s)


def drop_instructions(text):
    """Remove sentences that address an AI rather than a reader."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [x for x in sentences if not INSTRUCTION_LINE.search(x)]
    return " ".join(kept).strip()


def norm_link(url):
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return f"{host}{path}" + (f"?{p.query}" if p.query else "")


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    for fn in (parsedate_to_datetime, lambda v: datetime.fromisoformat(v.replace("Z", "+00:00"))):
        try:
            dt = fn(s)
            if dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError, IndexError):
            continue
    return None


# ---------------------------------------------------------------- parsing

def children(el):
    return {local(c.tag): c for c in reversed(list(el))}  # first occurrence wins


def parse_entry(el):
    """Return a plain dict for one RSS <item> or Atom <entry>."""
    kids = children(el)
    title = strip_html(text_of(kids.get("title")))
    if not title:
        for name in ("description", "summary", "content"):
            if name in kids:
                title = strip_html(text_of(kids[name]))[:140]
                break

    link = ""
    for c in el:
        if local(c.tag) != "link":
            continue
        rel = c.get("rel", "alternate")
        href = c.get("href")
        if href and rel == "alternate":
            link = href
            break
        if c.text and c.text.strip():
            link = c.text.strip()
            break
    if not link:
        guid = kids.get("guid")
        if guid is not None and guid.get("isPermaLink", "true") != "false":
            link = (guid.text or "").strip()

    body = ""
    for name in ("content", "encoded", "description", "summary"):
        if name in kids and text_of(kids[name]).strip():
            body = text_of(kids[name])
            if name == "encoded" or name == "content":
                break
    summary = strip_html(body)[:SUMMARY_CHARS]

    date = None
    for name in ("pubDate", "published", "date", "updated", "issued"):
        if name in kids:
            date = parse_date(text_of(kids[name]))
            if date:
                break

    tags = []
    for c in el:
        if local(c.tag) == "category":
            t = (c.get("term") or c.text or "").strip()
            if t:
                tags.append(t)

    source_el = kids.get("source")
    via = strip_html(text_of(source_el)) if source_el is not None and local(el.tag) == "item" else ""

    return {"title": title, "link": link.strip(), "summary": summary,
            "date": date, "tags": tags, "via": via, "image": entry_image(el, body)}


IMG_EXT = re.compile(r"\.(jpe?g|png|webp|gif)(\?|$)", re.I)


def good_image(url):
    url = (url or "").strip()
    if not url.startswith("https://") or len(url) > 500:
        return ""
    if re.search(r"(pixel|tracker|beacon|feedburner|1x1|spacer|emoji|avatar|gravatar|badge|icon)", url, re.I):
        return ""
    return url


def entry_image(el, body_html):
    """Lead image for a feed entry: media:content / enclosure / thumbnail, else first <img> in the body."""
    for c in el:
        name = local(c.tag)
        if name in ("content", "thumbnail", "enclosure", "image"):
            url = c.get("url") or c.get("href") or (c.text if name == "image" else "")
            mtype = c.get("type") or c.get("medium") or ""
            if url and ("image" in mtype or IMG_EXT.search(url)):
                img = good_image(url)
                if img:
                    return img
    for m in re.finditer(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", body_html or "", re.I):
        tag = m.group(0)
        w = re.search(r"\bwidth=[\"']?(\d+)", tag)
        if w and int(w.group(1)) < 200:
            continue
        img = good_image(html.unescape(m.group(1)))
        if img:
            return img
    return ""



def parse_feed(data):
    root = ET.fromstring(data)
    entries = [el for el in root.iter() if local(el.tag) in ("item", "entry")]
    return [parse_entry(el) for el in entries]


def points_of(summary):
    """Vote count when a feed states one (hnrss puts 'Points: N' in the description)."""
    m = re.search(r"\bPoints:\s*(\d+)", summary or "")
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- page text

def page_text(url):
    """(title, readable text) from an article page; text is None if nothing usable. Plain fetch, no model."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=PAGE_TIMEOUT) as r:
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype:
            return "", None, ""
        data = r.read(PAGE_MAX_BYTES)
    html_text = data.decode("utf-8", errors="replace")
    og = re.search(r"<meta\b[^>]*(?:property|name)=[\"'](?:og:image|twitter:image)[\"'][^>]*\bcontent=[\"']([^\"']+)[\"']", html_text, re.I) \
        or re.search(r"<meta\b[^>]*\bcontent=[\"']([^\"']+)[\"'][^>]*(?:property|name)=[\"'](?:og:image|twitter:image)[\"']", html_text, re.I)
    image = good_image(html.unescape(og.group(1))) if og else ""
    tm = re.search(r"<title\b[^>]*>(.*?)</title>", html_text, re.S | re.I)
    title = strip_html(tm.group(1)) if tm else ""
    title = re.split(r"\s+[|\u2013\u2014-]\s+", title)[0].strip()[:200]  # drop " | Site name"
    # prefer the article body when the page marks one
    m = re.search(r"<(article|main)\b.*?</\1>", html_text, re.S | re.I)
    body = m.group(0) if m else html_text
    body = re.sub(r"<(nav|header|footer|aside|form)\b.*?</\1>", " ", body, flags=re.S | re.I)
    paras = [strip_html(x) for x in re.findall(r"<p\b[^>]*>(.*?)</p>", body, re.S | re.I)]
    paras = [x for x in paras if len(x) > 60]
    text = " ".join(paras) if paras else strip_html(body)
    text = text.strip()
    return title, (text[:PAGE_CHARS] if len(text) > 80 else None), image


def previous_page_texts(path):
    """Page text already pulled on an earlier run, keyed by link, so pages are fetched once."""
    try:
        old = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return {it["link"]: it["summary"] for it in old.get("items", []) if it.get("summary_from") == "page"}


def previous_images(path):
    try:
        old = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return {it["link"]: it["image"] for it in old.get("items", []) if it.get("image")}


# ---------------------------------------------------------------- fetching

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def load_sources(path):
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) not in (3, 4) or not parts[2].startswith("http"):
            log(f"sources.txt line {n}: expected 'category | name | url [| flags]', got {line!r}")
            continue
        flags = {f.strip().lower() for f in parts[3].split(",")} if len(parts) == 4 else set()
        sample, embargo, skip = 0, 0, None
        for f in list(flags):
            if f.startswith("sample:"):
                sample = int(f.split(":", 1)[1])
                flags.discard(f)
            elif f.startswith("embargo:"):
                embargo = int(f.split(":", 1)[1])
                flags.discard(f)
            elif f.startswith("skip:"):
                skip = re.compile(f.split(":", 1)[1].replace(";", "|"), re.I)
                flags.discard(f)
        unknown = flags - {"evergreen", "fulltext", "nodrama", "filler"}
        if unknown:
            log(f"sources.txt line {n}: unknown flag(s) {sorted(unknown)}")
        out.append({"category": parts[0], "name": parts[1], "url": parts[2],
                    "evergreen": "evergreen" in flags or sample > 0,
                    "fulltext": "fulltext" in flags or sample > 0,
                    "nodrama": "nodrama" in flags, "filler": "filler" in flags, "sample": sample,
                    "embargo": embargo, "skip": skip})
    return out


def sample_sitemap(data, n, seen):
    """n page URLs from a sitemap, chosen at random but fixed for the day."""
    root = ET.fromstring(data)
    urls = [el.text.strip() for el in root.iter() if local(el.tag) == "loc" and el.text]
    urls = [u for u in urls if norm_link(u) not in seen and re.search(r"/\d{4}/\d{2}/", u)
            and not re.search(r"\.(png|jpe?g|gif|svg|webp|pdf|mp[34])$|/attachment/|/feed/?$", u, re.I)]
    rng = random.Random(datetime.now(LOCAL_TZ).date().isoformat())
    picks = rng.sample(urls, min(n, len(urls)))
    return [{"title": u.rstrip("/").rsplit("/", 1)[-1].replace("-", " "), "link": u, "summary": "",
             "date": None, "tags": [], "via": "", "image": "", "title_from_page": True} for u in picks]


def collect_one(src, seen=frozenset()):
    try:
        data = fetch(src["url"])
        entries = sample_sitemap(data, src["sample"], seen) if src["sample"] else parse_feed(data)
        return src, entries, None
    except urllib.error.HTTPError as e:
        return src, [], f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return src, [], f"network: {e.reason}"
    except ET.ParseError as e:
        head = data[:200].lstrip().lower()  # fetch succeeded, so data is set
        if head.startswith((b"<!doctype html", b"<html")):
            return src, [], "got an HTML page instead of a feed (blocked or wrong URL)"
        return src, [], f"not valid XML: {e}"
    except Exception as e:  # noqa: BLE001 - one bad feed must not stop the run
        return src, [], f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- embargoed articles

HELD_PATH = HERE / "held.json"
HELD_MAX_DAYS = 30


def load_held():
    try:
        return json.loads(HELD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def hold(held, e, src, now):
    """Remember a subscriber-only article so it can join the pool once it turns free."""
    if e["link"] in held:
        return
    held[e["link"]] = {
        "title": e["title"].removeprefix("[$]").strip(), "link": e["link"], "feed": src["name"],
        "category": src["category"], "tags": e["tags"][:8],
        "published": (e["date"] or now).astimezone(LOCAL_TZ).isoformat(timespec="minutes"),
        "free_after": ((e["date"] or now) + timedelta(days=src["embargo"])).astimezone(LOCAL_TZ).isoformat(timespec="minutes"),
        "fulltext": src["fulltext"], "evergreen": True,
    }


def release_held(held, seen, now):
    """Held articles whose embargo has passed become candidates; stale or used ones are dropped."""
    out = []
    for link, h in list(held.items()):
        pub = datetime.fromisoformat(h["published"])
        if norm_link(link) in seen or now - pub > timedelta(days=HELD_MAX_DAYS):
            del held[link]
            continue
        if now >= datetime.fromisoformat(h["free_after"]):
            out.append({**h, "source": h["feed"], "summary": "", "tier": "main",
                        "title_from_page": False, "points": None, "image": "", "freed": True})
    if out:
        log(f"{len(out)} held article(s) now free and in the pool")
    return out


def save_held(held):
    text = json.dumps(held, indent=1, ensure_ascii=False) + "\n"
    if not HELD_PATH.exists() or HELD_PATH.read_text(encoding="utf-8") != text:
        HELD_PATH.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- submissions

def submissions(seen, cached, now):
    """Links the owner put in submit.txt: fetched once, added to the pool, pruned when used."""
    path = ROOT / "submit.txt"
    if not path.exists():
        return []
    out, keep = [], []
    original = path.read_text(encoding="utf-8")
    for raw in original.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            keep.append(raw)
            continue
        link, _, note = (x.strip() for x in line.partition("|"))
        if not link.startswith("http"):
            keep.append(raw)
            continue
        if norm_link(link) in seen:
            log(f"submission used, pruned: {link}")
            continue
        keep.append(raw)
        title, text, image = "", cached.get(link), ""
        try:
            title, text, image = page_text(link)
        except Exception as e:  # noqa: BLE001
            log(f"submission {link}: {type(e).__name__}")
        host = (urlsplit(link).hostname or "").removeprefix("www.")
        item = {
            "title": title or link, "link": link, "source": host, "category": "Wildcard",
            "summary": ((OWNER + "'s note: " + note + " ") if note else "") + (text or ""),
            "published": now.astimezone(LOCAL_TZ).isoformat(timespec="minutes"), "tags": [],
            "feed": "Submitted", "evergreen": True, "tier": "submitted", "submitted_by": OWNER,
            "summary_from": "page" if text else "feed",
        }
        if image:
            item["image"] = image
        out.append(item)
    new_text = "\n".join(keep).rstrip("\n") + "\n"
    if new_text != original:
        path.write_text(new_text, encoding="utf-8")
    if out:
        log(f"{len(out)} submission(s) in the pool")
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(HERE / "sources.txt"))
    ap.add_argument("--out", default=str(ROOT / "candidates.json"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    sources = load_sources(Path(args.sources))
    seen_path = ROOT / "seen.txt"
    seen = {norm_link(l) for l in seen_path.read_text().split()} if seen_path.exists() else set()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_AGE_DAYS)

    held = load_held()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda src: collect_one(src, seen), sources))

    items, report, links = [], {}, set()
    for src, entries, err in results:
        key = f"{src['category']} | {src['name']}"
        if err:
            report[key] = {"url": src["url"], "ok": False, "error": err, "kept": 0}
            log(f"FAIL {key}: {err}")
            continue
        kept, dropped, old, dup, blank, drama, skipped, embargoed = 0, 0, 0, 0, 0, 0, 0, 0
        for e in entries:
            if not e["link"] or not e["title"]:
                blank += 1
                continue
            nl = norm_link(e["link"])
            if nl in links or nl in seen:
                dup += 1
                continue
            if BLOCK_RUST and (any(t.lower() == "rust" for t in e["tags"]) or RUST.search(e["title"]) or RUST.search(e["summary"])):
                dropped += 1
                continue
            if src["nodrama"] and DRAMA.search(e["title"]):
                drama += 1
                continue
            if src["skip"] and src["skip"].search(e["title"]):
                skipped += 1
                continue
            if src["embargo"] and e["title"].startswith("[$]"):
                # subscriber-only for now: hold it, release it when it turns free
                hold(held, e, src, now)
                embargoed += 1
                continue
            if e["date"] and e["date"] < cutoff and not src["evergreen"]:
                old += 1
                continue
            if kept >= MAX_PER_SOURCE:
                break
            links.add(nl)
            kept += 1
            items.append({
                "title": e["title"][:300],
                "link": e["link"],
                "source": e["via"] or src["name"],
                "category": src["category"],
                "summary": e["summary"],
                "published": e["date"].astimezone(LOCAL_TZ).isoformat(timespec="minutes") if e["date"] else None,
                "tags": e["tags"][:8],
                "feed": src["name"],
                "evergreen": src["evergreen"],
                "fulltext": src["fulltext"],
                "tier": "filler" if src["filler"] else "main",
                "title_from_page": e.get("title_from_page", False),
                "points": points_of(e["summary"]),
                "image": e.get("image") or "",
            })
        report[key] = {"url": src["url"], "ok": True, "kept": kept, "entries": len(entries),
                       "dropped_rust": dropped, "dropped_drama": drama, "skipped": skipped,
                       "held": embargoed, "old": old, "seen_or_dup": dup, "no_title_or_link": blank}
        if not args.quiet:
            why = ", ".join(f"{n} {w}" for n, w in ((dropped, "Rust"), (drama, "drama"), (skipped, "skipped"), (embargoed, "held"), (old, "old"), (dup, "seen/dup"), (blank, "no title/link")) if n)
            log(f"ok   {key}: {kept} kept of {len(entries)}" + (f" ({why})" if why else ""))

    # subscriber-only articles whose embargo has passed join the pool now, so they get text below
    items += release_held(held, seen, now)
    save_held(held)

    # pull article text for 'fulltext' sources (feeds whose entries are only a title)
    cached = previous_page_texts(args.out)
    old_images = previous_images(args.out)
    for it in items:
        if not it.get("image") and it["link"] in old_images:
            it["image"] = old_images[it["link"]]
    todo = [it for it in items if it["fulltext"]]
    def enrich(it):
        if it["link"] in cached:
            return it, cached[it["link"]], "cached"
        try:
            title, text, image = page_text(it["link"])
            if title and it.get("title_from_page"):
                it["title"] = title
            if image and not it.get("image"):
                it["image"] = image
            return it, text, "fetched"
        except Exception as e:  # noqa: BLE001
            return it, None, f"{type(e).__name__}"
    got = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for it, text, how in pool.map(enrich, todo):
            if text:
                it["summary"] = text
                it["summary_from"] = "page"
                got += 1
            elif how not in ("cached", "fetched") and not args.quiet:
                log(f"page {it['link']}: {how}")
    before = len(items)
    items = [it for it in items if not BLOCK_RUST or not (RUST.search(it["title"]) or RUST.search(it["summary"]))]
    if len(items) < before:
        log(f"dropped {before - len(items)} Rust item(s) found after pulling article text")
    for it in items:
        it.pop("fulltext", None)
        it.pop("title_from_page", None)
        if it.get("points") is None:
            it.pop("points", None)
        if not it.get("image"):
            it.pop("image", None)
        it.setdefault("summary_from", "feed")
    if todo:
        log(f"article text pulled for {got} of {len(todo)} fulltext candidates")

    items += submissions(seen, cached, now)

    items.sort(key=lambda it: it["published"] or "", reverse=True)
    out = {"generated": now.astimezone(LOCAL_TZ).isoformat(timespec="minutes"),
           "count": len(items), "sources": report, "items": items}
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = sum(1 for r in report.values() if not r["ok"])
    log(f"{len(items)} candidates from {len(report) - failed} feeds ({failed} failed)")


if __name__ == "__main__":
    main()
