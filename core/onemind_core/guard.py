# SPDX-License-Identifier: Apache-2.0
"""Request limits and security headers for every gateway response (H-18, H-20; contract §12.1).

One pure-ASGI middleware, added by routers/guard.py:
- **Body size:** a request body over `max_body_bytes` (256 KiB, §12.1) gets 413
  `payload_too_large`, whether it declares Content-Length or streams chunks (the server enforces
  a declared Content-Length, so a body cannot be longer than it says).
- **Rate:** a token bucket per principal (the bearer token's hash) or, without a token, per
  source address. Reads 20/s burst 60; action requests (`POST /v1/actions`, `/v1/plans`) 2/s
  burst 10. Over the limit: 429 `rate_limited` with Retry-After.
- **Wrong tokens:** more than `auth_failures_per_min` 401s from one source in a minute starts a
  15-minute back-off for that source (429, audited once as `auth.backoff`). /healthz stays open.
- **Headers:** Content-Security-Policy, nosniff, no-referrer, frame denial and friends on every
  response that does not set its own (the app proxy of CORE-NET sets the app's own headers).

The pending-action cap (§12.1, H-14) lives in actions.py; this module sets its value.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from .errors import error_response
from .sections import config_section

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)
SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
)
REQUEST_ROUTES = frozenset({("POST", "/v1/actions"), ("POST", "/v1/plans")})
OPEN_PATHS = frozenset({"/healthz"})
MAX_KEYS = 10_000


@config_section("limits")
@dataclass(frozen=True)
class LimitSettings:
    enabled: bool = True                 # ONEMIND_LIMITS_ENABLED=0 turns rate limits off (not headers or body size)
    max_body_bytes: int = 256 * 1024     # ONEMIND_LIMITS_MAX_BODY_BYTES
    read_rate: float = 20.0              # ONEMIND_LIMITS_READ_RATE (per second)
    read_burst: int = 60
    request_rate: float = 2.0            # action requests per second
    request_burst: int = 10
    max_pending: int = 10                # awaiting_approval actions per non-owner requester (0 = no cap)
    auth_failures_per_min: int = 10
    auth_backoff_s: int = 900

    def validate(self) -> None:
        if self.max_body_bytes < 1024:
            raise ValueError("ONEMIND_LIMITS_MAX_BODY_BYTES must be at least 1024")
        for name in ("read_rate", "request_rate"):
            if getattr(self, name) <= 0:
                raise ValueError(f"ONEMIND_LIMITS_{name.upper()} must be positive")
        for name in ("read_burst", "request_burst", "auth_failures_per_min", "auth_backoff_s"):
            if getattr(self, name) < 1:
                raise ValueError(f"ONEMIND_LIMITS_{name.upper()} must be at least 1")
        if self.max_pending < 0:
            raise ValueError("ONEMIND_LIMITS_MAX_PENDING must be 0 or more")


class TokenBuckets:
    """Token buckets keyed by string, bounded in size (oldest keys dropped first)."""

    def __init__(self, rate: float, burst: int, now: Callable[[], float]):
        self.rate, self.burst, self.now = rate, burst, now
        self._b: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._lock = threading.Lock()

    def take(self, key: str) -> float:
        """0 if allowed, else the seconds until a token is available."""
        with self._lock:
            t = self.now()
            tokens, last = self._b.pop(key, (float(self.burst), t))
            tokens = min(float(self.burst), tokens + (t - last) * self.rate)
            if tokens >= 1.0:
                self._b[key] = (tokens - 1.0, t)
                wait = 0.0
            else:
                self._b[key] = (tokens, t)
                wait = (1.0 - tokens) / self.rate
            while len(self._b) > MAX_KEYS:
                self._b.popitem(last=False)
            return wait


class AuthFailures:
    """401s per source per minute; over the limit the source backs off for a while."""

    def __init__(self, limit: int, backoff_s: int, now: Callable[[], float]):
        self.limit, self.backoff_s, self.now = limit, backoff_s, now
        self._fails: OrderedDict[str, list[float]] = OrderedDict()
        self._blocked: dict[str, float] = {}
        self._lock = threading.Lock()

    def blocked_for(self, source: str) -> float:
        with self._lock:
            until = self._blocked.get(source)
            if until is None:
                return 0.0
            left = until - self.now()
            if left <= 0:
                del self._blocked[source]
                return 0.0
            return left

    def failed(self, source: str) -> bool:
        """Record a 401. True when this one starts a back-off."""
        with self._lock:
            t = self.now()
            recent = [x for x in self._fails.pop(source, []) if t - x < 60.0] + [t]
            self._fails[source] = recent
            while len(self._fails) > MAX_KEYS:
                self._fails.popitem(last=False)
            if len(recent) > self.limit and source not in self._blocked:
                self._blocked[source] = t + self.backoff_s
                self._fails.pop(source, None)
                return True
            return False


class GuardMiddleware:
    def __init__(
        self, app, *, limits: LimitSettings, on_backoff: Callable[[str], None] | None = None,
        now: Callable[[], float] = time.monotonic,
    ):
        self.app = app
        self.limits = limits
        self.on_backoff = on_backoff
        self.reads = TokenBuckets(limits.read_rate, limits.read_burst, now)
        self.requests = TokenBuckets(limits.request_rate, limits.request_burst, now)
        self.auth = AuthFailures(limits.auth_failures_per_min, limits.auth_backoff_s, now)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        send = _with_headers(send)
        path, method = scope.get("path", ""), scope.get("method", "GET")
        source = (scope.get("client") or ("unknown", 0))[0]
        if self.limits.enabled and path not in OPEN_PATHS:
            left = self.auth.blocked_for(source)
            if left > 0:
                return await _reject(scope, receive, send, 429, "rate_limited",
                                     "too many failed sign-ins from this address", "auth_backoff", left)
            key = _principal_key(scope) or f"ip:{source}"
            buckets = self.requests if (method, path) in REQUEST_ROUTES else self.reads
            wait = buckets.take(key)
            if wait > 0:
                return await _reject(scope, receive, send, 429, "rate_limited", "too many requests", "rate", wait)

        limit = self.limits.max_body_bytes
        declared = _content_length(scope)
        if declared is not None and declared > limit:
            return await _reject(scope, receive, send, 413, "payload_too_large",
                                 f"request body is over {limit} bytes", None, None)
        if declared is None and _has_body(scope):
            # Chunked or unknown length: read it here, up to the limit, before any route sees it
            # (a route's own body parser would turn an error into a generic 400).
            body, more = bytearray(), True
            while more:
                msg = await receive()
                if msg["type"] != "http.request":
                    break
                body += msg.get("body", b"")
                more = msg.get("more_body", False)
                if len(body) > limit:
                    return await _reject(scope, receive, send, 413, "payload_too_large",
                                         f"request body is over {limit} bytes", None, None)
            receive = _replay(bytes(body), receive)

        status: dict[str, int] = {}

        async def tracking_send(msg):
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
            await send(msg)

        await self.app(scope, receive, tracking_send)
        if status.get("code") == 401 and self.limits.enabled and self.auth.failed(source):
            if self.on_backoff is not None:
                self.on_backoff(source)


def _with_headers(send):
    async def wrapped(msg):
        if msg["type"] == "http.response.start":
            headers = list(msg.get("headers") or [])
            present = {k.lower() for k, _ in headers}
            headers.extend((k, v) for k, v in SECURITY_HEADERS if k not in present)
            msg = {**msg, "headers": headers}
        await send(msg)

    return wrapped


async def _reject(scope, receive, send, status, error, message, reason, wait):
    retry = max(1, math.ceil(wait)) if wait is not None else None
    resp = error_response(status, error, message, reason=reason, retry_after_s=retry)
    await resp(scope, receive, send)


def _has_body(scope) -> bool:
    return any(k == b"transfer-encoding" for k, _ in scope.get("headers") or [])


def _replay(body: bytes, receive):
    sent = False

    async def replay():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


def _content_length(scope) -> int | None:
    for k, v in scope.get("headers") or []:
        if k == b"content-length":
            try:
                return int(v)
            except ValueError:
                return None
    return None


def _principal_key(scope) -> str | None:
    for k, v in scope.get("headers") or []:
        if k == b"authorization":
            scheme, _, token = v.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return "tok:" + hashlib.sha256(token.strip().encode()).hexdigest()[:32]
    return None
