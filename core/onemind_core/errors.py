"""Error envelope of contract section 3: {"error": <code>, "message": <text>}."""

from __future__ import annotations

import json

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

# The contract section 3 error codes plus the §12.2 codes this gateway sends so far
# (rate_limited, payload_too_large, policy_refused). Cases the contract has no code for are
# mapped onto these (see install_handlers and the README's "v0 deviations"); adding a code needs
# a contract PR.
ERROR_CODES = {
    "permission_denied",
    "stale_precondition",
    "expired",
    "conflict",
    "outcome_unknown",
    "not_found",
    "unauthenticated",
    "rate_limited",
    "payload_too_large",
    "policy_refused",
    "unavailable",
}


class ErrorBody(BaseModel):
    """The section 3 error envelope, published in /openapi.json."""

    error: Literal[
        "permission_denied", "stale_precondition", "expired", "conflict",
        "outcome_unknown", "not_found", "unauthenticated",
        "rate_limited", "payload_too_large", "policy_refused", "unavailable",
    ]
    message: str
    # §12.2 optional fields; present only when they carry something.
    reason: str | None = None
    details: list[dict] | None = None
    retry_after_s: int | None = None


_DESCRIPTIONS = {
    401: "Missing or unknown bearer token (unauthenticated)",
    403: "The principal may not do this (permission_denied)",
    404: "No such resource (not_found)",
    409: "stale_precondition, expired, conflict or policy_refused",
    413: "Request body over its limit (payload_too_large)",
    422: "Request failed validation (conflict, with the bad fields in message)",
    503: "unavailable: a feature is switched off or the service behind it cannot be used right now (see `reason` and Retry-After)",
    429: "Too many requests, attempts or open streams, or the pending-action cap (rate_limited); see Retry-After",
}


def error_responses(*statuses: int) -> dict[int, dict]:
    """OpenAPI `responses=` entries for the given error statuses, all using ErrorBody."""
    return {s: {"model": ErrorBody, "description": _DESCRIPTIONS[s]} for s in statuses}


class ApiError(Exception):
    def __init__(
        self, status: int, error: str, message: str, *,
        reason: str | None = None, details: list[dict] | None = None, retry_after_s: int | None = None,
    ):
        assert error in ERROR_CODES, error
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message
        self.reason = reason
        self.details = details
        self.retry_after_s = retry_after_s


def error_response(
    status: int, error: str, message: str, *,
    reason: str | None = None, details: list[dict] | None = None, retry_after_s: int | None = None,
) -> JSONResponse:
    body: dict = {"error": error, "message": message}
    headers: dict[str, str] = {}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if reason is not None:
        body["reason"] = reason
    if details is not None:
        body["details"] = details
    if retry_after_s is not None:
        body["retry_after_s"] = retry_after_s
        headers["Retry-After"] = str(retry_after_s)
    return JSONResponse(status_code=status, content=body, headers=headers or None)


