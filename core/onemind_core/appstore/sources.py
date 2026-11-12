# SPDX-License-Identifier: Apache-2.0
"""Community catalog sources (contract §12.22, PD-12): Git repositories pinned to a commit.

umbrelOS follows the branch head of every store repository and runs its hooks as root on the
host. Here a source is a URL plus a 40-hex commit, added and moved only by an owner-approved
request (`source.add`, `source.move`), fetched exactly at that commit, and nothing in it ever
executes on the host:

- git runs with an argv list (no shell), a fresh empty config (no system or global files), hooks
  pointed at /dev/null, symlinks checked out as plain files, no submodules, no LFS filters, only
  the https transport, no redirects, a timeout, and size and file-count limits on the checkout;
- the checkout is read as data: manifests are parsed with yaml.safe_load and checked;
- app ids must start with `<source name>-`, and an id the official catalog has is ignored;
- a source app's tier is at most `community`, and its own `scan.json` is ignored: installing it
  needs the gateway's **on-box** scan record for the pinned commit (static checks of the
  manifests plus an image scan) that passed and is at most 7 days old.

Without an image scanner on the box (CORE-DEPLOY-2 brings the Trivy/ClamAV job) the image check
is `unavailable` and the record is `fail`: source apps can be browsed but not installed.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

from ..catalog import APP_ID_RE, MANIFEST, AppEntry
from ..scan import ScanRecord
from .compose import ComposeError, check_expansion
from .store import AppStoreRepository, Source, SourceScan

log = logging.getLogger("onemind.appstore")

NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,18}[a-z0-9])?$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%/+-]*)?$")
DIGEST_IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/:-]*(:[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$")
MAX_MANIFEST_BYTES = 256 * 1024
MAX_YAML_BYTES = 1024 * 1024
# What an app may ship (the install sandbox's allowlist, sdk/policy/app-objects.yaml).
ALLOWED_KINDS = frozenset({
    ("apps/v1", "Deployment"), ("apps/v1", "StatefulSet"), ("batch/v1", "Job"), ("batch/v1", "CronJob"),
    ("v1", "Service"), ("v1", "ConfigMap"), ("v1", "Secret"), ("v1", "PersistentVolumeClaim"),
    ("v1", "ServiceAccount"), ("policy/v1", "PodDisruptionBudget"), ("autoscaling/v2", "HorizontalPodAutoscaler"),
    ("rbac.authorization.k8s.io/v1", "Role"), ("rbac.authorization.k8s.io/v1", "RoleBinding"),
})
KUSTOMIZE_REFUSED = ("helmCharts", "helmChartInflationGenerator", "generators", "transformers", "validators")


def param_problems(name: object = None, url: object = None, commit: object = None) -> list[str]:
    problems = []
    if name is not None and (not isinstance(name, str) or not NAME_RE.match(name)):
        problems.append("name must be a DNS label of at most 20 characters")
    if url is not None:
        if not isinstance(url, str) or len(url) > 500 or not URL_RE.match(url) or ".." in url:
            problems.append("url must be https://host/path with no user info, query or fragment")
    if commit is not None and (not isinstance(commit, str) or not COMMIT_RE.match(commit)):
        problems.append("commit must be a full 40-character lowercase hex commit id")
    return problems


class FetchError(Exception):
    pass


Runner = Callable[..., subprocess.CompletedProcess]


class GitFetcher:
    """Fetches exactly one commit of a repository into <root>/<source_id>/<commit>/ (read as data)."""

    def __init__(self, root: Path, *, git: str = "git", timeout_s: float = 120, max_bytes: int = 64 * 1024 * 1024,
                 max_files: int = 10000, allow_file_urls: bool = False, runner: Runner = subprocess.run):
        self.root, self.git, self.timeout_s = root, git, timeout_s
        self.max_bytes, self.max_files = max_bytes, max_files
        self.allow_file_urls = allow_file_urls  # tests only: fetch from a local file:// repository
        self.runner = runner

    def path(self, source_id: str, commit: str) -> Path:
        return self.root / source_id / commit

    def _config(self) -> list[str]:
        cfg = {
            "core.hooksPath": os.devnull, "core.symlinks": "false", "core.fsmonitor": "false",
            "protocol.allow": "never", "protocol.https.allow": "always",
            "http.followRedirects": "false", "submodule.recurse": "false", "fetch.recurseSubmodules": "false",
            "filter.lfs.required": "false", "filter.lfs.smudge": "", "filter.lfs.process": "",
            "advice.detachedHead": "false", "init.defaultBranch": "main", "core.protectNTFS": "true",
        }
        if self.allow_file_urls:
            cfg["protocol.file.allow"] = "always"
        return [arg for k, v in cfg.items() for arg in ("-c", f"{k}={v}")]

    def _git(self, cwd: Path, *args: str, home: Path) -> str:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "LC_ALL": "C",
            "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ASKPASS": "/bin/false", "SSH_ASKPASS": "/bin/false", "GIT_LFS_SKIP_SMUDGE": "1",
        }
        argv = [self.git, "-C", str(cwd), *self._config(), *args]
        try:
            cp = self.runner(argv, capture_output=True, text=True, timeout=self.timeout_s, env=env, check=False)
        except FileNotFoundError as exc:
            raise FetchError(f"{self.git} not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise FetchError(f"git {args[0]} timed out after {self.timeout_s}s") from exc
        if cp.returncode != 0:
            last = (cp.stderr or "").strip().splitlines()
            raise FetchError(f"git {args[0]} failed: {last[-1][:300] if last else cp.returncode}")
        return cp.stdout or ""

    def fetch(self, source_id: str, url: str, commit: str) -> Path:
        final = self.path(source_id, commit)
        if final.is_dir():
            return final
        if param_problems(url=url, commit=commit) and not (self.allow_file_urls and url.startswith("file://")):
            raise FetchError("refusing to fetch: bad url or commit")
        base = self.root / source_id
        base.mkdir(parents=True, exist_ok=True)
        tmp = base / f".tmp-{commit[:12]}-{uuid.uuid4().hex[:8]}"
        home = base / f".home-{uuid.uuid4().hex[:8]}"
        tmp.mkdir()
        home.mkdir()
        try:
            self._git(tmp, "init", "-q", home=home)
            self._git(tmp, "fetch", "-q", "--depth=1", "--no-tags", "--no-recurse-submodules", url, commit, home=home)
            self._git(tmp, "checkout", "-q", "--detach", "FETCH_HEAD", home=home)
            head = self._git(tmp, "rev-parse", "HEAD", home=home).strip()
            if head != commit:
                raise FetchError(f"fetched {head[:12]}, expected {commit[:12]}")
            shutil.rmtree(tmp / ".git")
            self._check_tree(tmp)
            os.replace(tmp, final)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)
        return final

    def _check_tree(self, root: Path) -> None:
        total, count = 0, 0
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for name in dirnames + filenames:
                p = Path(dirpath) / name
                if p.is_symlink():
                    raise FetchError(f"checkout contains a symlink ({p.relative_to(root)})")
            for name in filenames:
                count += 1
                total += (Path(dirpath) / name).stat().st_size
                if count > self.max_files or total > self.max_bytes:
                    raise FetchError(f"checkout is larger than {self.max_files} files or {self.max_bytes // (1024 * 1024)} MiB")

    def drop(self, source_id: str, keep: str | None = None) -> None:
        base = self.root / source_id
        if not base.is_dir():
            return
        for child in base.iterdir():
            if child.name != keep:
                shutil.rmtree(child, ignore_errors=True)
        if keep is None:
            shutil.rmtree(base, ignore_errors=True)


# ---- on-box scan ----------------------------------------------------------------------------------

class ImageScanner(Protocol):
    name: str

    def scan(self, images: list[str]) -> tuple[str, str]:
        """(pass | fail | unavailable, a short detail without secrets)."""


class NoImageScanner:
    name = "none"

    def scan(self, images: list[str]) -> tuple[str, str]:
        return "unavailable", "no on-box image scanner is installed (CORE-DEPLOY-2); images were not checked"


def _yaml_docs(path: Path) -> Iterator[Any]:
    if path.stat().st_size > MAX_YAML_BYTES:
        raise ValueError(f"{path.name} is larger than {MAX_YAML_BYTES // 1024} KiB")
    for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        try:
            check_expansion(doc)
        except ComposeError as exc:
            raise ValueError(str(exc)) from exc
        yield doc


def _pod_spec(doc: dict) -> dict | None:
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    if doc.get("kind") == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec") or {})
    tmpl = spec.get("template") if isinstance(spec.get("template"), dict) else None
    return tmpl.get("spec") if tmpl and isinstance(tmpl.get("spec"), dict) else None


def check_objects(docs: list[Any], app_id: str) -> tuple[list[str], list[str]]:
    """(problems, images) for raw manifest objects; the sandbox's rules, checked before any render."""
    problems: list[str] = []
    images: list[str] = []
    for doc in docs:
        if doc is None:
            continue
        if not isinstance(doc, dict):
            problems.append("a manifest document is not a mapping")
            continue
        if doc.get("kind") == "Kustomization":
            continue
        kind, api = doc.get("kind"), doc.get("apiVersion")
        name = (doc.get("metadata") or {}).get("name") if isinstance(doc.get("metadata"), dict) else None
        where = f"{kind}/{name}"
        if (api, kind) not in ALLOWED_KINDS:
            problems.append(f"K-01 {where}: kind is not allowed for apps")
            continue
        ns = (doc.get("metadata") or {}).get("namespace")
        if ns not in (None, f"app-{app_id}"):
            problems.append(f"N-01 {where}: must live in app-{app_id}")
        if kind == "Service":
            st = (doc.get("spec") or {}).get("type", "ClusterIP")
            if st != "ClusterIP":
                problems.append(f"V-01 {where}: Service type {st} is not allowed")
            if (doc.get("spec") or {}).get("externalIPs"):
                problems.append(f"V-02 {where}: externalIPs are not allowed")
        pod = _pod_spec(doc)
        if pod is None:
            continue
        for key, rule in (("hostNetwork", "F-01"), ("hostPID", "F-02"), ("hostIPC", "F-03")):
            if pod.get(key) is True:
                problems.append(f"{rule} {where}: spec.{key} is not allowed")
        for vol in pod.get("volumes") or []:
            if isinstance(vol, dict) and "hostPath" in vol:
                problems.append(f"F-04 {where}: hostPath volume {vol.get('name')} is not allowed")
        for c in (pod.get("containers") or []) + (pod.get("initContainers") or []):
            if not isinstance(c, dict):
                continue
            img = c.get("image")
            if isinstance(img, str):
                images.append(img)
                if not DIGEST_IMAGE_RE.match(img):
                    problems.append(f"I-01 {where}: image {img} is not pinned by digest")
            for port in c.get("ports") or []:
                if isinstance(port, dict) and port.get("hostPort"):
                    problems.append(f"F-05 {where}: hostPort is not allowed")
            sc = c.get("securityContext") if isinstance(c.get("securityContext"), dict) else {}
            if sc.get("privileged") is True:
                problems.append(f"F-06 {where}: privileged containers are not allowed")
            add = (sc.get("capabilities") or {}).get("add") if isinstance(sc.get("capabilities"), dict) else None
            for cap in add or []:
                if cap != "NET_BIND_SERVICE":
                    problems.append(f"F-07 {where}: capability {cap} is not on the reviewed list")
    return problems, sorted(set(images))


