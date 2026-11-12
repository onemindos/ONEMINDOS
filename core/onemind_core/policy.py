# SPDX-License-Identifier: Apache-2.0
"""Install sandbox: check an app's rendered objects against sdk/policy/app-objects.yaml.

Hardening H-01..H-04, docs/leap/core/SANDBOX.md. Pure Python, no network, no cluster calls:

- `check_kustomization(manifests_dir, app_dir)`: before rendering, refuse remote bases (Z-01),
  paths that leave the app folder (Z-02) and helm charts or kustomize plugins (Z-03).
- `check_objects(docs, app_id, manifest, rules)`: every rendered object against the allowlist
  and the forbidden fields (K-, N-, F-, S-, V-, P-, I-, R- rules).
- `pod_security_level(app_id, manifest, rules)`: the PSA level of the app's namespace.
- `network_policies(...)`: the default-deny NetworkPolicy plus the declared allowances.

The executor (executors.py) renders with `kubectl kustomize`, calls these, and applies exactly
the bytes it checked. A violation means kubectl never touches the cluster for that install.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .sections import config_section

# Repo-relative and image locations of the rule file, found the same way as the app schema.
_REPO_RULES = Path(__file__).resolve().parents[2] / "sdk" / "policy" / "app-objects.yaml"
_IMAGE_RULES = Path("/opt/onemind/sdk/policy/app-objects.yaml")
RULES_SCHEMA = "onemind.io/app-objects/v1"
PSA_LEVELS = ("restricted", "baseline")


@config_section("sandbox")
@dataclass(frozen=True)
class SandboxSettings:
    # ONEMIND_SANDBOX_RULES: the rule file; default sdk/policy/app-objects.yaml (repo or image).
    rules: Path | None = None
    # ONEMIND_SANDBOX_GATEWAY_SA=<namespace>/<name>: the gateway's ServiceAccount. When set, each
    # install binds it to ClusterRole `deployer_role` inside app-<id> only (H-03, deploy/install.sh).
    gateway_sa: str | None = None
    deployer_role: str = "onemind-app-deployer"

    def validate(self) -> None:
        if self.gateway_sa is not None and not re.fullmatch(r"[a-z0-9-]{1,63}/[a-z0-9-]{1,253}", self.gateway_sa):
            raise ValueError("ONEMIND_SANDBOX_GATEWAY_SA must be <namespace>/<serviceaccount>")

    def rules_path(self) -> Path | None:
        if self.rules is not None:
            return self.rules
        return next((p for p in (_REPO_RULES, _IMAGE_RULES) if p.is_file()), None)


@dataclass(frozen=True)
class Violation:
    rule: str
    kind: str
    name: str
    message: str
    path: str | None = None

    def to_json(self) -> dict:
        out = {"rule": self.rule, "kind": self.kind, "name": self.name, "message": self.message}
        if self.path:
            out["path"] = self.path
        return out


@dataclass(frozen=True)
class Rules:
    version: int
    allow: frozenset[tuple[str, str]]
    service_types: frozenset[str]
    storage_classes: frozenset[str | None]
    caps_allowed: frozenset[str]
    psa_default: str
    reviewed: dict[str, dict]
    require_digest: bool
    default_egress: tuple[str, ...]
    internet_except: tuple[str, ...]
    proxy_label: dict[str, str]
    messages: dict[str, str] = field(default_factory=dict)

    def msg(self, rule: str, extra: str = "") -> str:
        base = self.messages.get(rule, rule)
        return f"{base}: {extra}" if extra else base


def load_rules(path: Path) -> Rules:
    """Parse and sanity-check the rule file. Raises ValueError on anything unexpected."""
    try:
        doc = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read sandbox rules {path.name}: {exc.__class__.__name__}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != RULES_SCHEMA:
        raise ValueError(f"sandbox rules must declare schema: {RULES_SCHEMA}")
    if not isinstance(doc.get("version"), int):
        raise ValueError("sandbox rules need an integer version")
    allow = frozenset((str(a["apiVersion"]), str(a["kind"])) for a in doc.get("allow") or [])
    if not allow:
        raise ValueError("sandbox rules allow no kinds")
    ps = doc.get("pod_security") or {}
    default = ps.get("default", "restricted")
    if default not in PSA_LEVELS:
        raise ValueError("pod_security.default must be restricted or baseline")
    reviewed = {str(k): dict(v) for k, v in (ps.get("reviewed") or {}).items()}
    for app_id, entry in reviewed.items():
        if entry.get("level") not in PSA_LEVELS or not entry.get("reason"):
            raise ValueError(f"pod_security.reviewed.{app_id} needs a level and a reason")
    net = doc.get("network") or {}
    except_ = tuple(str(c) for c in net.get("internet_except") or [])
    for cidr in except_:
        ipaddress.ip_network(cidr)  # ValueError on a typo
    return Rules(
        version=doc["version"],
        allow=allow,
        service_types=frozenset(doc.get("service_types") or ["ClusterIP"]),
        storage_classes=frozenset(doc.get("storage_classes") or [None]),
        caps_allowed=frozenset((doc.get("capabilities") or {}).get("add_allowed") or []),
        psa_default=default,
        reviewed=reviewed,
        require_digest=bool((doc.get("images") or {}).get("require_digest", True)),
        default_egress=tuple(net.get("default_egress") or ["internet"]),
        internet_except=except_,
        proxy_label={str(k): str(v) for k, v in (net.get("proxy_namespace_label") or {}).items()},
        messages={str(k): str(v) for k, v in (doc.get("rules") or {}).items()},
    )


# ---- before rendering: the kustomization tree ---------------------------------------------------

KUSTOMIZATION_NAMES = ("kustomization.yaml", "kustomization.yml", "Kustomization")
_REMOTE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|git@|github\.com/|gitlab\.com/|bitbucket\.org/)|[?&]ref=|\.git(?:/|$|//)", re.I)
_PLUGIN_KEYS = ("helmCharts", "helmGlobals", "helmChartInflationGenerator", "generators", "transformers", "validators")


def _kfile(d: Path) -> Path | None:
    return next((d / n for n in KUSTOMIZATION_NAMES if (d / n).is_file()), None)


def check_kustomization(manifests_dir: Path, app_dir: Path, rules: Rules) -> list[Violation]:
    """Walk the local kustomization tree; refuse anything the render could fetch or read from outside."""
    root = app_dir.resolve()
    out: list[Violation] = []
    seen: set[Path] = set()

    def inside(p: Path) -> bool:
        try:
            return p.resolve().is_relative_to(root)
        except OSError:
            return False

    def walk(d: Path) -> None:
        d = d.resolve()
        if d in seen:
            return
        seen.add(d)
        kf = _kfile(d)
        label = str(d.relative_to(root)) if d.is_relative_to(root) else d.name
        if kf is None:
            out.append(Violation("G-02", "Kustomization", label, "no kustomization.yaml"))
            return
        try:
            doc = yaml.safe_load(kf.read_text()) or {}
        except (OSError, yaml.YAMLError):
            out.append(Violation("G-02", "Kustomization", label, "kustomization is not valid YAML"))
            return
        if not isinstance(doc, dict):
            out.append(Violation("G-02", "Kustomization", label, "kustomization is not a mapping"))
            return
        for key in _PLUGIN_KEYS:
            if doc.get(key):
                out.append(Violation("Z-03", "Kustomization", label, rules.msg("Z-03", key), key))
        refs: list[tuple[str, str]] = []
        for key in ("resources", "bases", "components", "crds", "patchesStrategicMerge"):
            for entry in doc.get(key) or []:
                if isinstance(entry, str):
                    refs.append((key, entry))
        for key in ("patches", "patchesJson6902", "replacements"):
            for p in doc.get(key) or []:
                if isinstance(p, dict) and isinstance(p.get("path"), str):
                    refs.append((key, p["path"]))
        for entry in doc.get("configurations") or []:
            if isinstance(entry, str):
                refs.append(("configurations", entry))
        openapi = doc.get("openapi")
        if isinstance(openapi, dict) and isinstance(openapi.get("path"), str):
            refs.append(("openapi", openapi["path"]))
        for gen in (doc.get("configMapGenerator") or []) + (doc.get("secretGenerator") or []):
            if not isinstance(gen, dict):
                continue
            for k in ("files", "envs"):
                for entry in gen.get(k) or []:
                    if isinstance(entry, str):
                        refs.append((k, entry.split("=", 1)[-1]))
            if isinstance(gen.get("env"), str):
                refs.append(("env", gen["env"]))
        for key, ref in refs:
            if _REMOTE.search(ref):
                out.append(Violation("Z-01", "Kustomization", label, rules.msg("Z-01", ref), key))
                continue
            if key == "patchesStrategicMerge" and "\n" in ref:
                continue  # an inline patch, not a path
            target = d / ref
            if Path(ref).is_absolute() or not inside(target):
                out.append(Violation("Z-02", "Kustomization", label, rules.msg("Z-02", ref), key))
                continue
            if not target.exists():
                # kustomize tries a reference that is not a local path as a remote one
                # (`git::https://…`, `gh:…`, `host/org/repo//dir`), which the pattern above cannot
                # list exhaustively. Every reference must be a file or folder the app ships.
                out.append(Violation("Z-01", "Kustomization", label, rules.msg("Z-01", f"{ref} (not in the app folder)"), key))
                continue
            if key in ("resources", "bases", "components") and target.is_dir():
                walk(target)

    walk(manifests_dir)
    return out


# ---- after rendering: every object --------------------------------------------------------------

_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
# Volume types PSA `restricted` allows (kubernetes.io/docs/concepts/security/pod-security-standards).
RESTRICTED_VOLUMES = frozenset({
    "configMap", "csi", "downwardAPI", "emptyDir", "ephemeral", "persistentVolumeClaim", "projected", "secret",
})
_NOT_VOLUME_TYPES = frozenset({"name"})


def parse_rendered(text: str) -> list[Any]:
    return [d for d in yaml.safe_load_all(text) if d is not None]


def rendered_sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def pod_security_level(app_id: str, manifest: dict, rules: Rules) -> tuple[str, Violation | None]:
    """The namespace's enforce level and, if the manifest asks for an unreviewed level, a violation."""
    reviewed = rules.reviewed.get(app_id)
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    sec = spec.get("security") if isinstance(spec, dict) else None
    declared = sec.get("podSecurity") if isinstance(sec, dict) else None
    if declared is not None and declared not in PSA_LEVELS:
        return rules.psa_default, Violation("G-01", "App", app_id, rules.msg("G-01", str(declared)), "spec.security.podSecurity")
    if reviewed is not None:
        level = reviewed["level"]
        if declared is not None and declared != level and declared != "restricted":
            return level, Violation("G-01", "App", app_id, rules.msg("G-01", str(declared)), "spec.security.podSecurity")
        return ("restricted" if declared == "restricted" else level), None
    if declared not in (None, rules.psa_default, "restricted"):
        return rules.psa_default, Violation("G-01", "App", app_id, rules.msg("G-01", str(declared)), "spec.security.podSecurity")
    return rules.psa_default, None


