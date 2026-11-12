"""Executors: the only part of the gateway that changes the outside world, and only after approval.

- noop: marks success without touching anything (Mac / compose demos and tests). It records the
  steps it would have taken, including the agent Secret of §11.2 (never the token).
- kubernetes: renders `kubectl kustomize <app>/manifests`, checks every object against the
  install sandbox's rule file (policy.py), then applies the namespace (Pod Security labels), the
  gateway's RoleBinding, the default-deny NetworkPolicy and the checked render with
  `kubectl apply -f -`; removal deletes the namespace. For an app with `spec.agent.principal` it
  creates the agent Secret before the manifests (so the app's pods start with it) and deletes it
  first on removal.

Outcome rules:
- install sandbox refusal          -> failed, with `violations` in the result (kubectl never ran)
- exit code 0                      -> succeeded
- non-zero exit / kubectl missing  -> failed
- timeout or unexpected exception  -> outcome_unknown (we cannot know what was applied; the
  ledger never re-dispatches by itself, a person decides what to do next)
"""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
import socket
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import yaml

from .catalog import AppEntry
from .policy import (
    Rules,
    SandboxSettings,
    Violation,
    check_kustomization,
    check_objects,
    egress_entries,
    load_rules,
    network_policies,
    parse_rendered,
    pod_security_level,
    rendered_sha256,
    summarize,
)

log = logging.getLogger("onemind.executor")


@dataclass
class ExecResult:
    outcome: str  # succeeded | failed | outcome_unknown
    message: str
    steps: list[dict] = field(default_factory=list)
    # Install sandbox (policy.py): the rules an install broke, and what was checked.
    violations: list[dict] | None = None
    plan: dict | None = None

    def to_json(self) -> dict:
        out = {"outcome": self.outcome, "message": self.message, "steps": self.steps}
        if self.plan is not None:
            out["plan"] = self.plan
        if self.violations is not None:
            out["violations"] = self.violations
        return out


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


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


class Executor:
    name = "base"

    def run(self, action_type: str, app: AppEntry, agent: AgentSecret | None = None) -> ExecResult:  # pragma: no cover
        raise NotImplementedError


