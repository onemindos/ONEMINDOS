# SPDX-License-Identifier: Apache-2.0
"""Docker Compose -> a private OneMind app folder (contract §12.22, PD-13; DEPLOYMENTS.md §3.1).

Our own minimal mapper (no converter dependency): every service becomes a Deployment, its ports a
ClusterIP Service, its named volumes PersistentVolumeClaims. The result is returned as files; the
conversion writes nothing and installs nothing.

It refuses, with the install sandbox's rule ids, everything the sandbox would refuse, so the
owner learns at import time rather than at approval:

| Compose | Rule | Why |
|---|---|---|
| `privileged: true` | F-06 | a privileged container is root on the host |
| `network_mode: host`, `pid: host`, `ipc: host` | F-01, F-02, F-03 | the host's namespaces |
| bind mounts (`./x:/y`, `/x:/y`, `type: bind`), volume `driver_opts` | F-04 | host paths |
| `cap_add` other than NET_BIND_SERVICE | F-07 | widened capabilities |
| `user: root` / `0` | S-01 | restricted pods run as non-root |
| image without `@sha256:` | I-01 | what was scanned must be what runs |
| `devices`, `security_opt`, `sysctls`, `userns_mode`, `cgroup_parent`, `uts` | C-06…C-08, C-10 | host devices and kernel settings |
| `build`, `env_file`, `secrets`, `configs`, `${VAR}` without default | C-02…C-05 | nothing is built or read from the host |
| any key it does not understand | C-01 | unknown means unchecked |

Published host ports are not refused: they become Service ports reached through the gateway, with
a warning (declare `spec.hostPorts` by hand only if the app must be on the host).
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import shlex
from dataclasses import dataclass, field
from typing import Any

import yaml

from ..catalog import APP_ID_RE

MAX_COMPOSE_BYTES = 256 * 1024
MAX_NODES = 20000
MAX_DEPTH = 100
MAX_SERVICES = 20
LABEL_RE = re.compile(r"^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$")
DIGEST_IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/:-]*(:[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,254}$")
SECRETISH_RE = re.compile(r"(password|secret|token|api_?key|private_?key)", re.IGNORECASE)
_VAR = re.compile(r"\$(\$|\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-?])([^}]*))?\}|[A-Za-z_][A-Za-z0-9_]*)")

TOP_KEYS = {"services", "volumes", "networks", "name", "version"}
TOP_REFUSED = {"secrets": "C-05", "configs": "C-05", "include": "C-02", "models": "C-01"}
SERVICE_KEYS = {
    "image", "command", "entrypoint", "environment", "ports", "expose", "volumes", "tmpfs", "working_dir",
    "user", "restart", "depends_on", "healthcheck", "labels", "container_name", "hostname", "deploy",
    "mem_limit", "mem_reservation", "cpus", "read_only", "stop_grace_period", "stop_signal", "init", "tty",
    "stdin_open", "networks", "extra_hosts", "logging", "platform", "pull_policy", "cap_drop", "cap_add",
    "network_mode", "privileged", "pid", "ipc", "ulimits", "domainname",
}
SERVICE_REFUSED = {
    "build": ("C-02", "nothing is built on the box; build and push the image, then pin its digest"),
    "env_file": ("C-04", "env files are read from the host; put the variables under environment"),
    "devices": ("C-06", "host devices are not allowed"),
    "device_cgroup_rules": ("C-06", "host devices are not allowed"),
    "gpus": ("C-06", "GPU access is declared in spec.requires.gpu, not in Compose"),
    "security_opt": ("C-07", "security options (seccomp, apparmor) are set by OneMind"),
    "sysctls": ("C-08", "kernel settings are not allowed"),
    "volumes_from": ("C-09", "sharing another container's volumes is not supported"),
    "links": ("C-09", "links are not needed: services reach each other by name"),
    "external_links": ("C-09", "external containers are not reachable"),
    "userns_mode": ("C-10", "the host user namespace is not allowed"),
    "uts": ("C-10", "the host UTS namespace is not allowed"),
    "cgroup_parent": ("C-10", "cgroup placement is not allowed"),
    "cgroup": ("C-10", "cgroup placement is not allowed"),
    "secrets": ("C-05", "Compose secrets read host files; use spec.secrets after import"),
    "configs": ("C-05", "Compose configs read host files; use a ConfigMap after import"),
    "isolation": ("C-10", "isolation modes are not supported"),
    "runtime": ("C-10", "container runtimes are chosen by OneMind"),
    "oom_kill_disable": ("C-10", "OOM settings are not allowed"),
    "oom_score_adj": ("C-10", "OOM settings are not allowed"),
    "shm_size": ("C-10", "shared memory size needs a reviewed volume; not converted"),
    "extends": ("C-02", "extends reads other files; inline the service"),
}
IGNORED = {"restart", "depends_on", "healthcheck", "labels", "container_name", "hostname", "logging",
           "platform", "pull_policy", "stop_signal", "init", "tty", "stdin_open", "networks", "ulimits",
           "cap_drop", "domainname", "stop_grace_period"}
DEFAULT_REQUESTS = {"cpu": "50m", "memory": "64Mi"}
DEFAULT_LIMITS = {"cpu": "1", "memory": "512Mi"}


class ComposeError(ValueError):
    """The input is not a Compose document we can read at all (422)."""


@dataclass
class Result:
    app_id: str
    files: dict[str, str] = field(default_factory=dict)
    refusals: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refusals

    def refuse(self, service: str | None, rule: str, fld: str, message: str) -> None:
        self.refusals.append({"service": service, "rule": rule, "field": fld, "message": message})

    def to_json(self) -> dict:
        return {"ok": self.ok, "app_id": self.app_id, "files": self.files if self.ok else {},
                "refusals": self.refusals, "warnings": self.warnings}


def check_expansion(doc: Any, limit: int = MAX_NODES) -> None:
    """Raise ComposeError when the document, with YAML aliases expanded, has more than `limit`
    nodes. Aliases share objects, so loading is cheap, but anything that walks the document (a
    schema validator, a serializer) pays the expanded size: the "billion laughs" attack."""
    budget = [limit]

    def walk(node: Any, depth: int = 1) -> None:
        budget[0] -= 1
        if budget[0] < 0:
            raise ComposeError(f"the document expands to more than {limit} nodes")
        if depth > MAX_DEPTH:
            raise ComposeError(f"the document is nested more than {MAX_DEPTH} levels deep")
        if isinstance(node, dict):
            for k, v in node.items():
                walk(k, depth + 1)
                walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)

    walk(doc)


def _label(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")[:63].strip("-")


class _Converter:
    def __init__(self, app_id: str, name: str | None, res: Result):
        self.app_id, self.name, self.res = app_id, name, res
        self.objects: list[tuple[str, dict]] = []
        self.pvcs: dict[str, str] = {}  # compose volume name -> PVC name
        self.web_port: int | None = None
        self.memory_mb = 0

    # -- interpolation: ${VAR:-default} -> default; ${VAR} with no default is refused --------------
    def interp(self, svc: str, fld: str, value: Any) -> Any:
        if isinstance(value, str):
            def sub(m: re.Match) -> str:
                if m.group(1) == "$":
                    return "$"
                if m.group(3) in ("-", ":-") and m.group(4) is not None:
                    return m.group(4)
                self.res.refuse(svc, "C-04", fld, f"{m.group(0)} reads the host environment; write the value")
                return ""
            return _VAR.sub(sub, value)
        if isinstance(value, list):
            return [self.interp(svc, fld, v) for v in value]
        if isinstance(value, dict):
            return {k: self.interp(svc, fld, v) for k, v in value.items()}
        return value

    def top_volumes(self, vols: Any) -> None:
        if vols is None:
            return
        if not isinstance(vols, dict):
            self.res.refuse(None, "C-01", "volumes", "top-level volumes must be a mapping")
            return
        for vname, spec in vols.items():
            spec = spec or {}
            if not isinstance(spec, dict):
                self.res.refuse(None, "C-01", f"volumes.{vname}", "must be a mapping")
                continue
            if spec.get("driver_opts") or spec.get("driver") not in (None, "local"):
                self.res.refuse(None, "F-04", f"volumes.{vname}", "volume drivers and driver_opts can bind host paths")
            if spec.get("external"):
                self.res.refuse(None, "C-09", f"volumes.{vname}", "external volumes do not exist on OneMind")
            unknown = set(spec) - {"driver", "driver_opts", "external", "labels", "name"}
            if unknown:
                self.res.refuse(None, "C-01", f"volumes.{vname}", f"unknown keys {sorted(unknown)}")
            pvc = _label(f"{vname}")
            if not LABEL_RE.match(pvc or "-") or pvc in self.pvcs.values():
                self.res.refuse(None, "C-01", f"volumes.{vname}", "volume name does not map to a unique DNS label")
                continue
            self.pvcs[str(vname)] = pvc

    def mount(self, svc: str, i: int, raw: Any, mounts: list, volumes: dict) -> None:
        fld = f"services.{svc}.volumes[{i}]"
        if isinstance(raw, str):
            parts = raw.split(":")
            if len(parts) == 1:
                src, dst, mode = None, parts[0], ""
            else:
                src, dst, mode = parts[0], parts[1], (parts[2] if len(parts) > 2 else "")
            kind = "volume" if src else "anonymous"
            if src and (src.startswith(("/", ".", "~")) or "/" in src or src == "."):
                kind = "bind"
            read_only = "ro" in mode.split(",")
        elif isinstance(raw, dict):
            kind, src, dst = raw.get("type", "volume"), raw.get("source"), raw.get("target")
            read_only = bool(raw.get("read_only"))
            if kind == "volume" and not src:
                kind = "anonymous"
            unknown = set(raw) - {"type", "source", "target", "read_only", "volume", "tmpfs", "consistency"}
            if unknown:
                self.res.refuse(svc, "C-01", fld, f"unknown keys {sorted(unknown)}")
        else:
            self.res.refuse(svc, "C-01", fld, "must be a string or a mapping")
            return
        if not isinstance(dst, str) or not dst.startswith("/"):
            self.res.refuse(svc, "C-01", fld, "target must be an absolute path in the container")
            return
        if kind == "bind":
            self.res.refuse(svc, "F-04", fld, f"bind mount of host path {src!r} is not allowed; use a named volume")
            return
        if kind == "tmpfs":
            vol = _label(f"tmp-{len(volumes)}")
            volumes[vol] = {"name": vol, "emptyDir": {"medium": "Memory"}}
        elif kind == "anonymous":
            vol = _label(f"anon-{len(volumes)}")
            volumes[vol] = {"name": vol, "emptyDir": {}}
            self.res.warnings.append(f"{fld}: anonymous volume {dst} becomes an emptyDir; its data is lost on restart")
        elif kind == "volume":
            if src not in self.pvcs:
                self.res.refuse(svc, "C-01", fld, f"volume {src!r} is not declared under top-level volumes")
                return
            vol = self.pvcs[src]
            volumes[vol] = {"name": vol, "persistentVolumeClaim": {"claimName": vol}}
        else:
            self.res.refuse(svc, "C-01", fld, f"volume type {kind!r} is not supported")
            return
        mounts.append({"name": vol, "mountPath": dst, **({"readOnly": True} if read_only else {})})

    def ports(self, svc: str, raw: Any, expose: Any) -> list[dict]:
        out: dict[tuple[int, str], dict] = {}

        def add(target: Any, proto: str, fld: str) -> None:
            try:
                port = int(target)
            except (TypeError, ValueError):
                self.res.refuse(svc, "C-01", fld, f"port {target!r} is not a number (ranges are not supported)")
                return
            if not 1 <= port <= 65535 or proto not in ("tcp", "udp"):
                self.res.refuse(svc, "C-01", fld, "port must be 1-65535 over tcp or udp")
                return
            out[(port, proto)] = {"name": f"{proto}-{port}", "port": port, "targetPort": port,
                                  "protocol": proto.upper()}

        for i, p in enumerate(raw or []):
            fld = f"services.{svc}.ports[{i}]"
            if isinstance(p, (int, str)):
                text = str(p)
                body, _, proto = text.partition("/")
                pieces = body.split(":")
                target = pieces[-1]
                published = pieces[-2] if len(pieces) >= 2 else None
                add(target, proto or "tcp", fld)
            elif isinstance(p, dict):
                target, published, proto = p.get("target"), p.get("published"), p.get("protocol", "tcp")
                add(target, proto, fld)
            else:
                self.res.refuse(svc, "C-01", fld, "must be a string, number or mapping")
                continue
            if published:
                self.res.warnings.append(
                    f"{fld}: host port {published} is not published; the app is reached through the gateway "
                    "(declare spec.hostPorts only if it must listen on the host)"
                )
            if self.web_port is None and (port := next(iter(out), None)):
                self.web_port = port[0]
        for i, p in enumerate(expose or []):
            body, _, proto = str(p).partition("/")
            add(body, proto or "tcp", f"services.{svc}.expose[{i}]")
        return list(out.values())

    def env(self, svc: str, raw: Any) -> list[dict]:
        items: list[tuple[str, Any]] = []
        if isinstance(raw, dict):
            items = list(raw.items())
        elif isinstance(raw, list):
            for e in raw:
                k, sep, v = str(e).partition("=")
                items.append((k, v if sep else None))
        elif raw is not None:
            self.res.refuse(svc, "C-01", f"services.{svc}.environment", "must be a mapping or a list")
        out = []
        for k, v in items:
            fld = f"services.{svc}.environment.{k}"
            if not isinstance(k, str) or not ENV_NAME_RE.match(k):
                self.res.refuse(svc, "C-01", fld, "not a valid variable name")
                continue
            if v is None:
                self.res.refuse(svc, "C-04", fld, "a variable without a value is read from the host environment")
                continue
            if isinstance(v, bool):
                v = "true" if v else "false"
            if isinstance(v, (dict, list)):
                self.res.refuse(svc, "C-01", fld, "value must be a scalar")
                continue
            if SECRETISH_RE.search(k):
                self.res.warnings.append(f"{fld}: looks like a credential; after import move it to spec.secrets")
            out.append({"name": k, "value": str(v)})
        return out

    def user(self, svc: str, raw: Any) -> dict:
        if raw is None:
            self.res.warnings.append(
                f"services.{svc}.user: not set; the pod requires a non-root user (runAsNonRoot), so an image "
                "that starts as root will not start until you set user: <uid>"
            )
            return {}
        uid, _, gid = str(raw).partition(":")
        if uid in ("0", "root") or gid in ("0", "root"):
            self.res.refuse(svc, "S-01", f"services.{svc}.user", "containers must run as a non-root user")
            return {}
        out: dict[str, int] = {}
        if uid.isdigit():
            out["runAsUser"] = int(uid)
        else:
            self.res.warnings.append(f"services.{svc}.user: named user {uid!r} cannot be checked; use a numeric uid")
        if gid.isdigit():
            out["runAsGroup"] = int(gid)
        return out

    def resources(self, svc: str, s: dict) -> dict:
        limits = dict(DEFAULT_LIMITS)
        requests = dict(DEFAULT_REQUESTS)
        dep = s.get("deploy") if isinstance(s.get("deploy"), dict) else {}
        res = dep.get("resources") if isinstance(dep.get("resources"), dict) else {}
        lim = res.get("limits") if isinstance(res.get("limits"), dict) else {}
        cpus = lim.get("cpus", s.get("cpus"))
        mem = lim.get("memory", s.get("mem_limit"))
        if cpus is not None:
            try:
                milli = int(float(cpus) * 1000)
                if milli > 0:
                    limits["cpu"] = f"{milli}m"
                    requests["cpu"] = f"{min(milli, 50)}m"
            except (TypeError, ValueError):
                self.res.warnings.append(f"services.{svc}: cpus {cpus!r} not understood; default limit kept")
        if mem is not None:
            mib = _mebibytes(mem)
            if mib:
                limits["memory"] = f"{mib}Mi"
                requests["memory"] = f"{min(mib, 64)}Mi"
            else:
                self.res.warnings.append(f"services.{svc}: memory {mem!r} not understood; default limit kept")
        self.memory_mb += int(requests["memory"].removesuffix("Mi"))
        return {"requests": requests, "limits": limits}

    def service(self, name: str, s: Any) -> None:
        res = self.res
        if not isinstance(s, dict):
            res.refuse(name, "C-01", f"services.{name}", "must be a mapping")
            return
        svc = _label(name)
        if not LABEL_RE.match(svc or "-"):
            res.refuse(name, "C-01", f"services.{name}", "service name does not map to a DNS label")
            return
        if svc != name:
            res.warnings.append(f"services.{name}: renamed {svc!r}; other services must use that name to reach it")
        for key in s:
            if key in SERVICE_REFUSED:
                rule, why = SERVICE_REFUSED[key]
                res.refuse(name, rule, f"services.{name}.{key}", why)
            elif key not in SERVICE_KEYS and not str(key).startswith("x-"):
                res.refuse(name, "C-01", f"services.{name}.{key}", "not understood, so not converted")
        s = self.interp(name, f"services.{name}", s)
        if s.get("privileged"):
            res.refuse(name, "F-06", f"services.{name}.privileged", "privileged containers are not allowed")
        nm = s.get("network_mode")
        if nm == "host":
            res.refuse(name, "F-01", f"services.{name}.network_mode", "host networking is not allowed")
        elif nm not in (None, "bridge", "default"):
            res.refuse(name, "C-09", f"services.{name}.network_mode", f"network_mode {nm!r} is not supported")
        for key, rule in (("pid", "F-02"), ("ipc", "F-03")):
            v = s.get(key)
            if v == "host":
                res.refuse(name, rule, f"services.{name}.{key}", f"the host {key.upper()} namespace is not allowed")
            elif v not in (None, "private"):
                res.refuse(name, "C-09", f"services.{name}.{key}", f"{key} {v!r} shares another namespace")
        caps = s.get("cap_add") or []
        add = []
        for cap in caps if isinstance(caps, list) else [caps]:
            c = str(cap).upper().removeprefix("CAP_")
            if c == "NET_BIND_SERVICE":
                add.append(c)
            else:
                res.refuse(name, "F-07", f"services.{name}.cap_add", f"capability {c} is not on the reviewed list")
        image = s.get("image")
        if not isinstance(image, str) or not image:
            res.refuse(name, "C-02", f"services.{name}.image", "every service needs an image")
        elif not DIGEST_IMAGE_RE.match(image):
            res.refuse(name, "I-01", f"services.{name}.image",
                       f"{image} is not pinned by digest; use name:tag@sha256:<digest>")
        for key in sorted(set(s) & IGNORED):
            res.warnings.append(f"services.{name}.{key}: ignored")
        if s.get("restart") == "no":
            res.warnings.append(f"services.{name}.restart: 'no' is not possible; Kubernetes restarts containers")
        mounts: list[dict] = []
        volumes: dict[str, dict] = {}
        for i, raw in enumerate(s.get("volumes") or []):
            self.mount(name, i, raw, mounts, volumes)
        tmpfs = s.get("tmpfs") or []
        for path in [tmpfs] if isinstance(tmpfs, str) else tmpfs:
            self.mount(name, len(mounts), {"type": "tmpfs", "target": str(path).split(":")[0]}, mounts, volumes)
        ports = self.ports(name, s.get("ports"), s.get("expose"))
        env = self.env(name, s.get("environment"))
        user = self.user(name, s.get("user"))
        container: dict[str, Any] = {"name": svc, "image": image}
        for key, target in (("entrypoint", "command"), ("command", "args")):
            v = s.get(key)
            if v is None:
                continue
            if isinstance(v, str):
                try:
                    v = shlex.split(v)
                except ValueError:
                    res.refuse(name, "C-01", f"services.{name}.{key}", "cannot split the command")
                    continue
            if not isinstance(v, list) or not all(isinstance(a, (str, int, float)) for a in v):
                res.refuse(name, "C-01", f"services.{name}.{key}", "must be a string or a list of strings")
                continue
            container[target] = [str(a) for a in v]
        if s.get("working_dir"):
            container["workingDir"] = str(s["working_dir"])
        if env:
            container["env"] = env
        if ports:
            container["ports"] = [{"name": p["name"], "containerPort": p["port"], "protocol": p["protocol"]}
                                  for p in ports]
        if mounts:
            container["volumeMounts"] = mounts
        container["resources"] = self.resources(name, s)
        container["securityContext"] = {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"], **({"add": add} if add else {})},
            "readOnlyRootFilesystem": bool(s.get("read_only")),
            "runAsNonRoot": True,
            **user,
        }
        labels = {"app.kubernetes.io/name": svc, "onemind.io/app": self.app_id}
        pod: dict[str, Any] = {
            "automountServiceAccountToken": False,
            "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [container],
        }
        if volumes:
            pod["volumes"] = list(volumes.values())
        hosts = s.get("extra_hosts")
        if hosts:
            aliases: dict[str, list[str]] = {}
            if isinstance(hosts, dict):
                pairs = [(str(h), str(ip)) for h, ip in hosts.items()]
            else:
                pairs = [(h, ip) for h, _, ip in (str(e).replace("=", ":", 1).partition(":") for e in hosts)]
            for host, ip in pairs:
                try:
                    ipaddress.ip_address(ip.strip("[]"))
                except ValueError:
                    res.refuse(name, "C-01", f"services.{name}.extra_hosts", f"{host}: {ip!r} is not an IP address")
                    continue
                aliases.setdefault(ip.strip("[]"), []).append(host)
            if aliases:
                pod["hostAliases"] = [{"ip": ip, "hostnames": hs} for ip, hs in aliases.items()]
        dep = s.get("deploy") if isinstance(s.get("deploy"), dict) else {}
        if dep.get("mode") == "global":
            res.refuse(name, "C-10", f"services.{name}.deploy.mode", "global mode runs on every node; not supported")
        replicas = dep.get("replicas", 1)
        if not isinstance(replicas, int) or isinstance(replicas, bool) or not 0 <= replicas <= 3:
            res.refuse(name, "C-01", f"services.{name}.deploy.replicas", "replicas must be 0-3")
            replicas = 1
        uses_pvc = any("persistentVolumeClaim" in v for v in volumes.values())
        self.objects.append((f"{svc}-deployment.yaml", {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": svc, "labels": labels},
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app.kubernetes.io/name": svc}},
                **({"strategy": {"type": "Recreate"}} if uses_pvc else {}),
                "template": {"metadata": {"labels": labels}, "spec": pod},
            },
        }))
        if ports:
            self.objects.append((f"{svc}-service.yaml", {
                "apiVersion": "v1", "kind": "Service",
                "metadata": {"name": svc, "labels": labels},
                "spec": {"type": "ClusterIP", "selector": {"app.kubernetes.io/name": svc},
                         "ports": [{"name": p["name"], "port": p["port"], "targetPort": p["port"],
                                    "protocol": p["protocol"]} for p in ports]},
            }))

    def finish(self, compose_sha: str) -> None:
        for vname, pvc in self.pvcs.items():
            self.objects.append((f"{pvc}-pvc.yaml", {
                "apiVersion": "v1", "kind": "PersistentVolumeClaim",
                "metadata": {"name": pvc, "labels": {"onemind.io/app": self.app_id}},
                "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "1Gi"}}},
            }))
            self.res.warnings.append(f"volumes.{vname}: PersistentVolumeClaim {pvc} asks for 1Gi; change it if needed")
        files = self.res.files
        for fname, obj in self.objects:
            files[f"manifests/{fname}"] = _dump(obj)
        files["manifests/kustomization.yaml"] = _dump({
            "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
            "resources": [f for f, _ in self.objects],
        })
        spec: dict[str, Any] = {
            "archs": ["amd64", "arm64"],
            "requires": {"gpu": False, "minMemoryMb": max(self.memory_mb, 64)},
            "manifests": "manifests/",
            "updates": {"channel": "stable", "automerge": "none"},
        }
        if self.web_port:
            spec["web"] = {"port": self.web_port}
        files["onemind.app.yaml"] = _dump({
            "apiVersion": "onemind.app/v1alpha1", "kind": "App",
            "metadata": {
                "id": self.app_id, "name": self.name or self.app_id, "version": "0.1.0",
                "description": "Private app imported from Docker Compose",
                "origin": "private",
                "annotations": {"onemind.io/compose-sha256": compose_sha},
            },
            "spec": spec,
        })
        self.res.warnings.append("spec.archs: set to amd64 and arm64; check that every pinned image has both")


def _mebibytes(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value // (1024 * 1024)) or None
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([kmgKMG]?)[iI]?[bB]?\s*", str(value))
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2).lower()
    mib = {"": n / (1024 * 1024), "k": n / 1024, "m": n, "g": n * 1024}[unit]
    return int(mib) or None


def _dump(obj: dict) -> str:
    return "# SPDX-License-Identifier: Apache-2.0\n# Generated by OneMind Compose import.\n" + yaml.safe_dump(
        obj, sort_keys=False, default_flow_style=False)


def convert(compose_text: str, app_id: str, name: str | None = None) -> Result:
    """Convert; raises ComposeError when the text is not a readable Compose document."""
    try:
        return _convert(compose_text, app_id, name)
    except RecursionError as exc:  # hostile nesting: PyYAML and every walker recurse per level
        raise ComposeError(f"the document is nested too deeply (at most {MAX_DEPTH} levels)") from exc



def _convert(compose_text: str, app_id: str, name: str | None = None) -> Result:
    if not isinstance(app_id, str) or not APP_ID_RE.match(app_id) or not LABEL_RE.match(app_id):
        raise ComposeError("app_id must be a DNS label starting with a letter (at most 59 characters)")
    data = compose_text.encode("utf-8")
    if len(data) > MAX_COMPOSE_BYTES:
        raise ComposeError(f"compose is larger than {MAX_COMPOSE_BYTES // 1024} KiB")
    try:
        doc = yaml.safe_load(compose_text)
    except yaml.YAMLError as exc:
        raise ComposeError(f"compose is not valid YAML ({exc.__class__.__name__})") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("services"), dict) or not doc["services"]:
        raise ComposeError("compose needs a services mapping")
    check_expansion(doc)
    res = Result(app_id=app_id)
    for key in doc:
        if key in TOP_REFUSED:
            res.refuse(None, TOP_REFUSED[key], str(key), f"top-level {key} is not supported")
        elif key not in TOP_KEYS and not str(key).startswith("x-"):
            res.refuse(None, "C-01", str(key), "not understood, so not converted")
    if "version" in doc:
        res.warnings.append("version: obsolete in Compose and ignored")
    if doc.get("networks"):
        res.warnings.append("networks: ignored; every service of the app shares one namespace")
    if len(doc["services"]) > MAX_SERVICES:
        raise ComposeError(f"at most {MAX_SERVICES} services")
    conv = _Converter(app_id, name, res)
    conv.top_volumes(doc.get("volumes"))
    for sname, s in doc["services"].items():
        conv.service(str(sname), s)
    names = [f for f, _ in conv.objects]
    if len(names) != len(set(names)):
        res.refuse(None, "C-01", "services", "two services map to the same Kubernetes name")
    conv.finish(hashlib.sha256(data).hexdigest())
    return res
