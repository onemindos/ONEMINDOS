"""Executors: the only part of the gateway that changes the outside world, and only after approval.

- noop: marks success without touching anything (Mac / compose demos and tests). It records the
  steps it would have taken, including the agent Secret of §11.2 (never the token).
- kubernetes: `kubectl apply -k <app>/manifests -n app-<id>` to install,
  `kubectl delete -k ... -n app-<id>` plus the namespace to remove. For an app with
  `spec.agent.principal` it creates the agent Secret before the manifests (so the app's pods
  start with it) and deletes it first on removal. The app's declared `spec.secrets` (values from
  the secret store, appsecrets/) are applied the same way, server-side, before the manifests;
  `app.configure` re-applies them and restarts the app's Deployments and StatefulSets.

Outcome rules:
- exit code 0                      -> succeeded
- non-zero exit / kubectl missing  -> failed
- timeout or unexpected exception  -> outcome_unknown (we cannot know what was applied; the
  ledger never re-dispatches by itself, a person decides what to do next)
"""

from __future__ import annotations

import base64
import json
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


@dataclass(frozen=True)
class AgentSecret:
    """§11.2: the Secret that hands an app its agent principal.

    For app.install, gateway_url and token are set. For app.remove only the name matters (the
    Secret is deleted). The token never appears in a step, result or log line.
    """

    name: str
    principal_id: str
    gateway_url: str | None = None
    token: str | None = field(default=None, repr=False)

    def manifest(self, namespace: str, app_id: str) -> str:
        if not self.token or not self.gateway_url:
            raise ValueError("an agent Secret to create needs gateway_url and token")
        doc = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": self.name,
                "namespace": namespace,
                "labels": {"onemind.io/app": app_id, "onemind.io/agent-principal": "true"},
                "annotations": {"onemind.io/principal": self.principal_id},
            },
            # data (base64), not stringData: the Secret is applied server-side (see plan()), and
            # data round-trips exactly through server-side apply's field ownership.
            "data": {"ONEMIND_GATEWAY_URL": _b64(self.gateway_url), "ONEMIND_AGENT_TOKEN": _b64(self.token)},
        }
        return json.dumps(doc)  # JSON is YAML; no quoting surprises in the token or URL


@dataclass(frozen=True)
class AppSecret:
    """One declared `spec.secrets` Secret with its current values (DEPLOYMENTS.md §7).

    The values never appear in a step, result, repr or log line: steps list the key names only,
    and kubectl output is scrubbed of every value (raw and base64) before it is recorded.
    """

    name: str
    data: dict[str, str] = field(default_factory=dict, repr=False)

    def keys(self) -> list[str]:
        return sorted(self.data)

    def manifest(self, namespace: str, app_id: str) -> str:
        doc = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": self.name,
                "namespace": namespace,
                "labels": {"onemind.io/app": app_id, "onemind.io/app-secret": "true"},
            },
            # Server-side apply with one field manager: a key this manager applied before and no
            # longer sends (a cleared value) is removed from the Secret by the API server.
            "data": {k: _b64(v) for k, v in sorted(self.data.items())},
        }
        return json.dumps(doc)


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _ssa(kubectl: str, ns: str) -> list[str]:
    # Server-side apply: a client-side `kubectl apply` would copy the whole object, values
    # included, into the kubectl.kubernetes.io/last-applied-configuration annotation, where tools
    # that mask Secret data still show it in plain text.
    return [kubectl, "apply", "--server-side", "--field-manager=onemind-gateway", "--force-conflicts", "-n", ns, "-f", "-"]


# `kubectl rollout restart` with no matching workload exits 1 with this text; for an app made only
# of Jobs or CronJobs there is nothing to restart, which is not a failure.
NOTHING_TO_RESTART = "no objects passed to restart"


class Executor:
    """Runs an approved action. `secrets` is passed only when the app declares spec.secrets, so an
    executor written before the secret store keeps working for every other app."""

    name = "base"

    def run(
        self, action_type: str, app: AppEntry, agent: AgentSecret | None = None, secrets: Sequence[AppSecret] = ()
    ) -> ExecResult:  # pragma: no cover
        raise NotImplementedError