class NoopExecutor(Executor):
    name = "noop"

    def run(self, action_type: str, app: AppEntry, agent: AgentSecret | None = None) -> ExecResult:
        steps: list[dict] = []
        ns = f"app-{app.id}"
        if agent is not None and action_type == "app.install":
            steps.append({
                "would": f"create Secret {agent.name} in {ns}",
                "keys": ["ONEMIND_GATEWAY_URL", "ONEMIND_AGENT_TOKEN"],
                "principal": agent.principal_id,
            })
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
    """Installs through the install sandbox (H-01..H-04, docs/leap/core/SANDBOX.md).

    app.install: refuse remote or escaping kustomize references, render with `kubectl kustomize`,
    check every rendered object against the rule file, and only then: namespace (with its Pod
    Security labels), the gateway's RoleBinding in it (H-03), the default-deny NetworkPolicy
    (H-04), the agent Secret (§11.2), and finally `kubectl apply -f -` with exactly the rendered
    bytes that were checked. A violation fails the action before kubectl touches the cluster.
    """

    name = "kubernetes"

    def __init__(
        self,
        kubectl: str = "kubectl",
        timeout_s: float = 300,
        runner: Runner = subprocess.run,
        *,
        sandbox: SandboxSettings | None = None,
        rules: Rules | None = None,
        sleep: Callable[[float], None] = time.sleep,
        resolve: Callable[[str], list[str]] | None = None,
    ):
        self.kubectl = kubectl
        self.timeout_s = timeout_s
        self.runner = runner
        self.sandbox = sandbox or SandboxSettings()
        if rules is None:
            path = self.sandbox.rules_path()
            if path is None:
                raise ValueError(
                    "the kubernetes executor needs the install sandbox rules "
                    "(sdk/policy/app-objects.yaml; set ONEMIND_SANDBOX_RULES)"
                )
            rules = load_rules(path)
        self.rules = rules
        self.sleep = sleep
        self.resolve = resolve or _resolve

    # ---- the documents the gateway itself writes ---------------------------------------------
    def namespace_doc(self, app: AppEntry, level: str) -> str:
        doc = {
            "apiVersion": "v1", "kind": "Namespace",
            "metadata": {"name": f"app-{app.id}", "labels": {
                "onemind.io/app": app.id,
                "pod-security.kubernetes.io/enforce": level,
                "pod-security.kubernetes.io/enforce-version": "latest",
                "pod-security.kubernetes.io/audit": "restricted",
                "pod-security.kubernetes.io/warn": "restricted",
            }},
        }
        return json.dumps(doc)

    def rolebinding_doc(self, app: AppEntry) -> str | None:
        if not self.sandbox.gateway_sa:
            return None
        sa_ns, sa_name = self.sandbox.gateway_sa.split("/", 1)
        doc = {
            "apiVersion": "rbac.authorization.k8s.io/v1", "kind": "RoleBinding",
            "metadata": {"name": "onemind-gateway", "namespace": f"app-{app.id}",
                         "labels": {"onemind.io/app": app.id, "onemind.io/managed-by": "onemind-gateway"}},
            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": self.sandbox.deployer_role},
            "subjects": [{"kind": "ServiceAccount", "name": sa_name, "namespace": sa_ns}],
        }
        return json.dumps(doc)

    def _gateway_egress(self, agent: AgentSecret | None) -> list[tuple[str, int | None]]:
        """An agent app must reach the gateway, which `internet` excludes when it is on the LAN."""
        if agent is None or not agent.gateway_url:
            return []
        parts = urlsplit(agent.gateway_url)
        if not parts.hostname:
            return []
        port = parts.port or (443 if parts.scheme == "https" else 80)
        out = []
        for ip in self.resolve(parts.hostname):
            addr = ipaddress.ip_address(ip)
            out.append((f"{addr}/{32 if addr.version == 4 else 128}", port))
        return out

    def plan(
        self, action_type: str, app: AppEntry, agent: AgentSecret | None = None, *,
        rendered: str | None = None, level: str = "restricted", egress: list[str] | None = None,
    ) -> list[tuple[list[str], str | None]]:
        """The cluster commands after the checks passed, as (argv, stdin).

        stdin is never recorded in a step, so the agent token stays out of the ledger and audit.
        """
        ns = f"app-{app.id}"
        k = self.kubectl
        if action_type == "app.install":
            if rendered is None:
                raise ValueError("app.install needs the checked render")
            steps: list[tuple[list[str], str | None]] = [([k, "apply", "-f", "-"], self.namespace_doc(app, level))]
            rb = self.rolebinding_doc(app)
            if rb is not None:
                steps.append(([k, "apply", "-n", ns, "-f", "-"], rb))
            netpols = network_policies(app.id, egress or [], self.rules, self._gateway_egress(agent))
            steps.append(([k, "apply", "-n", ns, "-f", "-"], "\n---\n".join(json.dumps(d) for d in netpols)))
            if agent is not None:  # before the manifests, so the pods start with the Secret
                # Server-side apply: a client-side `kubectl apply` would copy the whole object,
                # token included, into the kubectl.kubernetes.io/last-applied-configuration
                # annotation, where tools that mask Secret data still show it in plain text.
                steps.append((
                    [k, "apply", "--server-side", "--field-manager=onemind-gateway", "--force-conflicts",
                     "-n", ns, "-f", "-"],
                    agent.manifest(ns, app.id),
                ))
            steps.append(([k, "apply", "-n", ns, "-f", "-"], rendered))  # exactly the checked bytes
            return steps
        if action_type == "app.remove":
            first = []
            if agent is not None:
                first = [([k, "delete", "secret", agent.name, "-n", ns, "--ignore-not-found=true"], None)]
            # Deleting the namespace deletes everything the app created in it (it may create
            # nothing elsewhere). No re-render: a changed or broken manifest cannot block removal.
            return first + [([k, "delete", "namespace", ns, "--ignore-not-found=true"], None)]
        raise ValueError(f"unsupported action type {action_type}")

    # ---- running ------------------------------------------------------------------------------
    def _exec(self, argv: list[str], stdin: str | None, app: AppEntry, agent: AgentSecret | None,
              steps: list[dict], *, keep_stdout: bool = True, retry_forbidden: bool = False):
        """Run one command. Returns (CompletedProcess, None) or (None, ExecResult to return)."""
        step = {"argv": _display(argv, app)}
        steps.append(step)
        attempts = 5 if retry_forbidden else 1
        for attempt in range(attempts):
            try:
                cp = self.runner(argv, input=stdin, capture_output=True, text=True, timeout=self.timeout_s, check=False)
            except FileNotFoundError:
                step["error"] = "kubectl not found"
                return None, ExecResult("failed", f"{self.kubectl} not found on PATH", steps)
            except subprocess.TimeoutExpired as exc:
                step["error"] = f"timeout after {self.timeout_s}s"
                step["stderr"] = _scrub(_tail(exc.stderr), agent)
                return None, ExecResult("outcome_unknown", f"kubectl timed out after {self.timeout_s}s", steps)
            # A RoleBinding just created may take a moment to reach the API server's authorizer.
            if cp.returncode != 0 and attempt + 1 < attempts and "forbidden" in _tail(cp.stderr).lower():
                self.sleep(1.0)
                continue
            break
        step["returncode"] = cp.returncode
        step["stdout"] = _scrub(_tail(cp.stdout), agent) if keep_stdout else f"<{len(cp.stdout or '')} bytes>"
        step["stderr"] = _scrub(_tail(cp.stderr), agent)
        if cp.returncode != 0:
            return None, ExecResult("failed", f"kubectl exited {cp.returncode}", steps)
        return cp, None

    def _check(self, app: AppEntry, steps: list[dict]):
        """Render and check. Returns (rendered, level, egress, plan) or an ExecResult to return."""
        rules = self.rules
        try:
            mdir = app.manifests_dir
        except ValueError as exc:
            return ExecResult("failed", str(exc), steps)
        violations = check_kustomization(mdir, app.dir, rules)
        level, gv = pod_security_level(app.id, app.manifest, rules)
        egress, ev = egress_entries(app.id, app.manifest, rules)
        plan = {"policy_version": rules.version, "pod_security": level, "egress": egress}
        if violations:  # never render something that could fetch or read outside the app folder
            return _refused(app, violations + ([gv] if gv else []) + ev, plan, steps)
        argv = [self.kubectl, "kustomize", "--load-restrictor=LoadRestrictionsRootOnly", str(mdir)]
        cp, err = self._exec(argv, None, app, None, steps, keep_stdout=False)
        if err is not None:
            err.message = f"rendering the manifests failed: {err.message}"
            return err
        rendered = cp.stdout or ""
        try:
            docs = parse_rendered(rendered)
        except yaml.YAMLError:
            return _refused(app, [Violation("G-02", "?", app.id, rules.msg("G-02"))], plan, steps)
        plan.update(summarize(docs))
        plan["rendered_sha256"] = rendered_sha256(rendered)
        violations = check_objects(docs, app.id, app.manifest, rules) + ev
        if violations:
            return _refused(app, violations, plan, steps)
        return rendered, level, egress, plan

    def run(self, action_type: str, app: AppEntry, agent: AgentSecret | None = None) -> ExecResult:
        steps: list[dict] = []
        plan_info: dict | None = None
        kwargs: dict = {}
        if action_type == "app.install":
            checked = self._check(app, steps)
            if isinstance(checked, ExecResult):
                return checked
            rendered, level, egress, plan_info = checked
            kwargs = {"rendered": rendered, "level": level, "egress": egress}
        try:
            commands = self.plan(action_type, app, agent, **kwargs)
        except ValueError as exc:
            return ExecResult("failed", str(exc), steps, plan=plan_info)
        bound = False
        for argv, stdin in commands:
            cp, err = self._exec(argv, stdin, app, agent, steps, retry_forbidden=bound)
            if err is not None:
                err.plan = plan_info
                return err
            if stdin is not None and '"kind": "RoleBinding"' in stdin:
                bound = True  # later steps may race the new binding
        return ExecResult(
            "succeeded", f"{action_type} {app.id} applied to namespace app-{app.id}", steps, plan=plan_info
        )


