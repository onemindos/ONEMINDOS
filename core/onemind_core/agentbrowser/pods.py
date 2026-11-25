# SPDX-License-Identifier: Apache-2.0
"""One fresh browser pod per agent session, and the NetworkPolicy that boxes it in (#694).

Objects, in namespace `onemind-agent-browser` (Pod Security `restricted`):
- NetworkPolicy `default-deny` (every pod, both directions) and `agent-browser`: in, only the hub's
  host addresses on the control port; out, only the hub's host addresses on the egress proxy port.
  No DNS, no pod-to-pod, no internet: every page load goes through the gateway's proxy (proxy.py),
  which checks the agent's allowlist. Playwright MCP and browser-use both say their own domain
  filters are not a security boundary, so the boundary is the network, not the browser.
- Secret `ab-<sid>`: the control token and the proxy credential of this session only.
- Pod `ab-<sid>`: the pinned browser image, a fresh in-memory profile (emptyDir medium Memory, the
  only volumes it has), no service account token, no host anything, no CDP port: only the control
  port is declared, and Chromium's DevTools stay on a pipe inside the pod. activeDeadlineSeconds is
  the session's lifetime, so Kubernetes ends a forgotten session even if the gateway is gone.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

SESSION_LABEL = "onemind.io/agent-browser-session"
MANAGED = {"onemind.io/managed-by": "onemind-gateway", "onemind.io/component": "agent-browser"}
Runner = Callable[..., subprocess.CompletedProcess]


class PodError(Exception):
    """kubectl refused or did not run."""


def name_of(session_id: str) -> str:
    return "ab-" + session_id.removeprefix("abs_")[:40]


def _cidr(addr: str) -> str:
    return addr if "/" in addr else addr + ("/128" if ":" in addr else "/32")


def namespace_doc(ns: str) -> dict:
    return {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns, "labels": {
        **MANAGED, "pod-security.kubernetes.io/enforce": "restricted",
        "pod-security.kubernetes.io/enforce-version": "latest"}}}


def policy_docs(ns: str, hub: list[str], control_port: int, proxy_port: int) -> list[dict]:
    """Default deny, then the two holes. With no hub address known the pods stay fully closed."""
    deny = {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"name": "default-deny", "namespace": ns, "labels": MANAGED},
            "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}}
    blocks = [{"ipBlock": {"cidr": _cidr(a)}} for a in hub]
    allow = {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
             "metadata": {"name": "agent-browser", "namespace": ns, "labels": MANAGED},
             "spec": {"podSelector": {"matchExpressions": [{"key": SESSION_LABEL, "operator": "Exists"}]},
                      "policyTypes": ["Ingress", "Egress"],
                      "ingress": [{"from": blocks, "ports": [{"protocol": "TCP", "port": control_port}]}] if blocks else [],
                      "egress": [{"to": blocks, "ports": [{"protocol": "TCP", "port": proxy_port}]}] if blocks else []}}
    return [deny, allow]


def session_docs(ns: str, session_id: str, *, image: str, control_token: str, proxy_url: str,
                 control_port: int, lifetime_s: int, max_pages: int) -> list[dict]:
    name = name_of(session_id)
    labels = {**MANAGED, SESSION_LABEL: name}
    secret = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
              "metadata": {"name": name, "namespace": ns, "labels": labels},
              "stringData": {"ONEMIND_AB_CONTROL_TOKEN": control_token, "HTTPS_PROXY": proxy_url}}
    memory = {"medium": "Memory", "sizeLimit": "256Mi"}
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns, "labels": labels},
           "spec": {
               "restartPolicy": "Never", "activeDeadlineSeconds": lifetime_s,
               "automountServiceAccountToken": False, "enableServiceLinks": False,
               "hostNetwork": False, "hostPID": False, "hostIPC": False,
               "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001,
                                   "seccompProfile": {"type": "RuntimeDefault"}},
               "containers": [{
                   "name": "browser", "image": image, "imagePullPolicy": "IfNotPresent",
                   "ports": [{"name": "control", "containerPort": control_port, "protocol": "TCP"}],
                   "envFrom": [{"secretRef": {"name": name}}],
                   "env": [{"name": "HOME", "value": "/profile"},
                           {"name": "ONEMIND_AB_CONTROL_PORT", "value": str(control_port)},
                           {"name": "ONEMIND_AB_MAX_PAGES", "value": str(max_pages)},
                           {"name": "NO_PROXY", "value": ""}],
                   "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                       "capabilities": {"drop": ["ALL"]}},
                   "resources": {"requests": {"cpu": "250m", "memory": "512Mi"},
                                 "limits": {"cpu": "1", "memory": "1536Mi"}},
                   "volumeMounts": [{"name": "profile", "mountPath": "/profile"},
                                    {"name": "tmp", "mountPath": "/tmp"}],
               }],
               "volumes": [{"name": "profile", "emptyDir": dict(memory)}, {"name": "tmp", "emptyDir": dict(memory)}],
           }}
    return [secret, pod]


def isolation_problems(pod: dict) -> list[str]:
    """Why a rendered pod is not a fresh, sealed browser (empty when it is). Checked before apply."""
    spec = pod.get("spec") or {}
    out = []
    for v in spec.get("volumes") or []:
        if set(v) != {"name", "emptyDir"} or (v.get("emptyDir") or {}).get("medium") != "Memory":
            out.append(f"volume {v.get('name')} is not an in-memory emptyDir")
    for key in ("hostNetwork", "hostPID", "hostIPC", "automountServiceAccountToken"):
        if spec.get(key):
            out.append(f"{key} is on")
    for c in spec.get("containers") or []:
        ports = [p.get("containerPort") for p in c.get("ports") or []]
        if len(ports) != 1:
            out.append(f"container {c.get('name')} must declare only the control port")
        if any("hostPort" in p for p in c.get("ports") or []):
            out.append("a host port is declared")
    return out


class BrowserPods:
    """The session pods, through kubectl (the same runner pattern as browsers.py)."""

    def __init__(self, kubectl: str, ns: str, *, runner: Runner = subprocess.run, timeout_s: float = 30):
        self.kubectl, self.ns, self.runner, self.timeout_s = kubectl, ns, runner, timeout_s

    def _run(self, *args: str, stdin: str | None = None) -> str:
        try:
            cp = self.runner([self.kubectl, *args], input=stdin, capture_output=True, text=True,
                             timeout=self.timeout_s, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PodError(f"kubectl did not run: {exc.__class__.__name__}") from exc
        if cp.returncode != 0:
            raise PodError((cp.stderr or "kubectl failed").strip()[:300])
        return cp.stdout or ""

    def start(self, docs: list[dict], base: list[dict]) -> None:
        for d in docs:
            if d["kind"] == "Pod" and (problems := isolation_problems(d)):
                raise PodError("refused to start an unsealed browser pod: " + "; ".join(problems))
        self._run("apply", "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": base + docs}))

    def stop(self, session_id: str) -> None:
        self._run("delete", "pod,secret", "-n", self.ns, "-l", f"{SESSION_LABEL}={name_of(session_id)}",
                  "--ignore-not-found", "--wait=false")

    def stop_all(self) -> None:
        self._run("delete", "pod,secret", "-n", self.ns, "-l", SESSION_LABEL, "--ignore-not-found", "--wait=false")

    def address(self, session_id: str) -> str | None:
        """The pod's IP once it runs, else None."""
        out = self._run("get", "pod", name_of(session_id), "-n", self.ns, "-o", "json", "--ignore-not-found")
        if not out.strip():
            return None
        try:
            pod: dict[str, Any] = json.loads(out)
        except ValueError as exc:
            raise PodError("kubectl returned something that is not JSON") from exc
        status = pod.get("status") or {}
        return status.get("podIP") if status.get("phase") == "Running" else None
