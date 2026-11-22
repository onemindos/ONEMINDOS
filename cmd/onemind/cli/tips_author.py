# SPDX-License-Identifier: Apache-2.0
"""Authoring commands for the OneMind tips pack. Invoked by the CLI and CI."""
import argparse
import html
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

try:
    import yaml
except ImportError:
    sys.exit("Tips authoring needs PyYAML. Run tips/author from the checkout to set it up.")

SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
ASSET_URL = "https://github.com/onemindos/ONEMINDOS/releases/download"
CLIP_BYTES, PACK_BYTES = 3_000_000, 80_000_000


def require(test, message):
    if not test:
        raise ValueError(message)


def check_body(body):
    sentences = re.split(r"[.!?]+(?:\s+|$)", body)
    require(1 <= sum(bool(s.strip()) for s in sentences) <= 4, "write one to four sentences")


def routes(root):
    screens = root / "dashboard/src/screens"
    web = set()
    for source in screens.glob("*/screen.ts"):
        web.update(re.findall(r"""\bpath:\s*['"](/[^'"]*)['"]""", source.read_text()))
    if "/settings/:section" in web:
        web.remove("/settings/:section")
        for source in (screens / "settings-pages").glob("*.ts"):
            web.update("/settings/" + s for s in re.findall(r"""\bid:\s*['"]([^'"]+)['"]""", source.read_text()))
    app = (root / "mobile/App.tsx").read_text()
    linking = re.search(r"const linking\b.*?=\s*\{(.*?)^\};", app, re.M | re.S)
    require(linking, "cannot read the mobile linking configuration")
    prefixes, _, config = linking[1].partition("screens:")
    require(config and "onemind://" in prefixes, "cannot read the mobile deep links")
    phone = {"onemind://" + p for p in re.findall(r"""\b\w+:\s*['"]([^'"]+)['"]""", config)}
    require(web and phone, "screen registries are empty")
    return {"dashboard": web, "phone": phone}


def matches_route(value, choices):
    if value in choices:
        return ":" not in value.removeprefix("onemind://")
    return any(re.fullmatch("/".join(r"[A-Za-z0-9_-]+" if part.startswith(":") else re.escape(part)
                                     for part in route.split("/")), value) for route in choices)


def check_metadata(meta, schema, collections, links):
    require(isinstance(meta, dict), "expected front matter")
    require(set(schema["required"]) <= meta.keys() <= schema["properties"].keys(), "missing or unknown front matter field")
    for key in ("title", "collection", "from"):
        require(isinstance(meta[key], str) and meta[key].strip(), f"invalid {key}")
    require(meta["collection"] in collections, f"unknown collection {meta['collection']}")
    for key in ("from", "until"):
        if key in meta:
            require(isinstance(meta[key], str) and re.fullmatch(VERSION, meta[key]), f"invalid {key} OS version")
    if "until" in meta:
        require(tuple(map(int, meta["from"].split("."))) <= tuple(map(int, meta["until"].split("."))), "reversed OS range")
    require(isinstance(meta["opens"], dict) and meta["opens"].keys() == links.keys(), "opens needs dashboard and phone")
    for surface, path in meta["opens"].items():
        require(isinstance(path, str) and matches_route(path, links[surface]), f"dead {surface} link {path}")
    events = meta.get("skip_if_done", [])
    require(isinstance(events, list) and all(isinstance(e, str) and re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", e) for e in events)
            and len(events) == len(set(events)), "invalid skip_if_done events")
    if "clip" in meta:
        clip = meta["clip"]
        require(isinstance(clip, dict) and clip.keys() == {"release", "caption"}
                and isinstance(clip["caption"], str) and clip["caption"].strip(), "clip needs a hand-written caption")
        require(isinstance(clip["release"], str) and re.fullmatch(SLUG, clip["release"]), "invalid clip release tag")


def media(stem, clip, assets):
    require(shutil.which("ffmpeg") and shutil.which("ffprobe"), "clip tools missing: install ffmpeg (brew install ffmpeg on Mac)")
    total, sources = 0, {}
    with tempfile.TemporaryDirectory() as temporary:
        for ext in ("mp4", "webm", "jpg"):
            name = f"{stem}.{ext}"
            release = clip["release"]
            if assets:
                path = assets / release / name
                sources[ext] = path.resolve().as_uri()
            else:
                sources[ext] = f"{ASSET_URL}/{release}/{name}"
                path = Path(temporary) / name
                with urlopen(sources[ext], timeout=20) as response:
                    path.write_bytes(response.read(CLIP_BYTES + 1))
            size = path.stat().st_size
            require(0 < size <= CLIP_BYTES, f"{name} must be at most 3 MB")
            total += size
            if ext == "jpg":
                require(path.read_bytes().startswith(b"\xff\xd8\xff"), f"{name} is not a JPEG poster")
                continue
            result = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-f",
                                     "mov" if ext == "mp4" else "matroska", "-show_entries",
                                     "stream=codec_type:format=duration", "-of", "json", str(path)],
                                    check=True, capture_output=True, text=True, timeout=20)
            info = json.loads(result.stdout)
            require([s["codec_type"] for s in info.get("streams", [])] == ["video"], f"{name} must contain one silent video")
            duration = float(info.get("format", {}).get("duration", "nan"))
            require(math.isfinite(duration) and 0 < duration <= 30, f"{name} must be at most 30 seconds")
    return sources, total


