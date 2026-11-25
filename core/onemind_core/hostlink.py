# SPDX-License-Identifier: Apache-2.0
"""The gateway's link to the host executor (#146, #142; docs/leap/core/HOST-ACTIONS.md section 2).

`onemindd host serve` runs as root on the box and listens on /run/onemind/host.sock (mode 0660,
root:onemind). It does what an owner already approved, from the id of the approved action, and
nothing else: restart, shut down, factory reset, install an OS update, restart one service (#636), rename the box (P-05), set the keyboard layout (P-11). This module is the gateway's
half of that contract:

- `HostLink.problem(type)`: can this box do it now? (`GET /v1/status`)
- `HostLink.probe()`: is the host helper there and answering, and what is the box called? The gateway's
  `GET /v1/status` reports it as `host helper: reachable|missing` (#875). The gateway is a systemd unit
  (onemind-gateway.service, user onemind), not a k3s pod: it opens the socket directly, and the host
  admits root and the gateway's uid only (SO_PEERCRED), so no pod or host path is involved.
- `HostLink.run(action, finish)`: after the owner's approval, `POST /v1/operations` with the action
  id (and the approved version for an install). The host writes its journal before it acts, so a retry
  never runs twice. Argv never leaves the gateway: the host knows a fixed set of kinds and nothing else.
- a poller reads `GET /v1/operations/{id}` and closes the ledger action when the journal says
  `succeeded` or `failed`. `going_down` means the box is about to stop, so the action stays open;
  these types are SELF_RECONCILED (actions.py), so a gateway restarted by the reboot finds the action
  still `dispatched` and reads the verdict from the journal.

Deny by default: no socket, an unreachable socket or a host that says `unavailable` all end the action
`failed` with the reason, never `succeeded`. A request whose answer was lost (timeout) is left to the
journal. `interrupted` (the host crashed mid-action) is `outcome_unknown`: nothing says whether it ran.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from .context import Gateway
from .executors import ExecResult
from .ledger import Action, utc
from .sections import config_section
from .storage import StorageClient, StorageTimeout, StorageUnavailable

log = logging.getLogger("onemind.hostlink")

# gateway action type -> host kind (HOST-ACTIONS.md section 2)
KINDS = {
    "system.restart": "restart",
    "system.shutdown": "shutdown",
    "system.factory_reset": "factory-reset",
    "os.update.install": "os-install",
    "os.rollback": "os-rollback",  # P-16: back to the previous A/B slot
    "service.restart": "service-restart",  # #636: one registry unit; the host checks it is restartable
    "system.set_timezone": "set-timezone",  # P-04: one IANA zone; the host keeps it on /data
    "instance.rename": "set-hostname",  # P-05: the box's DNS label; avahi then answers <name>.local
    "storage.eject": "eject",  # P-10: unmount and power off one removable drive; the host checks it again
    "system.set_keymap": "set-keymap",  # P-11: the console and kiosk keyboard layout; the host checks the image offers it
}
ACTION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
# RFC 1123 labels: what the host helper may call the box (H-06: the answer is checked, not trusted).
HOSTNAME = re.compile(r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*")
PROBE_TIMEOUT_S = 2.0  # GET /v1/status reads the helper on every call: a silent socket must not hold it up
PLAN_SHA = re.compile(r"^[0-9a-f]{64}$")  # internal/host: the hash of the factory-reset plan the owner approved
LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")  # the box name: one lower-case DNS label
SERIAL = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
DEVICE = re.compile(r"^/dev/[a-z][a-z0-9]{1,15}$")
LAYOUT = re.compile(r"^[A-Za-z0-9_]{1,24}$")  # xkb layout and variant ids (internal/keymap)
VARIANT = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
UNIT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,90}\.(service|socket|timer|path)$")
ZONE = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}$")  # same shape as internal/host ZoneName
NOT_ZONES = frozenset({"localtime", "posixrules", "Factory"})  # tzdata helper entries; localtime loops (host list)
UNREACHABLE = "engine_unreachable"  # the reason when nothing answers on the socket
NO_HOST = ("The gateway cannot reach the host service on this box (onemind-host.socket), so the action did not run. "
           "Your approval is recorded; use the rescue console or the box itself.")


@config_section("hostlink")
@dataclass(frozen=True)
class HostLinkSettings:
    socket: Path = Path("/run/onemind/host.sock")  # ONEMIND_HOSTLINK_SOCKET
    poll_s: int = 5  # ONEMIND_HOSTLINK_POLL_S: how often open host actions are checked
    timeout_s: float = 10.0  # ONEMIND_HOSTLINK_TIMEOUT_S: one request to the host service
    # A request the host has no record of, or a host that stays silent, ends outcome_unknown after this long.
    give_up_s: int = 1800  # ONEMIND_HOSTLINK_GIVE_UP_S

    def validate(self) -> None:
        if self.poll_s < 1:
            raise ValueError("ONEMIND_HOSTLINK_POLL_S must be at least 1")
        if self.timeout_s <= 0:
            raise ValueError("ONEMIND_HOSTLINK_TIMEOUT_S must be positive")
        if self.give_up_s < 60:
            raise ValueError("ONEMIND_HOSTLINK_GIVE_UP_S must be at least 60")


def _text(v: Any, n: int = 300) -> str | None:
    return v[:n] if isinstance(v, str) and v else None


@dataclass(frozen=True)
class HelperState:
    """What `HostLink.probe` found: the helper answered its status request, and the box's name if it sent one."""

    reachable: bool
    hostname: str | None = None


