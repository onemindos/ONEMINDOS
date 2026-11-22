# SPDX-License-Identifier: Apache-2.0
"""Service cards (#623): every systemd unit the OS ships, with a plain name and description, and its state.

The words come from the services registry on the signed, read-only image (/usr/lib/onemind/services.yaml,
contract sdk/schema/onemind.services.schema.json). The gateway runs in a container and cannot ask systemd,
so `onemindd host serve` (root, on the host) joins the registry with `systemctl show` and answers
`GET /v1/services` on its local socket (internal/svcregistry). A OneMind unit the registry does not list
comes back as known=false and is shown as unknown; test/unit/test_services_registry.py stops one shipping.

The host service is trusted but not blindly (H-06): every field is checked again here, card by card. A
card that fails a check is dropped and counted in `dropped`, so one odd entry cannot hide the rest or put
unchecked text on a screen. This is read-only: restarting a unit is a later, owner-approved action.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .storage import StorageTimeout, StorageUnavailable, _UnixConnection

HOST_SCHEMA = "onemind.host.services/v1"
MAX_BODY = 1 << 20
MAX_CARDS = 300
UNIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,90}\.(service|socket|timer|path)$")
DOCS_RE = re.compile(r"^docs/([A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.md$")
STATE_RE = re.compile(r"^[a-z-]{1,32}$")
VERSION_RE = re.compile(r"^[0-9A-Za-z.+~-]{1,64}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
RISKS = ("low", "medium", "high")

Reason = Literal["host_service_unreachable", "host_service_error", "bad_response"]
RegistryState = Literal["ok", "missing", "invalid"]


class ServiceCard(BaseModel):
    """One systemd unit on the service cards: the registry's words plus what systemd says now."""

    model_config = ConfigDict(extra="forbid")
    unit: str = Field(description="systemd unit file name, e.g. onemind-gateway.service")
    known: bool = Field(description="false: the registry does not list this unit; name is the unit name and description is empty")
    name: str = Field(description="Plain name for the card")
    description: str = Field(description="Plain words: what it does and what stops working without it (empty when unknown)")
    docs: str | None = Field(default=None, description="Repo path of the page that explains it, e.g. docs/leap/core/HOST-ACTIONS.md")
    restartable: bool = Field(description="Whether a person may ask for a restart (an owner-approved action, later work)")
    risk: Literal["low", "medium", "high", "unknown"] = Field(
        description="low: a background job pauses; medium: a feature stops for everyone; high: boot, data or access at stake")
    depends_on: list[str] = Field(default=[], description="Other registry units it needs")
    installed: bool = Field(description="systemd has this unit on this box (boards ship different units)")
    load_state: str | None = Field(default=None, description="systemd LoadState: loaded, not-found, masked, ...")
    active_state: str | None = Field(default=None, description="systemd ActiveState: active, inactive, failed, activating, ...")
    sub_state: str | None = Field(default=None, description="systemd SubState: running, dead, exited, waiting, ...")
    memory_bytes: int | None = Field(default=None, description="Memory the unit uses now; null when systemd does not count it")
    version: str | None = Field(default=None, description="The OneMind release that shipped this unit; null when unknown or not installed")


class ServicesView(BaseModel):
    """GET /v1/system/services: one card per shipped unit, then any unknown OneMind unit."""

    model_config = ConfigDict(extra="forbid")
    available: bool
    reason: Reason | None = None
    message: str | None = None
    registry: RegistryState | None = Field(
        default=None, description="ok; missing (the image has no registry); invalid (it failed its checks, so every unit is unknown)")
    at: datetime | None = None
    services: list[ServiceCard] = []
    unknown: int = Field(default=0, description="Cards whose unit the registry does not list")
    dropped: int = Field(default=0, description="Cards the gateway refused because a field failed its checks")


def unavailable(reason: Reason, message: str) -> ServicesView:
    return ServicesView(available=False, reason=reason, message=message)


