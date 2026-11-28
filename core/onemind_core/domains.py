# SPDX-License-Identifier: Apache-2.0
"""NET-DOM-01 (#238), first slice: bring your own domain, owner-approved, off by default.

What is here: the owner registers a domain they own, proves it by a DNS TXT record, and then asks
(and approves, a separate owner step) for `<app>.<domain>` names. The ACME account key (the
identity the box uses to ask a certificate authority for certificates, RFC 8555) is created and
kept on the box (0600); only its public thumbprint is ever shown. The ACME DNS-01 value for a
challenge token is computed here (RFC 8555 section 8.4).

What is NOT here yet: talking to a certificate authority, serving a name on the public internet,
and the dynamic-DNS updater. Approving a host records the owner's decision only; nothing becomes
reachable until the issuance and edge slices land. Nothing here is reachable by an AI principal.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import socket
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, mapped_column

from .ledger import Base
from .sections import FALSE, TRUE, config_section
from .store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("domains")
ENV = "ONEMIND_DOMAINS_ENABLED"
PROOF_LABEL = "_onemind-challenge"
LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
APP_LABEL_RE = LABEL_RE
# Names that are the box's own or its admin surface: never handed out under an owner domain.
RESERVED_LABELS = frozenset({
    "onemind", "hub", "control", "join", "admin", "api", "gateway", "dashboard", "console", "grafana",
    "headscale", "nats", "k3s", "www", "mail", "ns1", "ns2", "_acme-challenge", PROOF_LABEL,
})
PRIVATE_TLDS = frozenset({"local", "internal", "localhost", "lan", "home", "arpa", "test", "invalid", "example"})


@config_section("domains")
@dataclass(frozen=True)
class DomainSettings:
    enabled: bool = False                # ONEMIND_DOMAINS_ENABLED=1: off by default
    resolver: str = "1.1.1.1"            # ONEMIND_DOMAINS_RESOLVER: DNS server the checks ask (an IP address)
    timeout_s: float = 3.0               # ONEMIND_DOMAINS_TIMEOUT_S

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> DomainSettings:
        raw = (env.get(ENV) or "").strip().lower()
        if raw not in ("",) + TRUE + FALSE:
            raise ValueError(f"{ENV} must be 1 or 0, got {raw!r}")
        resolver = (env.get("ONEMIND_DOMAINS_RESOLVER") or "1.1.1.1").strip()
        import ipaddress
        ipaddress.ip_address(resolver)  # ValueError refuses startup
        return cls(enabled=raw in TRUE, resolver=resolver,
                   timeout_s=float(env.get("ONEMIND_DOMAINS_TIMEOUT_S") or 3.0))


class DomainError(Exception):
    """`reason` is the specific machine-readable cause; the API error code follows from the status."""

    CODES = {404: "not_found", 409: "conflict", 422: "conflict", 503: "unavailable"}

    def __init__(self, status: int, reason: str, message: str):
        super().__init__(message)
        self.status, self.reason, self.message = status, reason, message
        self.code = self.CODES[status]


def normalize_domain(raw: str) -> str:
    d = raw.strip().lower().rstrip(".")
    labels = d.split(".")
    if len(d) > 253 or len(labels) < 2 or not all(LABEL_RE.match(x) for x in labels):
        raise DomainError(422, "invalid_domain", "enter a domain name such as example.org")
    if labels[-1] in PRIVATE_TLDS or labels[-1].isdigit():
        raise DomainError(422, "invalid_domain", "that is a private or reserved name; use a domain you own on the internet")
    return d


# ---- ACME pieces (RFC 8555, RFC 7638). The private key never leaves the box. ----------------------------------
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class AcmeAccount:
    """The ECDSA P-256 account key, created on first use under the TLS directory (0600)."""

    def __init__(self, tls_dir: Path):
        self.path = tls_dir / "acme-account.key"
        self.tls_dir = tls_dir

    def _key(self) -> ec.EllipticCurvePrivateKey:
        if not self.path.exists():
            self.tls_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(pem)
        key = serialization.load_pem_private_key(self.path.read_bytes(), None)
        assert isinstance(key, ec.EllipticCurvePrivateKey)
        return key

    def thumbprint(self) -> str:
        """RFC 7638 JWK thumbprint of the public key: members in lexicographic order, no spaces."""
        nums = self._key().public_key().public_numbers()
        jwk = {"crv": "P-256", "kty": "EC", "x": _b64(nums.x.to_bytes(32, "big")), "y": _b64(nums.y.to_bytes(32, "big"))}
        return _b64(hashlib.sha256(json.dumps(jwk, separators=(",", ":"), sort_keys=True).encode()).digest())

    def dns01_value(self, token: str) -> str:
        """The TXT value for _acme-challenge.<name>: base64url(sha256(token '.' thumbprint)) (RFC 8555 8.4)."""
        return _b64(hashlib.sha256(f"{token}.{self.thumbprint()}".encode()).digest())


# ---- DNS checks -------------------------------------------------------------------------------------------------
class Resolver(Protocol):
    def txt(self, name: str) -> list[str]: ...
    def addresses(self, name: str) -> list[str]: ...


class DnsResolver:
    """A minimal stdlib DNS client (UDP, one question). Raises OSError on timeout or a malformed reply."""

    def __init__(self, server: str, timeout_s: float = 3.0):
        self.server, self.timeout_s = server, timeout_s

    def txt(self, name: str) -> list[str]:
        return [d.decode("utf-8", "replace") for t, d in self._query(name, 16) if t == 16]

    def addresses(self, name: str) -> list[str]:
        out = []
        for qtype, family in ((1, socket.AF_INET), (28, socket.AF_INET6)):
            out += [socket.inet_ntop(family, d) for t, d in self._query(name, qtype) if t == qtype]
        return out

    def _query(self, name: str, qtype: int) -> list[tuple[int, bytes]]:
        qid = secrets.randbits(16)
        qname = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.split(".")) + b"\0"
        packet = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0) + qname + struct.pack(">HH", qtype, 1)
        family = socket.AF_INET6 if ":" in self.server else socket.AF_INET
        with socket.socket(family, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout_s)
            sock.connect((self.server, 53))
            sock.send(packet)
            data = sock.recv(4096)
        return parse_answers(data, qid)


def _skip_name(data: bytes, pos: int) -> int:
    while True:
        n = data[pos]
        if n == 0:
            return pos + 1
        if n & 0xC0 == 0xC0:
            return pos + 2
        pos += 1 + n


def parse_answers(data: bytes, qid: int) -> list[tuple[int, bytes]]:
    """(type, rdata) of each answer record; TXT rdata is the character-strings joined. NXDOMAIN gives []."""
    try:
        rid, flags, qd, an, _, _ = struct.unpack(">HHHHHH", data[:12])
        if rid != qid or not flags & 0x8000:
            raise OSError("unexpected DNS reply")
        if flags & 0xF == 3:
            return []
        if flags & 0xF:
            raise OSError("DNS server error")
        pos = 12
        for _ in range(qd):
            pos = _skip_name(data, pos) + 4
        out = []
        for _ in range(an):
            pos = _skip_name(data, pos)
            rtype, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[pos:pos + 10])
            rdata = data[pos + 10:pos + 10 + rdlen]
            if len(rdata) != rdlen:
                raise OSError("truncated DNS reply")
            pos += 10 + rdlen
            if rtype == 16:
                parts, i = [], 0
                while i < len(rdata):
                    parts.append(rdata[i + 1:i + 1 + rdata[i]])
                    i += 1 + rdata[i]
                rdata = b"".join(parts)
            out.append((rtype, rdata))
        return out
    except (struct.error, IndexError):
        raise OSError("malformed DNS reply") from None


# ---- storage and the service -----------------------------------------------------------------------------------
class DomainRow(Base):
    __tablename__ = "byo_domains"
    domain: Mapped[str] = mapped_column(String(253), primary_key=True)
    token: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HostRow(Base):
    __tablename__ = "byo_hosts"
    hostname: Mapped[str] = mapped_column(String(253), primary_key=True)
    domain: Mapped[str] = mapped_column(String(253), index=True)
    app_id: Mapped[str] = mapped_column(String(63))
    state: Mapped[str] = mapped_column(String(16))  # requested | approved
    requested_by: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _utc(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=UTC)


def _iso(d: datetime | None) -> str | None:
    d = _utc(d)
    return d.isoformat().replace("+00:00", "Z") if d else None


class DomainService(SqlRepository):
    def __init__(self, db, acme: AcmeAccount, resolver: Resolver, clock: Callable[[], datetime],
                 apps: Callable[[], list[str]], enabled: bool):
        super().__init__(db)
        self.acme, self.resolver, self.clock, self.apps, self.enabled = acme, resolver, clock, apps, enabled

    def require_enabled(self) -> None:
        if not self.enabled:
            # Off is how the box is set up, not a fault (503 is for a dependency that is down, contract §6):
            # 409, like map packs on a box without the Offline Maps volume. A DNS server that does not
            # answer stays 503 dns_unavailable.
            raise DomainError(409, "domains_disabled", f"bring-your-own-domain is off; set {ENV}=1 to turn it on")

    # -- views --
    def _view(self, row: DomainRow, hosts: list[HostRow]) -> dict:
        return {
            "domain": row.domain, "verified": row.verified_at is not None, "verified_at": _iso(row.verified_at),
            "proof": {"type": "TXT", "name": f"{PROOF_LABEL}.{row.domain}", "value": row.token},
            "hosts": [self._host_view(h) for h in hosts],
        }

    @staticmethod
    def _host_view(h: HostRow) -> dict:
        return {"hostname": h.hostname, "app_id": h.app_id, "state": h.state, "requested_by": h.requested_by,
                "approved_by": h.approved_by, "updated_at": _iso(h.updated_at), "public": False}

    def summary(self) -> dict:
        with self.db.session() as s:
            rows = s.scalars(select(DomainRow).order_by(DomainRow.domain)).all()
            hosts = s.scalars(select(HostRow).order_by(HostRow.hostname)).all()
            by: dict[str, list[HostRow]] = {}
            for h in hosts:
                by.setdefault(h.domain, []).append(h)
            return {"enabled": self.enabled, "acme": {"account_thumbprint": self.acme.thumbprint() if self.enabled else None,
                                                      "issuance": "not_available_yet"},
                    "domains": [self._view(r, by.get(r.domain, [])) for r in rows]}

    def _get(self, s, domain: str) -> DomainRow:
        row = s.get(DomainRow, normalize_domain(domain))
        if row is None:
            raise DomainError(404, "not_found", "that domain is not registered")
        return row

    # -- domain lifecycle --
    def add(self, raw: str, who: str) -> dict:
        self.require_enabled()
        domain = normalize_domain(raw)
        with self.db.session.begin() as s:
            if s.get(DomainRow, domain) is not None:
                raise DomainError(409, "conflict", "that domain is already registered")
            row = DomainRow(domain=domain, token=secrets.token_urlsafe(24), created_by=who, created_at=self.clock())
            s.add(row)
            s.flush()
            return self._view(row, [])

    def remove(self, raw: str) -> None:
        self.require_enabled()
        with self.db.session.begin() as s:
            row = self._get(s, raw)
            for h in s.scalars(select(HostRow).where(HostRow.domain == row.domain)).all():
                s.delete(h)
            s.delete(row)

    def check(self, raw: str) -> dict:
        """Ask DNS for the proof record. A wrong or missing record leaves the domain unverified."""
        self.require_enabled()
        with self.db.session() as s:
            row = self._get(s, raw)
            domain, token = row.domain, row.token
        try:
            seen = self.resolver.txt(f"{PROOF_LABEL}.{domain}")
            addrs = self.resolver.addresses(domain)
        except OSError as exc:
            raise DomainError(503, "dns_unavailable", f"could not reach the DNS server: {exc}") from None
        ok = token in [v.strip() for v in seen]
        with self.db.session.begin() as s:
            row = self._get(s, domain)
            row.verified_at = (row.verified_at or self.clock()) if ok else None
            view = self._view(row, list(s.scalars(select(HostRow).where(HostRow.domain == domain))))
        return {"domain": view, "proof_found": ok, "addresses": addrs}

    # -- hosts: request, then a separate owner approval --
    def request_host(self, raw: str, app_id: str, who: str) -> dict:
        self.require_enabled()
        if not APP_LABEL_RE.match(app_id) or app_id in RESERVED_LABELS:
            raise DomainError(422, "reserved_name", "that name is reserved for the box itself")
        if app_id not in self.apps():
            raise DomainError(422, "not_a_web_app", "only installed apps with a web page can get a public name")
        with self.db.session.begin() as s:
            row = self._get(s, raw)
            if row.verified_at is None:
                raise DomainError(409, "domain_unverified", "prove you own the domain first (add the TXT record, then check)")
            host = f"{app_id}.{row.domain}"
            if s.get(HostRow, host) is not None:
                raise DomainError(409, "conflict", "that name is already requested")
            h = HostRow(hostname=host, domain=row.domain, app_id=app_id, state="requested", requested_by=who,
                        approved_by=None, updated_at=self.clock())
            s.add(h)
            s.flush()
            return self._host_view(h)

    def approve_host(self, hostname: str, confirm: str, who: str) -> dict:
        self.require_enabled()
        if confirm.strip().lower() != hostname:
            raise DomainError(422, "confirm_mismatch", "type the full name to approve making it public")
        with self.db.session.begin() as s:
            h = s.get(HostRow, hostname)
            if h is None:
                raise DomainError(404, "not_found", "no such name")
            if h.state == "approved":
                raise DomainError(409, "conflict", "already approved")
            h.state, h.approved_by, h.updated_at = "approved", who, self.clock()
            return self._host_view(h)

    def revoke_host(self, hostname: str) -> None:
        self.require_enabled()
        with self.db.session.begin() as s:
            h = s.get(HostRow, hostname.lower())
            if h is None:
                raise DomainError(404, "not_found", "no such name")
            s.delete(h)
