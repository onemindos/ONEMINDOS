"""Error envelope of contract section 3: {"error": <code>, "message": <text>}."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Contract error codes, plus "invalid_request" for malformed bodies (v0 addition, see README).
ERROR_CODES = {
    "permission_denied",
    "stale_precondition",
    "expired",
    "conflict",
    "outcome_unknown",
    "not_found",
    "unauthenticated",
    "invalid_request",
}


class ApiError(Exception):
    def __init__(self, status: int, error: str, message: str):
        assert error in ERROR_CODES, error
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message


def error_response(status: int, error: str, message: str, **extra) -> JSONResponse:
    body = {"error": error, "message": message, **extra}
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(status_code=status, content=body, headers=headers)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.error, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()
        ]
        return error_response(422, "invalid_request", "request body failed validation", details=details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response(404, "not_found", "no such resource")
        if exc.status_code == 405:
            return error_response(405, "invalid_request", "method not allowed")
        return error_response(exc.status_code, "invalid_request", str(exc.detail))
