# SPDX-License-Identifier: Apache-2.0
"""The client protocol policy (sdk/contracts/protocol-versions.md, issue #697).

A client states the protocol generation it speaks in `X-OneMind-Protocol: <n>`. The gateway
serves every generation from `minimum` to `current`, answers each response with
`X-OneMind-Protocol-Min` and `X-OneMind-Protocol-Max`, and refuses an API request below the
minimum with 400 `upgrade_required` (reason `protocol_too_old`), so an old app can show
"Update needed" instead of failing on an answer it cannot read.

Rules (the contract has the why):
- a request without the header speaks generation 1, the API every client spoke before the header;
- a generation stays served for at least 12 months after its successor ships (N and N-1);
- the minimum moves only by a reviewed change to PROTOCOL_MINIMUM, never by the clock
  (core/tests/test_protocol.py refuses a minimum that drops a generation early);
- a client newer than the hub is served at the hub's maximum; the client steps down or says
  "Update the hub".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel

from .errors import error_response
from .sections import config_section

PROTOCOL_HEADER = "X-OneMind-Protocol"
PROTOCOL_MIN_HEADER = "X-OneMind-Protocol-Min"
PROTOCOL_MAX_HEADER = "X-OneMind-Protocol-Max"
SUPPORT_MONTHS = 12
# What a request without the header speaks: every client that predates the header.
UNDECLARED_PROTOCOL = 1
_VALUE_RE = re.compile(r"^[1-9][0-9]{0,3}$")
# Paths outside the policy: the health probe, the contract itself, the policy route (an old app
# must be able to read what it needs), and MCP, which carries its own protocol version.
EXEMPT_PATHS = frozenset({"/healthz", "/openapi.json", "/v1/protocol", "/mcp"})


@dataclass(frozen=True)
class ProtocolVersion:
    version: int
    released: date
    summary: str


# Append-only. A breaking change to any request or answer adds a generation here, records its
# corpus (core/tests/fixtures/protocol/v<n>.json) and leaves PROTOCOL_MINIMUM alone.
PROTOCOL_VERSIONS: tuple[ProtocolVersion, ...] = (
    ProtocolVersion(1, date(2026, 11, 11), "contract poc-v0 sections 3 and 12; clients sent no X-OneMind-Protocol header"),
    ProtocolVersion(2, date(2026, 11, 21), "clients send X-OneMind-Protocol; every answer carries the supported range"),
)
PROTOCOL_CURRENT = PROTOCOL_VERSIONS[-1].version
PROTOCOL_MINIMUM = 1


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    last = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, last))


def supported_until(version: int) -> date | None:
    """The earliest day a generation may be dropped: its successor's release plus 12 months.
    None for the current generation (no successor yet)."""
    later = [v for v in PROTOCOL_VERSIONS if v.version == version + 1]
    return _add_months(later[0].released, SUPPORT_MONTHS) if later else None


@config_section("protocol")
@dataclass(frozen=True)
class ProtocolSettings:
    # ONEMIND_PROTOCOL_MINIMUM: an owner (or a lab kit) may refuse old clients early. It can only
    # raise the minimum, never lower it below PROTOCOL_MINIMUM or above PROTOCOL_CURRENT.
    minimum: int | None = None

    def validate(self) -> None:
        if self.minimum is not None and not PROTOCOL_MINIMUM <= self.minimum <= PROTOCOL_CURRENT:
            raise ValueError(
                f"ONEMIND_PROTOCOL_MINIMUM must be between {PROTOCOL_MINIMUM} and {PROTOCOL_CURRENT}"
            )

    def effective_minimum(self) -> int:
        return self.minimum if self.minimum is not None else PROTOCOL_MINIMUM


class ProtocolVersionInfo(BaseModel):
    version: int
    released: date
    summary: str
    supported: bool
    # The earliest day this generation may be dropped; null for the current one.
    supported_until: date | None


class ProtocolInfo(BaseModel):
    """GET /v1/protocol: the generations this hub serves (also in every answer's headers)."""

    header: str
    current: int
    minimum: int
    maximum: int
    versions: list[ProtocolVersionInfo]


def protocol_info(minimum: int) -> dict:
    return {
        "header": PROTOCOL_HEADER,
        "current": PROTOCOL_CURRENT,
        "minimum": minimum,
        "maximum": PROTOCOL_CURRENT,
        "versions": [
            {
                "version": v.version, "released": v.released.isoformat(), "summary": v.summary,
                "supported": v.version >= minimum, "supported_until": (u.isoformat() if (u := supported_until(v.version)) else None),
            }
            for v in PROTOCOL_VERSIONS
        ],
    }


class ProtocolMiddleware:
    """Pure ASGI: stamps the range on every HTTP answer, refuses API requests below the minimum."""

    def __init__(self, app, minimum: int = PROTOCOL_MINIMUM):
        self.app = app
        self.minimum = minimum
        self.range_headers = [
            (PROTOCOL_MIN_HEADER.lower().encode(), str(minimum).encode()),
            (PROTOCOL_MAX_HEADER.lower().encode(), str(PROTOCOL_CURRENT).encode()),
        ]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def stamped(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), *self.range_headers]}
            await send(message)

        refusal = self.refusal(scope)
        if refusal is not None:
            return await refusal(scope, receive, stamped)
        return await self.app(scope, receive, stamped)

    def refusal(self, scope):
        path = scope.get("path", "")
        if path in EXEMPT_PATHS or not path.startswith("/v1/"):
            return None
        values = [v for k, v in scope.get("headers", []) if k == PROTOCOL_HEADER.lower().encode()]
        if not values:
            sent = UNDECLARED_PROTOCOL
        elif len(values) == 1 and _VALUE_RE.match(raw := values[0].decode("latin-1").strip()):
            sent = int(raw)
        else:
            return error_response(
                422, "conflict", f"{PROTOCOL_HEADER} must be one whole number, such as {PROTOCOL_CURRENT}",
                reason="protocol_header_invalid",
            )
        if sent >= self.minimum:
            return None  # a newer client than this hub is served at the hub's maximum
        return error_response(
            400, "upgrade_required",
            f"this app speaks OneMind protocol {sent}; the hub needs {self.minimum} to {PROTOCOL_CURRENT}. Update the app.",
            reason="protocol_too_old",
            details=[{"field": PROTOCOL_HEADER, "sent": sent, "minimum": self.minimum, "maximum": PROTOCOL_CURRENT}],
        )
