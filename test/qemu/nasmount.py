# SPDX-License-Identifier: Apache-2.0
"""NAS client step of the QEMU battery (issue #871; criteria: test/qemu/CRITERIA-NAS.md, TN0-TN2).

Called by run-tests.py right after T1, on the booted slot A. It checks that the image carries the SMB and NFS
client tools and nothing that serves (TN0), then mounts a throw-away export from the guest itself over NFSv4
(TN1) and SMB 3.1.1 (TN2) on 127.0.0.1 and reads a fresh random token back.

The image ships no NFS server tools (no nfs-kernel-server: #871 adds clients only). The NFS export is therefore
made with the kernel's own server (the nfsd module) and fed the way rpc.mountd would: one line each into the
kernel's auth.unix.ip, nfsd.fh and nfsd.export caches (/proc/net/rpc/<cache>/channel), NFSv4 only, with a
listener added through /proc/fs/nfsd/portlist (no rpcbind needed). The SMB export is a throw-away smbd (Samba is
already in the image for D-017) with its own config under /run on port 4450, never onemind-smb.service.
Everything lives under /run/onemind-nastest and is removed at the end.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
D = "/run/onemind-nastest"
DOMAIN = "onemind-nastest"
SMB_PORT = 4450
# nfsd.export flags (include/uapi/linux/nfsd/export.h): READONLY 0x1 | NOSUBTREECHECK 0x400 | FSID 0x2000.
# FSID is required for a filesystem without a backing device (tmpfs), with fsid 0 = the NFSv4 root.
EXPORT_FLAGS = 0x1 | 0x400 | 0x2000
CLIENT_PKGS = ("cifs-utils", "nfs-common")
SERVER_PKGS = ("nfs-kernel-server", "ksmbd-tools")
MODULES = ("cifs", "nfs", "nfsv4")


def slot_budget_mib(layout_text):
    """Size of the system slot A partition in a board's layout.yaml, in MiB (the read-only root must fit it)."""
    m = re.search(r"label:\s*onemind-system-a\b[^}\n]*?\bsize:\s*(\d+)\s*(GiB|MiB)", layout_text)
    if not m:
        raise ValueError("layout has no sized onemind-system-a partition")
    return int(m.group(1)) * (1024 if m.group(2) == "GiB" else 1)


def tn0_verdict(t, budget_mib):
    """TN0 from the NAME=value tags the guest printed (dict of str -> str or None). Returns (ok, detail dict)."""
    def num(k):
        try:
            return int(t.get(k) or "")
        except ValueError:
            return None
    d = {
        "clients_installed": all(num(f"PKG_{p}") == 1 for p in CLIENT_PKGS),
        "no_server_pkgs": all(num(f"SRV_{p}") == 0 for p in SERVER_PKGS),
        "modules": all((num(f"MOD_{m}") or 0) >= 1 for m in MODULES),
        "manifest_sizes_kib": {p: num(f"MAN_{p}") for p in CLIENT_PKGS},
        "units_enabled": num("UNITS_ENABLED"),
        "units_active": num("UNITS_ACTIVE"),
        "root_used_mib": num("ROOT_USED_MIB"),
        "budget_mib": budget_mib,
    }
    ok = (d["clients_installed"] and d["no_server_pkgs"] and d["modules"]
          and all((v or 0) > 0 for v in d["manifest_sizes_kib"].values())
          and d["units_enabled"] == 0 and d["units_active"] == 0
          and d["root_used_mib"] is not None and 0 < d["root_used_mib"] < budget_mib)
    return ok, d


def tn0_command():
    pk = " ".join(CLIENT_PKGS)
    return ("for p in " + pk + "; do echo \"PKG_$p=$(dpkg-query -W -f='${Status}' $p 2>/dev/null | grep -c 'ok installed')\"; "
            "echo \"MAN_$p=$(awk -v p=$p '$1==p {print $4}' /usr/lib/onemind/packages.txt)\"; done; "
            "for p in " + " ".join(SERVER_PKGS) + "; do echo \"SRV_$p=$(dpkg-query -W -f='${Status}' $p 2>/dev/null | grep -c 'ok installed')\"; done; "
            "for m in " + " ".join(MODULES) + "; do echo \"MOD_$m=$(modinfo -k $(uname -r) -F filename $m 2>/dev/null | grep -c '\\.ko')\"; done; "
            "echo \"UNITS_ENABLED=$(systemctl list-unit-files --no-legend --state=enabled 'rpcbind*' 'nfs*' 'rpc-*' | wc -l)\"; "
            "echo \"UNITS_ACTIVE=$(systemctl list-units --no-legend --state=active 'rpcbind*' 'nfs*' 'rpc-*' | wc -l)\"; "
            "echo \"ROOT_USED_MIB=$(df -B1M --output=used / | tail -n1 | tr -d ' ')\"")


