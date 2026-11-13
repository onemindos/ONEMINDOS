# SPDX-License-Identifier: Apache-2.0
"""The few kubectl calls the migration kit makes on THIS box's k3s, after an approval.

Same pattern as executors.KubernetesExecutor: argv lists, no shell, documents on stdin (so
Secret data never appears in argv, a step, the ledger or the audit log), bounded timeouts.
Everything happens in the app's own namespace, app-<id>.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

Runner = Callable[..., subprocess.CompletedProcess]
FIELD_MANAGER = "onemind-migrate"


class BoxKubeError(RuntimeError):
    pass


class BoxKube:
    def __init__(self, kubectl: str = "kubectl", timeout_s: float = 120, runner: Runner = subprocess.run):
        self.kubectl = kubectl
        self.timeout_s = timeout_s
        self.runner = runner

    def _run(self, argv: list[str], stdin: str | None = None, timeout_s: float | None = None) -> str:
        try:
            cp = self.runner(
                [self.kubectl, *argv], input=stdin, capture_output=True, text=True,
                timeout=timeout_s or self.timeout_s, check=False,
            )
        except FileNotFoundError:
            raise BoxKubeError(f"{self.kubectl} not found") from None
        except subprocess.TimeoutExpired:
            raise BoxKubeError(f"kubectl {argv[0]} timed out") from None
        if cp.returncode != 0:
            raise BoxKubeError(f"kubectl {' '.join(argv[:3])} exited {cp.returncode}: {(cp.stderr or '')[-500:]}")
        return cp.stdout or ""

    def apply(self, namespace: str, doc: dict) -> None:
        """Server-side apply of one object (Secrets too: no last-applied annotation holds their data)."""
        self._run(
            ["apply", "--server-side", f"--field-manager={FIELD_MANAGER}", "--force-conflicts", "-n", namespace, "-f", "-"],
            stdin=json.dumps(doc),
        )

    def delete(self, namespace: str, kind: str, name: str) -> None:
        self._run(["delete", kind, name, "-n", namespace, "--ignore-not-found=true", "--wait=false"])

    def get(self, namespace: str, kind: str, name: str) -> dict | None:
        out = self._run(["get", kind, name, "-n", namespace, "-o", "json", "--ignore-not-found=true"])
        return json.loads(out) if out.strip() else None

    def pods(self, namespace: str, selector: str) -> list[dict]:
        out = self._run(["get", "pods", "-n", namespace, "-l", selector, "-o", "json"])
        return (json.loads(out or "{}").get("items") or []) if out.strip() else []

    def logs(self, namespace: str, job: str, tail: int = 200) -> str:
        return self._run(["logs", f"job/{job}", "-n", namespace, f"--tail={tail}"])

    def scale(self, namespace: str, kind: str, name: str, replicas: int) -> None:
        self._run(["scale", f"{kind.lower()}/{name}", "-n", namespace, f"--replicas={replicas}"])

    def rollout(self, namespace: str, kind: str, name: str, timeout_s: int) -> None:
        self._run(
            ["rollout", "status", f"{kind.lower()}/{name}", "-n", namespace, f"--timeout={timeout_s}s"],
            timeout_s=timeout_s + 30,
        )
