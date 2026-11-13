# SPDX-License-Identifier: Apache-2.0
"""Storage actions: mirror create, add, replace, remove and repair as owner-approved actions.

STORAGE-ACT-1 / UMB-STOR-5 (docs/umbrel2/storage.md §4.5, §4.8; docs/leap/core/STORAGE-ACTIONS.md).

How a disk change happens:
1. A requester (owner or agent) posts `{type, params}` to /v1/storage/actions. The gateway asks the
   node's storage service (`onemindd storage serve`, a Unix socket) to render the plan: the exact
   commands, the checks they passed, and `plan_sha256`, which binds the disks' identity. A blocked
   plan is refused; otherwise the action is filed in the ledger (awaiting_approval) and the plan is
   kept in `storage_operations` for the approval card.
2. The owner approves through POST /v1/actions/{id}/approve. The gateway renders the plan again; a
   different hash (a disk was swapped, the set changed) is 409 stale_precondition and the action
   stays pending. Agents can never approve (403, actions.py).
3. Dispatch sends `{kind, params, plan_sha256, action_id}`; the node renders the plan a third time
   and runs it only if the hash still matches. It never receives commands from the gateway.
4. The operation runs on the node from a journal (resume or roll back after a power cut). A poller
   closes the action when the journal says the operation finished, and turns set state and disk
   health into events (`storage.degraded`, `storage.disk.failing`, ...) for notifications.

v0 limits: only the hub's own node (other nodes need the signed jobs of contract §12.11); an
unreachable storage service is reported as 409 stale_precondition (§12.2's `unavailable` code is
not in the §3 set yet); passkey step-up for these destructive types comes from the identity
stream's approval guard (F-2), until then the owner token approves (F-12 interim, API.md §8.4).
"""

from __future__ import annotations

import hashlib
import http.client
import json
import logging
import socket
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import JSON, DateTime, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from .auth import Principal
from .context import Gateway
from .errors import ApiError
from .executors import ExecResult
from .ledger import Action, Base, utc
from .sections import config_section
from .store import FeatureSchema, SqlRepository

log = logging.getLogger("onemind.storage")

SCHEMA = FeatureSchema("storage")


@config_section("storage")
@dataclass(frozen=True)
class StorageSettings:
    enabled: bool = False  # ONEMIND_STORAGE_ENABLED=1: talk to this node's onemindd storage service
    socket: Path = Path("/run/onemind/storage.sock")  # ONEMIND_STORAGE_SOCKET
    poll_s: int = 60  # ONEMIND_STORAGE_POLL_S: finish operations, raise health events
    timeout_s: float = 15.0  # ONEMIND_STORAGE_TIMEOUT_S: one request to the storage service
    # ONEMIND_STORAGE_RECOVERY_KEY_API=1: let an owner take the LUKS recovery key through
    # POST /v1/storage/recovery-key. OFF: how keys are held and shown waits on founder decisions
    # F-61/F-62 (D4); until they are made the gateway never hands a key out.
    recovery_key_api: bool = False

    def validate(self) -> None:
        if self.poll_s < 5:
            raise ValueError("ONEMIND_STORAGE_POLL_S must be at least 5")
        if self.timeout_s <= 0:
            raise ValueError("ONEMIND_STORAGE_TIMEOUT_S must be positive")


# type → (engine kind, risk, who may request). Proposed for contract §12.5 by UMB-STOR-0.
Requesters = frozenset[str]
TYPES: dict[str, tuple[str, str, Requesters]] = {
    "storage.mirror.create": ("create", "destructive", frozenset({"person", "agent"})),
    "storage.mirror.add": ("add", "destructive", frozenset({"person", "agent"})),
    "storage.mirror.replace": ("replace", "destructive", frozenset({"person", "agent"})),
    "storage.mirror.remove": ("remove", "destructive", frozenset({"person"})),
    "storage.mirror.repair": ("repair", "write", frozenset({"person", "agent"})),
}
StorageType = Literal[
    "storage.mirror.create", "storage.mirror.add", "storage.mirror.replace",
    "storage.mirror.remove", "storage.mirror.repair",
]
# What each type needs in params.
NEEDS = {"create": {"device"}, "add": {"device"}, "replace": {"member", "device"}, "remove": {"member"}, "repair": set()}

# A bare reference (WWN, serial, devid:N, kernel name) cannot start with "-" (an option) or ".".
DEVICE = r"^(/dev/[A-Za-z0-9/_.:+-]{1,120}|[A-Za-z0-9_:+][A-Za-z0-9_.:+-]{0,119})$"


