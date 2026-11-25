# SPDX-License-Identifier: Apache-2.0
"""A disposable wikilink index beside each person's Notes vault."""

from __future__ import annotations

import json
import os
import posixpath
import re
from collections import defaultdict
from collections.abc import Iterator

from ..auth import Principal
from . import paths
from .errors import FilesError
from .notes import MAX_NOTE_BYTES, VAULT, NotesVault, _identity, _note_parts, _read_data, _write_temp

_INDEX_NAME = "links-v1.json"
_MAX_INDEX_BYTES = 16 * 1024 * 1024
_FENCE = re.compile(r"^ {0,3}([`~])\1{2,}")
_CODE_RUN = re.compile(r"`+")
_WIKILINK = re.compile(r"(?<!\\)\[\[([^\[\]\n]+)\]\]")


def _plain_spans(line: str) -> Iterator[str]:
    runs = list(_CODE_RUN.finditer(line))
    next_by_size = {}
    closer = {}
    for run in reversed(runs):
        size = run.end() - run.start()
        if size in next_by_size:
            closer[run.start()] = next_by_size[size]
        next_by_size[size] = run.end()
    start = 0
    for run in runs:
        if run.start() >= start and run.start() in closer:
            yield line[start:run.start()]
            start = closer[run.start()]
    yield line[start:]


def wikilinks(markdown: str) -> list[str]:
    targets = set()
    fence = None
    for line in markdown.splitlines():
        marker = _FENCE.match(line)
        if marker:
            run = marker.group().lstrip()
            if fence is None:
                fence = run
                continue
            if run.startswith(fence) and not line[marker.end():].strip():
                fence = None
                continue
        if fence is None:
            for span in _plain_spans(line):
                for link in _WIKILINK.findall(span):
                    target = link.split("|", 1)[0].split("#", 1)[0].strip()
                    if target:
                        targets.add(target)
    return sorted(targets)


def _resolve_links(links: dict[str, list[str]]) -> dict[str, list[str]]:
    by_name = defaultdict(list)
    backlinks = defaultdict(set)
    for path in links:
        by_name[posixpath.basename(path)].append(path)
    for source, targets in links.items():
        directory = posixpath.dirname(source)
        for target in targets:
            if not target.lower().endswith(".md"):
                target += ".md"
            if target.startswith(("./", "../")) or "/" not in target:
                candidate = posixpath.normpath(posixpath.join(directory, target))
                # Normalising at '/' must not turn a link above the vault into a valid path.
                relative = posixpath.normpath(posixpath.join(directory.lstrip("/"), target))
                if relative.startswith("../"):
                    continue
                if candidate not in links and "/" not in target and len(by_name[target]) == 1:
                    candidate = by_name[target][0]
            else:
                candidate = "/" + target.lstrip("/")
            if candidate in links and candidate != source:
                backlinks[candidate].add(source)
    return {path: sorted(sources) for path, sources in backlinks.items()}


def _inventory(vault_fd: int) -> Iterator[tuple[str, list[int]]]:
    for base, dirs, names, folder in os.fwalk(".", dir_fd=vault_fd, follow_symlinks=False):
        dirs[:] = sorted(name for name in dirs if paths.is_utf8(name) and not name.startswith("."))
        relative = "" if base == "." else base.removeprefix("./")
        for name in sorted(names):
            try:
                parts = _note_parts(posixpath.join(relative, name))
                st = os.stat(name, dir_fd=folder, follow_symlinks=False)
            except (FileNotFoundError, paths.PathRefused):
                continue
            if paths.kind_of(st) == "file" and st.st_size <= MAX_NOTE_BYTES:
                yield paths.join(parts), list(_identity(st))


def _markdown(vault_fd: int, path: str) -> str | None:
    parts = _note_parts(path)
    try:
        with paths.dir_at(vault_fd, parts[:-1]) as folder:
            fd, _ = paths.open_file_at(folder, parts[-1])
            try:
                return _read_data(fd).decode("utf-8")
            finally:
                os.close(fd)
    except UnicodeDecodeError:
        return None
    except FilesError as exc:
        if exc.status in (404, 413) or exc.reason in {"symlink", "not_a_file", "not_a_folder"}:
            return None
        raise


def _cached(work: int) -> dict:
    try:
        fd, _ = paths.open_file_at(work, _INDEX_NAME)
    except FilesError as exc:
        if exc.status != 404:
            raise
        return {}
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(_MAX_INDEX_BYTES + 1)
    if len(raw) > _MAX_INDEX_BYTES:
        return {}
    try:
        index = json.loads(raw)
    except ValueError:
        return {}
    return index if isinstance(index, dict) else {}


class NotesIndex:
    def __init__(self, vault: NotesVault):
        self.vault = vault

    def rebuild(self, person: Principal) -> dict[str, list[str]]:
        return self._backlinks(person, rebuild=True)

    def backlinks(self, person: Principal, path: str) -> list[str]:
        key = paths.join(_note_parts(path))
        return self._backlinks(person, rebuild=False).get(key, [])

    def _backlinks(self, person: Principal, *, rebuild: bool) -> dict[str, list[str]]:
        t = self.vault._target(person)
        try:
            with self.vault._work(t) as work, self.vault.files._space(t.root) as space:
                with paths.dir_at(space, (VAULT,)) as vault_fd:
                    inventory = dict(_inventory(vault_fd))
                    index = {} if rebuild else _cached(work)
                    if index.get("files") == inventory and isinstance(index.get("backlinks"), dict):
                        return index["backlinks"]
                    links = {}
                    for path in inventory:
                        markdown = _markdown(vault_fd, path)
                        if markdown is not None:
                            links[path] = wikilinks(markdown)
                    backlinks = _resolve_links(links)
                raw = json.dumps({"files": inventory, "backlinks": backlinks}, sort_keys=True).encode("utf-8")
                if len(raw) <= _MAX_INDEX_BYTES:
                    name = _write_temp(work, raw)
                    try:
                        os.replace(name, _INDEX_NAME, src_dir_fd=work, dst_dir_fd=work)
                    except OSError:
                        os.unlink(name, dir_fd=work)
                        raise
                return backlinks
        except FilesError as exc:
            if exc.status == 404:
                return {}
            raise
        except OSError as exc:
            raise paths.os_error(exc) from None

    def search(self, person: Principal, query: str, *, limit: int = 25) -> list[str]:
        t = self.vault._target(person)
        needle = query.strip().casefold()
        if not needle or limit <= 0:
            return []
        matches = []
        try:
            with self.vault.files._space(t.root) as space, paths.dir_at(space, (VAULT,)) as vault_fd:
                for path, _ in _inventory(vault_fd):
                    markdown = _markdown(vault_fd, path)
                    if markdown is not None and (needle in path.casefold() or needle in markdown.casefold()):
                        matches.append(path)
                        if len(matches) >= min(limit, 100):
                            break
        except FilesError as exc:
            if exc.status != 404:
                raise
        except OSError as exc:
            raise paths.os_error(exc) from None
        return matches