def static_scan(entry: AppEntry) -> tuple[list[str], list[str]]:
    """(problems, images) for an app folder read as data; never renders or runs anything."""
    problems: list[str] = []
    try:
        mdir = entry.manifests_dir
    except ValueError as exc:
        return [f"Z-02 {exc}"], []
    if not mdir.is_dir():
        return [f"spec.manifests {mdir.name!r} is not a folder"], []
    kfile = next((mdir / n for n in ("kustomization.yaml", "kustomization.yml", "Kustomization") if (mdir / n).is_file()), None)
    if kfile is None:
        return ["no kustomization.yaml in spec.manifests"], []
    docs: list[Any] = []
    try:
        kust = next(iter(_yaml_docs(kfile)), None) or {}
    except (ValueError, yaml.YAMLError, OSError) as exc:
        return [f"kustomization: cannot parse ({exc.__class__.__name__})"], []
    if not isinstance(kust, dict):
        return ["kustomization is not a mapping"], []
    for key in KUSTOMIZE_REFUSED:
        if kust.get(key):
            problems.append(f"Z-03 kustomization: {key} is not allowed")
    root = mdir.resolve()
    for key in ("resources", "bases", "components", "patches", "patchesStrategicMerge"):
        for ref in kust.get(key) or []:
            path = ref.get("path") if isinstance(ref, dict) else ref
            if not isinstance(path, str):
                continue
            if "://" in path or path.startswith(("git@", "github.com/", "ssh:")) or "?ref=" in path:
                problems.append(f"Z-01 kustomization {key}: remote reference {path!r} is not allowed")
                continue
            target = (mdir / path).resolve()
            if not target.is_relative_to(entry.dir.resolve()):
                problems.append(f"Z-02 kustomization {key}: {path!r} leaves the app folder")
                continue
            if key in ("resources", "bases", "components") and target.is_file():
                try:
                    docs += list(_yaml_docs(target))
                except (ValueError, yaml.YAMLError, OSError) as exc:
                    problems.append(f"{path}: cannot parse ({exc.__class__.__name__})")
            elif target.is_dir() and target != root:
                for f in sorted(target.rglob("*.y*ml")):
                    try:
                        docs += list(_yaml_docs(f))
                    except (ValueError, yaml.YAMLError, OSError) as exc:
                        problems.append(f"{f.name}: cannot parse ({exc.__class__.__name__})")
    found, images = check_objects(docs, entry.id)
    return problems + found, images


