# SPDX-License-Identifier: Apache-2.0
"""The two short-lived pods that move one volume, and how their results are read.

1. The **helper pod** runs in the OLD cluster, in the app's namespace, with the volume mounted
   read-only. It writes a sha256 manifest of every file, then `restic backup`s the volume and the
   manifest (one snapshot) to this box's migration repository over the restic REST protocol,
   with an append-only user that expires when the action ends. It needs no Kubernetes API
   access (no service account token) and reads files as root with only CAP_DAC_READ_SEARCH.
2. The **restore Job** runs on THIS box, in namespace app-<id>, with the new volume mounted. It
   restores the snapshot with `--delete` (the volume ends up identical to the snapshot), then
   checks every file against the manifest with `sha256sum -c`. Its read-only repository user
   and the repository password come from a Secret that is deleted with the Job.

Each pod prints one line `ONEMIND-RESULT {json}` as its last output; nothing else is parsed.
"""

from __future__ import annotations

import base64
import json
import re

from .kube import HELPER_LABEL, HELPER_PREFIX

RESULT_PREFIX = "ONEMIND-RESULT "
MIGRATE_LABEL = "onemind.io/migrate"

_CA = (
    'if [ -n "${ONEMIND_CA_PEM:-}" ]; then printf \'%s\\n\' "$ONEMIND_CA_PEM" > /work/ca.pem; '
    "export RESTIC_CACERT=/work/ca.pem; fi\n"
)

HELPER_SCRIPT = (
    "set -eu\numask 077\n" + _CA
    + "export RESTIC_CACHE_DIR=/work/cache TMPDIR=/work/tmp\n"
    "mkdir -p /work/meta /work/tmp\n"
    "cd /src\n"
    "find . -type f -exec sha256sum {} + > /work/meta/manifest.sha256\n"
    "files=$(wc -l < /work/meta/manifest.sha256 | tr -d ' ')\n"
    "msha=$(sha256sum /work/meta/manifest.sha256 | cut -d' ' -f1)\n"
    "restic cat config >/dev/null 2>&1 || restic init >/dev/null\n"
    'restic backup --json --host onemind-migrate --tag "$ONEMIND_TAGS" /src /work/meta > /work/backup.json\n'
    "summary=$(grep '\"message_type\":\"summary\"' /work/backup.json | tail -n 1)\n"
    'printf \'ONEMIND-RESULT {"files":%s,"manifest_sha256":"%s","summary":%s}\\n\' "$files" "$msha" "$summary"\n'
)

RESTORE_SCRIPT = (
    "set -eu\n" + _CA
    + "export RESTIC_CACHE_DIR=/work/cache TMPDIR=/work/tmp\n"
    "mkdir -p /work/tmp\n"
    'restic restore --no-lock "$ONEMIND_SNAPSHOT:/src" --target /data --delete > /work/restore.log 2>&1 '
    "|| { tail -n 20 /work/restore.log; exit 1; }\n"
    'restic dump --no-lock "$ONEMIND_SNAPSHOT" /work/meta/manifest.sha256 > /work/manifest.sha256\n'
    "files=$(wc -l < /work/manifest.sha256 | tr -d ' ')\n"
    "msha=$(sha256sum /work/manifest.sha256 | cut -d' ' -f1)\n"
    "cd /data\n"
    "failed=0\n"
    # every manifest line that is not reported OK (changed, missing or unreadable) counts once
    'if [ "$files" -gt 0 ]; then good=$( (sha256sum -c /work/manifest.sha256 2>/dev/null || true) '
    "| grep -c ': OK$' || true); failed=$((files - good)); fi\n"
    "present=$(find . -type f | wc -l | tr -d ' ')\n"
    'printf \'ONEMIND-RESULT {"files":%s,"failed":%s,"present":%s,"manifest_sha256":"%s"}\\n\' '
    '"$files" "$failed" "$present" "$msha"\n'
)


def pod_name(copy_id: str, kind: str) -> str:
    """onemind-migrate-<kind>-<last 12 of the copy id>, lower case (a DNS label)."""
    return f"{HELPER_PREFIX}{kind}-{copy_id[-12:].lower()}"


