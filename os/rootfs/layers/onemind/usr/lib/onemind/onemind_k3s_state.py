# SPDX-License-Identifier: Apache-2.0
"""k3s state that survives a power cut (VM 501 test 2026-11-25, bug 1; CRITERIA-FIRSTBOOT.md F26; Refs #234).

What went wrong: k3s writes its first-start files (agent keys and certificates, the node password, the
server token, the containerd config) and containerd unpacks image layers on the ext4 /data disk without
fsync (a call that forces data onto the disk). A power cut in the first minute left them 0 bytes or torn,
k3s never started again, and on a committed slot the health gate only alerts. Stdlib only:

  atomic_write  temp file, fsync, rename, fsync of the folder (first boot's own writes use it)
  sync_fs       syncfs(2) of /data: every dirty page of the disk, whoever wrote it (k3s included)
  settle        (onemind-k3s-settle.service, hub, first boot) keeps syncing /data while k3s starts, waits
                until its first setup is done (API ready, the OS's own pods up), syncs once more and records
                that the first setup is on disk (k3s-settled marker).

On the ext4 boards (rpi5, Jetson) /data is also mounted with nodelalloc (etc/fstab), so a file's data is on
the disk before the metadata that names it; x86's /data line is "auto" (btrfs, or ext4 from before it), and
data-durable remounts it with nodelalloc (ext4) or flushoncommit (btrfs) once the type is known. Repairing state
that is already damaged is a separate step (recover, rescue console).

  onemind-k3s-state settle
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time

# Namespaces the OS itself owns. A workload in any other namespace belongs to the owner (apps).
SYSTEM_NAMESPACES = frozenset({"kube-system", "kube-public", "kube-node-lease", "default", "onemind-system"})
SETTLE_TIMEOUT_S = 900
SETTLE_POLL_S = 2
SETTLE_GRACE_S = 5          # k3s keeps writing for a moment after its first setup looks done


class Paths:
    """Every path touched, under one root (tests point it at a temp dir)."""

    def __init__(self, root: str = "/"):
        j = lambda *p: os.path.join(root, *p)
        self.root = root
        self.k3s = j("data", "k3s")
        self.server = j("data", "k3s", "server")
        self.agent = j("data", "k3s", "agent")
        self.node_dir = j("data", "state", "etc-rancher-node")      # bind-mounted at /etc/rancher/node
        self.node_password = j("data", "state", "etc-rancher-node", "password")
        self.settled = j("data", "onemind", "firstboot", "k3s-settled")
        self.role = j("data", "onemind", "etc", "role")
        self.kubeconfig = j("run", "k3s", "k3s.yaml")
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
    """The files k3s makes on its first start and needs to start again (the F26 definition, plus the rest of
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


def _rel(p: Paths, path: str) -> str:
    return os.path.relpath(path, p.data)


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
    """Journal and console."""
    log(msg)
    console(p, msg)


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
                       f"{bad[0][1]}); first setup not marked done")
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="onemind-k3s-state", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("ONEMIND_FIRSTBOOT_ROOT", "/"))
    ap.add_argument("cmd", choices=("settle",))
    a = ap.parse_args(argv)
    return settle(Paths(a.root))


if __name__ == "__main__":
    sys.exit(main())
