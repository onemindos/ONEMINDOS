# SPDX-License-Identifier: Apache-2.0
"""Custom apps (PLG-GIT-01, D-026): an owner links a Git repository that holds an onemind.app.yaml.

Coolify and Dokploy build and run whatever a push brings. Here a repository is only *read as data*
(the same hardened checkout as community sources, appstore/sources.py) and goes through the same
checks as every other app before anything runs:

1. `plan` (owner only) resolves the ref to a commit, fetches exactly that commit, validates the
   manifest against the app schema, runs the sandbox's static checks and the on-box image scan, and
   records a **revision**. Nothing is installed. The catalog serves the newest revision that passed.
2. The install or the update is the ordinary `app.install` / `app.update` action: it waits for an
   owner's approval (an agent may request it, never approve it) and is refused without a passing
   scan newer than 7 days. `app.update` restores the previous revision if the new one is not healthy.
3. `rollback` (owner only) points the catalog at the previously deployed revision, re-checks it, and
   leaves the `app.update` that applies it to the owner's approval.

What is not here yet: building a Containerfile, private repositories (no credential is accepted, so
none can reach a log) and a signing policy for custom apps (not decided; see SigningPolicy).
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

from ..auth import Principal
from ..catalog import APP_ID_RE, MANIFEST, AppEntry
from ..errors import ApiError
from ..ledger import Action, iso
from ..lifecycle import bundle_sha256
from ..scan import ScanRecord
from .compose import ComposeError, check_expansion
from .sources import MAX_MANIFEST_BYTES, FetchError, param_problems, static_scan
from .store import CustomApp, CustomRevision

log = logging.getLogger("onemind.appstore")

KEEP_CHECKOUTS = 5  # newest revisions whose checkout stays on disk (plus the served and deployed ones)
CONTAINERFILES = ("Containerfile", "Dockerfile")


class SigningPolicy(Protocol):
    """SEAM, not a policy. How a custom app is signed (who may sign, what a signature proves) is a
    founder decision that is not made yet, so none is invented here. A policy implements `check` and
    the plan shows its answer; today's default says plainly that nothing was checked."""

    def check(self, app_id: str, root: Path, manifest: dict) -> dict: ...


class UndecidedSigning:
    def check(self, app_id: str, root: Path, manifest: dict) -> dict:
        return {"policy": "undecided", "status": "not_checked",
                "detail": "No signing policy for custom apps is decided yet; this app is unsigned and capped at community."}


@dataclass(frozen=True)
class CustomAppEntry(AppEntry):
    """A catalog app that comes from a linked repository (read from its pinned checkout)."""

    custom: dict = field(default_factory=dict)
    scan_record: ScanRecord | None = None

    @property
    def scan(self) -> ScanRecord | None:  # the repository's own scan.json is never trusted
        return self.scan_record

    @property
    def manifest_tier(self) -> str:  # read by the standing-approval check (F-6), which must not see the claim
        return "community"

    def summary(self) -> dict:
        out = super().summary()
        out["tier"] = "community"  # a repository cannot grant itself a tier
        out["custom_source"] = dict(self.custom)
        return out


def _refuse(status: int, message: str, reason: str | None = None, details: list | None = None) -> ApiError:
    return ApiError(status, "conflict" if status == 422 else "stale_precondition", message, reason=reason, details=details)


def revision_json(rev: CustomRevision, app: CustomApp) -> dict:
    return {
        "revision": rev.revision, "commit": rev.commit, "ref": rev.ref, "version": rev.version,
        "scan": {"result": rev.scan_result, "scanned_at": iso(rev.scanned_at), "checks": rev.scan_checks},
        "created_by": rev.created_by, "created_at": iso(rev.created_at),
        "deployed_at": iso(rev.deployed_at) if rev.deployed_at else None, "action_id": rev.action_id,
        "current": rev.revision == app.current_revision, "deployed": rev.revision == app.deployed_revision,
    }


