# SPDX-License-Identifier: Apache-2.0
"""k3s state that survives a power cut (VM 501 test 2026-11-25, bug 1; CRITERIA-FIRSTBOOT.md F13/F14; Refs #234).

What went wrong: k3s writes its first-start files (agent keys and certificates, the node password, the
server token, the containerd config) to the ext4 /data disk without fsync (a call that forces data onto the
disk). A power cut in the first minute left them 0 bytes, k3s never started again, and on a committed slot the
health gate only alerts. Two fixes live here, both stdlib-only:

  settle   (onemind-k3s-settle.service, hub, first boot) keeps syncing /data while k3s starts, waits until
           k3s answers, syncs once more and records that the first setup is on disk (k3s-settled marker).
  recover  (ExecStartPre of k3s.service, every start) finds damaged k3s state (empty or non-PEM
           certificates and keys, empty tokens, node password or config). The generated state is moved
           aside, never deleted, and k3s makes it again. Owner data, apps' volumes (/data/k3s/storage,
           /data/k3s/agent/containerd) and the gateway's database (/data/onemind) are never touched. If the
           datastore holds the owner's own workloads, nothing is moved: it logs, alerts and waits for the
           owner to approve "Reset k3s state" in the rescue console (reset).

  onemind-k3s-state settle | recover | reset
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse

# Namespaces the OS itself owns. A workload in any other namespace belongs to the owner (apps).
SYSTEM_NAMESPACES = frozenset({"kube-system", "kube-public", "kube-node-lease", "default", "onemind-system"})
WORKLOAD_KINDS = ("deployments", "statefulsets", "daemonsets", "cronjobs", "jobs", "persistentvolumeclaims")
SETTLE_TIMEOUT_S = 900
SETTLE_POLL_S = 2
SETTLE_GRACE_S = 5          # k3s keeps writing for a moment after its first setup looks done
REPEAT_LIMIT = 3            # automatic repairs inside REPEAT_WINDOW_S before the owner must decide
REPEAT_WINDOW_S = 3600


class Paths:
    """Every path touched, under one root (tests point it at a temp dir)."""

    def __init__(self, root: str = "/"):
        j = lambda *p: os.path.join(root, *p)
        self.root = root
        self.k3s = j("data", "k3s")
        self.server = j("data", "k3s", "server")
        self.agent = j("data", "k3s", "agent")
        self.db = j("data", "k3s", "server", "db", "state.db")
        self.node_dir = j("data", "state", "etc-rancher-node")      # bind-mounted at /etc/rancher/node
        self.node_password = j("data", "state", "etc-rancher-node", "password")
        self.recovery = j("data", "onemind", "k3s-recovery")
        self.last = j("data", "onemind", "k3s-recovery", "last.json")
        self.settled = j("data", "onemind", "firstboot", "k3s-settled")
        self.role = j("data", "onemind", "etc", "role")
        self.kubeconfig = j("run", "k3s", "k3s.yaml")
        self.gw_kubeconfig = j("data", "onemind", "gateway", "kubeconfig")   # the gateway's ServiceAccount token for THIS cluster
        self.console = j("dev", "console")
        self.data = j("data")


# ------------------------------------------------------------------ durable writes
def fsync_dir(path: str) -> None:
    """fsync a directory: a rename or a new file is in the directory, which the file's own fsync does not cover."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: str, data: str | bytes, mode: int = 0o600, owner: tuple[int, int] | None = None) -> None:
    """Temp file in the same directory, fsync, rename over the target, fsync the directory. A power cut leaves
    the old file or the whole new one, and once this returns the new one is on the disk."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        if owner:
            os.chown(tmp, *owner)
        os.replace(tmp, path)
        fsync_dir(d)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sync_fs(path: str) -> bool:
    """syncfs(2) on the filesystem holding path: every dirty page of it, whoever wrote it (k3s included).
    Falls back to sync(2) (all filesystems) when syncfs is not available. Returns False if neither worked."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        fd = -1
    try:
        if fd >= 0:
            libc = ctypes.CDLL(None, use_errno=True)
            if hasattr(libc, "syncfs") and libc.syncfs(fd) == 0:
                return True
    except (OSError, AttributeError):
        pass
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        os.sync()
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ what is k3s state
def _walk(top: str):
    for root, _dirs, files in os.walk(top):
        for f in files:
            yield os.path.join(root, f)


