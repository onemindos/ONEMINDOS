# SPDX-License-Identifier: Apache-2.0
"""Mesh coordinator client: Headscale's REST API, driven only by owner-approved actions.

Not mounted yet (CORE-NET-8): no router imports this module.

Design: docs/architecture/NETWORKING.md §5 (enrollment), §6 (access rules), §13 (S3, S4, S7).

- HeadscaleClient speaks Headscale's REST API at a pinned version (HEADSCALE_VERSION, API prefix
  /api/v1). The endpoint and field names were read from the generated OpenAPI file at that tag
  (HEADSCALE_SWAGGER_SHA256). It talks to loopback only; Headscale is never reached over the LAN.
- MeshService mints a one-time pre-auth key only for an approved node.join (machines) or
  mesh.device.add (people's phones and laptops), expires keys, removes nodes and pushes the access
  policy rendered from OneMind roles. Every call that changes Headscale writes an audit line.
- Secrets: the API key and minted pre-auth keys are never logged, never written to the audit log
  and never shown in repr() or error messages. The caller hands a minted key to its holder once.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

from .audit import AuditLog
from .ledger import Action, iso, utc

log = logging.getLogger("onemind.mesh")

# ---- pinned coordinator API ------------------------------------------------------------------
HEADSCALE_VERSION = "0.29.7"
HEADSCALE_API_PREFIX = "/api/v1"
# sha256 of gen/openapiv2/headscale/v1/headscale.swagger.json at tag v0.29.7 (read 2026-11-12).
HEADSCALE_SWAGGER_SHA256 = "08f9b761ef4bf8ed763c13d7962a86025d43f53aecae164b1c35377f7bd630b7"

# ---- OneMind roles on the mesh (NETWORKING §6.1) ----------------------------------------------
TAG_HUB, TAG_WORKER, TAG_LEAF, TAG_K3S = "tag:onemind-hub", "tag:onemind-worker", "tag:onemind-leaf", "tag:onemind-k3s"
ROLE_TAGS: dict[str, tuple[str, ...]] = {
    "hub": (TAG_HUB, TAG_K3S),
    "worker": (TAG_WORKER, TAG_K3S),
    "leaf": (TAG_LEAF,),
}
# Roles the gateway may mint a join key for (§5.1). The hub enrolls itself at install over
# Headscale's local socket (§5.2); a joining machine never gets the hub's tags.
JOIN_ROLES = ("worker", "leaf")
ALL_TAGS = (TAG_HUB, TAG_WORKER, TAG_LEAF, TAG_K3S)
PERSON_GROUPS = {"owner": "group:owners", "adult": "group:adults", "guest": "group:guests"}
# Machine keys are minted under this Headscale user and carry the role tags; the tag, not the
# user, is the node's identity (the FB-3 lab enrolled the same way: --user + --tags).
MACHINES_USER = "onemind-machines"
JOIN_KEY_TTL = timedelta(minutes=15)  # §5.1
DEVICE_KEY_TTL = timedelta(minutes=10)  # §5.5
NODE_ID_RE = re.compile(r"^[a-z0-9]{1,32}$")
PERSON_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,54}[a-z0-9])?$")
AUTH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
HS_ID_RE = re.compile(r"^[0-9]{1,20}$")
# States in which an action has been approved by an owner and is being carried out.
APPROVED_STATES = frozenset({"accepted", "dispatched"})
_MAX_ERROR = 300


class HeadscaleError(Exception):
    """A Headscale call failed. The message never contains the API key or a pre-auth key."""

    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class MeshRefused(Exception):
    """MeshService refused a request (not approved, wrong type, bad parameters)."""


@dataclass(frozen=True)
class PreAuthKey:
    id: str
    expiration: str | None
    tags: tuple[str, ...]
    used: bool
    reusable: bool
    ephemeral: bool
    key: str = field(default="", repr=False)  # the secret; empty in listings we do not need it in

    def public(self) -> dict:
        """Everything except the key, for audit lines and API responses."""
        return {"id": self.id, "expiration": self.expiration, "tags": list(self.tags), "used": self.used,
                "reusable": self.reusable, "ephemeral": self.ephemeral}


@dataclass(frozen=True)
class MeshNode:
    id: str
    name: str
    user: str | None
    tags: tuple[str, ...]
    ip_addresses: tuple[str, ...]
    online: bool
    pre_auth_key_id: str | None


# A transport sends one request and returns (status, body bytes). Tests inject a fake Headscale.
Transport = Callable[[str, str, Mapping[str, str], bytes | None, float], tuple[int, bytes]]


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float):
    req = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    # No proxy handler: the coordinator is on loopback and must never be reached through a proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def read_api_key_file(path: Path) -> str:
    """The API key, from a file only its owner can read (0600 or stricter)."""
    st = path.stat()
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise PermissionError(f"{path.name}: Headscale API key file must not be readable by group or others")
    key = path.read_text().strip()
    if not key:
        raise ValueError(f"{path.name}: empty Headscale API key file")
    return key


class HeadscaleClient:
    """Headscale REST client, API v1 as served by Headscale v0.29.7. Loopback only."""

    def __init__(self, base_url: str, api_key: str, *, transport: Transport = urllib_transport, timeout: float = 10.0):
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not _is_loopback(parts.hostname):
            raise ValueError("Headscale base URL must be http(s) on a loopback address")
        if not api_key:
            raise ValueError("Headscale API key is empty")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport
        self.timeout = timeout

    @classmethod
    def from_key_file(cls, base_url: str, key_file: Path, **kw) -> "HeadscaleClient":
        return cls(base_url, read_api_key_file(key_file), **kw)

    def __repr__(self) -> str:
        return f"HeadscaleClient({self.base_url!r}, api=v1, headscale={HEADSCALE_VERSION})"

    def _scrub(self, text: str, extra: Iterable[str] = ()) -> str:
        for secret in (self._api_key, *extra):
            if secret:
                text = text.replace(secret, "[redacted]")
        return text[:_MAX_ERROR]

    def _call(self, method: str, path: str, body: dict | None = None, query: dict | None = None,
              secrets: Iterable[str] = ()) -> dict:
        url = f"{self.base_url}{HEADSCALE_API_PREFIX}{path}"
        if query:
            url += "?" + urlencode({k: v for k, v in query.items() if v is not None})
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        try:
            status, raw = self._transport(method, url, headers, data, self.timeout)
        except OSError as exc:  # connection refused, timeout: Headscale down
            raise HeadscaleError(None, f"{method} {path}: Headscale unreachable ({exc.__class__.__name__})") from None
        text = raw.decode("utf-8", "replace") if raw else ""
        if not 200 <= status < 300:
            try:
                detail = json.loads(text).get("message") or text
            except (ValueError, AttributeError):
                detail = text
            raise HeadscaleError(status, f"{method} {path}: HTTP {status}: {self._scrub(str(detail), secrets)}")
        if not text.strip():
            return {}
        try:
            out = json.loads(text)
        except ValueError:
            raise HeadscaleError(status, f"{method} {path}: response is not JSON") from None
        if not isinstance(out, dict):
            raise HeadscaleError(status, f"{method} {path}: response is not a JSON object")
        return out

    # ---- health ------------------------------------------------------------------------------
    def health(self) -> bool:
        return bool(self._call("GET", "/health").get("databaseConnectivity"))

    # ---- users -------------------------------------------------------------------------------
    def find_user(self, name: str) -> dict | None:
        users = self._call("GET", "/user", query={"name": name}).get("users") or []
        return next((u for u in users if u.get("name") == name), None)

    def create_user(self, name: str) -> dict:
        return self._call("POST", "/user", {"name": name}).get("user") or {}

    def ensure_user(self, name: str) -> tuple[str, bool]:
        """(user id, created?)."""
        user = self.find_user(name)
        if user is not None:
            return str(user["id"]), False
        return str(self.create_user(name)["id"]), True

    # ---- pre-auth keys -------------------------------------------------------------------------
    def create_preauth_key(self, user_id: str, *, tags: Iterable[str], expiration: datetime,
                           reusable: bool = False, ephemeral: bool = False) -> PreAuthKey:
        body = {"user": user_id, "reusable": reusable, "ephemeral": ephemeral,
                "expiration": iso(expiration), "aclTags": list(tags)}
        return _preauth_key(self._call("POST", "/preauthkey", body).get("preAuthKey") or {}, with_key=True)

    def expire_preauth_key(self, key_id: str) -> None:
        self._call("POST", "/preauthkey/expire", {"id": key_id})

    def list_preauth_keys(self) -> list[PreAuthKey]:
        return [_preauth_key(k, with_key=False) for k in self._call("GET", "/preauthkey").get("preAuthKeys") or []]

    # ---- nodes ---------------------------------------------------------------------------------
    def list_nodes(self) -> list[MeshNode]:
        return [_node(n) for n in self._call("GET", "/node").get("nodes") or []]

    def delete_node(self, node_id: str) -> None:
        self._call("DELETE", f"/node/{quote(node_id, safe='')}")

    def set_tags(self, node_id: str, tags: Iterable[str]) -> MeshNode:
        return _node(self._call("POST", f"/node/{quote(node_id, safe='')}/tags", {"tags": list(tags)}).get("node") or {})

    def register_pending(self, user: str, auth_id: str) -> MeshNode:
        """Approve a device waiting on Headscale's web registration page (§5.5, iOS flow)."""
        return _node(self._call("POST", "/auth/register", {"user": user, "authId": auth_id}).get("node") or {})

    # ---- policy --------------------------------------------------------------------------------
    def check_policy(self, policy: str) -> None:
        self._call("POST", "/policy/check", {"policy": policy})

    def set_policy(self, policy: str) -> None:
        self._call("PUT", "/policy", {"policy": policy})

    def get_policy(self) -> str:
        return str(self._call("GET", "/policy").get("policy") or "")


