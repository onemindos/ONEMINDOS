# SPDX-License-Identifier: Apache-2.0
"""The whole-system log viewer (P-07): GET /v1/system/journal.

The owner reads the box's systemd journal (kernel, SSH, any unit, not only the registry units that
/v1/system/services/{unit}/logs covers), filtered by `unit`, `priority` and `boot`. It is read only, so
it needs no approval, but every read is audited. Every line passes through the journal redaction filter
(journalfilter.py: tokens, passwords, keys, e-mail, IP and MAC addresses). It is bounded: at most 2000
lines, 1 MiB of text per read, 30 reads a minute and 3 open follow streams per owner, and a follow
stream ends after 15 minutes. Only the owner may read it; an agent's token is refused.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..hostservices import UNIT_RE, HostServicesClient
from ..identity.scopes import register_route_scope
from ..journalfilter import JournalRedactor
from ..netconf import NetSettings
from ..storage import StorageTimeout, StorageUnavailable

ORDER = 343  # after services (341) and ups (342): the system read routes sit together
MAX_LINES = 2000
MAX_BOOTS_BACK = 50
MAX_BYTES = 1 << 20          # one non-follow read
MAX_FOLLOW_BYTES = 8 << 20   # one follow stream
FOLLOW_MAX_S = 15 * 60
STREAMS_PER_PRINCIPAL = 3
READS_PER_MINUTE = 30
PRIORITY_RE = r"^(?:[0-7]|emerg|alert|crit|err|warning|notice|info|debug)$"

register_route_scope("GET,HEAD", r"/v1/system/journal", ("system:admin",))  # owner only, like /v1/system/controls

now = time.monotonic  # the tests move it


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(NetSettings)
    client = HostServicesClient(str(cfg.host_socket), cfg.host_timeout_s)
    streams: dict[str, int] = defaultdict(int)
    reads: dict[str, deque] = defaultdict(deque)
    lock = threading.Lock()

    def deny(p: Principal) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read system journal", "reason": "permission_denied"})
        return ApiError(403, "permission_denied", "only an owner may read the system journal")

    def limited(retry: int) -> JSONResponse:
        return JSONResponse(status_code=429, headers={"Retry-After": str(retry)},
                            content={"error": "rate_limited", "message": "too many journal reads, try again shortly",
                                     "reason": "limit_reached", "retry_after_s": retry})

    def admit(p: Principal, follow: bool) -> JSONResponse | None:
        """Count this read; a 429 response when the owner is over the rate or the stream limit."""
        with lock:
            if follow:
                if streams[p.id] >= STREAMS_PER_PRINCIPAL:
                    return limited(60)
                streams[p.id] += 1
                return None
            t = now()
            window = reads[p.id]
            while window and t - window[0] >= 60:
                window.popleft()
            if len(window) >= READS_PER_MINUTE:
                return limited(max(1, int(60 - (t - window[0])) + 1))
            window.append(t)
        return None

    def release(p: Principal, follow: bool) -> None:
        if follow:
            with lock:
                streams[p.id] -= 1

    @app.get("/v1/system/journal", tags=["system"], operation_id="system.journal.read", response_class=PlainTextResponse,
             responses={200: {"content": {"text/plain": {}, "text/event-stream": {}}},
                        **error_responses(401, 403, 409, 422, 429)},
             openapi_extra={"security": [{"bearer": ["system:admin"]}]})
    def system_journal(
        unit: Annotated[str | None, Query(max_length=100, description="a systemd unit such as sshd.service; all units when omitted")] = None,
        priority: Annotated[str | None, Query(pattern=PRIORITY_RE, description="0-7 or emerg..debug: that level and more severe")] = None,
        boot: Annotated[int, Query(ge=-MAX_BOOTS_BACK, le=0, description="0 is this boot, -1 the previous one")] = 0,
        tail: Annotated[int, Query(ge=1, le=MAX_LINES)] = 200,
        follow: bool = False,
        p: Principal = Depends(gw.principal),
    ):
        """The last `tail` journal lines of the whole box, every line redacted (tokens, passwords, keys,
        e-mail, IP and MAC addresses). `follow=true` streams new lines of this boot as server-sent events
        for at most 15 minutes. Owner only; every read is audited."""
        if not p.is_owner:
            raise deny(p)
        if unit is not None and not UNIT_RE.fullmatch(unit):
            raise ApiError(422, "conflict", "unit: a systemd unit name such as sshd.service", reason="invalid_unit")
        if follow and boot != 0:
            raise ApiError(422, "conflict", "only this boot (boot=0) can be followed", reason="invalid_boot")
        refused = admit(p, follow)
        if refused is not None:
            return refused
        gw.audit.append("system.journal.read", p.as_dict(), None,
                        {"unit": unit, "priority": priority, "boot": boot, "tail": tail, "follow": follow})
        try:
            stream = client.journal(unit, priority, boot, tail, follow, FOLLOW_MAX_S)
        except (StorageUnavailable, StorageTimeout):
            release(p, follow)
            raise ApiError(409, "conflict", "the host service is not reachable, so the journal cannot be read",
                           reason="host_unavailable") from None
        if stream.status != 200:
            stream.close()
            release(p, follow)
            if stream.status == 400:
                raise ApiError(422, "conflict", "the host service refused that unit, priority or boot", reason="invalid_query")
            raise ApiError(409, "conflict", f"the host service answered {stream.status}", reason="host_unavailable")
        r = JournalRedactor()
        if not follow:
            out: list[str] = []
            size = 0
            try:
                for raw in stream.lines():
                    line = r.line(raw)
                    size += len(line) + 1
                    if size > MAX_BYTES:
                        out.append("[output cut: the read is limited to 1 MiB, narrow the filters or lower tail]")
                        break
                    out.append(line)
            finally:
                stream.close()
            return PlainTextResponse("\n".join(out) + ("\n" if out else ""), headers={"Cache-Control": "no-store"})

        def gen():
            size = 0
            try:
                for raw in stream.lines():
                    line = r.line(raw)
                    size += len(line) + 1
                    if size > MAX_FOLLOW_BYTES:
                        yield "event: end\ndata: stream cut at its size limit\n\n"
                        return
                    yield f"data: {line}\n\n"
                yield "event: end\ndata: stream closed\n\n"
            finally:
                stream.close()
                release(p, True)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
