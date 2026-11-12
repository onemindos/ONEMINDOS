# SPDX-License-Identifier: Apache-2.0
"""Scopes, role defaults, grant bundles and the route → scope table (contract §12.6, API.md §8.2).

Effective access of an identity principal = (role defaults for a session, or the token's scopes)
∩ what its kind allows ∩ its owning person's current role. Static-file tokens are not checked here:
they keep contract v0 behaviour (the `v0` bundle).

A narrowed scope (`actions:read:own`, `actions:request:app.install`, `logs:read:<app>`) satisfies only
a route that asks for exactly it. Routes here ask for the broad scope, so a narrowed grant is refused
at the route (fail closed) until the module that can filter by owner or type checks it itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

ALL = "*"  # the owner role: every scope, including those of routes added later

BASE_SCOPES = frozenset({
    "instance:read", "nodes:read", "apps:read", "nodes:report", "docs:read",
    "actions:read", "actions:request", "actions:approve", "actions:withdraw",
    "fabric:read", "fabric:request", "fabric:admin",
    "backups:read", "backups:request", "backups:admin",
    "updates:read", "updates:request", "updates:admin",
    "notifications:read", "notifications:write", "notifications:send",
    "alerts:read", "monitoring:read", "logs:read",
    "automation:read", "automation:request", "automation:write",
    "audit:read", "audit:admin", "users:read", "users:admin",
    "tokens:self", "tokens:read", "tokens:admin", "events:read", "deploy:write",
})

# Narrowing suffixes the contract names; anything else after a base scope is refused.
_SUFFIX = {
    "actions:request": re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+"),
    "logs:read": re.compile(r"[a-z0-9][a-z0-9-]{0,62}"),
    "actions:read": re.compile(r"own|all"),
    "audit:read": re.compile(r"own|all"),
    "actions:withdraw": re.compile(r"own"),
    "events:read": re.compile(r"[a-z0-9_.*]{1,100}"),
}

# Never minted for agent, plugin, automation or node (§12.6).
_PERSON_ONLY = {"actions:approve", "tokens:admin", "tokens:self", "tokens:read", "notifications:read",
                "notifications:write"}
_KIND_ONLY = {"nodes:report": {"node"}, "notifications:send": {"plugin", "agent", "automation"},
              "automation:request": {"agent", "plugin", "person"}}

READ_SCOPES = frozenset(s for s in BASE_SCOPES if s.endswith(":read"))

ROLE_SCOPES: dict[str, frozenset[str]] = {
    "owner": frozenset({ALL}),
    "adult": frozenset((READ_SCOPES - {"users:read"}) | {
        "logs:read", "notifications:write", "tokens:self", "actions:request",
    }),
    "guest": frozenset({"instance:read", "nodes:read", "apps:read", "notifications:read",
                        "notifications:write", "alerts:read"}),
    "child": frozenset({"instance:read", "apps:read", "notifications:read", "alerts:read"}),
}

BUNDLES = {
    "reader": ("instance:read", "nodes:read", "apps:read", "actions:read:own", "audit:read:own",
               "updates:read", "backups:read", "docs:read"),
}
BUNDLES["requester"] = BUNDLES["reader"] + (
    "actions:request:app.install", "actions:request:app.remove", "actions:withdraw:own",
)


def role_scopes(role: str) -> frozenset[str]:
    """Unknown roles get the least privilege (child), as §12.6 tells v1 clients to treat them."""
    return ROLE_SCOPES.get(role, ROLE_SCOPES["child"])


def base_of(scope: str) -> str:
    parts = scope.split(":")
    return ":".join(parts[:2])


def parse_scope(scope: str) -> str:
    """Validate one scope string; returns it or raises ValueError."""
    if scope == ALL:
        return scope
    base = base_of(scope)
    if base not in BASE_SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    if scope != base:
        rx = _SUFFIX.get(base)
        if rx is None or not rx.fullmatch(scope[len(base) + 1:]):
            raise ValueError(f"scope {scope!r} has a suffix the contract does not define")
    return scope


def expand(scopes: Iterable[str]) -> list[str]:
    """Expand bundle names, validate, de-duplicate (order kept)."""
    out: list[str] = []
    for s in scopes:
        for item in BUNDLES.get(s, (s,)):
            item = parse_scope(item)
            if item not in out:
                out.append(item)
    return out


def allowed_for_kind(scope: str, kind: str) -> bool:
    base = base_of(scope)
    if kind == "person":
        only = _KIND_ONLY.get(base)
        return only is None or "person" in only
    if scope == ALL or base in _PERSON_ONLY or base.endswith(":admin") or base.startswith("users:"):
        return False
    if base == "automation:write":
        return False
    only = _KIND_ONLY.get(base)
    return only is None or kind in only


def within(scope: str, granted: Iterable[str]) -> bool:
    """Whether `scope` is covered by `granted` (the creator's rights): equal, ALL, or its broad form."""
    granted = set(granted)
    return ALL in granted or scope in granted or base_of(scope) in granted


def has_any(granted: Iterable[str], required: Iterable[str]) -> bool:
    g = set(granted)
    return ALL in g or any(r in g for r in required)


# ---- the route table ------------------------------------------------------------------------------
# (methods, path regex, scopes: any one grants). None = no scope; the handler checks who may call.
# A feature adds its routes with register_route_scope(...) in its router's register().
_ROUTES: list[tuple[frozenset[str], re.Pattern[str], tuple[str, ...] | None]] = []


def register_route_scope(methods: str, pattern: str, scopes: tuple[str, ...] | None) -> None:
    _ROUTES.append((frozenset(methods.split(",")), re.compile(pattern + r"\Z"), scopes))


_R = register_route_scope
_R("GET,HEAD", r"/v1/instance", ("instance:read",))
_R("GET,HEAD", r"/v1/me", ("instance:read",))
_R("GET,HEAD,POST,DELETE,PATCH,PUT", r"/v1/auth/.*", None)  # self-service; handlers check the person
_R("GET,HEAD", r"/v1/nodes(/.*)?", ("nodes:read",))
_R("GET,HEAD", r"/v1/apps/[^/]+/access", ("apps:read",))
_R("PUT", r"/v1/apps/[^/]+/access", ("users:admin",))
_R("GET,HEAD", r"/v1/apps(/.*)?", ("apps:read",))
_R("GET,HEAD", r"/v1/actions(/.*)?", ("actions:read",))
_R("POST", r"/v1/actions", ("actions:request",))
_R("POST", r"/v1/actions/[^/]+/(approve|deny|approve-options)", ("actions:approve",))
_R("POST", r"/v1/plans", ("actions:request",))  # a plan preview files nothing (contract §12.4)
# An app's generated login: owner only (PD-07). The handler also checks, this keeps scoped tokens out.
_R("GET,HEAD", r"/v1/apps/[^/]+/credentials", ("actions:approve",))
# /mcp's request_action is not scope-aware yet (DEV-MCP-2), so an identity-issued agent needs
# actions:request to use it at all; a reader-grant agent is refused rather than over-granted.
_R("POST,GET,DELETE", r"/mcp", ("actions:request",))
_R("GET,HEAD", r"/v1/users", ("users:read",))
_R("POST,PATCH", r"/v1/users(/.*)?", ("users:admin",))
_R("GET,HEAD", r"/v1/tokens", ("tokens:read", "tokens:self", "tokens:admin"))
_R("POST,DELETE", r"/v1/tokens(/.*)?", ("tokens:self", "tokens:admin"))


def required_scopes(method: str, path: str) -> tuple[str, ...] | None:
    """Scopes that grant this route (any one), None for self-service, (ALL,) for an unknown route."""
    for methods, rx, scopes in reversed(_ROUTES):  # later registrations override earlier ones
        if method in methods and rx.match(path):
            return scopes
    return (ALL,)
