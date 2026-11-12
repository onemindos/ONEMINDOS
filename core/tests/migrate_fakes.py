# SPDX-License-Identifier: Apache-2.0
"""Fakes for the migration kit tests: an in-memory old cluster API and this box's kubectl.

No test ever connects to a real cluster. The fixture namespace is generic (a notes app with a
volume, a database StatefulSet, a DaemonSet and a CronJob) and uses example.test names only.
"""

from __future__ import annotations

import base64
import copy
import json
import re
from urllib.parse import parse_qs, urlsplit

import yaml

from onemind_core.migrate.boxkube import BoxKube

NS = "legacy"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
SNAPSHOT = "c" * 64
MANIFEST_SHA = "d" * 64
TOKEN = "test-sa-token-" + "x" * 20  # generated fixture value, not a credential


def kubeconfig(server: str = "https://old.example.test:6443", user: dict | None = None, **cluster_extra) -> str:
    ca = base64.b64encode(b"-----BEGIN CERTIFICATE-----\nZmFrZQ==\n-----END CERTIFICATE-----\n").decode()
    doc = {
        "apiVersion": "v1", "kind": "Config", "current-context": "old",
        "clusters": [{"name": "old", "cluster": {"server": server, "certificate-authority-data": ca, **cluster_extra}}],
        "users": [{"name": "migrate", "user": user if user is not None else {"token": TOKEN}}],
        "contexts": [{"name": "old", "context": {"cluster": "old", "user": "migrate", "namespace": NS}}],
    }
    return yaml.safe_dump(doc)


def _pod(name, labels, image_ids: dict, node="node-a", claim=None, owner="ReplicaSet"):
    return {
        "metadata": {"name": name, "labels": labels, "ownerReferences": [{"kind": owner, "name": "x"}]},
        "spec": {"nodeName": node, "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": claim}}] if claim else []},
        "status": {"phase": "Running", "containerStatuses": [
            {"name": c, "imageID": iid} for c, iid in image_ids.items()
        ]},
    }