class HostLink:
    def __init__(self, gw: Gateway, client: StorageClient | None = None):
        self.gw = gw
        self.cfg: HostLinkSettings = gw.settings.section(HostLinkSettings)
        self.client = client or StorageClient(self.cfg.socket, self.cfg.timeout_s)
        self._probe = StorageClient(self.cfg.socket, min(PROBE_TIMEOUT_S, self.cfg.timeout_s))
        self._lock = threading.Lock()
        self._finishers: dict[str, Callable[[ExecResult], None]] = {}
        self._tracked: set[str] = set()  # action ids to read from the journal: started here or left by a restart
        self._inflight: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- can it run? ---------------------------------------------------------------------------
    def present(self) -> bool:
        try:
            os.stat(self.cfg.socket)
            return True
        except OSError:
            return False

    def probe(self) -> HelperState:
        """Reachable only when the helper answers `GET /v1/status` with 200 and a JSON object. Why not is
        logged, never returned: it can hold the socket path."""
        if not self.present():
            log.info("host helper missing: no socket at the configured path")
            return HelperState(False)
        try:
            status, st = self._probe.call("GET", "/v1/status")
        except (StorageUnavailable, StorageTimeout) as exc:
            log.warning("host helper did not answer: %s", exc)
            return HelperState(False)
        if status != 200 or not isinstance(st, dict):
            log.warning("host helper answered %s to its status request", status)
            return HelperState(False)
        name = st.get("hostname")
        return HelperState(True, name if isinstance(name, str) and HOSTNAME.fullmatch(name) else None)

    def problem(self, action_type: str) -> tuple[str, str] | None:
        """(reason, message) why this box cannot perform the action now, or None when it can."""
        kind = KINDS.get(action_type)
        if kind is None:
            return "unavailable", f"{action_type} is not a host action"
        if not self.present():
            return UNREACHABLE, NO_HOST
        try:
            status, st = self.client.call("GET", "/v1/status")
        except (StorageUnavailable, StorageTimeout) as exc:
            return UNREACHABLE, f"{NO_HOST} ({exc})"
        if status != 200 or not isinstance(st, dict):
            return "host_error", f"The host service answered {status} to its status request."
        if st.get("journal") is False:
            return "no_journal", "The host service cannot write its journal (is /data mounted?), so it will not act."
        for op in st.get("operations") or []:
            if isinstance(op, dict) and op.get("kind") == kind:
                if op.get("available") is True:
                    return None
                return "unavailable", _text(op.get("unavailable_reason")) or f"The host cannot {kind} now."
        return "unavailable", f"This version of the host service does not offer {kind}."

    def reset_plan_hash(self) -> str | None:
        """The hash of the factory-reset plan the host would carry out right now (GET /v1/plans/factory-reset),
        or None when the host cannot say. The request stores it; the host refuses a wipe whose plan changed."""
        try:
            status, plan = self.client.call("GET", "/v1/plans/factory-reset")
        except (StorageUnavailable, StorageTimeout):
            return None
        sha = plan.get("plan_sha256") if status == 200 and isinstance(plan, dict) else None
        return sha if isinstance(sha, str) and PLAN_SHA.fullmatch(sha) else None

    # ---- after approval --------------------------------------------------------------------------------
    def run(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        """FeatureAction.run: send the approved action to the host. Closes now when the host refuses
        or cannot be reached; otherwise the poller closes it from the host's journal."""
        result = self._submit(a)
        if result is not None:
            finish(result)
            return
        with self._lock:
            self._finishers[a.id] = finish
            self._tracked.add(a.id)

    def _submit(self, a: Action) -> ExecResult | None:
        kind = KINDS.get(a.type)
        if kind is None or not ACTION_ID.match(a.id):
            return ExecResult("failed", f"{a.type} cannot be sent to the host service", steps=[{"step": "host", "result": "bad_request"}])
        body: dict[str, str] = {"action_id": a.id, "kind": kind}
        if kind in ("os-install", "os-rollback"):
            version = (a.params or {}).get("version")
            if not isinstance(version, str) or not version:
                return ExecResult("failed", "the action has no approved version", steps=[{"step": "host", "result": "bad_request"}])
            body["version"] = version
        if kind == "factory-reset":
            plan = (a.params or {}).get("plan_sha256")
            if not isinstance(plan, str) or not PLAN_SHA.fullmatch(plan):
                return ExecResult("failed", "the reset has no approved plan", steps=[{"step": "host", "result": "bad_request"}])
            body["plan_sha256"] = plan
        if kind == "service-restart":
            unit = (a.params or {}).get("unit")
            if not isinstance(unit, str) or not UNIT.fullmatch(unit):
                return ExecResult("failed", "the restart has no approved unit", steps=[{"step": "host", "result": "bad_request"}])
            body["unit"] = unit
        if kind == "set-timezone":
            zone = (a.params or {}).get("zone")
            if not isinstance(zone, str) or not ZONE.fullmatch(zone) or zone in NOT_ZONES:
                return ExecResult("failed", "the change has no approved time zone", steps=[{"step": "host", "result": "bad_request"}])
            body["zone"] = zone
        if kind == "set-hostname":
            name = (a.params or {}).get("name")
            if not isinstance(name, str) or not LABEL.fullmatch(name):
                return ExecResult("failed", "the rename has no approved name", steps=[{"step": "host", "result": "bad_request"}])
            body["hostname"] = name
        if kind == "eject":
            device = (a.params or {}).get("device")
            if not isinstance(device, str) or not DEVICE.fullmatch(device):
                return ExecResult("failed", "the eject has no approved drive", steps=[{"step": "host", "result": "bad_request"}])
            body["device"] = device
            serial = (a.params or {}).get("serial")
            if serial is not None:
                if not isinstance(serial, str) or not SERIAL.fullmatch(serial):
                    return ExecResult("failed", "the eject has a malformed drive serial", steps=[{"step": "host", "result": "bad_request"}])
                body["serial"] = serial
        if kind == "set-keymap":
            layout, variant = (a.params or {}).get("layout"), (a.params or {}).get("variant")
            if not isinstance(layout, str) or not LAYOUT.fullmatch(layout) or (variant is not None and (not isinstance(variant, str) or not VARIANT.fullmatch(variant))):
                return ExecResult("failed", "the request has no approved layout", steps=[{"step": "host", "result": "bad_request"}])
            body["layout"] = layout
            if variant:
                body["variant"] = variant
        with self._lock:
            self._inflight.add(a.id)
        try:
            status, resp = self.client.call("POST", "/v1/operations", body)
        except StorageUnavailable as exc:
            return ExecResult("failed", f"{NO_HOST} ({exc})", steps=[{"step": "host", "kind": kind, "result": UNREACHABLE}])
        except StorageTimeout:
            with self._lock:  # sent, answer lost: the host's journal knows whether it took it
                self._tracked.add(a.id)
            return None
        finally:
            with self._lock:
                self._inflight.discard(a.id)
        resp = resp if isinstance(resp, dict) else {}
        if status in (200, 202):
            return None
        reason = _text(resp.get("reason"), 64) or f"http_{status}"
        msg = _text(resp.get("message")) or f"The host service answered {status}."
        return ExecResult("failed", f"The host did not start it: {msg}", steps=[{"step": "host", "kind": kind, "result": reason}])

    # ---- poller ------------------------------------------------------------------------------------
    def start(self) -> None:
        """Pick up what a restart left open (a reboot restarts the gateway while the host finishes the
        action), then poll."""
        for a in self.gw.repo.list(states={"accepted", "dispatched"}):
            if a.type not in KINDS:
                continue
            if a.state == "accepted":  # approved, never sent (dispatch comes first): a host action never starts from here
                self.gw.actions.finish(a.id, "outcome_unknown", "the gateway restarted before the request reached the host",
                                       from_states=frozenset({"accepted"}))
                continue
            with self._lock:
                self._tracked.add(a.id)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="hostlink-poller", daemon=True)
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
                log.exception("host poll failed")
            self._stop.wait(self.cfg.poll_s)

    def poll(self) -> None:
        with self._lock:
            ids = [i for i in self._tracked if i not in self._inflight]
        for action_id in ids:
            self._sync(action_id)

    def _sync(self, action_id: str) -> None:
        a = self.gw.repo.get(action_id)
        if a is None or a.state != "dispatched":
            self._forget(action_id)  # closed already (a refusal, or a person resolved it)
            return
        old = self.gw.clock() - utc(a.updated_at) > timedelta(seconds=self.cfg.give_up_s)
        try:
            status, op = self.client.call("GET", f"/v1/operations/{action_id}")
        except (StorageUnavailable, StorageTimeout) as exc:
            if old:
                self._close(a, "outcome_unknown", f"the host service could not be reached to learn the result ({exc})")
            return
        if status == 404:
            if old:  # the gateway stopped between approval and the request, or the journal lost it
                self._close(a, "outcome_unknown", "the host service has no record of this action; it may not have run")
            return
        if status != 200 or not isinstance(op, dict):
            if old:
                self._close(a, "outcome_unknown", f"the host service answered {status} when asked for the result")
            return
        state = op.get("state")
        if state == "succeeded":
            self._close(a, "succeeded", _text(op.get("message")) or "the host carried it out")
        elif state == "failed":
            msg = _text(op.get("message")) or "the host could not carry it out"
            if op.get("reason") == "interrupted":  # the host stopped mid-action: nothing says whether it ran
                self._close(a, "outcome_unknown", msg)
            else:
                self._close(a, "failed", msg, reason=_text(op.get("reason"), 64))
        # accepted | running | going_down: still open. The box may stop now; the journal keeps the answer.

    def _forget(self, action_id: str) -> None:
        with self._lock:
            self._tracked.discard(action_id)
            self._finishers.pop(action_id, None)

    def _close(self, a: Action, outcome: str, msg: str, reason: str | None = None) -> None:
        with self._lock:
            finish = self._finishers.pop(a.id, None)
            self._tracked.discard(a.id)
        steps = [{"step": "host", "kind": KINDS[a.type], "result": reason or outcome}]
        if finish is not None:  # started by this process: the ledger's own closer (audit, release)
            finish(ExecResult(outcome, msg, steps=steps))
            return
        # Left open by a restart: close it from the journal.
        self.gw.actions.finish(a.id, outcome, msg, {"steps": steps}, from_states=frozenset({"dispatched"}))