def _pod_spec(obj: dict) -> tuple[dict | None, str]:
    kind = obj.get("kind")
    spec = obj.get("spec") if isinstance(obj.get("spec"), dict) else {}
    if kind in ("Deployment", "StatefulSet", "Job", "ReplicaSet", "DaemonSet"):
        tpl = spec.get("template") or {}
        return (tpl.get("spec") if isinstance(tpl, dict) else None), "spec.template.spec"
    if kind == "CronJob":
        jt = (spec.get("jobTemplate") or {}).get("spec") or {}
        tpl = jt.get("template") or {} if isinstance(jt, dict) else {}
        return (tpl.get("spec") if isinstance(tpl, dict) else None), "spec.jobTemplate.spec.template.spec"
    if kind == "Pod":
        return spec, "spec"
    return None, ""


def _containers(pod: dict, base: str) -> Iterator[tuple[dict, str]]:
    for key in ("initContainers", "containers", "ephemeralContainers"):
        for i, c in enumerate(pod.get(key) or []):
            if isinstance(c, dict):
                yield c, f"{base}.{key}[{i}]"


def _check_pod(pod: dict, base: str, level: str, caps_allowed: frozenset[str], rules: Rules, kind: str, name: str) -> list[Violation]:
    out: list[Violation] = []

    def v(rule: str, path: str, extra: str = "") -> None:
        out.append(Violation(rule, kind, name, rules.msg(rule, extra), path))

    for field_, rule in (("hostNetwork", "F-01"), ("hostPID", "F-02"), ("hostIPC", "F-03")):
        if pod.get(field_) is True:
            v(rule, f"{base}.{field_}")
    psc = pod.get("securityContext") if isinstance(pod.get("securityContext"), dict) else {}
    if (psc.get("windowsOptions") or {}).get("hostProcess") is True:
        v("F-08", f"{base}.securityContext.windowsOptions.hostProcess")
    for i, vol in enumerate(pod.get("volumes") or []):
        if not isinstance(vol, dict):
            continue
        types_ = [k for k in vol if k not in _NOT_VOLUME_TYPES]
        if "hostPath" in vol:
            v("F-04", f"{base}.volumes[{i}].hostPath")
        elif level == "restricted":
            for t in types_:
                if t not in RESTRICTED_VOLUMES:
                    v("S-05", f"{base}.volumes[{i}].{t}", t)
    pod_nonroot = psc.get("runAsNonRoot") is True and psc.get("runAsUser") != 0
    pod_seccomp = (psc.get("seccompProfile") or {}).get("type") in ("RuntimeDefault", "Localhost")
    for c, cpath in _containers(pod, base):
        csc = c.get("securityContext") if isinstance(c.get("securityContext"), dict) else {}
        if (csc.get("windowsOptions") or {}).get("hostProcess") is True:
            v("F-08", f"{cpath}.securityContext.windowsOptions.hostProcess")
        for j, port in enumerate(c.get("ports") or []):
            if isinstance(port, dict) and port.get("hostPort") not in (None, 0):
                v("F-05", f"{cpath}.ports[{j}].hostPort")
        if csc.get("privileged") is True:
            v("F-06", f"{cpath}.securityContext.privileged")
        caps = csc.get("capabilities") if isinstance(csc.get("capabilities"), dict) else {}
        for cap in caps.get("add") or []:
            if str(cap).upper().removeprefix("CAP_") not in caps_allowed:
                v("F-07", f"{cpath}.securityContext.capabilities.add", str(cap))
        if level != "restricted":
            continue
        if csc.get("runAsUser") == 0 or not (csc.get("runAsNonRoot") is True or (pod_nonroot and csc.get("runAsNonRoot") is not False)):
            v("S-01", f"{cpath}.securityContext.runAsNonRoot")
        if csc.get("allowPrivilegeEscalation") is not False:
            v("S-02", f"{cpath}.securityContext.allowPrivilegeEscalation")
        if "ALL" not in [str(x).upper() for x in caps.get("drop") or []]:
            v("S-03", f"{cpath}.securityContext.capabilities.drop")
        ctype = (csc.get("seccompProfile") or {}).get("type")
        if not (ctype in ("RuntimeDefault", "Localhost") or (ctype is None and pod_seccomp)):
            v("S-04", f"{cpath}.securityContext.seccompProfile")
    return out