def namespace_objects() -> dict[str, list[dict]]:
    notes = {
        "metadata": {"name": "notes", "labels": {"app": "notes"}, "annotations": {"deployment.kubernetes.io/revision": "3"},
                     "uid": "u1", "resourceVersion": "9"},
        "spec": {
            "replicas": 1, "selector": {"matchLabels": {"app": "notes"}},
            "template": {
                "metadata": {"labels": {"app": "notes"}},
                "spec": {
                    "serviceAccountName": "notes-sa", "nodeSelector": {"disk": "ssd"},
                    "schedulerName": "default-scheduler",
                    "imagePullSecrets": [{"name": "regcred"}],
                    "containers": [{
                        "name": "notes", "image": "registry.example.test/notes:1.4",
                        "ports": [{"containerPort": 8080, "hostPort": 8080}],
                        "env": [{"name": "API_KEY", "valueFrom": {"secretKeyRef": {"name": "notes-env", "key": "API_KEY", "optional": True}}}],
                        "envFrom": [{"configMapRef": {"name": "notes-config"}}, {"secretRef": {"name": "notes-extra", "optional": True}}],
                        "resources": {"requests": {"memory": "64Mi"}},
                        "volumeMounts": [{"name": "data", "mountPath": "/data"}],
                    }],
                    "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "notes-data"}},
                                {"name": "cfg", "configMap": {"name": "notes-config"}}],
                },
            },
        },
        "status": {"readyReplicas": 1},
    }
    db = {
        "metadata": {"name": "db", "labels": {"app": "db"}},
        "spec": {
            "replicas": 1, "serviceName": "db", "selector": {"matchLabels": {"app": "db"}},
            "persistentVolumeClaimRetentionPolicy": {"whenDeleted": "Delete", "whenScaled": "Retain"},
            "template": {"metadata": {"labels": {"app": "db"}}, "spec": {"containers": [{
                "name": "db", "image": f"registry.example.test/db:2@{DIGEST_B}",
                "resources": {"limits": {"memory": "256Mi", "cpu": "500m"}},
                "volumeMounts": [{"name": "data", "mountPath": "/var/lib/db"}],
            }]}},
            "volumeClaimTemplates": [{"metadata": {"name": "data"}, "spec": {
                "accessModes": ["ReadWriteOnce"], "storageClassName": "fast-ssd",
                "resources": {"requests": {"storage": "5Gi"}}}}],
        },
    }
    return {
        "deployments": [notes],
        "statefulsets": [db],
        "daemonsets": [{"metadata": {"name": "log-agent"}, "spec": {}}],
        "services": [
            {"metadata": {"name": "notes"}, "spec": {"type": "NodePort", "clusterIP": "198.51.100.9", "selector": {"app": "notes"},
                                                     "ports": [{"name": "http", "port": 80, "targetPort": 8080, "nodePort": 30080}]}},
            {"metadata": {"name": "db"}, "spec": {"clusterIP": "None", "selector": {"app": "db"}, "ports": [{"port": 5432}]}},
            {"metadata": {"name": "external"}, "spec": {"type": "ExternalName", "externalName": "db.example.test"}},
        ],
        "persistentvolumeclaims": [
            {"metadata": {"name": "notes-data"}, "spec": {"accessModes": ["ReadWriteOnce"], "storageClassName": "fast-ssd",
                                                          "resources": {"requests": {"storage": "2Gi"}}},
             "status": {"phase": "Bound", "capacity": {"storage": "2Gi"}}},
            {"metadata": {"name": "data-db-0"}, "spec": {"accessModes": ["ReadWriteOnce"], "storageClassName": "fast-ssd",
                                                         "resources": {"requests": {"storage": "5Gi"}}},
             "status": {"phase": "Bound", "capacity": {"storage": "5Gi"}}},
            {"metadata": {"name": "orphan"}, "spec": {}, "status": {"phase": "Bound"}},
        ],
        "configmaps": [
            {"metadata": {"name": "notes-config"}, "data": {"MODE": "prod"}},
            {"metadata": {"name": "kube-root-ca.crt"}, "data": {"ca.crt": "x"}},
        ],
        "pods": [
            _pod("notes-7d9-abc", {"app": "notes", "pod-template-hash": "7d9"},
                 {"notes": f"registry.example.test/notes@{DIGEST_A}"}, claim="notes-data"),
            _pod("db-0", {"app": "db"}, {"db": f"registry.example.test/db@{DIGEST_B}"}, claim="data-db-0", owner="StatefulSet"),
        ],
        "ingresses": [{"metadata": {"name": "notes"}, "spec": {"rules": [{"host": "notes.example.test", "http": {"paths": [
            {"path": "/", "backend": {"service": {"name": "notes", "port": {"name": "http"}}}}]}}]}}],
        "jobs": [],
        "cronjobs": [{"metadata": {"name": "nightly"}, "spec": {}}],
    }


