# SPDX-License-Identifier: Apache-2.0
"""The appstore feature, wired into the gateway (contract §12.22).

`AppStore(gw)` owns the feature's state and does three things for the gateway:

1. **Reads** for the router: settings, dependencies, host ports, exposure, sources and the
   Compose conversion. App logs are §12.15 (routers/monitoring.py), not here.
2. **Action types** registered on the gateway's ActionService: `source.add`, `source.move`,
   `source.remove`, `exposure.private`, `exposure.mesh`, `exposure.public` (owner requests, owner
   approves; an agent never requests them). `app.configure` is §12.40's type; this module only
   checks its values against `spec.settings` and keeps the typed values for the settings view.
3. **Preconditions** on `app.install`, `app.remove` and `app.configure`: dependencies, host ports,
   the on-box scan of community apps, "remove these first", and setting values.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..actions import FeatureAction
from ..auth import Principal
from ..catalog import APP_ID_RE, MANIFEST, AppEntry
from ..context import Gateway
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import Action, iso
from ..scan import MAX_AGE
from ..sections import config_section
from . import appsettings, compose, deps, exposure, hostports
from .sources import (
    COMMIT_RE, FetchError, GitFetcher, ImageScanner, NoImageScanner, SourceAppEntry, SourceCatalog,
    param_problems, scan_entry,
)
from .store import AppStoreRepository, Source

log = logging.getLogger("onemind.appstore")

APP_ID = APP_ID_RE.pattern
SOURCE_ID = r"^src_[0-9A-Z]{26}$"
CONFIGMAP = "onemind-settings"
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@config_section("appstore")
@dataclass(frozen=True)
class AppStoreSettings:
    sources_dir: Path | None = None   # ONEMIND_APPSTORE_SOURCES_DIR; default: <audit log folder>/sources
    git: str = "git"                  # ONEMIND_APPSTORE_GIT
    fetch_timeout_s: int = 120        # ONEMIND_APPSTORE_FETCH_TIMEOUT_S
    max_source_mb: int = 64           # ONEMIND_APPSTORE_MAX_SOURCE_MB

    def validate(self) -> None:
        if not 5 <= self.fetch_timeout_s <= 900:
            raise ValueError("ONEMIND_APPSTORE_FETCH_TIMEOUT_S must be 5-900")
        if not 1 <= self.max_source_mb <= 1024:
            raise ValueError("ONEMIND_APPSTORE_MAX_SOURCE_MB must be 1-1024")


def new_source_id() -> str:
    """A prefixed ULID (contract §12.1): 48-bit milliseconds then 80 random bits, Crockford base32."""
    n = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    return "src_" + "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in reversed(range(26)))


def _refuse(status: int, code: str, message: str, reason: str | None = None, details: list | None = None) -> ApiError:
    return ApiError(status, code, message, reason=reason, details=details)


# ---- action params ---------------------------------------------------------------------------------

class SourceAddParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=20)
    url: str = Field(min_length=9, max_length=500)
    commit: str = Field(min_length=40, max_length=40)


class SourceMoveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(pattern=SOURCE_ID)
    to_commit: str = Field(min_length=40, max_length=40)


class SourceRemoveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(pattern=SOURCE_ID)


class AppParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID)


class AppStore:
    def __init__(self, gw: Gateway, *, image_scanner: ImageScanner | None = None, fetcher: GitFetcher | None = None):
        self.gw = gw
        cfg = gw.settings.section(AppStoreSettings)
        self.repo = AppStoreRepository(gw.db)
        root = cfg.sources_dir or gw.settings.audit_path.parent / "sources"
        self.fetcher = fetcher or GitFetcher(
            root, git=cfg.git, timeout_s=cfg.fetch_timeout_s, max_bytes=cfg.max_source_mb * 1024 * 1024,
        )
        self.image_scanner: ImageScanner = image_scanner or NoImageScanner()
        self.sources = SourceCatalog(self.repo, self.fetcher, gw.catalog.validate)
        self.reserved = hostports.load_reserved()

    # ---- shared helpers ----------------------------------------------------------------------------
    def statuses(self) -> dict[str, str]:
        # "removed" is an app taken away with its data kept (§12.40): not installed, so it provides
        # nothing, holds no host port and has no exposure.
        return {app_id: st.status for app_id, st in self.gw.repo.list_app_states().items()
                if st.status != "removed"}

    def _app(self, app_id: str) -> AppEntry:
        if not isinstance(app_id, str) or not APP_ID_RE.match(app_id):
            raise _refuse(404, "not_found", "no such app")
        entry = self.gw.catalog.get(app_id)
        if entry is None:
            raise _refuse(404, "not_found", f"app {app_id!r} is not in the catalog")
        return entry

    def _deny(self, p: Principal, what: str) -> ApiError:
        self.gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return _refuse(403, "permission_denied", f"{p.kind}/{p.role} may not {what}")

    @staticmethod
    def _adult_person(p: Principal) -> bool:
        return p.kind == "person" and p.role in ("owner", "adult")

    # ---- logs (PD-08) ------------------------------------------------------------------------------
    # ---- settings (PD-09) --------------------------------------------------------------------------
    def fields(self, entry: AppEntry) -> list[appsettings.SettingField]:
        try:
            return appsettings.parse_fields(entry.manifest)
        except appsettings.SettingsSchemaError as exc:
            raise _refuse(409, "stale_precondition", f"app {entry.id!r} has invalid spec.settings: {exc}"[:1000],
                          reason="settings_invalid") from exc

    def settings_view(self, p: Principal, app_id: str) -> dict:
        entry = self._app(app_id)
        fields = self.fields(entry)
        stored, action_id, updated_at = self.repo.get_settings(app_id)
        show = self._adult_person(p)
        return {
            "app_id": app_id, "fields": [f.to_json() for f in fields],
            "values": appsettings.effective(fields, stored) if show else None,
            "updated_at": iso(updated_at), "action_id": action_id,
        }

    def _check_configure(self, params: dict, phase: str) -> None:
        """app.configure on an app that declares spec.settings (registered in ActionService.app_checks).

        The lifecycle executor (contract §12.40) writes the ConfigMap; this checks the values against
        the manifest's fields, at request and again at approval. Apps without spec.settings keep the
        generic §12.40 behaviour.
        """
        entry = self._app(params["app_id"])
        fields = self.fields(entry)
        if not fields:
            return
        problems = appsettings.value_problems(fields, params.get("settings") or {})
        if problems:
            status = 422 if phase == "request" else 409
            code = "conflict" if phase == "request" else "stale_precondition"
            raise _refuse(status, code, "settings: " + "; ".join(problems)[:900], reason="settings_invalid",
                          details=[{"field": f"params.settings.{p.split(':', 1)[0]}", "problem": p} for p in problems[:20]])

    def settings_transform(self, app: AppEntry, merged: dict, changed: dict) -> tuple[dict, bool]:
        """(ConfigMap onemind-settings data, restart?): env name -> string with defaults included, and
        whether a changed field needs the workloads restarted."""
        fields = self.fields(app)
        if not fields:
            return merged, True
        values = appsettings.effective(fields, merged)
        return appsettings.configmap_data(fields, values), appsettings.needs_restart(fields, changed)

    def _record_settings(self, a: Action) -> None:
        entry = self.gw.catalog.get(a.params["app_id"])
        if entry is None:
            return
        fields = self.fields(entry)
        if not fields:
            return
        stored, _, _ = self.repo.get_settings(entry.id)
        values = {**appsettings.effective(fields, stored),
                  **(a.params.get("settings") or {})}
        self.repo.set_settings(entry.id, values, a.id, self.gw.clock())

    # ---- dependencies (PD-10) and host ports (PD-11) ----------------------------------------------
    def dependencies_view(self, app_id: str) -> dict:
        entry = self._app(app_id)
        apps = self.gw.catalog.load()
        statuses = self.statuses()
        have = deps.providing(statuses)
        requires = []
        for r in deps.requirements(entry.manifest):
            requires.append({**r.to_json(), "satisfied_by": deps.satisfied_by(r, have), "choices": [
                {"id": c, "name": (apps[c].manifest.get("metadata") or {}).get("name") if c in apps else None,
                 "in_catalog": c in apps, "installed": c in have} for c in r.choices]})
        dependents = deps.dependents(app_id, {k: v.manifest for k, v in apps.items()}, statuses)
        return {"app_id": app_id, "requires": requires, "dependents": [
            {"id": d, "name": (apps[d].manifest.get("metadata") or {}).get("name")} for d in dependents]}

    def host_ports_view(self, app_id: str, node_id: str | None) -> dict:
        entry = self._app(app_id)
        return {"app_id": app_id, "node_id": node_id or self.gw.settings.node_id,
                "declared": [h.to_json() for h in hostports.declared(entry.manifest)],
                "conflicts": self._port_conflicts(entry)}

    def _port_conflicts(self, entry: AppEntry) -> list[dict]:
        # v0 runs every app on the hub node; per-node placement (CORE-FABRIC-4) narrows `others`.
        apps = self.gw.catalog.load()
        others = {i: apps[i].manifest for i, st in self.statuses().items() if i in apps and st != "removing"}
        return hostports.conflicts(entry.id, entry.manifest, others, self.reserved)

    def check_app(self, action_type: str, params: dict, app: AppEntry, phase: str) -> None:
        """app.install / app.remove / app.configure preconditions (registered in ActionService.app_checks)."""
        if action_type == "app.configure":
            self._check_configure(params, phase)
            return
        statuses = self.statuses()
        if action_type == "app.install":
            missing = deps.unsatisfied(app.manifest, deps.providing(statuses))
            if missing:
                raise _refuse(409, "stale_precondition", deps.missing_message(app.id, missing),
                              reason="dependency_missing",
                              details=[{"field": "spec.dependencies", "problem": f"needs one of {list(r.choices)}"}
                                       for r in missing])
            found = self._port_conflicts(app)
            if found:
                raise _refuse(409, "stale_precondition", hostports.conflict_message(app.id, found),
                              reason="host_port_conflict",
                              details=[{"field": "spec.hostPorts", "problem": f"{c['port']}/{c['protocol']} held by {c['with']}"}
                                       for c in found])
            if phase == "request" and isinstance(app, SourceAppEntry):
                self._ensure_scan(app)
        elif action_type == "app.remove":
            apps = self.gw.catalog.load()
            blocking = deps.dependents(app.id, {k: v.manifest for k, v in apps.items()}, statuses)
            if blocking:
                raise _refuse(409, "stale_precondition", f"remove these first: {', '.join(blocking)}",
                              reason="has_dependents",
                              details=[{"field": "app_id", "problem": f"{d} depends on {app.id}"} for d in blocking])

    # ---- exposure (PD-17) --------------------------------------------------------------------------
    def tier(self, app_id: str) -> str:
        if self.statuses().get(app_id) is None:
            return "private"
        return self.repo.get_exposure(app_id)[0]

    def exposure_view(self, app_id: str) -> dict:
        self._app(app_id)
        tier, action_id, updated_at = self.repo.get_exposure(app_id)
        if self.statuses().get(app_id) is None:
            tier, action_id, updated_at = "private", None, None
        return {"app_id": app_id, "tier": tier, "names": exposure.names(app_id, tier),
                "updated_at": iso(updated_at), "action_id": action_id}

    def _check_exposure(self, tier: str):
        def check(params: dict, principal: Principal, phase: str) -> None:
            app_id = params["app_id"]
            self._app(app_id)
            status = self.statuses().get(app_id)
            if status not in deps.PROVIDING:
                raise _refuse(409, "stale_precondition", f"app {app_id!r} is {status or 'not installed'}")
            if tier == "public":
                raise _refuse(409, "stale_precondition",
                              "public exposure needs the relay (CORE-NET-15), which is parked; use mesh",
                              reason="parked")
        return check

    def _run_exposure(self, tier: str):
        def run(a: Action) -> ExecResult:
            app_id = a.params["app_id"]
            before = self.repo.get_exposure(app_id)[0]
            self.repo.set_exposure(app_id, tier, a.id, self.gw.clock())
            self.gw.events.publish_event("app", "exposure.changed", {
                "app_id": app_id, "from": before, "to": tier, "action_id": a.id,
            }, resource={"kind": "app", "id": app_id})
            return ExecResult("succeeded", f"{app_id} is now {tier}: {', '.join(exposure.names(app_id, tier))}",
                              [{"exposure": tier, "names": exposure.names(app_id, tier)}])
        return run

    def after_dispatch(self, a: Action, outcome: str) -> None:
        """A removal (or a fresh install) starts from private again; a configure records the typed values."""
        if a.type == "app.configure" and outcome == "succeeded":
            self._record_settings(a)
        if a.type in ("app.install", "app.remove") and outcome == "succeeded":
            app_id = a.params["app_id"]
            if self.repo.get_exposure(app_id)[1] is not None:
                self.repo.set_exposure(app_id, "private", None, self.gw.clock())

    # ---- Compose import (PD-13) --------------------------------------------------------------------
    def convert_compose(self, p: Principal, app_id: str, name: str | None, text: str) -> dict:
        if not p.is_owner:
            raise self._deny(p, "convert a Compose file")
        if self.gw.catalog.get(app_id) is not None:
            raise _refuse(409, "conflict", f"app id {app_id!r} is already in the catalog; pick another")
        try:
            result = compose.convert(text, app_id, name)
        except compose.ComposeError as exc:
            raise _refuse(422, "conflict", f"compose: {exc}") from exc
        self.gw.audit.append("deploy.compose.converted", p.as_dict(), None, {
            "app_id": app_id, "ok": result.ok, "refusals": len(result.refusals), "warnings": len(result.warnings),
            "compose_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "rules": sorted({r["rule"] for r in result.refusals}),
        })
        return result.to_json()

    # ---- community sources (PD-12) -----------------------------------------------------------------
    def _source_apps(self, src: Source) -> tuple[dict[str, SourceAppEntry], list[str]]:
        """The source's apps at its pinned commit, against every other catalog id."""
        apps = self.gw.catalog.load()
        others = {i for i, e in apps.items() if not (isinstance(e, SourceAppEntry) and e.source.get("id") == src.id)}
        return self.sources.entries_for(src, others)

    def source_json(self, src: Source, with_apps: bool = True) -> dict:
        out: dict[str, Any] = {
            "id": src.id, "name": src.name, "url": src.url, "commit": src.commit,
            "state": "ready" if self.fetcher.path(src.id, src.commit).is_dir() else "checkout_missing",
            "added_by": src.added_by, "added_at": iso(src.added_at), "updated_at": iso(src.updated_at),
            "action_id": src.action_id,
        }
        if with_apps:
            scans = self.repo.scans_for(src.id, src.commit)
            entries, errors = self._source_apps(src)
            out["apps"] = [{"id": e.id, "version": str((e.manifest.get("metadata") or {}).get("version")),
                            "scan": ({"result": scans[e.id].result, "scanned_at": iso(scans[e.id].scanned_at),
                                      "checks": scans[e.id].checks} if e.id in scans else None)}
                           for e in entries.values()]
            out["errors"] = errors
        return out

    def sources_view(self) -> list[dict]:
        return [self.source_json(s) for s in self.repo.list_sources()]

    def source_view(self, source_id: str) -> dict:
        src = self.repo.get_source(source_id)
        if src is None:
            raise _refuse(404, "not_found", "no such source")
        return self.source_json(src)

    def _installed_from(self, src: Source) -> list[str]:
        statuses = self.statuses()
        return sorted(i for i, e in self.gw.catalog.load().items()
                      if isinstance(e, SourceAppEntry) and e.source.get("id") == src.id and i in statuses)

    def _scan_all(self, src: Source, entries: dict[str, SourceAppEntry]) -> dict[str, str]:
        out = {}
        for entry in entries.values():
            rec = scan_entry(entry, self.image_scanner, self.gw.clock(), src)
            self.repo.put_scan(rec)
            out[entry.id] = rec.result
        return out

    def _ensure_scan(self, app: SourceAppEntry) -> None:
        """Before a first install: scan when the on-box record is missing or older than 7 days."""
        rec = app.scan_record
        if rec is not None and self.gw.clock() - rec.scanned_at <= MAX_AGE:
            return
        src = self.repo.get_source(app.source["id"])
        if src is None:
            return
        scan = scan_entry(app, self.image_scanner, self.gw.clock(), src)
        self.repo.put_scan(scan)
        self.gw.audit.append("source.app.scanned", None, None, {
            "source_id": src.id, "commit": src.commit, "app_id": app.id, "result": scan.result,
        })

    def _check_source_add(self, params: dict, principal: Principal, phase: str) -> None:
        problems = param_problems(params["name"], params["url"], params["commit"])
        if problems:
            raise _refuse(422, "conflict", "; ".join(problems))
        try:
            self.fetcher.check_url(params["url"])
        except FetchError as exc:
            raise _refuse(422, "conflict", str(exc), reason="source_host_refused") from exc
        if self.repo.source_by_name(params["name"]) is not None:
            raise _refuse(409, "conflict", f"a source named {params['name']!r} exists")

    def _run_source_add(self, a: Action) -> ExecResult:
        now = self.gw.clock()
        src = Source(new_source_id(), a.params["name"], a.params["url"], a.params["commit"],
                     str(a.requested_by.get("id")), now, now, a.id)
        try:
            self.fetcher.fetch(src.id, src.url, src.commit)
        except FetchError as exc:
            self.fetcher.drop(src.id)
            return ExecResult("failed", f"fetch failed: {exc}", [{"fetch": src.commit[:12]}])
        if not self.repo.add_source(src):
            self.fetcher.drop(src.id)
            return ExecResult("failed", f"a source named {src.name!r} exists", [])
        entries, errors = self._source_apps(src)
        results = self._scan_all(src, entries)
        self.gw.events.publish_event("catalog", "source.added", {
            "source_id": src.id, "name": src.name, "commit": src.commit, "apps": len(entries),
        }, resource={"kind": "source", "id": src.id})
        return ExecResult("succeeded", f"source {src.name} pinned at {src.commit[:12]}: {len(entries)} apps", [
            {"source_id": src.id, "apps": results, "errors": errors[:20]}])

    def _check_source_move(self, params: dict, principal: Principal, phase: str) -> None:
        if self.repo.get_source(params["source_id"]) is None:
            raise _refuse(404, "not_found", "no such source")
        if not COMMIT_RE.match(params["to_commit"]):
            raise _refuse(422, "conflict", "to_commit must be a full 40-character lowercase hex commit id")

    def _run_source_move(self, a: Action) -> ExecResult:
        src = self.repo.get_source(a.params["source_id"])
        if src is None:
            return ExecResult("failed", "the source was removed", [])
        to = a.params["to_commit"]
        before = {e.id: _manifest_sha(e) for e in self._source_apps(src)[0].values()}
        try:
            self.fetcher.fetch(src.id, src.url, to)
        except FetchError as exc:
            return ExecResult("failed", f"fetch failed: {exc}", [])
        moved = Source(src.id, src.name, src.url, to, src.added_by, src.added_at, self.gw.clock(), a.id)
        entries, errors = self._source_apps(moved)
        after = {i: _manifest_sha(e) for i, e in entries.items()}
        gone_installed = sorted(set(self._installed_from(src)) - set(after))
        if gone_installed:
            if to != src.commit:
                self.fetcher.drop(src.id, keep=src.commit)
            return ExecResult("failed", f"installed apps are not in {to[:12]}; remove these first: "
                              f"{', '.join(gone_installed)}", [])
        results = self._scan_all(moved, entries)
        self.repo.move_source(src.id, to, a.id, self.gw.clock())
        if to != src.commit:
            self.fetcher.drop(src.id, keep=to)
        diff = {"added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
                "changed": sorted(i for i in set(after) & set(before) if after[i] != before[i])}
        self.gw.events.publish_event("catalog", "source.moved", {
            "source_id": src.id, "from": src.commit, "to": to, **{k: len(v) for k, v in diff.items()},
        }, resource={"kind": "source", "id": src.id})
        return ExecResult("succeeded", f"source {src.name} moved {src.commit[:12]} -> {to[:12]}", [
            {"diff": diff, "apps": results, "errors": errors[:20]}])

    def _check_source_remove(self, params: dict, principal: Principal, phase: str) -> None:
        src = self.repo.get_source(params["source_id"])
        if src is None:
            raise _refuse(404, "not_found", "no such source")
        installed = self._installed_from(src)
        if installed:
            raise _refuse(409, "stale_precondition", f"remove these first: {', '.join(installed)}",
                          reason="has_installed_apps")

    def _run_source_remove(self, a: Action) -> ExecResult:
        src = self.repo.get_source(a.params["source_id"])
        if src is None:
            return ExecResult("succeeded", "the source was already removed", [])
        self.repo.remove_source(src.id)
        self.fetcher.drop(src.id)
        self.gw.events.publish_event("catalog", "source.removed", {"source_id": src.id, "name": src.name},
                                     resource={"kind": "source", "id": src.id})
        return ExecResult("succeeded", f"source {src.name} removed", [])

    # ---- registration ------------------------------------------------------------------------------
    def specs(self) -> dict[str, FeatureAction]:
        def feature(risk, params_model, run, check):
            """One POST /v1/actions type: only a person owner requests it, never an agent (§12.22)."""
            return FeatureAction(
                risk, lambda a, finish: finish(run(a)), params_model=params_model,
                check_request=lambda params, principal: check(params, principal, "request"),
                check=lambda a: check(a.params, None, "approve"),
            )
        return {
            "source.add": feature("sensitive", SourceAddParams, self._run_source_add, self._check_source_add),
            "source.move": feature("sensitive", SourceMoveParams, self._run_source_move, self._check_source_move),
            "source.remove": feature("write", SourceRemoveParams, self._run_source_remove, self._check_source_remove),
            "exposure.private": feature("write", AppParams, self._run_exposure("private"), self._check_exposure("private")),
            "exposure.mesh": feature("sensitive", AppParams, self._run_exposure("mesh"), self._check_exposure("mesh")),
            "exposure.public": feature("sensitive", AppParams, self._run_exposure("public"), self._check_exposure("public")),
        }

    def install(self) -> None:
        actions = self.gw.actions
        for action_type, spec in self.specs().items():
            actions.register_type(action_type, spec)
        actions.app_checks.append(self.check_app)
        actions.after_dispatch.append(self.after_dispatch)
        actions.settings_transform = self.settings_transform
        self.gw.catalog.providers.append(self.sources)


def _manifest_sha(entry: AppEntry) -> str:
    try:
        return hashlib.sha256((entry.dir / MANIFEST).read_bytes()).hexdigest()
    except OSError:
        return ""

