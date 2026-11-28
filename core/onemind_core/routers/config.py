# SPDX-License-Identifier: Apache-2.0
"""Owner-only private Git snapshot, dry run, and config.apply approval filing."""

import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Response
from pydantic import BaseModel, ConfigDict, Field

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..boxbundle import CONFIG_APPLY
from ..boxbundle.config_apply import FILES, SCHEMAS, ConfigApply, collect_all, read_documents, snapshot
from ..boxbundle.config_export import render
from ..boxbundle.manifest import BundleRefused, canonical, sha256
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope

ORDER = 290  # after backups, identity, and automation
SECURITY = {"security": [{"bearer": ["*"]}]}
register_route_scope("GET", r"/v1/config/export", ("*",))
register_route_scope("POST", r"/v1/config/(diff|apply)", ("*",))


class ConfigExportView(BaseModel):
    yaml: str = Field(description="Settings YAML, retained for clients of the single-file export.")
    files: dict[str, str]


class ConfigDiffBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    files: dict[str, str] = Field(min_length=1, max_length=len(FILES))


class ConfigApplyBody(ConfigDiffBody):
    revision: str = Field(pattern="^[0-9a-f]{64}$")


class ConfigChange(BaseModel):
    file: str
    before: str
    after: str


class ConfigDiffView(BaseModel):
    revision: str
    changes: list[ConfigChange]
    blockers: list[str]


def documents(body: ConfigDiffBody) -> dict:
    if body.files.keys() - SCHEMAS.keys():
        raise ApiError(422, "conflict", "use the supported configuration filenames")
    if any(len(value.encode("utf-8")) > 200 * 1024 for value in body.files.values()):
        raise ApiError(422, "conflict", "a configuration file exceeds 200 KiB")
    try:
        return read_documents(body.files)
    except BundleRefused as exc:
        raise ApiError(422, "conflict", exc.problems[0]) from None


def register(app: FastAPI, gw: Gateway) -> None:
    svc = ConfigApply(gw, app.state.backups)
    # Sensitive requests always wait for the owner and are ineligible for automation and standing approvals.
    gw.actions.register_type(CONFIG_APPLY, FeatureAction("sensitive", svc.run, check=svc.recheck, bind_plan=True))

    def owner(p: Principal = Depends(gw.principal)) -> Principal:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "config as code", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "configuration snapshots require the owner")
        return p

    @app.get("/v1/config/export", operation_id="config.export", tags=["config"],
             response_model=ConfigExportView, responses=error_responses(401, 403, 409), openapi_extra=SECURITY)
    def export(response: Response, p: Principal = Depends(owner)):
        """Export the schema-approved configuration as versioned cleartext YAML."""
        try:
            with snapshot(gw) as read:
                files = {name: render(doc) for name, doc in collect_all(read, svc.backups).items()}
        except BundleRefused:
            raise ApiError(409, "conflict", "box configuration did not pass export checks") from None
        gw.audit.append("config.exported", p.as_dict(), None, {"files": {
            name: {"schema": SCHEMAS[name], "sha256": sha256(content.encode("utf-8"))}
            for name, content in files.items()
        }})
        response.headers["Cache-Control"] = "no-store"
        return ConfigExportView(yaml=files["settings.yaml"], files=files)

    def preview(proposed: dict):
        try:
            return svc.preview(proposed)
        except BundleRefused:
            raise ApiError(409, "conflict", "live box configuration did not pass export checks") from None

    @app.post("/v1/config/diff", operation_id="config.diff", tags=["config"],
              response_model=ConfigDiffView, responses=error_responses(401, 403, 409, 422), openapi_extra=SECURITY)
    def diff(body: ConfigDiffBody, response: Response, _: Principal = Depends(owner)):
        """Compare validated YAML with the live configuration without writing settings or filing an action."""
        result = preview(documents(body))
        response.headers["Cache-Control"] = "no-store"
        return ConfigDiffView(revision=result.revision, changes=result.changes, blockers=result.blockers)

    @app.post("/v1/config/apply", operation_id="config.apply", tags=["config"], response_model=Action, status_code=202,
              responses=error_responses(401, 403, 409, 422, 429), openapi_extra=SECURITY)
    def apply(body: ConfigApplyBody, response: Response, p: Principal = Depends(owner),
              idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """File an owner approval for a dry-run revision. Approval is a separate action."""
        proposed = documents(body)
        digest = sha256(canonical(proposed))
        key = idem or "auto:" + secrets.token_hex(16)
        existing = gw.repo.get_by_idempotency_key(key)
        if existing is not None:
            if (existing.type != CONFIG_APPLY or existing.requested_by["id"] != p.id
                    or existing.params.get("revision") != body.revision or existing.params.get("source_sha256") != digest):
                raise ApiError(409, "conflict", "idempotency key was used for a different request")
            action, created = gw.actions.request_feature(
                p, CONFIG_APPLY, existing.params, idempotency_key=key, expires_at=existing.expires_at,
            )
        else:
            result = preview(proposed)
            if result.revision != body.revision:
                raise ApiError(409, "stale_precondition", "configuration or proposed change differs from the dry run")
            if result.blockers:
                raise ApiError(422, "conflict", result.blockers[0])
            if not result.patch:
                raise ApiError(409, "conflict", "configuration already matches the proposed files")
            action, created = gw.actions.request_feature(
                p, CONFIG_APPLY, {"revision": result.revision, "base_revision": result.base_revision,
                                 "source_sha256": digest, "patch": result.patch},
                idempotency_key=key, expires_at=gw.clock() + timedelta(hours=24), pending_cap=True,
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Location"] = f"/v1/actions/{action['id']}"
        if not created:
            response.headers["OneMind-Idempotent-Replay"] = "true"
        return action
