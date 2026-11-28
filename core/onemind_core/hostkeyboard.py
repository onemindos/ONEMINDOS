# SPDX-License-Identifier: Apache-2.0
"""The box's keyboard layout and the layouts its image offers (P-11), read from the host service.

The gateway runs apart from the host's files, so `onemindd host serve` answers `GET /v1/keyboard` on its local socket
(internal/host/keymap.go): the layout in /data/onemind/console/keyboard and the list the image's xkb-data ships. The host
service is trusted but not blindly (H-06): every field is checked again here, a layout or variant that fails a check is
dropped and counted in `dropped`, so one odd entry cannot hide the rest or put unchecked text on a screen. Changing the
layout is a later step: an owner-approved `system.set_keymap` action (routers/keyboard.py, hostlink.py).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .storage import StorageTimeout, StorageUnavailable, _UnixConnection

SCHEMA = "onemind.keyboard/v1"
MAX_BODY = 4 << 20
LAYOUT_RE = re.compile(r"^[A-Za-z0-9_]{1,24}$")
VARIANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
VALUE_RE = re.compile(r"^[A-Za-z0-9_,:+-]{0,200}$")  # what the console script accepts in the keyboard file
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
MAX_LAYOUTS = 600
MAX_VARIANTS = 300

Reason = Literal["host_service_unreachable", "host_service_error", "bad_response"]


class KeyboardSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(description="The keyboard model, as in /etc/default/keyboard (pc105 unless changed).")
    layout: str = Field(description="The layout id, e.g. us, de, fr.")
    variant: str = Field(description="The variant id of that layout, empty for the plain layout.")
    options: str = Field(description="xkb options, e.g. ctrl:nocaps; empty for none.")


class KeyboardVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str


class KeyboardLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    variants: list[KeyboardVariant]


class KeyboardView(BaseModel):
    """The keyboard layout of the text console and the box's own screen, and every layout this image offers."""

    model_config = ConfigDict(extra="forbid")
    available: bool
    reason: Reason | None = None
    message: str | None = None
    at: datetime | None = None
    current: KeyboardSetting | None = None
    seeded: bool = Field(default=False, description="True while nothing is chosen yet: the box then runs the US layout.")
    layouts: list[KeyboardLayout] = []
    dropped: int = Field(default=0, description="Entries the gateway refused because a field failed its checks.")


def unavailable(reason: Reason, message: str) -> KeyboardView:
    return KeyboardView(available=False, reason=reason, message=message)


class HostKeyboardClient:
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
                conn.request("GET", "/v1/keyboard")
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


def _id(v: Any, pattern: re.Pattern) -> str:
    if not isinstance(v, str) or not pattern.match(v):
        raise ValueError("bad id")
    return v


def _name(v: Any) -> str:
    if not isinstance(v, str) or not 1 <= len(v) <= 120 or CONTROL_RE.search(v):
        raise ValueError("bad name")
    return v


def _setting(d: Any) -> KeyboardSetting:
    if not isinstance(d, dict):
        raise ValueError("not an object")
    vals = {k: d.get(k) for k in ("model", "layout", "variant", "options")}
    if not all(isinstance(v, str) and VALUE_RE.match(v) for v in vals.values()) or not vals["layout"]:
        raise ValueError("bad setting")
    return KeyboardSetting(**vals)


def _layout(d: dict) -> tuple[KeyboardLayout, int]:
    variants: list[KeyboardVariant] = []
    dropped = 0
    raw = d.get("variants")
    if isinstance(raw, list):
        seen: set[str] = set()
        for v in raw[:MAX_VARIANTS]:
            try:
                if not isinstance(v, dict):
                    raise ValueError("not an object")
                vid = _id(v.get("id"), VARIANT_RE)
                if vid in seen:
                    raise ValueError("listed twice")
                seen.add(vid)
                variants.append(KeyboardVariant(id=vid, name=_name(v.get("name"))))
            except (ValueError, TypeError):
                dropped += 1
        dropped += max(0, len(raw) - MAX_VARIANTS)
    elif raw is not None:
        dropped += 1
    return KeyboardLayout(id=_id(d.get("id"), LAYOUT_RE), name=_name(d.get("name")), variants=variants), dropped


def parse_view(body: Any) -> KeyboardView:
    if not isinstance(body, dict) or body.get("schema") != SCHEMA:
        return unavailable("bad_response", "the host service sent something the gateway does not understand")
    try:
        current = _setting(body.get("current"))
    except (ValueError, TypeError):
        return unavailable("bad_response", "the host service sent a keyboard layout the gateway does not understand")
    layouts: list[KeyboardLayout] = []
    dropped = 0
    raw = body.get("layouts")
    if isinstance(raw, list):
        seen: set[str] = set()
        for entry in raw[:MAX_LAYOUTS]:
            try:
                if not isinstance(entry, dict):
                    raise ValueError("not an object")
                layout, lost = _layout(entry)
                if layout.id in seen:
                    raise ValueError("listed twice")
                seen.add(layout.id)
                layouts.append(layout)
                dropped += lost
            except (ValueError, TypeError):
                dropped += 1
        dropped += max(0, len(raw) - MAX_LAYOUTS)
    elif raw is not None:
        dropped = 1
    at = None
    try:
        at = datetime.fromisoformat(str(body.get("at")).replace("Z", "+00:00"))
    except ValueError:
        pass
    return KeyboardView(available=True, at=at, current=current, seeded=body.get("seeded") is True, layouts=layouts,
                        dropped=dropped)


def offers(view: KeyboardView, layout: str, variant: str | None) -> bool:
    """Whether the image offers this layout (and variant, when given)."""
    found = next((x for x in view.layouts if x.id == layout), None)
    if found is None:
        return False
    return not variant or any(v.id == variant for v in found.variants)


def read_view(client: HostKeyboardClient) -> KeyboardView:
    try:
        status, body = client.fetch()
    except (StorageUnavailable, StorageTimeout):
        return unavailable("host_service_unreachable",
                           "the host service is not reachable from the gateway, so the keyboard layout cannot be read yet")
    if status == 404:
        return unavailable("host_service_error", "this version of the host service cannot change the keyboard layout")
    if status != 200:
        return unavailable("host_service_error", f"the host service answered {status}")
    return parse_view(body)
