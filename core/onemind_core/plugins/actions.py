# SPDX-License-Identifier: Apache-2.0
"""Plugin ledger views never disclose actions filed by another principal."""
from __future__ import annotations

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError


def _owned(action, principal: Principal) -> bool:
    return (action.requested_by or {}) == {"id": principal.id, "kind": "plugin"}


def own_actions(gw: Gateway, principal: Principal) -> list[dict]:
    # Filter before expiry/projection: no unrelated action is read into the response.
    return [gw.actions.expire_if_due(a).to_json() for a in gw.repo.list() if _owned(a, principal)]


def own_action(gw: Gateway, principal: Principal, action_id: str) -> dict:
    action = gw.repo.get(action_id)
    if action is None or not _owned(action, principal):
        raise ApiError(404, "not_found", "no such action")
    return gw.actions.expire_if_due(action).to_json()
