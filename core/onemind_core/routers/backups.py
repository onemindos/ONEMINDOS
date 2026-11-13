# SPDX-License-Identifier: Apache-2.0
"""Contract §12.12: backups and restores (CORE-BACKUP-8, DEV-API-11).

Reads (status, runs, snapshots, verifications, restores) are open to owners, adults and agents
(`backups:read`); browsing a snapshot's files is owner-only and every read is audited. Every change
is an action: `backup.run` and `backup.verify` (owners and agents may request), `backup.restore`,
`backup.destination.add|remove` and `backup.kit.issue` (owners only). Agents never approve. An
owner may add `"approve": true` to approve their own request in the same call (the owner shortcut
of §12.1); a restore still lands in Approvals first unless the owner does that on purpose.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ..auth import Principal
from ..backups.jobs import AgentError
from ..backups.service import BackupService, Unavailable
from ..backups.settings import BackupsSettings
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..ledger import utc

SNAP_RE = r"^[0-9a-f]{8,64}$"
DEST_RE = r"^dst_[0-9a-f]{16}$"
USB_UUID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
USER_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)
    expires_at: AwareDatetime | None = None
    approve: bool = False


class AppScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)


class PathScope(AppScope):
    path: str = Field(min_length=1, max_length=4096, pattern=r"^/")

    @field_validator("path")
    @classmethod
    def _plain(cls, v: str) -> str:
        # The approval card shows this path; the agent cleans it. Refuse anything they would read
        # differently (`..`, `.`, `//`), so the owner approves exactly what is restored.
        parts = v.rstrip("/").split("/")[1:]
        if not parts or any(s in ("", ".", "..") for s in parts):
            raise ValueError("path must be an absolute path without '.', '..' or empty segments")
        return v


class RunBody(_Request):
    scope: Literal["box"] | AppScope = "box"
    destination_id: str | None = Field(default=None, pattern=DEST_RE)


class VerifyBody(_Request):
    mode: Literal["scratch_restore", "check"] = "scratch_restore"
    latest: bool = True
    units: list[str] | None = Field(default=None, max_length=100)


class RestoreBody(_Request):
    snapshot_id: str = Field(pattern=SNAP_RE)
    scope: Literal["box"] | PathScope | AppScope
    mode: Literal["portable", "exact"] = "portable"
    target: Literal["in_place", "new_namespace"] = "in_place"


class DestinationBody(_Request):
    kind: Literal["usb", "box", "rest", "s3"]
    label: str = Field(min_length=1, max_length=80)
    primary: bool = False
    config: dict[str, str | bool]
    # Write-only: kept in memory until the owner approves, then written to the agent's 0600 files.
    # `sealed` (encrypted to GET /v1/secrets/public-key) replaces this once the secrets store lands.
    credentials: dict[str, str] | None = None


class KitConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, str] = Field(max_length=4)


def _check_destination(b: DestinationBody) -> dict:
    c, creds = dict(b.config), b.credentials or {}
    problem = None
    if b.kind == "usb":
        if not USB_UUID_RE.match(str(c.get("usb_uuid", ""))):
            problem = "config.usb_uuid must be the disk's filesystem UUID"
        c = {"usb_uuid": c.get("usb_uuid")}
    elif b.kind in ("box", "rest"):
        if not str(c.get("url", "")).startswith("https://") or not USER_RE.match(str(c.get("user", ""))):
            problem = "config.url must be https:// and config.user a plain name"
        elif not creds.get("password"):
            problem = "credentials.password is required"
        c = {"url": c.get("url"), "user": c.get("user"), "append_only": bool(c.get("append_only", b.kind == "box"))}
    else:
        if not str(c.get("endpoint", "")).startswith("https://") or not c.get("bucket"):
            problem = "config.endpoint must be https:// and config.bucket is required"
        elif not creds.get("access_key") or not creds.get("secret_key"):
            problem = "credentials.access_key and credentials.secret_key are required"
        c = {k: c[k] for k in ("endpoint", "bucket", "prefix", "region") if c.get(k)}
    if set(creds) - {"password", "ca", "access_key", "secret_key"}:
        problem = "credentials may hold password, ca, access_key and secret_key only"
    if problem:
        raise ApiError(422, "conflict", problem)
    return c


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings.section(BackupsSettings)
    svc = BackupService(gw, settings, pg=getattr(app.state, "databases", None))
    app.state.backups = svc
    gw.on_startup(svc.startup)
    gw.on_shutdown(svc.shutdown)
    principal = gw.principal

    @app.exception_handler(Unavailable)
    async def _unavailable(_: Request, exc: Unavailable):
        return JSONResponse(status_code=503, headers={"Retry-After": "30"},
                            content={"error": "unavailable", "message": exc.message, "reason": exc.reason, "retry_after_s": 30})

    @app.exception_handler(AgentError)
    async def _agent_error(_: Request, exc: AgentError):
        # The agent answered but refused or failed a read (no destination yet, a key mismatch):
        # a dependency problem (§12.2 `unavailable`), not a gateway crash.
        reason = "agent_refused" if exc.reason.startswith("refused") else "agent_failed"
        return JSONResponse(status_code=503, headers={"Retry-After": "30"},
                            content={"error": "unavailable", "message": str(exc)[:500], "reason": reason, "retry_after_s": 30})

    def deny(p: Principal, what: str) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not {what}")

    def reader(p: Principal = Depends(principal)) -> Principal:
        if not (p.is_owner or p.role in ("adult", "agent")):
            raise deny(p, "read backups")
        return p

    def owner(p: Principal = Depends(principal)) -> Principal:
        if not p.is_owner:
            raise deny(p, "do this (owner only)")
        return p

    def window(body: _Request) -> datetime:
        now = gw.clock()
        exp = utc(body.expires_at) if body.expires_at else now + timedelta(hours=24)
        if exp > now + timedelta(days=7):
            raise ApiError(422, "conflict", "expires_at may be at most 7 days ahead")
        return exp

    def shortcut(p: Principal, body: _Request) -> None:
        """§12.1: `"approve": true` from anyone but an owner is refused before anything is filed."""
        if body.approve and not p.is_owner:
            raise deny(p, "approve (owner shortcut)")

    def filed(p: Principal, body: _Request, action: dict, created: bool, extra: dict | None = None) -> JSONResponse:
        if body.approve and created:
            shortcut(p, body)
            action = gw.actions.approve(p, action["id"])
        headers = {"Location": f"/v1/actions/{action['id']}"}
        if not created:
            headers["OneMind-Idempotent-Replay"] = "true"
        return JSONResponse(status_code=202, content={**action, **(extra or {})}, headers=headers)

    def key(header: str | None) -> str:
        if header is not None and not 1 <= len(header) <= 200:
            raise ApiError(422, "conflict", "Idempotency-Key must be 1-200 characters")
        return header or "auto:" + secrets.token_hex(16)

    tags = ["backups"]

    @app.get("/v1/backups/status", operation_id="backups.status", tags=tags, responses=error_responses(401, 403))
    def status(_: Principal = Depends(reader)):
        return svc.status()

    @app.get("/v1/backups/destinations", operation_id="backups.destinations.list", tags=tags, responses=error_responses(401, 403))
    def destinations(p: Principal = Depends(principal)):
        if not (p.is_owner or p.role == "adult"):
            raise deny(p, "list backup destinations")
        return svc.destinations()

    @app.post("/v1/backups/destinations", operation_id="backups.destinations.add", tags=tags, status_code=202, responses=error_responses(401, 403, 409, 422))
    def add_destination(body: DestinationBody, p: Principal = Depends(owner),
                        idem: str | None = Header(default=None, alias="Idempotency-Key")):
        b = body.model_dump()
        b["config"] = _check_destination(body)
        action, created = svc.request_destination(p, b, idempotency_key=key(idem), expires_at=window(body), reason=body.reason)
        return filed(p, body, action, created)

    @app.delete("/v1/backups/destinations/{dest_id}", operation_id="backups.destinations.remove", tags=tags, status_code=202, responses=error_responses(401, 403, 404))
    def remove_destination(dest_id: str, p: Principal = Depends(owner),
                           idem: str | None = Header(default=None, alias="Idempotency-Key")):
        if not any(d.id == dest_id for d in svc.repo.destinations()):
            raise ApiError(404, "not_found", "no such destination")
        body = _Request()
        action, created = gw.actions.request_feature(p, "backup.destination.remove", {"destination_id": dest_id},
                                                     idempotency_key=key(idem), expires_at=window(body))
        return filed(p, body, action, created)

    @app.post("/v1/backups/runs", operation_id="backups.runs.request", tags=tags, status_code=202, responses=error_responses(401, 403, 409, 422))
    def request_run(body: RunBody, p: Principal = Depends(principal),
                    idem: str | None = Header(default=None, alias="Idempotency-Key")):
        shortcut(p, body)
        if not svc.enabled:
            raise Unavailable("backups are not switched on (ONEMIND_BACKUPS_ENABLED=1)", "backups_disabled")
        scope = body.scope if body.scope == "box" else body.scope.model_dump()
        params = {"scope": scope, **({"destination_id": body.destination_id} if body.destination_id else {})}
        action, created = gw.actions.request_feature(p, "backup.run", params, idempotency_key=key(idem),
                                                     expires_at=window(body), reason=body.reason)
        return filed(p, body, action, created)

    @app.get("/v1/backups/runs", operation_id="backups.runs.list", tags=tags, responses=error_responses(401, 403))
    def runs(_: Principal = Depends(reader)):
        return svc.runs()

    @app.get("/v1/backups/runs/{run_id}", operation_id="backups.runs.get", tags=tags, responses=error_responses(401, 403, 404))
    def run(run_id: str, _: Principal = Depends(reader)):
        return svc.run(run_id)

    @app.get("/v1/backups/snapshots", operation_id="backups.snapshots.list", tags=tags, responses=error_responses(401, 403))
    def snapshots(app_id: str | None = Query(default=None, pattern=APP_ID_RE.pattern),
                  unit: str | None = Query(default=None, max_length=128), _: Principal = Depends(reader)):
        return svc.snapshots(app_id=app_id, unit=unit)

    @app.get("/v1/backups/snapshots/{snapshot_id}", operation_id="backups.snapshots.get", tags=tags, responses=error_responses(401, 403, 404))
    def snapshot(snapshot_id: str, _: Principal = Depends(reader)):
        return svc.snapshot(snapshot_id)

    @app.get("/v1/backups/snapshots/{snapshot_id}/tree", operation_id="backups.snapshots.tree", tags=tags, responses=error_responses(401, 403, 404))
    def tree(snapshot_id: str, path: str = Query(default="/", max_length=4096), p: Principal = Depends(owner)):
        gw.audit.append("backup.browse", p.as_dict(), None, {"snapshot_id": snapshot_id, "path": path})
        return svc.tree(snapshot_id, path)

    @app.get("/v1/backups/snapshots/{snapshot_id}/file", operation_id="backups.snapshots.file", tags=tags, responses=error_responses(401, 403, 404))
    def file(snapshot_id: str, path: str = Query(min_length=2, max_length=4096), p: Principal = Depends(owner)):
        gw.audit.append("backup.download", p.as_dict(), None, {"snapshot_id": snapshot_id, "path": path})
        body, headers = svc.file(snapshot_id, path)
        name = re.sub(r'[^A-Za-z0-9._ -]', "_", headers["name"])[:200] or "file"
        return StreamingResponse(body, media_type="application/octet-stream", headers={
            "Content-Length": headers["Content-Length"], "Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/v1/backups/verify", operation_id="backups.verify", tags=tags, status_code=202, responses=error_responses(401, 403, 409, 422))
    def verify(body: VerifyBody, p: Principal = Depends(principal),
               idem: str | None = Header(default=None, alias="Idempotency-Key")):
        shortcut(p, body)
        if not svc.enabled:
            raise Unavailable("backups are not switched on (ONEMIND_BACKUPS_ENABLED=1)", "backups_disabled")
        params = {"mode": body.mode, "latest": body.latest, **({"units": body.units} if body.units else {})}
        action, created = gw.actions.request_feature(p, "backup.verify", params, idempotency_key=key(idem),
                                                     expires_at=window(body), reason=body.reason)
        return filed(p, body, action, created)

    @app.get("/v1/backups/verifications", operation_id="backups.verifications.list", tags=tags, responses=error_responses(401, 403))
    def verifications(_: Principal = Depends(reader)):
        return svc.verifications()

    @app.post("/v1/restores", operation_id="restores.request", tags=["restores"], status_code=202, responses=error_responses(401, 403, 404, 409, 422))
    def request_restore(body: RestoreBody, p: Principal = Depends(principal),
                        idem: str | None = Header(default=None, alias="Idempotency-Key")):
        if not p.is_owner:  # agents need the explicit grant actions:request:backup.restore (not in v0)
            raise deny(p, "request backup.restore")
        if body.scope == "box":
            raise ApiError(409, "stale_precondition",
                           "a whole-box restore runs at onboarding on a fresh box (onemind init --restore), not on a running one")
        if body.target != "in_place" or body.mode != "portable":
            raise ApiError(409, "stale_precondition", "v0 restores in place, portable mode only")
        b = {"snapshot_id": body.snapshot_id, "scope": body.scope.model_dump(), "mode": body.mode, "target": body.target}
        action, created = svc.request_restore(p, b, idempotency_key=key(idem), expires_at=window(body), reason=body.reason)
        restore = next((r for r in svc.restores() if r["action_id"] == action["id"]), None)
        return filed(p, body, action, created, {"restore": restore})

    @app.get("/v1/restores", operation_id="restores.list", tags=["restores"], responses=error_responses(401, 403))
    def restores(_: Principal = Depends(reader)):
        return svc.restores()

    @app.get("/v1/restores/{restore_id}", operation_id="restores.get", tags=["restores"], responses=error_responses(401, 403, 404))
    def restore(restore_id: str, _: Principal = Depends(reader)):
        return svc.restore(restore_id)

    @app.get("/v1/backups/kit", operation_id="backups.kit.get", tags=tags, responses=error_responses(401, 403))
    def kit(_: Principal = Depends(owner)):
        return svc.kit_state()

    @app.post("/v1/backups/kit", operation_id="backups.kit.issue", tags=tags, status_code=201, responses=error_responses(401, 403, 409))
    def issue_kit(p: Principal = Depends(owner), idem: str | None = Header(default=None, alias="Idempotency-Key")):
        """Owner shortcut: files backup.kit.issue and approves it; the key is in this response only."""
        if not svc.enabled:
            raise Unavailable("backups are not switched on (ONEMIND_BACKUPS_ENABLED=1)", "backups_disabled")
        action, created = gw.actions.request_feature(p, "backup.kit.issue", {}, idempotency_key=key(idem),
                                                     expires_at=gw.clock() + timedelta(minutes=10))
        if not created:
            raise ApiError(409, "conflict", "this kit was already issued; it is never shown twice")
        action = gw.actions.approve(p, action["id"])
        one_time = svc.take_one_time(action["id"])
        if action["state"] != "succeeded" or one_time is None:
            raise ApiError(409, "stale_precondition", (action.get("result") or {}).get("message") or "the kit was not issued")
        return JSONResponse(status_code=201, headers={"Cache-Control": "no-store"},
                            content={"action": action, "kit": svc.kit_state(), "one_time": one_time})

    @app.post("/v1/backups/kit/confirm", operation_id="backups.kit.confirm", tags=tags, responses=error_responses(401, 403, 404, 409))
    def confirm_kit(body: KitConfirmBody, p: Principal = Depends(owner)):
        return svc.confirm_kit(p, body.answers)
