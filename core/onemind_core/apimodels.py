# SPDX-License-Identifier: Apache-2.0
"""Response shapes published in /openapi.json for the SDKs (docs/leap/dev/SDK.md §3.2, DEV-SDK-1).

These models document what the routes already return; the routes attach them through
`responses={200: {"model": ...}}`, which describes the body without filtering it, so adding a
model here never changes a response. Enums that may grow (action state, node status) are plain
strings marked `x-onemind-open-enum`: an SDK must accept a value it does not know.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

OPEN_ENUM = {"x-onemind-open-enum": True}


class Healthz(BaseModel):
    ok: bool


class Instance(BaseModel):
    """GET /v1/instance."""

    name: str
    version: str
    hub_node_id: str | None


class PrincipalRef(BaseModel):
    """{id, kind, role} of contract §3; kind and role may gain values (§12.1). An action's
    `requested_by` carries only {id, kind} (§12.4), so role is optional."""

    model_config = ConfigDict(extra="allow")
    id: str
    kind: str = Field(json_schema_extra=OPEN_ENUM)
    role: str | None = Field(default=None, json_schema_extra=OPEN_ENUM)


class NodeOS(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    version_id: str | None = None
    pretty: str | None = None


class NodeK3s(BaseModel):
    model_config = ConfigDict(extra="allow")
    present: bool | None = None
    role: str | None = None
    ready: bool | None = None


class Node(BaseModel):
    """One node: the §2 heartbeat plus the gateway's `status` and `last_seen`. More fields may appear."""

    model_config = ConfigDict(extra="allow")
    schema_: str | None = Field(default=None, alias="schema")
    node_id: str
    hostname: str | None = None
    role: str | None = None
    board: str | None = Field(default=None, json_schema_extra=OPEN_ENUM)
    arch: str | None = None
    os: NodeOS | None = None
    k3s: NodeK3s | None = None
    status: str = Field(description="online | stale | offline", json_schema_extra=OPEN_ENUM)
    last_seen: str = Field(description="RFC 3339 time the gateway last received a heartbeat")


class Action(BaseModel):
    """One action of the ledger (contract §3). §12.4 adds optional fields; ignore what you do not know."""

    model_config = ConfigDict(extra="allow")
    id: str
    type: str = Field(description="app.install | app.remove | app.start | app.stop | app.restart | app.update | app.configure | app.delete_data (more in §12.5)", json_schema_extra=OPEN_ENUM)
    params: dict[str, Any]
    state: str = Field(
        description="requested | awaiting_approval | accepted | dispatched | succeeded | failed | "
        "cancelled | expired | outcome_unknown",
        json_schema_extra=OPEN_ENUM,
    )
    requested_by: PrincipalRef
    idempotency_key: str
    created_at: str
    updated_at: str
    expires_at: str
    decided_by: PrincipalRef | None
    decided_at: str | None
    result: dict[str, Any] | None
    version: int
    risk: str | None = Field(default=None, description="read | write | sensitive | destructive | actuate (§12.3)")
    plan: dict[str, Any] | None = Field(default=None, description="§12.4: what the action would do, rendered at request time")
    plan_sha256: str | None = Field(default=None, description="§12.4: fingerprint the approval is bound to")
    progress: dict[str, Any] | None = Field(default=None, description="{step, pct} while an executor runs")


class AuditRecord(BaseModel):
    """One hash-chained audit line (contract §3 "Audit", §12.16)."""

    seq: int
    ts: str
    event: str
    principal: PrincipalRef | None
    action_id: str | None
    data: dict[str, Any]
    prev_hash: str
    hash: str


class AuditHead(BaseModel):
    seq: int
    hash: str


class AuditVerify(BaseModel):
    """GET /v1/audit/verify (§12.16). `last_checkpoint` stays null until signed checkpoints ship (H-10)."""

    ok: bool
    records: int
    head: AuditHead | None
    first_bad_seq: int | None
    reason: str
    checked_at: str
    last_checkpoint: dict[str, Any] | None


class PlanPreview(BaseModel):
    """GET /v1/apps/{id}/plan and POST /v1/plans (contract §12.4): what an action would do. Files nothing."""

    type: str = Field(description="the action type previewed", json_schema_extra=OPEN_ENUM)
    app_id: str
    risk: str = Field(description="read | write | sensitive | destructive | actuate (§12.3)", json_schema_extra=OPEN_ENUM)
    policy_verdict: str = Field(
        description="needs_approval | refused (the app is in a state this action cannot start from)",
        json_schema_extra=OPEN_ENUM,
    )
    reason: str | None = Field(description="why the verdict is refused; null otherwise")
    plan: dict[str, Any] = Field(description="summary, objects, volumes, warnings: what the approval card shows")
    plan_sha256: str = Field(description="send this with the request and the approval; a different plan is refused")


class AppCredentials(BaseModel):
    """GET /v1/apps/{id}/credentials: the app's generated login. Owner only, audited, never cached."""

    username: str | None
    password: str