def k3s_files(p: Paths) -> list[str]:
    """The files k3s makes on its first start and needs to start again (the F13 definition, plus the rest of
    its credentials): tokens, certificates and keys, the credentials folder, the agent's kubeconfigs and
    config, and the node password."""
    out = [os.path.join(p.server, "token"), os.path.join(p.server, "agent-token")]
    for top in (os.path.join(p.server, "tls"), os.path.join(p.server, "cred"), os.path.join(p.agent, "etc")):
        out += sorted(_walk(top))
    try:
        for f in sorted(os.listdir(p.agent)):
            if f.endswith((".crt", ".key", ".kubeconfig")):
                out.append(os.path.join(p.agent, f))
    except OSError:
        pass
    out.append(p.node_password)
    return [f for f in out if os.path.isfile(f)]


def damaged(path: str) -> str | None:
    """Why this file is damaged, or None. Empty is the power-cut signature; a certificate or key that is not
    PEM text is a torn write."""
    try:
        size = os.path.getsize(path)
        if size == 0:
            return "empty"
        if path.endswith((".crt", ".key")):
            with open(path, "rb") as f:
                if f.read(11) != b"-----BEGIN ":
                    return "not PEM"
    except OSError as exc:
        return f"unreadable ({exc.strerror or exc})"
    return None


def find_damaged(p: Paths) -> list[tuple[str, str]]:
    return [(f, why) for f in k3s_files(p) if (why := damaged(f))]


def owner_workloads(p: Paths) -> tuple[str, list[str]]:
    """Does the datastore hold workloads the owner made (apps)? Returns ("none"|"found"|"unreadable", names).
    A missing, empty or unreadable datastore counts as no owner workloads: k3s cannot use it either, and it is
    only moved aside, never deleted. Reads kine's table (k3s's sqlite store: one row per revision of each
    key; the newest row of a key decides whether it exists); read-only."""
    try:
        if not os.path.isfile(p.db) or os.path.getsize(p.db) == 0:
            return "none", []
    except OSError:
        return "none", []
    likes = " OR ".join("name LIKE ?" for _ in WORKLOAD_KINDS)
    sql = (f"SELECT k.name FROM kine k JOIN (SELECT name, max(id) AS mid FROM kine WHERE {likes} GROUP BY name) m "
           "ON k.id = m.mid WHERE k.deleted = 0")
    try:
        con = sqlite3.connect("file:" + urllib.parse.quote(p.db) + "?mode=ro", uri=True, timeout=5)
        try:
            rows = [r[0] for r in con.execute(sql, [f"/registry/{k}/%" for k in WORKLOAD_KINDS])]
        finally:
            con.close()
    except sqlite3.Error:
        return "unreadable", []
    found = []
    for name in rows:
        parts = name.split("/")                        # "", "registry", kind, namespace, object
        if len(parts) >= 5 and parts[3] not in SYSTEM_NAMESPACES:
            found.append(name)
    return ("found" if found else "none"), sorted(found)


def _rel(p: Paths, path: str) -> str:
    return os.path.relpath(path, p.data)


def move_set(p: Paths, bad: list[tuple[str, str]], force: bool) -> list[str]:
    """What to move aside. Only the agent's own config when that is all that is damaged (k3s writes it again
    at every start). Anything else damaged (certificates, tokens, the node password, credentials) means the
    whole generated state: they belong together (the certificates are signed by one CA, the node password is
    remembered by the datastore), so the PKI, credentials, tokens, node password and datastore all go. Never
    /data/k3s/storage (apps' volumes), /data/k3s/agent/containerd (image store), /data/k3s/data (k3s's own
    binaries), manifests (the unit copies them in at every start) or the gateway's database and the rest of
    /data/onemind. The one file taken from the gateway's folder is its kubeconfig: it holds a token and CA of the
    cluster that is being replaced, and onemind-gateway-kube.service writes a new one once k3s is back."""
    etc = os.path.join(p.agent, "etc")
    agent_etc_only = not force and bad and all(f.startswith(etc + os.sep) for f, _ in bad)
    paths = [etc]
    if not agent_etc_only:
        paths += [os.path.join(p.server, d) for d in ("tls", "cred", "db")]
        paths += [os.path.join(p.server, f) for f in ("token", "agent-token")]
        try:
            paths += [os.path.join(p.agent, f) for f in sorted(os.listdir(p.agent))
                      if f.endswith((".crt", ".key", ".kubeconfig"))]
        except OSError:
            pass
        paths.append(p.node_password)
        paths.append(p.gw_kubeconfig)     # a credential of the old cluster, not the gateway's database: made again below
    return [x for x in paths if os.path.lexists(x)]


