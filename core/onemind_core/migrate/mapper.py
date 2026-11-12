# SPDX-License-Identifier: Apache-2.0
"""Turn an old namespace into a private OneMind app, and say exactly what maps and what does not.

Pure functions over the inventory: no I/O, so every rule is unit-tested with fixtures.

Each finding has a level, shown by `onemind migrate plan` as one line:

| level | meaning |
|---|---|
| ok    | imported as it is |
| note  | imported as it is, but worth knowing (runs as root, no limits on a sidecar, ...) |
| fixed | imported with an automatic change (storage class, image pinned to the running digest, ...) |
| move  | the owner re-enters it on the box (secret values, registry credentials); never copied |
| drop  | not imported because OneMind does it itself (Ingress, node placement, RBAC) |
| skip  | not imported, and nothing replaces it yet (DaemonSet, CronJob, bare pod) |
| fail  | blocks the import (host paths, privileged containers, host network, unpinnable image) |
"""

from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass, field

from .inventory import Inventory

STORAGE_CLASS = "onemind-local"
LEVELS = ("ok", "note", "fixed", "move", "drop", "skip", "fail")
DIGEST_RE = re.compile(r"@(sha256:[0-9a-f]{64})$")
# PSA "baseline" allows these added capabilities; anything else is refused.
SAFE_CAPS = {
    "AUDIT_WRITE", "CHOWN", "DAC_OVERRIDE", "FOWNER", "FSETID", "KILL", "MKNOD", "NET_BIND_SERVICE",
    "SETFCAP", "SETGID", "SETPCAP", "SETUID", "SYS_CHROOT",
}
# Values the API server fills in by itself: removing them is not worth a report line.
SERVER_DEFAULTS = {"schedulerName": "default-scheduler", "priority": 0, "preemptionPolicy": "PreemptLowerPriority"}
DEFAULT_MEMORY_LIMIT = "1Gi"
DEFAULT_CPU_LIMIT = "1"
SKIP_CONFIGMAPS = {"kube-root-ca.crt"}
DROP_META_PREFIXES = ("kubectl.kubernetes.io/", "deployment.kubernetes.io/", "meta.helm.sh/")
POD_DROP_FIELDS = (
    "nodeSelector", "affinity", "tolerations", "nodeName", "schedulerName", "priorityClassName",
    "priority", "serviceAccountName", "serviceAccount", "topologySpreadConstraints", "runtimeClassName",
    "preemptionPolicy", "overhead", "hostAliases",
)


@dataclass
class Finding:
    level: str
    kind: str
    name: str
    message: str
    hint: str | None = None


@dataclass
class MapResult:
    app_id: str
    namespace: str
    findings: list[Finding] = field(default_factory=list)
    objects: list[dict] = field(default_factory=list)
    workloads: list[dict] = field(default_factory=list)  # {kind, name, replicas}
    volumes: list[dict] = field(default_factory=list)  # {pvc, size, used_by, node, bound}
    images: list[dict] = field(default_factory=list)  # {workload, container, ref, source}
    secrets: list[dict] = field(default_factory=list)  # {name, keys, all_keys, optional, used_by}
    hosts: list[str] = field(default_factory=list)
    web: dict | None = None  # {service, port}
    gpu: bool = False

    def add(self, level: str, kind: str, name: str, message: str, hint: str | None = None) -> None:
        assert level in LEVELS, level
        self.findings.append(Finding(level, kind, name, message, hint))

    @property
    def blocking(self) -> int:
        return sum(1 for f in self.findings if f.level == "fail")

    def counts(self) -> dict[str, int]:
        out = {lvl: 0 for lvl in LEVELS}
        for f in self.findings:
            out[f.level] += 1
        return out

    def report(self) -> dict:
        return {
            "app_id": self.app_id,
            "namespace": self.namespace,
            "blocking": self.blocking,
            "counts": self.counts(),
            "findings": [asdict(f) for f in self.findings],
            "workloads": self.workloads,
            "volumes": self.volumes,
            "images": self.images,
            "secrets": self.secrets,
            "hosts": self.hosts,
            "web": self.web,
        }


