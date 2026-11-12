# SPDX-License-Identifier: Apache-2.0
"""Helpers shared by the app tools: manifests, GitHub API, registry (crane), kustomize."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
APPS_DIR = REPO_ROOT / "apps"
MATRIX_CSV = REPO_ROOT / "research-output" / "evidence" / "license-matrix.csv"
MANIFEST_NAME = "onemind.app.yaml"
UNVERIFIED = "UNVERIFIED"
USER_AGENT = "onemind-app-tools"

POD_TEMPLATE_PATHS = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "ReplicaSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}
GITHUB_URL_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


class ToolError(RuntimeError):
    """An external tool or service failed (exit code 2 territory)."""


def dig(obj: object, path: tuple) -> object:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def load_manifest(app_dir: Path) -> dict:
    return yaml.safe_load((app_dir / MANIFEST_NAME).read_text(encoding="utf-8"))


def owner_repo(manifest: dict) -> str | None:
    for url in (dig(manifest, ("metadata", "links", "github")), dig(manifest, ("metadata", "source"))):
        m = GITHUB_URL_RE.match(url or "")
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


def which(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ToolError(f"required tool not on PATH: {name}")
    return path


def run(argv: list[str], *, input: str | None = None, timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=input, capture_output=True, text=True, timeout=timeout, check=False)


# --- HTTP / GitHub ---------------------------------------------------------------------------

Fetcher = Callable[[str], "bytes | None"]


def http_get(url: str) -> bytes | None:
    """GET a URL; returns None on 404. GITHUB_TOKEN is sent only to api.github.com."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if url.startswith("https://api.github.com/"):
        req.add_header("Accept", "application/vnd.github+json")
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (https URLs only)
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code < 500 or attempt == 2:
                raise ToolError(f"GET {url}: HTTP {exc.code}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            if attempt == 2:
                raise ToolError(f"GET {url}: {getattr(exc, 'reason', exc)}") from exc
        time.sleep(2 * (attempt + 1))
    return None


class GitHub:
    def __init__(self, fetch: Fetcher = http_get):
        self.fetch = fetch

    def json(self, path: str) -> object | None:
        body = self.fetch(f"https://api.github.com/{path}")
        return None if body is None else json.loads(body)

    def raw(self, repo: str, ref: str, path: str) -> str | None:
        body = self.fetch(f"https://raw.githubusercontent.com/{repo}/{ref}/{path}")
        return None if body is None else body.decode("utf-8", "replace")

    def repo(self, repo: str) -> dict | None:
        return self.json(f"repos/{repo}")

    def latest_release(self, repo: str) -> dict | None:
        return self.json(f"repos/{repo}/releases/latest")

    def last_commit_date(self, repo: str) -> str | None:
        commits = self.json(f"repos/{repo}/commits?per_page=1")
        return dig(commits[0], ("commit", "committer", "date")) if commits else None

    def tree(self, repo: str, ref: str) -> list[str]:
        data = self.json(f"repos/{repo}/git/trees/{ref}?recursive=1") or {}
        return [e["path"] for e in data.get("tree", []) if e.get("type") == "blob"]


# --- Registry (crane) ------------------------------------------------------------------------

class Registry:
    """Thin wrapper over crane so tests can replace it with recorded answers."""

    def __init__(self, crane: str | None = None):
        self.crane = crane

    def _crane(self, *args: str) -> str | None:
        exe = self.crane or which("crane")
        proc = run([exe, *args], timeout=600)
        if proc.returncode != 0:
            if re.search(r"MANIFEST_UNKNOWN|NAME_UNKNOWN|not found|404", proc.stderr):
                return None
            raise ToolError(f"crane {' '.join(args)}: {proc.stderr.strip()}")
        return proc.stdout

    def digest(self, ref: str) -> str | None:
        out = self._crane("digest", ref)
        return out.strip() if out else None

    def manifest(self, ref: str) -> dict | None:
        out = self._crane("manifest", ref)
        return json.loads(out) if out else None

    def config(self, ref: str, arch: str) -> dict | None:
        out = self._crane("config", "--platform", f"linux/{arch}", ref)
        return json.loads(out) if out else None

    def platforms(self, ref: str) -> tuple[list[str], dict[str, str]]:
        """Return (linux archs, {arch: child digest}) for an index, or the single image's arch."""
        m = self.manifest(ref)
        if m is None:
            return [], {}
        if "manifests" in m:
            archs, children = [], {}
            for p in m["manifests"]:
                plat = p.get("platform") or {}
                if plat.get("os") == "linux" and plat.get("architecture") not in (None, "unknown"):
                    arch = plat["architecture"] + (f"/{plat['variant']}" if plat.get("variant") and plat["architecture"] != "arm64" else "")
                    if arch not in children:
                        archs.append(arch)
                        children[arch] = p["digest"]
            return archs, children
        cfg = self._crane("config", ref)
        arch = json.loads(cfg).get("architecture") if cfg else None
        return ([arch], {arch: ref.split("@", 1)[1]}) if arch and "@" in ref else ([arch] if arch else [], {})


def split_image(ref: str) -> tuple[str, str | None, str | None]:
    """'reg/repo:tag@sha256:x' -> ('reg/repo', 'tag', 'sha256:x')."""
    digest = None
    if "@" in ref:
        ref, digest = ref.split("@", 1)
    name, tag = ref, None
    last = ref.rsplit("/", 1)[-1]
    if ":" in last:
        name, tag = ref.rsplit(":", 1)
    return name, tag, digest


# --- Rendered manifests ----------------------------------------------------------------------

def render(manifests_dir: Path) -> list[dict]:
    proc = run([which("kustomize"), "build", str(manifests_dir)], timeout=300)
    if proc.returncode != 0:
        raise ToolError(f"kustomize build {manifests_dir}: {proc.stderr.strip()}")
    return [o for o in yaml.safe_load_all(proc.stdout) if isinstance(o, dict)]


def workloads(objects: list[dict]):
    """Yield (object, pod spec) for every object with a pod template."""
    for obj in objects:
        path = POD_TEMPLATE_PATHS.get(obj.get("kind"))
        if path:
            spec = dig(obj, path)
            if isinstance(spec, dict):
                yield obj, spec


def containers(pod_spec: dict):
    for field in ("initContainers", "containers"):
        for c in pod_spec.get(field) or []:
            if isinstance(c, dict):
                yield c


def images(objects: list[dict]) -> list[str]:
    seen: list[str] = []
    for _, spec in workloads(objects):
        for c in containers(spec):
            img = c.get("image")
            if isinstance(img, str) and img not in seen:
                seen.append(img)
    return seen


def resources_summary(objects: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return ([{workload, container, requests, limits}], [{name, size}]) for the README."""
    rows = []
    for obj, spec in workloads(objects):
        for c in containers(spec):
            r = c.get("resources") or {}
            rows.append({"workload": f"{obj['kind']}/{dig(obj, ('metadata', 'name'))}",
                         "container": c.get("name", "?"),
                         "requests": r.get("requests") or {}, "limits": r.get("limits") or {}})
    pvcs = [{"name": dig(o, ("metadata", "name")),
             "size": dig(o, ("spec", "resources", "requests", "storage"))}
            for o in objects if o.get("kind") == "PersistentVolumeClaim"]
    return rows, pvcs


def unverified_files(app_dir: Path) -> list[str]:
    """Files under apps/<id>/ (except scan.json) that still say UNVERIFIED (blocks tier verified)."""
    hits = []
    for p in sorted(app_dir.rglob("*")):
        if p.is_file() and p.name != "scan.json" and p.suffix in (".yaml", ".yml", ".md", ".json"):
            if UNVERIFIED in p.read_text(encoding="utf-8", errors="replace"):
                hits.append(str(p.relative_to(app_dir)))
    return hits


def set_tier(manifest_path: Path, tier: str) -> bool:
    """Rewrite metadata.tier in place, keeping comments. Returns True if the file changed."""
    text = manifest_path.read_text(encoding="utf-8")
    new, n = re.subn(r"(?m)^(  tier:\s*)(verified|community|blocked)\b", rf"\g<1>{tier}", text, count=1)
    if n != 1:
        raise ToolError(f"{manifest_path}: no 'metadata.tier' line to update")
    if new != text:
        manifest_path.write_text(new, encoding="utf-8")
        return True
    return False