# ------------------------------------------------------------------ messages
def log(msg: str) -> None:
    print(f"onemind-k3s-state: {msg}", flush=True)


def console(p: Paths, msg: str) -> None:
    try:
        with open(p.console, "a") as c:
            c.write(msg + "\n")
    except OSError:
        pass


def say(p: Paths, msg: str) -> None:
    """Journal and console: this is the alert (the rescue console shows last.json as well)."""
    log(msg)
    console(p, msg)


def _record(p: Paths, rec: dict) -> None:
    os.makedirs(p.recovery, mode=0o700, exist_ok=True)
    atomic_write(p.last, json.dumps(rec, indent=2) + "\n", 0o600)


def _already_waiting(p: Paths, reason: str) -> bool:
    """k3s restarts every 5 s while it cannot start (Restart=always): say it once, not every time."""
    try:
        with open(p.last, encoding="utf-8") as f:
            last = json.load(f)
    except (OSError, ValueError):
        return False
    return isinstance(last, dict) and last.get("action") == "needs-approval" and last.get("reason") == reason


def _recent_repairs(p: Paths, now: float) -> int:
    n = 0
    try:
        for d in os.listdir(p.recovery):
            full = os.path.join(p.recovery, d)
            if os.path.isdir(full) and now - os.path.getmtime(full) < REPEAT_WINDOW_S:
                n += 1
    except OSError:
        pass
    return n


# ------------------------------------------------------------------ recover / reset
def start_followups(p: Paths) -> None:
    """After a repair k3s makes its state again: have settle sync it (its marker was removed) and have the
    gateway's kubeconfig made again if it was moved. Real box only."""
    if p.root == "/":
        for unit in ("onemind-k3s-settle.service", "onemind-gateway-kube.service"):
            subprocess.run(["systemctl", "start", "--no-block", unit], check=False)


def recover(p: Paths, force: bool = False, now: float | None = None) -> dict | None:
    """Repair damaged k3s state (see the module doc). Returns the record written, or None when nothing is
    damaged. force (the owner approved "Reset k3s state") moves the whole generated state even if nothing is
    detectably damaged or the owner has workloads in the datastore."""
    now = time.time() if now is None else now
    bad = find_damaged(p)
    if not bad and not force:
        return None
    wl_state, wl = owner_workloads(p)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
           "damaged": [{"file": _rel(p, f), "why": why} for f, why in bad],
           "datastore": wl_state, "owner_workloads": wl[:20]}
    moves = move_set(p, bad, force)
    only_etc = all(os.path.join(p.agent, "etc") == m for m in moves)
    needs_datastore = not only_etc and not force
    if needs_datastore and wl_state == "found":
        rec.update(action="needs-approval", reason="the datastore holds the owner's apps, so the cluster state is "
                   "not rebuilt automatically")
        if _already_waiting(p, rec["reason"]):
            return rec
        _record(p, rec)
        say(p, f"ONEMIND-K3S-RECOVERY: NOT repaired: {len(bad)} damaged k3s file(s) and the owner's apps are in "
               "the cluster; open the rescue console (port 7443) and approve \"Reset k3s state\"")
        return rec
    if not force and _recent_repairs(p, now) >= REPEAT_LIMIT:
        rec.update(action="needs-approval", reason=f"repaired {REPEAT_LIMIT} times in the last hour; something keeps "
                   "damaging the disk, so it waits for the owner")
        if _already_waiting(p, rec["reason"]):
            return rec
        _record(p, rec)
        say(p, "ONEMIND-K3S-RECOVERY: NOT repaired: it was repaired several times in the last hour; check the disk, "
               "then approve \"Reset k3s state\" in the rescue console (port 7443)")
        return rec
    qdir = os.path.join(p.recovery, stamp)
    os.makedirs(qdir, mode=0o700, exist_ok=True)
    moved = []
    for src in moves:
        dst = os.path.join(qdir, _rel(p, src))
        os.makedirs(os.path.dirname(dst), mode=0o700, exist_ok=True)
        os.rename(src, dst)                           # same filesystem (/data): atomic, nothing is copied or lost
        moved.append(_rel(p, src))
    try:
        os.unlink(p.settled)                           # settle must run again and sync what k3s writes next
    except OSError:
        pass
    for d in {os.path.dirname(x) for x in moves} | {qdir, p.recovery}:
        try:
            fsync_dir(d)
        except OSError:
            pass
    rec.update(action="reset" if force else "repaired", quarantine=_rel(p, qdir), moved=moved)
    _record(p, rec)
    sync_fs(p.data)
    start_followups(p)
    verb = "reset (owner approved)" if force else "repaired"
    say(p, f"ONEMIND-K3S-RECOVERY: {verb} k3s state: {len(moved)} item(s) moved to /data/{_rel(p, qdir)}; k3s makes them "
           "again. The owner's data, the apps' volumes and the gateway database were not touched.")
    return rec


