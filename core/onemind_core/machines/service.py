# SPDX-License-Identifier: Apache-2.0
"""Machine actions: request, owner approval, then the runtime (MACH-01, #281 scope 3 and 4).

`machine.create|start|stop|delete` are feature action types (actions.py). The same ledger, the same
owner-only approval and the same audit lines apply as for apps: an owner or an agent may *request*
one, only an owner approves, and nothing reaches the runtime before an approval. The checks run
twice, at the request and again at approval, so a box that lost KVM or filled up in between is a
409 and the action stays waiting. The quota is reserved at approval (`claim`).
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from datetime import timedelta

from ..actions import FeatureAction
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from ..executors import ExecResult
from .capability import refusals
from .runtime import KubectlRuntime, MachineRuntime, NoopRuntime
from .spec import (
    MachineCreateParams, MachineDeleteParams, MachineRefParams, quota_problem,
)
from .store import MachineRow, MachinesRepository

CONSOLE_TTL_S = 60
REQUESTERS = frozenset({"person", "agent"})  # an agent may ask; approval stays owner-only


class MachineService:
    def __init__(self, gw: Gateway, runtime: MachineRuntime | None = None):
        self.gw = gw
        self.repo = MachinesRepository(gw.db)
        s = gw.settings
        self.runtime: MachineRuntime = runtime or (
            NoopRuntime() if s.executor == "noop" else KubectlRuntime(s.kubectl, timeout_s=s.executor_timeout_s))
        self._lock = threading.Lock()
        self._tickets: dict[str, tuple[str, object, dict | None]] = {}  # sha256(ticket) -> (machine, expires_at, who minted it)

    # ---- which node, and does it fit ------------------------------------------------------
    def _host(self) -> dict | None:
        """The node machines would run on: the first hub the preflight accepts."""
        for n in self.gw.registry.list():
            if not refusals(n):
                return n
        return None

    def _refusal_text(self) -> str:
        why = sorted({r.message for n in self.gw.registry.list() for r in refusals(n)})
        return "This box cannot run virtual machines: " + (" ".join(why) or "no node has reported yet.")

    def problem(self, verb: str, params: dict, *, reserve_own: str | None = None) -> tuple[str, str] | None:
        """(reason, message) when the action cannot be done now; None when it can."""
        name = params["name"]
        row = self.repo.get(name)
        if verb == "create":
            node = self._host()
            if node is None:
                return "machines_unsupported", self._refusal_text()
            if row is not None and not (reserve_own and row["state"] == "creating" and self.repo.owner(name) == reserve_own):
                return "name_taken", f"A machine named {name} already exists."
            others = [m for m in self.repo.all() if m["name"] != name]
            msg = quota_problem(node, others, params["ram_mb"], params["cpus"])
            return ("quota_exceeded", msg) if msg else None
        if row is None:
            return "machine_unknown", f"There is no machine named {name}."
        if row["state"] == "creating":
            return "machine_busy", f"Machine {name} is still being created."
        if verb == "start" and row["state"] != "stopped":
            return "wrong_state", f"Machine {name} is {row['state']}, so it cannot be started."
        if verb == "stop" and row["state"] != "running":
            return "wrong_state", f"Machine {name} is {row['state']}, so it cannot be stopped."
        if verb == "delete" and params.get("confirm") != name:
            return "confirm_mismatch", "Deleting a machine erases its disk: confirm needs the machine's name, typed by the owner."
        return None

    def _check_request(self, verb: str):
        def check(params: dict, principal: Principal) -> None:
            if verb == "delete" and params.get("confirm") != params["name"]:
                raise ApiError(422, "conflict", "params.confirm: must equal the machine name, typed by the owner")
            if (found := self.problem(verb, params)) is not None:
                raise ApiError(409, "policy_refused", found[1], reason=found[0])
        return check

    def _recheck(self, verb: str):
        def check(a) -> str | None:
            found = self.problem(verb, a.params, reserve_own=a.id)
            return found[1] if found else None
        return check

    # ---- approval: reserve what the action changes ----------------------------------------
    def _claim_create(self, a) -> str | None:
        with self._lock:  # two approved creates never both fit into the same last gigabyte
            found = self.problem("create", a.params)
            if found:
                return found[1]
            now = self.gw.clock()
            p = a.params
            ok = self.repo.add(MachineRow(
                name=p["name"], node_id=(self._host() or {}).get("node_id", ""), ram_mb=p["ram_mb"], cpus=p["cpus"],
                disk_gb=p["disk_gb"], state="creating", action_id=a.id, created_at=now, updated_at=now))
            return None if ok else f"A machine named {p['name']} already exists."

    def _release_create(self, a) -> None:
        """Runs when the action ends. Only a create that surely did nothing gives its quota back.

        outcome_unknown (a kubectl timeout, a gateway restart mid-create) may have left the VM in the
        cluster, so the row stays as `unknown`: the name and the RAM/CPU stay booked until an owner
        deletes or reconciles it. The ledger already holds the final state when this runs."""
        name = a.params["name"]
        final = self.gw.actions.repo.get(a.id)
        if final is not None and final.state == "outcome_unknown":
            self.repo.set_state(name, "unknown", self.gw.clock(), only_from=("creating",), action_id=a.id)
        else:
            self.repo.remove(name, only_state="creating", action_id=a.id)

    # ---- what runs after approval ---------------------------------------------------------
    def _run_create(self, a, finish) -> None:
        res = self.runtime.create(MachineCreateParams.model_validate(a.params))
        if res.outcome == "succeeded":
            self.repo.set_state(a.params["name"], "stopped", self.gw.clock(), action_id=a.id)
        finish(res)

    def _run_toggle(self, running: bool):
        def run(a, finish) -> None:
            name = a.params["name"]
            res = self.runtime.set_running(name, running)
            if res.outcome == "succeeded":
                self.repo.set_state(name, "running" if running else "stopped", self.gw.clock())
            finish(res)
        return run

    def _run_delete(self, a, finish) -> None:
        name = a.params["name"]
        res = self.runtime.delete(name)
        if res.outcome == "succeeded":
            self.repo.remove(name)
        finish(res)

    def register(self) -> None:
        acts = self.gw.actions
        for verb, model, risk, run in (
            ("create", MachineCreateParams, "actuate", self._run_create),
            ("start", MachineRefParams, "actuate", self._run_toggle(True)),
            ("stop", MachineRefParams, "write", self._run_toggle(False)),
            ("delete", MachineDeleteParams, "destructive", self._run_delete),
        ):
            acts.register_type(f"machine.{verb}", FeatureAction(
                risk, run, REQUESTERS, check=self._recheck(verb), params_model=model,
                check_request=self._check_request(verb),
                claim=self._claim_create if verb == "create" else None,
                release=self._release_create if verb == "create" else None))

    # ---- console (the owner only) ---------------------------------------------------------
    def console_ticket(self, name: str, actor: dict | None = None) -> dict:
        row = self.repo.get(name)
        if row is None:
            raise ApiError(404, "not_found", f"There is no machine named {name}.")
        if row["state"] != "running":
            raise ApiError(409, "conflict", f"Machine {name} is {row['state']}: start it first.", reason="not_running")
        ticket = secrets.token_urlsafe(32)
        expires = self.gw.clock() + timedelta(seconds=CONSOLE_TTL_S)
        with self._lock:
            self._tickets = {h: v for h, v in self._tickets.items() if v[1] > self.gw.clock()}
            self._tickets[hashlib.sha256(ticket.encode()).hexdigest()] = (name, expires, actor)
        return {"machine": name, "ticket": ticket, "expires_at": expires.isoformat().replace("+00:00", "Z"),
                "path": f"/v1/machines/{name}/console/ws", "broker": "ready"}

    def redeem(self, ticket: str, name: str) -> dict | None:
        """Single use. The broker (console.py) calls this when the owner's browser connects; it gets
        back who minted the ticket (for the audit line), or None for a used, expired or foreign ticket."""
        with self._lock:
            entry = self._tickets.pop(hashlib.sha256(ticket.encode()).hexdigest(), None)
        if entry is None or entry[0] != name or entry[1] <= self.gw.clock():
            return None
        return entry[2] or {}

    def redeem_ticket(self, ticket: str, name: str) -> bool:
        return self.redeem(ticket, name) is not None
