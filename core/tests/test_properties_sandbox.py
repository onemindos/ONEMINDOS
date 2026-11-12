# SPDX-License-Identifier: Apache-2.0
"""Property tests: the install sandbox's object checker (hardening H-01..H-04, docs/leap/core/SANDBOX.md).

Hypothesis builds sets of objects the rule file allows (sdk/policy/app-objects.yaml): every allowed
kind, restricted pod specs with digest-pinned images, init containers, allowed volume types and
storage classes, Roles and RoleBindings that stay in the app's namespace. Then:

- every such set passes check_objects() with no violation (so the generator really is "allowed");
- adding any one forbidden field to any one object of the set (host namespaces, hostPath,
  hostPort, privileged, a capability not on the list, Windows hostProcess, root, privilege
  escalation, keeping capabilities, an unconfined seccomp profile, a volume type restricted forbids,
  an image without a digest, a foreign namespace, a NodePort or LoadBalancer, externalIPs, a storage
  class not on the list, wildcard or escalating RBAC, a ClusterRole binding, a foreign subject, a
  kind that is not on the list, a List wrapper) is always refused, with that rule's id and that
  object's kind and name;
- the host-level rules (F-, I-, K-, N-, V-, P-, R-) are refused at PSA baseline too: the reviewed
  baseline exemption (home-assistant) relaxes only the restricted-profile rules (S-).

The checker and its rule file shipped in PR #40. Missing either must now fail collection,
not silently skip the sandbox properties.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from onemind_core import policy
from props import budget

RULES_FILE = Path(__file__).resolve().parents[2] / "sdk" / "policy" / "app-objects.yaml"
RULES = policy.load_rules(RULES_FILE)

# ---- allowed objects ---------------------------------------------------------------------------

names = st.from_regex(r"[a-z][a-z0-9-]{0,14}[a-z0-9]", fullmatch=True)
app_ids = st.from_regex(r"[a-z0-9][a-z0-9-]{0,20}[a-z0-9]", fullmatch=True).filter(lambda a: a not in RULES.reviewed)
digests = st.binary(min_size=32, max_size=32).map(lambda b: b.hex())
images = st.builds(lambda repo, tag, d: f"ghcr.io/example/{repo}{tag}@sha256:{d}",
                   names, st.sampled_from(["", ":1.2.3", ":latest"]), digests)
safe_caps = st.lists(st.sampled_from(sorted(RULES.caps_allowed)) | st.sampled_from(["net_bind_service", "CAP_NET_BIND_SERVICE"]),
                     max_size=1)
WORKLOADS = {"Deployment": "apps/v1", "StatefulSet": "apps/v1", "Job": "batch/v1", "CronJob": "batch/v1"}
ROLE_GROUPS = sorted(api.rpartition("/")[0] for api, _ in RULES.allow if not api.startswith("rbac."))


@st.composite
def containers(draw, pod_level_ok: bool):
    sc = {"allowPrivilegeEscalation": False,
          "capabilities": {"drop": [draw(st.sampled_from(["ALL", "all"]))], "add": draw(safe_caps)}}
    if not pod_level_ok or draw(st.booleans()):  # set here, or inherited from the pod
        sc["runAsNonRoot"] = True
        sc["seccompProfile"] = {"type": draw(st.sampled_from(["RuntimeDefault", "Localhost"]))}
    c = {"name": draw(names), "image": draw(images), "securityContext": sc}
    if draw(st.booleans()):
        c["ports"] = [{"containerPort": draw(st.integers(1, 65535))}]
    return c


@st.composite
def pod_specs(draw):
    pod_level = draw(st.booleans())
    pod: dict = {"containers": draw(st.lists(containers(pod_level), min_size=1, max_size=2))}
    if pod_level:
        pod["securityContext"] = {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}}
    if draw(st.booleans()):
        pod["initContainers"] = draw(st.lists(containers(pod_level), min_size=1, max_size=1))
    vols = draw(st.lists(st.sampled_from(["emptyDir", "configMap", "secret", "persistentVolumeClaim",
                                          "projected", "downwardAPI"]), max_size=2, unique=True))
    if vols:
        pod["volumes"] = [{"name": f"v{i}", t: {}} for i, t in enumerate(vols)]
    return pod


@st.composite
def allowed_object(draw, app_id: str):
    kind = draw(st.sampled_from(sorted({k for _, k in RULES.allow})))
    api = next(a for a, k in sorted(RULES.allow) if k == kind)
    md: dict = {"name": draw(names)}
    if draw(st.booleans()):
        md["namespace"] = f"app-{app_id}"
    obj: dict = {"apiVersion": api, "kind": kind, "metadata": md}
    sc = st.sampled_from(sorted(RULES.storage_classes, key=str))
    if kind in WORKLOADS:
        pod = draw(pod_specs())
        tpl = {"metadata": {"labels": {"app": md["name"]}}, "spec": pod}
        if kind == "CronJob":
            obj["spec"] = {"schedule": "0 3 * * *", "jobTemplate": {"spec": {"template": tpl}}}
        else:
            obj["spec"] = {"template": tpl}
        if kind == "StatefulSet" and draw(st.booleans()):
            claim_spec = {"accessModes": ["ReadWriteOnce"]}
            if (cls := draw(sc)) is not None:
                claim_spec["storageClassName"] = cls
            obj["spec"]["volumeClaimTemplates"] = [{"metadata": {"name": "data"}, "spec": claim_spec}]
    elif kind == "Service":
        obj["spec"] = {"ports": [{"port": 80}]}
        if draw(st.booleans()):
            obj["spec"]["type"] = "ClusterIP"
    elif kind == "PersistentVolumeClaim":
        obj["spec"] = {"accessModes": ["ReadWriteOnce"]}
        if (cls := draw(sc)) is not None:
            obj["spec"]["storageClassName"] = cls
    elif kind == "Role":
        obj["rules"] = [{"apiGroups": draw(st.lists(st.sampled_from(ROLE_GROUPS), min_size=1, max_size=2, unique=True)),
                         "resources": draw(st.lists(st.sampled_from(["pods", "configmaps", "services", "pods/log"]),
                                                    min_size=1, max_size=2, unique=True)),
                         "verbs": draw(st.lists(st.sampled_from(["get", "list", "watch"]), min_size=1, unique=True))}]
    elif kind == "RoleBinding":
        subject = {"kind": "ServiceAccount", "name": draw(names)}
        if draw(st.booleans()):
            subject["namespace"] = f"app-{app_id}"
        obj["roleRef"] = {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": draw(names)}
        obj["subjects"] = [subject]
    return obj


@st.composite
def allowed_sets(draw, app_id=None):
    app_id = app_id or draw(app_ids)
    return app_id, draw(st.lists(allowed_object(app_id), min_size=1, max_size=4))


def pod_of(obj: dict) -> dict | None:
    spec = obj.get("spec") or {}
    if obj["kind"] == "CronJob":
        return spec["jobTemplate"]["spec"]["template"]["spec"]
    return spec["template"]["spec"] if obj["kind"] in WORKLOADS else None


@budget(150)
@given(allowed=allowed_sets())
def test_generated_objects_are_allowed(allowed):
    app_id, objs = allowed
    assert policy.check_objects(objs, app_id, {}, RULES) == []


# ---- forbidden fields --------------------------------------------------------------------------
# Each injection: (applies to obj?, mutate(draw, obj) -> rule id). Host-level rules hold at every
# PSA level; restricted-only ones are marked so the baseline test skips them.

def any_container(draw, obj):
    pod = pod_of(obj)
    pool = pod["containers"] + pod.get("initContainers", [])
    return draw(st.sampled_from(pool))


def set_pod(field, rule):
    def mutate(draw, obj):
        pod_of(obj)[field] = True
        return rule
    return mutate


def host_path(draw, obj):
    pod_of(obj).setdefault("volumes", []).append({"name": "host", "hostPath": {"path": draw(st.sampled_from(["/", "/etc", "/var/run"]))}})
    return "F-04"


def host_port(draw, obj):
    any_container(draw, obj).setdefault("ports", []).append({"containerPort": 80, "hostPort": draw(st.integers(1, 65535))})
    return "F-05"


def privileged(draw, obj):
    any_container(draw, obj)["securityContext"]["privileged"] = True
    return "F-06"


def bad_capability(draw, obj):
    cap = draw(st.sampled_from(["SYS_ADMIN", "NET_ADMIN", "CAP_SYS_PTRACE", "sys_module", "ALL", "NET_RAW"]))
    any_container(draw, obj)["securityContext"]["capabilities"]["add"].append(cap)
    return "F-07"


def host_process(draw, obj):
    target = pod_of(obj) if draw(st.booleans()) else any_container(draw, obj)
    target.setdefault("securityContext", {})["windowsOptions"] = {"hostProcess": True}
    return "F-08"


def run_as_root(draw, obj):
    any_container(draw, obj)["securityContext"]["runAsUser"] = 0
    return "S-01"


def escalation(draw, obj):
    sc = any_container(draw, obj)["securityContext"]
    if draw(st.booleans()):
        sc["allowPrivilegeEscalation"] = True
    else:
        del sc["allowPrivilegeEscalation"]
    return "S-02"


def keeps_capabilities(draw, obj):
    any_container(draw, obj)["securityContext"]["capabilities"]["drop"] = draw(st.sampled_from([[], ["NET_RAW"]]))
    return "S-03"


def unconfined(draw, obj):
    any_container(draw, obj)["securityContext"]["seccompProfile"] = {"type": "Unconfined"}
    return "S-04"


def restricted_volume(draw, obj):
    t = draw(st.sampled_from(["nfs", "iscsi", "gitRepo", "cephfs", "rbd", "glusterfs"]))
    pod_of(obj).setdefault("volumes", []).append({"name": "x", t: {}})
    return "S-05"


def no_digest(draw, obj):
    c = any_container(draw, obj)
    c["image"] = c["image"].split("@", 1)[0] if draw(st.booleans()) else c["image"][:-1]
    return "I-01"


def foreign_namespace(draw, obj):
    obj["metadata"]["namespace"] = draw(st.sampled_from(["kube-system", "default", "app-other", "onemind"]))
    return "N-01"


def service_type(draw, obj):
    obj["spec"]["type"] = draw(st.sampled_from(["NodePort", "LoadBalancer", "ExternalName"]))
    return "V-01"


def external_ips(draw, obj):
    obj["spec"]["externalIPs"] = ["203.0.113.7"]  # TEST-NET-3 documentation address
    return "V-02"


def storage_class(draw, obj):
    cls = draw(st.sampled_from(["", "fast-ssd", "hostpath", "do-block-storage"]))
    if obj["kind"] == "StatefulSet":
        obj["spec"]["volumeClaimTemplates"] = [{"metadata": {"name": "d"}, "spec": {"storageClassName": cls}}]
    else:
        obj["spec"]["storageClassName"] = cls
    return "P-01"


def cluster_role_ref(draw, obj):
    obj["roleRef"]["kind"] = "ClusterRole"
    return "R-01"


def foreign_subject(draw, obj):
    obj["subjects"].append(draw(st.sampled_from([
        {"kind": "User", "name": "someone"},
        {"kind": "Group", "name": "system:masters"},
        {"kind": "ServiceAccount", "name": "default", "namespace": "kube-system"},
    ])))
    return "R-02"


def wide_role(draw, obj):
    rule = obj["rules"][0]
    field, value = draw(st.sampled_from([
        ("verbs", "*"), ("verbs", "escalate"), ("verbs", "bind"), ("verbs", "impersonate"),
        ("resources", "*"), ("resources", "namespaces"), ("resources", "pods/exec"), ("resources", "pods/attach"),
        ("resources", "serviceaccounts/token"), ("resources", "secrets/*"), ("resources", "nodes"),
        ("apiGroups", "*"), ("apiGroups", "networking.k8s.io"), ("apiGroups", "rbac.authorization.k8s.io"),
        ("nonResourceURLs", "/metrics"),
    ]))
    rule.setdefault(field, []).append(value)
    return "R-03"


def other_kind(draw, obj):
    obj["apiVersion"], obj["kind"] = draw(st.sampled_from([
        ("apps/v1", "DaemonSet"), ("v1", "Pod"), ("v1", "Namespace"), ("rbac.authorization.k8s.io/v1", "ClusterRole"),
        ("rbac.authorization.k8s.io/v1", "ClusterRoleBinding"), ("networking.k8s.io/v1", "NetworkPolicy"),
        ("networking.k8s.io/v1", "Ingress"), ("apiextensions.k8s.io/v1", "CustomResourceDefinition"),
        ("admissionregistration.k8s.io/v1", "MutatingWebhookConfiguration"), ("v1", "PersistentVolume"),
        ("extensions/v1beta1", "Deployment"), ("apps/v1beta2", "StatefulSet"),
    ]))
    return "K-01"


def is_workload(obj):
    return obj["kind"] in WORKLOADS


INJECTIONS = {
    "hostNetwork": (is_workload, set_pod("hostNetwork", "F-01"), False),
    "hostPID": (is_workload, set_pod("hostPID", "F-02"), False),
    "hostIPC": (is_workload, set_pod("hostIPC", "F-03"), False),
    "hostPath": (is_workload, host_path, False),
    "hostPort": (is_workload, host_port, False),
    "privileged": (is_workload, privileged, False),
    "capability": (is_workload, bad_capability, False),
    "hostProcess": (is_workload, host_process, False),
    "root": (is_workload, run_as_root, True),
    "escalation": (is_workload, escalation, True),
    "capabilities kept": (is_workload, keeps_capabilities, True),
    "seccomp": (is_workload, unconfined, True),
    "volume type": (is_workload, restricted_volume, True),
    "digest": (is_workload, no_digest, False),
    "namespace": (lambda o: True, foreign_namespace, False),
    "service type": (lambda o: o["kind"] == "Service", service_type, False),
    "externalIPs": (lambda o: o["kind"] == "Service", external_ips, False),
    "storage class": (lambda o: o["kind"] in ("PersistentVolumeClaim", "StatefulSet"), storage_class, False),
    "ClusterRole": (lambda o: o["kind"] == "RoleBinding", cluster_role_ref, False),
    "subject": (lambda o: o["kind"] == "RoleBinding", foreign_subject, False),
    "role rule": (lambda o: o["kind"] == "Role", wide_role, False),
    "kind": (lambda o: True, other_kind, False),
}


def inject(data, objs, *, restricted: bool):
    """Pick one object and one injection that applies to it; return (objs, index, rule)."""
    objs = copy.deepcopy(objs)
    i = data.draw(st.integers(0, len(objs) - 1), label="object")
    usable = sorted(n for n, (applies, _, s_rule) in INJECTIONS.items() if applies(objs[i]) and (restricted or not s_rule))
    name = data.draw(st.sampled_from(usable), label="injection")
    rule = INJECTIONS[name][1](data.draw, objs[i])
    return objs, i, rule


def assert_refused(violations, objs, i, rule):
    hits = [v for v in violations if v.rule == rule]
    assert hits, (rule, [v.to_json() for v in violations])
    assert any(v.kind == objs[i]["kind"] and v.name == objs[i]["metadata"]["name"] for v in hits), hits


@budget(300)
@given(allowed=allowed_sets(), data=st.data())
def test_any_forbidden_field_on_any_allowed_object_is_refused(allowed, data):
    app_id, objs = allowed
    objs, i, rule = inject(data, objs, restricted=True)
    assert_refused(policy.check_objects(objs, app_id, {}, RULES), objs, i, rule)


@budget(100)
@given(allowed=allowed_sets(), data=st.data())
def test_a_list_wrapper_is_refused(allowed, data):
    app_id, objs = allowed
    wrapped = [{"apiVersion": "v1", "kind": "List", "metadata": {"name": "wrapper"}, "items": objs}]
    assert {v.rule for v in policy.check_objects(wrapped, app_id, {}, RULES)} == {"K-01"}


BASELINE = [(a, e) for a, e in RULES.reviewed.items() if e.get("level") == "baseline"]


@pytest.mark.skipif(not BASELINE, reason="no app is reviewed for PSA baseline in the rule file")
@budget(200)
@given(data=st.data())
def test_baseline_relaxes_only_the_restricted_rules(data):
    app_id = data.draw(st.sampled_from([a for a, _ in BASELINE]), label="reviewed app")
    manifest = {"spec": {"security": {"podSecurity": "baseline"}}}
    _, objs = data.draw(allowed_sets(app_id), label="objects")
    assert policy.check_objects(objs, app_id, manifest, RULES) == []
    objs, i, rule = inject(data, objs, restricted=False)
    assert_refused(policy.check_objects(objs, app_id, manifest, RULES), objs, i, rule)


# ---- known gap: fields Pod Security Admission checks and the checker does not ----------------
# PSA on the app namespace still refuses these pods (deploy/k8s/psa.yaml), but only at pod
# admission: the Deployment is applied and its pods never start, instead of a refusal with a rule
# id before anything reaches the cluster. Finding F-SBX-1 in docs/testing/PROPERTY-AND-FUZZ.md;
# field list from kubernetes.io/docs/concepts/security/pod-security-standards.

def _deployment(pod_sc: dict | None = None, **container_sc) -> list[dict]:
    sc = {"runAsNonRoot": True, "allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]},
          "seccompProfile": {"type": "RuntimeDefault"}, **container_sc}
    pod = {"containers": [{"name": "c", "image": "ghcr.io/example/app@sha256:" + "a" * 64, "securityContext": sc}]}
    if pod_sc:
        pod["securityContext"] = pod_sc
    return [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "d"}, "spec": {"template": {"spec": pod}}}]


@pytest.mark.xfail(strict=True, reason="finding F-SBX-1: the checker does not mirror these PSA fields")
@pytest.mark.parametrize("objs", [
    _deployment({"runAsUser": 0}),  # restricted: runAsUser must not be 0, pod level included
    _deployment({"seccompProfile": {"type": "Unconfined"}}),  # baseline: never Unconfined
    _deployment(procMount="Unmasked"),  # baseline: /proc mount type Default only
    _deployment(appArmorProfile={"type": "Unconfined"}),  # baseline
    _deployment(seLinuxOptions={"type": "spc_t"}),  # baseline: container_t and friends only
    _deployment({"sysctls": [{"name": "kernel.msgmax", "value": "65536"}]}),  # baseline: safe set only
], ids=["pod-runAsUser-0", "pod-seccomp-unconfined", "procMount", "apparmor", "selinux", "sysctls"])
def test_psa_fields_are_refused_before_apply(objs):
    assert policy.check_objects(objs, "demo", {}, RULES) != []
