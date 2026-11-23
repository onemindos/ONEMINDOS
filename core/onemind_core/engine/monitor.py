# SPDX-License-Identifier: Apache-2.0
"""Read the hub nats-server's loopback monitoring port, keep only allow-listed numbers (issue #619).

nats-server answers plain HTTP GETs on its `http:` port (nats-server v2.15 server/monitor.go):

- /varz      the server: version, uptime, connection counts, slow consumers, the JetStream limits;
- /connz     one entry per client connection (`auth=true` adds the account each one is bound to);
- /jsz       JetStream: storage used, the configured caps, each account's streams and their sources;
- /healthz   200 {"status": "ok"} or 503 with an error;
- /leafz     the leaf links (one per joined node). An older server or one without leaf nodes may
             answer 404; that is "no leaf data", not an error.

The port has no password, which is why it listens on loopback only and why `check_url` refuses any
other host: the gateway never asks a monitor on another machine. Each answer is cut down here, at
read time, to the numbers the Engine feed shows. Client addresses, user names and nkeys
(`authorized_user`), JWTs, server names, the store directory and every subject are dropped before
anything is cached, so no later code can leak them.

A read costs five loopback requests; `MonitorReader.read` caches the result for CACHE_S (2 s), so a
dashboard refreshing every few seconds and a CLI loop never make NATS do more work than that.
"""

from __future__ import annotations

import ipaddress
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

DEFAULT_URL = "http://127.0.0.1:8222"   # onemind-firstboot and deploy/install.sh: `http: 127.0.0.1:8222`
CACHE_S = 2.0
TIMEOUT_S = 1.5
CONN_LIMIT = 4096                        # /connz pages; a hub with more clients reports `truncated`
ENDPOINTS = ("varz", "connz", "jsz", "healthz", "leafz")
_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_$.-]{1,64}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_RTT_RE = re.compile(r"^[0-9.µunmsh]{1,24}$")      # a Go duration: 1.2ms, 512µs, 1m2.5s
_UPTIME_RE = re.compile(r"^[0-9ydhms]{1,24}$")     # nats-server's uptime: 3d4h5m6s


class MonitorError(ValueError):
    """The monitor URL is not a loopback http URL: refused."""


def check_url(url: str) -> str:
    """`url` without a trailing slash when it is http://<loopback>[:port] and nothing else."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if parts.scheme != "http" or not loopback or parts.username or parts.password or parts.query \
            or parts.fragment or parts.path not in ("", "/"):
        raise MonitorError("the NATS monitor is read on loopback only, as http://127.0.0.1:<port>")
    return url.rstrip("/")


def _int(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _name(v, rx=_NAME_RE) -> str | None:
    return v if isinstance(v, str) and rx.match(v) else None


def reduce_varz(d: dict) -> dict:
    js = d.get("jetstream") if isinstance(d.get("jetstream"), dict) else {}
    cfg = js.get("config") if isinstance(js.get("config"), dict) else {}
    slow = d.get("slow_consumer_stats") if isinstance(d.get("slow_consumer_stats"), dict) else {}
    return {
        "version": _name(d.get("version")),
        "uptime": _name(d.get("uptime"), _UPTIME_RE),
        "connections": _int(d.get("connections")),
        "total_connections": _int(d.get("total_connections")),
        "leafnodes": _int(d.get("leafnodes")),
        "slow_consumers": _int(d.get("slow_consumers")),
        "slow_consumer_stats": {k: _int(slow.get(k)) for k in ("clients", "routes", "gateways", "leafs")},
        "in_msgs": _int(d.get("in_msgs")), "out_msgs": _int(d.get("out_msgs")),
        "jetstream_max_storage": _int(cfg.get("max_storage")), "jetstream_max_memory": _int(cfg.get("max_memory")),
    }


def reduce_connz(d: dict) -> dict:
    """Connections per account. Everything else about a client (address, user, nkey, JWT, name) is dropped."""
    per: dict[str, int] = {}
    conns = d.get("connections") if isinstance(d.get("connections"), list) else []
    for c in conns:
        if isinstance(c, dict):
            acc = _name(c.get("account"), _ACCOUNT_RE) or "$G"   # nats-server leaves the global account out
            per[acc] = per.get(acc, 0) + 1
    total = _int(d.get("total"))
    return {"accounts": per, "total": total if total is not None else len(conns),
            "truncated": total is not None and total > len(conns)}


def reduce_leafz(d: dict) -> list[dict]:
    """One row per leaf link: its server name, account and round trip. The remote address is dropped."""
    out = []
    for lf in d.get("leafs") if isinstance(d.get("leafs"), list) else []:
        if isinstance(lf, dict):
            out.append({"name": _name(lf.get("name")), "account": _name(lf.get("account"), _ACCOUNT_RE),
                        "rtt": _name(lf.get("rtt"), _RTT_RE), "in_msgs": _int(lf.get("in_msgs")),
                        "out_msgs": _int(lf.get("out_msgs"))})
    return out


def _source(src: dict) -> dict:
    err = src.get("error") if isinstance(src.get("error"), dict) else None
    return {"lag": _int(src.get("lag")), "active_ns": _int(src.get("active")),
            "error": (_name(str(err.get("err_code")), re.compile(r"^[0-9]{1,6}$")) if err else None)}


def reduce_jsz(d: dict) -> dict:
    """JetStream totals, each account's use, and every stream that sources another (the node outboxes)."""
    if d.get("disabled") is True:
        return {"enabled": False}
    cfg = d.get("config") if isinstance(d.get("config"), dict) else {}
    accounts, sourced = [], {}
    for a in d.get("account_details") if isinstance(d.get("account_details"), list) else []:
        if not isinstance(a, dict):
            continue
        name = _name(a.get("name"), _ACCOUNT_RE)
        streams = a.get("stream_detail") if isinstance(a.get("stream_detail"), list) else []
        accounts.append({"account": name, "storage": _int(a.get("storage")), "streams": len(streams)})
        for s in streams:
            if not isinstance(s, dict) or not _name(s.get("name")):
                continue
            srcs = [x for x in (s.get("sources") or []) if isinstance(x, dict)]
            if not srcs:
                continue
            st = s.get("state") if isinstance(s.get("state"), dict) else {}
            first = _source(srcs[0])
            sourced[s["name"]] = {"account": name, "messages": _int(st.get("messages")), "bytes": _int(st.get("bytes")),
                                  "lag": sum(x["lag"] or 0 for x in map(_source, srcs)), "active_ns": first["active_ns"],
                                  "error": first["error"]}
    return {
        "enabled": True,
        "storage": _int(d.get("storage")), "memory": _int(d.get("memory")),
        "reserved_storage": _int(d.get("reserved_storage")),
        "max_storage": _int(cfg.get("max_storage")), "max_memory": _int(cfg.get("max_memory")),
        "streams": _int(d.get("streams")), "consumers": _int(d.get("consumers")),
        "messages": _int(d.get("messages")), "bytes": _int(d.get("bytes")),
        "accounts": accounts, "sourced": sourced,
    }


