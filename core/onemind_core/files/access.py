# SPDX-License-Identifier: Apache-2.0
"""Who may read or write which space (contract §12.6 roles; docs/umbrel2/files-backups.md §4.3).

Roots are ids, never host paths: `home:<person_id>` (a person's own files) and `shared` (the
household folder). People:

| Role    | Own Home   | Shared     |
|---------|------------|------------|
| owner   | read-write | read-write |
| adult   | read-write | read-write |
| child   | read-write | read-only  |
| guest   | none       | read-only  |
| other   | none       | none       |  (unknown roles are the least privileged, §12.6)

Nobody reads another person's Home through FILES, the owner included: a Home is private.
Agents (and apps) reach files only through approved folder grants (service.py), read-only
unless the owner approved read-write. Until the identity stream (§12.6) lands, people are the
`kind: person` principals of the tokens file and their id is the principal id.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..auth import Principal
from .errors import FilesError

HOME_ROLES = frozenset({"owner", "adult", "child"})
SHARED_WRITE_ROLES = frozenset({"owner", "adult"})
SHARED_READ_ROLES = frozenset({"owner", "adult", "child", "guest"})


@dataclass(frozen=True)
class Root:
    kind: str                # home | shared
    person_id: str | None    # for home

    @property
    def id(self) -> str:
        return f"home:{self.person_id}" if self.kind == "home" else "shared"


@dataclass(frozen=True)
class Access:
    read: bool = False
    write: bool = False

    @property
    def label(self) -> str | None:
        return "rw" if self.write else ("r" if self.read else None)


NONE = Access()
READ = Access(read=True)
READ_WRITE = Access(read=True, write=True)


def parse_root(root: str | None) -> Root:
    if not root:
        raise FilesError(422, "conflict", "root is required (home:<person_id> or shared)", reason="invalid_root")
    if root == "shared":
        return Root("shared", None)
    kind, sep, rest = root.partition(":")
    if kind == "home" and sep and rest and len(rest) <= 200 and rest.isprintable():
        return Root("home", rest)
    raise FilesError(422, "conflict", f"unknown root {root[:60]!r}", reason="invalid_root")


def is_person(p: Principal) -> bool:
    return p.kind == "person"


def has_home(p: Principal) -> bool:
    return is_person(p) and p.role in HOME_ROLES


def person_access(p: Principal, root: Root) -> Access:
    """What a person may do in a root by role alone (grants do not apply to people)."""
    if not is_person(p):
        return NONE
    if root.kind == "home":
        return READ_WRITE if root.person_id == p.id and p.role in HOME_ROLES else NONE
    if p.role in SHARED_WRITE_ROLES:
        return READ_WRITE
    if p.role in SHARED_READ_ROLES:
        return READ
    return NONE
