# SPDX-License-Identifier: Apache-2.0
"""Contract §12.41: owner-only first-run software settings."""
import secrets
from datetime import timedelta
from typing import Annotated, Literal
from zoneinfo import available_timezones

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..auth import Principal
from ..backups.service import Unavailable
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..ledger import utc
from ..onboarding import OnboardingService

# Owner only (#323): the row asks for every scope, the same answer as the fail-closed fallback.
register_route_scope("GET", r"/v1/onboarding/state", ("*",))


class OnboardingSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    box_name: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
    time_zone: str = Field(min_length=1, max_length=128)
    backup_choice: Literal["usb", "peer", "s3", "later"]
    backup_destination_id: str | None = Field(default=None, pattern=r"^dst_[0-9a-f]{16}$")

    @field_validator("time_zone")
    @classmethod
    def iana_zone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("choose an installed IANA time zone")
        return value


class RestoreCandidatesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination_id: str = Field(pattern=r"^dst_[0-9a-f]{16}$")
    box_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    # The owner recovery key from the kit (its QR carries key= and box=). An old box's repository is sealed with
    # that box's own device key, so a box id alone cannot open it; the key is used once, in memory, never stored.
    recovery_key: str | None = Field(default=None, min_length=32, max_length=256, pattern=r"^[^\r\n]+$",
                                     json_schema_extra={"writeOnly": True})

    @model_validator(mode="after")
    def _other_box_needs_its_key(self):
        if self.box_id and not self.recovery_key:
            raise ValueError("restoring another box's backup needs the owner recovery key from the kit")
        if self.recovery_key and not self.box_id:
            raise ValueError("recovery_key goes with the box_id it opens")
        return self


