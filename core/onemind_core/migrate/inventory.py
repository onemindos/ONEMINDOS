# SPDX-License-Identifier: Apache-2.0
"""Read one namespace of the old cluster (GET only) into a plain inventory."""

from __future__ import annotations

from dataclasses import dataclass, field

from .kube import KubeApiError, KubeClient

# (api, resource, kind, required). A required kind that cannot be listed stops the plan; an
# optional one is reported as "not read", so the owner knows the report may be incomplete.
KINDS = (
    ("apps/v1", "deployments", "Deployment", True),
    ("apps/v1", "statefulsets", "StatefulSet", True),
    ("", "services", "Service", True),
    ("", "persistentvolumeclaims", "PersistentVolumeClaim", True),
    ("", "pods", "Pod", True),
    ("", "configmaps", "ConfigMap", True),
    ("apps/v1", "daemonsets", "DaemonSet", False),
    ("networking.k8s.io/v1", "ingresses", "Ingress", False),
    ("batch/v1", "jobs", "Job", False),
    ("batch/v1", "cronjobs", "CronJob", False),
)


@dataclass
class Inventory:
    namespace: str
    server_version: str = ""
    objects: dict[str, list[dict]] = field(default_factory=dict)
    not_read: dict[str, str] = field(default_factory=dict)  # kind -> reason

    def of(self, kind: str) -> list[dict]:
        return self.objects.get(kind, [])


class Forbidden(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def read_namespace(client: KubeClient) -> Inventory:
    inv = Inventory(namespace=client.namespace)
    try:
        v = client.version()
        inv.server_version = str(v.get("gitVersion") or "")
    except KubeApiError:
        inv.server_version = ""  # /version may be closed to this identity; not needed
    for api, resource, kind, required in KINDS:
        try:
            inv.objects[kind] = client.list(api, resource)
        except KubeApiError as exc:
            if exc.status in (401, 403) and required:
                raise Forbidden(kind, f"cannot list {resource} in {client.namespace} (HTTP {exc.status})") from None
            if exc.status in (401, 403, 404):
                inv.not_read[kind] = f"HTTP {exc.status}"
                inv.objects[kind] = []
                continue
            raise
    return inv