def _preauth_key(raw: dict, *, with_key: bool) -> PreAuthKey:
    return PreAuthKey(
        id=str(raw.get("id", "")),
        expiration=raw.get("expiration"),
        tags=tuple(raw.get("aclTags") or ()),
        used=bool(raw.get("used")),
        reusable=bool(raw.get("reusable")),
        ephemeral=bool(raw.get("ephemeral")),
        key=str(raw.get("key") or "") if with_key else "",
    )


def _node(raw: dict) -> MeshNode:
    pak = raw.get("preAuthKey") or {}
    user = raw.get("user") or {}
    return MeshNode(
        id=str(raw.get("id", "")),
        name=str(raw.get("givenName") or raw.get("name") or ""),
        user=user.get("name"),
        tags=tuple(raw.get("tags") or ()),
        ip_addresses=tuple(raw.get("ipAddresses") or ()),
        online=bool(raw.get("online")),
        pre_auth_key_id=str(pak["id"]) if pak.get("id") is not None else None,
    )


# ---- access policy from OneMind roles (§6) ----------------------------------------------------
@dataclass(frozen=True)
class MeshPerson:
    """A OneMind person who may own mesh devices. Agents are never mesh identities."""

    id: str
    role: str  # owner | adult | guest


def person_user(person_id: str) -> str:
    if not PERSON_ID_RE.match(person_id):
        raise MeshRefused("person id must be a lowercase DNS label")
    return f"person-{person_id}"