def nfs_commands():
    """Guest commands for TN1, in order. The last one prints NFS_TYPE and NFS_READ."""
    return [
        f"rm -rf {D}/nfs-export {D}/nfs-mnt; mkdir -p {D}/nfs-export {D}/nfs-mnt; "
        f"tok=$(cat /proc/sys/kernel/random/uuid); echo \"$tok\" > {D}/nfs-export/token.txt; "
        f"chmod 0755 {D}/nfs-export; chmod 0644 {D}/nfs-export/token.txt",
        # Server: nfsd module, NFSv4 only (v2/v3 would need rpcbind), short lease and grace, one TCP listener.
        "modprobe nfsd && (mountpoint -q /proc/fs/nfsd || mount -t nfsd nfsd /proc/fs/nfsd) && "
        "echo 10 > /proc/fs/nfsd/nfsv4leasetime && echo 10 > /proc/fs/nfsd/nfsv4gracetime && "
        "echo '-2 -3' > /proc/fs/nfsd/versions && echo 'tcp 2049' > /proc/fs/nfsd/portlist && "
        "echo 4 > /proc/fs/nfsd/threads; echo \"NFSD_THREADS=$(cat /proc/fs/nfsd/threads)\"",
        # What rpc.mountd would answer: 127.0.0.1 is client DOMAIN; fsid 0 (the v4 root) is the export directory.
        # One second after the start, so no cache flush made in the start's second can expire these entries.
        "sleep 1; exp=$(( $(date +%s) + 3600 )); "
        f"printf '%s %s %s %s\\n' nfsd 127.0.0.1 \"$exp\" {DOMAIN} > /proc/net/rpc/auth.unix.ip/channel && "
        f"printf '%s %s %s %s %s\\n' {DOMAIN} 1 '\\x00000000' \"$exp\" {D}/nfs-export > /proc/net/rpc/nfsd.fh/channel && "
        f"printf '%s %s %s %s %s %s %s\\n' {DOMAIN} {D}/nfs-export \"$exp\" {EXPORT_FLAGS} 65534 65534 0 "
        "> /proc/net/rpc/nfsd.export/channel; echo \"NFS_CACHES=$?\"",
        "sleep 12",  # the 10 s NFSv4 grace period: OPEN is refused until it ends
        f"timeout 90 mount -t nfs4 -o ro,soft,timeo=50,retrans=2,retry=1 127.0.0.1:/ {D}/nfs-mnt; "
        f"echo \"NFS_TYPE=$(findmnt -no FSTYPE {D}/nfs-mnt)\"; "
        f"echo \"NFS_READ=$([ \"$(timeout 30 cat {D}/nfs-mnt/token.txt)\" = \"$tok\" ] && echo ok || echo bad)\"",
    ]


def nfs_teardown():
    return (f"umount {D}/nfs-mnt && echo NFS_UMOUNT=ok; echo 0 > /proc/fs/nfsd/threads; now=$(date +%s); "
            "for c in nfsd.export nfsd.fh auth.unix.ip; do echo \"$now\" > /proc/net/rpc/$c/flush; done; "
            f"rm -rf {D}/nfs-export {D}/nfs-mnt")


