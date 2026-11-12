"""Static bearer-token principals (v0 shortcut; Kanidm/OIDC replaces this, BD-03 / D-B9.1).

ONEMIND_TOKENS_FILE is YAML. Two accepted shapes:

    tokens:
      "<token>": {id: owner, kind: person, role: owner}
      "sha256:<hex of token>": {id: hermes, kind: agent, role: agent}

or a list:

    tokens:
      - {token: "<token>", id: owner, kind: person, role: owner}

A key starting with "sha256:" stores only the hash, so the file need not hold the secret.
Tokens are looked up by their sha256, which keeps the comparison timing-safe.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger("onemind.auth")

KINDS = {"person", "agent"}
ROLES = {"owner", "adult", "guest", "agent"}


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


class TokenStore:
    """Loads the tokens file and reloads it when its mtime changes."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._by_hash: dict[str, Principal] = {}
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
                by_hash = parse_tokens(yaml.safe_load(self.path.read_text()))
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
            self._by_hash, self._mtime = by_hash, mtime
            log.info("loaded %d principals from tokens file", len(self._by_hash))

    def lookup(self, token: str) -> Principal | None:
        if not token:
            return None
        self._reload_if_changed()
        return self._by_hash.get(_hash(token))
