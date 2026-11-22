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
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger("onemind.auth")

KINDS = {"person", "agent"}
ROLES = {"owner", "adult", "guest", "child", "teen", "agent"}
# Scope strings an agent token may hold on /mcp: the vocabulary of docs/leap/dev/MCP.md §4.1.
# Only the scopes whose tools exist today are accepted; a string from the plan that is not built yet
# (docs:read, actions:withdraw:own, ...) is refused, never silently ignored. instance:read is
# always granted.
MCP_SCOPES = (
    "instance:read", "nodes:read", "apps:read", "actions:read:own", "audit:read:own",
    "actions:request:app.install", "actions:request:app.remove", "actions:request:app.start",
    "actions:request:app.stop", "actions:request:app.restart", "actions:request:app.update",
    "actions:request:app.configure", "actions:request:app.delete_data",
)
ALWAYS_GRANTED = frozenset({"instance:read"})
_READER = ("instance:read", "nodes:read", "apps:read", "actions:read:own", "audit:read:own")
# One scope per request_action type (the lifecycle.TYPES keys; a test keeps the two in step), so a
# token holds exactly the types it was granted and the rest are denied by default.
_REQUEST = tuple(x for x in MCP_SCOPES if x.startswith("actions:request:"))
_REQUESTER_REQUEST = ("actions:request:app.install", "actions:request:app.remove")
MCP_BUNDLES = {  # §4.1 named bundles, limited to what exists today
    "reader": frozenset(_READER),
    # §4.1: reader + exactly app.install and app.remove (actions:withdraw:own is not built yet).
    # Every other request type (start, stop, restart, update, configure, delete_data) is denied
    # by default; a token must be granted those scopes by name, or hold v0.
    "requester": frozenset(_READER + _REQUESTER_REQUEST),
    # Today's behaviour: every tool /mcp already serves (the §4.1 table lists fewer read scopes than
    # the shipped tools, so v0 here is the full shipped set, not a downgrade). Default with no `scopes:`.
    "v0": frozenset(MCP_SCOPES),
}


@dataclass(frozen=True)
class Principal:
    id: str
    kind: str
    role: str
    # MCP scopes of an agent token (tokens file `scopes`). None = the v0 bundle (the §4.1 default for agents with no `scopes:` field).
    scopes: frozenset[str] | None = field(default=None, compare=False)

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
    if "mcp_scopes" in entry:
        raise ValueError(f"{where}: the field is `scopes` (docs/leap/dev/MCP.md §4.1), not `mcp_scopes`")
    if "scopes" in entry:
        scopes = entry["scopes"]
        if p.kind != "agent" or not isinstance(scopes, list) or not all(isinstance(x, str) for x in scopes):
            raise ValueError(f"{where}: scopes is a list of strings and belongs to agents only")
        granted: set[str] = set(ALWAYS_GRANTED)
        for x in scopes:
            if x in MCP_BUNDLES:
                granted |= MCP_BUNDLES[x]
            elif x in MCP_SCOPES:
                granted.add(x)
            else:
                raise ValueError(f"{where}: unknown scopes [{x!r}]; known: {sorted(MCP_SCOPES)} "
                                 f"and bundles {sorted(MCP_BUNDLES)}")
        p = Principal(id=p.id, kind=p.kind, role=p.role, scopes=frozenset(granted))
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
            except Exception:
                # Fail closed: `_retired` lives in memory and is False after every restart, so on a
                # failed check we cannot know the owner account does not exist. Deny for this call
                # (without caching) rather than accept a possibly retired credential, and never 500.
                log.exception("could not check whether the first-boot token is retired; denying it")
                return True
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