def install_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def static_resource_methods(request: Request, call_next):
        # OpenAPI gives literal resources precedence over sibling templates. Do the same
        # for routing: DELETE /passkeys/register must not delete credential "register".
        literal = [r for r in request.app.router.routes
                   if getattr(r, "path", None) == request.scope["path"]]
        documented = [r for r in literal if getattr(r, "include_in_schema", False)]
        methods = set().union(*(getattr(r, "methods", set()) for r in documented))
        handled = set().union(*(getattr(r, "methods", set()) for r in literal))
        # Hidden transport handlers (MCP GET/DELETE) still authenticate before their
        # own 405. Do not intercept a method with an explicit handler on this resource.
        if methods and request.method not in handled:
            response = error_response(405, "not_found", "method not allowed on this resource")
            response.headers["Allow"] = ", ".join(sorted(methods))
            return response
        return await call_next(request)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(
            exc.status, exc.error, exc.message,
            reason=exc.reason, details=exc.details, retry_after_s=exc.retry_after_s,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # A feature router may map specific parameter failures onto its own protocol status (for
        # example tus's 412 and 415) so the published schema can require what the protocol requires.
        for hook in getattr(request.app.state, "validation_overrides", ()):
            if (response := hook(request, exc.errors())) is not None:
                return response
        # §3 has no "invalid request" code: a body that does not fit the schema is reported as a
        # conflict with it, keeping HTTP 422 and naming the offending fields in the message.
        problems = "; ".join(
            f"{'.'.join(str(x) for x in e.get('loc', []))}: {e.get('msg', '')}" for e in exc.errors()
        )
        return error_response(422, "conflict", f"request failed validation: {problems}"[:1000])

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response(404, "not_found", "no such resource")
        if exc.status_code == 405:
            resp = error_response(405, "not_found", "method not allowed on this resource")
            # RFC 9110 §15.5.6: a 405 must list the methods the resource supports (finding F-API-2,
            # api-fuzz.yml). Starlette's own Allow names only the first route for the path.
            if allow := allowed_methods(request) or (exc.headers or {}).get("Allow"):
                resp.headers["Allow"] = allow
            return resp
        if exc.status_code == 400:
            # A body that cannot be parsed at all (not UTF-8, say) fails the schema like any other
            # bad body: 422 conflict (§3, §12.2), not an undocumented 400 (finding F-API-3).
            return error_response(422, "conflict", f"request failed validation: {exc.detail}"[:1000])
        code = {401: "unauthenticated", 403: "permission_denied"}.get(exc.status_code, "conflict")
        return error_response(exc.status_code, code, str(exc.detail))

    build = app.openapi

    def openapi() -> dict:
        # A request that fails validation gets ErrorBody (422 `conflict`, above), never FastAPI's
        # HTTPValidationError, so /openapi.json says so for routes that do not list 422 themselves.
        # Also keeps the HTTPValidationError `loc` union out of the generated SDK types.
        # Errors are always JSON, also on a route whose success is text (app logs): FastAPI files
        # their model under the route's media type, so move it back to application/json.
        doc = build()
        bad, body = "#/components/schemas/HTTPValidationError", "#/components/schemas/ErrorBody"
        for ops in doc.get("paths", {}).values():
            for op in ops.values():
                # The global body guard runs before every body-bearing operation.
                if "requestBody" in op:
                    op["responses"].setdefault("413", {
                        "description": _DESCRIPTIONS[413],
                        "content": {"application/json": {"schema": {"$ref": body}}},
                    })
                for code, r in op.get("responses", {}).items():
                    refs = {(c.get("schema") or {}).get("$ref") for c in (r.get("content") or {}).values()}
                    if code == "422" and bad in refs:
                        op["responses"][code] = {"description": _DESCRIPTIONS[422],
                                                 "content": {"application/json": {"schema": {"$ref": body}}}}
                    elif refs == {body} and set(r["content"]) != {"application/json"}:
                        r["content"] = {"application/json": {"schema": {"$ref": body}}}
        schemas = doc.get("components", {}).get("schemas", {})
        if bad not in json.dumps(doc.get("paths", {})):
            schemas.pop("HTTPValidationError", None)
            if "#/components/schemas/ValidationError" not in json.dumps(doc):
                schemas.pop("ValidationError", None)
        return doc

    app.openapi = openapi  # type: ignore[method-assign]


def allowed_methods(request: Request) -> str | None:
    """Every method the documented routes for this path accept, for a 405's Allow header.

    Routes outside the schema (the dashboard's SPA fallback matches every path) are left out, so
    an API path never advertises a GET it does not have.
    """
    methods: set[str] = set()
    for route in request.app.router.routes:
        if not getattr(route, "include_in_schema", False) or not getattr(route, "methods", None):
            continue
        match, _ = route.matches(request.scope)
        if match != Match.NONE:
            methods |= route.methods
    return ", ".join(sorted(methods)) or None