# A Role binds inside app-<id>, but a rule there on `namespaces` acts on the app-<id> Namespace
# itself (its Pod Security and proxy labels), and one on NetworkPolicies undoes the gateway's
# default-deny. The gateway holds both rights, so Kubernetes' escalation check would not stop it
# from creating such a Role: only the API groups of the app kinds are allowed (no
# networking.k8s.io), and these resources are refused by name.
ROLE_FORBIDDEN_RESOURCES = frozenset({"namespaces", "nodes", "persistentvolumes", "componentstatuses"})
ROLE_FORBIDDEN_SUBRESOURCES = frozenset({"exec", "attach", "portforward", "proxy", "ephemeralcontainers", "token"})
RBAC_GROUP = "rbac.authorization.k8s.io"


def _role_groups(rules: Rules) -> frozenset[str]:
    """API groups of the allowed kinds, without RBAC: "" for v1, "apps" for apps/v1, ..."""
    return frozenset(api.rpartition("/")[0] for api, _ in rules.allow) - {RBAC_GROUP}


def _check_role(obj: dict, rules: Rules, name: str) -> list[Violation]:
    out = []
    allowed_groups = _role_groups(rules)
    for i, rule in enumerate(obj.get("rules") or []):
        if not isinstance(rule, dict):
            out.append(Violation("R-03", "Role", name, rules.msg("R-03"), f"rules[{i}]"))
            continue
        groups = [str(g) for g in rule.get("apiGroups") or []]
        res = [str(r) for r in rule.get("resources") or []]
        verbs = [str(vb) for vb in rule.get("verbs") or []]
        bad = (
            "*" in groups or "*" in res or "*" in verbs
            or any(g not in allowed_groups for g in groups)
            or any(r.partition("/")[0] in ROLE_FORBIDDEN_RESOURCES for r in res)
            or any(r.partition("/")[2] in ROLE_FORBIDDEN_SUBRESOURCES or r.endswith("/*") for r in res)
            or any(vb in ("escalate", "bind", "impersonate") for vb in verbs)
            or rule.get("nonResourceURLs")
        )
        if bad:
            out.append(Violation("R-03", "Role", name, rules.msg("R-03"), f"rules[{i}]"))
    return out