# ------------------------------------------------------------------ settle
def system_pods_ready(pods: dict) -> bool:
    """k3s's first setup is done when the OS's own pods (coredns, local-path, onemind-core, the helm jobs) have
    started: at least one of them, every one either Ready or finished (Succeeded). Owners' apps never count."""
    seen = 0
    for pod in pods.get("items", []):
        if pod.get("metadata", {}).get("namespace") not in SYSTEM_NAMESPACES:
            continue
        seen += 1
        status = pod.get("status", {})
        if status.get("phase") == "Succeeded":
            continue
        if not any(c.get("type") == "Ready" and c.get("status") == "True" for c in status.get("conditions", [])):
            return False
    return seen > 0


def k3s_ready(p: Paths) -> bool:
    """k3s answers and its first setup has finished: the API is ready and the OS's own pods are up (their images are
    unpacked and started, which is the last thing k3s writes in bulk on a new box). Read-only."""
    if not os.path.exists(p.kubeconfig):
        return False
    k = ["/usr/local/bin/k3s", "kubectl", "--kubeconfig", p.kubeconfig, "--request-timeout=5s"]
    if subprocess.run(k + ["get", "--raw=/readyz"], capture_output=True, check=False).returncode != 0:
        return False
    r = subprocess.run(k + ["get", "pods", "-A", "-o", "json"], capture_output=True, check=False)
    if r.returncode != 0:
        return False
    try:
        return system_pods_ready(json.loads(r.stdout))
    except ValueError:
        return False


def settle(p: Paths, timeout: int = SETTLE_TIMEOUT_S, sleep=time.sleep, ready=None, sync=None) -> int:
    """First boot's last step for k3s. Hub only, once: sync /data every few seconds while k3s starts (so a power
    cut loses seconds of its work, not the whole first start), wait until its first setup is done (API ready and
    the OS's own pods up), sync again, check its files, and only then write the marker that says the first setup
    is on the disk."""
    ready = ready or (lambda: k3s_ready(p))
    sync = sync or (lambda: sync_fs(p.data))
    if os.path.exists(p.settled):
        return 0
    try:
        with open(p.role, encoding="utf-8") as f:
            if f.read().strip() != "hub":
                return 0
    except OSError:
        return 0
    waited = 0
    while waited < timeout:
        sync()
        if ready():
            sleep(SETTLE_GRACE_S)
            sync()
            bad = find_damaged(p)
            if bad:
                say(p, f"ONEMIND-FIRSTBOOT: k3s is up but {len(bad)} of its files are damaged ({_rel(p, bad[0][0])}: "
                       f"{bad[0][1]}); the next start repairs them")
                return 1
            atomic_write(p.settled, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n", 0o644)
            say(p, "ONEMIND-FIRSTBOOT: k3s finished its first setup and /data is synced (a power cut is safe now)")
            return 0
        sleep(SETTLE_POLL_S)
        waited += SETTLE_POLL_S
    sync()
    say(p, f"ONEMIND-FIRSTBOOT: k3s did not finish its first setup within {timeout} s; /data is synced, first setup "
           "not marked done")
    return 1


# ------------------------------------------------------------------ reset (owner approved)
def reset(p: Paths) -> int:
    """The rescue console's approved "Reset k3s state": stop k3s, move the whole generated state aside, start it."""
    subprocess.run(["systemctl", "stop", "k3s.service"], check=False)
    try:
        rec = recover(p, force=True)
    finally:
        subprocess.run(["systemctl", "start", "--no-block", "k3s.service"], check=False)
    return 0 if rec else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="onemind-k3s-state", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("ONEMIND_FIRSTBOOT_ROOT", "/"))
    ap.add_argument("cmd", choices=("settle", "recover", "reset"))
    a = ap.parse_args(argv)
    p = Paths(a.root)
    if a.cmd == "recover":
        try:
            recover(p)
        except OSError as exc:                        # never block k3s's start on a repair that could not run
            say(p, f"ONEMIND-K3S-RECOVERY: could not repair: {exc}")
        return 0
    return {"settle": settle, "reset": reset}[a.cmd](p)


if __name__ == "__main__":
    sys.exit(main())
