# SPDX-License-Identifier: Apache-2.0
"""F-7 owner override (override.py): wiring, and what the approval card needs to know.

GET /v1/apps/{id}/owner-override   owner: {enabled, scan_problem, eligible, refusal, confirm, step_up}

The override itself is a field of the approve body (routers/actions.py).
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..override import ENV, OwnerOverride, OwnerOverrideSettings

log = logging.getLogger("onemind.override")


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(OwnerOverrideSettings)
    ov = OwnerOverride(cfg.enabled, gw.audit, gw.events)
    gw.actions.owner_override = ov
    app.state.owner_override = ov
    principal = gw.principal

    if cfg.enabled:
        log.warning("%s=1: owners may approve installs whose scan failed (F-7 owner override)", ENV)

        def announce() -> None:
            gw.events.publish_event(
                "security", "owner_override.enabled", {"setting": ENV}, severity="warning",
                dedupe_key="owner-override-enabled",
            )

        gw.on_startup(announce)

    @app.get("/v1/apps/{app_id}/owner-override", tags=["apps"], responses=error_responses(401, 403, 404))
    def describe(app_id: str, p: Principal = Depends(principal)):
        if not p.is_owner:
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not use the owner override")
        entry = gw.catalog.get(app_id)
        if entry is None:
            raise ApiError(404, "not_found", f"app {app_id!r} is not in the catalog")
        return ov.describe(entry, gw.clock())
