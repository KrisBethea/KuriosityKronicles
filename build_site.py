#!/usr/bin/env python3
"""Build the Neat website (index.html + sections/*.html) from items.json.

Standard library only. Called by build_feed.py on every run, so the site and the
feed always match. A late-90s news-for-nerds front page: stories grouped by day,
a sections sidebar, dept lines, and the curator's note up front.
"""
import html
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

# The GitHub workflow uses Python isolated mode (-I). Explicitly add only this repo.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))


ROOT = Path(__file__).resolve().parent
SECTIONS_DIR = ROOT / "sections"
ICONS_DIR = ROOT / "icons"
ARCHIVE_DIR = ROOT / "archive"
from site_config import SITE_TITLE, TAGLINE, DESCRIPTION
FRONT_PAGE_STORIES = 30    # the home and section pages show this many; the archive has the rest


def esc(s):
    return html.escape(s or "", quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "misc").lower()).strip("-") or "misc"


def posted(dt):
    hour = dt.strftime("%I").lstrip("0") or "12"
    return dt.strftime(f"%A %B {dt.day}, %Y @{hour}:%M%p")


CSS = """
:root{--orange:#e07a36;--orange-ink:#b0521a;--orange-bar:#dc7a38;--orange-bar-ink:#2b1709;--orange-soft:#fdf3ea;--orange-rule:#eeb88f;--blue:#1d5fa8;--blue-visited:#5a4f9a;
--bar-ink:#fff;--bg:#fff;--panel:#fffaf5;--ink:#1d1a17;--muted:#6b625a;--rule:#eadfd4;--quote:#fbf7f2}
@media (prefers-color-scheme:dark){:root{--orange:#e0884c;--orange-ink:#eda172;--orange-bar:#8f4d22;--orange-bar-ink:#fbeee4;--orange-soft:#241b14;--orange-rule:#6a4428;
--blue:#8cb8f0;--blue-visited:#b3a8e6;--bar-ink:#1a120b;--bg:#15120f;--panel:#1d1813;--ink:#ece6df;
--muted:#a89c90;--rule:#3a3027;--quote:#1b1611}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 Verdana,Geneva,"DejaVu Sans",sans-serif}
a{color:var(--blue)}a:visited{color:var(--blue-visited)}
header.masthead{background:var(--bg);padding:18px 16px 10px;border-bottom:5px solid var(--orange);max-width:1180px;margin:0 auto}
.masthead .logo{font:bold 2.6rem/1 Georgia,"Times New Roman",serif;letter-spacing:-1px;color:var(--orange-ink);text-decoration:none}
.masthead .logo:visited{color:var(--orange-ink)}
.masthead .mark{width:46px;height:46px;vertical-align:-8px;margin-right:10px}
.masthead .tag{display:block;font-size:.85rem;color:var(--blue);margin-top:4px;font-style:italic}
nav.topnav{max-width:1180px;margin:0 auto;padding:6px 16px;font-size:.8rem;border-bottom:1px solid var(--rule)}
nav.topnav a,nav.topnav a:visited{color:var(--blue);margin-right:16px;text-decoration:none;font-weight:bold}
nav.topnav a:hover{text-decoration:underline}
.wrap{display:grid;grid-template-columns:180px minmax(0,1fr) 220px;gap:20px;max-width:1180px;margin:0 auto;padding:16px}
aside .box{background:var(--panel);border:1px solid var(--rule);border-top:3px solid var(--orange);margin-bottom:16px}
aside .box h3{margin:0;color:var(--orange-ink);font-size:.78rem;padding:6px 8px 0;text-transform:uppercase;letter-spacing:.06em}
aside .box div{padding:6px 8px 8px;font-size:.82rem}
aside ul{list-style:none;margin:0;padding:0}aside li{padding:2px 0}
aside li.on a{font-weight:bold}
.day{font:bold .8rem Verdana,sans-serif;color:var(--blue);margin:24px 0 10px;text-transform:uppercase;letter-spacing:.06em}
.day:first-child{margin-top:0}
article{margin-bottom:28px;border:1px solid var(--rule);border-radius:0 8px 0 0}
article h2{margin:0;background:var(--orange-bar);color:var(--orange-bar-ink);font-size:1.05rem;padding:7px 12px;line-height:1.35;border-radius:0 7px 0 0;display:flex;align-items:center;gap:10px}
article h2 a{flex:1}
.icon{width:24px;height:24px;flex:none;color:var(--orange-bar-ink)}
.icon.side{width:14px;height:14px;vertical-align:-2px;margin-right:5px;color:var(--orange-ink)}
article h2 a,article h2 a:visited{color:var(--orange-bar-ink);text-decoration:none}
article h2 a:hover{text-decoration:underline}
.meta{font-size:.78rem;color:var(--muted);padding:6px 12px 0}
.meta .sec{font-weight:bold;color:var(--blue);text-decoration:none}
.dept{font-size:.78rem;color:var(--orange-ink);padding:0 12px 6px;font-style:italic}
.body{padding:4px 12px;overflow:hidden}
.body img{float:right;width:240px;max-width:45%;height:auto;margin:4px 0 8px 12px;border:1px solid var(--rule);border-radius:4px}
.note{margin:6px 0}
.summary{margin:8px 0;padding:8px 12px;background:var(--quote);border-left:3px solid var(--orange-rule)}
.more{font-size:.82rem;padding:4px 12px 10px;font-weight:bold}
.more span{font-weight:normal;color:var(--muted)}
.older{margin:8px 0 24px;font-weight:bold;font-size:.9rem}
form.search{display:flex;gap:8px;margin:0 0 6px}
form.search input{flex:1;min-width:0;font:inherit;padding:8px 10px;border:1px solid var(--rule);border-radius:6px;background:var(--panel);color:var(--ink)}
form.search select{font:inherit;padding:8px;border:1px solid var(--rule);border-radius:6px;background:var(--panel);color:var(--ink);max-width:45%}
.stat{color:var(--muted);font-size:.85rem;margin:0 0 14px}
.older-stuff li.od{font-weight:bold;color:var(--orange-ink);text-transform:uppercase;font-size:.7rem;letter-spacing:.05em;margin-top:6px}
.older-stuff li{line-height:1.35;padding:2px 0}
.fortune{font-style:italic;color:var(--ink);margin:0 auto 12px;max-width:40rem;font-size:.85rem}
.fortune span{color:var(--muted);font-style:normal}
footer{max-width:1180px;margin:0 auto;border-top:4px solid var(--orange);color:var(--muted);font-size:.75rem;text-align:center;padding:14px 16px 28px}
@media (max-width:900px){.wrap{grid-template-columns:minmax(0,1fr)}.left{order:2}.right{order:3}main{order:1}
.body img{width:100%;max-width:100%;float:none;margin:4px 0 10px;max-height:240px;object-fit:cover}}
"""


