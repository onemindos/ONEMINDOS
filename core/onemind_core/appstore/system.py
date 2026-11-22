# SPDX-License-Identifier: Apache-2.0
"""System apps ("Built in"): switch off, never uninstall (founder ask 2026-11-21, refs #234).

What this adds on top of the app store:

- `GET /v1/system-apps` (routers/appstore.py): every app on the signed list with its state.
- Two action types, `app.disable` and `app.enable`. An owner requests and approves them; an agent
  may only *request* (it lands in awaiting_approval and waits for an owner, like every other write).
- While an app is switched off: its workload is scaled to zero (volumes, secrets and settings are
  untouched), it disappears from `GET /v1/apps` (so from the dock, search, MCP tools and the phone),
  and every `/v1/apps/<id>/...` route answers 409 `stale_precondition` with reason `app_disabled`.
- A system app can never be removed or have its data deleted, by anyone (owner, CLI or agent): 409,
  reason `system_app_protected`. Files, Approvals, Settings and Market cannot be switched off either.

Which ids are system apps comes only from the signed list (systemlist.py), never from a manifest.
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel, ConfigDict, Field

from .. import lifecycle as lc
from ..actions import FeatureAction
from ..auth import Principal
from ..catalog import APP_ID_RE, AppEntry
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import Action, iso
from ..systemlist import SystemApp, SystemList
from .store import AppStoreRepository

PROTECTED = frozenset({"app.remove", "app.delete_data"})
# Only app.stop is harmless on a switched-off app; the rest would bring it back to life.
BLOCKED_WHILE_OFF = frozenset({"app.install", "app.start", "app.restart", "app.update", "app.configure"})


class SystemAppParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)


def _refuse(status: int, code: str, message: str, reason: str | None = None) -> ApiError:
    return ApiError(status, code, message, reason=reason)


class SystemApps:
    def __init__(self, store, system: SystemList):
        self.store = store  # the AppStore
        self.gw = store.gw
        self.repo: AppStoreRepository = store.repo
        self.list = system

    # ---- reads -----------------------------------------------------------------------------------
    def disabled_ids(self) -> frozenset[str]:
        return frozenset(self.repo.disabled())

    def view(self) -> list[dict]:
        off = self.repo.disabled()
        catalog = self.gw.catalog.load()
        statuses = self.store.statuses()
        rows = []
        for app in sorted(self.list.apps.values(), key=lambda a: a.name.lower()):
            entry = catalog.get(app.id)
            md = (entry.manifest.get("metadata") or {}) if entry else {}
            spec = (entry.manifest.get("spec") or {}) if entry else {}
            updates = spec.get("updates") if isinstance(spec.get("updates"), dict) else {}
            prior, action_id, when = off.get(app.id, (None, None, None))
            rows.append({
                "id": app.id, "name": md.get("name") or app.name, "kind": app.klass, "update": app.update,
                "disable": "allowed" if app.can_disable else "never",
                "enabled": app.id not in off, "can_disable": app.can_disable,
                "status": statuses.get(app.id) if entry else None,
                "version": str(md["version"]) if md.get("version") is not None else None,
                "license": md.get("license") if isinstance(md.get("license"), str) else None,
                "update_channel": updates.get("channel") if app.update == "own" else "os",
                "disabled_at": iso(when), "action_id": action_id,
            })
        return rows

    # ---- preconditions on the ordinary lifecycle types ---------------------------------------------
    def check_app(self, action_type: str, params: dict, app: AppEntry, phase: str) -> None:
        if app.id not in self.list.apps:
            return
        if action_type in PROTECTED and app.id in self.list.apps:
            raise _refuse(409, "stale_precondition",
                          f"{app.id} is a built-in app: it cannot be removed, only switched off",
                          "system_app_protected")
        if action_type in BLOCKED_WHILE_OFF and app.id in self.disabled_ids():
            raise _refuse(409, "stale_precondition",
                          f"{app.id} is switched off; switch it on first (app.enable)", "app_disabled")

    # ---- app.disable / app.enable ---------------------------------------------------------------------
    def _system_app(self, app_id: str) -> SystemApp:
        app = self.list.get(app_id)
        if app is None:
            raise _refuse(404, "not_found", f"{app_id!r} is not a built-in app")
        return app

    def _check_disable(self, params: dict, principal: Principal | None, phase: str) -> None:
        app = self._system_app(params["app_id"])
        if not app.can_disable:
            raise _refuse(409, "stale_precondition", f"{app.name} cannot be switched off", "system_app_protected")
        if app.id in self.disabled_ids():
            raise _refuse(409, "stale_precondition", f"{app.name} is already switched off", "already_disabled")
        status = self.store.statuses().get(app.id)
        if app.klass == "container" and status not in (None, "installed", "stopped"):
            raise _refuse(409, "stale_precondition", f"{app.name} is {status}; try again when it has settled")

    def _check_enable(self, params: dict, principal: Principal | None, phase: str) -> None:
        app = self._system_app(params["app_id"])
        if app.id not in self.disabled_ids():
            raise _refuse(409, "stale_precondition", f"{app.name} is already on", "already_enabled")

    def _entry(self, app: SystemApp) -> AppEntry | None:
        return self.gw.catalog.get(app.id) if app.klass == "container" else None

    def _exec(self, a: Action, action_type: str, entry: AppEntry) -> ExecResult:
        # The executor is told the lifecycle type (stop | start), not "app.disable": a disable is a
        # stop that the owner approved and the gateway then remembers.
        run = self.gw.executor.run
        if "ctx" in inspect.signature(run).parameters:
            return run(action_type, entry, agent=None, ctx=lc.ExecContext())
        return run(action_type, entry, agent=None)

    def _run_disable(self, a: Action) -> ExecResult:
        app = self._system_app(a.params["app_id"])
        entry = self._entry(app)
        status = self.store.statuses().get(app.id) if entry else None
        prior = status if status in ("installed", "stopped") else "not_installed"
        steps: list[dict] = []
        if entry is not None and status == "installed":
            result = self._exec(a, "app.stop", entry)
            if result.outcome != "succeeded":
                return result
            steps = result.steps
            self.gw.repo.set_app_state(app.id, "stopped", self.gw.clock(), a.id)
        self.repo.set_disabled(app.id, prior, a.id, self.gw.clock())
        self.gw.events.publish_event("app", "disabled", {"app_id": app.id, "action_id": a.id},
                                     resource={"kind": "app", "id": app.id})
        return ExecResult("succeeded", f"{app.name} is switched off; its data is kept", steps)

    def _run_enable(self, a: Action) -> ExecResult:
        app = self._system_app(a.params["app_id"])
        prior = self.repo.disabled().get(app.id, ("not_installed", None, None))[0]
        entry = self._entry(app)
        steps: list[dict] = []
        if entry is not None and prior == "installed":
            # Start first, clear the switch after: a failed start leaves the app off, not half on.
            self.repo.clear_disabled(app.id)
            self.gw.repo.set_app_state(app.id, "installed", self.gw.clock(), a.id)
            result = self._exec(a, "app.start", entry)
            if result.outcome != "succeeded":
                self.gw.repo.set_app_state(app.id, "stopped", self.gw.clock(), a.id)
                self.repo.set_disabled(app.id, prior, a.id, self.gw.clock())
                return result
            steps = result.steps
        else:
            self.repo.clear_disabled(app.id)
        self.gw.events.publish_event("app", "enabled", {"app_id": app.id, "action_id": a.id},
                                     resource={"kind": "app", "id": app.id})
        return ExecResult("succeeded", f"{app.name} is on", steps)

    def specs(self) -> dict[str, FeatureAction]:
        def feature(run, check):
            # Owners request and approve. An agent may request; approval is still an owner's (the base
            # rule: only an owner approves a feature action).
            return FeatureAction(
                "sensitive", lambda a, finish: finish(run(a)), requesters=frozenset({"agent"}),
                params_model=SystemAppParams,
                check_request=lambda params, principal: check(params, principal, "request"),
                check=lambda a: check(a.params, None, "approve"),
            )
        return {
            "app.disable": feature(self._run_disable, self._check_disable),
            "app.enable": feature(self._run_enable, self._check_enable),
        }