# ---- quantities --------------------------------------------------------------------------------
_SUFFIX = {
    "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "Pi": 2**50,
    "k": 10**3, "K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12, "P": 10**15, "m": 0.001, "": 1,
}
_QTY = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(Ki|Mi|Gi|Ti|Pi|k|K|M|G|T|P|m)?$")


def quantity(value: object) -> float | None:
    """A Kubernetes quantity in base units (bytes, cores), or None if it cannot be read."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    m = _QTY.match(value.strip())
    if not m:
        return None
    return float(m.group(1)) * _SUFFIX[m.group(2) or ""]


# ---- helpers -----------------------------------------------------------------------------------
def _meta(obj: dict) -> dict:
    return obj.get("metadata") or {}


def _name(obj: dict) -> str:
    return str(_meta(obj).get("name", ""))


def _clean_map(m: object) -> dict:
    if not isinstance(m, dict):
        return {}
    return {k: v for k, v in m.items() if not any(str(k).startswith(p) for p in DROP_META_PREFIXES)}


def _clean_meta(obj: dict, *, keep_annotations: bool = False) -> dict:
    md = _meta(obj)
    out: dict = {"name": md.get("name")}
    labels = _clean_map(md.get("labels"))
    if labels:
        out["labels"] = labels
    if keep_annotations:
        ann = _clean_map(md.get("annotations"))
        if ann:
            out["annotations"] = ann
    return out


def _selector_matches(selector: dict | None, labels: dict | None) -> bool:
    """matchLabels as a subset test. matchExpressions are not evaluated (used only to find digests)."""
    ml = (selector or {}).get("matchLabels") or {}
    labels = labels or {}
    return bool(ml) and all(labels.get(k) == v for k, v in ml.items())


def _pin(image: str, digest: str | None) -> str | None:
    if DIGEST_RE.search(image):
        return image
    if digest is None:
        return None
    return f"{image}@{digest}"


def _running_digests(pods: list[dict], container: str) -> list[str]:
    out = []
    for pod in pods:
        status = pod.get("status") or {}
        for cs in (status.get("containerStatuses") or []) + (status.get("initContainerStatuses") or []):
            if cs.get("name") != container:
                continue
            m = re.search(r"@(sha256:[0-9a-f]{64})$", str(cs.get("imageID") or ""))
            if m:
                out.append(m.group(1))
    return out


# ---- the mapper --------------------------------------------------------------------------------
class _Mapper:
    def __init__(self, inv: Inventory, app_id: str):
        self.inv = inv
        self.r = MapResult(app_id=app_id, namespace=inv.namespace)
        self.claims_used: dict[str, list[str]] = {}  # pvc -> workloads
        self.sts_templates: list[tuple[str, str, dict]] = []  # (sts, template name, template)
        self.secret_refs: dict[str, dict] = {}
        self.workload_pods: dict[str, list[dict]] = {}

    # pods ------------------------------------------------------------------------------------
    def pods_for(self, selector: dict | None) -> list[dict]:
        return [p for p in self.inv.of("Pod") if _selector_matches(selector, _meta(p).get("labels"))]

    def secret_ref(self, name: str, key: str | None, optional: bool, used_by: str) -> None:
        ref = self.secret_refs.setdefault(
            name, {"name": name, "keys": set(), "all_keys": False, "optional": True, "used_by": set()}
        )
        if key is None:
            ref["all_keys"] = True
        else:
            ref["keys"].add(key)
        ref["optional"] = ref["optional"] and optional
        ref["used_by"].add(used_by)

    # containers ------------------------------------------------------------------------------
    def container(self, c: dict, where: str, pods: list[dict]) -> dict | None:
        """Check and clean one container in place; returns None when it blocks the import."""
        r = self.r
        cname = c.get("name", "?")
        sc = c.get("securityContext") or {}
        ok = True
        if sc.get("privileged"):
            r.add("fail", "Container", f"{where}/{cname}", "privileged containers are not allowed",
                  "remove privileged: true in the source and re-run the plan")
            ok = False
        if sc.get("allowPrivilegeEscalation") is True:
            r.add("fail", "Container", f"{where}/{cname}", "allowPrivilegeEscalation: true is not allowed")
            ok = False
        added = set((sc.get("capabilities") or {}).get("add") or [])
        bad = sorted(cap for cap in added if str(cap).upper().removeprefix("CAP_") not in SAFE_CAPS)
        if bad:
            r.add("fail", "Container", f"{where}/{cname}", f"capabilities {', '.join(bad)} are not allowed")
            ok = False
        for p in c.get("ports") or []:
            if "hostPort" in p:
                p.pop("hostPort", None)
                p.pop("hostIP", None)
                r.add("fixed", "Container", f"{where}/{cname}", "hostPort removed; the app is reached through OneMind")
        image = str(c.get("image") or "")
        digests = _running_digests(pods, cname)
        digest = max(set(digests), key=digests.count) if digests else None
        pinned = _pin(image, digest)
        if pinned is None:
            r.add("fail", "Image", image or f"{where}/{cname}",
                  "no digest: the image is not pinned and no running pod shows which one runs",
                  "pin it as image@sha256:... in the source, or start the workload once, then re-run the plan")
            ok = False
        else:
            if pinned != image:
                r.add("fixed", "Image", image, f"pinned to the digest the old cluster runs ({digest[:19]}…)")
            if len(set(digests)) > 1:
                r.add("note", "Image", image, "pods run different digests (a rollout in progress?); the most common one was used")
            c["image"] = pinned
            r.images.append({"workload": where, "container": cname, "ref": pinned, "source": image})
        res = c.setdefault("resources", {})
        limits = res.setdefault("limits", {})
        requests = res.get("requests") or {}
        if "nvidia.com/gpu" in limits or "nvidia.com/gpu" in requests:
            r.gpu = True
            r.add("note", "Container", f"{where}/{cname}", "asks for an NVIDIA GPU; it runs only on a GPU node")
        added_limits = []
        if "memory" not in limits:
            req = quantity(requests.get("memory"))
            limits["memory"] = requests["memory"] if req and req > quantity(DEFAULT_MEMORY_LIMIT) else DEFAULT_MEMORY_LIMIT
            added_limits.append(f"memory {limits['memory']}")
        if "cpu" not in limits:
            req = quantity(requests.get("cpu"))
            limits["cpu"] = requests["cpu"] if req and req > quantity(DEFAULT_CPU_LIMIT) else DEFAULT_CPU_LIMIT
            added_limits.append(f"cpu {limits['cpu']}")
        if added_limits:
            r.add("fixed", "Container", f"{where}/{cname}", f"no limit set; added {', '.join(added_limits)}",
                  "review the limits before switching over")
        for env in c.get("env") or []:
            ref = (env.get("valueFrom") or {}).get("secretKeyRef")
            if isinstance(ref, dict) and ref.get("name"):
                self.secret_ref(str(ref["name"]), str(ref.get("key")), bool(ref.get("optional")), where)
        for src in c.get("envFrom") or []:
            ref = src.get("secretRef")
            if isinstance(ref, dict) and ref.get("name"):
                self.secret_ref(str(ref["name"]), None, bool(ref.get("optional")), where)
        return c if ok else None

    # pod template ---------------------------------------------------------------------------
    def pod_spec(self, kind: str, name: str, spec: dict, pods: list[dict]) -> bool:
        r, where = self.r, f"{kind}/{name}"
        ok = True
        for flag in ("hostNetwork", "hostPID", "hostIPC"):
            if spec.get(flag):
                r.add("fail", kind, name, f"{flag}: true is not allowed (apps never share the host's namespaces)")
                ok = False
        original = dict(spec)
        dropped = [f for f in POD_DROP_FIELDS if f in spec]
        sa = spec.get("serviceAccountName") or spec.get("serviceAccount")
        for f in dropped:
            spec.pop(f, None)
        if spec.get("dnsPolicy") == "ClusterFirstWithHostNet":
            spec.pop("dnsPolicy")
        placement = [f for f in dropped if f not in ("serviceAccountName", "serviceAccount")
                     and SERVER_DEFAULTS.get(f, object()) != original.get(f)]
        if placement:
            r.add("drop", kind, name, f"{', '.join(placement)} removed; OneMind places apps on its own nodes")
        if sa and sa != "default":
            r.add("drop", kind, name, f"service account {sa} not imported; the app gets no Kubernetes API token",
                  "apps on OneMind never get Kubernetes API access (RBAC is never imported)")
        spec["automountServiceAccountToken"] = False
        for ips in spec.pop("imagePullSecrets", None) or []:
            if isinstance(ips, dict) and ips.get("name"):
                r.add("move", "Secret", str(ips["name"]), "registry credentials are not copied",
                      f"add pull credentials for {name} on the box (CORE-DEPLOY-4) before switching over")
        volumes = spec.get("volumes") or []
        for v in volumes:
            vname = v.get("name", "?")
            if "persistentVolumeClaim" in v:
                claim = str((v["persistentVolumeClaim"] or {}).get("claimName"))
                self.claims_used.setdefault(claim, []).append(where)
            elif "hostPath" in v:
                r.add("fail", kind, name, f"volume {vname} is a hostPath; host folders are never given to apps",
                      "move the data into a PersistentVolumeClaim in the old cluster first")
                ok = False
            elif "secret" in v:
                sec = v["secret"] or {}
                items = [i.get("key") for i in sec.get("items") or [] if isinstance(i, dict)]
                if sec.get("secretName"):
                    if items:
                        for key in items:
                            self.secret_ref(str(sec["secretName"]), str(key), bool(sec.get("optional")), where)
                    else:
                        self.secret_ref(str(sec["secretName"]), None, bool(sec.get("optional")), where)
            elif "projected" in v:
                for src in (v["projected"] or {}).get("sources") or []:
                    if "secret" in src and (src["secret"] or {}).get("name"):
                        self.secret_ref(str(src["secret"]["name"]), None, bool(src["secret"].get("optional")), where)
                    if "serviceAccountToken" in src:
                        r.add("drop", kind, name, f"volume {vname}: service account tokens are not given to apps")
            elif any(k in v for k in ("configMap", "emptyDir", "downwardAPI")):
                pass
            else:
                other = next((k for k in v if k != "name"), "unknown")
                r.add("fail", kind, name, f"volume {vname} of type {other} is not supported",
                      "only PersistentVolumeClaims, ConfigMaps, Secrets, emptyDir and downwardAPI move")
                ok = False
        containers = []
        for group in ("initContainers", "containers"):
            cleaned = []
            for c in spec.get(group) or []:
                out = self.container(c, where, pods)
                ok = ok and out is not None
                cleaned.append(c)
            if cleaned:
                spec[group] = cleaned
            containers.extend(cleaned)
        if any(((c.get("securityContext") or {}).get("runAsUser") == 0) for c in containers) or (
            (spec.get("securityContext") or {}).get("runAsUser") == 0
        ):
            r.add("note", kind, name, "runs as root (UID 0)", "prefer a non-root image when you can")
        return ok

    # workloads ------------------------------------------------------------------------------
    def workload(self, obj: dict, kind: str) -> None:
        r, name = self.r, _name(obj)
        before = len(r.findings)
        src = obj.get("spec") or {}
        spec = copy.deepcopy(src)
        replicas = spec.get("replicas", 1)
        replicas = replicas if isinstance(replicas, int) and replicas >= 0 else 1
        template = spec.get("template") or {}
        pod_spec = template.get("spec") or {}
        pods = self.pods_for(spec.get("selector"))
        ok = self.pod_spec(kind, name, pod_spec, pods)
        template_meta = _clean_meta(template, keep_annotations=True)
        template_meta.pop("name", None)
        template["metadata"] = template_meta
        spec.pop("revisionHistoryLimit", None)
        if kind == "StatefulSet":
            policy = spec.get("persistentVolumeClaimRetentionPolicy") or {}
            if "Delete" in (policy.get("whenDeleted"), policy.get("whenScaled")):
                r.add("fixed", kind, name, "volume retention set to Retain; OneMind deletes data only by an approved action")
            spec["persistentVolumeClaimRetentionPolicy"] = {"whenDeleted": "Retain", "whenScaled": "Retain"}
            templates = []
            for tpl in spec.get("volumeClaimTemplates") or []:
                tname = _name(tpl)
                tspec = self.pvc_spec(tpl.get("spec") or {}, "StatefulSet", f"{name}/{tname}")
                templates.append({"metadata": {"name": tname}, "spec": tspec})
                self.sts_templates.append((name, tname, tspec))
            if templates:
                spec["volumeClaimTemplates"] = templates
            svc = spec.get("serviceName")
            if svc and not any(_name(s) == svc for s in self.inv.of("Service")):
                r.add("note", kind, name, f"its governing Service {svc} does not exist in the namespace")
        if not ok:
            return
        api = "apps/v1"
        self.r.objects.append({"apiVersion": api, "kind": kind, "metadata": _clean_meta(obj), "spec": spec})
        selector = dict((spec.get("selector") or {}).get("matchLabels") or {})
        self.r.workloads.append({"kind": kind, "name": name, "replicas": replicas, "selector": selector})
        self.workload_pods[f"{kind}/{name}"] = pods
        if len(r.findings) == before:
            r.add("ok", kind, name, f"{replicas} replica(s)")

    # storage --------------------------------------------------------------------------------
    def pvc_spec(self, spec: dict, kind: str, name: str) -> dict:
        r = self.r
        out: dict = {"accessModes": ["ReadWriteOnce"], "storageClassName": STORAGE_CLASS}
        modes = spec.get("accessModes") or ["ReadWriteOnce"]
        if any(m != "ReadWriteOnce" for m in modes):
            r.add("fixed", kind, name, f"access mode {', '.join(modes)} → ReadWriteOnce (storage is local to a node)")
        sc = spec.get("storageClassName")
        if sc != STORAGE_CLASS:
            r.add("fixed", kind, name, f"storage class {sc or '(default)'} → {STORAGE_CLASS} (kept when the app is removed)")
        if spec.get("volumeMode") == "Block":
            r.add("fail", kind, name, "raw block volumes are not supported")
        size = ((spec.get("resources") or {}).get("requests") or {}).get("storage") or "1Gi"
        out["resources"] = {"requests": {"storage": size}}
        return out

    def pvcs(self) -> None:
        r = self.r
        sts_claims: dict[str, tuple[str, dict]] = {}
        for pvc in self.inv.of("PersistentVolumeClaim"):
            name = _name(pvc)
            for sts, tname, tspec in self.sts_templates:
                if re.fullmatch(rf"{re.escape(tname)}-{re.escape(sts)}-[0-9]+", name):
                    sts_claims[name] = (f"StatefulSet/{sts}", tspec)
        imported = {w["kind"] + "/" + w["name"] for w in r.workloads}
        for pvc in self.inv.of("PersistentVolumeClaim"):
            name = _name(pvc)
            spec = pvc.get("spec") or {}
            used_by = self.claims_used.get(name, [])
            if name in sts_claims:
                used_by = [sts_claims[name][0]]
            used_by = [u for u in used_by if u in imported]
            if not used_by:
                r.add("skip", "PersistentVolumeClaim", name, "not mounted by an imported workload; not copied")
                continue
            out_spec = self.pvc_spec(spec, "PersistentVolumeClaim", name)
            bound = (pvc.get("status") or {}).get("phase") == "Bound"
            labels = _clean_map(_meta(pvc).get("labels"))
            md = {"name": name, **({"labels": labels} if labels else {})}
            r.objects.append({"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": md, "spec": out_spec})
            node = None
            for wl in used_by:
                for pod in self.workload_pods.get(wl, []):
                    if (pod.get("status") or {}).get("phase") == "Running" and any(
                        (v.get("persistentVolumeClaim") or {}).get("claimName") == name
                        for v in (pod.get("spec") or {}).get("volumes") or []
                    ):
                        node = (pod.get("spec") or {}).get("nodeName")
            if bound:
                cap = ((pvc.get("status") or {}).get("capacity") or {}).get("storage")
                r.volumes.append({"pvc": name, "size": cap or out_spec["resources"]["requests"]["storage"],
                                  "used_by": used_by, "node": node})
            else:
                r.add("note", "PersistentVolumeClaim", name, "not bound in the old cluster; nothing to copy")
            if not any(f.name == name and f.kind == "PersistentVolumeClaim" for f in r.findings):
                r.add("ok", "PersistentVolumeClaim", name, f"{out_spec['resources']['requests']['storage']}")
        for claim, users in self.claims_used.items():
            if not any(_name(p) == claim for p in self.inv.of("PersistentVolumeClaim")):
                r.add("note", "PersistentVolumeClaim", claim, f"used by {', '.join(users)} but not found in the namespace")

    # services, config, ingress -----------------------------------------------------------------
    def services(self) -> None:
        r = self.r
        for svc in self.inv.of("Service"):
            name = _name(svc)
            spec = copy.deepcopy(svc.get("spec") or {})
            typ = spec.get("type", "ClusterIP")
            if typ == "ExternalName" or not spec.get("selector"):
                r.add("skip", "Service", name, "a Service without a selector (or ExternalName) points outside the app; not imported")
                continue
            out: dict = {"selector": spec["selector"], "ports": []}
            if spec.get("clusterIP") == "None":
                out["clusterIP"] = "None"
            if spec.get("publishNotReadyAddresses"):
                out["publishNotReadyAddresses"] = True
            for p in spec.get("ports") or []:
                p = {k: v for k, v in p.items() if k != "nodePort"}
                out["ports"].append(p)
            if typ in ("NodePort", "LoadBalancer"):
                r.add("fixed", "Service", name, f"type {typ} → ClusterIP; OneMind serves the app by name, never on node ports")
            else:
                r.add("ok", "Service", name, f"{len(out['ports'])} port(s)")
            r.objects.append({"apiVersion": "v1", "kind": "Service", "metadata": _clean_meta(svc), "spec": out})

    def configmaps(self) -> None:
        r = self.r
        for cm in self.inv.of("ConfigMap"):
            name = _name(cm)
            if name in SKIP_CONFIGMAPS:
                continue
            obj = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": _clean_meta(cm)}
            for key in ("data", "binaryData"):
                if cm.get(key):
                    obj[key] = cm[key]
            r.objects.append(obj)
            r.add("ok", "ConfigMap", name, f"{len(cm.get('data') or {}) + len(cm.get('binaryData') or {})} key(s)")

    def ingresses(self) -> None:
        r = self.r
        services = {_name(s): s for s in self.inv.of("Service")}
        for ing in self.inv.of("Ingress"):
            name = _name(ing)
            hosts = []
            for rule in (ing.get("spec") or {}).get("rules") or []:
                host = rule.get("host")
                if host:
                    hosts.append(host)
                for path in ((rule.get("http") or {}).get("paths")) or []:
                    backend = (path.get("backend") or {}).get("service") or {}
                    port = self._service_port(services.get(backend.get("name")), backend.get("port") or {})
                    if r.web is None and port is not None:
                        r.web = {"service": backend.get("name"), "port": port}
            r.hosts.extend(h for h in hosts if h not in r.hosts)
            target = f"https://{r.app_id}.onemind.local"
            r.add("drop", "Ingress", name, f"→ served by OneMind at {target}",
                  f"at switch-over, point {', '.join(hosts) or 'its hostnames'} at this box" if hosts else None)

    @staticmethod
    def _service_port(svc: dict | None, port: dict) -> int | None:
        if svc is None:
            return None
        if isinstance(port.get("number"), int):
            return port["number"]
        for p in (svc.get("spec") or {}).get("ports") or []:
            if p.get("name") == port.get("name"):
                return p.get("port")
        return None

    def others(self) -> None:
        r = self.r
        for ds in self.inv.of("DaemonSet"):
            r.add("skip", "DaemonSet", _name(ds), "runs on every node; not imported (OneMind places apps itself)")
        for cj in self.inv.of("CronJob"):
            r.add("skip", "CronJob", _name(cj), "not imported yet", "re-create it as a OneMind automation (AUTOMATION)")
        for job in self.inv.of("Job"):
            owners = _meta(job).get("ownerReferences") or []
            if not any(o.get("kind") == "CronJob" for o in owners):
                r.add("skip", "Job", _name(job), "one-off Jobs are not imported")
        for pod in self.inv.of("Pod"):
            if not _meta(pod).get("ownerReferences"):
                r.add("skip", "Pod", _name(pod), "a bare pod (no controller) is not imported")
        for kind, why in sorted(self.inv.not_read.items()):
            r.add("note", kind, "*", f"could not be read ({why}); the report may miss some {kind} objects")

    def secrets_findings(self) -> None:
        r = self.r
        for name in sorted(self.secret_refs):
            ref = self.secret_refs[name]
            keys = sorted(ref["keys"])
            r.secrets.append({
                "name": name, "keys": keys, "all_keys": ref["all_keys"], "optional": ref["optional"],
                "used_by": sorted(ref["used_by"]),
            })
            what = "all keys" if ref["all_keys"] else ", ".join(keys)
            r.add("move", "Secret", name, f"values are never imported ({what})",
                  f"set them on the box: onemind secret set {r.app_id} <KEY> (CORE-DEPLOY-4)")

    def run(self) -> MapResult:
        for obj in self.inv.of("Deployment"):
            self.workload(obj, "Deployment")
        for obj in self.inv.of("StatefulSet"):
            self.workload(obj, "StatefulSet")
        self.pvcs()
        self.services()
        self.configmaps()
        self.ingresses()
        self.others()
        self.secrets_findings()
        if not self.r.workloads:
            self.r.add("fail", "Namespace", self.inv.namespace, "no Deployment or StatefulSet to import")
        order = {lvl: i for i, lvl in enumerate(("fail", "move", "fixed", "drop", "skip", "note", "ok"))}
        self.r.findings.sort(key=lambda f: order[f.level])
        return self.r


def map_namespace(inv: Inventory, app_id: str) -> MapResult:
    return _Mapper(inv, app_id).run()


def app_manifest(result: MapResult, *, name: str, arch: str, version: str) -> dict:
    """The onemind.app.yaml of the private app (contract §4, §12.18 `origin: private`)."""
    spec: dict = {
        "archs": [arch],
        "requires": {"gpu": result.gpu},
        "manifests": "manifests/",
    }
    if result.web:
        spec["web"] = {"port": result.web["port"]}
    if result.secrets:
        spec["secrets"] = [
            {"name": s["name"], "keys": [{"key": k, "required": not s["optional"]} for k in s["keys"]]}
            for s in result.secrets
        ]
    return {
        "apiVersion": "onemind.app/v1alpha1",
        "kind": "App",
        "metadata": {
            "id": result.app_id,
            "name": name,
            "version": version,
            "description": f"Moved from namespace {result.namespace} with onemind migrate",
            "origin": "private",
            "generatedBy": f"onemind-migrate/{version}",
        },
        "spec": spec,
    }
