# SPDX-License-Identifier: Apache-2.0
"""FILES errors: the §12.2 envelope {error, message, reason?, retry_after_s?}.

The gateway's ApiError knows only the §3 codes; FILES also needs §12.2's `payload_too_large`,
`rate_limited` and `unavailable`, and tus's 412/416/460 statuses, so it has its own exception
and handler (installed by routers/files.py for this feature's routes only).
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

CODES = {
    "permission_denied", "stale_precondition", "expired", "conflict", "not_found", "unauthenticated",
    "payload_too_large", "rate_limited", "unavailable",
}


class FilesError(Exception):
    def __init__(self, status: int, error: str, message: str, *, reason: str | None = None,
                 headers: dict[str, str] | None = None):
        assert error in CODES, error
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message
        self.reason = reason
        self.headers = headers or {}

    def body(self) -> dict:
        out = {"error": self.error, "message": self.message}
        if self.reason:
            out["reason"] = self.reason
        return out


def not_found(what: str = "no such file or folder") -> FilesError:
    return FilesError(404, "not_found", what)


def denied(message: str, reason: str | None = None) -> FilesError:
    return FilesError(403, "permission_denied", message, reason=reason)


def conflict(message: str, reason: str | None = None) -> FilesError:
    return FilesError(409, "conflict", message, reason=reason)


async def handle(_: Request, exc: FilesError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.body(), headers=exc.headers or None)