def _refused(app: AppEntry, violations: list[Violation], plan: dict, steps: list[dict]) -> ExecResult:
    n = len(violations)
    return ExecResult(
        "failed", f"app {app.id!r} breaks {n} install rule{'s' if n != 1 else ''}", steps,
        violations=[v.to_json() for v in violations], plan=plan,
    )


def _resolve(host: str) -> list[str]:
    try:
        return sorted({str(ipaddress.ip_address(host))})
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return []
    return sorted({info[4][0].split("%", 1)[0] for info in infos})


def _scrub(text: str, agent: AgentSecret | None) -> str:
    # kubectl does not echo stringData, but an error message must never carry the token anyway.
    if agent is not None and agent.token:
        for form in (agent.token, _b64(agent.token)):
            text = text.replace(form, "[redacted]")
    return text


def _display(argv: Sequence[str], app: AppEntry) -> list[str]:
    # Rewrite the apps folder prefix, so the audit log and API never leak host paths.
    root = str(app.dir.resolve().parent)
    return [a.replace(root, "$ONEMIND_APPS_DIR", 1) if a.startswith(root) else a for a in argv]


def make_executor(
    name: str, kubectl: str = "kubectl", timeout_s: float = 300, sandbox: SandboxSettings | None = None
) -> Executor:
    if name == "kubernetes":
        return KubernetesExecutor(kubectl=kubectl, timeout_s=timeout_s, sandbox=sandbox)
    return NoopExecutor()
