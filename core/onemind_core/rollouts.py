# SPDX-License-Identifier: Apache-2.0
"""Fleet-staged OS updates: OneMind's own release service on NATS (CORE-UPDATE-9, #156; Z-20).

In plain words: the owner picks a version and a list of stages, for example 10 %, 50 %, 100 %.
The gateway offers that version to the first 10 % of the machines, waits until each of them reports
the new version committed (the heartbeat's `update` object, filled by `internal/update` after the
RAUC health gate decided), then offers it to the next stage. A machine that rolls back, errors or
stays silent too long is a failure; more failures than `max_failures` pause the whole rollout.

- **AI never actuates without owner approval.** Starting and resuming a rollout are action types
  (`os.rollout.start`, `os.rollout.resume`) on the shared ledger: an owner or an agent may request
  one, only an owner approves, and nothing is offered to any machine before that approval.
- **The offer is a signed job** (contract §12.11, `onemind.job/v2` addressed to that one machine, kind `update.apply`), published
  on `onemind.node.<node_id>.job.update.apply`, the subject the hub already sends to each node. It
  is signed with the gateway's job key (backups/jobs.py) and names the action the owner approved.
- **Progress is read from heartbeats** the registry already keeps, so this needs no new subject
  from the nodes. A pass (`tick`) runs every `TICK_S` and after each approval.
"""

from __future__ import annotations

import json
import logging
import math
import secrets
import threading
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from .actions import FeatureAction
from .auth import Principal
from .backups.jobs import POLICY_EPOCH, gateway_job_key_path, load_or_create_job_key, sign_job_v2
from .errors import ApiError
from .executors import ExecResult
from .ledger import Base, iso, utc
from .store import FeatureSchema, SqlRepository

log = logging.getLogger("onemind.rollouts")

SCHEMA = FeatureSchema("rollouts")  # version 1 = the shape below

VERSION_RE = r"^[0-9]{1,10}(\.[0-9]{1,20}){0,5}(-dev)?$"  # CHANNEL.md §5: dot-separated integers
JOB_KIND = "update.apply"


def _text(v: object, n: int = 128) -> str | None:
    """A heartbeat field is whatever a LAN device sent (H-06): only a short non-empty string counts."""
    return v[:n] if isinstance(v, str) and v else None


def _update(node: dict) -> dict | None:
    up = node.get("update")
    return up if isinstance(up, dict) else None
TICK_S = 15.0
ACTIVE = ("running", "paused")
DONE_STATES = ("committed", "idle")  # internal/update states once the new slot is the booted one
FAIL_STATES = ("rolled_back", "error")
REQUESTERS = frozenset({"person", "agent"})  # an agent may ask; approval stays owner-only


def job_subject(node_id: str) -> str:
    return f"onemind.node.{node_id}.job.{JOB_KIND}"


class RolloutStartParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=64, pattern=VERSION_RE)
    # Cumulative percentages of the eligible machines, strictly rising, ending at 100.
    stages: list[int] = Field(default=[10, 50, 100], min_length=1, max_length=10)
    # How many machines may fail before the rollout pauses. 0 = pause on the first failure.
    max_failures: int = Field(default=0, ge=0, le=100)
    # A machine that has not reported the new version this long after its offer counts as failed.
    node_timeout_s: int = Field(default=6 * 3600, ge=60, le=7 * 86400)

    @field_validator("stages")
    @classmethod
    def _rising_to_100(cls, v: list[int]) -> list[int]:
        if any(not 1 <= p <= 100 for p in v) or any(b <= a for a, b in zip(v, v[1:])) or v[-1] != 100:
            raise ValueError("stages must be percentages from 1 to 100, strictly rising, ending at 100")
        return v


class RolloutRefParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rollout_id: str = Field(min_length=1, max_length=40, pattern=r"^rol_[0-9a-f]{26}$")


