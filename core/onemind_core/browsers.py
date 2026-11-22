# SPDX-License-Identifier: Apache-2.0
"""Browser apps in a desktop window, one profile per person (#692).

A Market browser app (Neko, apps/firefox and apps/chromium; #593) declares `spec.browser` in its
manifest. The app's own Deployment is only a template: it runs no replica and its Service is never
proxied, so there is no shared profile. Each signed-in person gets, in the app's namespace:
- PersistentVolumeClaim `profile-<key>`, mounted where the template mounts `spec.browser.profileVolume`;
- Deployment and ClusterIP Service `browser-<key>` (no hostPort, no NodePort, no host network).

`<key>` is person_key(person id): a one-way hash, so no name or id of a person appears in a cluster
object or an app host name. The person reaches their pod only through the gateway proxy at
`<app>--<key>.<box domain>` (proxy.py), which compares the key with the signed-in person and
refuses any other (403). The claim is created when the person first opens the browser and is
deleted only by `browser.profile.reset` after an owner approves it (or with the app's namespace, by
an owner-approved app.remove). Closing the window scales the pod to zero and keeps the claim.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .catalog import APP_ID_RE
from .executors import ExecResult
from .ledger import Action

PROFILE_LABEL = "onemind.io/browser-profile"
HOST_SEP = "--"
KEY_LEN = 16
KEY_RE = re.compile(r"^[0-9a-f]{16}$")
RESET_ACTION = "browser.profile.reset"
DNS_LABEL_MAX = 63
_VOLUME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class BrowserError(Exception):
    """The cluster refused or the app's template cannot carry a per-person profile."""


def person_key(person_id: str) -> str:
    """The stable, one-way key of a person's browser profile (16 hex characters)."""
    return hashlib.sha256(b"onemind-browser-profile\0" + person_id.encode()).hexdigest()[:KEY_LEN]


def workload_name(key: str) -> str:
    return f"browser-{key}"


def profile_claim(key: str) -> str:
    return f"profile-{key}"


@dataclass(frozen=True)
class BrowserSpec:
    profile_volume: str
    port: int


def browser_spec(manifest: dict) -> BrowserSpec | None:
    """`spec.browser` of a manifest with a web port, or None for any other app."""
    spec = manifest.get("spec") or {}
    browser, web = spec.get("browser"), spec.get("web")
    if not isinstance(browser, dict) or not isinstance(web, dict):
        return None
    volume, port = browser.get("profileVolume"), web.get("port")
    if not isinstance(volume, str) or not _VOLUME_RE.match(volume):
        return None
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return None
    return BrowserSpec(volume, port)


def host_label(app_id: str, key: str) -> str | None:
    """`<app>--<key>`, the first label of the person's browser host; None when it is too long."""
    label = f"{app_id}{HOST_SEP}{key}"
    return label if len(label) <= DNS_LABEL_MAX else None


def split_host_label(label: str) -> tuple[str, str] | None:
    """(app id, key) for a browser host label, else None."""
    app_id, sep, key = label.rpartition(HOST_SEP)
    if not sep or not KEY_RE.match(key) or not APP_ID_RE.match(app_id):
        return None
    return app_id, key


def _labels(app_id: str, key: str) -> dict[str, str]:
    return {PROFILE_LABEL: key, "onemind.io/app": app_id, "app.kubernetes.io/part-of": "onemind-apps",
            "app.kubernetes.io/component": "browser-profile"}


def person_objects(app_id: str, key: str, spec: BrowserSpec, template: dict, template_claim: dict,
                   *, running: bool = True) -> list[dict]:
    """The person's PVC, Deployment and Service, made from the app's template Deployment and claim.

    Refuses (BrowserError) a template that publishes a port on the node or shares the host network:
    a person's browser is reached only through the gateway.
    """
    if not KEY_RE.match(key):
        raise BrowserError("not a profile key")
    labels = _labels(app_id, key)
    pod = copy.deepcopy(((template.get("spec") or {}).get("template") or {}).get("spec") or {})
    if pod.get("hostNetwork") or pod.get("hostPID") or pod.get("hostIPC"):
        raise BrowserError("the template shares the host's network or processes")
    for c in [*(pod.get("containers") or []), *(pod.get("initContainers") or [])]:
        if any(p.get("hostPort") for p in c.get("ports") or []):
            raise BrowserError("the template publishes a port on the node")
    volumes = pod.get("volumes") or []
    found = [v for v in volumes if v.get("name") == spec.profile_volume]
    if len(found) != 1:
        raise BrowserError(f"the template has no volume {spec.profile_volume!r} for the profile")
    found[0].clear()
    found[0].update({"name": spec.profile_volume, "persistentVolumeClaim": {"claimName": profile_claim(key)}})
    claim_spec = template_claim.get("spec") or {}
    claim = {"accessModes": claim_spec.get("accessModes") or ["ReadWriteOnce"],
             "resources": {"requests": dict(((claim_spec.get("resources") or {}).get("requests")) or {"storage": "5Gi"})}}
    if claim_spec.get("storageClassName"):
        claim["storageClassName"] = claim_spec["storageClassName"]
    name = workload_name(key)
    return [
        {"apiVersion": "v1", "kind": "PersistentVolumeClaim",
         "metadata": {"name": profile_claim(key), "labels": labels}, "spec": claim},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name, "labels": labels},
         "spec": {"replicas": 1 if running else 0, "revisionHistoryLimit": 2, "strategy": {"type": "Recreate"},
                  "selector": {"matchLabels": {PROFILE_LABEL: key}},
                  "template": {"metadata": {"labels": labels}, "spec": pod}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "labels": labels},
         "spec": {"type": "ClusterIP", "selector": {PROFILE_LABEL: key},
                  "ports": [{"name": "http", "port": spec.port, "targetPort": spec.port, "protocol": "TCP"}]}},
    ]