class RestoreAppBody(JsonBody):
    """Put one app's data back from another box's backup. The app is installed first, then this restores its data."""
    model_config = ConfigDict(extra="forbid")
    destination_id: str = Field(pattern=r"^dst_[0-9a-f]{16}$")
    box_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    recovery_key: str = Field(min_length=32, max_length=256, pattern=r"^[^\r\n]+$", json_schema_extra={"writeOnly": True})
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    app_id: str = Field(min_length=1, max_length=59, pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
    reason: str | None = Field(default=None, max_length=500)
    approve: bool = False


class RestorePoint(BaseModel):
    run_id: str | None
    taken_at: str | None
    reason: str | None
    system: bool
    apps: list[str]
    snapshot_ids: list[str]


class RestoreCandidatesView(BaseModel):
    destination_id: str
    points: list[RestorePoint]


class OnboardingSettingsView(BaseModel):
    box_name: str | None
    time_zone: str | None
    backup_choice: Literal["usb", "peer", "s3", "later"]
    backup_destination_id: str | None
    saved: bool


class OnboardingKit(BaseModel):
    state: Literal["missing", "issued", "confirmed"]
    confirmed_at: str | None
    fingerprint: str | None
    positions: list[int]


class OnboardingStateView(BaseModel):
    """What the first-run wizard needs to decide whether to open: no browser flag involved."""
    complete: bool
    settings_saved: bool
    backups_enabled: bool
    destinations: int
    kit: OnboardingKit


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 210


def register(app: FastAPI, gw: Gateway) -> None:
    svc = OnboardingService(gw.db)
    app.state.onboarding = svc

    def owner(p: Principal = Depends(gw.principal)) -> Principal:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "onboarding.settings", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "first-run settings require the owner")
        # Identity credentials also pass the existing route-scope guard (unknown route needs *).
        return p

    @app.get("/v1/onboarding/state", operation_id="onboarding.state", tags=["onboarding"],
             response_model=OnboardingStateView, responses=error_responses(401, 403))
    def state(response: Response, _: Principal = Depends(owner)):
        """The wizard is complete once the first-run settings are saved and, when a backup destination exists,
        the emergency kit is typed back (confirmed). Read-only; the recovery key is never part of this answer."""
        response.headers["Cache-Control"] = "no-store"
        backups = app.state.backups
        saved = svc.read()["saved"]
        kit = backups.kit_state()
        dests = len(backups.destinations())
        return {"complete": saved and (dests == 0 or kit["state"] == "confirmed"), "settings_saved": saved,
                "backups_enabled": bool(backups.enabled), "destinations": dests,
                "kit": {k: kit[k] for k in ("state", "confirmed_at", "fingerprint", "positions")}}

    @app.get("/v1/onboarding/settings", operation_id="onboarding.settings.get", tags=["onboarding"],
             response_model=OnboardingSettingsView, responses=error_responses(401, 403))
    def read(response: Response, _: Principal = Depends(owner)):
        response.headers["Cache-Control"] = "no-store"
        return svc.read()

    @app.put("/v1/onboarding/settings", operation_id="onboarding.settings.save", tags=["onboarding"],
             response_model=OnboardingSettingsView, responses=error_responses(401, 403, 422))
    def save(body: OnboardingSettingsBody, response: Response, p: Principal = Depends(owner)):
        dest = body.backup_destination_id
        if dest is not None:
            kind = {"usb": "usb", "peer": "box", "s3": "s3"}.get(body.backup_choice)
            if kind is None or not any(d["id"] == dest and d["kind"] == kind
                                       for d in app.state.backups.destinations()):
                raise ApiError(422, "conflict", "choose an existing backup destination matching the choice")
        values = body.model_dump()
        result = svc.save(values)
        gw.audit.append("onboarding.settings.saved", p.as_dict(), None, values)
        response.headers["Cache-Control"] = "no-store"
        return result

    @app.post("/v1/onboarding/restore/apps", operation_id="onboarding.restore.app", tags=["onboarding"], status_code=202,
              responses=error_responses(401, 403, 404, 409, 422, 503))
    def restore_app(body: RestoreAppBody, request: Request, p: Principal = Depends(owner),
                    idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """Restore one installed app's data from another box's backup point (new hardware, UMB-P08).

        Files the ordinary `backup.restore` action (undo snapshot, stop, swap, start, health gate, roll back), with the
        owner recovery key held in memory for that one action only: never in the action, the audit log or a response.
        An unclaimed installation can approve in the same call. A household owner approves the filed action
        at POST /v1/actions/{id}/approve with the verification it asks for."""
        backups = app.state.backups
        if not backups.enabled:
            raise Unavailable("backups are not switched on (ONEMIND_BACKUPS_ENABLED=1)", "backups_disabled")
        action, created = backups.request_first_run_restore(
            p, body.model_dump(), idempotency_key=idem or "auto:" + secrets.token_hex(16),
            expires_at=utc(gw.clock() + timedelta(hours=24)), reason=body.reason)
        if body.approve and created:
            identity = getattr(app.state, "identity", None)
            if identity is None or not identity.account_setup_exists():
                for guard in gw.approval_guards:
                    guard(p, action["id"], {}, request)
                action = gw.actions.approve(p, action["id"])
        restore = next((r for r in backups.restores() if r["action_id"] == action["id"]), None)
        headers = {"Location": f"/v1/actions/{action['id']}", "Cache-Control": "no-store"}
        if not created:
            headers["OneMind-Idempotent-Replay"] = "true"
        return JSONResponse(status_code=202, content={**action, "restore": restore}, headers=headers)

    @app.post("/v1/onboarding/restore/candidates", operation_id="onboarding.restore.candidates", tags=["onboarding"],
              response_model=RestoreCandidatesView, responses=error_responses(401, 403, 404, 409, 422, 503))
    def restore_candidates(body: RestoreCandidatesBody, response: Response, p: Principal = Depends(owner)):
        """The first-run wizard's "restore from a backup" step: list what a destination holds. Read-only.

        Backup made by this box's hardware: send only `destination_id`. Backup made by another (dead or replaced) box:
        also send its `box_id` and the owner `recovery_key` from the recovery kit (the kit QR carries both); a fresh box
        has no way to discover the old box id, and its own device key cannot open the old repository."""
        backups = app.state.backups
        if not backups.enabled:
            raise Unavailable("backups are not switched on (ONEMIND_BACKUPS_ENABLED=1)", "backups_disabled")
        points = backups.restore_candidates(body.destination_id, body.box_id, body.recovery_key)
        gw.audit.append("onboarding.restore.candidates", p.as_dict(), None,
                        {"destination_id": body.destination_id, "box_id": body.box_id, "points": len(points)})
        response.headers["Cache-Control"] = "no-store"
        return {"destination_id": body.destination_id, "points": points}
