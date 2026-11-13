#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline link check for a built static site (site/dist; backlog CORE-WEB-1 "0 broken links").

For every HTML page it checks each href, src, srcset and poster:
  * same-site links (relative or root-relative, under --base) must resolve to a file in the build,
    a directory with index.html, and a #fragment must name an id (or <a name>) on the target page;
  * links into this repository (--repo-url .../blob|tree|edit|raw/main/<path>) must name a path that
    exists in the checkout (--repo-root), so docs and "Edit page" links cannot rot when files move;
  * other external links are counted, not fetched: the check stays deterministic and offline.

  python3 -I scripts/check-links.py site/dist [--base /] [--repo-url URL --repo-root .]
Exit 0 when nothing is broken, 1 with one line per broken link, 2 on bad input.
"""
import argparse
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "blob:")
URL_ATTRS = ("href", "src", "poster", "xlink:href")


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        if tag == "link" and (a.get("rel") or "").lower() in ("preconnect", "dns-prefetch"):
            return
        for k in URL_ATTRS:
            if a.get(k) is not None:
                self.links.append(a[k].strip())
        if a.get("srcset"):
            self.links += [c.strip().split()[0] for c in a["srcset"].split(",") if c.strip()]


def parse(path: Path) -> Page:
    p = Page()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    return p


class Checker:
    def __init__(self, dist: Path, base: str, repo_url: str | None, repo_root: Path | None):
        self.dist, self.base = dist.resolve(), "/" + base.strip("/") + ("/" if base.strip("/") else "")
        self.repo = repo_url.rstrip("/") if repo_url else None
        self.repo_root = repo_root.resolve() if repo_root else None
        self.pages: dict[Path, Page] = {}
        self.external = 0
        self.repo_links = 0

    def page(self, f: Path) -> Page:
        if f not in self.pages:
            self.pages[f] = parse(f)
        return self.pages[f]

    def target(self, url_path: str) -> Path | None:
        """Map a site path (already without the base) to a file in the build, or None."""
        rel = unquote(url_path).lstrip("/")
        f = (self.dist / rel).resolve()
        if f != self.dist and self.dist not in f.parents:
            return None
        if url_path.endswith("/") or f.is_dir():
            f = f / "index.html"
        return f if f.is_file() else None

    def check_repo(self, url: str) -> str | None:
        m = re.match(re.escape(self.repo) + r"/(blob|tree|edit|raw)/main/(.+)$", url.split("#")[0].split("?")[0])
        if not m:
            self.external += 1
            return None
        self.repo_links += 1
        rel = PurePosixPath(unquote(m.group(2)).rstrip("/"))
        if ".." in rel.parts:
            return "repository path escapes the checkout"
        return None if (self.repo_root / rel).exists() else f"no '{rel}' in the repository"

    def check(self, page_file: Path, link: str) -> str | None:
        if not link or link == "#" or link.lower().startswith(SKIP_SCHEMES):
            return None
        parts = urlsplit(link)
        if parts.scheme in ("http", "https") or link.startswith("//"):
            if self.repo and self.repo_root and link.startswith(self.repo + "/"):
                return self.check_repo(link)
            self.external += 1
            return None
        if parts.scheme:
            return None
        if not parts.path:  # "#fragment" on the same page
            target = page_file
        else:
            page_url = "/" + page_file.relative_to(self.dist).as_posix()
            path = parts.path if parts.path.startswith("/") else os.path.normpath(
                os.path.join(os.path.dirname(page_url), parts.path)) + ("/" if parts.path.endswith("/") else "")
            if not path.startswith(self.base):
                return f"outside the site base {self.base}"
            target = self.target(path[len(self.base) - 1:])
            if target is None:
                return "no such file in the build"
        if parts.fragment and target.suffix == ".html":
            frag = unquote(parts.fragment)
            if frag not in self.page(target).ids:
                return f"no id '{frag}' on {target.relative_to(self.dist).as_posix()}"
        return None

    def run(self) -> list[str]:
        broken = []
        for f in sorted(self.dist.rglob("*.html")):
            for link in self.page(f).links:
                why = self.check(f, link)
                if why:
                    broken.append(f"{f.relative_to(self.dist).as_posix()}: {link} ({why})")
        return broken


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dist", type=Path)
    ap.add_argument("--base", default=os.environ.get("BASE_PATH") or "/", help="site base path (BASE_PATH)")
    ap.add_argument("--repo-url", help="links under <repo-url>/(blob|tree|edit|raw)/main/ are checked against --repo-root")
    ap.add_argument("--repo-root", type=Path)
    a = ap.parse_args(argv)
    if not (a.dist / "index.html").is_file():
        print(f"error: {a.dist}/index.html not found (build the site first)", file=sys.stderr)
        return 2
    if bool(a.repo_url) != bool(a.repo_root):
        print("error: --repo-url and --repo-root go together", file=sys.stderr)
        return 2
    c = Checker(a.dist, a.base, a.repo_url, a.repo_root)
    broken = c.run()
    for b in broken:
        print(f"BROKEN {b}")
    links = sum(len(p.links) for p in c.pages.values())
    print(f"{'FAILED' if broken else 'ok'}: {len(c.pages)} pages, {links} links, {len(broken)} broken, "
          f"{c.repo_links} repository links checked, {c.external} external links not fetched")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
