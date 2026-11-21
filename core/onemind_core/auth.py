"""Static bearer-token principals (v0 shortcut; Kanidm/OIDC replaces this, BD-03 / D-B9.1).

ONEMIND_TOKENS_FILE is YAML. Two accepted shapes:

    tokens:
      "<token>": {id: owner, kind: person, role: owner}
      "sha256:<hex of token>": {id: hermes, kind: agent, role: agent}

or a list:

    tokens:
      - {token: "<token>", id: owner, kind: person, role: owner}

An entry may carry `retire_on_setup: true` (onemind-firstboot sets it on the first-boot owner token): the
gateway stops accepting that token on the API once the first owner account exists (SECURITY.md §3.2,
break-glass). The file entry stays, so the rescue console still signs in with it (D-008).

A key starting with "sha256:" stores only the hash, so the file need not hold the secret.
Tokens are looked up by their sha256, which keeps the comparison timing-safe.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger("onemind.auth")

KINDS = {"person", "agent"}
ROLES = {"owner", "adult", "guest", "child", "agent"}


@dataclass(frozen=True)
class Principal:
    id: str
    kind: str
    role: str

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "role": self.role}

    @property
    def is_owner(self) -> bool:
        # An agent can never act as an owner, whatever its configured role (no self-approval).
        return self.kind == "person" and self.role == "owner"

    @property
    def can_request_actions(self) -> bool:
        # Contract §12.1: an automation rule requests as automation:<rule-id> and never approves.
        return self.is_owner or (self.kind, self.role) in (("agent", "agent"), ("automation", "automation"))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


token_hash = _hash


def new_agent_token() -> str:
    """A fresh 256-bit bearer token for an app's agent principal (§11.2)."""
    return secrets.token_urlsafe(32)


def agent_principal(principal_id: str) -> Principal:
    return Principal(id=principal_id, kind="agent", role="agent")


def _principal(entry: dict, where: str) -> Principal:
    try:
        p = Principal(id=str(entry["id"]), kind=str(entry["kind"]), role=str(entry["role"]))
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{where}: principal needs id, kind, role") from exc
    if p.kind not in KINDS:
        raise ValueError(f"{where}: kind must be one of {sorted(KINDS)}")
    if p.role not in ROLES:
        raise ValueError(f"{where}: role must be one of {sorted(ROLES)}")
    if (p.kind == "agent") != (p.role == "agent"):
        raise ValueError(f"{where}: kind 'agent' goes with role 'agent' and only with it")
    return p


def parse_tokens(doc: object) -> dict[str, Principal]:
    if not isinstance(doc, dict) or "tokens" not in doc:
        raise ValueError("tokens file must be a mapping with a 'tokens' key")
    raw = doc["tokens"] or {}
    out: dict[str, Principal] = {}
    if isinstance(raw, dict):
        items = [(k, v) for k, v in raw.items()]
    elif isinstance(raw, list):
        items = []
        for i, e in enumerate(raw):
            if not isinstance(e, dict) or "token" not in e:
                raise ValueError(f"tokens[{i}]: needs a 'token' field")
            items.append((e["token"], e))
    else:
        raise ValueError("'tokens' must be a mapping or a list")
    for i, (key, entry) in enumerate(items):
        key = str(key)
        if key.startswith("sha256:"):
            digest = key[len("sha256:"):].lower()
            if len(digest) != 64:
                raise ValueError(f"tokens entry {i}: bad sha256 digest")
        else:
            if len(key) < 16:
                raise ValueError(f"tokens entry {i}: token shorter than 16 characters")
            digest = _hash(key)
        out[digest] = _principal(entry, f"tokens entry {i}")
    return out


def parse_retiring(doc: object) -> set[str]:
    """sha256 hex of every entry flagged `retire_on_setup: true`. Call after parse_tokens succeeded."""
    raw = doc["tokens"] or {}  # type: ignore[index]
    items = list(raw.items()) if isinstance(raw, dict) else [(e["token"], e) for e in raw]
    out: set[str] = set()
    for key, entry in items:
        if entry.get("retire_on_setup") is True:
            key = str(key)
            out.add(key[len("sha256:"):].lower() if key.startswith("sha256:") else _hash(key))
    return out


class TokenStore:
    """Loads the tokens file and reloads it when its mtime changes."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._by_hash: dict[str, Principal] = {}
        self._retiring: set[str] = set()
        # Set by the identity feature: True once the first owner account exists. Never goes back.
        self.retire_when: Callable[[], bool] | None = None
        self._retired = False
        self._reload_if_changed()

    def _reload_if_changed(self) -> None:
        if self.path is None:
            return
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            if self._mtime is not None or not self._by_hash:
                log.warning("tokens file not readable; every request will get 401")
            self._by_hash, self._mtime = {}, None
            return
        if mtime == self._mtime:
            return
        with self._lock:
            if mtime == self._mtime:
                return
            try:
                doc = yaml.safe_load(self.path.read_text())
                by_hash = parse_tokens(doc)
                retiring = parse_retiring(doc)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                # A bad edit or a half-written file must never turn into a 500. Keep the last good
                # principals (none at startup, so every request gets 401) and remember this mtime,
                # so the broken file is not parsed again on every request.
                log.error(
                    "tokens file is invalid (%s); keeping %d previously loaded principals",
                    exc.__class__.__name__, len(self._by_hash),
                )
                self._mtime = mtime
                return
            self._by_hash, self._retiring, self._mtime = by_hash, retiring, mtime
            log.info("loaded %d principals from tokens file", len(self._by_hash))

    def principals(self) -> list[Principal]:
        """Every principal in the file (never a token), e.g. to find the owners to notify."""
        self._reload_if_changed()
        return list(self._by_hash.values())

    def entries(self) -> list[tuple[str, Principal]]:
        """(sha256 hex, principal) of every loaded file token, for read-only listing (§12.6)."""
        self._reload_if_changed()
        return sorted(((h, p) for h, p in self._by_hash.items() if not self._is_retired(h)),
                      key=lambda kv: kv[1].id)

    def has_retiring(self) -> bool:
        self._reload_if_changed()
        return bool(self._retiring)

    def _is_retired(self, digest: str) -> bool:
        if digest not in self._retiring:
            return False
        if not self._retired and self.retire_when is not None:
            try:
                self._retired = bool(self.retire_when())
            except Exception:  # a database hiccup must not re-enable a retired token, nor 500 a request
                log.exception("could not check whether the first-boot token is retired")
        return self._retired

    def lookup(self, token: str, *, include_retired: bool = False) -> Principal | None:
        """The principal for a bearer token. A first-boot token is None once the first owner account
        exists, unless include_retired (only POST /v1/auth/setup asks, to answer 409 not 401)."""
        if not token:
            return None
        self._reload_if_changed()
        digest = _hash(token)
        p = self._by_hash.get(digest)
        if p is not None and not include_retired and self._is_retired(digest):
            return None
        return p
