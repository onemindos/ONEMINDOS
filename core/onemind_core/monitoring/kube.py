# SPDX-License-Identifier: Apache-2.0
"""Read-only access to the Kubernetes API for monitoring (contract §12.15).

Uses `kubectl` like the executor does (the same binary and kubeconfig), with read verbs only:
`get pods|events -o json`, `logs`, and `get --raw` on the metrics-server API. Every call has a
timeout and a size bound; any failure returns None (the caller reports "unknown"), so a missing
cluster never breaks the gateway. Pods are always read from one app's namespace `app-<id>`.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

log = logging.getLogger("onemind.monitoring.kube")

MAX_JSON = 8 * 1024 * 1024
MAX_LOG_BYTES = 2 * 1024 * 1024

Runner = Callable[..., subprocess.CompletedProcess]


def parse_cpu(q: str | None) -> float | None:
    """Kubernetes CPU quantity -> millicores ("250m", "1", "123456789n", "15u")."""
    if not q:
        return None
    try:
        for suffix, div in (("n", 1e6), ("u", 1e3), ("m", 1.0)):
            if q.endswith(suffix):
                return float(q[:-1]) / div
        return float(q) * 1000
    except ValueError:
        return None


def parse_mem(q: str | None) -> float | None:
    """Kubernetes memory quantity -> MiB."""
    if not q:
        return None
    units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "Ti": 1024 ** 2, "k": 1e3 / 2 ** 20, "M": 1e6 / 2 ** 20,
             "G": 1e9 / 2 ** 20}
    try:
        for suffix, mul in sorted(units.items(), key=lambda kv: -len(kv[0])):
            if q.endswith(suffix):
                return float(q[: -len(suffix)]) * mul
        return float(q) / 2 ** 20
    except ValueError:
        return None


class KubeReader:
    def __init__(self, kubectl: str = "kubectl", timeout_s: float = 10, runner: Runner = subprocess.run,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen):
        self.kubectl = kubectl
        self.timeout_s = timeout_s
        self.runner = runner
        self.popen = popen

    def _run(self, args: list[str], limit: int) -> str | None:
        try:
            cp = self.runner([self.kubectl, *args], capture_output=True, text=True,
                             timeout=self.timeout_s, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("kubectl %s failed: %s", args[0], exc.__class__.__name__)
            return None
        if cp.returncode != 0:
            return None
        return (cp.stdout or "")[:limit]

    def _json(self, args: list[str]) -> dict | None:
        out = self._run(args, MAX_JSON)
        if out is None:
            return None
        try:
            doc = json.loads(out)
        except ValueError:
            return None
        return doc if isinstance(doc, dict) else None

    def pods(self, namespace: str) -> list[dict] | None:
        doc = self._json(["get", "pods", "-n", namespace, "-o", "json"])
        return None if doc is None else list(doc.get("items") or [])

    def events(self, namespace: str, limit: int = 10) -> list[dict] | None:
        doc = self._json(["get", "events", "-n", namespace, "-o", "json"])
        if doc is None:
            return None
        out = []
        for e in doc.get("items") or []:
            obj = e.get("involvedObject") or {}
            out.append({
                "type": e.get("type"), "reason": e.get("reason"), "message": (e.get("message") or "")[:300],
                "object": f"{obj.get('kind', '')}/{obj.get('name', '')}", "count": e.get("count") or 1,
                "last_seen": e.get("lastTimestamp") or e.get("eventTime") or (e.get("metadata") or {}).get("creationTimestamp"),
            })
        out.sort(key=lambda x: x["last_seen"] or "", reverse=True)
        return out[:limit]

    def logs(self, namespace: str, pod: str, container: str | None, tail: int, since_s: int | None) -> list[str] | None:
        args = ["logs", pod, "-n", namespace, f"--tail={tail}", f"--limit-bytes={MAX_LOG_BYTES}"]
        args += ["-c", container] if container else ["--all-containers=true", "--prefix=true"]
        if since_s:
            args.append(f"--since={since_s}s")
        out = self._run(args, MAX_LOG_BYTES)
        return None if out is None else out.splitlines()[-tail:]

    @contextmanager
    def follow(self, namespace: str, pod: str, container: str | None, tail: int,
               max_s: float) -> Iterator[Iterator[str]]:
        """`kubectl logs -f`: yields an iterator of lines; the process is killed after max_s or on exit."""
        args = [self.kubectl, "logs", "-f", pod, "-n", namespace, f"--tail={tail}"]
        args += ["-c", container] if container else ["--all-containers=true", "--prefix=true"]
        proc = self.popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        timer = threading.Timer(max_s, proc.kill)
        timer.daemon = True
        timer.start()
        try:
            yield (line.rstrip("\n") for line in proc.stdout)
        finally:
            timer.cancel()
            proc.kill()
            threading.Thread(target=proc.wait, daemon=True).start()

    def pod_metrics(self, namespace: str) -> dict[str, dict[str, tuple[float | None, float | None]]] | None:
        doc = self._json(["get", "--raw", f"/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods"])
        if doc is None:
            return None
        return {
            (p.get("metadata") or {}).get("name", ""): {
                c.get("name", ""): (parse_cpu((c.get("usage") or {}).get("cpu")), parse_mem((c.get("usage") or {}).get("memory")))
                for c in p.get("containers") or []
            }
            for p in doc.get("items") or []
        }

    def node_metrics(self) -> dict[str, float] | None:
        """k8s node name -> CPU millicores in use (metrics-server)."""
        doc = self._json(["get", "--raw", "/apis/metrics.k8s.io/v1beta1/nodes"])
        if doc is None:
            return None
        out = {}
        for n in doc.get("items") or []:
            cpu = parse_cpu((n.get("usage") or {}).get("cpu"))
            if cpu is not None:
                out[(n.get("metadata") or {}).get("name", "")] = cpu
        return out
