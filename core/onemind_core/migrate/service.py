# SPDX-License-Identifier: Apache-2.0
"""The migration kit: move a namespace from an existing Kubernetes cluster onto this box.

    plan     (owner, direct)   read the namespace (GET only), write the private app bundle and a
                               dry-run report of what maps and what does not. Nothing changes.
    import   migrate.import    sensitive   create app-<id> with every workload at 0 replicas, so
                                           volumes and config exist but nothing runs yet
    copy     migrate.copy      destructive copy each volume (helper pod + restic) into the new
                                           volumes, check every file's sha256, then start the new
                                           app: old and new now run side by side
    cutover  migrate.cutover   destructive stop the old writers, copy the last changes, check them,
                                           start the new app; the old app is left scaled to 0
    revert   migrate.revert    destructive stop the new app and scale the old one back up

Every step after `plan` is an action a person with role owner approves. The kubeconfig for the
old cluster is used for the request it came with and held in memory only until that action ends
(never on disk, never in params, plans or the audit log, which records its sha256).
"""

from __future__ import annotations

import logging
import os
import platform
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit

from .. import __version__
from ..actions import FeatureActionType
from ..auth import Principal
from ..catalog import APP_ID_RE
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import Action, utc
from ..scan import read_scan, scan_problem
from ..sections import config_section
from . import bundle as bundlemod
from . import copyjobs
from .boxkube import BoxKube, BoxKubeError
from .inventory import Forbidden, read_namespace
from .kube import (
    HELPER, SCALE, FenceError, KubeApiError, KubeClient, KubeconfigError, KubeTarget, KubeUnreachable,
    Transport, parse_kubeconfig,
)
from .mapper import STORAGE_CLASS, app_manifest, map_namespace
from .store import MigrateCopyRow, MigratePlanRow, MigrateStore, copy_json, new_id, plan_json

log = logging.getLogger("onemind.migrate")

RESTIC_IMAGE = (
    "docker.io/restic/restic:0.19.1@sha256:136600b6ff6843d61d355f7f71f460a166429f35de6fd11b568fece3c9a4d510"
)


@config_section("migrate")
@dataclass(frozen=True)
class MigrateSettings:
    # ONEMIND_MIGRATE_DATA_DIR: bundles, repositories, keys. Default: <ONEMIND_DATA_DIR>/migrate.
    data_dir: Path | None = None
    # How pods (the helper in the old cluster, the restore Job here) reach this gateway. Defaults
    # to ONEMIND_PUBLIC_URL / the listen address.
    repo_url: str | None = None  # ONEMIND_MIGRATE_REPO_URL
    ca_file: Path | None = None  # ONEMIND_MIGRATE_CA_FILE: the CA those pods trust for repo_url
    helper_image: str = RESTIC_IMAGE  # ONEMIND_MIGRATE_HELPER_IMAGE (pinned by digest)
    kube_timeout_s: float = 30
    copy_timeout_s: int = 6 * 3600
    rollout_timeout_s: int = 600
    poll_s: float = 3.0

    def validate(self) -> None:
        if self.repo_url is not None:
            u = urlsplit(self.repo_url)
            if u.scheme not in ("http", "https") or not u.hostname or u.username or u.query:
                raise ValueError("ONEMIND_MIGRATE_REPO_URL must be http(s)://host[:port][/prefix]")
        if "@sha256:" not in self.helper_image:
            raise ValueError("ONEMIND_MIGRATE_HELPER_IMAGE must be pinned by digest (@sha256:...)")
        if self.ca_file is not None and not self.ca_file.is_file():
            raise ValueError("ONEMIND_MIGRATE_CA_FILE does not name a readable file")
        if self.poll_s <= 0 or self.copy_timeout_s < 60:
            raise ValueError("ONEMIND_MIGRATE_POLL_S must be > 0 and COPY_TIMEOUT_S >= 60")


class StepError(Exception):
    """A step of a running action failed; the message is shown on the action."""


@dataclass
class Held:
    target: KubeTarget
    expires_at: datetime


def _arch() -> str:
    m = platform.machine().lower()
    return "arm64" if m in ("arm64", "aarch64") else "amd64"