def _check_rolebinding(obj: dict, ns: str, rules: Rules, name: str) -> list[Violation]:
    out = []
    ref = obj.get("roleRef") if isinstance(obj.get("roleRef"), dict) else {}
    if ref.get("kind") != "Role":
        out.append(Violation("R-01", "RoleBinding", name, rules.msg("R-01", str(ref.get("name"))), "roleRef"))
    for i, s in enumerate(obj.get("subjects") or []):
        if not isinstance(s, dict) or s.get("kind") != "ServiceAccount" or s.get("namespace") not in (None, ns):
            out.append(Violation("R-02", "RoleBinding", name, rules.msg("R-02"), f"subjects[{i}]"))
    return out


def check_objects(docs: Iterable[Any], app_id: str, manifest: dict, rules: Rules) -> list[Violation]:
    """Every rendered object against the rule file. Empty list = allowed."""
    ns = f"app-{app_id}"
    level, gv = pod_security_level(app_id, manifest, rules)
    out: list[Violation] = [gv] if gv else []
    reviewed = rules.reviewed.get(app_id) or {}
    caps_allowed = rules.caps_allowed | frozenset(reviewed.get("add_capabilities") or [])
    for idx, obj in enumerate(docs):
        if not isinstance(obj, dict) or not obj.get("kind") or not obj.get("apiVersion"):
            out.append(Violation("G-02", "?", f"#{idx}", rules.msg("G-02")))
            continue
        kind, api = str(obj["kind"]), str(obj["apiVersion"])
        md = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        name = str(md.get("name") or md.get("generateName") or f"#{idx}")
        if kind.endswith("List") and isinstance(obj.get("items"), list):
            out.append(Violation("K-01", kind, name, rules.msg("K-01", "lists are not allowed")))
            continue
        if (api, kind) not in rules.allow:
            out.append(Violation("K-01", kind, name, rules.msg("K-01", f"{api} {kind}")))
            continue
        if md.get("namespace") not in (None, ns):
            out.append(Violation("N-01", kind, name, rules.msg("N-01", str(md.get("namespace"))), "metadata.namespace"))
        spec = obj.get("spec") if isinstance(obj.get("spec"), dict) else {}
        if kind == "Service":
            stype = spec.get("type") or "ClusterIP"
            if stype not in rules.service_types:
                out.append(Violation("V-01", kind, name, rules.msg("V-01", stype), "spec.type"))
            if spec.get("externalIPs"):
                out.append(Violation("V-02", kind, name, rules.msg("V-02"), "spec.externalIPs"))
        elif kind == "PersistentVolumeClaim":
            sc = spec.get("storageClassName")
            if sc not in rules.storage_classes:
                out.append(Violation("P-01", kind, name, rules.msg("P-01", str(sc)), "spec.storageClassName"))
        elif kind == "Role":
            out.extend(_check_role(obj, rules, name))
        elif kind == "RoleBinding":
            out.extend(_check_rolebinding(obj, ns, rules, name))
        elif kind == "StatefulSet":
            for i, t in enumerate(spec.get("volumeClaimTemplates") or []):
                sc = ((t or {}).get("spec") or {}).get("storageClassName")
                if sc not in rules.storage_classes:
                    out.append(Violation("P-01", kind, name, rules.msg("P-01", str(sc)), f"spec.volumeClaimTemplates[{i}]"))
        pod, base = _pod_spec(obj)
        if isinstance(pod, dict):
            out.extend(_check_pod(pod, base, level, caps_allowed, rules, kind, name))
            if rules.require_digest:
                for c, cpath in _containers(pod, base):
                    image = str(c.get("image") or "")
                    if not _DIGEST.search(image):
                        out.append(Violation("I-01", kind, name, rules.msg("I-01", image or "<none>"), f"{cpath}.image"))
    return out