def _device_ref(v: str | None) -> str | None:
    """A disk reference is a /dev path or a WWN/serial/devid; never a path that climbs out of /dev.
    The node still accepts only disks its own lsblk reported (internal/storage Find); this refuses
    the rest before anything is stored, audited or sent."""
    if v is not None and v.startswith("/dev/") and any(seg in ("", ".", "..") for seg in v[5:].split("/")):
        raise ValueError("device path must be /dev/<name> with no '..', '.' or empty parts")
    return v


class StorageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str | None = Field(default=None, max_length=64)
    device: str | None = Field(default=None, pattern=DEVICE)  # the blank disk (path, WWN or serial)
    member: str | None = Field(default=None, pattern=DEVICE)  # devid, device, disk or "missing"
    unprotect: bool = False  # remove: accept going below two members
    wipe: bool = False  # replace/remove: erase the old disk afterwards

    @field_validator("device", "member")
    @classmethod
    def _safe_ref(cls, v: str | None) -> str | None:
        return _device_ref(v)


class StoragePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: StorageType
    params: StorageParams = StorageParams()


class StorageActionRequest(StoragePlanRequest):
    reason: str | None = Field(default=None, max_length=500)
    expires_at: AwareDatetime | None = None  # default now + 24 h, at most now + 7 d
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


# ---- the node's storage service ---------------------------------------------------------------
class StorageUnavailable(Exception):
    """The storage service could not be reached (nothing was sent)."""


class StorageTimeout(Exception):
    """The request was sent but no answer came: its effect is unknown."""


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float):
        super().__init__("storage", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._path)
        self.sock = s


class StorageClient:
    """JSON over the node's Unix socket (internal/storage/ops/server.go)."""

    def __init__(self, path: Path, timeout_s: float):
        self.path, self.timeout_s = str(path), timeout_s

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
        conn = _UnixConnection(self.path, self.timeout_s)
        try:
            try:
                conn.connect()
            except OSError as exc:
                raise StorageUnavailable(f"{exc.__class__.__name__}: {exc.strerror or exc}") from None
            data = json.dumps(body).encode() if body is not None else None
            try:
                conn.request(method, path, body=data, headers={"Content-Type": "application/json"})
                resp = conn.getresponse()
                raw = resp.read()
            except (TimeoutError, OSError, http.client.HTTPException) as exc:
                raise StorageTimeout(f"{exc.__class__.__name__}") from None
            try:
                return resp.status, json.loads(raw or b"null")
            except ValueError:
                return resp.status, {"error": "bad_response", "message": raw[:200].decode("utf-8", "replace")}
        finally:
            conn.close()


# ---- the feature's table ------------------------------------------------------------------------
class StorageOperationRow(Base):
    __tablename__ = "storage_operations"
    action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON)
    plan: Mapped[dict] = mapped_column(JSON)
    plan_sha256: Mapped[str] = mapped_column(String(64))
    risk: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(32))  # requested, running, succeeded, failed, rolled_back, needs_attention
    progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StorageObservationRow(Base):
    """What the poller last told as events: the set's state ("set") and each disk's verdict
    ("disk:<disk_key>"). Kept across gateway restarts, so a state that changed while the gateway was
    down still resolves its open alert (storage.ok, storage.disk.ok) and nothing is told twice."""

    __tablename__ = "storage_observations"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _row_json(r: StorageOperationRow) -> dict:
    return {
        "action_id": r.action_id, "node_id": r.node_id, "type": r.type, "params": r.params, "risk": r.risk,
        "plan": r.plan, "plan_sha256": r.plan_sha256, "state": r.state, "progress": r.progress, "error": r.error,
        "created_at": utc(r.created_at).isoformat().replace("+00:00", "Z"),
        "updated_at": utc(r.updated_at).isoformat().replace("+00:00", "Z"),
    }