class MigrateService:
    def __init__(
        self,
        gw,
        settings: MigrateSettings,
        *,
        box: BoxKube | None = None,
        transport: Callable[[KubeTarget], Transport] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.gw = gw
        self.settings = settings
        self.store = MigrateStore(gw.db)
        self.box = box
        self.transport = transport  # tests: a fake API server instead of HTTPS
        self.sleep = sleep
        self._held: dict[str, Held] = {}
        self.data_dir = settings.data_dir or gw.settings.audit_path.parent / "migrate"

    # ---- paths and small helpers -------------------------------------------------------------
    def bundle_dir(self, plan_id: str) -> Path:
        return self.data_dir / "bundles" / plan_id

    def repo_dir(self, plan_id: str) -> Path:
        return self.data_dir / "repos" / plan_id

    def repo_password(self, plan_id: str) -> str:
        """The restic password of a plan's repository: random, in a 0600 file next to it."""
        keys = self.data_dir / "keys"
        keys.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = keys / f"{plan_id}.key"
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            value = secrets.token_urlsafe(32)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(value)
            return value

    def repo_base(self) -> str:
        return (self.settings.repo_url or self.gw.settings.gateway_url()).rstrip("/")

    def ca_pem(self) -> str | None:
        return self.settings.ca_file.read_text() if self.settings.ca_file else None

    def client(self, target: KubeTarget, namespace: str, grants: frozenset[str] = frozenset()) -> KubeClient:
        transport = self.transport(target) if self.transport else None
        return KubeClient(target, namespace, grants=grants, timeout_s=self.settings.kube_timeout_s, transport=transport)

    def _now(self) -> datetime:
        return self.gw.clock()

    def _plan(self, plan_id: object) -> MigratePlanRow:
        row = self.store.get_plan(str(plan_id)) if isinstance(plan_id, str) else None
        if row is None:
            raise ApiError(404, "not_found", "no such migration plan")
        return row

    def view(self, row: MigratePlanRow) -> dict:
        out = plan_json(row, [copy_json(c) for c in self.store.copies(row.id)])
        out["next"] = {
            "planned": "import", "staged": "copy", "running": "cutover", "switched": "done", "superseded": "-",
        }.get(row.state, "-")
        return out

    def list(self) -> list[dict]:
        return [self.view(r) for r in self.store.list_plans()]

    def get(self, plan_id: str) -> dict:
        return self.view(self._plan(plan_id))

    def _event(self, name: str, payload: dict, *, severity: str = "info", principal: Principal | None = None,
               action_id: str | None = None) -> None:
        self.gw.events.publish_event(
            "migrate", name, payload, severity=severity, action_id=action_id,
            resource={"kind": "migration", "id": payload.get("plan_id")},
            principal=principal.as_dict() if principal else None,
        )

    def _deny(self, p: Principal, what: str) -> ApiError:
        self.gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not {what}")

    # ---- plan (direct, owner) ----------------------------------------------------------------
    def plan(self, p: Principal, *, kubeconfig: str, namespace: str, context: str | None,
             app_id: str | None, name: str | None) -> dict:
        if not p.is_owner:
            raise self._deny(p, "plan a migration")
        app_id = app_id or namespace
        if not APP_ID_RE.match(app_id):
            raise ApiError(422, "conflict", "app_id must be a lowercase DNS label of at most 59 characters")
        if self.gw.catalog.get(app_id) is not None:
            raise ApiError(409, "conflict", f"{app_id!r} is a Market app id; pick another with app_id")
        if self.store.active_for_app(app_id) is not None or self.gw.repo.get_app_state(app_id) is not None:
            raise ApiError(409, "conflict", f"an app {app_id!r} already exists on this box; pick another app_id")
        target = self._target(kubeconfig, context)
        inv = self._read(target, namespace)
        result = map_namespace(inv, app_id)
        now = self._now()
        plan_id = new_id("mig")
        manifest = app_manifest(result, name=(name or namespace)[:80], arch=_arch(), version=__version__)
        digest = bundlemod.write_bundle(self.bundle_dir(plan_id), manifest, result.objects, result.workloads)
        report = result.report()
        report["warnings"] = self._warnings()
        row = MigratePlanRow(
            id=plan_id, app_id=app_id, name=manifest["metadata"]["name"], namespace=namespace, state="planned",
            source={
                "server_host": target.server_host, "context": target.context, "version": inv.server_version,
                "credentials_sha256": target.fingerprint,
            },
            report=report, bundle_sha256=digest, busy_action_id=None, old_replicas=None, last_error=None,
            created_by=p.id, created_at=now, updated_at=now,
        )
        self.store.add_plan(row)
        self._event(
            "plan.created",
            {"plan_id": plan_id, "app_id": app_id, "namespace": namespace, "blocking": result.blocking,
             "counts": result.counts(), "credentials": "provided", "credentials_sha256": target.fingerprint},
            principal=p,
        )
        return self.view(row)

    def _warnings(self) -> list[str]:
        out = []
        if urlsplit(self.repo_base()).scheme == "http":
            out.append(
                "the copy travels over plain http to this box (restic encrypts the data; the "
                "short-lived upload password is visible on the network). Set ONEMIND_MIGRATE_REPO_URL "
                "to an https:// address when the box has HTTPS."
            )
        return out

    def _target(self, kubeconfig: str, context: str | None) -> KubeTarget:
        try:
            return parse_kubeconfig(kubeconfig, context)
        except KubeconfigError as exc:
            raise ApiError(422, "conflict", f"kubeconfig: {exc}") from None

    def _read(self, target: KubeTarget, namespace: str):
        try:
            return read_namespace(self.client(target, namespace))
        except Forbidden as exc:
            raise ApiError(
                409, "stale_precondition",
                f"{exc}; give the kubeconfig get/list rights there (onemind migrate role prints them)",
            ) from None
        except KubeUnreachable as exc:
            raise ApiError(409, "stale_precondition", f"cannot reach the cluster: {exc}") from None
        except KubeApiError as exc:
            raise ApiError(409, "stale_precondition", f"the cluster refused a read: {exc}") from None

    # ---- requests (owner) --------------------------------------------------------------------
    def request(self, p: Principal, action_type: str, plan_id: str, *, params: dict, kubeconfig: str | None,
                context: str | None, idempotency_key: str, expires_at: datetime, reason: str | None) -> tuple[dict, bool]:
        if not p.is_owner:  # checked first, so an agent learns nothing about the plan or the cluster
            raise self._deny(p, f"request {action_type}")
        row = self._plan(plan_id)
        if action_type == "migrate.revert" and row.old_replicas and kubeconfig is None:
            raise ApiError(409, "stale_precondition",
                           "OneMind stopped the old app, so scaling it back up needs the old cluster's kubeconfig")
        extra: dict = {}
        target = None
        if kubeconfig is not None:
            target = self._target(kubeconfig, context)
            if target.server_host != row.source.get("server_host"):
                raise ApiError(409, "stale_precondition",
                               "this kubeconfig points at a different cluster than the plan was made from")
            extra = {"credentials": "provided", "credentials_sha256": target.fingerprint}
        action, created = self.gw.actions.request_feature(
            p, action_type, {"plan_id": row.id, **params}, idempotency_key=idempotency_key,
            expires_at=expires_at, reason=reason, audit_extra=extra,
        )
        if target is not None and action["state"] in ("requested", "awaiting_approval"):
            self._held[action["id"]] = Held(target, utc(expires_at))
        return action, created

    def _take_held(self, action_id: str) -> KubeTarget | None:
        held = self._held.get(action_id)
        if held is None or held.expires_at <= self._now():
            self._held.pop(action_id, None)
            return None
        return held.target

    # ---- action types ------------------------------------------------------------------------
    def action_types(self) -> list[FeatureActionType]:
        return [
            FeatureActionType("migrate.import", "sensitive", self._check_import, self._run_import,
                              claim=self._claim_import, release=self._release),
            FeatureActionType("migrate.copy", "destructive", self._check_copy, self._run_copy,
                              claim=self._claim_with_kube, release=self._release),
            FeatureActionType("migrate.cutover", "destructive", self._check_cutover, self._run_cutover,
                              claim=self._claim_with_kube, release=self._release),
            FeatureActionType("migrate.revert", "destructive", self._check_revert, self._run_revert,
                              claim=self._claim_revert, release=self._release),
        ]

    def _claim(self, a: Action) -> str | None:
        if not self.store.claim(a.params["plan_id"], a.id, self._now()):
            return "another migration step is running for this plan"
        return None

    def _claim_import(self, a: Action) -> str | None:
        """At approval only, as for app.install (§10.3, F-7): nothing unscanned runs, private apps included."""
        if not self.gw.skip_scan:
            row = self._plan(a.params["plan_id"])
            problem = scan_problem(row.app_id, read_scan(self.bundle_dir(row.id)), self._now())
            if problem:
                return problem + " (the on-box scan of private bundles, CORE-DEPLOY-2, writes this record)"
        return self._claim(a)

    def _claim_with_kube(self, a: Action) -> str | None:
        if a.id not in self._held or self._take_held(a.id) is None:
            return ("the old cluster's kubeconfig is no longer held (it is kept in memory only until the "
                    "action expires or the gateway restarts); deny this and request the step again")
        return self._claim(a)

    def _claim_revert(self, a: Action) -> str | None:
        row = self.store.get_plan(a.params["plan_id"])
        if row is not None and row.old_replicas and self._take_held(a.id) is None:
            return "scaling the old app back up needs the old cluster's kubeconfig; request the revert again"
        return self._claim(a)

    def _release(self, a: Action) -> None:
        self.store.release(a.params["plan_id"], a.id, self._now())
        self._held.pop(a.id, None)
        self.store.revoke_users(a.id)

    def _check_import(self, params: dict) -> str | None:
        row = self.store.get_plan(str(params.get("plan_id")))
        if row is None:
            return "no such migration plan"
        if row.state not in ("planned", "staged"):
            return f"the plan is {row.state}; import runs only before the data is copied"
        if row.report.get("blocking"):
            return f"the report has {row.report['blocking']} blocking finding(s); fix them in the source and plan again"
        if params.get("bundle_sha256") != row.bundle_sha256:
            return "the request names a different bundle than the plan"
        root = self.bundle_dir(row.id)
        if not root.is_dir() or bundlemod.bundle_sha256(root) != row.bundle_sha256:
            return "the bundle on disk changed after the plan was made; plan again"
        if row.state == "planned":
            if self.gw.catalog.get(row.app_id) is not None or self.gw.repo.get_app_state(row.app_id) is not None:
                return f"an app {row.app_id!r} already exists on this box"
        return None

    def _check_copy(self, params: dict) -> str | None:
        row = self.store.get_plan(str(params.get("plan_id")))
        if row is None:
            return "no such migration plan"
        if row.state not in ("staged", "running"):
            return f"the plan is {row.state}; copy runs after import and before switch-over"
        known = {v["pvc"] for v in row.report.get("volumes") or []}
        unknown = [v for v in params.get("pvcs") or [] if v not in known]
        if unknown:
            return f"not volumes of this plan: {', '.join(unknown)}"
        if not known:
            return "this plan has no volumes to copy"
        return None

    def _check_cutover(self, params: dict) -> str | None:
        row = self.store.get_plan(str(params.get("plan_id")))
        if row is None:
            return "no such migration plan"
        if row.state != "running":
            return f"the plan is {row.state}; switch-over needs the new app running side by side (copy first)"
        copied = {c.pvc for c in self.store.copies(row.id) if c.state in ("verified", "mismatch")}
        missing = [v["pvc"] for v in row.report.get("volumes") or [] if v["pvc"] not in copied]
        if missing:
            return f"copy these volumes once before switching over: {', '.join(missing)}"
        return None

    def _check_revert(self, params: dict) -> str | None:
        row = self.store.get_plan(str(params.get("plan_id")))
        if row is None:
            return "no such migration plan"
        if row.state != "switched":
            return f"the plan is {row.state}; only a switched migration can be reverted"
        return None

    # ---- runners -----------------------------------------------------------------------------
    def _result(self, a: Action, fn: Callable[[MigratePlanRow], tuple[str, list[dict]]]) -> ExecResult:
        row = self._plan(a.params["plan_id"])
        steps: list[dict] = []
        try:
            message, steps = fn(row)
            self.store.update_plan(row.id, self._now(), last_error=None)
            return ExecResult("succeeded", message, steps)
        except (StepError, BoxKubeError, KubeApiError, KubeUnreachable, FenceError) as exc:
            msg = str(exc)[:900]
            self.store.update_plan(row.id, self._now(), last_error=msg)
            self._event("step.failed", {"plan_id": row.id, "type": a.type, "message": msg}, severity="error",
                        action_id=a.id)
            return ExecResult("failed", msg, steps)

    def _run_import(self, a: Action) -> ExecResult:
        def go(row: MigratePlanRow) -> tuple[str, list[dict]]:
            manifest = self._manifest(row)
            if self.box is not None and self.box.get("default", "storageclass", STORAGE_CLASS) is None:
                # Without it the volumes never bind and the copy would wait for nothing.
                raise StepError(f"this box has no StorageClass {STORAGE_CLASS} (the OS platform layer creates it)")
            res = self.gw.executor.run("app.install", bundlemod.entry(self.bundle_dir(row.id), manifest, staging=True))
            if res.outcome != "succeeded":
                self.gw.repo.set_app_state(row.app_id, "failed" if res.outcome == "failed" else "unknown",
                                           self._now(), a.id)
                raise StepError(f"applying the staged app failed: {res.message}")
            self.gw.repo.set_app_state(row.app_id, "stopped", self._now(), a.id)
            self.store.update_plan(row.id, self._now(), state="staged")
            self._event("import.done", {"plan_id": row.id, "app_id": row.app_id}, action_id=a.id)
            return (f"private app {row.app_id} created in app-{row.app_id} with every workload at 0 replicas; "
                    "next: copy the data", res.steps)

        return self._result(a, go)

    def _manifest(self, row: MigratePlanRow) -> dict:
        import yaml

        return yaml.safe_load((self.bundle_dir(row.id) / "onemind.app.yaml").read_text())

    def _need_box(self) -> BoxKube:
        if self.box is None:
            raise StepError("copying data needs this box's Kubernetes (ONEMIND_EXECUTOR=kubernetes)")
        return self.box

    def _run_copy(self, a: Action) -> ExecResult:
        def go(row: MigratePlanRow) -> tuple[str, list[dict]]:
            box = self._need_box()
            target = self._take_held(a.id)
            if target is None:
                raise StepError("the old cluster's kubeconfig is no longer held; request the copy again")
            client = self.client(target, row.namespace, frozenset({HELPER}))
            wanted = a.params.get("pvcs") or [v["pvc"] for v in row.report["volumes"]]
            steps: list[dict] = []
            self._stop_new(box, row, steps)
            results = [self._copy_volume(client, box, row, a, pvc, "warm", steps) for pvc in wanted]
            failed = [r for r in results if r["state"] == "failed"]
            if failed:
                raise StepError("; ".join(f"{r['pvc']}: {r['error']}" for r in failed))
            self._start_new(box, row, a, steps)
            self.store.update_plan(row.id, self._now(), state="running")
            changed = sum(r["failed_files"] or 0 for r in results)
            files = sum(r["files"] or 0 for r in results)
            msg = f"copied {len(results)} volume(s), {files} file(s); the new app runs side by side"
            if changed:
                msg += (f". {changed} file(s) changed while copying (the old app is still writing); the final "
                        "copy at switch-over runs with the old app stopped")
            return msg, steps

        return self._result(a, go)

    def _run_cutover(self, a: Action) -> ExecResult:
        def go(row: MigratePlanRow) -> tuple[str, list[dict]]:
            box = self._need_box()
            stop_old = bool(a.params.get("stop_old"))
            target = self._take_held(a.id)
            if target is None:
                raise StepError("the old cluster's kubeconfig is no longer held; request the switch-over again")
            grants = frozenset({HELPER, SCALE}) if stop_old else frozenset({HELPER})
            client = self.client(target, row.namespace, grants)
            steps: list[dict] = []
            old = self._stop_old(client, row, stop_old, steps)
            try:
                self._stop_new(box, row, steps)
                results = [self._copy_volume(client, box, row, a, v["pvc"], "final", steps)
                           for v in row.report["volumes"]]
                bad = [r for r in results if r["state"] != "verified"]
                if bad:
                    raise StepError("final copy did not verify: " + "; ".join(
                        f"{r['pvc']}: {r['error'] or str(r['failed_files']) + ' file(s) differ'}" for r in bad))
                self._start_new(box, row, a, steps)
            except Exception as exc:
                self._undo_cutover(client, box, row, a, old, steps, exc)
                raise
            self.store.update_plan(row.id, self._now(), state="switched")
            hosts = row.report.get("hosts") or []
            self._event("cutover.done", {"plan_id": row.id, "app_id": row.app_id, "hosts": hosts}, action_id=a.id)
            msg = f"{row.app_id} now runs on this box with the final data; the old app is stopped and left in place"
            if hosts:
                msg += f". Point {', '.join(hosts)} at this box"
            return msg, steps

        return self._result(a, go)

    def _undo_cutover(self, client, box, row, a, old: dict, steps: list[dict], exc: Exception) -> None:
        """Put old and new back side by side after a failed switch-over (best effort, each step logged)."""
        log.warning("cutover of %s failed (%s); restoring the side-by-side state", row.id, exc)
        for key, replicas in old.items():
            kind, name = key.split("/", 1)
            try:
                client.scale(kind, name, replicas)
                steps.append({"undo": f"old {key} scaled back to {replicas}"})
            except Exception as undo_exc:  # report, keep going
                steps.append({"undo": f"old {key} could not be scaled back: {undo_exc.__class__.__name__}"})
        self.store.update_plan(row.id, self._now(), old_replicas=None)
        try:
            self._start_new(box, row, a, steps)
        except Exception as undo_exc:
            steps.append({"undo": f"new app could not be restarted: {undo_exc.__class__.__name__}"})

    def _run_revert(self, a: Action) -> ExecResult:
        def go(row: MigratePlanRow) -> tuple[str, list[dict]]:
            box = self._need_box()
            steps: list[dict] = []
            self._stop_new(box, row, steps)
            self.gw.repo.set_app_state(row.app_id, "stopped", self._now(), a.id)
            if row.old_replicas:
                target = self._take_held(a.id)
                if target is None:
                    raise StepError("the old cluster's kubeconfig is no longer held; request the revert again")
                client = self.client(target, row.namespace, frozenset({SCALE}))
                for key, replicas in row.old_replicas.items():
                    kind, name = key.split("/", 1)
                    client.scale(kind, name, int(replicas))
                    steps.append({"old": f"{key} scaled back to {replicas}"})
                msg = "the new app is stopped and the old app runs again"
            else:
                msg = "the new app is stopped; start the old app yourself (OneMind did not stop it)"
            self.store.update_plan(row.id, self._now(), state="staged", old_replicas=None)
            self._event("reverted", {"plan_id": row.id, "app_id": row.app_id}, severity="warning", action_id=a.id)
            return msg + "; copy again before the next switch-over", steps

        return self._result(a, go)

    # ---- the steps ------------------------------------------------------------------------------
    def _workloads(self, row: MigratePlanRow) -> list[dict]:
        return list(row.report.get("workloads") or [])

    def _stop_new(self, box: BoxKube, row: MigratePlanRow, steps: list[dict]) -> None:
        ns = f"app-{row.app_id}"
        for w in self._workloads(row):
            box.scale(ns, w["kind"], w["name"], 0)
        self._wait(lambda: not box.pods(ns, f"onemind.io/app={row.app_id}"), self.settings.rollout_timeout_s,
                   "the new app's pods did not stop")
        steps.append({"new": f"workloads in {ns} scaled to 0"})

    def _start_new(self, box: BoxKube, row: MigratePlanRow, a: Action, steps: list[dict]) -> None:
        res = self.gw.executor.run("app.install", bundlemod.entry(self.bundle_dir(row.id), self._manifest(row),
                                                                  staging=False))
        if res.outcome != "succeeded":
            raise StepError(f"starting the new app failed: {res.message}")
        ns = f"app-{row.app_id}"
        for w in self._workloads(row):
            if w["replicas"] > 0:
                box.rollout(ns, w["kind"], w["name"], self.settings.rollout_timeout_s)
        self.gw.repo.set_app_state(row.app_id, "installed", self._now(), a.id)
        steps.append({"new": f"{row.app_id} started in {ns}", "workloads": len(self._workloads(row))})

    def _stop_old(self, client: KubeClient, row: MigratePlanRow, stop_old: bool, steps: list[dict]) -> dict:
        """Scale the old workloads to 0 (stop_old) or check that the owner did; wait for their pods to end."""
        old: dict[str, int] = {}
        running = []
        for w in self._workloads(row):
            obj = client.get_workload(w["kind"], w["name"])
            replicas = (obj.get("spec") or {}).get("replicas", 1)
            if replicas:
                old[f"{w['kind']}/{w['name']}"] = int(replicas)
                running.append(w)
        if running and not stop_old:
            cmds = "; ".join(f"kubectl -n {row.namespace} scale {w['kind'].lower()}/{w['name']} --replicas=0"
                             for w in running)
            raise StepError(f"the old app still runs; stop it first ({cmds}) or request the switch-over with stop_old")
        self.store.update_plan(row.id, self._now(), old_replicas=old or None)
        if old:
            # The old replica counts are recorded (above) before anything is scaled, so revert can
            # restore them.
            for key in old:
                kind, name = key.split("/", 1)
                client.scale(kind, name, 0)
            steps.append({"old": f"scaled to 0: {', '.join(sorted(old))}"})
        selectors = [w.get("selector") or {} for w in self._workloads(row)]

        def gone() -> bool:
            for pod in client.list("", "pods"):
                labels = (pod.get("metadata") or {}).get("labels") or {}
                if any(sel and all(labels.get(k) == v for k, v in sel.items()) for sel in selectors):
                    return False
            return True

        self._wait(gone, self.settings.rollout_timeout_s, "the old app's pods did not stop")
        steps.append({"old": "no old pods left"})
        return old

    def _check_scheduled(self, status: dict, started: float, what: str) -> None:
        """A pod still unschedulable after the rollout timeout fails the step instead of waiting hours."""
        if time.monotonic() - started <= self.settings.rollout_timeout_s:
            return
        for cond in status.get("conditions") or []:
            if cond.get("type") == "PodScheduled" and cond.get("status") == "False":
                raise StepError(f"{what} could not be scheduled: {str(cond.get('message') or cond.get('reason'))[:300]}")

    def _wait(self, done: Callable[[], bool], timeout_s: float, what: str) -> None:
        deadline = time.monotonic() + timeout_s
        while not done():
            if time.monotonic() >= deadline:
                raise StepError(f"{what} within {int(timeout_s)} s")
            self.sleep(self.settings.poll_s)

    def _issue_user(self, row: MigratePlanRow, a: Action, mode: str) -> tuple[str, str]:
        username = f"m{mode}-" + secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)
        expires = self._now() + timedelta(seconds=self.settings.copy_timeout_s + 3600)
        self.store.add_user(username, row.id, a.id, secret, mode, expires)
        return username, secret

    def _repository(self, plan_id: str, user: str, secret: str) -> str:
        u = urlsplit(self.repo_base())
        netloc = f"{quote(user, safe='')}:{quote(secret, safe='')}@{u.netloc}"
        return f"rest:{u.scheme}://{netloc}{u.path}/v1/migrate/repo/{plan_id}/"

    def _copy_volume(self, client: KubeClient, box: BoxKube, row: MigratePlanRow, a: Action, pvc: str,
                     phase: str, steps: list[dict]) -> dict:
        now = self._now()
        copy_id = new_id("cpy")
        self.store.add_copy(MigrateCopyRow(
            id=copy_id, plan_id=row.id, action_id=a.id, pvc=pvc, phase=phase, state="running", started_at=now,
        ))
        repo_password = self.repo_password(row.id)
        if not self.repo_dir(row.id).exists():
            self.repo_dir(row.id).mkdir(parents=True, mode=0o700)
        wuser, wsecret = self._issue_user(row, a, "w")
        ruser, rsecret = self._issue_user(row, a, "r")
        hidden = [wsecret, rsecret, repo_password, quote(wsecret, safe=""), quote(rsecret, safe="")]
        vol = next((v for v in row.report["volumes"] if v["pvc"] == pvc), {})
        out: dict = {"pvc": pvc, "state": "failed", "files": None, "failed_files": None, "error": None}
        try:
            helper = self._run_helper(client, row, copy_id, pvc, vol.get("node"), repo_password,
                                      self._repository(row.id, wuser, wsecret), hidden)
            steps.append({"copy": pvc, "phase": phase, "snapshot": helper["snapshot_id"][:12], "files": helper["files"]})
            restored = self._run_restore(box, row, copy_id, pvc, helper["snapshot_id"], repo_password,
                                         self._repository(row.id, ruser, rsecret), hidden)
            same = restored["manifest_sha256"] == helper["manifest_sha256"] and restored["failed"] == 0
            state = "verified" if same else "mismatch"
            self.store.finish_copy(
                copy_id, self._now(), state=state, snapshot_id=helper["snapshot_id"], files=helper["files"],
                failed_files=restored["failed"], bytes=helper["bytes"], manifest_sha256=helper["manifest_sha256"],
            )
            steps.append({"verify": pvc, "result": state, "failed_files": restored["failed"]})
            self._event(f"copy.{state}", {"plan_id": row.id, "pvc": pvc, "phase": phase, "files": helper["files"],
                                          "failed_files": restored["failed"]},
                        severity="info" if same else "warning", action_id=a.id)
            out.update(state=state, files=helper["files"], failed_files=restored["failed"])
        except (StepError, BoxKubeError, KubeApiError, KubeUnreachable) as exc:
            err = copyjobs.scrub(str(exc), hidden)[:900]
            self.store.finish_copy(copy_id, self._now(), state="failed", error=err)
            self._event("copy.failed", {"plan_id": row.id, "pvc": pvc, "phase": phase}, severity="error",
                        action_id=a.id)
            out["error"] = err
        return out

    def _run_helper(self, client: KubeClient, row: MigratePlanRow, copy_id: str, pvc: str, node: str | None,
                    repo_password: str, repository: str, hidden: list[str]) -> dict:
        name = copyjobs.pod_name(copy_id, "copy")
        pod = copyjobs.helper_pod(
            name=name, plan_id=row.id, copy_id=copy_id, pvc=pvc, node=node, image=self.settings.helper_image,
            repository=repository, repo_password=repo_password, ca_pem=self.ca_pem(),
            tags=["onemind", "unit=migrate", f"plan={row.id.lower()}", f"copy={copy_id.lower()}", f"pvc={pvc}"],
            deadline_s=self.settings.copy_timeout_s,
        )
        client.create_helper_pod(pod)
        try:
            phase = {"v": None}

            started = time.monotonic()

            def finished() -> bool:
                status = client.get_pod(name).get("status") or {}
                phase["v"] = status.get("phase")
                self._check_scheduled(status, started, f"helper pod {name} in the old cluster")
                return phase["v"] in ("Succeeded", "Failed")

            self._wait(finished, self.settings.copy_timeout_s, f"helper pod {name} did not finish")
            logs = client.helper_log(name)
        finally:
            try:
                client.delete_helper_pod(name)
            except Exception:  # deleted on the next try or by its activeDeadlineSeconds; never fatal
                log.warning("could not delete helper pod %s", name)
        outcome = copyjobs.helper_outcome(copyjobs.parse_result(logs))
        if phase["v"] != "Succeeded" or outcome is None:
            raise StepError(f"helper pod {phase['v']}: {copyjobs.scrub(logs, hidden)[-600:]}")
        return outcome

    def _run_restore(self, box: BoxKube, row: MigratePlanRow, copy_id: str, pvc: str, snapshot: str,
                     repo_password: str, repository: str, hidden: list[str]) -> dict:
        ns = f"app-{row.app_id}"
        name = copyjobs.pod_name(copy_id, "restore")
        box.apply(ns, copyjobs.restore_secret(name=name, namespace=ns, app_id=row.app_id, repository=repository,
                                              repo_password=repo_password, ca_pem=self.ca_pem()))
        try:
            box.apply(ns, copyjobs.restore_job(
                name=name, namespace=ns, app_id=row.app_id, plan_id=row.id, pvc=pvc, snapshot_id=snapshot,
                image=self.settings.helper_image, secret=name, deadline_s=self.settings.copy_timeout_s,
            ))
            state = {"job": None}

            started = time.monotonic()

            def finished() -> bool:
                state["job"] = box.get(ns, "job", name)
                st = (state["job"] or {}).get("status") or {}
                if st.get("succeeded") or st.get("failed"):
                    return True
                if time.monotonic() - started > self.settings.rollout_timeout_s:
                    for pod in box.pods(ns, f"job-name={name}"):
                        self._check_scheduled(pod.get("status") or {}, started, f"restore pod for {pvc}")
                return False

            self._wait(finished, self.settings.copy_timeout_s, f"restore job {name} did not finish")
            logs = box.logs(ns, name)
            box.delete(ns, "job", name)
        finally:
            box.delete(ns, "secret", name)
        outcome = copyjobs.restore_outcome(copyjobs.parse_result(logs))
        if not ((state["job"] or {}).get("status") or {}).get("succeeded") or outcome is None:
            raise StepError(f"restore job failed: {copyjobs.scrub(logs, hidden)[-600:]}")
        return outcome

    # ---- startup -----------------------------------------------------------------------------------
    def reconcile(self) -> None:
        """After a restart: release plans whose action ended, mark copies that were running failed."""
        now = self._now()
        n = self.store.fail_running_copies(now, "gateway restarted during the copy")
        if n:
            log.warning("%d migration copies were interrupted by a restart", n)
        for row in self.store.busy_plans():
            a = self.gw.repo.get(row.busy_action_id)
            if a is None or a.state not in ("accepted", "dispatched"):
                self.store.release(row.id, row.busy_action_id, now)

    def helper_preview(self, plan_id: str, pvc: str) -> dict:
        """The helper pod the copy step would create, with placeholders instead of credentials."""
        row = self._plan(plan_id)
        vol = next((v for v in row.report.get("volumes") or [] if v["pvc"] == pvc), None)
        if vol is None:
            raise ApiError(404, "not_found", "no such volume in this plan")
        return copyjobs.helper_pod(
            name=copyjobs.pod_name("x" * 12, "copy"), plan_id=row.id, copy_id="<copy-id>", pvc=pvc,
            node=vol.get("node"), image=self.settings.helper_image,
            repository="rest:" + self.repo_base().replace("://", "://<user>:<password issued at copy>@", 1)
            + f"/v1/migrate/repo/{row.id}/",
            repo_password="<repository password, kept on the box>", tags=["onemind", "unit=migrate"],
            ca_pem=None, deadline_s=self.settings.copy_timeout_s,
        )