class RolloutRow(Base):
    __tablename__ = "rollouts_rollouts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(12))  # running | paused | completed | cancelled
    stages: Mapped[list] = mapped_column(JSON)
    stage: Mapped[int] = mapped_column(Integer)  # index into stages of the wave being offered
    max_failures: Mapped[int] = mapped_column(Integer)
    failure_base: Mapped[int] = mapped_column(Integer)  # failures already accepted by a resume
    node_timeout_s: Mapped[int] = mapped_column(Integer)
    # node_id -> {wave, state: waiting|offered|succeeded|failed, sent, offered_at, finished_at,
    # reason, baseline: [update.state, update.last_result] when offered}
    nodes: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    action_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def to_json(self) -> dict:
        counts = {s: 0 for s in ("waiting", "offered", "succeeded", "failed")}
        for n in self.nodes.values():
            counts[n["state"]] += 1
        return {
            "id": self.id, "version": self.version, "state": self.state, "stages": list(self.stages),
            "stage": self.stage, "max_failures": self.max_failures, "node_timeout_s": self.node_timeout_s,
            "reason": self.reason, "action_id": self.action_id, "counts": counts,
            "nodes": [{"node_id": k, **{f: v[f] for f in ("wave", "state", "offered_at", "finished_at", "reason")}}
                      for k, v in sorted(self.nodes.items())],
            "created_at": iso(self.created_at), "updated_at": iso(self.updated_at),
        }


