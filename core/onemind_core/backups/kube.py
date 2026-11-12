# SPDX-License-Identifier: Apache-2.0
"""The kubectl calls backups and databases need, with the gateway's own Kubernetes identity.

Every command is an argv list; stdin carries anything secret, so no password reaches a process
listing, the audit log or an action result. App hooks run as `kubectl exec` inside the app's own
container (contract §12.18): no host shell is ever involved.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger("onemind.backups")

Runner = Callable[..., subprocess.CompletedProcess]


class KubeError(Exception):
    pass


@dataclass(frozen=True)
class Workload:
    kind: str  # deployment | statefulset
    name: str
    replicas: int


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Kube:
    def __init__(self, kubectl: str = "kubectl", timeout_s: float = 300, runner: Runner = subprocess.run):
        self.kubectl = kubectl
        self.timeout_s = timeout_s
        self.runner = runner

    def run(self, args: Sequence[str], stdin: str | None = None, timeout: float | None = None) -> str:
        argv = [self.kubectl, *args]
        try:
            cp = self.runner(argv, input=stdin, capture_output=True, text=True,
                             timeout=timeout or self.timeout_s, check=False)
        except FileNotFoundError:
            raise KubeError(f"{self.kubectl} not found") from None
        except subprocess.TimeoutExpired:
            raise KubeError(f"kubectl {args[0]} timed out") from None
        if cp.returncode != 0:
            raise KubeError(f"kubectl {' '.join(args[:3])}: {(cp.stderr or '').strip()[-400:]}")
        return cp.stdout

    def get_json(self, *args: str) -> dict:
        return json.loads(self.run(["get", *args, "-o", "json"]) or "{}")

    def exists(self, *args: str) -> bool:
        return bool(self.run(["get", *args, "--ignore-not-found", "-o", "name"]).strip())

    def pvcs(self, namespace: str) -> list[dict]:
        """Bound claims of a namespace: [{claim, volume, storage_class}]."""
        out = []
        for item in self.get_json("pvc", "-n", namespace).get("items", []):
            if (item.get("status") or {}).get("phase") != "Bound":
                continue
            spec = item.get("spec") or {}
            out.append({"claim": item["metadata"]["name"], "volume": spec.get("volumeName"),
                        "storage_class": spec.get("storageClassName")})
        return out

    def pods(self, namespace: str) -> list[dict]:
        return self.get_json("pods", "-n", namespace).get("items", [])

    def running_pod(self, namespace: str, container: str | None = None) -> str:
        for p in self.pods(namespace):
            if (p.get("status") or {}).get("phase") != "Running" or p["metadata"].get("deletionTimestamp"):
                continue
            names = [c["name"] for c in (p.get("spec") or {}).get("containers", [])]
            if container is None or container in names:
                return p["metadata"]["name"]
        raise KubeError(f"no running pod in {namespace}" + (f" with container {container}" if container else ""))

    def exec(self, namespace: str, pod: str, command: Sequence[str], *, container: str | None = None,
             stdin: str | None = None, timeout: float | None = None) -> str:
        args = ["exec", "-n", namespace, pod]
        if stdin is not None:
            args.append("-i")
        if container:
            args += ["-c", container]
        return self.run([*args, "--", *command], stdin=stdin, timeout=timeout)

    def workloads(self, namespace: str) -> list[Workload]:
        out = []
        for kind in ("deployment", "statefulset"):
            for item in self.get_json(kind, "-n", namespace).get("items", []):
                out.append(Workload(kind, item["metadata"]["name"], int((item.get("spec") or {}).get("replicas", 1))))
        return out

    def scale(self, namespace: str, w: Workload, replicas: int) -> None:
        self.run(["scale", "-n", namespace, f"{w.kind}/{w.name}", f"--replicas={replicas}"])

    def wait_no_pods(self, namespace: str, deadline_s: float) -> None:
        end = time.monotonic() + deadline_s
        while time.monotonic() < end:
            if not self.pods(namespace):
                return
            time.sleep(2)
        raise KubeError(f"pods in {namespace} did not stop within {int(deadline_s)} s")

    def fresh_ready(self, namespace: str, since: datetime, expected: int) -> tuple[bool, dict]:
        """Fresh-signal readiness (BACKUPS.md §8): only pods created after `since` count.

        Kubernetes records creationTimestamp in whole seconds, so `since` is cut to its second:
        a pod started in the same second as the restart is fresh (the Lima run showed a pod at
        10:35:48Z for a restart at 10:35:48.38 that a sub-second comparison never counted). The
        caller has already waited for every old pod to go, so this admits no stale pod.
        """
        since = since.replace(microsecond=0)
        fresh = ready = 0
        for p in self.pods(namespace):
            md = p["metadata"]
            if md.get("deletionTimestamp") or _ts(md["creationTimestamp"]) < since:
                continue
            fresh += 1
            conds = {c["type"]: c["status"] for c in (p.get("status") or {}).get("conditions", [])}
            if conds.get("Ready") == "True":
                ready += 1
        return ready >= expected, {"fresh_pods": fresh, "ready": ready, "expected": expected}

    def apply(self, doc: dict | str, namespace: str | None = None, server_side: bool = False) -> None:
        args = ["apply"]
        if server_side:
            args += ["--server-side", "--field-manager=onemind-gateway", "--force-conflicts"]
        if namespace:
            args += ["-n", namespace]
        self.run([*args, "-f", "-"], stdin=doc if isinstance(doc, str) else json.dumps(doc))


class DryKube(Kube):
    """Used with the noop executor: records what it would run, changes nothing, reports nothing."""

    def __init__(self) -> None:
        super().__init__("kubectl")
        self.calls: list[list[str]] = []

    def run(self, args: Sequence[str], stdin: str | None = None, timeout: float | None = None) -> str:
        self.calls.append(list(args))
        return '{"items": []}' if "-o" in args and "json" in args else ""

    def exists(self, *args: str) -> bool:
        return False

    def wait_no_pods(self, namespace: str, deadline_s: float) -> None:
        return None

    def fresh_ready(self, namespace: str, since: datetime, expected: int) -> tuple[bool, dict]:
        return True, {"dry_run": True}
