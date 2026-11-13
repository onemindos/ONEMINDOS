# SPDX-License-Identifier: Apache-2.0
"""App health from pod status (contract §12.15 `GET /v1/apps/{id}` `health` and `components`).

A component is a workload: the pod label `app.kubernetes.io/component`, else the owner
(a ReplicaSet's name without its template hash, a StatefulSet or DaemonSet name), else the pod.

health.state:
- `stopped`   the app is not installed, or has no pods
- `starting`  a pod is not ready yet but has been not-ready for less than `unhealthy_after_s`
- `unhealthy` a pod has been not ready for `unhealthy_after_s` or more (3 min by default), or a
              container waits in CrashLoopBackOff / ImagePullBackOff
- `healthy`   every pod is ready
- `unknown`   the Kubernetes API could not be read
"""

from __future__ import annotations

import re
from datetime import datetime

from ..ledger import iso

_RS_HASH = re.compile(r"-[a-z0-9]{6,10}$")
BAD_WAITING = {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError",
               "CreateContainerError", "InvalidImageName"}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def component_of(pod: dict) -> str:
    meta = pod.get("metadata") or {}
    label = (meta.get("labels") or {}).get("app.kubernetes.io/component")
    if label:
        return label
    for ref in meta.get("ownerReferences") or []:
        if ref.get("kind") == "ReplicaSet":
            return _RS_HASH.sub("", ref.get("name", ""))
        if ref.get("name"):
            return ref["name"]
    return meta.get("name", "pod")


def pod_ready(pod: dict) -> bool:
    for c in (pod.get("status") or {}).get("conditions") or []:
        if c.get("type") == "Ready":
            return c.get("status") == "True"
    return False


def containers(pod: dict) -> list[dict]:
    """[{pod, container, restarts, last_exit_reason, last_restart_at, waiting}] for one pod."""
    out = []
    name = (pod.get("metadata") or {}).get("name", "")
    for cs in (pod.get("status") or {}).get("containerStatuses") or []:
        term = ((cs.get("lastState") or {}).get("terminated")) or {}
        waiting = ((cs.get("state") or {}).get("waiting") or {}).get("reason")
        out.append({
            "pod": name, "container": cs.get("name", ""), "restarts": int(cs.get("restartCount") or 0),
            "last_exit_reason": term.get("reason"), "last_restart_at": term.get("finishedAt"), "waiting": waiting,
        })
    return out


def summarise(pods: list[dict]) -> list[dict]:
    """Components: [{name, ready, restarts, last_restart_at?, last_exit_reason?}] (contract §12.15)."""
    comps: dict[str, dict] = {}
    for pod in pods:
        name = component_of(pod)
        c = comps.setdefault(name, {"name": name, "ready": True, "restarts": 0,
                                    "last_restart_at": None, "last_exit_reason": None, "pods": 0})
        c["pods"] += 1
        c["ready"] = c["ready"] and pod_ready(pod)
        for cs in containers(pod):
            c["restarts"] += cs["restarts"]
            if cs["last_restart_at"] and (c["last_restart_at"] is None or cs["last_restart_at"] > c["last_restart_at"]):
                c["last_restart_at"], c["last_exit_reason"] = cs["last_restart_at"], cs["last_exit_reason"]
    return sorted(comps.values(), key=lambda c: c["name"])


def assess(pods: list[dict] | None, installed: bool, not_ready_since: datetime | None, now: datetime,
           unhealthy_after_s: int) -> dict:
    """{state, checked_at, reason?}."""
    out: dict = {"checked_at": iso(now)}
    if not installed:
        return {**out, "state": "stopped", "reason": "not installed"}
    if pods is None:
        return {**out, "state": "unknown", "reason": "the Kubernetes API is not reachable"}
    if not pods:
        return {**out, "state": "stopped", "reason": "no pods are running"}
    for pod in pods:
        for cs in containers(pod):
            if cs["waiting"] in BAD_WAITING:
                return {**out, "state": "unhealthy",
                        "reason": f"{component_of(pod)}: {cs['waiting']} (last exit: {cs['last_exit_reason'] or 'unknown'})"}
    not_ready = [component_of(p) for p in pods if not pod_ready(p)]
    if not not_ready:
        return {**out, "state": "healthy"}
    since = not_ready_since or now
    age = int((now - since).total_seconds())
    names = ", ".join(sorted(set(not_ready)))
    if age >= unhealthy_after_s:
        return {**out, "state": "unhealthy", "reason": f"{names} not ready for {age} s"}
    return {**out, "state": "starting", "reason": f"{names} not ready yet"}


def earliest_start(pods: list[dict]) -> datetime | None:
    starts = [parse_time((p.get("status") or {}).get("startTime")) for p in pods if not pod_ready(p)]
    starts = [s for s in starts if s is not None]
    return min(starts) if starts else None
