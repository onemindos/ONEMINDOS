# SPDX-License-Identifier: Apache-2.0
"""GET /v1/subjects and /v1/subjects/check: the one NATS subject tree (issue #600, contract §12.9).

The registry is read from sdk/schema/onemind.subjects.json (core/onemind_core/subjects.py). The
check route answers "may this publisher send on this subject?" with a reason, so the app checker,
the CLI and screens explain a refusal the same way the gateway and the lint do. Read-only: it
never publishes anything.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel

from .. import subjects
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope

ORDER = 338

# The subject tree is the same contract the events stream (§12.8) is built on.
register_route_scope("GET,HEAD", r"/v1/subjects(/check)?", ("events:read",))


class SubjectTreeRetention(BaseModel):
    """How long a stream keeps messages: policy limits, workqueue, latest (last value per subject) or none."""

    policy: Literal["limits", "workqueue", "latest", "none"]
    max_age_s: int | None = None
    max_bytes: int | None = None
    deny_delete: bool | None = None
    deny_purge: bool | None = None


class SubjectTreePattern(BaseModel):
    pattern: str
    publishers: list[Literal["gateway", "node", "app", "agent"]]
    owner: str | None
    stream: str | None
    retention: SubjectTreeRetention
    envelope: str


class SubjectTreeKind(BaseModel):
    kind: str
    description: str
    core: bool
    stream: str | None
    retention: SubjectTreeRetention
    envelope: str
    subjects: list[SubjectTreePattern]


class SubjectTreeReserved(BaseModel):
    kind: str
    reason: str


class SubjectTreeEnvelope(BaseModel):
    id: str
    file: str | None
    contract: str | None
    description: str


class SubjectTreeMapping(BaseModel):
    """One row of the mapping table: a subject of an older grammar (`old`) and where it lives in the tree (`new`)."""

    grammar: str
    old: str
    new: str
    note: str


class SubjectTree(BaseModel):
    """GET /v1/subjects."""

    version: str
    root: str
    grammar: str
    kinds: list[SubjectTreeKind]
    reserved: list[SubjectTreeReserved]
    envelopes: list[SubjectTreeEnvelope]
    mappings: list[SubjectTreeMapping]


class SubjectTreeCheck(BaseModel):
    """GET /v1/subjects/check."""

    subject: str
    publisher: str
    ok: bool
    reason: str
    kind: str | None
    pattern: str | None


def _registry() -> subjects.Registry:
    try:
        return subjects.load()
    except subjects.RegistryError as exc:
        raise ApiError(503, "unavailable", f"the subject registry cannot be read: {exc}", reason="subjects_unavailable") from None


def register(app: FastAPI, gw: Gateway) -> None:
    @app.get("/v1/subjects", tags=["subjects"], operation_id="subjects.list", response_model=SubjectTree,
             responses=error_responses(401, 503))
    def subjects_list(_: Principal = Depends(gw.principal)):
        """Every subject kind: who may publish, the stream and retention, the envelope schema; the reserved
        kinds with the reason; and the mapping from the older grammars (contract 12.9, plugin SDK, cluster)."""
        return _registry().public()

    @app.get("/v1/subjects/check", tags=["subjects"], operation_id="subjects.check", response_model=SubjectTreeCheck,
             responses=error_responses(401, 503))
    def subjects_check(
        _: Principal = Depends(gw.principal),
        subject: str = Query(..., max_length=subjects.MAX_SUBJECT_LEN),
        publisher: Literal["gateway", "node", "app", "agent"] = Query("app"),
        owner_id: str | None = Query(None, max_length=64, description="the publisher's own node, app or agent id"),
    ):
        """Would `publisher` with its own id be allowed to publish on `subject`? Answers with a reason; never publishes."""
        v = _registry().check(subject, publisher, owner_id)
        return {"subject": subject, "publisher": publisher, "ok": v.ok, "reason": v.reason, "kind": v.kind,
                "pattern": v.pattern}