class RolloutRepository(SqlRepository):
    def all(self) -> list[dict]:
        with self.db.session() as s:
            return [r.to_json() for r in s.scalars(select(RolloutRow).order_by(RolloutRow.created_at.desc(), RolloutRow.id))]

    def get(self, rollout_id: str) -> dict | None:
        with self.db.session() as s:
            row = s.get(RolloutRow, rollout_id)
            return row.to_json() if row else None

    def active_id(self) -> str | None:
        with self.db.session() as s:
            return s.scalars(select(RolloutRow.id).where(RolloutRow.state.in_(ACTIVE))).first()

    def add(self, row: RolloutRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def edit(self, rollout_id: str, fn) -> dict | None:
        """Run fn(row) inside one transaction; JSON columns are reassigned so the change is stored."""
        with self.db.session.begin() as s:
            row = s.get(RolloutRow, rollout_id)
            if row is None:
                return None
            nodes = json.loads(json.dumps(row.nodes))  # a deep copy: SQLAlchemy sees the reassignment
            fn(row, nodes)
            row.nodes = nodes
            return row.to_json()


class RolloutService:
    def __init__(self, gw):
        self.gw = gw
        self.repo = RolloutRepository(gw.db)
        self._lock = threading.RLock()
        self._key = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- the fleet view ---------------------------------------------------------------------
    def fleet(self) -> dict:
        """Every machine's OS version and update state, and how many machines run each version."""
        machines, versions = [], {}
        for n in self.gw.registry.list():
            up = _update(n)
            version = _text((up or {}).get("current_version"), 64)
            machines.append({
                "node_id": n["node_id"], "hostname": n.get("hostname"), "board": n.get("board"),
                "status": n["status"], "last_seen": n["last_seen"], "version": version,
                "channel": _text((up or {}).get("channel"), 32), "update_state": _text((up or {}).get("state"), 32),
                "available_version": _text((up or {}).get("available_version"), 64), "updatable": up is not None,
            })
            key = version or "unknown"
            versions[key] = versions.get(key, 0) + 1
        return {"machines": machines, "versions": [{"version": k, "count": v} for k, v in sorted(versions.items())],
                "active_rollout_id": self.repo.active_id()}

    # ---- checks shared by the request and the approval -----------------------------------
    def _eligible(self) -> list[dict]:
        return [n for n in self.gw.registry.list() if isinstance(n.get("update"), dict)]

    def start_problem(self, params: dict) -> tuple[str, str] | None:
        if (active := self.repo.active_id()) is not None:
            return "rollout_active", f"Rollout {active} is still running or paused: finish or cancel it first."
        if not self._eligible():
            return "no_updatable_nodes", "No machine reports an update service yet, so there is nothing to roll out to."
        return None

    def resume_problem(self, params: dict) -> tuple[str, str] | None:
        row = self.repo.get(params["rollout_id"])
        if row is None:
            return "rollout_unknown", f"There is no rollout {params['rollout_id']}."
        if row["state"] != "paused":
            return "wrong_state", f"Rollout {row['id']} is {row['state']}, so it cannot be resumed."
        return None

    def _check_request(self, problem):
        def check(params: dict, principal: Principal) -> None:
            if (found := problem(params)) is not None:
                raise ApiError(409, "policy_refused", found[1], reason=found[0])
        return check

    def _recheck(self, problem):
        def check(a) -> str | None:
            found = problem(a.params)
            return found[1] if found else None
        return check

    # ---- what runs after the owner approved ------------------------------------------------
    def _run_start(self, a, finish) -> None:
        p = RolloutStartParams.model_validate(a.params)
        with self._lock:
            if (found := self.start_problem(a.params)) is not None:
                finish(ExecResult("failed", found[1]))
                return
            now = self.gw.clock()
            nodes = {}
            for n in sorted(self._eligible(), key=lambda n: n["node_id"]):
                done = _text(n["update"].get("current_version"), 64) == p.version
                nodes[n["node_id"]] = {"wave": None, "state": "succeeded" if done else "waiting", "sent": False,
                                       "offered_at": None, "finished_at": iso(now) if done else None,
                                       "reason": "already on this version" if done else None, "baseline": None}
            rid = "rol_" + secrets.token_hex(13)
            self.repo.add(RolloutRow(
                id=rid, version=p.version, state="running", stages=p.stages, stage=0, max_failures=p.max_failures,
                failure_base=0, node_timeout_s=p.node_timeout_s, nodes=nodes, reason=None, action_id=a.id,
                created_at=now, updated_at=now))
            self.gw.audit.append("os.rollout.started", None, a.id, {"rollout_id": rid, "version": p.version,
                                                                    "stages": p.stages, "nodes": len(nodes)})
            self._advance(rid)
        finish(ExecResult("succeeded", f"rollout {rid} of {p.version} started", steps=[{"rollout_id": rid}]))

    def _run_resume(self, a, finish) -> None:
        rid = a.params["rollout_id"]
        with self._lock:
            if (found := self.resume_problem(a.params)) is not None:
                finish(ExecResult("failed", found[1]))
                return

            def resume(row, nodes):
                row.state, row.reason, row.updated_at = "running", None, self.gw.clock()
                row.failure_base = sum(1 for n in nodes.values() if n["state"] == "failed")
            self.repo.edit(rid, resume)
            self.gw.audit.append("os.rollout.resumed", None, a.id, {"rollout_id": rid})
            self._advance(rid)
        finish(ExecResult("succeeded", f"rollout {rid} resumed", steps=[{"rollout_id": rid}]))

    def cancel(self, rollout_id: str, p: Principal) -> dict:
        with self._lock:
            row = self.repo.get(rollout_id)
            if row is None:
                raise ApiError(404, "not_found", f"There is no rollout {rollout_id}.")
            if row["state"] not in ACTIVE:
                raise ApiError(409, "conflict", f"Rollout {rollout_id} is already {row['state']}.", reason="wrong_state")

            def stop(r, nodes):
                r.state, r.reason, r.updated_at = "cancelled", "cancelled by the owner", self.gw.clock()
            out = self.repo.edit(rollout_id, stop)
        self.gw.audit.append("os.rollout.cancelled", p.as_dict(), row["action_id"], {"rollout_id": rollout_id})
        return out

    # ---- one pass over the active rollout ----------------------------------------------------
    def tick(self) -> dict | None:
        with self._lock:
            rid = self.repo.active_id()
            return self._advance(rid) if rid else None

    def _advance(self, rid: str) -> dict | None:
        now = self.gw.clock()
        beats = {n["node_id"]: n for n in self.gw.registry.list()}
        offers: list[tuple[str, str]] = []
        events: list[tuple[str, dict]] = []

        def step(row, nodes):
            if row.state != "running":
                return
            # 1. read what the offered machines report
            for node_id, n in nodes.items():
                if n["state"] != "offered":
                    continue
                up = _update(beats.get(node_id) or {}) or {}
                if _text(up.get("current_version"), 64) == row.version and _text(up.get("state"), 32) in DONE_STATES:
                    n.update(state="succeeded", finished_at=iso(now))
                elif _text(up.get("state"), 32) in FAIL_STATES and [_text(up.get("state"), 32), _text(up.get("last_result"), 200)] != n["baseline"]:
                    n.update(state="failed", finished_at=iso(now), reason=f"{_text(up.get('state'), 32)}: {_text(up.get('last_result'), 200) or ''}"[:200])
                elif now - utc(datetime.fromisoformat(n["offered_at"].replace("Z", "+00:00"))) > timedelta(seconds=row.node_timeout_s):
                    n.update(state="failed", finished_at=iso(now), reason="no new version reported in time")
                if n["state"] == "failed":
                    events.append(("os.rollout.node_failed", {"rollout_id": rid, "node_id": node_id, "reason": n["reason"]}))
            # 2. too many failures: pause until an owner approves a resume
            failed = sum(1 for n in nodes.values() if n["state"] == "failed")
            if failed - row.failure_base > row.max_failures:
                row.state, row.updated_at = "paused", now
                row.reason = f"{failed} machine(s) failed; more than the {row.max_failures} allowed"
                events.append(("os.rollout.paused", {"rollout_id": rid, "failed": failed}))
                return
            # 3. the current wave is done: open the next one, until every machine had its offer
            while not any(n["state"] == "offered" for n in nodes.values()):
                waiting = sorted(k for k, n in nodes.items() if n["state"] == "waiting")
                if not waiting:
                    row.state, row.reason, row.updated_at = "completed", None, now
                    events.append(("os.rollout.completed", {"rollout_id": rid, "failed": failed}))
                    return
                # The last stage is 100 %, so while a machine waits its target is never reached there.
                target = max(1, math.ceil(row.stages[row.stage] * len(nodes) / 100))
                need = target - sum(1 for n in nodes.values() if n["state"] != "waiting")
                if need <= 0:  # this stage's share has had its offer: move on to the next one
                    row.stage += 1
                    continue
                for node_id in waiting[:need]:
                    up = _update(beats.get(node_id) or {}) or {}
                    nodes[node_id].update(state="offered", wave=row.stage, offered_at=iso(now), sent=False,
                                          baseline=[_text(up.get("state"), 32), _text(up.get("last_result"), 200)])
                events.append(("os.rollout.wave", {"rollout_id": rid, "stage": row.stage,
                                                   "percent": row.stages[row.stage], "offered": waiting[:need]}))
            # 4. (re)send the offer to each offered machine the bus has not reached yet
            for node_id, n in nodes.items():
                if n["state"] == "offered" and not n["sent"]:
                    offers.append((node_id, row.action_id))
            row.updated_at = now

        out = self.repo.edit(rid, step)
        for name, data in events:
            self.gw.audit.append(name, None, out["action_id"] if out else None, data)
        if offers and out is not None:
            sent = [node_id for node_id, action_id in offers if self._offer(node_id, out["version"], rid, action_id)]
            if sent:
                def mark(row, nodes):
                    for node_id in sent:
                        nodes[node_id]["sent"] = True
                out = self.repo.edit(rid, mark)
        return out

    def _offer(self, node_id: str, version: str, rid: str, action_id: str) -> bool:
        """Publish the signed update.apply job. False when NATS is down (the next pass retries)."""
        if not self.gw.bus.connected:
            return False
        if self._key is None:
            # The gateway's one job key, the same file the backup service signs with and whose public half
            # the fabric join reply hands each machine to pin (job.pub), so a machine trusts one key.
            self._key = load_or_create_job_key(gateway_job_key_path(self.gw.settings))
        # v2: addressed to this one machine (aud), with the key id and policy epoch the machine checks.
        # The current policy epoch (D-029 N7): a machine refuses this offer once a newer stop or revoke
        # snapshot exists, so an offer made before "Stop" never runs after it.
        epoch = self.gw.policy.epoch() if getattr(self.gw, "policy", None) is not None else POLICY_EPOCH
        job = sign_job_v2(self._key, JOB_KIND, {"version": version, "rollout_id": rid, "node_id": node_id},
                          self.gw.clock(), node_id=node_id, action_id=action_id, ttl=timedelta(hours=1),
                          policy_epoch=epoch)
        # Kept by the hub's ONEMIND_JOBS work queue in this machine's own consumer until it is back
        # (D-029 N2), named by job id so a retried publish is stored once.
        self.gw.bus.publish_threadsafe(job_subject(node_id), json.dumps(job).encode(),
                                       headers={"Nats-Msg-Id": job["job_id"]})
        return True

    # ---- wiring ---------------------------------------------------------------------------
    def register(self) -> None:
        acts = self.gw.actions
        acts.register_type("os.rollout.start", FeatureAction(
            "actuate", self._run_start, REQUESTERS, check=self._recheck(self.start_problem),
            params_model=RolloutStartParams, check_request=self._check_request(self.start_problem)))
        acts.register_type("os.rollout.resume", FeatureAction(
            "actuate", self._run_resume, REQUESTERS, check=self._recheck(self.resume_problem),
            params_model=RolloutRefParams, check_request=self._check_request(self.resume_problem)))

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="rollouts", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(10)

    def _loop(self) -> None:
        while not self._stop.wait(TICK_S):
            try:
                self.tick()
            except Exception:
                log.exception("rollout pass failed")