def summarize(docs: Iterable[Any]) -> dict:
    """What the approval card and the action result show: kinds, names and images."""
    objects, images = [], []
    for obj in docs:
        if not isinstance(obj, dict):
            continue
        md = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        objects.append({"kind": obj.get("kind"), "name": md.get("name")})
        pod, base = _pod_spec(obj)
        if isinstance(pod, dict):
            images.extend(str(c.get("image")) for c, _ in _containers(pod, base) if c.get("image"))
    return {"objects": objects, "images": sorted(set(images))}


# ---- network ------------------------------------------------------------------------------------

def egress_entries(app_id: str, manifest: dict, rules: Rules) -> tuple[list[str], list[Violation]]:
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    net = spec.get("network") if isinstance(spec, dict) else None
    declared = net.get("egress") if isinstance(net, dict) else None
    if declared is None:
        return list(rules.default_egress), []
    if not isinstance(declared, list):
        return [], [Violation("X-01", "App", app_id, rules.msg("X-01", "not a list"), "spec.network.egress")]
    out, bad = [], []
    for i, e in enumerate(declared):
        if e in ("internet", "none"):
            out.append(e)
            continue
        try:
            out.append(str(ipaddress.ip_network(str(e), strict=False)))
        except ValueError:
            bad.append(Violation("X-01", "App", app_id, rules.msg("X-01", str(e)), f"spec.network.egress[{i}]"))
    return out, bad


