# SPDX-License-Identifier: Apache-2.0
"""What an agent's browser may open (#694): URL checks, the sign-in / payment / download rules.

Pure functions, no I/O, so the gateway (visit decisions) and the egress proxy (CONNECT checks)
apply exactly the same rules:
- https only, a DNS host name only (no IP literal, no user:password@, no `localhost`), port 443;
- a host is reachable only when it is on the agent's allowlist (exact name, or a `*.` entry that
  covers its subdomains, never the bare parent);
- a sign-in page, a payment page and every download need a one-time owner approval even on an
  approved site, because "AI never actuates without human approval" (D-001).
- the audit keeps the URL without its query and fragment (they can carry tokens and personal data).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")
KINDS = ("navigate", "submit", "download")
# Suffixes that never name a public site: the box's own names and private-use top-level domains.
PRIVATE_SUFFIXES = (".local", ".internal", ".lan", ".home", ".arpa", ".localhost", ".onion", ".test", ".invalid")

# A path segment or host label that marks a sign-in or a payment step. Lower case, whole segments.
SIGN_IN_SEGMENTS = frozenset({
    "login", "log-in", "signin", "sign-in", "sign_in", "logon", "auth", "oauth", "oauth2", "authorize",
    "sso", "saml", "session", "sessions", "password", "passwords", "2fa", "mfa", "register", "signup",
    "sign-up", "account", "accounts", "my-account", "myaccount",
})
SIGN_IN_HOSTS = ("login.", "signin.", "accounts.", "account.", "auth.", "sso.", "id.", "idp.", "secure.")
PAYMENT_SEGMENTS = frozenset({
    "checkout", "payment", "payments", "pay", "billing", "purchase", "buy", "order", "orders", "cart",
    "basket", "subscribe", "subscription", "donate", "wallet", "invoice",
})
PAYMENT_HOSTS = ("pay.", "checkout.", "billing.", "payments.", "wallet.")
PAYMENT_DOMAINS = ("paypal.com", "stripe.com", "klarna.com", "adyen.com", "squareup.com", "venmo.com")


class UrlRefused(ValueError):
    """The URL cannot be opened by the agent browser at all (not a policy question)."""


@dataclass(frozen=True)
class Target:
    host: str
    url: str        # scheme://host/path, no query, no fragment, no credentials: what the audit keeps
    full: str       # the URL as given (kept only in memory, handed to the browser pod)


def normalize_host(raw: str) -> str:
    host = (raw or "").strip().lower().rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise UrlRefused(f"{raw!r} is not a valid host name") from None
    if not HOST_RE.match(host):
        raise UrlRefused(f"{raw!r} is not a public DNS host name")
    if host.endswith(PRIVATE_SUFFIXES):
        raise UrlRefused(f"{host} is a private name; the agent browser opens public sites only")
    return host


def normalize_entry(raw: str) -> str:
    """An allowlist entry: `example.org` (that host) or `*.example.org` (its subdomains)."""
    raw = (raw or "").strip().lower()
    wildcard = raw.startswith("*.")
    host = normalize_host(raw[2:] if wildcard else raw)
    if wildcard and host.count(".") < 1:
        raise UrlRefused("a wildcard needs a registrable domain under it (*.example.org)")
    return ("*." if wildcard else "") + host


def parse(url: str) -> Target:
    if not isinstance(url, str) or len(url) > 4096:
        raise UrlRefused("url must be a string of at most 4096 characters")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise UrlRefused("url is not a valid URL") from None
    if parts.scheme != "https":
        raise UrlRefused("the agent browser opens https pages only")
    if parts.username is not None or parts.password is not None:
        raise UrlRefused("a URL with a user name or password in it is refused")
    if port not in (None, 443):
        raise UrlRefused("the agent browser opens port 443 only")
    raw_host = parts.hostname or ""
    if _is_ip(raw_host):
        raise UrlRefused("an IP address is refused; approved sites are host names")
    host = normalize_host(raw_host)
    path = parts.path or "/"
    return Target(host=host, url=f"https://{host}{path}"[:2048], full=url.strip())


def _is_ip(raw: str) -> bool:
    try:
        ipaddress.ip_address(raw.strip("[]"))
    except ValueError:
        return False
    return True


def allowed(host: str, entries: set[str] | frozenset[str]) -> bool:
    if host in entries:
        return True
    labels = host.split(".")
    return any("*." + ".".join(labels[i:]) in entries for i in range(1, len(labels) - 1))


def _segments(path: str) -> list[str]:
    return [s for s in re.split(r"[/.;]+", path.lower()) if s]


def classify(target: Target, kind: str) -> str | None:
    """The reason this step needs a one-time owner approval on an approved site, or None."""
    path = urlsplit(target.url).path
    segs = set(_segments(path))
    host = target.host
    if segs & SIGN_IN_SEGMENTS or host.startswith(SIGN_IN_HOSTS):
        return "sign_in"
    if segs & PAYMENT_SEGMENTS or host.startswith(PAYMENT_HOSTS) or any(
            host == d or host.endswith("." + d) for d in PAYMENT_DOMAINS):
        return "payment"
    if kind == "download":
        return "download"
    return None


def step_plan(agent: str, session_id: str, kind: str, reason: str, url: str) -> tuple[dict, str]:
    """(plan, plan_sha256) of one step an owner approves once: the hash covers who, where and what."""
    plan = {"agent": agent, "session_id": session_id, "kind": kind, "reason": reason, "url": url}
    body = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return plan, "sha256:" + hashlib.sha256(body.encode()).hexdigest()


def site_plan(agent: str, entry: str) -> tuple[dict, str]:
    """(plan, plan_sha256) of adding one allowlist entry for one agent."""
    plan = {"agent": agent, "entry": entry}
    body = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return plan, "sha256:" + hashlib.sha256(body.encode()).hexdigest()


def public_address(ip: str) -> bool:
    """True only for a global unicast address: the proxy never connects into the box or the LAN."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast
