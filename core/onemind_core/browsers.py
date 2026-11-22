# SPDX-License-Identifier: Apache-2.0
"""Browser apps in a desktop window, one profile per person (#692).

A Market browser app (Neko, apps/firefox and apps/chromium; #593) declares `spec.browser` in its
manifest. The app's own Deployment is only a template: it runs no replica and its Service is never
proxied, so there is no shared profile. Each signed-in person gets, in the app's namespace:
- PersistentVolumeClaim `profile-<key>`, mounted where the template mounts `spec.browser.profileVolume`;
- Secret `browser-<key>`: the person's own Neko logins (a member password they are shown, and an
  admin password nobody is shown), in place of the app's shared `<app>-credentials`;
- Deployment and ClusterIP Service `browser-<key>` (no hostPort, no NodePort, no host network).

`<key>` is person_key(box secret, person id): an HMAC under a random key file kept next to the
audit log, so no name or id of a person appears in a cluster object or an app host name, and nobody
who knows a person id can work out their key. The app's NetworkPolicies (policy.network_policies,
browser=True) let into a person's pod only the gateway on the web port: not another pod in the
namespace, so one person's browser cannot open another's Service. The person reaches their pod only through the gateway proxy at
`<app>--<key>.<box domain>` (proxy.py), which compares the key with the signed-in person and
refuses any other (403). The claim is created when the person first opens the browser and is
deleted only by `browser.profile.reset` after an owner approves it (or with the app's namespace, by
an owner-approved app.remove). Closing the window scales the pod to zero and keeps the claim.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .catalog import APP_ID_RE
from .executors import ExecResult
from .ledger import Action
from .policy import BROWSER_PROFILE_LABEL

PROFILE_LABEL = BROWSER_PROFILE_LABEL
ADMIN_PASSWORD_ENV_SUFFIX = "ADMIN_PASSWORD"
HOST_SEP = "--"
KEY_LEN = 16
KEY_RE = re.compile(r"^[0-9a-f]{16}$")
RESET_ACTION = "browser.profile.reset"
DNS_LABEL_MAX = 63
_VOLUME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class BrowserError(Exception):
    """The cluster refused or the app's template cannot carry a per-person profile."""


def person_key(secret: bytes, person_id: str) -> str:
    """The stable, one-way key of a person's browser profile (16 hex characters).

    HMAC-SHA256 under the box's secret: without the secret a key cannot be computed from an id.
    """
    if len(secret) < 32:
        raise BrowserError("the browser key secret is too short")
    return hmac.new(secret, b"onemind-browser-profile\0" + person_id.encode(), hashlib.sha256).hexdigest()[:KEY_LEN]


def load_secret(path: Path) -> bytes:
    """The box's browser key secret (32 random bytes, hex, file mode 0600), created on first use.

    Written to a private temp file and hard-linked into place, so a concurrent reader never sees a
    half-written key and nobody replaces a key that already named profiles (as CredentialStore).
    """
    try:
        return bytes.fromhex(path.read_text().strip())
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex())
    try:
        os.link(tmp, path)
    except FileExistsError:
        return bytes.fromhex(path.read_text().strip())
    finally:
        tmp.unlink(missing_ok=True)
    return key


def workload_name(key: str) -> str:
    return f"browser-{key}"


def profile_claim(key: str) -> str:
    return f"profile-{key}"


def login_secret(key: str) -> str:
    return f"browser-{key}"


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
    _own_logins(app_id, key, pod)
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


LOGIN_KEYS = ("PASSWORD", "ADMIN_PASSWORD")


def _own_logins(app_id: str, key: str, pod: dict) -> None:
    """Point the pod's logins at the person's own Secret instead of the app's shared `<app>-credentials`.

    An env var whose name ends in ADMIN_PASSWORD gets the person's admin password (shown to nobody),
    every other reference to the shared login gets their member password. Refuses (BrowserError) a
    template that would still hand the shared login to the pod: as envFrom or as a volume.
    """
    shared, own = f"{app_id}-credentials", login_secret(key)
    for c in [*(pod.get("containers") or []), *(pod.get("initContainers") or [])]:
        for src in c.get("envFrom") or []:
            if (src.get("secretRef") or {}).get("name") == shared:
                raise BrowserError("the template loads the shared login with envFrom")
        for env in c.get("env") or []:
            ref = (env.get("valueFrom") or {}).get("secretKeyRef")
            if not isinstance(ref, dict) or ref.get("name") != shared:
                continue
            want = "ADMIN_PASSWORD" if str(env.get("name", "")).endswith(ADMIN_PASSWORD_ENV_SUFFIX) else ref.get("key")
            if want not in LOGIN_KEYS:
                raise BrowserError(f"the template reads {ref.get('key')!r} of the shared login")
            ref.update({"name": own, "key": want})
    for vol in pod.get("volumes") or []:
        names = [(vol.get("secret") or {}).get("secretName")]
        names += [(p.get("secret") or {}).get("name") for p in (vol.get("projected") or {}).get("sources") or []]
        if shared in names:
            raise BrowserError("the template mounts the shared login as a volume")


def login_object(app_id: str, key: str) -> dict:
    """The person's own Neko logins: two fresh random passwords. Created once, never re-applied."""
    data = {k: base64.b64encode(secrets.token_urlsafe(24).encode()).decode() for k in LOGIN_KEYS}
    return {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
            "metadata": {"name": login_secret(key), "labels": _labels(app_id, key)}, "data": data}


Runner = Callable[..., subprocess.CompletedProcess]


class BrowserProfiles:
    """The per-person browser objects of installed browser apps, through kubectl."""

    def __init__(self, kubectl: str = "kubectl", *, secret: bytes, runner: Runner = subprocess.run,
                 timeout_s: float = 60, ttl: float = 5.0):
        """secret: the box's browser key secret (load_secret); every person key is an HMAC under it."""
        if len(secret) < 32:
            raise BrowserError("the browser key secret is too short")
        self.kubectl, self.runner, self.timeout_s, self.ttl = kubectl, runner, timeout_s, ttl
        self._secret = secret
        self._hosts: dict[tuple[str, str], tuple[float, str | None]] = {}
        self._lock = threading.Lock()

    def key_of(self, person_id: str) -> str:
        """The profile key of a person on this box."""
        return person_key(self._secret, person_id)

    def _run(self, *args: str, stdin: str | None = None, missing_ok: bool = False,
             exists_ok: bool = False) -> str | None:
        try:
            cp = self.runner([self.kubectl, *args], input=stdin, capture_output=True, text=True,
                             timeout=self.timeout_s, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise BrowserError(f"kubectl did not run: {exc}") from exc
        if cp.returncode != 0:
            if missing_ok and "NotFound" in (cp.stderr or ""):
                return None
            if exists_ok and "AlreadyExists" in (cp.stderr or ""):
                return ""
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

    def open(self, app_id: str, key: str, spec: BrowserSpec) -> str:
        """Create the person's objects if missing and run their pod. The claim is kept as it is.

        Answers the person's own member password (from their Secret), for the browser's sign-in.
        """
        ns = f"app-{app_id}"
        template, claim = self._template(ns, spec)
        objects = person_objects(app_id, key, spec, template, claim)
        if self._json("get", "pvc", profile_claim(key), "-n", ns, missing_ok=True) is not None:
            objects = objects[1:]  # never re-apply over an existing profile
        # `create`, not `apply`: apply would copy the passwords into the last-applied annotation.
        # Values go on stdin only. An existing Secret is kept (AlreadyExists), so logins stay stable.
        self._run("create", "-n", ns, "-f", "-", stdin=json.dumps(login_object(app_id, key)), exists_ok=True)
        self._run("apply", "-n", ns, "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": objects}))
        return self._password(ns, key)

    def _password(self, ns: str, key: str) -> str:
        sec = self._json("get", "secret", login_secret(key), "-n", ns, missing_ok=True) or {}
        try:
            return base64.b64decode(((sec.get("data") or {})["PASSWORD"]), validate=True).decode()
        except (KeyError, TypeError, ValueError) as exc:
            raise BrowserError("the person's browser login was not found") from exc

    def close(self, app_id: str, key: str) -> None:
        """Stop the person's pod. The profile claim stays."""
        self._run("scale", f"deployment/{workload_name(key)}", "--replicas=0", "-n", f"app-{app_id}", missing_ok=True)

    def reset(self, app_id: str, key: str) -> None:
        """Delete the person's pod and profile. Only browser.profile.reset calls this, after an owner approved."""
        ns = f"app-{app_id}"
        self._run("delete", "deployment", workload_name(key), "-n", ns, "--ignore-not-found", "--wait=true")
        self._run("delete", "pvc", profile_claim(key), "-n", ns, "--ignore-not-found", "--wait=true")
        self._run("delete", "secret", login_secret(key), "-n", ns, "--ignore-not-found", "--wait=true")
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
