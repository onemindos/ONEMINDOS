# SPDX-License-Identifier: Apache-2.0
"""The system-account observer (#620, NATS plan N3): who connects to the hub's message bus, and who is refused.

In plain words: the hub's NATS server can announce on its own system account every time a client or a
machine's leaf connects or disconnects, and every time a sign-in is refused. A read-only observer user
(natsconf.py, account SYS) listens to just those three kinds of announcement. This module turns each
one into an audit line, and raises an alert when it means something:

- `fabric.connect` / `fabric.disconnect`: one line per sign-in or drop (account, public key, what the
  client calls itself, why it dropped). A client address is never copied: only its public nkey.
- `fabric.auth_failed`: a refused sign-in. `cause` says why it matters:
  - `unknown_key`: a key this box never issued (or no key at all). Alert `fabric.unknown_key`;
  - `revoked_key`: a key that signed in here before and is not on the list any more (a removed machine
    or agent still retrying). Alert `fabric.revoked_retry`;
  - `known_key`: a key that is on the list, refused anyway. nats-server reports the key the client
    *claimed*, whether or not its signature checked out, so this is also what someone presenting another
    live identity's public key (public keys are readable on the box) looks like. Alert `fabric.key_refused`.
- A key that connects five times in two minutes is flapping: alert `fabric.flapping`, cleared by
  `fabric.flap_cleared` once it has been quiet for ten minutes.

The observer never acts. It cannot publish (the server refuses), it changes no key and no account, and
an alert only informs the owner. Audit lines are rate limited per key (a revoked machine retries every
second; a spoofer can invent keys), and the count of what was left out is carried on the next line.

Subjects, from nats-server v2.15.3 server/events.go: `$SYS.ACCOUNT.<acc>.CONNECT`, `.DISCONNECT` and
`$SYS.SERVER.<id>.CLIENT.AUTH.ERR`. The message body is the server's ConnectEventMsg or
DisconnectEventMsg: `client.user` is the public nkey, `client.kind` is Client or Leafnode.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import threading
from collections import deque
from collections.abc import Callable, Iterable
from datetime import datetime

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, mapped_column

from .bus import SeedClient
from .ledger import Base, utc
from .natsconf import OBSERVER_SUBJECTS, SYS_ACCOUNT, is_user_public_nkey
from .store import Database, FeatureSchema

log = logging.getLogger("onemind.fabricwatch")

SCHEMA = FeatureSchema("fabricwatch")

EVENTS = ("fabric.connect", "fabric.disconnect", "fabric.auth_failed")
FLAP_CONNECTS = 5          # this many connects ...
FLAP_WINDOW_S = 120.0      # ... within this many seconds is flapping
FLAP_QUIET_S = 600.0       # ... and it clears after this long with no connect
MIN_GAP_S = {"fabric.connect": 5.0, "fabric.disconnect": 5.0, "fabric.auth_failed": 60.0}
AUTH_LINES_PER_MIN = 30    # across all keys: a spoofer inventing keys cannot flood the audit log
ALERTS_PER_WINDOW = 5      # new unknown-key, revoked-key or key-refused alerts per ALERT_WINDOW_S
ALERT_WINDOW_S = 600.0
OPEN_FOR_S = 86400.0
RECENT = 200               # newest events kept in memory for GET /v1/fabric/events (its largest `count`)
RETRY_S = 5.0
TICK_S = 30.0
_NAME_RE = re.compile(r"[^A-Za-z0-9_.:@ -]")


class FabricSeenKeyRow(Base):
    """Every key that has signed in to this hub: what tells a removed key from one never issued."""
    __tablename__ = "fabricwatch_seen_keys"
    nkey: Mapped[str] = mapped_column(String(56), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SeenKeys:
    def __init__(self, db: Database):
        self.db = db

    def note(self, nkey: str, label: str | None, now: datetime) -> None:
        with self.db.session.begin() as s:
            row = s.get(FabricSeenKeyRow, nkey)
            if row is None:
                s.add(FabricSeenKeyRow(nkey=nkey, label=label, first_seen=now, last_seen=now))
            else:
                row.last_seen = now
                if label:
                    row.label = label

    def get(self, nkey: str) -> dict | None:
        with self.db.session() as s:
            row = s.get(FabricSeenKeyRow, nkey)
            return None if row is None else {"label": row.label, "last_seen": utc(row.last_seen)}

    def all(self) -> list[str]:
        with self.db.session() as s:
            return list(s.scalars(select(FabricSeenKeyRow.nkey)))


def parse(subject: str, data: bytes) -> dict | None:
    """One server announcement as {event, account, key, client, name, reason}, or None when it is not one
    of the three kinds or is malformed. A user name or token in `client.user` is never kept: only a
    well-formed public nkey is."""
    if len(data) > 16384:
        return None
    toks = subject.split(".")
    if len(toks) == 4 and toks[:2] == ["$SYS", "ACCOUNT"] and toks[3] in ("CONNECT", "DISCONNECT"):
        event, account = "fabric." + toks[3].lower(), toks[2]
    elif len(toks) == 6 and toks[:2] == ["$SYS", "SERVER"] and toks[3:] == ["CLIENT", "AUTH", "ERR"]:
        event, account = "fabric.auth_failed", None
    else:
        return None
    try:
        body = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict) or not isinstance(body.get("client"), dict):
        return None
    c = body["client"]
    user = c.get("user")
    key = user if isinstance(user, str) and is_user_public_nkey(user) else ""
    if account is None or account == "$G":   # $G: the global account a refused client never reached
        acc = c.get("acc")
        account = acc if isinstance(acc, str) and acc != "$G" and re.fullmatch(r"[A-Za-z0-9_$.-]{1,64}", acc) else None
    name = c.get("name") if isinstance(c.get("name"), str) else ""
    reason = body.get("reason") if isinstance(body.get("reason"), str) else ""
    return {
        "event": event, "account": account, "key": key,
        "client": "leaf" if str(c.get("kind", "")).lower().startswith("leaf") else "client",
        "name": _NAME_RE.sub("", name)[:64], "reason": _NAME_RE.sub("", reason)[:120],
    }


class FabricWatch:
    """`identities()` returns {public nkey: label} for every key currently allowed (a node, an agent, a
    service); `publish_event(domain, name, payload, severity=, dedupe_key=)` raises an alert."""

    def __init__(self, *, url: str | None, seed, audit, publish_event: Callable[..., object],
                 identities: Callable[[], dict[str, str]], seen: SeenKeys, clock: Callable[[], datetime]):
        self.url, self.seed = url, seed
        self.audit, self.publish_event, self.identities, self.seen, self.clock = audit, publish_event, identities, seen, clock
        self.state = "off" if not (url and seed) else "connecting"   # off | connecting | watching
        # handle() and tick() run on worker threads (asyncio.to_thread), so every shared dict and deque below
        # is touched under this one lock.
        self._lock = threading.Lock()
        self._recent: deque[dict] = deque(maxlen=RECENT)   # newest audit records this watch wrote
        self._backfilled = False
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last: dict[tuple[str, str], float] = {}
        self._left_out: dict[tuple[str, str], int] = {}
        self._auth_times: deque[float] = deque()
        self._alert_times: deque[float] = deque()
        self._open: dict[str, float] = {}   # alert key -> when raised; raised again after a day if it comes back
        self._connects: dict[str, deque[float]] = {}
        self._flapping: dict[str, float] = {}

    # ---- the pure part: one announcement in, audit lines and alerts out ---------------------------
    def handle(self, subject: str, data: bytes) -> dict | None:
        ev = parse(subject, data)
        if ev is None:
            return None
        with self._lock:
            return self._handle(ev)

    def _handle(self, ev: dict) -> dict | None:
        if ev["account"] == SYS_ACCOUNT:   # the observer's own sign-in is not news
            return None
        if ev["event"] == "fabric.disconnect" and ev["reason"].startswith("Authentication"):
            return None   # a refusal also sends a DISCONNECT (account $G); auth_failed already says it
        now = self.clock().timestamp()
        ids = self.identities()
        key = ev["key"]
        label = ids.get(key) if key else None
        if ev["event"] == "fabric.auth_failed":
            ev["cause"] = self._cause(key, ids)
        if ev["event"] == "fabric.connect" and key:
            try:
                self.seen.note(key, label, self.clock())
            except Exception:
                log.exception("could not note a signed-in key")
            self._flap(key, label, now)
        line = self._audit_line(ev, label, now)
        if ev["event"] == "fabric.auth_failed":
            self._alert(ev, label, now)
        return line

    def _cause(self, key: str, ids: dict[str, str]) -> str:
        if not key:
            return "unknown_key"
        if key in ids:
            return "known_key"
        return "revoked_key" if self.seen.get(key) is not None else "unknown_key"

    def _audit_line(self, ev: dict, label: str | None, now: float) -> dict | None:
        event, key = ev["event"], ev["key"]
        if event == "fabric.auth_failed":
            while self._auth_times and now - self._auth_times[0] > 60.0:
                self._auth_times.popleft()
            if len(self._auth_times) >= AUTH_LINES_PER_MIN:
                self._left_out[(event, "*")] = self._left_out.get((event, "*"), 0) + 1
                return None
        slot = (event, key or "-")
        last = self._last.get(slot)
        if last is not None and now - last < MIN_GAP_S[event]:
            self._left_out[slot] = self._left_out.get(slot, 0) + 1
            return None
        self._last[slot] = now
        if len(self._last) > 4096:   # bounded: forget the oldest half
            for k in sorted(self._last, key=self._last.get)[:2048]:
                self._last.pop(k, None)
                self._left_out.pop(k, None)
        data = {k: v for k, v in (("account", ev["account"]), ("key", key or None), ("identity", label),
                                  ("client", ev["client"]), ("name", ev["name"] or None),
                                  ("reason", ev["reason"] or None), ("cause", ev.get("cause"))) if v}
        out = self._left_out.pop(slot, 0) + (self._left_out.pop((event, "*"), 0) if event == "fabric.auth_failed" else 0)
        if out:
            data["repeats"] = out
        if event == "fabric.auth_failed":
            self._auth_times.append(now)
        rec = self.audit.append(event, None, None, data)
        if isinstance(rec, dict) and isinstance(rec.get("seq"), int):
            self._recent.append(rec)
        return data

    def _alert(self, ev: dict, label: str | None, now: float) -> None:
        cause, key = ev["cause"], ev["key"]
        name, dedupe = {
            "unknown_key": ("unknown_key", f"fabric:unknown:{key or 'none'}"),
            "revoked_key": ("revoked_retry", f"fabric:revoked:{key}"),
            "known_key": ("key_refused", f"fabric:refused:{key}"),
        }[cause]
        if now - self._open.get(dedupe, -OPEN_FOR_S) < OPEN_FOR_S:
            return
        while self._alert_times and now - self._alert_times[0] > ALERT_WINDOW_S:
            self._alert_times.popleft()
        if len(self._alert_times) >= ALERTS_PER_WINDOW:
            return
        self._alert_times.append(now)
        self._open[dedupe] = now
        if len(self._open) > 1024:
            self._open.pop(next(iter(self._open)), None)
        seen = self.seen.get(key) if key else None
        who = (seen or {}).get("label") or label or ""
        self._raise(name, {"key": key or "none", "key_short": (key[:8] + "…") if key else "no key",
                           "who": who or "a device", "account": ev["account"] or "", "client": ev["client"]},
                    "warning", dedupe)

    def _flap(self, key: str, label: str | None, now: float) -> None:
        q = self._connects.setdefault(key, deque())
        q.append(now)
        while q and now - q[0] > FLAP_WINDOW_S:
            q.popleft()
        if len(self._connects) > 1024:
            self._connects.pop(next(iter(self._connects)), None)
        if len(q) >= FLAP_CONNECTS and key not in self._flapping:
            self._raise("flapping", {"key": key, "key_short": key[:8] + "…", "who": label or "a device",
                                     "connects": len(q), "window_s": int(FLAP_WINDOW_S)}, "warning", f"fabric:flap:{key}")
        if len(q) >= FLAP_CONNECTS:
            self._flapping[key] = now

    def tick(self) -> None:
        """Clear flapping alerts for keys that have been quiet long enough."""
        now = self.clock().timestamp()
        with self._lock:
            for key, last in list(self._flapping.items()):
                if now - last >= FLAP_QUIET_S:
                    del self._flapping[key]
                    self._connects.pop(key, None)
                    self._raise("flap_cleared", {"key": key, "key_short": key[:8] + "…"}, "info", f"fabric:flap:{key}")

    def recent(self, count: int, load: Callable[[], Iterable[dict]]) -> list[dict]:
        """The newest `count` fabric audit records, newest first. The audit log is read once (`load`, the
        first time anyone asks); after that the answer comes from memory, so a card that polls does not
        re-read every audit segment each time."""
        with self._lock:   # handle() appends under this lock, so nothing is missed between the read and the ring
            if not self._backfilled:
                known = {r["seq"] for r in self._recent}
                older = deque((r for r in load() if r["seq"] not in known), maxlen=RECENT)
                self._recent = deque(sorted([*older, *self._recent], key=lambda r: r["seq"])[-RECENT:], maxlen=RECENT)
                self._backfilled = True
            return list(reversed(self._recent))[:count]

    def _raise(self, name: str, payload: dict, severity: str, dedupe: str) -> None:
        try:
            self.publish_event("fabric", name, payload, severity=severity, dedupe_key=dedupe)
        except Exception:
            log.exception("could not raise fabric.%s", name)

    # ---- the live part: the observer's own NATS connection -----------------------------------------
    async def start(self) -> None:
        if self.state == "off":
            log.info("no NATS observer key; the bus is not watched")
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="fabric-watch")

    async def _on_msg(self, msg) -> None:
        try:
            await asyncio.to_thread(self.handle, msg.subject, msg.data)
        except Exception:  # one bad announcement never stops the watch
            log.exception("fabric announcement failed")

    async def _down(self) -> None:
        self.state = "connecting"

    async def _up(self) -> None:
        self.state = "watching"

    async def _run(self) -> None:
        ticker = asyncio.create_task(self._ticker())
        try:
            while not self._stop.is_set():
                nc = None
                try:
                    nc = SeedClient()
                    # nats-py reconnects by itself; the callbacks keep `state` honest while it does.
                    await nc.connect(self.url, nkeys_seed=str(self.seed), connect_timeout=2, allow_reconnect=True,
                                     max_reconnect_attempts=-1, reconnect_time_wait=2, name="onemind-observer",
                                     disconnected_cb=self._down, reconnected_cb=self._up, closed_cb=self._down)
                    for subject in OBSERVER_SUBJECTS:
                        await nc.subscribe(subject, cb=self._on_msg)
                    self.state = "watching"
                    await self._stop.wait()
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.state = "connecting"
                    log.warning("NATS observer not connected (%s); retrying in %.0fs", exc.__class__.__name__, RETRY_S)
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._stop.wait(), timeout=RETRY_S)
                finally:
                    # Always close this attempt's connection: a failed subscribe must not leave a client that
                    # keeps reconnecting while the loop makes another one.
                    if nc is not None:
                        with contextlib.suppress(Exception):
                            await (nc.drain() if self._stop.is_set() else nc.close())
        finally:
            ticker.cancel()

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(TICK_S)
            try:
                await asyncio.to_thread(self.tick)
            except Exception:
                log.exception("fabric watch tick failed")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