_ICON_CACHE = {}


def icon(cat, cls="icon"):
    """Inline SVG for a category, or empty string if there's no icons/<slug>.svg."""
    s = slug(cat)
    if s not in _ICON_CACHE:
        p = ICONS_DIR / f"{s}.svg"
        _ICON_CACHE[s] = p.read_text(encoding="utf-8").strip() if p.exists() else ""
    svg = _ICON_CACHE[s]
    return svg.replace("<svg ", f'<svg class="{cls}" aria-hidden="true" ', 1) if svg else ""


def story(it, prefix):
    dt = datetime.fromisoformat(it["added"])
    cat = it.get("category") or "Misc"
    parts = [f'<article id="{esc(slug(it["id"]))[:80]}">',
             f'<h2><a href="{esc(it["link"])}" target="_blank" rel="noopener">{esc(it["title"])}</a>{icon(cat)}</h2>',
             f'<div class="meta">Posted by the Editor on {esc(posted(dt))} in '
             f'<a class="sec" href="{prefix}sections/{slug(cat)}.html">{esc(cat)}</a>'
             + (f' &middot; submitted by {esc(it["submitted_by"])}' if it.get("submitted_by") else "") + '</div>']
    if it.get("dept"):
        parts.append(f'<div class="dept">{esc(it["dept"])}</div>')
    parts.append('<div class="body">')
    if it.get("image") and it["image"].startswith("https://"):
        parts.append(f'<img src="{esc(it["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">')
    if it.get("reasoning"):
        parts.append(f'<p class="note">{esc(it["reasoning"])}</p>')
    if it.get("summary"):
        parts.append(f'<div class="summary">{esc(it["summary"])}</div>')
    parts.append("</div>")
    src = f' <span>({esc(it["source"])})</span>' if it.get("source") else ""
    parts.append(f'<div class="more"><a href="{esc(it["link"])}" target="_blank" rel="noopener">Read the rest of this story</a>{src}</div>')
    parts.append("</article>")
    return "\n".join(parts)


def month_name(key):
    return datetime.strptime(key, "%Y-%m").strftime("%B %Y")


