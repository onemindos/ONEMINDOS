# SPDX-License-Identifier: Apache-2.0
"""Contract §12.41: owner-only first-run software settings."""
from typing import Literal
from zoneinfo import available_timezones

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..onboarding import OnboardingService


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


class OnboardingSettingsView(BaseModel):
    box_name: str | None
    time_zone: str | None
    backup_choice: Literal["usb", "peer", "s3", "later"]
    backup_destination_id: str | None
    saved: bool


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