def _container_security(caps: list[str]) -> dict:
    return {
        "runAsUser": 0,
        "runAsGroup": 0,
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"], "add": caps},
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def helper_pod(
    *, name: str, plan_id: str, copy_id: str, pvc: str, node: str | None, image: str, repository: str,
    repo_password: str, tags: list[str], ca_pem: str | None, deadline_s: int,
) -> dict:
    """The pod created in the old cluster. repository carries the append-only user's password."""
    env = [
        {"name": "RESTIC_REPOSITORY", "value": repository},
        {"name": "RESTIC_PASSWORD", "value": repo_password},
        {"name": "ONEMIND_TAGS", "value": ",".join(tags)},
    ]
    if ca_pem:
        env.append({"name": "ONEMIND_CA_PEM", "value": ca_pem})
    spec: dict = {
        "restartPolicy": "Never",
        "activeDeadlineSeconds": deadline_s,
        "automountServiceAccountToken": False,
        "enableServiceLinks": False,
        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [{
            "name": "copy",
            "image": image,
            "command": ["/bin/sh", "-c", HELPER_SCRIPT],
            "env": env,
            "securityContext": _container_security(["DAC_READ_SEARCH"]),
            "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "1", "memory": "2Gi"}},
            "volumeMounts": [
                {"name": "src", "mountPath": "/src", "readOnly": True},
                {"name": "work", "mountPath": "/work"},
            ],
        }],
        "volumes": [
            {"name": "src", "persistentVolumeClaim": {"claimName": pvc, "readOnly": True}},
            {"name": "work", "emptyDir": {}},
        ],
    }
    if node:
        # A ReadWriteOnce volume in use can be mounted a second time only on the same node.
        spec["nodeName"] = node
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": name,
            "labels": {HELPER_LABEL: copy_id, MIGRATE_LABEL: plan_id},
            "annotations": {"onemind.io/purpose": "copies this volume to a OneMind box; deleted when done"},
        },
        "spec": spec,
    }


def restore_secret(*, name: str, namespace: str, app_id: str, repository: str, repo_password: str,
                   ca_pem: str | None) -> dict:
    def b64(v: str) -> str:
        return base64.b64encode(v.encode()).decode()

    data = {"RESTIC_REPOSITORY": b64(repository), "RESTIC_PASSWORD": b64(repo_password)}
    if ca_pem:
        data["ONEMIND_CA_PEM"] = b64(ca_pem)
    return {
        "apiVersion": "v1", "kind": "Secret", "type": "Opaque",
        "metadata": {"name": name, "namespace": namespace, "labels": {"onemind.io/app": app_id, MIGRATE_LABEL: "restore"}},
        "data": data,
    }


def restore_job(*, name: str, namespace: str, app_id: str, plan_id: str, pvc: str, snapshot_id: str, image: str,
                secret: str, deadline_s: int) -> dict:
    labels = {"onemind.io/app": app_id, MIGRATE_LABEL: plan_id}
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": deadline_s,
            "ttlSecondsAfterFinished": 3600,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "enableServiceLinks": False,
                    "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [{
                        "name": "restore",
                        "image": image,
                        "command": ["/bin/sh", "-c", RESTORE_SCRIPT],
                        "env": [{"name": "ONEMIND_SNAPSHOT", "value": snapshot_id}],
                        "envFrom": [{"secretRef": {"name": secret}}],
                        "securityContext": _container_security(["CHOWN", "DAC_OVERRIDE", "FOWNER", "FSETID"]),
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "128Mi"},
                            "limits": {"cpu": "1", "memory": "2Gi"},
                        },
                        "volumeMounts": [
                            {"name": "data", "mountPath": "/data"},
                            {"name": "work", "mountPath": "/work"},
                        ],
                    }],
                    "volumes": [
                        {"name": "data", "persistentVolumeClaim": {"claimName": pvc}},
                        {"name": "work", "emptyDir": {}},
                    ],
                },
            },
        },
    }


_SNAPSHOT_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_result(log: str) -> dict | None:
    """The JSON of the last `ONEMIND-RESULT` line, or None."""
    for line in reversed(log.splitlines()):
        if line.startswith(RESULT_PREFIX):
            try:
                doc = json.loads(line[len(RESULT_PREFIX):])
            except ValueError:
                return None
            return doc if isinstance(doc, dict) else None
    return None


def helper_outcome(doc: dict | None) -> dict | None:
    """{snapshot_id, files, bytes, manifest_sha256} from the helper's result, or None if malformed."""
    if not doc:
        return None
    summary = doc.get("summary") or {}
    snap = summary.get("snapshot_id") if isinstance(summary, dict) else None
    msha = doc.get("manifest_sha256")
    if not isinstance(snap, str) or not _SNAPSHOT_RE.match(snap) or not isinstance(msha, str):
        return None
    files = doc.get("files")
    return {
        "snapshot_id": snap,
        "files": files if isinstance(files, int) else None,
        "bytes": summary.get("total_bytes_processed") if isinstance(summary.get("total_bytes_processed"), int) else None,
        "manifest_sha256": "sha256:" + msha,
    }


def restore_outcome(doc: dict | None) -> dict | None:
    if not doc or not all(isinstance(doc.get(k), int) for k in ("files", "failed", "present")):
        return None
    if not isinstance(doc.get("manifest_sha256"), str):
        return None
    return {**doc, "manifest_sha256": "sha256:" + doc["manifest_sha256"]}


def scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "[redacted]")
    return text[-2000:]