def render_policy(people: Iterable[MeshPerson], *, owner_ssh: bool = False) -> str:
    """Headscale policy (grants) for §6.2. Deterministic: same input, same bytes.

    Machines get their identity from tags, people from their Headscale user (person-<id>) placed
    in a group by OneMind role. Apps are not mesh identities: they are reached through the hub's
    port 443 and the gateway decides per person and app (proxy.py). Anything not granted is denied.
    """
    groups: dict[str, list[str]] = {g: [] for g in PERSON_GROUPS.values()}
    for p in people:
        group = PERSON_GROUPS.get(p.role)
        if group is None:
            raise MeshRefused(f"role {p.role!r} has no mesh group")
        groups[group].append(f"{person_user(p.id)}@")
    grants = [
        {"src": ["group:owners", "group:adults"], "dst": [TAG_HUB], "ip": ["tcp:443"]},
        {"src": [TAG_WORKER, TAG_LEAF], "dst": [TAG_HUB], "ip": ["tcp:443", "tcp:7422"]},
        {"src": [TAG_WORKER], "dst": [TAG_HUB], "ip": ["tcp:6443"]},
        {"src": [TAG_K3S], "dst": [TAG_K3S], "ip": ["tcp:10250", "udp:51820"]},
    ]
    if owner_ssh:  # §6.3, the approved mesh.ssh.set setting
        grants.append({"src": ["group:owners"], "dst": [TAG_K3S, TAG_LEAF], "ip": ["tcp:22"]})
    policy = {
        "groups": {g: sorted(set(m)) for g, m in sorted(groups.items())},
        # No person may claim a machine tag: only pre-auth keys set tags (§5.1, S4).
        "tagOwners": {t: [] for t in ALL_TAGS},
        "grants": grants,
    }
    return json.dumps(policy, indent=2, sort_keys=False) + "\n"


# ---- the service the gateway calls --------------------------------------------------------------
@dataclass(frozen=True)
class MintedKey:
    """A one-time key for its holder. `key` is shown once and never stored by the gateway."""

    key_id: str
    expiration: str | None
    tags: tuple[str, ...]
    user: str
    key: str = field(repr=False)


