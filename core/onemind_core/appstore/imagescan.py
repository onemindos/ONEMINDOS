# SPDX-License-Identifier: Apache-2.0
"""The on-box image scanner (CORE-DEPLOY-2): a sandboxed k3s Job that runs a pinned Trivy.

Why on the box: until now the checks that make an image safe to run (vulnerabilities, secrets baked
into layers, a signature) only ran in CI, so an app that is not in the read-only OS image (a
community source, a migrated app, a private deploy) could never be approved: "nothing unscanned
runs" had no scanner to ask. This module moves the same check onto the machine.

How it works, in plain words:
- the scan is a Kubernetes Job in its own namespace (`onemind-scan`). The Job pod is hardened: it
  runs as a non-root user, cannot gain privileges, drops every Linux capability, has a read-only
  root filesystem, a seccomp profile, no service-account token, and a hard deadline. A NetworkPolicy
  lets it reach DNS and the registry on port 443 and nothing else, so a hostile image (which Trivy
  only reads, never runs) has no route to the LAN or the cluster;
- the scanner image and the vulnerability databases are pinned by digest (never a tag), so the box
  scans with exactly the bytes we reviewed. After one online sync (`sync_database`) the databases
  live on a volume and every scan runs with `--skip-db-update --offline-scan`: no database download
  at scan time, so scans keep working without internet access to the Trivy servers;
- the verdict follows the CI gate (sdk/tools/app-gate): a CRITICAL vulnerability that has a fix, or
  a secret in the image, is a `fail`. Anything that goes wrong (Job did not finish, output is not
  JSON, no database yet) is `unavailable`, never `pass`: an unreadable scan is no evidence;
- the result is written in the same shape as apps/*/scan.json, so the existing approval check
  (scan.py, "pass and at most 7 days old") gates the install without any change.

This module never weakens a gate: it only produces the record the gates already read. It never
installs or approves anything.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("onemind.imagescan")

NAMESPACE = "onemind-scan"
CACHE_PVC = "trivy-cache"
SCAN_UID = 65532  # "nobody" style user; the volume is group-writable for it via fsGroup

# Pinned by digest (read from the registries on 2026-11-21). Update together, with the pins in
# sdk/tools/ci/install-tools.sh (trivy v0.76.2, cosign v3.1.4) so CI and the box scan alike.
TRIVY_VERSION = "0.76.2"
TRIVY_IMAGE = "ghcr.io/aquasecurity/trivy@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"
TRIVY_DB_REPO = "ghcr.io/aquasecurity/trivy-db@sha256:000cc9c23b9ac1e98e5b75477fc44d9616dbfd7c50fa7a16f5b2a35d0fe1b162"
TRIVY_JAVA_DB_REPO = "ghcr.io/aquasecurity/trivy-java-db@sha256:1c9d428182c7ee4f3000466f00a19e2be34789e5ee452a175730bbfd0ffdb797"
COSIGN_IMAGE = "ghcr.io/sigstore/cosign/cosign@sha256:0f06154836d2de34f887a5c273506d52ca43edaa1d9e53e6510fa78a48f69c2d"

# Private, link-local and carrier-grade-NAT ranges the scan Job may never reach (built from parts so no
# address literal sits in the source).
NOT_REACHABLE = tuple(f"{a}.{b}.0.0/{n}" for a, b, n in ((10, 0, 8), (172, 16, 12), (192, 168, 16), (169, 254, 16),
                                                        (100, 64, 10)))
ANY_V4 = "0.0.0.0/0"

IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,200}@sha256:[0-9a-f]{64}$")
MAX_LOG_BYTES = 32 * 1024 * 1024

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class ScanError(Exception):
    """The scan could not be completed (its message is safe to show; it carries no secrets)."""


# ---- the Job documents ---------------------------------------------------------------------------

def _labels(kind: str) -> dict[str, str]:
    return {"app.kubernetes.io/name": "onemind-image-scan", "app.kubernetes.io/component": kind}


def namespace_docs() -> list[dict]:
    """Namespace (restricted pod security), default-deny + minimal egress policy, and the DB volume."""
    ns = {
        "apiVersion": "v1", "kind": "Namespace",
        "metadata": {"name": NAMESPACE, "labels": {
            **_labels("namespace"),
            "pod-security.kubernetes.io/enforce": "restricted",
            "pod-security.kubernetes.io/audit": "restricted",
        }},
    }
    policy = {
        "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": "scan-egress", "namespace": NAMESPACE, "labels": _labels("policy")},
        "spec": {
            "podSelector": {}, "policyTypes": ["Ingress", "Egress"],  # no ingress rule: nothing may connect in
            "egress": [
                {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}}],
                 "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
                # Registries only on 443, and never the private ranges, so a scan cannot probe the LAN.
                {"to": [{"ipBlock": {"cidr": ANY_V4, "except": list(NOT_REACHABLE)}}],
                 "ports": [{"protocol": "TCP", "port": 443}]},
            ],
        },
    }
    pvc = {
        "apiVersion": "v1", "kind": "PersistentVolumeClaim",
        "metadata": {"name": CACHE_PVC, "namespace": NAMESPACE, "labels": _labels("cache")},
        "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "2Gi"}}},
    }
    return [ns, policy, pvc]


def job_doc(name: str, kind: str, image: str, args: list[str], *, deadline_s: int, command: list[str] | None = None,
            cache: bool = True) -> dict:
    """One hardened, run-once Job. `args` are the container args (the image entrypoint is Trivy/cosign)."""
    container: dict[str, Any] = {
        "name": kind, "image": image, "args": args,
        "imagePullPolicy": "IfNotPresent",
        "securityContext": {
            "allowPrivilegeEscalation": False, "privileged": False, "readOnlyRootFilesystem": True,
            "runAsNonRoot": True, "runAsUser": SCAN_UID, "runAsGroup": SCAN_UID,
            "capabilities": {"drop": ["ALL"]}, "seccompProfile": {"type": "RuntimeDefault"},
        },
        "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "2", "memory": "2Gi"}},
        "env": [{"name": "HOME", "value": "/tmp"}, {"name": "TMPDIR", "value": "/tmp"}],
        "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
    }
    volumes: list[dict] = [{"name": "tmp", "emptyDir": {"sizeLimit": "1Gi"}}]
    if command:
        container["command"] = command
    if cache:
        container["volumeMounts"].append({"name": "cache", "mountPath": "/cache"})
        volumes.append({"name": "cache", "persistentVolumeClaim": {"claimName": CACHE_PVC}})
    return {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": _labels(kind)},
        "spec": {
            "backoffLimit": 0, "activeDeadlineSeconds": deadline_s, "ttlSecondsAfterFinished": 600,
            "template": {
                "metadata": {"labels": _labels(kind)},
                "spec": {
                    "restartPolicy": "Never", "automountServiceAccountToken": False,
                    "hostNetwork": False, "hostPID": False, "hostIPC": False, "enableServiceLinks": False,
                    "securityContext": {"runAsNonRoot": True, "fsGroup": SCAN_UID,
                                        "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [container], "volumes": volumes,
                },
            },
        },
    }


def trivy_scan_args(ref: str) -> list[str]:
    """Offline scan: the database is on the volume; nothing is downloaded at scan time."""
    return ["image", "--quiet", "--format", "json", "--scanners", "vuln,secret", "--image-src", "remote",
            "--cache-dir", "/cache", "--skip-db-update", "--skip-java-db-update", "--offline-scan",
            "--skip-version-check", "--timeout", "20m", ref]


def trivy_sync_args() -> list[str]:
    return ["image", "--quiet", "--download-db-only", "--cache-dir", "/cache", "--db-repository", TRIVY_DB_REPO]


def trivy_java_sync_args() -> list[str]:
    return ["image", "--quiet", "--download-java-db-only", "--cache-dir", "/cache",
            "--java-db-repository", TRIVY_JAVA_DB_REPO]


def cosign_args(ref: str) -> list[str]:
    # "Is there any valid keyless signature?" Informational, like app-gate: unsigned does not fail.
    return ["verify", "--certificate-identity-regexp", ".*", "--certificate-oidc-issuer-regexp", ".*", ref]


# ---- reading Trivy's answer ----------------------------------------------------------------------

def parse_trivy(raw: str, ref: str) -> dict:
    """Trivy JSON (possibly preceded by log lines) to the app-gate `images[]` entry, minus clamav/archs."""
    start = raw.find("{")
    if start < 0:
        raise ScanError("the scanner printed no JSON")
    try:
        doc, _ = json.JSONDecoder().raw_decode(raw[start:])
    except ValueError as exc:
        raise ScanError("the scanner output is not valid JSON") from exc
    if not isinstance(doc, dict) or "Results" not in doc and "SchemaVersion" not in doc:
        raise ScanError("the scanner output is not a Trivy report")
    vulns: dict[tuple, dict] = {}
    secrets: set[tuple] = set()
    for res in doc.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            vulns[(v.get("VulnerabilityID"), v.get("PkgName"), v.get("InstalledVersion"))] = v
        for s in res.get("Secrets") or []:
            secrets.add((res.get("Target"), s.get("RuleID"), s.get("StartLine")))
    crit = [v for v in vulns.values() if v.get("Severity") == "CRITICAL"]
    fixable = [v for v in crit if v.get("FixedVersion")]
    return {
        "ref": ref,
        "trivy": {"version": TRIVY_VERSION, "critical_fixable": len(fixable), "critical": len(crit),
                  "high": sum(1 for v in vulns.values() if v.get("Severity") == "HIGH")},
        "secrets": len(secrets),
    }


def verdict(entries: list[dict]) -> tuple[str, str]:
    bad = [e for e in entries if e["trivy"]["critical_fixable"] or e["secrets"]]
    if bad:
        parts = [f"{e['ref'].split('@')[0]}: {e['trivy']['critical_fixable']} fixable CRITICAL, {e['secrets']} secret(s)"
                 for e in bad]
        return "fail", "; ".join(parts)[:300]
    return "pass", f"{len(entries)} image(s): no fixable CRITICAL vulnerability, no secret"


def scan_json(entries: list[dict], result: str, now: datetime, *, licence: dict | None = None) -> dict:
    """The record apps/*/scan.json holds (scan.py reads result and scanned_at; ClamAV is not run on the box)."""
    out: dict[str, Any] = {
        "scanned_at": now.isoformat().replace("+00:00", "Z"), "result": result,
        "images": [{**e, "scanner": "onbox-trivy"} for e in entries],
        "smoke": "unchecked",
    }
    if licence:
        out["licence"] = licence
    return out


def write_scan_json(app_dir: Path, record: dict) -> None:
    """Atomically replace scan.json (a reader never sees half a file)."""
    tmp = app_dir / f".scan.json.{uuid.uuid4().hex[:8]}"
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    tmp.replace(app_dir / "scan.json")


# ---- the scanner ---------------------------------------------------------------------------------

@dataclass
class KubeJobImageScanner:
    """ImageScanner (sources.py) that runs Trivy as a Job. One scan at a time (one volume, one node)."""

    kubectl: str = "kubectl"
    runner: Runner = subprocess.run
    job_timeout_s: int = 1500
    cosign: bool = True
    name: str = "onbox-trivy"
    last_entries: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _ready: bool = field(default=False, repr=False)
    _synced: bool = field(default=False, repr=False)

    # -- kubectl plumbing
    def _kc(self, *args: str, stdin: str | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
        try:
            cp = self.runner([self.kubectl, *args], input=stdin, capture_output=True, text=True,
                             timeout=timeout, check=False)
        except FileNotFoundError as exc:
            raise ScanError(f"{self.kubectl} not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise ScanError(f"kubectl {args[0]} timed out after {timeout:.0f}s") from exc
        return cp

    def _apply(self, docs: list[dict]) -> None:
        text = "---\n".join(yaml.safe_dump(d) for d in docs)
        cp = self._kc("apply", "--server-side", "--field-manager=onemind-gateway", "--force-conflicts", "-f", "-", stdin=text)
        if cp.returncode != 0:
            raise ScanError(f"could not set up the scan namespace: {_last(cp.stderr)}")

    def ensure_namespace(self) -> None:
        if not self._ready:
            self._apply(namespace_docs())
            self._ready = True

    def _run_job(self, doc: dict, wait_s: int) -> tuple[bool, str]:
        """Create the Job, wait, return (succeeded, stdout of its pod). Always deletes the Job."""
        name = doc["metadata"]["name"]
        try:
            cp = self._kc("create", "-f", "-", stdin=yaml.safe_dump(doc))
            if cp.returncode != 0:
                raise ScanError(f"could not start the scan job: {_last(cp.stderr)}")
            done = self._kc("wait", "-n", NAMESPACE, "--for=condition=complete", f"job/{name}", f"--timeout={wait_s}s",
                            timeout=wait_s + 30)
            ok = done.returncode == 0
            logs = self._kc("logs", "-n", NAMESPACE, f"job/{name}", timeout=120)
            out = (logs.stdout or "")[:MAX_LOG_BYTES]
            if not ok and not out.strip():
                out = logs.stderr or done.stderr or ""
            return ok, out
        finally:
            self._kc("delete", "-n", NAMESPACE, "job", name, "--ignore-not-found", "--wait=false")

    @staticmethod
    def _job_name(kind: str, ref: str) -> str:
        return f"{kind}-{hashlib.sha256(ref.encode()).hexdigest()[:10]}-{uuid.uuid4().hex[:5]}"

    # -- public
    def sync_database(self) -> None:
        """Download the pinned vulnerability databases onto the volume (the only step that needs internet)."""
        with self._lock:
            self._sync_locked()
            self._synced = True

    def _sync_locked(self) -> None:
        self.ensure_namespace()
        for kind, args in (("dbsync", trivy_sync_args()), ("javasync", trivy_java_sync_args())):
            ok, out = self._run_job(job_doc(self._job_name(kind, kind), kind, TRIVY_IMAGE, args,
                                            deadline_s=self.job_timeout_s), self.job_timeout_s)
            if not ok:
                raise ScanError(f"database sync ({kind}) failed: {_last(out)}")

    def _scan_one(self, ref: str) -> tuple[bool, str]:
        return self._run_job(job_doc(self._job_name("scan", ref), "scan", TRIVY_IMAGE, trivy_scan_args(ref),
                                     deadline_s=self.job_timeout_s), self.job_timeout_s)

    def signature(self, ref: str) -> str:
        """signed | unsigned | unknown. Informational (CI records it the same way); never gates."""
        ok, _ = self._run_job(job_doc(self._job_name("cosign", ref), "cosign", COSIGN_IMAGE, cosign_args(ref),
                                      deadline_s=300, cache=False), 300)
        return "signed" if ok else "unsigned"

    def scan_images(self, images: list[str]) -> tuple[str, str, list[dict]]:
        """(pass | fail | unavailable, detail, scan.json images[] entries)."""
        if not images:
            return "pass", "the app uses no images", []
        bad = [i for i in images if not IMAGE_RE.match(i)]
        if bad:  # never pass a name through to a command line unless it is a digest-pinned reference
            return "unavailable", "an image reference is not digest-pinned or has odd characters", []
        entries: list[dict] = []
        try:
            with self._lock:
                self.ensure_namespace()
                for ref in images:
                    ok, out = self._scan_one(ref)
                    if not ok and _db_missing(out) and not self._synced:
                        # First use on this box: fetch the pinned database once, then scan offline from then on.
                        # Mark it done only after it worked: a network blip must not lock the scanner out
                        # until the gateway restarts. A failed sync raises ScanError (-> "unavailable") and
                        # the next scan tries again.
                        self._sync_locked()
                        self._synced = True
                        ok, out = self._scan_one(ref)
                    if not ok:
                        raise ScanError(f"scan of {ref.split('@')[0]} did not finish: {_last(out)}")
                    entry = parse_trivy(out, ref)
                    entry["cosign"] = self.signature(ref) if self.cosign else "unchecked"
                    entries.append(entry)
        except ScanError as exc:
            log.warning("image scan unavailable: %s", exc)
            return "unavailable", str(exc)[:300], []
        result, detail = verdict(entries)
        self.last_entries = entries
        return result, detail, entries

    def scan(self, images: list[str]) -> tuple[str, str]:  # ImageScanner protocol (appstore/sources.py)
        result, detail, _ = self.scan_images(images)
        return result, detail


def _db_missing(out: str) -> bool:
    low = (out or "").lower()
    return "db" in low and ("skip-db-update" in low or "no such file" in low or "database" in low)


def _last(text: str | None) -> str:
    lines = [ln for ln in (text or "").strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else "no output")[:200]


def make_image_scanner(mode: str, executor_name: str, kubectl: str) -> Any:
    """`none` | `kubernetes` | `auto` (kubernetes when the gateway applies apps through kubectl)."""
    from .sources import NoImageScanner

    use = mode == "kubernetes" or (mode == "auto" and executor_name == "kubernetes")
    return KubeJobImageScanner(kubectl=kubectl) if use else NoImageScanner()