def page(title, items, counts, current, prefix, total, months=(), intro="", tail="", older_box=""):
    days, last = [], None
    for it in items:
        dt = datetime.fromisoformat(it["added"])
        d = dt.strftime(f"%A, %B {dt.day}, %Y")
        if d != last:
            days.append(f'<div class="day">{esc(d)}</div>')
            last = d
        days.append(story(it, prefix))
    if not items and not intro:
        days.append("<p>Nothing here yet.</p>")
    secs = [f'<li class="{"on" if current is None else ""}"><a href="{prefix}index.html">All stories</a> ({total})</li>']
    for name, n in sorted(counts.items(), key=lambda kv: kv[0].lower()):
        on = "on" if current == name else ""
        secs.append(f'<li class="{on}">{icon(name, "icon side")}<a href="{prefix}sections/{slug(name)}.html">{esc(name)}</a> ({n})</li>')
    updated = esc(posted(datetime.fromisoformat(items[0]["added"]))) if items else ""
    head_title = SITE_TITLE if current is None else f"{current} | {SITE_TITLE}"
    arch = "".join(f'<li class="{"on" if current == month_name(m) else ""}"><a href="{prefix}archive/{m}.html">{esc(month_name(m))}</a> ({n})</li>'
                   for m, n in months)
    archive_box = (f'<div class="box"><h3>Archive</h3><div><ul>{arch}</ul>'
                   f'<p style="margin:6px 0 0"><a href="{prefix}archive/index.html">Every story ever</a></p></div></div>') if months else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(head_title)}</title>