class MeshService:
    def __init__(self, client: HeadscaleClient, audit: AuditLog, clock: Callable[[], datetime]):
        self.client = client
        self.audit = audit
        self.clock = clock
        self._lock = threading.Lock()
        # Action ids a key was minted for in this process. The FABRIC join record (fabric_nodes,
        # Part 2) is the durable copy; this stops a double call within one process.
        self._minted: set[str] = set()

    # -- guards
    def _require_approved(self, action: Action, action_type: str) -> dict:
        if action.type != action_type:
            raise MeshRefused(f"action {action.id} is {action.type}, not {action_type}")
        if action.state not in APPROVED_STATES:
            raise MeshRefused(f"action {action.id} is {action.state}; only an approved action mints a key")
        d = action.decided_by or {}
        if d.get("kind") != "person" or d.get("role") != "owner":
            raise MeshRefused(f"action {action.id} was not approved by an owner")
        return d

    def _claim(self, action_id: str) -> None:
        with self._lock:
            if action_id in self._minted:
                raise MeshRefused(f"a key was already minted for action {action_id}")
            self._minted.add(action_id)

    def _release(self, action_id: str) -> None:
        with self._lock:
            self._minted.discard(action_id)

    # -- machines (§5.1)
    def mint_join_key(self, action: Action) -> MintedKey:
        """One single-use, 15-minute, role-tagged key for an approved node.join.

        Params read from the action: node_id (fabric node id) and role (worker | leaf).
        """
        decided = self._require_approved(action, "node.join")
        node_id, role = action.params.get("node_id"), action.params.get("role")
        if not isinstance(node_id, str) or not NODE_ID_RE.match(node_id):
            raise MeshRefused("node.join params.node_id must be lowercase hex/alphanumerics (max 32)")
        tags = ROLE_TAGS.get(role) if isinstance(role, str) and role in JOIN_ROLES else None
        if tags is None:
            raise MeshRefused(f"node.join params.role must be one of {list(JOIN_ROLES)}")
        self._claim(action.id)
        try:
            user_id, created = self.client.ensure_user(MACHINES_USER)
            if created:
                self.audit.append("mesh.user.created", None, action.id, {"user": MACHINES_USER})
            expires = utc(self.clock()) + JOIN_KEY_TTL
            pak = self.client.create_preauth_key(user_id, tags=tags, expiration=expires)
        except Exception as exc:
            self._release(action.id)
            self.audit.append("mesh.key.mint_failed", None, action.id,
                              {"node_id": node_id, "role": role, "reason": _reason(exc)})
            raise
        self.audit.append("mesh.key.minted", None, action.id, {
            "for": "node.join", "node_id": node_id, "role": role, "approved_by": decided.get("id"),
            "user": MACHINES_USER, **pak.public(),
        })
        return MintedKey(key_id=pak.id, expiration=pak.expiration, tags=pak.tags, user=MACHINES_USER, key=pak.key)

    # -- people's devices (§5.5)
    def mint_device_key(self, action: Action) -> MintedKey:
        """A single-use, 10-minute, untagged key in the person's own Headscale user."""
        decided = self._require_approved(action, "mesh.device.add")
        user = person_user(str(action.params.get("person_id", "")))
        self._claim(action.id)
        try:
            user_id, created = self.client.ensure_user(user)
            if created:
                self.audit.append("mesh.user.created", None, action.id, {"user": user})
            pak = self.client.create_preauth_key(user_id, tags=(), expiration=utc(self.clock()) + DEVICE_KEY_TTL)
        except Exception as exc:
            self._release(action.id)
            self.audit.append("mesh.key.mint_failed", None, action.id, {"user": user, "reason": _reason(exc)})
            raise
        self.audit.append("mesh.key.minted", None, action.id,
                          {"for": "mesh.device.add", "approved_by": decided.get("id"), "user": user, **pak.public()})
        return MintedKey(key_id=pak.id, expiration=pak.expiration, tags=(), user=user, key=pak.key)

    def register_device(self, action: Action) -> MeshNode:
        """Approve a pending web registration (iOS) for the person named in an approved mesh.device.add."""
        decided = self._require_approved(action, "mesh.device.add")
        user = person_user(str(action.params.get("person_id", "")))
        auth_id = action.params.get("auth_id")
        if not isinstance(auth_id, str) or not AUTH_ID_RE.match(auth_id):
            raise MeshRefused("mesh.device.add params.auth_id is missing or malformed")
        self._claim(action.id)
        try:
            _, created = self.client.ensure_user(user)
            if created:
                self.audit.append("mesh.user.created", None, action.id, {"user": user})
            node = self.client.register_pending(user, auth_id)
        except Exception as exc:
            self._release(action.id)
            self.audit.append("mesh.device.register_failed", None, action.id, {"user": user, "reason": _reason(exc)})
            raise
        self.audit.append("mesh.device.registered", None, action.id,
                          {"approved_by": decided.get("id"), "user": user, "mesh_node_id": node.id, "name": node.name})
        return node

    def expire_key(self, key_id: str, *, reason: str, action_id: str | None = None,
                   principal: dict | None = None) -> None:
        """Expire a key that was not used in time, or whose join was cancelled."""
        if not HS_ID_RE.match(key_id):
            raise MeshRefused("pre-auth key id must be numeric")
        self.client.expire_preauth_key(key_id)
        self.audit.append("mesh.key.expired", principal, action_id, {"key_id": key_id, "reason": reason})

    def check_join(self, key_id: str, node_id: str, role: str) -> MeshNode | None:
        """§5.1 bind check: the node that used our key has the expected name and exactly the role tags.

        Returns the node when it matches, None when no node used the key yet. A node that used the
        key but does not match is deleted, audited, and MeshRefused is raised.
        """
        node = next((n for n in self.client.list_nodes() if n.pre_auth_key_id == key_id), None)
        if node is None:
            return None
        want_tags, want_name = set(ROLE_TAGS.get(role, ())), f"node-{node_id}"
        if set(node.tags) != want_tags or node.name != want_name:
            self.client.delete_node(node.id)
            self.audit.append("mesh.node.rejected", None, None, {
                "mesh_node_id": node.id, "key_id": key_id, "expected_name": want_name, "name": node.name,
                "expected_tags": sorted(want_tags), "tags": sorted(node.tags),
            })
            raise MeshRefused(f"mesh node {node.id} does not match join of {node_id}; deleted")
        self.audit.append("mesh.node.bound", None, None,
                          {"mesh_node_id": node.id, "node_id": node_id, "role": role, "ips": list(node.ip_addresses)})
        return node

    def remove_node(self, mesh_node_id: str, *, reason: str, principal: dict | None = None,
                    action_id: str | None = None) -> None:
        """Removal only reduces reach, so it is audited but needs no approval (§5.3, §5.5)."""
        if not HS_ID_RE.match(mesh_node_id):
            raise MeshRefused("mesh node id must be numeric")
        self.client.delete_node(mesh_node_id)
        self.audit.append("mesh.node.removed", principal, action_id, {"mesh_node_id": mesh_node_id, "reason": reason})

    def set_role(self, mesh_node_id: str, role: str, *, action_id: str | None = None) -> MeshNode:
        if not HS_ID_RE.match(mesh_node_id) or role not in JOIN_ROLES:  # worker <-> leaf (§5.2)
            raise MeshRefused("bad mesh node id or role")
        node = self.client.set_tags(mesh_node_id, ROLE_TAGS[role])
        self.audit.append("mesh.node.retagged", None, action_id,
                          {"mesh_node_id": mesh_node_id, "role": role, "tags": list(ROLE_TAGS[role])})
        return node

    def push_policy(self, people: Iterable[MeshPerson], *, owner_ssh: bool = False,
                    action_id: str | None = None) -> str:
        """Render, check, then apply. A policy Headscale rejects is not applied (alert mesh.policy_rejected).

        Returns the sha256 of the applied policy.
        """
        policy = render_policy(people, owner_ssh=owner_ssh)
        digest = hashlib.sha256(policy.encode()).hexdigest()
        try:
            self.client.check_policy(policy)
        except HeadscaleError as exc:
            self.audit.append("mesh.policy_rejected", None, action_id, {"sha256": digest, "reason": _reason(exc)})
            raise
        self.client.set_policy(policy)
        self.audit.append("mesh.policy.applied", None, action_id, {"sha256": digest, "owner_ssh": owner_ssh})
        return digest


def _reason(exc: Exception) -> str:
    # HeadscaleError messages are already scrubbed; other exceptions are named, not printed.
    return exc.message if isinstance(exc, HeadscaleError) else exc.__class__.__name__


def write_secret_file(path: Path, value: str) -> None:
    """Write a 0600 file atomically (for handing a key file to a local process)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, value.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