def smb_commands():
    """Guest commands for TN2, in order. The last one prints SMB_TYPE and SMB_READ."""
    s = f"{D}/smb"
    conf = ["[global]", f"smb ports = {SMB_PORT}", "bind interfaces only = yes", "interfaces = lo",
            "server min protocol = SMB3", "disable netbios = yes", "map to guest = Bad User", "guest account = nobody",
            "load printers = no", "printing = bsd", "printcap name = /dev/null", "disable spoolss = yes",
            f"lock directory = {s}/lock", f"state directory = {s}/state", f"cache directory = {s}/cache",
            f"private dir = {s}/private", f"pid directory = {s}/pid", f"ncalrpc dir = {s}/ncalrpc",
            f"binddns dir = {s}/bind-dns", f"log file = {s}/log.%m",
            "[nastest]", f"path = {D}/smb-export", "read only = yes", "guest ok = yes", "guest only = yes"]
    quoted = " ".join("'" + line + "'" for line in conf)
    return [
        f"rm -rf {s} {D}/smb-export {D}/smb-mnt; mkdir -p {s}/lock {s}/state {s}/cache {s}/private {s}/pid "
        f"{s}/ncalrpc {s}/bind-dns {D}/smb-export {D}/smb-mnt; chmod 0700 {s}/private; "
        f"tok=$(cat /proc/sys/kernel/random/uuid); echo \"$tok\" > {D}/smb-export/token.txt; "
        f"chmod 0755 {D}/smb-export; chmod 0644 {D}/smb-export/token.txt",
        f"printf '%s\\n' {quoted} > {s}/smb.conf && smbd -D -s {s}/smb.conf; "
        f"for i in $(seq 30); do ss -ltn | grep -q ':{SMB_PORT} ' && break; sleep 1; done; "
        f"echo \"SMB_LISTEN=$(ss -ltn | grep -c ':{SMB_PORT} ')\"",
        f"timeout 90 mount -t cifs -o ro,guest,vers=3.1.1,port={SMB_PORT} //127.0.0.1/nastest {D}/smb-mnt; "
        f"echo \"SMB_TYPE=$(findmnt -no FSTYPE {D}/smb-mnt)\"; "
        f"echo \"SMB_READ=$([ \"$(timeout 30 cat {D}/smb-mnt/token.txt)\" = \"$tok\" ] && echo ok || echo bad)\"",
    ]


def smb_teardown():
    return (f"umount {D}/smb-mnt && echo SMB_UMOUNT=ok; for f in {D}/smb/pid/*.pid; do kill $(cat $f); done; sleep 1; "
            f"tail -n 5 {D}/smb/log.smbd 2>/dev/null; rm -rf {D}/smb {D}/smb-export {D}/smb-mnt")


def run(vm, record, tag, board):
    """TN0-TN2 on the booted guest. `tag` reads a NAME=value line from guest output (run-tests.tag)."""
    with open(os.path.join(HERE, "..", "..", "os", "boards", board, "layout.yaml")) as f:
        budget_mib = slot_budget_mib(f.read())
    vm.mark("TN0 NAS client tools in the image, nothing serving")
    _, o = vm.run(tn0_command())
    keys = [f"PKG_{p}" for p in CLIENT_PKGS] + [f"MAN_{p}" for p in CLIENT_PKGS] + [f"SRV_{p}" for p in SERVER_PKGS] \
        + [f"MOD_{m}" for m in MODULES] + ["UNITS_ENABLED", "UNITS_ACTIVE", "ROOT_USED_MIB"]
    ok, d = tn0_verdict({k: tag(o, k) for k in keys}, budget_mib)
    record("TN0", ok, " ".join(f"{k}={v}" for k, v in d.items()))

    vm.mark("TN1 NFSv4 loopback mount of a throw-away export")
    out = ""
    for c in nfs_commands():
        out += vm.run(c, 240)[1]
    ntype, nread = tag(out, "NFS_TYPE"), tag(out, "NFS_READ")
    _, t = vm.run(nfs_teardown(), 120)
    record("TN1", ntype == "nfs4" and nread == "ok" and tag(t, "NFS_UMOUNT") == "ok",
           f"nfsd_threads={tag(out, 'NFSD_THREADS')} caches_rc={tag(out, 'NFS_CACHES')} fstype={ntype} token={nread} "
           f"umount={tag(t, 'NFS_UMOUNT')}")

    vm.mark("TN2 SMB 3.1.1 loopback mount of a throw-away share")
    out = ""
    for c in smb_commands():
        out += vm.run(c, 240)[1]
    stype, sread = tag(out, "SMB_TYPE"), tag(out, "SMB_READ")
    _, t = vm.run(smb_teardown(), 120)
    record("TN2", stype in ("cifs", "smb3") and sread == "ok" and tag(t, "SMB_UMOUNT") == "ok",
           f"listening={tag(out, 'SMB_LISTEN')} fstype={stype} token={sread} umount={tag(t, 'SMB_UMOUNT')}")