def reduce_healthz(code: int, d: dict) -> dict:
    status = "ok" if code == 200 and d.get("status") == "ok" else "unavailable"
    err = d.get("error") if isinstance(d.get("error"), str) else None
    # The error names what is not current (a stream, a consumer); keep it short and on one line.
    return {"status": status, "error": None if status == "ok" else (err or f"HTTP {code}")[:160].replace("\n", " ")}


@dataclass(frozen=True)
class Snapshot:
    """One read of the monitor, already cut down. `None` for an endpoint that did not answer."""

    at: datetime
    varz: dict | None = None
    connz: dict | None = None
    jsz: dict | None = None
    healthz: dict | None = None
    leafz: list[dict] | None = None
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def reachable(self) -> bool:
        return self.varz is not None or self.healthz is not None


class MonitorReader:
    """Reads the loopback monitor at most once per `ttl` seconds; `read()` never raises."""

    def __init__(self, url: str = DEFAULT_URL, ttl: float = CACHE_S,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 monotonic: Callable[[], float] = time.monotonic, transport: httpx.BaseTransport | None = None,
                 timeout: float = TIMEOUT_S):
        self.url = check_url(url)
        self.ttl, self.clock, self.monotonic = ttl, clock, monotonic
        # The client is built on the first read, not here: httpx.Client loads the TLS trust store (certifi, ssl
        # context, httpcore) even for plain http, a few MiB the idle gateway never needs (perf budget, issue #849).
        self._client_args = dict(base_url=self.url, timeout=timeout, transport=transport, follow_redirects=False,
                                 trust_env=False)
        self._client_obj: httpx.Client | None = None
        self._client_lock = threading.Lock()
        self._lock = threading.Lock()
        self._cached: tuple[float, Snapshot] | None = None
        self.fetches = 0

    @property
    def _client(self) -> httpx.Client:
        with self._client_lock:
            if self._client_obj is None:
                self._client_obj = httpx.Client(**self._client_args)
            return self._client_obj

    def close(self) -> None:
        with self._client_lock:
            if self._client_obj is not None:
                self._client_obj.close()

    def read(self) -> Snapshot:
        with self._lock:
            now = self.monotonic()
            if self._cached is not None and now - self._cached[0] < self.ttl:
                return self._cached[1]
            snap = self._fetch()
            self._cached = (self.monotonic(), snap)
            return snap

    def _get(self, path: str, params: dict | None = None) -> tuple[int, dict]:
        r = self._client.get(path, params=params)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") or r.content[:1] == b"{" else {}
        return r.status_code, body if isinstance(body, dict) else {}

    def _fetch(self) -> Snapshot:
        self.fetches += 1
        out: dict = {}
        errors: dict[str, str] = {}
        calls = {
            "varz": ("/varz", None), "connz": ("/connz", {"auth": "true", "subs": "0", "limit": str(CONN_LIMIT)}),
            "jsz": ("/jsz", {"accounts": "true", "streams": "true"}), "healthz": ("/healthz", None),
            "leafz": ("/leafz", None),
        }
        for key, (path, params) in calls.items():
            try:
                code, body = self._get(path, params)
            except (httpx.HTTPError, ValueError) as exc:
                errors[key] = exc.__class__.__name__   # never the URL or the text: it may carry a path
                continue
            if key == "healthz":
                out[key] = reduce_healthz(code, body)
            elif key == "leafz" and code == 404:
                out[key] = None                         # this server has no leaf data: not an error
            elif code != 200:
                errors[key] = f"HTTP {code}"
            else:
                out[key] = {"varz": reduce_varz, "connz": reduce_connz, "jsz": reduce_jsz, "leafz": reduce_leafz}[key](body)
        return Snapshot(at=self.clock(), errors=errors, **out)