Runner = Callable[..., subprocess.CompletedProcess]


class BrowserProfiles:
    """The per-person browser objects of installed browser apps, through kubectl."""

    def __init__(self, kubectl: str = "kubectl", *, runner: Runner = subprocess.run, timeout_s: float = 60,
                 ttl: float = 5.0):
        self.kubectl, self.runner, self.timeout_s, self.ttl = kubectl, runner, timeout_s, ttl
        self._hosts: dict[tuple[str, str], tuple[float, str | None]] = {}
        self._lock = threading.Lock()

    def _run(self, *args: str, stdin: str | None = None, missing_ok: bool = False) -> str | None:
        try:
            cp = self.runner([self.kubectl, *args], input=stdin, capture_output=True, text=True,
                             timeout=self.timeout_s, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise BrowserError(f"kubectl did not run: {exc}") from exc
        if cp.returncode != 0:
            if missing_ok and "NotFound" in (cp.stderr or ""):
                return None
            raise BrowserError((cp.stderr or "kubectl failed").strip()[:300])
        return cp.stdout or ""

    def _json(self, *args: str, missing_ok: bool = False) -> dict | None:
        out = self._run(*args, "-o", "json", missing_ok=missing_ok)
        try:
            return json.loads(out) if out is not None else None
        except ValueError as exc:
            raise BrowserError("kubectl returned something that is not JSON") from exc

    def _template(self, ns: str, spec: BrowserSpec) -> tuple[dict, dict]:
        """The app's own Deployment that mounts the profile volume, and the claim it names."""
        for dep in (self._json("get", "deployments", "-n", ns) or {}).get("items") or []:
            if PROFILE_LABEL in ((dep.get("metadata") or {}).get("labels") or {}):
                continue
            for vol in ((dep.get("spec") or {}).get("template") or {}).get("spec", {}).get("volumes") or []:
                claim = (vol.get("persistentVolumeClaim") or {}).get("claimName")
                if vol.get("name") == spec.profile_volume and claim:
                    return dep, self._json("get", "pvc", claim, "-n", ns, missing_ok=True) or {}
        raise BrowserError("the app's template Deployment was not found")

    def open(self, app_id: str, key: str, spec: BrowserSpec) -> None:
        """Create the person's objects if missing and run their pod. The claim is kept as it is."""
        ns = f"app-{app_id}"
        template, claim = self._template(ns, spec)
        objects = person_objects(app_id, key, spec, template, claim)
        if self._json("get", "pvc", profile_claim(key), "-n", ns, missing_ok=True) is not None:
            objects = objects[1:]  # never re-apply over an existing profile
        self._run("apply", "-n", ns, "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": objects}))

    def close(self, app_id: str, key: str) -> None:
        """Stop the person's pod. The profile claim stays."""
        self._run("scale", f"deployment/{workload_name(key)}", "--replicas=0", "-n", f"app-{app_id}", missing_ok=True)

    def reset(self, app_id: str, key: str) -> None:
        """Delete the person's pod and profile. Only browser.profile.reset calls this, after an owner approved."""
        ns = f"app-{app_id}"
        self._run("delete", "deployment", workload_name(key), "-n", ns, "--ignore-not-found", "--wait=true")
        self._run("delete", "pvc", profile_claim(key), "-n", ns, "--ignore-not-found", "--wait=true")
        with self._lock:
            self._hosts.pop((app_id, key), None)

    def service_host(self, app_id: str, key: str, port: int) -> str | None:
        """The ClusterIP of the person's Service when it exposes `port`, else None (cached `ttl` seconds)."""
        now = time.monotonic()
        with self._lock:
            hit = self._hosts.get((app_id, key))
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        try:
            svc = self._json("get", "service", workload_name(key), "-n", f"app-{app_id}", missing_ok=True) or {}
        except BrowserError:
            svc = {}
        s = svc.get("spec") or {}
        labels = (svc.get("metadata") or {}).get("labels") or {}
        ok = s.get("type", "ClusterIP") == "ClusterIP" and labels.get(PROFILE_LABEL) == key and \
            any(p.get("port") == port for p in s.get("ports") or [])
        ip = s.get("clusterIP") if ok and s.get("clusterIP") not in (None, "", "None") else None
        with self._lock:
            self._hosts[(app_id, key)] = (now, ip)
        return ip


class ResetHandler:
    """`browser.profile.reset` {app_id, person_key}: filed by the person, run only after an owner approves."""

    def __init__(self, profiles: BrowserProfiles, is_browser: Callable[[str], bool]):
        self.profiles, self.is_browser = profiles, is_browser

    def recheck(self, action: Action) -> str | None:
        p = action.params
        if not self.is_browser(str(p.get("app_id"))) or not KEY_RE.match(str(p.get("person_key"))):
            return "the browser app or profile no longer exists"
        return None

    def dispatch(self, action: Action) -> ExecResult:
        app_id, key = action.params["app_id"], action.params["person_key"]
        try:
            self.profiles.reset(app_id, key)
        except BrowserError as exc:
            return ExecResult("failed", f"the profile was not reset: {exc}")
        return ExecResult("succeeded", "the browser profile was erased; the next open starts a new one")
