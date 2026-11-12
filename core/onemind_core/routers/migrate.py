# SPDX-License-Identifier: Apache-2.0
"""Migration kit routes (CORE-DEPLOY-6, docs/leap/core/MIGRATE.md).

/v1/migrate/plans...  bearer-token routes: plan (owner, direct), read, and the step requests
                      (owner; 202 with the action, contract §12.1).
/v1/migrate/repo/...  the restic REST data plane for helper pods and restore Jobs. These
                      routes do not take a bearer token: each request carries a short-lived
                      per-action restic user (HTTP Basic), checked against migrate_repo_users.
                      They are left out of /openapi.json because they are restic's protocol,
                      not a client API.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..auth import Principal
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..ledger import utc
from ..migrate.boxkube import BoxKube
from ..migrate.repo import V2, Repo, RepoError, parse_range
from ..migrate.service import MigrateService, MigrateSettings

DNS_LABEL = r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
MAX_TTL = timedelta(days=7)
DEFAULT_TTL = timedelta(hours=24)


class PlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kubeconfig: str = Field(min_length=1, max_length=65536, description="a self-contained kubeconfig; held in memory only")
    namespace: str = Field(min_length=1, max_length=63, pattern=DNS_LABEL)
    context: str | None = Field(default=None, max_length=253)
    app_id: str | None = Field(default=None, max_length=59, pattern=APP_ID_RE.pattern)
    name: str | None = Field(default=None, min_length=1, max_length=80)


class StepBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)
    expires_at: AwareDatetime | None = None


class ImportBody(StepBody):
    bundle_sha256: str | None = Field(default=None, max_length=80, description="binds the approval to this bundle")


class KubeStepBody(StepBody):
    kubeconfig: str = Field(min_length=1, max_length=65536)
    context: str | None = Field(default=None, max_length=253)


class CopyBody(KubeStepBody):
    pvcs: list[str] | None = Field(default=None, max_length=100)


class CutoverBody(KubeStepBody):
    stop_old: bool = Field(default=False, description="let OneMind scale the old workloads to 0 (needs the scale verb)")


class RevertBody(StepBody):
    kubeconfig: str | None = Field(default=None, min_length=1, max_length=65536)
    context: str | None = Field(default=None, max_length=253)


def _expiry(gw: Gateway, given: datetime | None) -> datetime:
    now = gw.clock()
    if given is None:
        return now + DEFAULT_TTL
    given = utc(given)
    if given - now > MAX_TTL:
        raise ApiError(422, "conflict", "expires_at may be at most 7 days ahead")
    return given


def _accepted(action: dict, created: bool) -> JSONResponse:
    headers = {"Location": f"/v1/actions/{action['id']}"}
    if not created:
        headers["OneMind-Idempotent-Replay"] = "true"
    return JSONResponse(status_code=202 if created else 200, content=action, headers=headers)


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings.section(MigrateSettings)
    box = BoxKube(gw.settings.kubectl, gw.settings.executor_timeout_s) if gw.settings.executor == "kubernetes" else None
    svc = MigrateService(gw, settings, box=box)
    for ft in svc.action_types():
        gw.actions.register_type(ft)
    gw.on_startup(svc.reconcile)
    app.state.migrate = svc
    principal = gw.principal
    step_errors = error_responses(401, 403, 404, 409, 422)

    @app.post("/v1/migrate/plans", tags=["migrate"], status_code=201, responses=error_responses(401, 403, 409, 422))
    def create_plan(body: PlanBody, p: Principal = Depends(principal)):
        """Read a namespace of another cluster (GET only) and write a private app bundle plus a dry-run report."""
        return JSONResponse(status_code=201, content=svc.plan(
            p, kubeconfig=body.kubeconfig, namespace=body.namespace, context=body.context,
            app_id=body.app_id, name=body.name,
        ))

    @app.get("/v1/migrate/plans", tags=["migrate"], responses=error_responses(401, 403))
    def list_plans(p: Principal = Depends(principal)):
        """Owners, adults and agents; guests get 403."""
        svc.check_read(p)
        return svc.list()

    @app.get("/v1/migrate/plans/{plan_id}", tags=["migrate"], responses=error_responses(401, 403, 404))
    def get_plan(plan_id: str, p: Principal = Depends(principal)):
        svc.check_read(p)
        return svc.get(plan_id)

    @app.get("/v1/migrate/plans/{plan_id}/helper", tags=["migrate"], responses=error_responses(401, 403, 404))
    def helper_preview(plan_id: str, pvc: str, p: Principal = Depends(principal)):
        """The helper pod the copy step creates in the old cluster (credentials shown as placeholders)."""
        svc.check_read(p)
        return svc.helper_preview(plan_id, pvc)

    def key(given: str | None) -> str:
        return given or f"migrate-{uuid.uuid4()}"

    @app.post("/v1/migrate/plans/{plan_id}/import", tags=["migrate"], status_code=202, responses=step_errors)
    def request_import(plan_id: str, body: ImportBody, p: Principal = Depends(principal),
                       idempotency_key: str | None = Header(default=None, max_length=200)):
        bundle = body.bundle_sha256
        if bundle is None and p.is_owner:  # others are refused (403) by svc.request below
            bundle = svc.get(plan_id)["bundle_sha256"]
        return _accepted(*svc.request(
            p, "migrate.import", plan_id, params={"bundle_sha256": bundle}, kubeconfig=None, context=None,
            idempotency_key=key(idempotency_key), expires_at=_expiry(gw, body.expires_at), reason=body.reason,
        ))

    @app.post("/v1/migrate/plans/{plan_id}/copy", tags=["migrate"], status_code=202, responses=step_errors)
    def request_copy(plan_id: str, body: CopyBody, p: Principal = Depends(principal),
                     idempotency_key: str | None = Header(default=None, max_length=200)):
        params = {"pvcs": sorted(set(body.pvcs))} if body.pvcs else {}
        return _accepted(*svc.request(
            p, "migrate.copy", plan_id, params=params, kubeconfig=body.kubeconfig, context=body.context,
            idempotency_key=key(idempotency_key), expires_at=_expiry(gw, body.expires_at), reason=body.reason,
        ))

    @app.post("/v1/migrate/plans/{plan_id}/cutover", tags=["migrate"], status_code=202, responses=step_errors)
    def request_cutover(plan_id: str, body: CutoverBody, p: Principal = Depends(principal),
                        idempotency_key: str | None = Header(default=None, max_length=200)):
        return _accepted(*svc.request(
            p, "migrate.cutover", plan_id, params={"stop_old": body.stop_old}, kubeconfig=body.kubeconfig,
            context=body.context, idempotency_key=key(idempotency_key), expires_at=_expiry(gw, body.expires_at),
            reason=body.reason,
        ))

    @app.post("/v1/migrate/plans/{plan_id}/revert", tags=["migrate"], status_code=202, responses=step_errors)
    def request_revert(plan_id: str, body: RevertBody, p: Principal = Depends(principal),
                       idempotency_key: str | None = Header(default=None, max_length=200)):
        return _accepted(*svc.request(
            p, "migrate.revert", plan_id, params={}, kubeconfig=body.kubeconfig, context=body.context,
            idempotency_key=key(idempotency_key), expires_at=_expiry(gw, body.expires_at), reason=body.reason,
        ))

    # ---- restic REST data plane -----------------------------------------------------------------
    def repo_user(request: Request, plan_id: str, write: bool) -> Response | None:
        """None when the request may go on; else the 401/403 response to send."""
        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        user = secret = ""
        if scheme.lower() == "basic":
            try:
                user, _, secret = base64.b64decode(value.strip(), validate=True).decode().partition(":")
            except (binascii.Error, UnicodeDecodeError):
                user = ""
        mode = svc.store.check_user(user, secret, plan_id, gw.clock()) if user and secret else None
        if mode is None:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="onemind-migrate"'})
        if write and mode != "w":
            return Response(status_code=403)
        return None

    def repo(plan_id: str) -> Repo:
        return Repo(svc.repo_dir(plan_id))

    def repo_error(exc: RepoError) -> Response:
        return Response(status_code=exc.status, content=str(exc), media_type="text/plain")

    @app.post("/v1/migrate/repo/{plan_id}/", include_in_schema=False)
    @app.post("/v1/migrate/repo/{plan_id}", include_in_schema=False)
    def repo_create(plan_id: str, request: Request, create: bool = False):
        denied = repo_user(request, plan_id, write=True)
        if denied is not None:
            return denied
        if not create:
            return Response(status_code=400)
        repo(plan_id).create()
        return Response(status_code=200)

    @app.api_route("/v1/migrate/repo/{plan_id}/config", methods=["HEAD", "GET", "POST"], include_in_schema=False)
    async def repo_config(plan_id: str, request: Request):
        return await object_route(plan_id, "config", None, request)

    @app.get("/v1/migrate/repo/{plan_id}/{typ}/", include_in_schema=False)
    def repo_list(plan_id: str, typ: str, request: Request):
        denied = repo_user(request, plan_id, write=False)
        if denied is not None:
            return denied
        try:
            items = repo(plan_id).listing(typ)
        except RepoError as exc:
            return repo_error(exc)
        if V2 in request.headers.get("accept", ""):
            return JSONResponse(items, media_type=V2)
        return JSONResponse([i["name"] for i in items])

    @app.api_route("/v1/migrate/repo/{plan_id}/{typ}/{name}", methods=["HEAD", "GET", "POST", "DELETE"],
                   include_in_schema=False)
    async def repo_object(plan_id: str, typ: str, name: str, request: Request):
        return await object_route(plan_id, typ, name, request)

    async def object_route(plan_id: str, typ: str, name: str | None, request: Request) -> Response:
        method = request.method
        denied = repo_user(request, plan_id, write=method in ("POST", "DELETE"))
        if denied is not None:
            return denied
        r = repo(plan_id)
        try:
            if method == "POST":
                await r.write(typ, name, request.stream())
                return Response(status_code=200)
            if method == "DELETE":
                r.delete(typ, name or "")
                return Response(status_code=200)
            size = r.stat(typ, name)
            if size is None:
                return Response(status_code=404)
            if method == "HEAD":
                return Response(status_code=200, headers={"Content-Length": str(size)})
            rng = parse_range(request.headers.get("range"), size)
            if rng is None:
                return Response(content=r.read(typ, name), media_type="application/octet-stream")
            start, end = rng
            return Response(
                status_code=206, content=r.read(typ, name, start, end), media_type="application/octet-stream",
                headers={"Content-Range": f"bytes {start}-{end}/{size}"},
            )
        except RepoError as exc:
            return repo_error(exc)