@dataclass(frozen=True)
class SourceAppEntry(AppEntry):
    """A catalog app that comes from a community source (read from its pinned checkout)."""

    source: dict = field(default_factory=dict)
    scan_record: ScanRecord | None = None

    @property
    def scan(self) -> ScanRecord | None:  # the repository's scan.json is never trusted
        return self.scan_record

    def summary(self) -> dict:
        out = super().summary()
        if out.get("tier") == "verified":
            out["tier"] = "community"
        out["catalog_source"] = dict(self.source)
        return out


def scan_entry(entry: AppEntry, scanner: ImageScanner, now: datetime, source: Source) -> SourceScan:
    problems, images = static_scan(entry)
    if problems:
        img_verdict, img_detail = "skipped", "static checks failed"
    else:
        img_verdict, img_detail = scanner.scan(images)
    result = "pass" if not problems and img_verdict == "pass" else "fail"
    checks = {
        "static": {"result": "pass" if not problems else "fail", "problems": problems[:50]},
        "images": {"result": img_verdict, "scanner": scanner.name, "detail": img_detail[:300], "count": len(images)},
    }
    return SourceScan(source.id, source.commit, entry.id, result, checks, now)


class SourceCatalog:
    """Lists the apps of every source from its pinned checkout, for Catalog.load()."""

    def __init__(self, repo: AppStoreRepository, fetcher: GitFetcher, validate: Callable[[object], list[str]]):
        self.repo, self.fetcher, self.validate = repo, fetcher, validate
        self.errors: dict[str, list[str]] = {}

    def entries_for(self, src: Source, official: set[str]) -> tuple[dict[str, SourceAppEntry], list[str]]:
        root = self.fetcher.path(src.id, src.commit)
        if not root.is_dir():
            return {}, [f"checkout of {src.commit[:12]} is missing; move the source to its commit again to refetch"]
        scans = self.repo.scans_for(src.id, src.commit)
        meta = {"id": src.id, "name": src.name, "commit": src.commit}
        out: dict[str, SourceAppEntry] = {}
        errors: list[str] = []
        for path in sorted(root.glob(f"*/{MANIFEST}")):
            folder = path.parent.name
            if not folder.startswith(src.name + "-") or not APP_ID_RE.match(folder):
                errors.append(f"{folder}: app ids from source {src.name!r} must start with '{src.name}-'")
                continue
            if folder in official:
                errors.append(f"{folder}: the official catalog has this id; ignored")
                continue
            try:
                if path.stat().st_size > MAX_MANIFEST_BYTES:
                    raise ValueError("manifest too large")
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
                check_expansion(doc, 5000)  # before the schema validator walks it
            except (OSError, ValueError, yaml.YAMLError) as exc:
                errors.append(f"{folder}: cannot parse ({exc.__class__.__name__})")
                continue
            errs = self.validate(doc)
            if not errs and doc["metadata"]["id"] != folder:
                errs = [f"metadata.id must match folder name {folder!r}"]
            if errs:
                errors.append(f"{folder}: {'; '.join(errs[:3])}")
                continue
            sc = scans.get(folder)
            record = ScanRecord(scanned_at=sc.scanned_at, result=sc.result) if sc else None
            out[folder] = SourceAppEntry(id=folder, dir=path.parent, manifest=doc, source=meta, scan_record=record)
        return out, errors

    def __call__(self, official: set[str]) -> dict[str, AppEntry]:
        apps: dict[str, AppEntry] = {}
        errors: dict[str, list[str]] = {}
        for src in self.repo.list_sources():
            found, errs = self.entries_for(src, official | set(apps))
            apps.update(found)
            if errs:
                errors[src.id] = errs
        self.errors = errors
        return apps
