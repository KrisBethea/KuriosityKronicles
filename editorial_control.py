#!/usr/bin/env python3
"""Turn one owner-maintained YAML file into legacy feed sources and editorial guidance.

The existing collector and Gemini curator continue using their familiar files.
This module only reads local, owner-controlled configuration, never article bodies.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "editorial_config.yml"
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_FLAGS = {"evergreen", "fulltext", "nodrama", "filler"}
SPECIAL_CATEGORIES = {"Wildcard", "Meta"}



def _text(value, label, max_length=500, allow_newlines=False):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(
            f"{label}: expected nonempty text (max {max_length} characters)"
        )

    disallowed = ("\r", "|") if allow_newlines else ("\r", "\n", "|")

    if any(c in value for c in disallowed):
        raise ValueError(f"{label}: disallowed newline or | character")

    return value.strip()



def _strings(values, label):
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{label}: expected a list")
    return [_text(v, f"{label} entry", 180) for v in values]


def load_config(config_path=CONFIG):
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is needed: python3 -m pip install 'PyYAML>=6,<7'") from exc

    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("editorial_config.yml must have version: 1")

    editor = data.get("editor")
    if not isinstance(editor, dict):
        raise ValueError("editor must be a mapping")   
    editor["purpose"] = _text(
        editor.get("purpose"), "editor.purpose", 1200, allow_newlines=True
    )
    editor["voice"] = _text(editor.get("voice"), "editor.voice", 1200)
    editor["avoid"] = _strings(editor.get("avoid"), "editor.avoid")

    topics = data.get("topics")
    if not isinstance(topics, list) or not topics:
        raise ValueError("topics must be a nonempty list")
    names, feeds = set(), set()
    enabled_count = 0
    for i, topic in enumerate(topics, 1):
        if not isinstance(topic, dict):
            raise ValueError(f"topics[{i}] must be a mapping")
        name = _text(topic.get("name"), f"topics[{i}].name", 70)
        if name in names or name == "Meta":
            raise ValueError(f"Duplicate or reserved category: {name!r}")
        names.add(name)
        enabled = topic.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"{name}.enabled must be true or false")
        topic["enabled"] = enabled
        if enabled:
            enabled_count += 1
        priority = topic.get("priority", "medium")
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"{name}.priority must be high, medium or low")
        topic["priority"] = priority
        topic["description"] = _text(topic.get("description", name), f"{name}.description", 600)
        topic["keywords"] = _strings(topic.get("keywords"), f"{name}.keywords")
        topic["avoid"] = _strings(topic.get("avoid"), f"{name}.avoid")
        sources = topic.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError(f"{name}.sources must be a list")
        for j, source in enumerate(sources, 1):
            if not isinstance(source, dict):
                raise ValueError(f"{name}.sources[{j}] must be a mapping")
            source["name"] = _text(source.get("name"), f"{name}.sources[{j}].name", 80)
            url = _text(source.get("url"), f"{name}.sources[{j}].url", 1200)
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError(f"{name}.sources[{j}].url needs a public http(s) address")
            if url in feeds:
                # Duplicate URLs used in different categories are supported by the old collector.
                pass
            feeds.add(url)
            flags = _strings(source.get("flags"), f"{name}.sources[{j}].flags")
            for flag in flags:
                if "," in flag or "#" in flag:
                    raise ValueError(f"{name}.sources[{j}]: flags cannot contain comma or #")
                if flag not in VALID_FLAGS and not re.fullmatch(r"(?:sample|embargo):\d+", flag) and not flag.startswith("skip:"):
                    raise ValueError(f"Unknown source flag {flag!r} in {name}")
                if flag.startswith("skip:"):
                    try:
                        re.compile(flag.split(":", 1)[1].replace(";", "|"))
                    except re.error as exc:
                        raise ValueError(f"Invalid skip expression in {name}: {exc}") from exc
            source["flags"] = flags
            source["url"] = url
    if not enabled_count:
        raise ValueError("At least one category must be enabled")
    return data


def category_names():
    """Checker keeps historical category names permitted even if currently disabled."""
    return {topic["name"] for topic in load_config()["topics"]} | SPECIAL_CATEGORIES


def render_sources(config):
    lines = ["# GENERATED from editorial_config.yml by editorial_control.py.",
             "# Edit editorial_config.yml, not this file.",
             "# category | source | RSS/Atom URL | optional flags", ""]
    for topic in config["topics"]:
        if not topic["enabled"]:
            continue
        lines.append(f"# {topic['name']} | priority: {topic['priority']}")
        for src in topic["sources"]:
            if "#" in src["url"] or "|" in src["url"]:
                raise ValueError(f"URL for {src['name']} cannot contain # or | in legacy collector format")
            line = f"{topic['name']} | {src['name']} | {src['url']}"
            if src["flags"]:
                line += " | " + ", ".join(src["flags"])
            lines.append(line)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_profile(config):
    ed = config["editor"]
    lines = ["# Kuriosity Kronicles editorial profile", "",
             "<!-- GENERATED from editorial_config.yml. Edit that file, not this one. -->", "",
             ed["purpose"], ""]
    for priority in ("high", "medium", "low"):
        group = [t for t in config["topics"] if t["enabled"] and t["priority"] == priority]
        if not group:
            continue
        lines.extend([f"## {priority.title()} priority", ""])
        for t in group:
            lines.append(f"- **{t['name']}**: {t['description']}")
            if t["keywords"]:
                lines.append("  Interesting signals: " + "; ".join(t["keywords"]) + ".")
            if t["avoid"]:
                lines.append("  Deprioritize: " + "; ".join(t["avoid"]) + ".")
        lines.append("")
    lines.extend(["## Avoid or minimize", ""])
    lines.extend(f"- {item}" for item in ed["avoid"])
    lines.extend(["", "## Editorial mix", "",
                  "- Choose up to 8 per edition; fewer if nothing merits publication.",
                  "- At most 2 per category per edition; don't manufacture a balanced mix.",
                  "- Prefer high-priority categories when equally good stories compete.",
                  "- Read only from sanitized candidates.json; do not browse the web.",
                  "- Avoid duplicate stories, and follow the existing RUN.md contract.",
                  "", "## Voice", "", ed["voice"], ""])
    return "\n".join(lines)


def sync(config_path=CONFIG, root=ROOT):
    config = load_config(config_path)
    targets = {
        root / "collector" / "sources.txt": render_sources(config),
        root / "profile.md": render_profile(config),
    }
    # Validate everything before changing either generated file.
    updates = [p for p, content in targets.items() if not p.exists() or p.read_text(encoding="utf-8") != content]
    for path in updates:
        path.write_text(targets[path], encoding="utf-8")
        print("Updated", path.relative_to(root))
    if not updates:
        print("Editorial settings are already synchronized")
    print(f"Active categories: {sum(t['enabled'] for t in config['topics'])}; RSS sources: "
          f"{sum(len(t['sources']) for t in config['topics'] if t['enabled'])}")
    return updates


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate and sync Kuriosity Kronicles editorial settings")
    parser.add_argument("command", choices=("validate", "sync"))
    args = parser.parse_args()
    if args.command == "sync":
        sync()
    else:
        cfg = load_config()
        print(f"Valid configuration: {len(cfg['topics'])} categories")