class FakeCluster:
    """Answers the paths the kit uses; records every request; forbids what a Role would."""

    def __init__(self, objects: dict[str, list[dict]] | None = None, forbidden: set[str] | None = None):
        self.objects = objects if objects is not None else namespace_objects()
        self.forbidden = forbidden or set()
        self.requests: list[tuple[str, str]] = []
        self.created: list[dict] = []
        self.helper_phase = "Succeeded"
        self.helper_log = (
            'restic noise\nONEMIND-RESULT {"files":2,"manifest_sha256":"' + MANIFEST_SHA + '","summary":'
            '{"message_type":"summary","snapshot_id":"' + SNAPSHOT + '","total_bytes_processed":4096}}\n'
        )
        self.helpers: dict[str, dict] = {}

    def send(self, method: str, url: str, headers: dict, body: bytes | None):
        parts = urlsplit(url)
        path, query = parts.path, parse_qs(parts.query)
        self.requests.append((method, path))
        assert headers.get("Authorization") == f"Bearer {TOKEN}"
        if path == "/version":
            return 200, json.dumps({"gitVersion": "v1.30.0"}).encode()
        m = re.match(rf"^/api(?:s/[^/]+)?/v1/namespaces/{NS}/([a-z]+)(?:/([^/]+))?(?:/(log|scale))?$", path)
        if not m:
            return 404, b'{"message":"not found"}'
        resource, name, sub = m.groups()
        if resource in self.forbidden:
            return 403, json.dumps({"message": f"{resource} is forbidden"}).encode()
        if method == "GET" and name is None:
            items = self.objects.get(resource, []) + (list(self.helpers.values()) if resource == "pods" else [])
            return 200, json.dumps({"items": items}).encode()
        if resource == "pods" and method == "POST":
            pod = json.loads(body)
            self.created.append(pod)
            self.helpers[pod["metadata"]["name"]] = {**pod, "status": {"phase": self.helper_phase}}
            return 201, json.dumps(pod).encode()
        if resource == "pods" and method == "DELETE":
            self.helpers.pop(name, None)
            return 200, b"{}"
        if resource == "pods" and sub == "log":
            return 200, self.helper_log.encode()
        if resource == "pods" and method == "GET":
            pod = self.helpers.get(name) or next((p for p in self.objects["pods"] if p["metadata"]["name"] == name), None)
            return (200, json.dumps(pod).encode()) if pod else (404, b'{"message":"not found"}')
        if resource in ("deployments", "statefulsets") and sub == "scale" and method == "PATCH":
            replicas = json.loads(body)["spec"]["replicas"]
            obj = next(o for o in self.objects[resource] if o["metadata"]["name"] == name)
            obj["spec"]["replicas"] = replicas
            sel = obj["spec"]["selector"]["matchLabels"]
            if replicas == 0:
                self.objects["pods"] = [p for p in self.objects["pods"]
                                        if not all(p["metadata"]["labels"].get(k) == v for k, v in sel.items())]
            return 200, b"{}"
        if resource in ("deployments", "statefulsets") and method == "GET":
            obj = next((o for o in self.objects[resource] if o["metadata"]["name"] == name), None)
            return (200, json.dumps(obj).encode()) if obj else (404, b'{"message":"nf"}')
        return 405, b'{"message":"unexpected"}'


class FakeBox(BoxKube):
    """This box's kubectl, recorded. Restore Jobs succeed with the manifest the helper reported."""

    def __init__(self):
        super().__init__(runner=None)
        self.calls: list[tuple] = []
        self.applied: list[dict] = []
        self.restore_failed = 0
        self.job_ok = True
        self.pods_left: list[dict] = []
        self.storage_class = True

    def apply(self, namespace, doc):
        self.calls.append(("apply", namespace, doc["kind"], doc["metadata"]["name"]))
        self.applied.append(copy.deepcopy(doc))

    def delete(self, namespace, kind, name):
        self.calls.append(("delete", namespace, kind, name))

    def get(self, namespace, kind, name):
        self.calls.append(("get", namespace, kind, name))
        if kind == "storageclass":
            return {"metadata": {"name": name}} if self.storage_class else None
        return {"status": {"succeeded": 1} if self.job_ok else {"failed": 1}}

    def pods(self, namespace, selector):
        return self.pods_left

    def logs(self, namespace, job, tail=200):
        return ('ONEMIND-RESULT {"files":2,"failed":%d,"present":2,"manifest_sha256":"%s"}\n'
                % (self.restore_failed, MANIFEST_SHA))

    def scale(self, namespace, kind, name, replicas):
        self.calls.append(("scale", namespace, kind, name, replicas))

    def rollout(self, namespace, kind, name, timeout_s):
        self.calls.append(("rollout", namespace, kind, name))
