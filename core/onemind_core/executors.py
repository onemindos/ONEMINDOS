"""Executors: the only part of the gateway that changes the outside world, and only after approval.

- noop: marks success without touching anything (Mac / compose demos and tests).
- kubernetes: `kubectl apply -k <app>/manifests -n app-<id>` to install,
  `kubectl delete -k ... -n app-<id>` plus the namespace to remove.

Outcome rules:
- exit code 0                      -> succeeded
- non-zero exit / kubectl missing  -> failed
- timeout or unexpected exception  -> outcome_unknown (we cannot know what was applied; the
  ledger never re-dispatches by itself, a person decides what to do next)
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .catalog import AppEntry

log = logging.getLogger("onemind.executor")


@dataclass
class ExecResult:
    outcome: str  # succeeded | failed | outcome_unknown
    message: str
    steps: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"outcome": self.outcome, "message": self.message, "steps": self.steps}


class Executor:
    name = "base"

    def run(self, action_type: str, app: AppEntry) -> ExecResult:  # pragma: no cover
        raise NotImplementedError


class NoopExecutor(Executor):
    name = "noop"

    def run(self, action_type: str, app: AppEntry) -> ExecResult:
        return ExecResult("succeeded", f"noop executor: {action_type} {app.id} recorded, nothing changed")


Runner = Callable[..., subprocess.CompletedProcess]


def _tail(text: str | bytes | None, limit: int = 2000) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return text[-limit:]


class KubernetesExecutor(Executor):
    name = "kubernetes"

    def __init__(self, kubectl: str = "kubectl", timeout_s: float = 300, runner: Runner = subprocess.run):
        self.kubectl = kubectl
        self.timeout_s = timeout_s
        self.runner = runner

    def plan(self, action_type: str, app: AppEntry) -> list[tuple[list[str], str | None]]:
        """The exact commands, as (argv, stdin). Public so tests and the README can show them."""
        ns = f"app-{app.id}"
        mdir = str(app.manifests_dir)
        k = self.kubectl
        if action_type == "app.install":
            ns_doc = (
                "apiVersion: v1\nkind: Namespace\nmetadata:\n"
                f"  name: {ns}\n  labels:\n    onemind.io/app: {app.id}\n"
            )
            return [
                ([k, "apply", "-f", "-"], ns_doc),
                ([k, "apply", "-k", mdir, "-n", ns], None),
            ]
        if action_type == "app.remove":
            return [
                ([k, "delete", "-k", mdir, "-n", ns, "--ignore-not-found=true"], None),
                ([k, "delete", "namespace", ns, "--ignore-not-found=true"], None),
            ]
        raise ValueError(f"unsupported action type {action_type}")

    def run(self, action_type: str, app: AppEntry) -> ExecResult:
        steps: list[dict] = []
        try:
            plan = self.plan(action_type, app)
        except ValueError as exc:
            return ExecResult("failed", str(exc), steps)
        for argv, stdin in plan:
            step = {"argv": _display(argv, app)}
            steps.append(step)
            try:
                cp = self.runner(
                    argv, input=stdin, capture_output=True, text=True, timeout=self.timeout_s, check=False
                )
            except FileNotFoundError:
                step["error"] = "kubectl not found"
                return ExecResult("failed", f"{self.kubectl} not found on PATH", steps)
            except subprocess.TimeoutExpired as exc:
                step["error"] = f"timeout after {self.timeout_s}s"
                step["stderr"] = _tail(exc.stderr)
                return ExecResult("outcome_unknown", f"kubectl timed out after {self.timeout_s}s", steps)
            step["returncode"] = cp.returncode
            step["stdout"] = _tail(cp.stdout)
            step["stderr"] = _tail(cp.stderr)
            if cp.returncode != 0:
                return ExecResult("failed", f"kubectl exited {cp.returncode}", steps)
        return ExecResult("succeeded", f"{action_type} {app.id} applied to namespace app-{app.id}", steps)


def _display(argv: Sequence[str], app: AppEntry) -> list[str]:
    # Rewrite the apps folder prefix, so the audit log and API never leak host paths.
    root = str(app.dir.resolve().parent)
    return [a.replace(root, "$ONEMIND_APPS_DIR", 1) if a.startswith(root) else a for a in argv]


def make_executor(name: str, kubectl: str = "kubectl", timeout_s: float = 300) -> Executor:
    if name == "kubernetes":
        return KubernetesExecutor(kubectl=kubectl, timeout_s=timeout_s)
    return NoopExecutor()
