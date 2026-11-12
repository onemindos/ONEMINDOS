# SPDX-License-Identifier: Apache-2.0
"""Contract §12.16: read and verify the audit log (GET /v1/audit/events[/{seq}], /v1/audit/verify).

Read-only: nothing here edits or deletes a record. Signed checkpoints (H-10) are not built yet,
so `last_checkpoint` is null and /v1/audit/checkpoints is absent (404).
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from ..apimodels import AuditRecord, AuditVerify
from ..auditread import MAX_LIMIT, AuditReader, can_read_all, can_read_own
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope

# §12.16: audit:read (owner, adult) for household accounts and identity tokens. A narrowed
# audit:read:own (the agent reader bundle) is refused here (fail closed) until this module
# checks the narrowing itself rather than the principal's role.
register_route_scope("GET,HEAD", r"/v1/audit/(events(/[^/]+)?|verify)", ("audit:read",))


def owned_action_ids(gw: Gateway):
    """Ids of the actions a principal requested (an agent's `:own` view)."""

    def ids(principal_id: str) -> set[str]:
        return {a.id for a in gw.repo.list() if (a.requested_by or {}).get("id") == principal_id}

    return ids


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    reader = AuditReader(gw.settings.audit_path, gw.clock, owned_action_ids(gw))

    def readable(p: Principal) -> Principal:
        if not can_read_own(p):
            raise gw.actions._deny(p, "read the audit log")
        return p

    @app.get(
        "/v1/audit/events", tags=["audit"], operation_id="audit.events.list",
        responses={200: {"model": list[AuditRecord], "description": "Records in seq order. A `Link: rel=next` "
                         "header is present when more records match."}, **error_responses(401, 403, 422)},
    )
    def list_events(
        request: Request,
        after_seq: int | None = Query(None, ge=0),
        before_seq: int | None = Query(None, ge=1),
        event: str | None = Query(None, max_length=500, description="comma = OR, `*` glob, e.g. action.*"),
        principal_id: str | None = Query(None, max_length=200),
        action_id: str | None = Query(None, max_length=200),
        since: str | None = Query(None, max_length=40, description="RFC 3339, inclusive"),
        until: str | None = Query(None, max_length=40, description="RFC 3339, exclusive"),
        limit: int = Query(100, ge=1, le=MAX_LIMIT),
        p: Principal = Depends(principal),
    ):
        readable(p)
        try:
            rows, more = reader.list(
                p, after_seq=after_seq, before_seq=before_seq, event=event, principal_id=principal_id,
                action_id=action_id, since=since, until=until, limit=limit,
            )
        except ValueError as e:
            raise ApiError(422, "conflict", str(e)) from None
        headers = {}
        if more and rows:
            q = {k: v for k, v in request.query_params.items() if k != "after_seq"}
            q["after_seq"] = str(rows[-1]["seq"])
            headers["Link"] = f'</v1/audit/events?{urlencode(q)}>; rel="next"'
        return JSONResponse(rows, headers=headers)

    @app.get(
        "/v1/audit/events/{seq}", tags=["audit"], operation_id="audit.events.get",
        responses={200: {"model": AuditRecord}, **error_responses(401, 403, 404, 422)},
    )
    def get_event(seq: int, p: Principal = Depends(principal)):
        readable(p)
        rec = reader.get(p, seq)
        if rec is None:
            raise ApiError(404, "not_found", "no such audit record")
        return rec

    @app.get(
        "/v1/audit/verify", tags=["audit"], operation_id="audit.verify",
        responses={200: {"model": AuditVerify}, **error_responses(401, 403, 422)},
    )
    def verify(from_seq: int | None = Query(None, ge=1), p: Principal = Depends(principal)):
        if not can_read_all(p):  # the whole chain is visible in the head hash and counts
            raise gw.actions._deny(p, "verify the audit log")
        return reader.verify(from_seq)
