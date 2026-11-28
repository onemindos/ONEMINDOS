# SPDX-License-Identifier: Apache-2.0
"""The Kiwix library catalogue (OPDS 1.2) and the book paths the Kiwix app's `zims` setting takes.

The catalogue at opds.library.kiwix.org lists every ZIM file with its size: each `<entry>` has a
`<name>` (for example `wikipedia_en_medicine`), a `<flavour>` (mini, nopic, maxi or empty) and an
acquisition link `https://…/zim/<folder>/<file>.zim.meta4 length="<bytes>"`. That `<folder>/<file>.zim`
is exactly what apps/kiwix/manifests/library-sync.sh downloads, checks against the mirror's .sha256
file and serves. Sources: `GET https://opds.library.kiwix.org/catalog/v2/entries?name=…` (read
2026-11-19; library.kiwix.org answers 301 to that host) and apps/kiwix/onemind.app.yaml.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass

CATALOG_URL = "https://opds.library.kiwix.org/catalog/v2/entries"
MAX_FEED_BYTES = 4 * 1024 * 1024
CACHE_S = 3600.0

_ATOM = "{http://www.w3.org/2005/Atom}"
# The same rule library-sync.sh applies before it downloads anything.
ZIM_PATH_RE = re.compile(r"^[a-z0-9_-]+/[A-Za-z0-9_.-]+\.zim$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
FLAVOUR_RE = re.compile(r"^[a-z0-9-]{0,20}$")
_HREF_RE = re.compile(r"/zim/([a-z0-9_-]+/[A-Za-z0-9_.-]+\.zim)(?:\.meta4)?$")
_DATED_RE = re.compile(r"^(?P<key>[a-z0-9_-]+/[A-Za-z0-9_.-]+?)_(?P<date>\d{4}-\d{2})\.zim$")


class CatalogError(Exception):
    """The catalogue could not be read (offline box, mirror down, unexpected answer)."""


@dataclass(frozen=True)
class Book:
    name: str
    flavour: str
    title: str
    language: str
    path: str  # <folder>/<file>.zim, what the `zims` setting lists
    size_bytes: int
    issued: str

    @property
    def key(self) -> str:
        return book_key(self.path)

    def to_json(self) -> dict:
        return asdict(self)


def book_key(path: str) -> str:
    """`wikipedia/wikipedia_en_medicine_maxi_2026-10.zim` -> `wikipedia/wikipedia_en_medicine_maxi`.

    The key names one book across its monthly releases, so a newer date is an update of it.
    A path without a `_YYYY-MM` date is its own key.
    """
    m = _DATED_RE.match(path)
    return m.group("key") if m else path.removesuffix(".zim")


def book_date(path: str) -> str | None:
    m = _DATED_RE.match(path)
    return m.group("date") if m else None


def ref_key(folder: str, name: str, flavour: str) -> str:
    return f"{folder}/{name}_{flavour}" if flavour else f"{folder}/{name}"


def parse_feed(data: bytes) -> list[Book]:
    """The books of one OPDS acquisition feed. Entries without a usable ZIM link are skipped."""
    if len(data) > MAX_FEED_BYTES:
        raise CatalogError("the catalogue answer is too large")
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:  # no entity expansion from a remote document
        raise CatalogError("the catalogue answer has a document type declaration")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise CatalogError(f"the catalogue answer is not valid XML ({exc})") from None
    if root.tag != _ATOM + "feed":
        raise CatalogError("the catalogue answer is not an OPDS feed")
    books = []
    for e in root.findall(_ATOM + "entry"):
        name = (e.findtext(_ATOM + "name") or "").strip()
        flavour = (e.findtext(_ATOM + "flavour") or "").strip()
        if not NAME_RE.match(name) or not FLAVOUR_RE.match(flavour):
            continue
        for link in e.findall(_ATOM + "link"):
            if link.get("type") != "application/x-zim":
                continue
            m = _HREF_RE.search(urllib.parse.urlsplit(link.get("href") or "").path)
            length = link.get("length") or ""
            if not m or not length.isdigit() or int(length) <= 0 or not ZIM_PATH_RE.match(m.group(1)):
                continue
            books.append(Book(
                name=name, flavour=flavour, title=(e.findtext(_ATOM + "title") or name).strip()[:200],
                language=(e.findtext(_ATOM + "language") or "").strip()[:20], path=m.group(1),
                size_bytes=int(length), issued=(e.findtext("{http://purl.org/dc/terms/}issued") or "").strip()[:40],
            ))
            break
    return books


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # the catalogue host is fixed: a redirect is an error
        return None


def http_fetch(url: str) -> bytes:
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "onemind-content/1", "Accept": "application/atom+xml"})
    try:
        with opener.open(req, timeout=20) as resp:
            data = resp.read(MAX_FEED_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise CatalogError(f"the Kiwix catalogue answered HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CatalogError(f"the Kiwix catalogue cannot be reached ({getattr(exc, 'reason', exc)})") from None
    return data


class KiwixCatalog:
    """Newest release of each (name, flavour), read live from the catalogue and kept for an hour."""

    def __init__(self, fetch: Callable[[str], bytes] = http_fetch, base_url: str = CATALOG_URL):
        self.fetch = fetch
        self.base_url = base_url
        self._cache: dict[str, tuple[float, list[Book]]] = {}
        self._lock = threading.Lock()

    def books(self, name: str) -> list[Book]:
        if not NAME_RE.match(name):
            raise CatalogError(f"{name!r} is not a catalogue name")
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(name)
            if hit and now - hit[0] < CACHE_S:
                return hit[1]
        url = f"{self.base_url}?{urllib.parse.urlencode({'name': name, 'count': 50})}"
        newest: dict[str, Book] = {}
        for b in parse_feed(self.fetch(url)):
            if b.name != name:  # the filter is a search on the server; keep exact matches only
                continue
            have = newest.get(b.flavour)
            if have is None or (book_date(b.path) or "") > (book_date(have.path) or ""):
                newest[b.flavour] = b
        out = sorted(newest.values(), key=lambda b: b.size_bytes)
        with self._lock:
            self._cache[name] = (now, out)
        return out

    def book(self, name: str, flavour: str) -> Book | None:
        return next((b for b in self.books(name) if b.flavour == flavour), None)
