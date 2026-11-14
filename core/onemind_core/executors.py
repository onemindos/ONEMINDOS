"""Executors: the only part of the gateway that changes the outside world, and only after approval.

- noop: marks success without touching anything (Mac / compose demos and tests). It records the
  steps it would have taken, including the agent Secret of §11.2 (never the token).
- kubernetes: renders `kubectl kustomize <app>/manifests`, checks every object against the
  install sandbox's rule file (policy.py), then applies the namespace (Pod Security labels), the
  gateway's RoleBinding, the default-deny NetworkPolicy and the checked render with
  `kubectl apply -f -`; removal deletes the workloads and keeps the data volumes. For an app with `spec.agent.principal` it
  creates the agent Secret before the manifests (so the app's pods start with it) and deletes it
  first on removal.
  The app's declared `spec.secrets` (values from the secret store, appsecrets/) are applied the
  same way, server-side, before the manifests; `app.configure` re-applies them and rolls the
  app's workloads.

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
from .lifecycle import AppCredentialGrant, ExecContext, report_progress
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
    # Health-gated update: True when the new revision was not healthy and the old one was restored.
    reverted: bool | None = None

    def to_json(self) -> dict:
        out = {"outcome": self.outcome, "message": self.message, "steps": self.steps}
        if self.reverted is not None:
            out["reverted"] = self.reverted
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


class Executor:
    name = "base"

    def run(
        self, action_type: str, app: AppEntry, agent: AgentSecret | None = None, ctx: ExecContext | None = None
    ) -> ExecResult:  # pragma: no cover
        raise NotImplementedError


class NoopExecutor(Executor):
    name = "noop"

    def run(
        self, action_type: str, app: AppEntry, agent: AgentSecret | None = None, ctx: ExecContext | None = None
    ) -> ExecResult:
        steps: list[dict] = []
        ns = f"app-{app.id}"
        ctx = ctx or ExecContext()
        report_progress(f"{action_type} started", 10)
        if agent is not None and action_type == "app.install":
            steps.append({
                "would": f"create Secret {agent.name} in {ns}",
                "keys": ["ONEMIND_GATEWAY_URL", "ONEMIND_AGENT_TOKEN"],
                "principal": agent.principal_id,
            })
        if ctx.credentials is not None and action_type == "app.install":
            steps.append({"would": f"create Secret {ctx.credentials.secret_name} in {ns}", "keys": ["USERNAME", "PASSWORD"]})
        if action_type in ("app.install", "app.configure"):
            for sec in ctx.secrets:
                steps.append({"would": f"apply Secret {sec.name} in {ns} (server-side)", "keys": sec.keys()})
        if action_type in ("app.install", "app.update", "app.start"):
            steps.append({"would": f"apply manifests of {app.id} in {ns}"})
            if action_type == "app.update":
                steps.append({"would": f"wait until every workload of {app.id} is ready; restore the previous revision if not"})
        elif action_type == "app.stop":
            steps.append({"would": f"scale the workloads of {app.id} in {ns} to zero; data kept"})
        elif action_type == "app.restart":
            steps.append({"would": f"roll the workloads of {app.id} in {ns}"})
        elif action_type == "app.configure":
            if ctx.settings:
                steps.append({
                    "would": f"apply ConfigMap {SETTINGS_CONFIGMAP} ({len(ctx.settings)} settings) in {ns}"
                             + (", then roll the workloads" if ctx.restart else "; the workloads are not restarted"),
                    "keys": sorted(ctx.settings),
                })
            if not ctx.settings or (ctx.secrets and not ctx.restart):  # a changed Secret is read only at start
                steps.append({"would": f"roll the workloads of {app.id} in {ns}"})
        elif action_type == "app.remove":
            if agent is not None:
                steps.append({"would": f"delete Secret {agent.name} in {ns}", "principal": agent.principal_id})
            steps.append({"would": f"delete the workloads of {app.id} in {ns}; its data (PersistentVolumeClaims) is kept"})
        elif action_type == "app.delete_data":
            steps.append({"would": f"delete namespace {ns} with all its PersistentVolumeClaims"})
        report_progress(f"{action_type} done", 100)
        return ExecResult("succeeded", f"noop executor: {action_type} {app.id} recorded, nothing changed", steps)


Runner = Callable[..., subprocess.CompletedProcess]

# The ConfigMap the gateway writes for app.configure; manifests read it with envFrom (optional: true).
SETTINGS_CONFIGMAP = "onemind-settings"

# Namespaced kinds app.remove deletes: the app kinds of sdk/policy/app-objects.yaml minus
# PersistentVolumeClaim (data is kept, contract 12.5) and minus RoleBinding (the gateway's own
# binding lives there). Pods go with their controllers.
REMOVABLE_KINDS = (
    "deployments", "statefulsets", "jobs", "cronjobs", "services", "configmaps", "secrets",
    "serviceaccounts", "poddisruptionbudgets", "horizontalpodautoscalers", "roles",
)
WORKLOAD_KINDS = "deployments,statefulsets"
REPLICAS_ANNOTATION = "onemind.io/replicas-before-stop"


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
        health_timeout_s: float = 120,
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
        self.health_timeout_s = health_timeout_s
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
            # Contract 12.5: a plain app.remove keeps the app's data. Deleting the namespace would
            # delete its PersistentVolumeClaims, and k3s's local-path volumes are reclaimed on
            # delete. So delete every kind an app may ship (sdk/policy/app-objects.yaml) except
            # PersistentVolumeClaim, and keep the namespace, the gateway's own RoleBinding and the
            # default-deny NetworkPolicies. Reinstalling picks the volumes up again. No re-render:
            # a changed or broken manifest cannot block removal.
            kinds = ",".join(REMOVABLE_KINDS)
            return first + [([k, "delete", kinds, "--all", "-n", ns, "--ignore-not-found=true"], None)]
        if action_type == "app.delete_data":
            # Only reachable from status `removed` (the gateway checks). The namespace takes the
            # PersistentVolumeClaims, the gateway's RoleBinding and the NetworkPolicies with it.
            return [([k, "delete", "namespace", ns, "--ignore-not-found=true"], None)]
        if action_type == "app.stop":
            return [([k, "scale", WORKLOAD_KINDS, "--all", "--replicas=0", "-n", ns], None)]
        raise ValueError(f"unsupported action type {action_type}")

    # ---- running ------------------------------------------------------------------------------
    def _exec(self, argv: list[str], stdin: str | None, app: AppEntry, agent: AgentSecret | None,
              steps: list[dict], *, keep_stdout: bool = True, retry_forbidden: bool = False,
              secrets: Sequence[AppSecret] = ()):
        """Run one command. Returns (CompletedProcess, None) or (None, ExecResult to return)."""
        step = {"argv": _display(argv, app)}
        steps.append(step)
        hidden = _sensitive(agent, secrets)
        attempts = 5 if retry_forbidden else 1
        for attempt in range(attempts):
            try:
                cp = self.runner(argv, input=stdin, capture_output=True, text=True, timeout=self.timeout_s, check=False)
            except FileNotFoundError:
                step["error"] = "kubectl not found"
                return None, ExecResult("failed", f"{self.kubectl} not found on PATH", steps)
            except subprocess.TimeoutExpired as exc:
                step["error"] = f"timeout after {self.timeout_s}s"
                step["stderr"] = _tail(_scrub(exc.stderr, hidden))
                return None, ExecResult("outcome_unknown", f"kubectl timed out after {self.timeout_s}s", steps)
            # A RoleBinding just created may take a moment to reach the API server's authorizer.
            if cp.returncode != 0 and attempt + 1 < attempts and "forbidden" in _tail(cp.stderr).lower():
                self.sleep(1.0)
                continue
            break
        step["returncode"] = cp.returncode
        step["stdout"] = _tail(_scrub(cp.stdout, hidden)) if keep_stdout else f"<{len(cp.stdout or '')} bytes>"
        step["stderr"] = _tail(_scrub(cp.stderr, hidden))
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

    # ---- lifecycle helpers ---------------------------------------------------------------------
    def settings_doc(self, app: AppEntry, settings: dict) -> str:
        doc = {
            "apiVersion": "v1", "kind": "ConfigMap",
            "metadata": {"name": SETTINGS_CONFIGMAP, "namespace": f"app-{app.id}",
                         "labels": {"onemind.io/app": app.id, "onemind.io/managed-by": "onemind-gateway"}},
            "data": {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in sorted(settings.items())},
        }
        return json.dumps(doc)

    def credentials_doc(self, app: AppEntry, grant: AppCredentialGrant) -> str:
        data = {"PASSWORD": _b64(grant.password)}
        if grant.username:
            data["USERNAME"] = _b64(grant.username)
        return json.dumps({
            "apiVersion": "v1", "kind": "Secret", "type": "Opaque",
            "metadata": {"name": grant.secret_name, "namespace": f"app-{app.id}",
                         "labels": {"onemind.io/app": app.id, "onemind.io/credentials": "true"}},
            "data": data,
        })

    def _workloads(self, app: AppEntry, steps: list[dict]):
        """(refs, error): the app's Deployments and StatefulSets as [(ref, replicas, saved_replicas)]."""
        cp, err = self._exec([self.kubectl, "get", WORKLOAD_KINDS, "-n", f"app-{app.id}", "-o", "json"],
                             None, app, None, steps, keep_stdout=False)
        if err is not None:
            return None, err
        try:
            items = json.loads(cp.stdout or "{}").get("items") or []
            out = []
            for it in items:
                kind = "statefulset" if it.get("kind") == "StatefulSet" else "deployment"
                ann = (it.get("metadata") or {}).get("annotations") or {}
                saved = ann.get(REPLICAS_ANNOTATION)
                out.append((f"{kind}/{it['metadata']['name']}", int((it.get("spec") or {}).get("replicas", 1)),
                            int(saved) if saved is not None else None))
            return out, None
        except (ValueError, KeyError, TypeError, AttributeError):
            return None, ExecResult("failed", "could not read the app's workloads", steps)

    def _rollout_wait(self, app: AppEntry, refs: list[str], steps: list[dict]) -> ExecResult | None:
        """The health gate: every workload must report a finished rollout. None = healthy."""
        for ref in refs:
            argv = [self.kubectl, "rollout", "status", ref, "-n", f"app-{app.id}", f"--timeout={int(self.health_timeout_s)}s"]
            _, err = self._exec(argv, None, app, None, steps)
            if err is not None:
                return err
        return None

    def _lifecycle(self, action_type: str, app: AppEntry, ctx: ExecContext, steps: list[dict]) -> ExecResult:
        ns = f"app-{app.id}"
        k = self.kubectl
        if action_type == "app.configure":
            # Secrets first, server-side (values on stdin only, scrubbed from recorded output).
            for sec in ctx.secrets:
                report_progress("writing secrets", 15)
                _, err = self._exec(_ssa(k, ns), sec.manifest(ns, app.id), app, None, steps, secrets=ctx.secrets)
                if err is not None:
                    return err
            if ctx.settings:  # none stored and none sent: a secrets-only change on a plain app
                report_progress("writing settings", 20)
                _, err = self._exec([k, "apply", "-n", ns, "-f", "-"], self.settings_doc(app, ctx.settings), app, None, steps, secrets=ctx.secrets)
                if err is not None:
                    return err
            if not ctx.restart and not ctx.secrets:
                # every changed setting is read live (§12.22 restart: false); a changed Secret is read
                # only at start, so a secret change always rolls the workloads
                report_progress("done", 100)
                return ExecResult("succeeded", f"app.configure {app.id}: settings applied, no restart needed", steps)
        report_progress("reading workloads", 30)
        work, err = self._workloads(app, steps)
        if err is not None:
            return err
        for i, (ref, replicas, saved) in enumerate(work):
            report_progress(f"{action_type.split('.')[1]} {ref}", 40 + int(40 * i / max(1, len(work))))
            if action_type == "app.stop":
                cmds = []
                if replicas > 0:  # remember the count; a second stop must not overwrite it with 0
                    cmds.append([k, "annotate", ref, f"{REPLICAS_ANNOTATION}={replicas}", "--overwrite", "-n", ns])
                cmds.append([k, "scale", ref, "--replicas=0", "-n", ns])
            elif action_type == "app.start":
                cmds = [[k, "scale", ref, f"--replicas={saved if saved else 1}", "-n", ns]]
            else:
                cmds = [[k, "rollout", "restart", ref, "-n", ns]]
            for argv in cmds:
                _, err = self._exec(argv, None, app, None, steps, secrets=ctx.secrets)
                if err is not None:
                    return err
        if action_type != "app.stop" and work:
            report_progress("waiting for the workloads", 85)
            err = self._rollout_wait(app, [w[0] for w in work], steps)
            if err is not None:
                return err
        report_progress("done", 100)
        return ExecResult("succeeded", f"{action_type} {app.id} applied to namespace {ns}", steps)

    def _update(self, app: AppEntry, agent: AgentSecret | None, steps: list[dict]) -> ExecResult:
        """Check, apply the new render, wait for health; restore the previous revision if unhealthy."""
        ns = f"app-{app.id}"
        k = self.kubectl
        report_progress("checking the new version against the install rules", 10)
        checked = self._check(app, steps)
        if isinstance(checked, ExecResult):
            return checked
        rendered, _level, egress, plan_info = checked
        report_progress("applying the new version", 35)
        netpols = network_policies(app.id, egress or [], self.rules, self._gateway_egress(agent))
        for argv, stdin in (
            ([k, "apply", "-n", ns, "-f", "-"], "\n---\n".join(json.dumps(d) for d in netpols)),
            ([k, "apply", "-n", ns, "-f", "-"], rendered),  # exactly the checked bytes
        ):
            _, err = self._exec(argv, stdin, app, agent, steps)
            if err is not None:
                err.plan = plan_info
                return err
        work, err = self._workloads(app, steps)
        if err is not None:
            err.plan = plan_info
            return err
        refs = [w[0] for w in work]
        report_progress("waiting for the new version to become healthy", 60)
        unhealthy = self._rollout_wait(app, refs, steps)
        if unhealthy is None:
            report_progress("healthy", 100)
            return ExecResult("succeeded", f"app.update {app.id} applied and healthy", steps, plan=plan_info, reverted=False)
        if unhealthy.outcome == "outcome_unknown":  # timed out talking to kubectl: we cannot tell
            unhealthy.plan = plan_info
            return unhealthy
        report_progress("not healthy: restoring the previous revision", 75)
        for ref in refs:
            _, err = self._exec([k, "rollout", "undo", ref, "-n", ns], None, app, None, steps)
            if err is not None:  # could not restore: do not claim anything about the app
                return ExecResult(
                    "outcome_unknown", "the update was not healthy and the revert did not finish", steps,
                    plan=plan_info,
                )
        back = self._rollout_wait(app, refs, steps)
        if back is not None:
            return ExecResult(
                "outcome_unknown", "the update was not healthy; the previous revision was restored but is not ready",
                steps, plan=plan_info,
            )
        report_progress("previous revision restored", 100)
        return ExecResult(
            "failed", "the new version was not healthy; the previous revision was restored", steps,
            plan=plan_info, reverted=True,
        )

    def run(
        self, action_type: str, app: AppEntry, agent: AgentSecret | None = None, ctx: ExecContext | None = None
    ) -> ExecResult:
        steps: list[dict] = []
        ctx = ctx or ExecContext()
        if action_type == "app.update":
            return self._update(app, agent, steps)
        if action_type in ("app.stop", "app.start", "app.restart", "app.configure"):
            return self._lifecycle(action_type, app, ctx, steps)
        plan_info: dict | None = None
        kwargs: dict = {}
        if action_type == "app.install":
            report_progress("checking the app against the install rules", 10)
            checked = self._check(app, steps)
            if isinstance(checked, ExecResult):
                return checked
            rendered, level, egress, plan_info = checked
            kwargs = {"rendered": rendered, "level": level, "egress": egress}
        try:
            commands = self.plan(action_type, app, agent, **kwargs)
        except ValueError as exc:
            return ExecResult("failed", str(exc), steps, plan=plan_info)
        if action_type == "app.install":
            ns = f"app-{app.id}"
            extra: list[tuple[list[str], str | None]] = []
            if ctx.credentials is not None:  # same server-side apply as the agent Secret (no last-applied copy)
                extra.append(([self.kubectl, "apply", "--server-side", "--field-manager=onemind-gateway",
                               "--force-conflicts", "-n", ns, "-f", "-"], self.credentials_doc(app, ctx.credentials)))
            for sec in ctx.secrets:  # declared spec.secrets, server-side, before the manifests
                extra.append((_ssa(self.kubectl, ns), sec.manifest(ns, app.id)))
            if ctx.settings:
                extra.append(([self.kubectl, "apply", "-n", ns, "-f", "-"], self.settings_doc(app, ctx.settings)))
            commands = commands[:-1] + extra + commands[-1:]  # before the manifests, so pods start with them
        bound = False
        total = max(1, len(commands))
        for n, (argv, stdin) in enumerate(commands):
            report_progress(f"{action_type.split('.')[1]} step {n + 1} of {total}", 20 + int(75 * n / total))
            _, err = self._exec(argv, stdin, app, agent, steps, retry_forbidden=bound, secrets=ctx.secrets)
            if err is not None:
                err.plan = plan_info
                return err
            if stdin is not None and '"kind": "RoleBinding"' in stdin:
                bound = True  # later steps may race the new binding
        report_progress("done", 100)
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


def _sensitive(agent: AgentSecret | None, secrets: Sequence[AppSecret]) -> list[str]:
    values = [agent.token] if agent is not None and agent.token else []
    values += [v for s in secrets for v in s.data.values() if v]
    # Longest first, so a value that contains another is redacted whole.
    return sorted({form for v in values for form in (v, _b64(v))}, key=len, reverse=True)


def _scrub(text: str | bytes | None, hidden: Sequence[str]) -> str:
    # kubectl does not echo Secret data, but an error message must never carry a value anyway.
    # Scrub the whole output before _tail cuts it: a value cut at the tail's edge would no
    # longer match and its end would be kept.
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    for form in hidden:
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
