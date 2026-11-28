# SPDX-License-Identifier: Apache-2.0
"""The client protocol policy (protocol.py, sdk/contracts/protocol-versions.md, #697).

Adds the middleware that stamps `X-OneMind-Protocol-Min`/`-Max` on every answer and refuses
API requests below the minimum, the open `GET /v1/protocol`, and `info.x-onemind-protocol` in
/openapi.json so the SDKs and apps can check the generation they declare against the contract.
"""

from __future__ import annotations

from fastapi import FastAPI

from ..context import Gateway
from ..protocol import PROTOCOL_CURRENT, PROTOCOL_HEADER, ProtocolInfo, ProtocolMiddleware, ProtocolSettings, protocol_info

# Before guard (ORDER 0), so guard wraps the refusal too: it gets the security headers and the
# rate limit like any other answer (routers/__init__.py; later middleware wraps earlier).
ORDER = -1


def register(app: FastAPI, gw: Gateway) -> None:
    minimum = gw.settings.section(ProtocolSettings).effective_minimum()
    app.add_middleware(ProtocolMiddleware, minimum=minimum)

    # Open like /v1/instance/name: an app that is too old must learn what it needs before it signs
    # in, and every answer (a 401 too) already carries the same two numbers in its headers.
    @app.get(
        "/v1/protocol", tags=["meta"], operation_id="meta.protocol",
        responses={200: {"model": ProtocolInfo}},
    )
    def protocol():
        """The protocol generations this hub serves, and until when each older one is kept."""
        return protocol_info(minimum)

    build = app.openapi

    def openapi() -> dict:
        doc = build()
        doc.setdefault("info", {})["x-onemind-protocol"] = {"header": PROTOCOL_HEADER, "current": PROTOCOL_CURRENT}
        return doc

    app.openapi = openapi  # type: ignore[method-assign]
