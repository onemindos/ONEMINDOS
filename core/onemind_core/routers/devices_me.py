# SPDX-License-Identifier: Apache-2.0
"""My devices (#715): GET /v1/me/devices and DELETE /v1/me/devices/{device_id} (Lost this device).

/v1/devices belongs to the IoT device registry (#728); a person's own phones, laptops and browsers
live under /v1/me. Logic is in devices/service.py."""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel

from ..auth import Principal
from ..context import Gateway
from ..devices import MyDevicesService
from ..errors import error_responses
from ..identity import ctx_of
from ..identity.scopes import register_route_scope

# After identity (260), whose service this reads, and notifications (240), whose push registrations it joins.
ORDER = 262

# Self-service: the handler checks for a person's own session (never an API token or agent). At module
# level, so creating the app twice does not grow the scope registry (#323).
register_route_scope("GET,HEAD", r"/v1/me/devices", None)
register_route_scope("DELETE", r"/v1/me/devices/[^/]+", None)


class MyDeviceCredential(BaseModel):
    source: Literal["sessions", "passkeys", "approver_keys", "push"]
    id: str
    label: str
    detail: str
    created_at: str | None
    last_seen_at: str | None


class MyDevice(BaseModel):
    id: str
    label: str
    kind: Literal["phone", "browser", "app", "unknown"]
    current: bool
    last_seen_at: str | None
    first_seen_at: str | None
    credentials: list[MyDeviceCredential]


class MyDeviceSources(BaseModel):
    sessions: bool
    passkeys: bool
    approver_keys: bool
    push: bool
    mesh: bool
    nats: bool


class MyDevices(BaseModel):
    devices: list[MyDevice]
    sources: MyDeviceSources


class MyDeviceRevoked(BaseModel):
    sessions: int
    passkeys: int
    approver_keys: int
    push: int


class MyDeviceRemoved(BaseModel):
    id: str
    removed: bool
    revoked: MyDeviceRevoked


def register(app: FastAPI, gw: Gateway) -> None:
    svc = MyDevicesService(app.state.identity, getattr(app.state, "notify", None))
    app.state.my_devices = svc
    principal = gw.principal

    @app.get("/v1/me/devices", operation_id="me.devices.list", tags=["auth"], response_model=MyDevices,
             responses=error_responses(401, 403))
    def my_devices(request: Request, p: Principal = Depends(principal)):
        """Your devices: each joins the sessions, passkeys, approver keys and push registrations of one
        app install (its `install_id`), or, for credentials without one, that carry its name, with when
        it was last seen."""
        return svc.list(ctx_of(request), p)

    @app.delete("/v1/me/devices/{device_id}", operation_id="me.devices.remove", tags=["auth"],
                response_model=MyDeviceRemoved, responses=error_responses(401, 403, 409))
    def remove_my_device(device_id: str, request: Request, p: Principal = Depends(principal)):
        """Revoke a lost device from a signed-in session. Refuses the current device or the last sign-in
        method and requires stronger proof to remove the last proven keys. If the device is already
        gone, `removed` is false."""
        return svc.remove(ctx_of(request), p, device_id)
