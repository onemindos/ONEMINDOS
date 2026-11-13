# SPDX-License-Identifier: Apache-2.0
"""Fabric join: one-time ticket -> node request -> owner approval -> one-time credentials.

Contract §12.11 (binding); design: docs/leap/core/FABRIC.md §3.1, docs/architecture/NETWORKING.md
§5.1 (mesh enrollment), §7 (NATS), §8 (k3s).

1. The owner makes a ticket (POST /v1/fabric/join-tickets). Its join code is shown once (as a QR
   with the box CA fingerprint); only the code's sha256 is stored. A ticket is single use and lives
   at most an hour.
2. The new machine sends the code, what it is, a CSR for its own key and its NATS public nkey
   (POST /v1/fabric/join-requests, no session: the code authenticates, rate-limited per source).
   That files a `node.join` action (sensitive) and nothing else: no credential exists yet.
3. The owner approves it like any action (POST /v1/actions/{id}/approve). Only then does the box
   sign the node's certificate and add the node's own NATS account (natsconf.py).
4. The node polls with the code *and* a signature by its key (proof it holds the key in the CSR).
   The first poll after approval mints the short-lived secrets — a single-use, 15-minute,
   role-tagged mesh key (mesh.py) and, for a worker, a 1-hour k3s bootstrap token — returns them
   once, and never stores them. Later polls answer `delivered`.
5. `node.join` succeeds when the node's first heartbeat arrives over its own NATS account and
   Headscale shows the machine bound to the key the box minted (name and tags as minted).

Secrets never reach the database, the audit log or events: they are minted at delivery.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import subprocess

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, String, Text, delete, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .auth import Principal
from .ca import MESH_DOMAIN, BoxCA
from .errors import ApiError
from .executors import ExecResult
from .ledger import Action, Base, iso, utc
from .mesh import ROLE_TAGS, MeshRefused, MeshService
from .natsconf import NodeAccount, is_user_public_nkey, write_accounts
from .netconf import FabricSettings, MeshSettings, NetSettings
from .store import Database, FeatureSchema, SqlRepository

log = logging.getLogger("onemind.fabric")

SCHEMA = FeatureSchema("fabric")

ROLES = ("worker", "leaf")
TICKET_MAX_S = 3600
TICKET_DEFAULT_S = 900
REQUEST_TTL = timedelta(minutes=15)       # an unapproved join request expires (FABRIC §6)
COLLECT_TTL = timedelta(minutes=15)       # approved credentials not collected in time
FIRST_HEARTBEAT_TTL = timedelta(minutes=30)
K3S_TOKEN_TTL = timedelta(hours=1)
POLL_CONTEXT = b"onemind-join-poll:v1:"
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
NODE_ID_RE = re.compile(r"^[a-z0-9]{1,32}$")
ACTIVE = ("awaiting_approval", "approved", "delivering", "delivered")


# ---- ids and codes ---------------------------------------------------------------------------------
def _b32(n: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_CROCKFORD[n & 31])
        n >>= 5
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    """A prefixed ULID (§12.1): 48-bit millisecond time + 80 random bits, Crockford base32."""
    return prefix + _b32((int(time.time() * 1000) << 80) | secrets.randbits(80), 26)


def new_join_code() -> str:
    """12 Crockford characters (60 bits), grouped for reading aloud: 7KQ4-M2XP-9D3F."""
    raw = _b32(secrets.randbits(60), 12)
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def normalize_code(code: str) -> str:
    c = re.sub(r"[\s-]", "", code or "").upper().translate(str.maketrans("ILO", "110"))
    return c if re.fullmatch(f"[{_CROCKFORD}]{{12}}", c) else ""


def code_hash(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def match_code(request_id: str, public_key_der: bytes) -> str:
    """The short code the owner compares on both screens (K7-4QX)."""
    n = int.from_bytes(hashlib.sha256(request_id.encode() + public_key_der).digest()[:4], "big")
    c = _b32(n, 6)
    return f"{c[:2]}-{c[2:]}"


# ---- tables -------------------------------------------------------------------------------------------
class FabricTicketRow(Base):
    __tablename__ = "fabric_tickets"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    code_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(16))
    labels: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_node_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FabricRequestRow(Base):
    __tablename__ = "fabric_requests"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(40), index=True)
    action_id: Mapped[str] = mapped_column(String(36), unique=True)
    node_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(16))
    hostname: Mapped[str] = mapped_column(String(63))
    node: Mapped[dict] = mapped_column(JSON)  # board, arch, os: what the approval card shows
    csr_pem: Mapped[str] = mapped_column(Text)
    nats_pubkey: Mapped[str] = mapped_column(String(56))
    match_code: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(20), index=True)
    node_cert_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    cert_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mesh_key_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    k3s_token_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FabricNodeRow(Base):
    """A node with fabric identity: its NATS account exists while it is here (joining or joined)."""

    __tablename__ = "fabric_nodes"
    node_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    hostname: Mapped[str] = mapped_column(String(63))
    nats_pubkey: Mapped[str] = mapped_column(String(56))
    state: Mapped[str] = mapped_column(String(16))  # joining | joined
    request_id: Mapped[str] = mapped_column(String(40))
    mesh_node_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cert_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _row_dict(row: Any) -> dict:
    out = {}
    for c in row.__table__.columns.keys():
        v = getattr(row, c)
        out[c] = utc(v) if isinstance(v, datetime) else v
    return out


class FabricRepository(SqlRepository):
    # tickets
    def add_ticket(self, **values) -> None:
        with self.db.session.begin() as s:
            s.add(FabricTicketRow(**values))

    def ticket_by_code(self, digest: str) -> dict | None:
        with self.db.session() as s:
            r = s.scalars(select(FabricTicketRow).where(FabricTicketRow.code_sha256 == digest)).first()
            return _row_dict(r) if r else None

    def ticket(self, ticket_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.get(FabricTicketRow, ticket_id)
            return _row_dict(r) if r else None

    def list_tickets(self) -> list[dict]:
        with self.db.session() as s:
            return [_row_dict(r) for r in s.scalars(select(FabricTicketRow).order_by(FabricTicketRow.created_at.desc()))]

    def claim_ticket(self, ticket_id: str, node_id: str, now: datetime) -> bool:
        """Single use: compare-and-swap on used_at."""
        with self.db.session.begin() as s:
            res = s.execute(update(FabricTicketRow).where(
                FabricTicketRow.id == ticket_id, FabricTicketRow.used_at.is_(None),
                FabricTicketRow.revoked_at.is_(None), FabricTicketRow.expires_at > now,
            ).values(used_at=now, used_by_node_id=node_id))
            return res.rowcount == 1

    def revoke_ticket(self, ticket_id: str, now: datetime) -> bool:
        with self.db.session.begin() as s:
            res = s.execute(update(FabricTicketRow).where(
                FabricTicketRow.id == ticket_id, FabricTicketRow.used_at.is_(None),
                FabricTicketRow.revoked_at.is_(None),
            ).values(revoked_at=now))
            return res.rowcount == 1

    # requests
    def add_request(self, **values) -> None:
        with self.db.session.begin() as s:
            s.add(FabricRequestRow(**values))

    def request(self, request_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.get(FabricRequestRow, request_id)
            return _row_dict(r) if r else None

    def request_by_action(self, action_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.scalars(select(FabricRequestRow).where(FabricRequestRow.action_id == action_id)).first()
            return _row_dict(r) if r else None

    def requests(self, states: tuple[str, ...]) -> list[dict]:
        with self.db.session() as s:
            q = select(FabricRequestRow).where(FabricRequestRow.state.in_(states)).order_by(FabricRequestRow.created_at)
            return [_row_dict(r) for r in s.scalars(q)]

    def active_for_node(self, node_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.scalars(select(FabricRequestRow).where(
                FabricRequestRow.node_id == node_id, FabricRequestRow.state.in_(ACTIVE))).first()
            return _row_dict(r) if r else None

    def count_pending(self) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(FabricRequestRow).where(
                FabricRequestRow.state == "awaiting_approval")) or 0

    def move(self, request_id: str, from_states: tuple[str, ...], to_state: str, now: datetime, **fields) -> bool:
        """Compare-and-swap on the request state."""
        with self.db.session.begin() as s:
            res = s.execute(update(FabricRequestRow).where(
                FabricRequestRow.id == request_id, FabricRequestRow.state.in_(from_states),
            ).values(state=to_state, updated_at=now, **fields))
            return res.rowcount == 1

    # nodes
    def upsert_node(self, **values) -> None:
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(FabricNodeRow).values(**values).on_conflict_do_update(
                index_elements=[FabricNodeRow.node_id],
                set_={k: v for k, v in values.items() if k != "node_id"},
            ))

    def set_node(self, node_id: str, **values) -> None:
        with self.db.session.begin() as s:
            s.execute(update(FabricNodeRow).where(FabricNodeRow.node_id == node_id).values(**values))

    def delete_node(self, node_id: str, request_id: str) -> bool:
        with self.db.session.begin() as s:
            res = s.execute(delete(FabricNodeRow).where(
                FabricNodeRow.node_id == node_id, FabricNodeRow.request_id == request_id))
            return res.rowcount == 1

    def nodes(self) -> list[dict]:
        with self.db.session() as s:
            return [_row_dict(r) for r in s.scalars(select(FabricNodeRow).order_by(FabricNodeRow.node_id))]

    def node(self, node_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.get(FabricNodeRow, node_id)
            return _row_dict(r) if r else None


# ---- request bodies -----------------------------------------------------------------------------------
class TicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(default="worker", pattern="^(worker|leaf|node)$")
    expires_in_s: int = Field(default=TICKET_DEFAULT_S, ge=60, le=TICKET_MAX_S)
    labels: dict[str, str] = Field(default_factory=dict, max_length=16)


class JoinOS(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default="", max_length=32)
    version_id: str = Field(default="", max_length=32)
    pretty: str = Field(default="", max_length=120)


class JoinNode(BaseModel):
    model_config = ConfigDict(extra="ignore")  # a newer node may send more facts; we keep ours
    node_id: str = Field(pattern=NODE_ID_RE.pattern)
    hostname: str = Field(min_length=1, max_length=63, pattern=r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
    board: str = Field(default="unknown", max_length=32, pattern=r"^[a-z0-9_-]+$")
    arch: str = Field(pattern="^(amd64|arm64)$")
    os: JoinOS = Field(default_factory=JoinOS)


class JoinRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    join_code: str = Field(min_length=12, max_length=20)
    node: JoinNode
    csr_pem: str = Field(min_length=100, max_length=4096)
    nats_pubkey: str = Field(min_length=56, max_length=56)


# ---- rate limiting for the unauthenticated routes (§12.1) ----------------------------------------
class SourceLimiter:
    """Per-source: at most `per_min` requests a minute; `max_fail` wrong codes in a minute block the
    source for `block_s` (contract §12.1: 10/min, then a 15-minute back-off)."""

    MAX_KEYS = 10_000   # per book; above it, stale entries are dropped (at most every GC_EVERY_S)
    GC_EVERY_S = 10

    def __init__(self, clock: Callable[[], datetime], per_min: int = 10, max_fail: int = 10, block_s: int = 900):
        self.clock, self.per_min, self.max_fail, self.block_s = clock, per_min, max_fail, block_s
        self._hits: dict[str, list[datetime]] = {}
        self._fails: dict[str, list[datetime]] = {}
        self._blocked: dict[str, datetime] = {}
        self._last_gc: datetime | None = None
        self._lock = threading.Lock()

    def _recent(self, book: dict[str, list[datetime]], key: str, now: datetime) -> list[datetime]:
        kept = [t for t in book.get(key, []) if (now - t).total_seconds() < 60]
        book[key] = kept
        return kept

    def _gc(self, now: datetime) -> None:
        """Bounded memory under a spray of source addresses (these routes need no session).

        Drops counts older than a minute and finished blocks. If a book is still over MAX_KEYS, the
        spray is of fresh sources: their counts are dropped too, which costs nothing, because every
        new source starts with a full budget anyway. Runs at most every GC_EVERY_S, so a spray
        cannot turn each request into a full scan.
        """
        if len(self._hits) <= self.MAX_KEYS and len(self._fails) <= self.MAX_KEYS \
                and len(self._blocked) <= self.MAX_KEYS:
            return
        if self._last_gc is not None and (now - self._last_gc).total_seconds() < self.GC_EVERY_S:
            return
        self._last_gc = now

        def fresh(book: dict[str, list[datetime]]) -> dict[str, list[datetime]]:
            out = {}
            for k, v in book.items():
                kept = [t for t in v if (now - t).total_seconds() < 60]
                if kept:
                    out[k] = kept
            return out

        self._hits, self._fails = fresh(self._hits), fresh(self._fails)
        self._blocked = {k: u for k, u in self._blocked.items() if u > now}
        if len(self._hits) > self.MAX_KEYS:
            self._hits = {}
        if len(self._fails) > self.MAX_KEYS:
            self._fails = {}
        if len(self._blocked) > self.MAX_KEYS:
            self._blocked = {}

    def check(self, key: str) -> None:
        now = self.clock()
        with self._lock:
            self._gc(now)
            until = self._blocked.get(key)
            if until and until > now:
                raise ApiError(429, "rate_limited", "too many attempts from this address",
                               retry_after_s=int((until - now).total_seconds()) + 1)
            hits = self._recent(self._hits, key, now)
            if len(hits) >= self.per_min:
                raise ApiError(429, "rate_limited", "too many requests from this address", retry_after_s=60)
            hits.append(now)

    def fail(self, key: str) -> None:
        now = self.clock()
        with self._lock:
            self._gc(now)
            fails = self._recent(self._fails, key, now)
            fails.append(now)
            if len(fails) >= self.max_fail:
                self._blocked[key] = now + timedelta(seconds=self.block_s)


# ---- k3s bootstrap tokens ------------------------------------------------------------------------
Runner = Callable[..., subprocess.CompletedProcess]


class K3sBootstrapTokens:
    """1-hour k3s join tokens (FABRIC §4: no standing shared secret), as Kubernetes bootstrap-token
    Secrets in kube-system, the same objects `k3s token create --ttl 1h` writes. The gateway's own
    ServiceAccount creates and deletes them; the token is returned once and never stored."""

    def __init__(self, kubectl: str, ca_hash: str | None, *, runner: Runner = subprocess.run, timeout_s: float = 20):
        self.kubectl, self.ca_hash, self.runner, self.timeout_s = kubectl, ca_hash, runner, timeout_s

    def create(self, node_id: str, expires_at: datetime) -> tuple[str, str]:
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        tid = "".join(secrets.choice(alphabet) for _ in range(6))
        secret = "".join(secrets.choice(alphabet) for _ in range(16))
        manifest = (
            "apiVersion: v1\nkind: Secret\ntype: bootstrap.kubernetes.io/token\n"
            f"metadata:\n  name: bootstrap-token-{tid}\n  namespace: kube-system\n"
            "  labels: {app.kubernetes.io/managed-by: onemind-gateway}\n"
            "stringData:\n"
            f"  description: \"OneMind join of node-{node_id}\"\n"
            f"  token-id: \"{tid}\"\n  token-secret: \"{secret}\"\n"
            f"  expiration: \"{iso(expires_at)}\"\n"
            "  usage-bootstrap-authentication: \"true\"\n  usage-bootstrap-signing: \"true\"\n"
            "  auth-extra-groups: \"system:bootstrappers:k3s:default-node-token\"\n"
        )
        proc = self.runner([self.kubectl, "create", "-f", "-"], input=manifest.encode(), capture_output=True,
                           timeout=self.timeout_s, check=False)
        if proc.returncode != 0:
            raise RuntimeError("creating the k3s bootstrap token failed")  # stderr may echo the manifest
        creds = f"{tid}.{secret}"
        return tid, (f"{self.ca_hash}::{creds}" if self.ca_hash else creds)

    def delete(self, token_id: str) -> None:
        if not re.fullmatch(r"[a-z0-9]{6}", token_id or ""):
            return
        self.runner([self.kubectl, "-n", "kube-system", "delete", "secret", f"bootstrap-token-{token_id}",
                     "--ignore-not-found"], capture_output=True, timeout=self.timeout_s, check=False)


# ---- the service --------------------------------------------------------------------------------------
@dataclass
class FabricDeps:
    """What FabricService needs from the gateway (built by routers/net.py)."""

    actions: Any            # ActionService
    audit: Any              # AuditLog
    events: Any             # EventHub
    registry: Any           # NodeRegistry
    db: Database
    clock: Callable[[], datetime]
    box_ca: BoxCA
    net: NetSettings
    mesh_settings: MeshSettings
    fabric: FabricSettings
    mesh: MeshService | None = None
    k3s: K3sBootstrapTokens | None = None
    hub_node_id: str | None = None


class FabricService:
    def __init__(self, deps: FabricDeps):
        self.d = deps
        self.repo = FabricRepository(deps.db)
        self.limiter = SourceLimiter(deps.clock)
        self._tick_lock = threading.Lock()

    # -- helpers
    def _deny(self, principal: Principal, what: str) -> ApiError:
        self.d.audit.append("authz.denied", principal.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not {what}")

    def hub_url(self) -> str:
        return self.d.fabric.hub_url or f"https://{self.d.net.box()}.local"

    def nats_url(self) -> str | None:
        host = self.d.mesh_settings.hub_ip if self.d.mesh_settings.enabled else self.d.net.lan_addr
        return f"tls://{host}:{self.d.fabric.nats_leaf_port}" if host else None

    def write_accounts(self) -> bool:
        path = self.d.fabric.nats_accounts_file
        if path is None:
            return False
        accounts = [NodeAccount(n["node_id"], n["nats_pubkey"]) for n in self.repo.nodes()]
        changed = write_accounts(path, accounts)
        if changed:
            log.info("NATS accounts updated (%d nodes)", len(accounts))
        return changed

    # -- tickets (owner)
    def create_ticket(self, principal: Principal, body: TicketRequest) -> dict:
        if not principal.is_owner:
            raise self._deny(principal, "create join tickets")
        now = self.d.clock()
        role = "worker" if body.role == "node" else body.role
        code = new_join_code()
        tid = new_id("tkt_")
        expires = now + timedelta(seconds=body.expires_in_s)
        self.repo.add_ticket(id=tid, code_sha256=code_hash(code), role=role, labels=dict(body.labels),
                             created_by=principal.id, created_at=now, expires_at=expires)
        ca = self.d.box_ca.ca_fingerprint()
        hub = self.hub_url()
        payload = f"onemind-join:v1?code={code}&ca={ca}&role={role}&hub={quote(hub, safe='')}"
        self.d.events.publish_event("fabric", "ticket.created", {"ticket_id": tid, "role": role,
                                    "expires_at": iso(expires)}, principal=principal.as_dict())
        return {"ticket_id": tid, "role": role, "labels": dict(body.labels), "expires_at": iso(expires),
                "hub_ca_sha256": ca, "hub_url": hub, "qr_payload": payload, "one_time": {"join_code": code}}

    def list_tickets(self, principal: Principal) -> list[dict]:
        if not principal.is_owner:
            raise self._deny(principal, "list join tickets")
        return [{"ticket_id": t["id"], "role": t["role"], "labels": t["labels"], "created_by": t["created_by"],
                 "created_at": iso(t["created_at"]), "expires_at": iso(t["expires_at"]),
                 "used_by_node_id": t["used_by_node_id"], "revoked": t["revoked_at"] is not None}
                for t in self.repo.list_tickets()]

    def revoke_ticket(self, principal: Principal, ticket_id: str) -> None:
        if not principal.is_owner:
            raise self._deny(principal, "revoke join tickets")
        if self.repo.ticket(ticket_id) is None:
            raise ApiError(404, "not_found", "no such ticket")
        if not self.repo.revoke_ticket(ticket_id, self.d.clock()):
            raise ApiError(409, "conflict", "the ticket was already used or revoked")
        self.d.audit.append("fabric.ticket.revoked", principal.as_dict(), None, {"ticket_id": ticket_id})

    # -- join requests (no session; the code authenticates)
    def create_request(self, source: str, body: JoinRequestBody) -> dict:
        self.limiter.check(source)
        now = self.d.clock()
        ticket = self.repo.ticket_by_code(code_hash(body.join_code)) if normalize_code(body.join_code) else None
        if ticket is None or ticket["revoked_at"] is not None:
            self.limiter.fail(source)
            raise ApiError(401, "unauthenticated", "unknown join code", reason="code_unknown")
        if ticket["used_at"] is not None:
            self.limiter.fail(source)
            raise ApiError(401, "unauthenticated", "this join code was already used", reason="code_used")
        if ticket["expires_at"] <= now:
            raise ApiError(409, "expired", "the join code has expired; make a new one")
        n = body.node
        if n.node_id == self.d.hub_node_id or self.repo.node(n.node_id) or self.repo.active_for_node(n.node_id):
            raise ApiError(409, "conflict", f"node {n.node_id} has already joined or is joining",
                           reason="duplicate_node_id")
        if not is_user_public_nkey(body.nats_pubkey):
            raise ApiError(422, "conflict", "nats_pubkey is not a NATS user public nkey")
        try:
            csr = x509.load_pem_x509_csr(body.csr_pem.encode())
            pub = csr.public_key()
            if not csr.is_signature_valid or not isinstance(pub, ec.EllipticCurvePublicKey) \
                    or pub.curve.name != "secp256r1":
                raise ValueError
        except ValueError:
            raise ApiError(422, "conflict", "csr_pem must be a valid ECDSA P-256 certificate request") from None
        if self.repo.count_pending() >= self.d.fabric.max_pending:
            raise ApiError(429, "rate_limited", "too many join requests are waiting for approval",
                           reason="too_many_pending", retry_after_s=60)
        if not self.repo.claim_ticket(ticket["id"], n.node_id, now):
            raise ApiError(401, "unauthenticated", "this join code was already used", reason="code_used")
        rid = new_id("jr_")
        der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        mcode = match_code(rid, der)
        role = ticket["role"]
        node_facts = {"board": n.board, "arch": n.arch, "os": n.os.model_dump()}
        params = {"join_request_id": rid, "node_id": n.node_id, "role": role, "hostname": n.hostname,
                  **node_facts, "match_code": mcode, "labels": ticket["labels"]}
        requester = {"id": f"node:{n.node_id}", "kind": "node"}
        action = self.d.actions.file(
            "node.join", params, requester, expires_at=now + REQUEST_TTL, idempotency_key=f"fabric:{rid}",
            audit_principal={**requester, "role": "node"},
        )
        self.repo.add_request(
            id=rid, ticket_id=ticket["id"], action_id=action.id, node_id=n.node_id, role=role,
            hostname=n.hostname, node=node_facts, csr_pem=body.csr_pem, nats_pubkey=body.nats_pubkey,
            match_code=mcode, state="awaiting_approval", created_at=now, updated_at=now,
        )
        self.d.events.publish_event(
            "node", "join_requested", {"node_id": n.node_id, "role": role, "hostname": n.hostname,
                                       "match_code": mcode, "join_request_id": rid},
            action_id=action.id, resource={"kind": "node", "id": n.node_id},
        )
        return {"join_request_id": rid, "match_code": mcode, "role": role,
                "poll": f"/v1/fabric/join-requests/{rid}", "action": action.to_json()}

    def _verify_poll(self, req: dict, code: str, proof: str) -> None:
        ticket = self.repo.ticket(req["ticket_id"])
        if ticket is None or not normalize_code(code) or not hmac.compare_digest(ticket["code_sha256"], code_hash(code)):
            raise ApiError(401, "unauthenticated", "join code does not match this request", reason="code_unknown")
        try:
            sig = base64.b64decode(proof, validate=True)
            pub = x509.load_pem_x509_csr(req["csr_pem"].encode()).public_key()
            pub.verify(sig, POLL_CONTEXT + req["id"].encode(), ec.ECDSA(hashes.SHA256()))
        except (ValueError, InvalidSignature, TypeError):
            raise ApiError(401, "unauthenticated", "proof of the node key is missing or wrong",
                           reason="assertion_invalid") from None

    def _sync_from_action(self, req: dict) -> dict:
        """Mirror a decided action (denied, expired, or approved but failed) onto its request."""
        if req["state"] != "awaiting_approval":
            return req
        a = self.d.actions.repo.get(req["action_id"])
        if a is not None:
            a = self.d.actions.expire_if_due(a)
        if a is not None and a.state in ("failed", "outcome_unknown"):
            # Approved, but its effect did not complete (dispatch failed or crashed before the
            # request moved on): drop whatever it made, so the node id and the pending slot free up.
            self._fail(req, "failed", f"the approval did not complete (action {a.state})")
            return self.repo.request(req["id"]) or req
        target = {"cancelled": "denied", "expired": "expired"}.get(a.state if a else "expired")
        if target and self.repo.move(req["id"], ("awaiting_approval",), target, self.d.clock(),
                                     reason=f"action {a.state if a else 'missing'}"):
            return self.repo.request(req["id"]) or req
        return req

    def poll(self, source: str, request_id: str, code: str, proof: str) -> dict:
        self.limiter.check(source)
        req = self.repo.request(request_id)
        if req is None:
            self.limiter.fail(source)
            raise ApiError(404, "not_found", "no such join request")
        try:
            self._verify_poll(req, code, proof)
        except ApiError:
            self.limiter.fail(source)
            raise
        req = self._sync_from_action(req)
        out = {"id": req["id"], "state": req["state"], "match_code": req["match_code"],
               "action_id": req["action_id"], "role": req["role"]}
        if req["state"] == "approved":
            creds = self._deliver(req)
            if creds is not None:
                return {**out, "state": "delivered", "credentials": creds}
        if req["state"] in ("delivering", "approved"):
            out["state"] = "approved"
        return out

    def _deliver(self, req: dict) -> dict | None:
        """Mint the one-time secrets and hand them over exactly once."""
        now = self.d.clock()
        if not self.repo.move(req["id"], ("approved",), "delivering", now):
            return None  # a concurrent poll is delivering
        action = self.d.actions.repo.get(req["action_id"])
        k3s_id, k3s_token, mesh_key = None, None, None
        try:
            if req["role"] == "worker" and self.d.fabric.k3s and self.d.k3s is not None:
                k3s_id, k3s_token = self.d.k3s.create(req["node_id"], now + K3S_TOKEN_TTL)
            if self.d.mesh_settings.enabled and self.d.mesh is not None:
                mesh_key = self.d.mesh.mint_join_key(action)
        except Exception as exc:
            self.repo.move(req["id"], ("delivering",), "approved", self.d.clock())
            if k3s_id and self.d.k3s is not None:
                self.d.k3s.delete(k3s_id)
            log.warning("join %s: minting credentials failed: %s", req["id"], exc.__class__.__name__)
            raise ApiError(503, "unavailable", "the box could not mint join credentials right now; retrying is safe",
                           reason="mesh_control_down", retry_after_s=10) from None
        creds: dict[str, Any] = {
            "role": req["role"],
            "node_cert": req["node_cert_pem"],
            "ca_cert": self.d.box_ca.ca_pem().decode(),
            "nats": {"url": self.nats_url(), "account": f"NODE_{req['node_id']}", "user_pubkey": req["nats_pubkey"]},
            "job_pubkey": None,  # signed jobs (§12.11) are a later step
        }
        if mesh_key is not None:
            creds["mesh"] = {
                "control_url": self.d.mesh_settings.control_url,
                "control_addrs": [self.d.net.lan_addr] if self.d.net.lan_addr else [],
                "ca_sha256": self.d.box_ca.ca_fingerprint(),
                "auth_key": mesh_key.key,
                "hostname": f"node-{req['node_id']}",
                "hub_mesh_ip": self.d.mesh_settings.hub_ip,
                "tags": list(mesh_key.tags),
                "shields_up": req["role"] == "leaf",
            }
        if k3s_token is not None:
            creds["k3s"] = {"server_url": f"https://{self.d.mesh_settings.hub_ip}:6443", "token": k3s_token}
        self.repo.move(req["id"], ("delivering",), "delivered", self.d.clock(), delivered_at=self.d.clock(),
                       mesh_key_id=mesh_key.key_id if mesh_key else None, k3s_token_id=k3s_id)
        self.d.audit.append("fabric.credentials.delivered", None, req["action_id"], {
            "join_request_id": req["id"], "node_id": req["node_id"], "role": req["role"],
            "mesh_key_id": mesh_key.key_id if mesh_key else None, "k3s_token_id": k3s_id,
            "credentials": "provided",
        })
        return creds

    # -- the node.join handler (actions.ActionHandler)
    def recheck(self, action: Action) -> str | None:
        req = self.repo.request_by_action(action.id)
        if req is None:
            return "no join request belongs to this action"
        if req["state"] != "awaiting_approval":
            return f"the join request is {req['state']}"
        node = self.repo.node(req["node_id"])
        if node is not None:
            return f"node {req['node_id']} has already joined"
        return None

    def dispatch(self, action: Action) -> ExecResult | None:
        req = self.repo.request_by_action(action.id)
        if req is None:
            return ExecResult("failed", "no join request belongs to this action")
        now = self.d.clock()
        cert = self.d.box_ca.sign_node_csr(req["csr_pem"], req["node_id"])
        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        self.repo.upsert_node(node_id=req["node_id"], role=req["role"], hostname=req["hostname"],
                              nats_pubkey=req["nats_pubkey"], state="joining", request_id=req["id"],
                              mesh_node_id=None, cert_expires_at=cert.not_valid_after_utc, created_at=now,
                              joined_at=None)
        try:
            self.write_accounts()
        except OSError as exc:
            self.repo.delete_node(req["node_id"], req["id"])
            return ExecResult("failed", f"writing the NATS accounts failed: {exc.__class__.__name__}")
        self.repo.move(req["id"], ("awaiting_approval",), "approved", now, node_cert_pem=pem,
                       cert_expires_at=cert.not_valid_after_utc, approved_at=now)
        self.d.audit.append("fabric.node.approved", None, action.id, {
            "node_id": req["node_id"], "role": req["role"], "cert_serial": format(cert.serial_number, "x"),
            "cert_not_after": iso(cert.not_valid_after_utc), "nats_account": f"NODE_{req['node_id']}",
            "san": f"node-{req['node_id']}.{MESH_DOMAIN}",
        })
        return None  # stays dispatched until the node is up (tick)

    # -- background: finish or expire joins
    def reconcile(self) -> None:
        """Startup: a delivery a crash interrupted is retried (the key was never handed over). An
        approval a crash interrupted (action accepted or dispatched, request still awaiting) is not
        retried: the action ends outcome_unknown, what it may have made is dropped, and the owner
        makes a new code (ActionService.reconcile_interrupted leaves handler types to this)."""
        for req in self.repo.requests(("delivering",)):
            self.repo.move(req["id"], ("delivering",), "approved", self.d.clock())
        for req in self.repo.requests(("awaiting_approval",)):
            a = self.d.actions.repo.get(req["action_id"])
            if a is not None and a.state in ("accepted", "dispatched"):
                self._fail(req, "failed", "the gateway restarted while this join was being approved",
                           outcome="outcome_unknown")
        self.write_accounts()

    def _fail(self, req: dict, state: str, why: str, *, outcome: str = "failed") -> None:
        if not self.repo.move(req["id"], (req["state"],), state, self.d.clock(), reason=why[:200]):
            return
        self.repo.delete_node(req["node_id"], req["id"])
        try:
            self.write_accounts()
        except OSError:
            log.exception("rewriting NATS accounts after a failed join")
        if req.get("mesh_key_id") and self.d.mesh is not None:
            try:
                self.d.mesh.expire_key(req["mesh_key_id"], reason=why, action_id=req["action_id"])
            except Exception:  # Headscale down: the key expires by itself within 15 minutes
                log.warning("could not expire mesh key of %s", req["id"])
        if req.get("k3s_token_id") and self.d.k3s is not None:
            self.d.k3s.delete(req["k3s_token_id"])
        self.d.actions.finish(req["action_id"], outcome, why, from_states=frozenset({"accepted", "dispatched"}))

    def _heard_from(self, node_id: str, since: datetime | None) -> bool:
        hb = self.d.registry.get(node_id)
        if not hb or hb.get("status") != "online" or since is None:
            return False
        seen = datetime.fromisoformat(hb["last_seen"].replace("Z", "+00:00"))
        return seen >= since

    def tick(self) -> None:
        """Every few seconds: expire stale requests, finish joins whose node is up."""
        if not self._tick_lock.acquire(blocking=False):
            return
        try:
            now = self.d.clock()
            for req in self.repo.requests(("awaiting_approval",)):
                self._sync_from_action(req)
            for req in self.repo.requests(("approved",)):
                if req["approved_at"] and now - req["approved_at"] > COLLECT_TTL:
                    self._fail(req, "expired", "the node did not collect its credentials in time")
            for req in self.repo.requests(("delivered",)):
                self._check_joined(req, now)
        finally:
            self._tick_lock.release()

    def _k3s_ready(self, req: dict) -> bool:
        """A worker that got a k3s ticket is joined only once its agent runs (§12.11: "for a worker,
        k3s Ready"); until then the 1-hour token must stay, or the agent cannot use it."""
        if req["role"] != "worker" or not req.get("k3s_token_id"):
            return True
        k3s = (self.d.registry.get(req["node_id"]) or {}).get("k3s") or {}
        return bool(k3s.get("ready"))

    def _check_joined(self, req: dict, now: datetime) -> None:
        if not self._heard_from(req["node_id"], req["delivered_at"]) or not self._k3s_ready(req):
            if req["delivered_at"] and now - req["delivered_at"] > FIRST_HEARTBEAT_TTL:
                self._fail(req, "failed", "the node did not come up (heartbeat, and k3s for a worker) "
                                          "after it collected its credentials")
            return
        mesh_node = None
        if self.d.mesh_settings.enabled and self.d.mesh is not None and req.get("mesh_key_id"):
            try:
                mesh_node = self.d.mesh.check_join(req["mesh_key_id"], req["node_id"], req["role"])
            except MeshRefused as exc:
                self._fail(req, "failed", str(exc))
                return
            except Exception:
                return  # Headscale unreachable: try again next tick
            if mesh_node is None:
                return
        if not self.repo.move(req["id"], ("delivered",), "joined", now):
            return
        self.repo.set_node(req["node_id"], state="joined", joined_at=now,
                           mesh_node_id=mesh_node.id if mesh_node else None)
        if req.get("k3s_token_id") and self.d.k3s is not None:
            self.d.k3s.delete(req["k3s_token_id"])  # the agent has its own credentials now
        self.d.actions.finish(req["action_id"], "succeeded", f"node {req['node_id']} joined as {req['role']}")
        self.d.events.publish_event("node", "joined", {"node_id": req["node_id"], "role": req["role"],
                                                       "mesh": mesh_node is not None},
                                    action_id=req["action_id"], resource={"kind": "node", "id": req["node_id"]})

    # -- read views
    def summary(self) -> dict:
        nodes, counts = [], {"hub": 1, "worker": 0, "leaf": 0}
        for n in self.repo.nodes():
            hb = self.d.registry.get(n["node_id"]) or {}
            counts[n["role"]] = counts.get(n["role"], 0) + (1 if n["state"] == "joined" else 0)
            fabric = hb.get("fabric") or {}
            nodes.append({
                "node_id": n["node_id"], "hostname": n["hostname"], "role": n["role"],
                "state": n["state"] if n["state"] != "joined" else hb.get("status", "offline"),
                "leaf_link": fabric.get("leaf_link", "none") if hb else "none",
                "mesh": hb.get("mesh"), "cert_expires_at": iso(n["cert_expires_at"]),
                "joined_at": iso(n["joined_at"]),
            })
        pending = [{"join_request_id": r["id"], "node_id": r["node_id"], "hostname": r["hostname"],
                    "role": r["role"], "state": r["state"], "match_code": r["match_code"],
                    "action_id": r["action_id"], "created_at": iso(r["created_at"])}
                   for r in self.repo.requests(ACTIVE)]
        return {"hub_node_id": self.d.hub_node_id, "counts": counts, "nodes": nodes, "joining": pending}


def role_tags(role: str) -> list[str]:
    return list(ROLE_TAGS.get(role, ()))
