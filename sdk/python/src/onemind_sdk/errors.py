# SPDX-License-Identifier: Apache-2.0
"""Typed errors (docs/leap/dev/SDK.md §3.8). `code` is exactly the gateway's `error` value."""

from __future__ import annotations

from typing import Any


class OneMindError(Exception):
    """Base error. An unknown code from a newer gateway is a OneMindError with that code."""

    def __init__(self, status: int, code: str, message: str, *, reason: str | None = None,
                 retry_after_s: float | None = None, action: Any = None):
        super().__init__(f"HTTP {status} {code}: {message}" if status else f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.reason = reason
        self.retry_after_s = retry_after_s
        self.action = action


class Unauthenticated(OneMindError): ...
class PermissionDenied(OneMindError): ...
class NotFound(OneMindError): ...
class StalePrecondition(OneMindError): ...
class Expired(OneMindError): ...
class Conflict(OneMindError): ...
class OutcomeUnknown(OneMindError): ...
class RateLimited(OneMindError): ...
class UnexpectedResponse(OneMindError): ...


class NetworkError(OneMindError):
    def __init__(self, message: str, timed_out: bool = False):
        super().__init__(0, "network", message)
        self.timed_out = timed_out


class AmbiguousResult(OneMindError):
    """An approve or deny was sent, the reply was lost, and read-back could not confirm it."""

    def __init__(self, message: str, action: Any = None):
        super().__init__(0, "ambiguous_result", message, action=action)


BY_CODE: dict[str, type[OneMindError]] = {
    "unauthenticated": Unauthenticated, "permission_denied": PermissionDenied, "not_found": NotFound,
    "stale_precondition": StalePrecondition, "expired": Expired, "conflict": Conflict,
    "outcome_unknown": OutcomeUnknown, "rate_limited": RateLimited, "unexpected_response": UnexpectedResponse,
}


def error_for(status: int, code: str, message: str, **extra: Any) -> OneMindError:
    return BY_CODE.get(code, OneMindError)(status, code, message, **extra)