class HostServicesClient:
    def __init__(self, path: str, timeout_s: float):
        self.path, self.timeout_s = path, timeout_s

    def fetch(self) -> tuple[int, Any]:
        conn = _UnixConnection(self.path, self.timeout_s)
        try:
            try:
                conn.connect()
            except OSError as exc:
                raise StorageUnavailable(exc.__class__.__name__) from None
            try:
                conn.request("GET", "/v1/services")
                resp = conn.getresponse()
                raw = resp.read(MAX_BODY + 1)
            except Exception as exc:  # timeout, reset, protocol error
                raise StorageTimeout(exc.__class__.__name__) from None
            if len(raw) > MAX_BODY:
                return resp.status, None
            try:
                return resp.status, json.loads(raw or b"null")
            except ValueError:
                return resp.status, None
        finally:
            conn.close()


def _text(v: Any, lo: int, hi: int) -> str:
    if not isinstance(v, str) or not lo <= len(v) <= hi or CONTROL_RE.search(v):
        raise ValueError("bad text")
    return v


def _opt(v: Any, pattern: re.Pattern) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str) or not pattern.match(v):
        raise ValueError("bad value")
    return v


def _bool(v: Any) -> bool:
    if not isinstance(v, bool):
        raise ValueError("not a boolean")
    return v


def _card(d: dict) -> ServiceCard:
    unit = d.get("unit")
    if not isinstance(unit, str) or not UNIT_RE.match(unit):
        raise ValueError("bad unit")
    known = _bool(d.get("known"))
    mem = d.get("memory_bytes")
    if mem is not None and (not isinstance(mem, int) or isinstance(mem, bool) or not 0 <= mem < 1 << 50):
        raise ValueError("bad memory")
    deps = d.get("depends_on") or []
    if not isinstance(deps, list) or len(deps) > 20 or not all(isinstance(x, str) and UNIT_RE.match(x) for x in deps):
        raise ValueError("bad depends_on")
    common = dict(unit=unit, known=known, installed=_bool(d.get("installed")),
                  load_state=_opt(d.get("load_state"), STATE_RE), active_state=_opt(d.get("active_state"), STATE_RE),
                  sub_state=_opt(d.get("sub_state"), STATE_RE), memory_bytes=mem)
    if not known:
        # Nothing the registry vouches for: the unit name is the name, and nothing else is believed.
        return ServiceCard(**common, name=unit, description="", docs=None, restartable=False, risk="unknown", depends_on=[])
    if d.get("risk") not in RISKS:
        raise ValueError("bad risk")
    return ServiceCard(**common, name=_text(d.get("name"), 1, 60), description=_text(d.get("description"), 10, 300),
                       docs=_opt(d.get("docs"), DOCS_RE), restartable=_bool(d.get("restartable")), risk=d["risk"],
                       depends_on=list(deps), version=_opt(d.get("version"), VERSION_RE))


def parse_view(body: Any) -> ServicesView:
    if not isinstance(body, dict) or body.get("schema") != HOST_SCHEMA:
        return unavailable("bad_response", "the host service sent something the gateway does not understand")
    registry = body.get("registry") if body.get("registry") in ("ok", "missing", "invalid") else None
    raw = body.get("services")
    cards: list[ServiceCard] = []
    dropped = 0
    if isinstance(raw, list):
        seen: set[str] = set()
        for entry in raw[:MAX_CARDS]:
            try:
                if not isinstance(entry, dict):
                    raise ValueError("not an object")
                card = _card(entry)
                if card.unit in seen:
                    raise ValueError("listed twice")
                seen.add(card.unit)
                cards.append(card)
            except (ValueError, TypeError):
                dropped += 1
        dropped += max(0, len(raw) - MAX_CARDS)
    elif raw is not None:
        dropped = 1
    at = None
    try:
        at = datetime.fromisoformat(str(body.get("at")).replace("Z", "+00:00"))
    except ValueError:
        pass
    message = None
    if registry == "missing":
        message = "this OS image has no services registry, so every service shows as unknown"
    elif registry == "invalid":
        message = "the services registry on this OS image failed its checks, so every service shows as unknown"
    return ServicesView(available=True, registry=registry, message=message, at=at, services=cards,
                        unknown=sum(1 for c in cards if not c.known), dropped=dropped)


def read_view(client: HostServicesClient) -> ServicesView:
    try:
        status, body = client.fetch()
    except (StorageUnavailable, StorageTimeout):
        return unavailable("host_service_unreachable",
                           "the host service is not reachable from the gateway, so the services on this box cannot be read yet")
    if status != 200:
        return unavailable("host_service_error", f"the host service answered {status}")
    return parse_view(body)