class StorageRepository(SqlRepository):
    def add(self, row: StorageOperationRow) -> None:
        with self.db.session.begin() as s:
            if s.get(StorageOperationRow, row.action_id) is None:
                s.add(row)

    def get(self, action_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.get(StorageOperationRow, action_id)
            return _row_json(r) if r else None

    def update(self, action_id: str, now: datetime, **fields) -> None:
        with self.db.session.begin() as s:
            r = s.get(StorageOperationRow, action_id)
            if r is None:
                return
            for k, v in fields.items():
                setattr(r, k, v)
            r.updated_at = now

    def list(self, limit: int = 50) -> list[dict]:
        with self.db.session() as s:
            rows = s.scalars(select(StorageOperationRow).order_by(StorageOperationRow.created_at.desc()).limit(limit))
            return [_row_json(r) for r in rows]

    def observations(self) -> dict[str, str]:
        with self.db.session() as s:
            return {r.key: r.value for r in s.scalars(select(StorageObservationRow))}

    def observe(self, key: str, value: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            r = s.get(StorageObservationRow, key)
            if r is None:
                s.add(StorageObservationRow(key=key, value=value, updated_at=now))
            else:
                r.value, r.updated_at = value, now


# ---- the service -----------------------------------------------------------------------------------
def _disk_key(node_id: str, disk_id: str) -> str:
    """A stable, non-identifying key for a disk: alert dedupe keys and events never carry serials."""
    return hashlib.sha256(f"{node_id}\x00{disk_id}".encode()).hexdigest()[:16]


def _redacted(body: dict, principal: Principal) -> dict:
    """A plan names each target disk by its full WWN or serial (`targets[].id`) for the owner's
    approval card. Everyone else sees path, model and serial tail only (storage.md §4.10)."""
    plan = body.get("plan")
    if principal.is_owner or not isinstance(plan, dict) or not plan.get("targets"):
        return body
    targets = [{k: v for k, v in t.items() if k != "id"} for t in plan["targets"] if isinstance(t, dict)]
    return {**body, "plan": {**plan, "targets": targets}}


BAD_STATES = {"degraded", "unavailable", "unsupported"}
DISK_RANK = {"ok": 0, "unknown": 0, "warning": 1, "critical": 2}
FINAL = {"succeeded", "failed", "rolled_back", "needs_attention"}


class StorageService:
    """The action-type handler for storage.mirror.*, plus the status poller."""

    def __init__(self, gw: Gateway, client: StorageClient | None = None):
        self.gw = gw
        self.cfg: StorageSettings = gw.settings.section(StorageSettings)
        self.client = client or StorageClient(self.cfg.socket, self.cfg.timeout_s)
        self.repo = StorageRepository(gw.db)
        self.node_id = gw.settings.node_id or "hub"
        self._inflight: set[str] = set()
        self._finishers: dict[str, Callable[[ExecResult], None]] = {}
        self._lock = threading.Lock()
        self._seen: dict[str, str] | None = None  # storage_observations, loaded at the first poll
        # An action the node does not know yet is "never started" only after this long: dispatch may
        # still be on its way (the poller can see it accepted before the request is sent), or the node
        # still rendering its plan (a sleeping disk spins up for SMART).
        self._start_grace = timedelta(seconds=max(60.0, 4 * self.cfg.timeout_s))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- talking to the node -----------------------------------------------------------------
    def _need_enabled(self) -> None:
        if not self.cfg.enabled:
            raise ApiError(409, "stale_precondition", "storage actions are off on this box (ONEMIND_STORAGE_ENABLED)")

    def _call(self, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
        self._need_enabled()
        try:
            return self.client.call(method, path, body)
        except (StorageUnavailable, StorageTimeout) as exc:
            raise ApiError(409, "stale_precondition", f"the storage service on this node is not reachable ({exc})") from None

    def _node(self, params: StorageParams) -> str:
        node = params.node_id or self.node_id
        if node != self.node_id:
            raise ApiError(409, "stale_precondition", "storage actions run on the hub's own disks in v0; other nodes need signed jobs (§12.11)")
        return node

    @staticmethod
    def _engine_request(kind: str, params: dict) -> dict:
        return {"kind": kind, **{k: params[k] for k in ("device", "member", "unprotect", "wipe") if params.get(k)}}

    def render(self, action_type: str, params: StorageParams) -> dict:
        kind, _, _ = TYPES[action_type]
        missing = sorted(k for k in NEEDS[kind] if not getattr(params, k))
        if missing:
            raise ApiError(422, "conflict", f"{action_type} needs params {', '.join(missing)}")
        self._node(params)
        status, body = self._call("POST", "/v1/plans", self._engine_request(kind, params.model_dump()))
        if status != 200 or not isinstance(body, dict):
            raise ApiError(409, "stale_precondition", f"the storage service refused the plan: {(body or {}).get('message', status)}")
        return body

    # ---- API operations ------------------------------------------------------------------------------
    def summary(self) -> dict:
        out: dict[str, Any] = {"node_id": self.node_id, "enabled": self.cfg.enabled, "available": False}
        if not self.cfg.enabled:
            return out
        try:
            status, st = self.client.call("GET", "/v1/status")
        except (StorageUnavailable, StorageTimeout) as exc:
            return {**out, "error": str(exc)}
        if status != 200:
            return {**out, "error": (st or {}).get("message", str(status))}
        m = st.get("mirror") or {}
        active = st.get("active_operation")
        return {
            **out, "available": True, "state": m.get("state"), "mount": st.get("mount"),
            "encrypted": m.get("encrypted", False), "generation": m.get("generation", 0),
            "needs_scrub": m.get("needs_scrub", False), "reasons": m.get("reasons") or [], "repair": m.get("repair") or [],
            "profiles": m.get("profiles") or [], "used_bytes": m.get("used_bytes"),
            "members": [{k: x.get(k) for k in ("devid", "missing", "size_bytes", "allocated_bytes", "errors")} for x in m.get("members") or []],
            "operations_available": st.get("operations_available", False),
            "active_operation": _progress(active) if active else None,
            "recovery_key_pending": st.get("recovery_key_pending", False), "tpm2": st.get("tpm2", False), "at": st.get("at"),
        }

    def devices(self) -> list[dict]:
        status, st = self._call("GET", "/v1/status")
        if status != 200:
            raise ApiError(409, "stale_precondition", f"storage status failed: {(st or {}).get('message', status)}")
        health = st.get("health") or {}
        return [{**d, "health": health.get(d.get("path"))} for d in st.get("disks") or []]

    def plan(self, principal: Principal, req: StoragePlanRequest) -> dict:
        self._may_request(principal, req.type)
        plan = self.render(req.type, req.params)
        body = {"type": req.type, "risk": TYPES[req.type][1], "plan": plan, "plan_sha256": plan.get("plan_sha256")}
        return _redacted(body, principal)

    def _may_request(self, principal: Principal, action_type: str) -> None:
        if principal.kind not in TYPES[action_type][2] or not principal.can_request_actions:
            self.gw.audit.append("authz.denied", principal.as_dict(), None, {"attempted": f"request {action_type}", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not request {action_type}")

    def request(self, principal: Principal, req: StorageActionRequest, idem_header: str | None) -> tuple[dict, bool]:
        self._may_request(principal, req.type)
        now = self.gw.clock()
        expires = utc(req.expires_at) if req.expires_at else now + timedelta(hours=24)
        if expires > now + timedelta(days=7):
            raise ApiError(422, "conflict", "expires_at may be at most 7 days ahead")
        key = req.idempotency_key or idem_header or f"storage:{uuid.uuid4()}"
        params = {**req.params.model_dump(exclude_none=True), "node_id": self._node(req.params)}
        existing = self.gw.repo.get_by_idempotency_key(key)
        if existing is not None:  # a replay files nothing new and renders nothing
            action, created = self.gw.actions.request_feature(
                principal, req.type, params, idempotency_key=key, expires_at=expires, reason=req.reason)
            return _redacted({"action": action, **(self.repo.get(action["id"]) or {})}, principal), created
        plan = self.render(req.type, req.params)
        if plan.get("blocked"):
            failed = [f"{c['id']}: {c['detail']}" for c in plan.get("checks", []) if not c.get("ok")]
            raise ApiError(409, "stale_precondition", "the plan is blocked: " + "; ".join(failed)[:900])
        action, created = self.gw.actions.request_feature(
            principal, req.type, params, idempotency_key=key, expires_at=expires, reason=req.reason)
        if created:
            self.repo.add(StorageOperationRow(
                action_id=action["id"], node_id=params["node_id"], type=req.type, params=params, plan=plan,
                plan_sha256=plan["plan_sha256"], risk=TYPES[req.type][1], state="requested", created_at=now, updated_at=now,
            ))
        return _redacted({"action": action, **(self.repo.get(action["id"]) or {})}, principal), created

    def operation(self, action_id: str, principal: Principal) -> dict:
        row = self.repo.get(action_id)
        if row is None:
            raise ApiError(404, "not_found", "no such storage operation")
        if self.cfg.enabled and row["state"] in ("running",):
            try:
                status, op = self.client.call("GET", f"/v1/operations/{action_id}")
                if status == 200:
                    row = {**row, "journal": _journal(op)}
            except (StorageUnavailable, StorageTimeout):
                pass
        return _redacted(row, principal)

    def take_recovery_key(self, principal: Principal) -> dict:
        status, body = self._call("POST", "/v1/recovery-key/take")
        if status == 404:
            raise ApiError(404, "not_found", "no recovery key is waiting: it is shown once")
        if status != 200 or not (body or {}).get("recovery_key"):
            raise ApiError(409, "stale_precondition", f"the storage service could not hand over the key ({status})")
        self.gw.events.publish_event("storage", "recovery_key.shown", {"node_id": self.node_id}, principal=principal.as_dict())
        return {"one_time": {"recovery_key": body["recovery_key"]}}

    # ---- FeatureAction callbacks (check, run) ----------------------------------------------------------
    def recheck(self, a: Action) -> str | None:
        row = self.repo.get(a.id)
        if row is None:
            return "this storage action has no stored plan"
        try:
            plan = self.render(a.type, StorageParams(**a.params))
        except ApiError as exc:
            return exc.message
        if plan.get("blocked"):
            failed = [c["id"] for c in plan.get("checks", []) if not c.get("ok")]
            return "the plan is blocked now: " + ", ".join(failed)
        if plan.get("plan_sha256") != row["plan_sha256"]:
            return "the plan changed since the request (a disk or the set changed): deny it and request again"
        return None

    def run(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        """After approval: start the operation on the node. The action closes now when the node
        refused it, else the poller closes it (through `finish`) when the node's journal ends."""
        result = self._dispatch(a)
        if result is not None:
            finish(result)
            return
        with self._lock:
            self._finishers[a.id] = finish

    def _dispatch(self, a: Action) -> ExecResult | None:
        row = self.repo.get(a.id) or {}
        kind = TYPES[a.type][0]
        body = {**self._engine_request(kind, a.params), "plan_sha256": row.get("plan_sha256"), "action_id": a.id}
        with self._lock:
            self._inflight.add(a.id)
        try:
            status, resp = self.client.call("POST", "/v1/operations", body)
        except StorageUnavailable as exc:
            return ExecResult("failed", f"the storage service is not reachable; nothing ran ({exc})")
        except StorageTimeout:
            return None  # sent; the poller learns the outcome from the node's journal
        finally:
            with self._lock:
                self._inflight.discard(a.id)
        if status == 202:
            self.repo.update(a.id, self.gw.clock(), state="running", progress=_progress(resp))
            return None
        msg = (resp or {}).get("message", f"storage service answered {status}")
        self.repo.update(a.id, self.gw.clock(), state="failed", error=msg)
        return ExecResult("failed", f"not started: {msg}")

    def _close(self, a: Action, outcome: str, msg: str) -> bool:
        """Close the ledger action through the callback `run` kept. After a gateway restart the
        ledger already says outcome_unknown (actions.reconcile_interrupted) and stays so."""
        with self._lock:
            finish = self._finishers.pop(a.id, None)
        if finish is None:
            return False
        finish(ExecResult(outcome, msg))
        return True

    # ---- poller ----------------------------------------------------------------------------------------
    def start(self) -> None:
        if not self.cfg.enabled:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="storage-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception:
                log.exception("storage poll failed")
            self._stop.wait(self.cfg.poll_s)

    def poll(self) -> None:
        """One pass: close finished operations, then turn set state and disk health into events."""
        self._sync_operations()
        try:
            status, st = self.client.call("GET", "/v1/status")
        except (StorageUnavailable, StorageTimeout):
            return
        if status == 200 and isinstance(st, dict):
            self._observe(st)

    def _sync_operations(self) -> None:
        # Actions the ledger still tracks, plus those a gateway restart left as outcome_unknown while
        # the node kept working: the storage row, not the ledger, says whether it is still going.
        for a in self.gw.repo.list(states={"accepted", "dispatched", "outcome_unknown"}):
            if a.type not in TYPES:
                continue
            row = self.repo.get(a.id)
            if row is None or row["state"] in FINAL:
                continue
            with self._lock:
                if a.id in self._inflight:
                    continue
            try:
                status, op = self.client.call("GET", f"/v1/operations/{a.id}")
            except (StorageUnavailable, StorageTimeout):
                continue
            now = self.gw.clock()
            if status == 404:
                if now - utc(a.updated_at) < self._start_grace:
                    continue  # just approved: dispatch may still be sending it
                # Never reached the node (the gateway stopped between approval and dispatch).
                self.repo.update(a.id, now, state="failed", error="never started")
                self._close(a, "failed", "the storage service never started it")
                continue
            if status != 200 or not isinstance(op, dict):
                continue
            state = op.get("state")
            self.repo.update(a.id, now, state=state, progress=_progress(op), error=op.get("error"))
            if state not in FINAL:
                continue
            outcome = "succeeded" if state == "succeeded" else "failed"
            msg = {"succeeded": "the operation finished and the set was verified",
                   "rolled_back": f"rolled back, the set is as before: {op.get('error')}",
                   "needs_attention": f"stopped; needs the owner: {op.get('error')}"}.get(state, op.get("error") or state)
            self._close(a, outcome, msg)
            sev = {"succeeded": "info", "rolled_back": "warning"}.get(state, "critical")
            self.gw.events.publish_event(
                "storage", "operation.finished", {"node_id": self.node_id, "action_id": a.id, "type": a.type, "state": state, "error": op.get("error")},
                action_id=a.id, severity=sev, resource={"kind": "storage_set", "id": self.node_id},
            )

    def _observe(self, st: dict) -> None:
        if self._seen is None:
            self._seen = self.repo.observations()
        seen, now = self._seen, self.gw.clock()
        m = st.get("mirror") or {}
        state = m.get("state")
        res = {"kind": "storage_set", "id": self.node_id}
        if state and state != seen.get("set"):
            prev = seen.get("set")
            seen["set"] = state
            self.repo.observe("set", state, now)
            sev = "critical" if state in BAD_STATES else "info"
            payload = {"node_id": self.node_id, "state": state, "previous": prev, "reasons": (m.get("reasons") or [])[:8], "repair": m.get("repair") or []}
            self.gw.events.publish_event("storage", "state", payload, severity=sev, resource=res)
            if state in BAD_STATES:
                self.gw.events.publish_event("storage", "degraded", payload, severity="critical", resource=res, dedupe_key=f"storage:{self.node_id}:set")
            elif prev in BAD_STATES:
                self.gw.events.publish_event("storage", "ok", payload, severity="info", resource=res, dedupe_key=f"storage:{self.node_id}:set")
        disks = {d.get("path"): d for d in st.get("disks") or []}
        for path, h in (st.get("health") or {}).items():
            d = disks.get(path) or {}
            key = _disk_key(self.node_id, d.get("id") or path)
            verdict = (h or {}).get("verdict", "unknown")
            prev = seen.get(f"disk:{key}", "ok")
            if verdict != prev:
                seen[f"disk:{key}"] = verdict
                self.repo.observe(f"disk:{key}", verdict, now)
            rank, prev_rank = DISK_RANK.get(verdict, 0), DISK_RANK.get(prev, 0)
            if rank == prev_rank:  # each change is told once; notifications dedupe on the key
                continue
            payload = {"node_id": self.node_id, "disk": path, "disk_key": key, "model": d.get("model"),
                       "serial_tail": d.get("serial_tail"), "role": d.get("role"), "verdict": verdict, "reasons": (h or {}).get("reasons") or []}
            dedupe = f"storage:{self.node_id}:disk:{key}"
            if verdict == "critical":
                self.gw.events.publish_event("storage", "disk.failing", payload, severity="critical", resource=res, dedupe_key=dedupe)
            elif verdict == "warning":
                self.gw.events.publish_event("storage", "disk.warning", payload, severity="warning", resource=res, dedupe_key=dedupe)
            else:
                self.gw.events.publish_event("storage", "disk.ok", payload, severity="info", resource=res, dedupe_key=dedupe)


def _progress(op: dict | None) -> dict | None:
    if not op:
        return None
    steps, runs = (op.get("plan") or {}).get("steps") or [], op.get("steps") or []
    done = sum(1 for r in runs if r.get("state") in ("done", "skipped"))
    nxt = op.get("next", 0)
    return {"id": op.get("id"), "kind": (op.get("request") or {}).get("kind"), "state": op.get("state"),
            "done": done, "total": len(steps), "step": steps[nxt].get("id") if nxt < len(steps) else None,
            "resumes": op.get("resumes", 0), "error": op.get("error")}


def _journal(op: dict) -> list[dict]:
    steps, runs = (op.get("plan") or {}).get("steps") or [], op.get("steps") or []
    return [{"id": s.get("id"), "phase": s.get("phase"), "state": r.get("state"), "attempts": r.get("attempts", 0), "note": r.get("note")}
            for s, r in zip(steps, runs, strict=False)]
