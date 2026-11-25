# SPDX-License-Identifier: Apache-2.0
"""Radio-found cards (issue #732): GET /v1/radios and POST /v1/radios/{id}/confirm.

The cards come from the hardware profile in each machine's latest heartbeat (radios.py). Confirming
is an owner's statement about what a radio is ("MeshCore companion (USB)"); it opens, probes and
sends nothing, and the grant that would pass the radio into an app is a separate action (#854). A radio
is addressed by its stable id, <node_id>.<kind><n> (radios.radio_id), as every later radio route is.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Path

from ..apimodels import RADIO_ID, RadioCard, RadioConfirmRequest
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..radios import CONFIRM, RadioService, parse_radio_id

# Right after the node routes (routers/nodes.py, 110).
ORDER = 111

# The cards come from the hardware profile, so reading them needs what the profile needs. Confirming
# asks for every scope (an owner as themselves; a scoped token is refused) and the handler checks the
# caller is an owner and a person: an agent never confirms a radio.
register_route_scope("GET,HEAD", r"/v1/radios", ("nodes:read",))
register_route_scope("POST", r"/v1/radios/[^/]+/confirm", ("*",))


def register(app: FastAPI, gw: Gateway) -> None:
    registry = gw.registry
    svc = RadioService(gw.db, gw.clock)
    app.state.radios = svc

    @app.get(
        "/v1/radios", tags=["nodes"], operation_id="radios.list",
        response_model=list[RadioCard], responses=error_responses(401, 403),
    )
    def list_radios(_: Principal = Depends(gw.principal)):
        """Radio-found cards: every USB serial line on every machine. A known radio carries its kind and
        stable name; a LoRa radio's card asks the owner to confirm it. Unknown lines are never named."""
        return svc.cards(registry.list())

    @app.post(
        "/v1/radios/{radio_id}/confirm", tags=["nodes"], operation_id="radios.confirm",
        response_model=RadioCard, responses=error_responses(401, 403, 404, 409, 422),
    )
    def confirm_radio(body: RadioConfirmRequest, radio_id: str = Path(pattern=RADIO_ID, description="the radio's id from its card, e.g. 3f9c2a1b7d4e.lora0"),
                      p: Principal = Depends(gw.principal)):
        """An owner confirms what a radio on its card is (a LoRa radio: "MeshCore companion (USB)").

        Refused for anyone but an owner, for a line that is not a known radio (an unknown serial device is
        never named or granted), for a kind that needs no confirming and for a machine that is not online.
        Nothing is opened or sent; the grant is a separate action (#854)."""
        attempt = {"radio_id": radio_id, "profile": body.profile}
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "confirm a radio", "reason": "permission_denied", **attempt})
            raise ApiError(403, "permission_denied", "only an owner may confirm a radio")
        parsed = parse_radio_id(radio_id)  # the path pattern already refused anything else (422)
        node = registry.get(parsed[0]) if parsed else None
        card = next((c for c in svc.node_cards(node) if c["id"] == radio_id), None) if node else None
        if card is None:
            raise ApiError(404, "not_found", "no radio with that id")
        need = CONFIRM.get(card["kind"])
        if need is None or need["profile"] != body.profile:
            raise ApiError(409, "conflict", f"a {card['kind']} radio is not confirmed as {body.profile}")
        if card["node_status"] != "online":
            raise ApiError(409, "conflict", "the machine is not online; confirm the radio while it is plugged in")
        svc.confirm(card, body.profile, p.as_dict())
        gw.audit.append("radio.confirmed", p.as_dict(), None, {**attempt, "node_id": card["node_id"], "device": card["device"],
                                                                "kind": card["kind"], "usb_id": card["usb_id"], "usb_port": card["usb_port"]})
        return next(c for c in svc.node_cards(node) if c["id"] == radio_id)
