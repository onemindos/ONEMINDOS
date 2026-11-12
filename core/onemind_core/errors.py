"""Error envelope of contract section 3: {"error": <code>, "message": <text>}."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

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
}


class ErrorBody(BaseModel):
    """The section 3 error envelope, published in /openapi.json."""

    error: Literal[
        "permission_denied", "stale_precondition", "expired", "conflict",
        "outcome_unknown", "not_found", "unauthenticated",
        "rate_limited", "payload_too_large", "policy_refused",
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
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(
            exc.status, exc.error, exc.message,
            reason=exc.reason, details=exc.details, retry_after_s=exc.retry_after_s,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # §3 has no "invalid request" code: a body that does not fit the schema is reported as a
        # conflict with it, keeping HTTP 422 and naming the offending fields in the message.
        problems = "; ".join(
            f"{'.'.join(str(x) for x in e.get('loc', []))}: {e.get('msg', '')}" for e in exc.errors()
        )
        return error_response(422, "conflict", f"request failed validation: {problems}"[:1000])

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response(404, "not_found", "no such resource")
        if exc.status_code == 405:
            return error_response(405, "not_found", "method not allowed on this resource")
        code = {401: "unauthenticated", 403: "permission_denied"}.get(exc.status_code, "conflict")
        return error_response(exc.status_code, code, str(exc.detail))
