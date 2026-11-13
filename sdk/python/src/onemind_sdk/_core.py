# SPDX-License-Identifier: Apache-2.0
"""What the sync and async clients share: URL rules, request shapes, response parsing, retry
policy and the SSE parser. Neither client adds behaviour of its own (SDK.md §3)."""

from __future__ import annotations

import json
import os
import random
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx

from .errors import NetworkError, UnexpectedResponse, error_for

VERSION = "0.1.0"
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "expired", "outcome_unknown"})
RETRY_STATUSES = frozenset({429, 502, 503, 504})
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_EXPIRY = timedelta(hours=24)


def normalize_hub_url(url: str) -> str:
    url = url.strip()
    if "://" not in url:
        url = "http://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"onemind: hub URL must be an absolute http(s) URL, got {url!r}")
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def from_env(env: dict[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    if env.get("ONEMIND_HUB"):
        return env["ONEMIND_HUB"], env.get("ONEMIND_TOKEN", "")
    if env.get("ONEMIND_GATEWAY_URL"):
        return env["ONEMIND_GATEWAY_URL"], env.get("ONEMIND_AGENT_TOKEN", "")
    raise ValueError("onemind: set ONEMIND_HUB (and ONEMIND_TOKEN) or ONEMIND_GATEWAY_URL")


def plain_http_warning(base: str) -> str | None:
    p = urlsplit(base)
    if p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1", "::1"):
        return f"talking to {p.netloc} over plain http: the token crosses the network unencrypted"
    return None


def backoff(attempt: int, retry_after: float | None) -> float:
    if retry_after:
        return retry_after
    return random.uniform(0, min(4.0, 0.25 * 2 ** (attempt - 1)))


@dataclass
class Req:
    method: str
    path: str
    body: Any = None
    retry: bool = False
    headers: dict[str, str] = field(default_factory=dict)


class ExpiryMemo:
    """expires_at, fixed once per idempotency key. The hub compares the whole request body when a key
    is replayed, so a retry that recomputed expires_at in a later second would get a 409."""

    MAX = 1024

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: OrderedDict[str, tuple[str, datetime]] = OrderedDict()

    def get(self, key: str, now: datetime, span: timedelta) -> str:
        with self._lock:
            hit = self._by_key.get(key)
            if hit and hit[1] > now:
                return hit[0]
            exp = now + span
            text = exp.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            self._by_key.pop(key, None)
            self._by_key[key] = (text, exp)
            for k in [k for k, (_, e) in self._by_key.items() if e <= now]:  # expired: the hub would refuse a replay anyway
                del self._by_key[k]
            while len(self._by_key) > self.MAX:
                self._by_key.popitem(last=False)
            return text


def action_request(type_: str, app_id: str, hub_now: datetime, expires_in: timedelta | None,
                   idempotency_key: str | None, memo: ExpiryMemo | None = None) -> Req:
    span = expires_in or DEFAULT_EXPIRY
    if idempotency_key and memo is not None:
        expires_at = memo.get(idempotency_key, hub_now, span)
    else:
        expires_at = (hub_now + span).astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "type": type_, "params": {"app_id": app_id}, "idempotency_key": idempotency_key or str(uuid.uuid4()),
        "expires_at": expires_at,
    }
    return Req("POST", "/v1/actions", body, retry=True)


def audit_query(**q: Any) -> str:
    keys = ("after_seq", "before_seq", "event", "principal_id", "action_id", "since", "until", "limit")
    params = {k: q[k] for k in keys if q.get(k) not in (None, "")}
    return "/v1/audit/events" + ("?" + urlencode(params) if params else "")


def pid(s: str) -> str:
    return quote(s, safe="")


def hub_offset(resp: httpx.Response) -> timedelta | None:
    try:
        return parsedate_to_datetime(resp.headers["date"]) - datetime.now(UTC)
    except (KeyError, TypeError, ValueError):
        return None


def parse(resp: httpx.Response) -> Any:
    """The JSON body of a 2xx, else the typed error."""
    try:
        body = resp.json() if resp.content else None
    except ValueError:
        body = None
    if resp.is_success:
        if body is None and resp.status_code != 204:
            raise UnexpectedResponse(resp.status_code, "unexpected_response",
                                     "the hub did not answer with JSON (a proxy in the way?)")
        return body
    ra = resp.headers.get("retry-after")
    retry_after = float(ra) if ra and ra.isdigit() else (body or {}).get("retry_after_s") if isinstance(body, dict) else None
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        raise error_for(resp.status_code, body["error"], str(body.get("message", "")),
                        reason=body.get("reason"), retry_after_s=retry_after)
    code = "not_found" if resp.status_code == 404 else "unexpected_response"
    raise error_for(resp.status_code, code, f"HTTP {resp.status_code} without the OneMind error body",
                    retry_after_s=retry_after)


def network_error(exc: Exception, token: str) -> NetworkError:
    msg = str(exc) or exc.__class__.__name__
    if token:
        msg = msg.replace(token, "[redacted]")
    return NetworkError(msg, timed_out=isinstance(exc, httpx.TimeoutException))


class SseParser:
    """Feeds text, yields (id, event dict). Tracks the server's retry: in ms."""

    def __init__(self) -> None:
        self.buf = ""
        self.retry_ms: int | None = None

    def feed(self, text: str):
        self.buf += text.replace("\r\n", "\n")
        while "\n\n" in self.buf:
            block, self.buf = self.buf.split("\n\n", 1)
            id_, typ, data = "", "", []
            for line in block.split("\n"):
                if line.startswith(":"):
                    continue
                k, _, v = line.partition(":")
                v = v[1:] if v.startswith(" ") else v
                if k == "id":
                    id_ = v
                elif k == "event":
                    typ = v
                elif k == "data":
                    data.append(v)
                elif k == "retry" and v.isdigit():
                    self.retry_ms = int(v)
            if not data:
                continue
            try:
                ev = json.loads("\n".join(data))
            except ValueError:
                ev = {"id": id_, "type": typ, "data": {"raw": "\n".join(data)}}
            if isinstance(ev, dict):
                ev.setdefault("type", typ)
                yield id_, ev