class NoopExecutor(Executor):
    name = "noop"

    def run(
        self, action_type: str, app: AppEntry, agent: AgentSecret | None = None, secrets: Sequence[AppSecret] = ()
    ) -> ExecResult:
        steps: list[dict] = []
        ns = f"app-{app.id}"
        if agent is not None and action_type == "app.install":
            steps.append({
                "would": f"create Secret {agent.name} in {ns}",
                "keys": ["ONEMIND_GATEWAY_URL", "ONEMIND_AGENT_TOKEN"],
                "principal": agent.principal_id,
            })
        if action_type in ("app.install", "app.configure"):
            for s in secrets:
                steps.append({"would": f"apply Secret {s.name} in {ns} (server-side)", "keys": s.keys()})
        if action_type == "app.configure":
            steps.append({"would": f"restart the Deployments and StatefulSets in {ns}"})
        if action_type == "app.install":
            steps.append({"would": f"apply manifests of {app.id} in {ns}"})
        elif action_type == "app.remove":
            if agent is not None:
                steps.append({"would": f"delete Secret {agent.name} in {ns}", "principal": agent.principal_id})
            steps.append({"would": f"delete manifests of {app.id} and namespace {ns}"})
        return ExecResult("succeeded", f"noop executor: {action_type} {app.id} recorded, nothing changed", steps)


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

    def plan(
        self, action_type: str, app: AppEntry, agent: AgentSecret | None = None, secrets: Sequence[AppSecret] = ()
    ) -> list[tuple[list[str], str | None]]:
        """The exact commands, as (argv, stdin). Public so tests and the README can show them.

        stdin is never recorded in a step, so the agent token and secret values stay out of the
        ledger and audit.
        """
        ns = f"app-{app.id}"
        mdir = str(app.manifests_dir)
        k = self.kubectl
        if action_type == "app.install":
            ns_doc = (
                "apiVersion: v1\nkind: Namespace\nmetadata:\n"
                f"  name: {ns}\n  labels:\n    onemind.io/app: {app.id}\n"
            )
            steps = [([k, "apply", "-f", "-"], ns_doc)]
            if agent is not None:  # before the manifests, so the pods start with the Secret
                steps.append((_ssa(k, ns), agent.manifest(ns, app.id)))
            steps += [(_ssa(k, ns), s.manifest(ns, app.id)) for s in secrets]
            steps.append(([k, "apply", "-k", mdir, "-n", ns], None))
            return steps
        if action_type == "app.configure":
            # envFrom and env values are read at container start, so the new values reach the app
            # only through a restart of its workloads.
            return [(_ssa(k, ns), s.manifest(ns, app.id)) for s in secrets] + [
                ([k, "rollout", "restart", "deployment,statefulset", "-n", ns], None),
            ]
        if action_type == "app.remove":
            first = []
            if agent is not None:
                first = [([k, "delete", "secret", agent.name, "-n", ns, "--ignore-not-found=true"], None)]
            return first + [
                ([k, "delete", "-k", mdir, "-n", ns, "--ignore-not-found=true"], None),
                ([k, "delete", "namespace", ns, "--ignore-not-found=true"], None),
            ]
        raise ValueError(f"unsupported action type {action_type}")

    def run(
        self, action_type: str, app: AppEntry, agent: AgentSecret | None = None, secrets: Sequence[AppSecret] = ()
    ) -> ExecResult:
        steps: list[dict] = []
        try:
            plan = self.plan(action_type, app, agent, secrets)
        except ValueError as exc:
            return ExecResult("failed", str(exc), steps)
        hidden = _sensitive(agent, secrets)
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
                step["stderr"] = _scrub(_tail(exc.stderr), hidden)
                return ExecResult("outcome_unknown", f"kubectl timed out after {self.timeout_s}s", steps)
            step["returncode"] = cp.returncode
            step["stdout"] = _scrub(_tail(cp.stdout), hidden)
            step["stderr"] = _scrub(_tail(cp.stderr), hidden)
            if cp.returncode != 0 and argv[1:3] == ["rollout", "restart"] and NOTHING_TO_RESTART in (cp.stderr or ""):
                step["note"] = "no Deployment or StatefulSet to restart"
                continue
            if cp.returncode != 0:
                return ExecResult("failed", f"kubectl exited {cp.returncode}", steps)
        return ExecResult("succeeded", f"{action_type} {app.id} applied to namespace app-{app.id}", steps)


def _sensitive(agent: AgentSecret | None, secrets: Sequence[AppSecret]) -> list[str]:
    values = [agent.token] if agent is not None and agent.token else []
    values += [v for s in secrets for v in s.data.values() if v]
    # Longest first, so a value that contains another is redacted whole.
    return sorted({form for v in values for form in (v, _b64(v))}, key=len, reverse=True)


def _scrub(text: str, hidden: Sequence[str]) -> str:
    # kubectl does not echo Secret data, but an error message must never carry a value anyway.
    for form in hidden:
        text = text.replace(form, "[redacted]")
    return text


def _display(argv: Sequence[str], app: AppEntry) -> list[str]:
    # Rewrite the apps folder prefix, so the audit log and API never leak host paths.
    root = str(app.dir.resolve().parent)
    return [a.replace(root, "$ONEMIND_APPS_DIR", 1) if a.startswith(root) else a for a in argv]


def make_executor(name: str, kubectl: str = "kubectl", timeout_s: float = 300) -> Executor:
    if name == "kubernetes":
        return KubernetesExecutor(kubectl=kubectl, timeout_s=timeout_s)
    return NoopExecutor()