class CustomApps:
    def __init__(self, store: Any, signing: SigningPolicy | None = None):
        self.store = store  # the AppStore; fetcher and image_scanner are read from it on each use
        self.gw, self.repo = store.gw, store.repo
        self.signing: SigningPolicy = signing or UndecidedSigning()
        self._lock = threading.Lock()
        self._manifests: dict[tuple[str, str], tuple[str, dict]] = {}

    @staticmethod
    def key(url: str) -> str:
        return "custom-" + hashlib.sha256(url.encode()).hexdigest()[:16]

    # ---- the catalog provider -------------------------------------------------------------------
    def __call__(self, official: set[str]) -> dict[str, AppEntry]:
        out: dict[str, AppEntry] = {}
        system = set(self.gw.catalog.system_ids())
        for app, rev in self.repo.custom_current():
            root = self.store.fetcher.path(self.key(app.url), rev.commit)
            if app.app_id in official or app.app_id in system or not root.is_dir():
                continue
            doc = self._manifest_at(root, rev)
            if doc is None:
                continue
            meta = {"url": app.url, "ref": rev.ref, "commit": rev.commit, "revision": rev.revision}
            record = ScanRecord(scanned_at=rev.scanned_at, result=rev.scan_result)
            out[app.app_id] = CustomAppEntry(id=app.app_id, dir=root, manifest=doc, custom=meta, scan_record=record)
        return out

    def _manifest_at(self, root: Path, rev: CustomRevision) -> dict | None:
        """The parsed manifest (parsed once per checkout), served only while the checkout is still the
        bytes that were scanned: the manifest and the manifests folder are re-hashed on every load."""
        cached = self._manifests.get((str(root), rev.manifest_sha))
        if cached is not None:
            if self._sha(root, cached[1]) == rev.manifest_sha:
                return cached[1]
            self._manifests.pop((str(root), rev.manifest_sha), None)
        doc, errs = self._read_manifest(root)
        if errs or doc is None or self._sha(root, doc) != rev.manifest_sha:
            log.warning("custom app checkout %s no longer matches what was scanned; not served", root.name)
            return None
        self._manifests[(str(root), rev.manifest_sha)] = (rev.manifest_sha, doc)
        return doc

    @staticmethod
    def _sha(root: Path, doc: dict) -> str:
        """The bundle fingerprint the plan and its approval are bound to (manifest plus manifests
        folder), as bare hex. Empty when it cannot be computed."""
        digest = bundle_sha256(AppEntry(id=str((doc.get("metadata") or {}).get("id", "")), dir=root, manifest=doc))
        return digest.removeprefix("sha256:") if digest else ""

    def _read_manifest(self, root: Path) -> tuple[dict | None, list[str]]:
        path = root / MANIFEST
        try:
            if not path.is_file():
                return None, [f"there is no {MANIFEST} at the top of the repository"]
            if path.stat().st_size > MAX_MANIFEST_BYTES:
                return None, [f"{MANIFEST} is larger than {MAX_MANIFEST_BYTES // 1024} KiB"]
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            check_expansion(doc, 5000)  # before the schema validator walks it
        except (OSError, ValueError, ComposeError, yaml.YAMLError) as exc:
            return None, [f"{MANIFEST} cannot be parsed ({exc.__class__.__name__})"]
        errs = self.gw.catalog.validate(doc)
        if errs:
            return None, [e for e in errs[:10]]
        if not isinstance(doc, dict) or not APP_ID_RE.match(str((doc.get("metadata") or {}).get("id", ""))):
            return None, ["metadata.id is not a valid app id"]
        return doc, []

    # ---- plan -----------------------------------------------------------------------------------
    def plan(self, p: Principal, url: str, ref: str) -> dict:
        problems = param_problems(url=url)
        if problems:
            raise _refuse(422, "; ".join(problems))
        fetcher = self.store.fetcher
        with self._lock:
            try:
                commit = fetcher.resolve_ref(url, ref)
                root = fetcher.fetch(self.key(url), url, commit)
            except FetchError as exc:
                raise _refuse(422, str(exc), reason="custom_fetch_failed") from exc
            return self._record(p, url, ref, commit, root)

    def _checks(self, entry: AppEntry) -> tuple[str, dict, list[str]]:
        problems, images = static_scan(entry)
        verdict, detail = ("skipped", "static checks failed") if problems else self.store.image_scanner.scan(images)
        result = "pass" if not problems and verdict == "pass" else "fail"
        scanner = self.store.image_scanner.name
        checks = {
            "static": {"result": "pass" if not problems else "fail", "problems": problems[:50]},
            "images": {"result": verdict, "scanner": scanner, "detail": detail[:300], "count": len(images)},
        }
        return result, checks, images

    def _id_clash(self, app_id: str, url: str) -> str | None:
        existing = self.repo.get_custom(app_id)
        if existing is not None:
            return None if existing.url == url else f"{app_id!r} is already a custom app from a different repository"
        taken = {i for i, e in self.gw.catalog.load().items() if not isinstance(e, CustomAppEntry)}
        if app_id in taken or app_id in self.gw.catalog.system_ids():
            return f"an app with the id {app_id!r} is already in the catalog"
        return None

    def _record(self, p: Principal, url: str, ref: str, commit: str, root: Path) -> dict:
        doc, errs = self._read_manifest(root)
        base = {"url": url, "ref": ref, "commit": commit}
        if doc is None:
            return {**base, "app_id": None, "verdict": "blocked", "revision": None, "problems": errs, "notes": [],
                    "scan": None, "signature": None, "action_type": None}
        meta = doc["metadata"]
        app_id = str(meta["id"])
        clash = self._id_clash(app_id, url)
        if clash:
            raise _refuse(409, clash, reason="app_id_taken")
        result, checks, images = self._checks(AppEntry(id=app_id, dir=root, manifest=doc))
        now = self.gw.clock()
        revs = self.repo.custom_revisions(app_id)
        same = next((r for r in reversed(revs) if r.commit == commit), None)
        serve = result == "pass"
        if same is not None:  # the same commit again: refresh its scan, never a second revision
            self.repo.rescan_custom_revision(app_id, same.revision, result, checks, now)
            if serve:
                self.repo.set_custom_current(app_id, same.revision)
            number = same.revision
        else:
            new = CustomRevision(app_id, 0, commit, ref, str(meta.get("version")) if meta.get("version") is not None else None,
                                 self._sha(root, doc), result, checks, now, str(p.id), now, None, None)
            number = self.repo.add_custom_revision(app_id, url, ref, new, serve).revision
        self._prune(self.repo.get_custom(app_id), self.repo.custom_revisions(app_id))
        self.gw.audit.append("customapp.planned", p.as_dict(), None, {
            "app_id": app_id, "url": url, "ref": ref, "commit": commit, "revision": number, "scan": result,
        })
        notes = []
        if any((root / n).is_file() for n in CONTAINERFILES):
            notes.append("A Containerfile is in the repository, but building images is not part of this release: "
                         "the manifests must reference digest-pinned images that already exist.")
        installed = self.store.statuses().get(app_id) == "installed"
        return {**base, "app_id": app_id, "name": meta.get("name"), "version": meta.get("version"), "revision": number,
                "verdict": "ready" if serve else "blocked",
                "problems": checks["static"]["problems"] + ([] if checks["images"]["result"] == "pass" or checks["static"]["problems"]
                                                             else [f"image scan: {checks['images']['detail']}"]),
                "scan": {"result": result, "scanned_at": iso(now), "checks": checks}, "images": images, "notes": notes,
                "signature": self.signing.check(app_id, root, doc),
                "action_type": ("app.update" if installed else "app.install") if serve else None,
                "next": "Request the install in the Market; an owner approves it there." if serve and not installed
                else ("Request the update in the Market; an owner approves it there." if serve else None)}

    def _prune(self, app: CustomApp | None, revs: list[CustomRevision]) -> None:
        if app is None:
            return
        keep = {r.commit for r in revs[-KEEP_CHECKOUTS:]}
        keep |= {r.commit for r in revs if r.revision in (app.current_revision, app.deployed_revision)}
        base = self.store.fetcher.path(self.key(app.url), "x").parent
        if not base.is_dir():
            return
        for child in base.iterdir():
            if child.is_dir() and not child.name.startswith(".") and child.name not in keep:
                shutil.rmtree(child, ignore_errors=True)

    # ---- reads ----------------------------------------------------------------------------------
    @staticmethod
    def rollback_target(app: CustomApp, revs: list[CustomRevision]) -> CustomRevision | None:
        """The most recently deployed revision other than the one running now."""
        earlier = [r for r in revs if r.deployed_at is not None and r.revision != app.deployed_revision]
        return max(earlier, key=lambda r: r.deployed_at, default=None)  # type: ignore[arg-type,return-value]

    def app_json(self, app: CustomApp) -> dict:
        revs = self.repo.custom_revisions(app.app_id)
        target = self.rollback_target(app, revs)
        return {
            "app_id": app.app_id, "url": app.url, "ref": app.ref, "added_at": iso(app.added_at),
            "status": self.store.statuses().get(app.app_id, "not_installed"),
            "current_revision": app.current_revision, "deployed_revision": app.deployed_revision,
            "rollback_to": target.revision if target else None,
            "revisions": [revision_json(r, app) for r in reversed(revs)],
        }

    def view(self) -> list[dict]:
        return [self.app_json(a) for a in self.repo.list_custom()]

    def view_one(self, app_id: str) -> dict:
        app = self.repo.get_custom(app_id)
        if app is None:
            raise ApiError(404, "not_found", "no such custom app")
        return self.app_json(app)

    # ---- rollback -------------------------------------------------------------------------------
    def rollback(self, p: Principal, app_id: str, revision: int | None) -> dict:
        app = self.repo.get_custom(app_id)
        if app is None:
            raise ApiError(404, "not_found", "no such custom app")
        with self._lock:
            revs = self.repo.custom_revisions(app_id)
            if self.store.statuses().get(app_id) != "installed" or app.deployed_revision is None:
                raise _refuse(409, "only an installed custom app can be rolled back", reason="not_installed")
            if revision is None:
                target = self.rollback_target(app, revs)
                if target is None:
                    raise _refuse(409, "there is no earlier deployed revision to go back to", reason="no_previous_revision")
            else:
                target = next((r for r in revs if r.revision == revision), None)
                if target is None or target.deployed_at is None:
                    raise _refuse(422, "only a revision that was deployed before can be rolled back to")
                if target.revision == app.deployed_revision:
                    raise _refuse(409, "that revision is already running", reason="already_deployed")
            fetcher = self.store.fetcher
            try:
                root = fetcher.fetch(self.key(app.url), app.url, target.commit)  # a no-op while the checkout exists
            except FetchError as exc:
                raise _refuse(409, f"revision {target.revision} cannot be fetched again: {exc}", reason="checkout_missing") from exc
            doc, errs = self._read_manifest(root)
            if doc is None or self._sha(root, doc) != target.manifest_sha:
                raise _refuse(409, f"revision {target.revision} no longer matches what was scanned; plan the repository again",
                              reason="revision_changed", details=[{"field": "manifest", "problem": e} for e in errs])
            result, checks, _ = self._checks(AppEntry(id=app_id, dir=root, manifest=doc))
            now = self.gw.clock()
            self.repo.rescan_custom_revision(app_id, target.revision, result, checks, now)
            if result != "pass":
                raise _refuse(409, f"revision {target.revision} no longer passes the scan", reason="scan_failed",
                              details=[{"field": "scan", "problem": x} for x in checks["static"]["problems"][:10]])
            self.repo.set_custom_current(app_id, target.revision)
            self.gw.audit.append("customapp.rollback_planned", p.as_dict(), None, {
                "app_id": app_id, "from_revision": app.deployed_revision, "to_revision": target.revision, "commit": target.commit,
            })
            return {"app_id": app_id, "from_revision": app.deployed_revision, "to_revision": target.revision,
                    "commit": target.commit, "version": target.version, "verdict": "ready", "action_type": "app.update",
                    "scan": {"result": result, "scanned_at": iso(now), "checks": checks},
                    "next": "Request the update in the Market; an owner approves it there, and it is undone if the app is not healthy."}

    # ---- deployed marker ------------------------------------------------------------------------
    def after_dispatch(self, a: Action, outcome: str) -> None:
        """An approved install or update that succeeded marks the revision it was approved for as the
        deployed one. That is found from the bundle fingerprint in the approved plan, not from whatever
        the catalog serves now: a plan or rollback filed while the action ran may have moved it."""
        if a.type not in ("app.install", "app.update") or outcome != "succeeded":
            return
        app = self.repo.get_custom(str(a.params.get("app_id")))
        if app is None or not isinstance(self.gw.catalog.get(app.app_id), CustomAppEntry):
            return  # another app with this id (a source or a signed one) is what was installed
        approved = self._approved_bundle(a)
        rev = next((r for r in reversed(self.repo.custom_revisions(app.app_id)) if approved and r.manifest_sha == approved), None)
        if rev is None:
            log.warning("custom app %s: no revision matches the approved plan of action %s; none marked deployed", app.app_id, a.id)
            return
        self.repo.mark_custom_deployed(app.app_id, rev.revision, a.id, self.gw.clock())

    @staticmethod
    def _approved_bundle(a: Action) -> str | None:
        objects = a.plan.get("objects") if isinstance(a.plan, dict) else None
        for obj in objects or []:
            sha = obj.get("bundle_sha256") if isinstance(obj, dict) else None
            if isinstance(sha, str):
                return sha.removeprefix("sha256:")
        return None