<meta name="description" content="{esc(DESCRIPTION)}">
<link rel="alternate" type="application/rss+xml" title="{esc(SITE_TITLE)}" href="{prefix}feed.xml">
<link rel="icon" type="image/svg+xml" href="{prefix}favicon.svg">
<style>{CSS}</style></head><body>
<header class="masthead"><a class="logo" href="{prefix}index.html"><img src="{prefix}favicon.svg" alt="" class="mark">{esc(SITE_TITLE)}</a><span class="tag">{esc(TAGLINE)}</span></header>
<nav class="topnav"><a href="{prefix}index.html">Home</a><a href="{prefix}archive/index.html">Archive</a><a href="{prefix}search.html">Search</a><a href="{prefix}feed.xml">RSS</a><a href="#about">About</a></nav>
<div class="wrap">
<aside class="left"><div class="box"><h3>Sections</h3><div><ul>{''.join(secs)}</ul></div></div>{archive_box}</aside>
<main>{intro if intro else ("" if current is None else f'<div class="day">Section: {esc(title)}</div>')}
{chr(10).join(days)}{tail}</main>
<aside class="right">
<div class="box" id="about"><h3>About</h3><div>A personalized collection of astronomy, space weather, astrophotography, C# development,
AI agents, science fiction, Minnesota nature and surprising discoveries.
Picked automatically from public source feeds, with a note on why.</div></div>
<div class="box"><h3>Subscribe</h3><div>Point any feed reader at <a href="{prefix}feed.xml">feed.xml</a>.</div></div>
{older_box}
{f'<div class="box"><h3>Last updated</h3><div>{updated}</div></div>' if updated else ''}
</aside></div>
<footer>{fortune().replace("{prefix}", prefix)}{esc(SITE_TITLE)}. All stories link to their original sources; notes and summaries are written fresh.
No ads, no comments, no outrage.</footer>
</body></html>
"""


def load_archive(live):
    """All stories by month: archived ones plus the live ones from the same month."""
    by_month = {}
    for it in live:
        by_month.setdefault(it["added"][:7], {})[it["id"]] = it
    if ARCHIVE_DIR.exists():
        for f in sorted(ARCHIVE_DIR.glob("????-??.json")):
            for it in json.loads(f.read_text(encoding="utf-8")):
                by_month.setdefault(f.stem, {}).setdefault(it["id"], it)
    months = {}
    for m, d in by_month.items():
        months[m] = sorted(d.values(), key=lambda it: it["added"], reverse=True)
    return dict(sorted(months.items(), reverse=True))


SEARCH_JS = r"""
(function(){
var q=document.getElementById('q'),cat=document.getElementById('cat'),out=document.getElementById('hits'),st=document.getElementById('stat');
var data=null;
function esc(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function posted(iso){var d=new Date(iso);return d.toLocaleDateString(undefined,{weekday:'long',year:'numeric',month:'long',day:'numeric'});}
function slug(s){return (s||'misc').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||'misc';}
function card(it){
  var h='<article><h2><a href="'+esc(it.l)+'" target="_blank" rel="noopener">'+esc(it.t)+'</a>'+(ICONS[it.c]||'')+'</h2>';
  h+='<div class="meta">Posted by the Editor on '+esc(posted(it.a))+' in <a class="sec" href="sections/'+slug(it.c)+'.html">'+esc(it.c)+'</a>'+(it.b?' &middot; submitted by '+esc(it.b):'')+'</div>';
  if(it.d)h+='<div class="dept">'+esc(it.d)+'</div>';
  h+='<div class="body">'+(it.i?'<img src="'+esc(it.i)+'" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">':'')+(it.r?'<p class="note">'+esc(it.r)+'</p>':'')+(it.s?'<div class="summary">'+esc(it.s)+'</div>':'')+'</div>';
  h+='<div class="more"><a href="'+esc(it.l)+'" target="_blank" rel="noopener">Read the rest of this story</a>'+(it.o?' <span>('+esc(it.o)+')</span>':'')+'</div></article>';
  return h;
}
function score(it,terms){
  var t=it.t.toLowerCase(),rest=((it.d||'')+' '+(it.r||'')+' '+(it.s||'')+' '+(it.o||'')+' '+it.c).toLowerCase(),sc=0;
  for(var k=0;k<terms.length;k++){var w=terms[k];if(t.indexOf(w)>=0)sc+=3;else if(rest.indexOf(w)>=0)sc+=1;else return 0;}
  return sc;
}
function run(){
  if(!data)return;
  var terms=q.value.toLowerCase().split(/\s+/).filter(Boolean),c=cat.value,hits=[];
  for(var i=0;i<data.length;i++){var it=data[i];if(c&&it.c!==c)continue;
    if(terms.length){var sc=score(it,terms);if(!sc)continue;hits.push([sc,it]);}else if(c)hits.push([0,it]);}
  hits.sort(function(a,b){return b[0]-a[0]||(a[1].a<b[1].a?1:-1);});
  var shown=hits.slice(0,60);
  st.textContent=(terms.length||c)?(hits.length+' stor'+(hits.length===1?'y':'ies')+(hits.length>shown.length?', showing the first '+shown.length:'')):('Type to search '+data.length+' stories.');
  out.innerHTML=shown.map(function(h){return card(h[1]);}).join('');
  var u=new URL(location);if(q.value)u.searchParams.set('q',q.value);else u.searchParams.delete('q');if(c)u.searchParams.set('cat',c);else u.searchParams.delete('cat');history.replaceState(null,'',u);
}
fetch('search.json').then(function(r){return r.json();}).then(function(d){data=d;var p=new URL(location).searchParams;if(p.get('q'))q.value=p.get('q');if(p.get('cat'))cat.value=p.get('cat');run();q.focus();});
q.addEventListener('input',run);cat.addEventListener('change',run);
})();
"""


def write_search(by_month, counts, months, total_live):
    """search.json (every story ever, compact keys) and search.html (client-side search)."""
    index = []
    for stories in by_month.values():
        for it in stories:
            row = {"t": it["title"], "l": it["link"], "c": it.get("category") or "Misc", "a": it["added"],
                   "o": it.get("source", ""), "d": it.get("dept", ""), "r": it.get("reasoning", ""),
                   "s": it.get("summary", "")}
            if it.get("image"):
                row["i"] = it["image"]
            if it.get("submitted_by"):
                row["b"] = it["submitted_by"]
            index.append(row)
    index.sort(key=lambda r: r["a"], reverse=True)
    (ROOT / "search.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    cats = sorted({r["c"] for r in index}, key=str.lower)
    icon_map = json.dumps({c: icon(c) for c in cats}, ensure_ascii=False)
    options = '<option value="">All sections</option>' + "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in cats)
    intro = (f'<div class="day">Search: every story ever ({len(index)})</div>'
             f'<form class="search" onsubmit="return false"><input id="q" type="search" placeholder="dinosaur, fiddle, Plan 9…" autocomplete="off">'
             f'<select id="cat">{options}</select></form><p id="stat" class="stat"></p><div id="hits"></div>'
             f'<script>var ICONS={icon_map};{SEARCH_JS}</script>')
    (ROOT / "search.html").write_text(
        page("Search", [], counts, "Search", "", total_live, months, intro), encoding="utf-8")


def fortune():
    """A fortune picked in the browser on every page view, from fortunes.json (built from fortunes.txt).
    Falls back to one chosen at build time when scripts are off."""
    path = ROOT / "fortunes.txt"
    if not path.exists():
        return ""
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    if not lines:
        return ""
    import random
    pairs = [list(l.partition(" -- ")[::2]) for l in lines]
    (ROOT / "fortunes.json").write_text(json.dumps(pairs, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    text, who = random.choice(pairs)
    return (f'<div class="fortune" id="fortune">{esc(text)}{f" <span>&mdash; {esc(who)}</span>" if who else ""}</div>'
            '<script>fetch("{prefix}fortunes.json").then(function(r){return r.json()}).then(function(f){'
            'var p=f[Math.floor(Math.random()*f.length)],e=document.getElementById("fortune");'
            'e.textContent=p[0];if(p[1]){var s=document.createElement("span");s.textContent=" \u2014 "+p[1];e.appendChild(s)}}).catch(function(){})</script>')


def older_stuff(items, shown, prefix):
    """Slashdot's Older Stuff box: headlines that have fallen off the front page, by day."""
    rest = [it for it in items if it not in shown][:24]
    if not rest:
        return ""
    out, last = [], None
    for it in rest:
        dt = datetime.fromisoformat(it["added"])
        d = dt.strftime(f"%A, %B {dt.day}")
        if d != last:
            out.append(f'<li class="od">{esc(d)}</li>')
            last = d
        out.append(f'<li><a href="{prefix}archive/{it["added"][:7]}.html#{esc(slug(it["id"]))[:80]}">{esc(it["title"])}</a></li>')
    return f'<div class="box"><h3>Older Stuff</h3><div><ul class="older-stuff">{"".join(out)}</ul></div></div>'


def build(items=None):
    if items is None:
        items = json.loads((ROOT / "items.json").read_text(encoding="utf-8"))
    items = [it for it in items if it.get("category") != "Meta"] or items
    counts = Counter(it.get("category") or "Misc" for it in items)
    by_month = load_archive(items)
    months = [(m, len(v)) for m, v in by_month.items()]
    total_ever = sum(n for _, n in months)

    def recent(stories):
        shown = stories[:FRONT_PAGE_STORIES]
        if len(stories) > len(shown):
            when = datetime.fromisoformat(shown[-1]["added"]).strftime("%B %Y").lower()
            return shown, (f'<p class="older"><a href="{{prefix}}archive/{shown[-1]["added"][:7]}.html">'
                           f'Older stories &rarr; the {esc(when)} archive</a></p>')
        return shown, ""

    front, older = recent(items)
    (ROOT / "index.html").write_text(
        page(SITE_TITLE, front, counts, None, "", len(items), months, tail=older.replace("{prefix}", ""),
             older_box=older_stuff(items, front, "")), encoding="utf-8")
    SECTIONS_DIR.mkdir(exist_ok=True)
    for old in SECTIONS_DIR.glob("*.html"):
        old.unlink()
    for name in counts:
        all_sub = [it for it in items if (it.get("category") or "Misc") == name]
        sub, older = recent(all_sub)
        (SECTIONS_DIR / f"{slug(name)}.html").write_text(
            page(name, sub, counts, name, "../", len(items), months, tail=older.replace("{prefix}", "../"),
                 older_box=older_stuff(all_sub, sub, "../")), encoding="utf-8")

    ARCHIVE_DIR.mkdir(exist_ok=True)
    for old in ARCHIVE_DIR.glob("*.html"):
        old.unlink()
    for m, stories in by_month.items():
        intro = f'<div class="day">Archive: {esc(month_name(m))} ({len(stories)} stories)</div>'
        (ARCHIVE_DIR / f"{m}.html").write_text(
            page(month_name(m), stories, counts, month_name(m), "../", len(items), months, intro), encoding="utf-8")
    rows = "".join(f'<li><a href="{m}.html">{esc(month_name(m))}</a> ({n} stories)</li>' for m, n in months)
    intro = (f'<div class="day">Archive: every story ever ({total_ever})</div>'
             f'<p>Nothing is thrown away. The feed carries the newest {len(items)}; everything older lives here, by month.</p>'
             f'<ul>{rows}</ul>')
    write_search(by_month, counts, months, len(items))
    (ARCHIVE_DIR / "index.html").write_text(
        page("Archive", [], counts, "Archive", "../", len(items), months, intro), encoding="utf-8")
    print(f"site written: index.html + {len(counts)} section pages + {len(by_month)} archive month(s)")


if __name__ == "__main__":
    build()