def network_policies(
    app_id: str, egress: list[str], rules: Rules, extra_egress: Iterable[tuple[str, int | None]] = ()
) -> list[dict]:
    """Default-deny for app-<id>, then the allowances: own namespace, DNS, the proxy, declared egress.

    extra_egress: (cidr, port) pairs the gateway adds itself; for an agent app, the gateway's own
    address and port, which `internet` excludes when it is on the LAN.
    """
    ns = f"app-{app_id}"
    labels = {"onemind.io/app": app_id, "onemind.io/managed-by": "onemind-gateway"}
    deny = {
        "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": "onemind-default-deny", "namespace": ns, "labels": labels},
        "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
    }
    ingress: list[dict] = [{"from": [{"podSelector": {}}]}]
    if rules.proxy_label:
        ingress.append({"from": [{"namespaceSelector": {"matchLabels": dict(rules.proxy_label)}}]})
    egress_rules: list[dict] = [
        {"to": [{"podSelector": {}}]},
        {
            "to": [{
                "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
            }],
            "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}],
        },
    ]
    blocks: list[dict] = []
    if "internet" in egress and "none" not in egress:
        v4 = [c for c in rules.internet_except if ipaddress.ip_network(c).version == 4]
        v6 = [c for c in rules.internet_except if ipaddress.ip_network(c).version == 6]
        blocks.append({"ipBlock": {"cidr": "0.0.0.0/0", "except": v4}})
        blocks.append({"ipBlock": {"cidr": "::/0", "except": v6}})
    if "none" not in egress:
        blocks.extend({"ipBlock": {"cidr": c}} for c in egress if c not in ("internet", "none"))
    if blocks:
        egress_rules.append({"to": blocks})
    for cidr, port in extra_egress:
        r: dict = {"to": [{"ipBlock": {"cidr": cidr}}]}
        if port:
            r["ports"] = [{"protocol": "TCP", "port": port}]
        egress_rules.append(r)
    allow = {
        "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": "onemind-allow", "namespace": ns, "labels": labels},
        "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"], "ingress": ingress, "egress": egress_rules},
    }
    return [deny, allow]