def validate(root, assets):
    tips = root / "tips"
    collections = yaml.safe_load((tips / "collections.yaml").read_text())
    require(isinstance(collections, dict) and collections and all(isinstance(k, str) and re.fullmatch(SLUG, k)
            and isinstance(v, str) and v.strip() for k, v in collections.items()), "invalid collections")
    schema = json.loads((tips / "frontmatter.schema.json").read_text())
    links, entries, total = routes(root), {}, 0
    require(not any(p.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"} for p in tips.rglob("*")), "put clips in release assets outside tips/")
    for path in sorted((tips / "entries").glob("*.md")):
        try:
            require(re.fullmatch(SLUG, path.stem), "invalid tip id")
            match = re.fullmatch(r"---\n(.+?)\n---\n(.+)", path.read_text(), re.S)
            require(match, "expected Markdown with YAML front matter")
            meta, body = yaml.safe_load(match[1]), match[2].strip()
            check_metadata(meta, schema, collections, links)
            check_body(body)
            sources = {}
            if "clip" in meta:
                sources, size = media(path.stem, meta["clip"], assets)
                total += size
                require(total <= PACK_BYTES, "the full media pack exceeds 80 MB")
            entries[path.stem] = meta, body, sources
        except (ValueError, OSError, yaml.YAMLError, subprocess.SubprocessError) as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
    require(entries, "no tip entries")
    checklist = yaml.safe_load((tips / "checklist.yaml").read_text())
    require(isinstance(checklist, list) and all(isinstance(k, str) and k in entries for k in checklist)
            and len(set(checklist)) == len(checklist), "checklist contains a missing or repeated tip")
    return entries, collections, links


def pick(label, choices):
    values = sorted(choices)
    for i, value in enumerate(values, 1):
        print(f"  {i}. {value}")
    answer = input(label + " (number): ").strip()
    require(answer.isdecimal() and 1 <= int(answer) <= len(values), f"choose a listed {label}")
    return values[int(answer) - 1]


def new(root, entries, collections, links):
    title = input("Tip title: ").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    require(slug and slug not in entries, "choose a unique title with letters or numbers")
    collection = pick("Collection", collections)
    opens = {k: pick(k, [s for s in paths if ":" not in s.removeprefix("onemind://")]) for k, paths in links.items()}
    version = input("First OS version: ").strip()
    require(re.fullmatch(VERSION, version), "use a version such as 0.1.0")
    body = input("Write one to four sentences: ").strip()
    check_body(body)
    path = root / "tips/entries" / (slug + ".md")
    with path.open("x") as out:
        out.write("---\n" + yaml.safe_dump(dict(title=title, collection=collection, opens=opens, **{"from": version}),
                                             allow_unicode=True, sort_keys=False) + "---\n" + body + "\n")
    print(f"Created {path.name}. Ask your agent to open a draft PR for review.")


def paragraph_html(paragraph):
    # The short tip format allows paragraphs with emphasis and inline code, never raw HTML.
    parts = re.split(r"(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*)", paragraph)
    for i in range(1, len(parts), 2):
        token = parts[i]
        marker, tag = ("**", "strong") if token.startswith("**") else (token[0], "code" if token[0] == "`" else "em")
        parts[i] = f"<{tag}>{html.escape(token[len(marker):-len(marker)])}</{tag}>"
    parts[::2] = [html.escape(s) for s in parts[::2]]
    return "<p>" + "".join(parts) + "</p>"


def preview(entries, collections):
    print('<!doctype html><html lang="en"><meta charset="utf-8"><title>OneMind Tips</title><main><h1>OneMind Tips</h1>')
    for key, label in collections.items():
        print("<section><h2>" + html.escape(label) + "</h2>")
        for slug, (meta, body, sources) in entries.items():
            if meta["collection"] != key:
                continue
            print(f'<article id="{slug}"><h3>{html.escape(meta["title"])}</h3>')
            for paragraph in re.split(r"\n\s*\n", body):
                print(paragraph_html(paragraph))
            if sources:
                attrs = {k: html.escape(v, quote=True) for k, v in sources.items()}
                caption = html.escape(" ".join(meta["clip"]["caption"].split()))
                vtt = quote("WEBVTT\n\n00:00:00.000 --> 00:00:30.000\n" + caption + "\n")
                print(f'<figure><video controls muted playsinline preload="none" poster="{attrs["jpg"]}" data-mp4="{attrs["mp4"]}" data-webm="{attrs["webm"]}">'
                      f'<track kind="captions" src="data:text/vtt;charset=utf-8,{vtt}" srclang="en" label="English" default></video>'
                      f'<figcaption>{caption}</figcaption></figure>')
            for surface, link in meta["opens"].items():
                print(f'<p>{surface}: <code>{html.escape(link)}</code></p>')
            print("</article>")
        print("</section>")
    print('</main><script>for (const v of document.querySelectorAll("video")) {'
          'if (v.canPlayType("video/webm")) v.src=v.dataset.webm; else if (v.canPlayType("video/mp4")) v.src=v.dataset.mp4;'
          '}</script></html>')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "new", "preview"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--assets", type=Path, help="directory of staged release assets, grouped by release tag")
    args = parser.parse_args()
    root = args.root or next((p for p in (Path.cwd(), *Path.cwd().parents) if (p / "tips/collections.yaml").is_file()), None)
    require(root, "run inside the OneMind checkout, or pass --root PATH")
    entries, collections, links = validate(root, args.assets)
    if args.command == "check":
        print(f"Checked {len(entries)} tips.")
    elif args.command == "new":
        new(root, entries, collections, links)
    else:
        preview(entries, collections)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, yaml.YAMLError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
