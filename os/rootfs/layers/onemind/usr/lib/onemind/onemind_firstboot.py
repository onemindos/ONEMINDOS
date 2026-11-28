# SPDX-License-Identifier: Apache-2.0
"""OneMind first boot (docs/leap/core/IMAGES.md §3): role, per-box secrets, role services, the mesh.

Runs on every boot as onemind-firstboot.service, with the gateway venv's Python (stdlib, PyYAML and
onemind_core, whose box CA and NATS key code this file reuses so an image box and a
deploy/install.sh box are set up the same way, IMG-MESH-01 #292).

  onemind-firstboot apply        configure once (role + secrets on /data), then start the role's units
  onemind-firstboot configure    --role R [--name N] [--join-code C] [--hub-addr IP] (same as the wizard)
  onemind-firstboot kubeconfig   hub: wait for k3s, write the gateway's ServiceAccount kubeconfig
  onemind-firstboot mesh         hub: Headscale up, the hub joins its own mesh, NATS leaf port, gateway mesh
                                 settings (onemind-mesh-setup.service; every boot, skips what is done)
  onemind-firstboot join         worker/leaf: `onemind fabric join` with the saved join code
                                 (onemind-fabric-join.service; the owner approves on the hub)

Where the settings come from, first match wins:
  1. a cloud-init / NoCloud seed: `onemind:` mapping in the #cloud-config user-data
     (cloud-init's copy on cloud boards, else a filesystem labelled CIDATA/cidata, read-only)
  2. /boot/efi/onemind.conf: key = value lines a user edits after flashing (renamed .applied after use)
  3. none: start the local setup wizard (onemind-setup.service, http://onemind.local:8080/)

The root filesystem is read-only, so all state is under /data/onemind and every unit is started
at runtime (`systemctl start`), never enabled in /etc. The owner token is printed once on the
console (never into the journal) and handed to the wizard through /run (tmpfs). The mesh keys
(Headscale pre-auth key, Headscale API key) never reach the journal or the console either.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import pathlib
import pwd
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

ROLES = ("hub", "worker", "leaf")
# Started on every boot. A unit whose Condition* is not met yet is skipped without error (for
# example tailscaled before the box CA exists, or the NATS leaf before `onemind fabric join` wrote
# its config); whoever creates the missing file starts the unit itself.
ROLE_UNITS = {
    "hub": ["onemind-starting.service", "onemind-nats.service", "onemind-nats-accounts.path", "onemindd.service", "onemind-gateway.service",
            "onemind-gateway-kube.service", "tailscaled.service", "onemind-headscale.service",
            "onemind-mesh-setup.service", "onemind-rescue.service", "onemind-host.service",
            "onemind-storage.service", "onemind-images.service"],
    # A worker and a leaf both get the mesh and a local NATS leaf (internal/fabric Installer.Apply).
    "worker": ["tailscaled.service", "onemind-nats-leaf.service", "onemindd.service", "onemind-fabric-join.service"],
    "leaf": ["tailscaled.service", "onemind-nats-leaf.service", "onemindd.service", "onemind-fabric-join.service"],
}
# A box configured before IMG-MESH-01 (state.json without "mesh") keeps the units it was set up for.
LEGACY_ROLE_UNITS = {
    "hub": ["onemind-nats.service", "onemindd.service", "onemind-gateway.service", "onemind-gateway-kube.service",
            "onemind-rescue.service", "onemind-host.service"],
    "worker": ["onemindd.service"],
    "leaf": ["onemind-nats.service", "onemindd.service"],
}
KEYS = ("role", "name", "join_code", "hub_addr")
NAME_RE = re.compile(r"^[^\x00-\x1f\"\\]{1,64}$")
SCHEMA = "onemind.firstboot/v1"

# The join code the owner gets from `onemind fabric ticket` or the dashboard (core/onemind_core/
# fabric.py builds it; internal/fabric/join.go ParseQR reads it):
#   onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=<sha256 of the box CA>&role=worker|leaf&hub=<https URL, %-encoded>
JOIN_CODE_RE = re.compile(r"^onemind-join:v1\?[A-Za-z0-9%=&._:/-]{20,620}$")
TICKET_RE = re.compile(r"^[0-9A-Za-z]{4}-?[0-9A-Za-z]{4}-?[0-9A-Za-z]{4}$")   # join.go codeRe
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")

HS_PORT = 8444            # Headscale's own TLS listener until onemind-edge fronts it on :443 (deploy/install.sh)
CONTROL_URL = f"https://control.onemind.internal:{HS_PORT}"
MESH_V4 = ipaddress.ip_network("100.64.0.0/10")
HOSTS_BEGIN = "# BEGIN onemind fabric (managed by onemind fabric join)"   # same markers as install.sh and
HOSTS_END = "# END onemind fabric"                                      # internal/fabric/install.go
ONEMIND_CLI = "/usr/bin/onemind"
ONEMINDD = "/usr/bin/onemindd"
HEADSCALE = "/usr/bin/headscale"
TAILSCALE = "/usr/bin/tailscale"
LAN_WAIT_S = 60          # how long `mesh` waits for a LAN IPv4 address (a slow DHCPv4 lease)
JOIN_TIMEOUT = "20m"      # how long `onemind fabric join` waits for the owner's approval


class ConfigError(ValueError):
    pass


class Paths:
    """Every path the program touches, under one root (tests point it at a temp dir)."""

    def __init__(self, root: str = "/"):
        j = lambda *p: os.path.join(root, *p)
        self.root = root
        self.data = j("data", "onemind")
        self.etc = j("data", "onemind", "etc")
        self.secrets = j("data", "onemind", "secrets")
        self.identity = j("data", "onemind", "identity")
        self.gateway = j("data", "onemind", "gateway")
        self.photos = os.path.join(self.gateway, "photos")                # default ONEMIND_PHOTOS_DIR
        self.tls = j("data", "onemind", "gateway", "tls")              # the box CA (ONEMIND_NET_TLS_DIR)
        self.accounts = j("data", "onemind", "gateway", "nats", "accounts.conf")
        self.nats_keys = j("data", "onemind", "nats", "keys")
        self.hs_conf = j("data", "onemind", "etc", "headscale", "config.yaml")
        self.hs_key = j("data", "onemind", "etc", "headscale.key")
        self.hs_sock = j("run", "onemind-headscale", "headscale.sock")
        self.ts_state = j("var", "lib", "tailscale", "tailscaled.state")  # tailscaled's own state (bind from /data)
        self.lan_file = j("data", "onemind", "etc", "lan-addr")
        self.join_code = j("data", "onemind", "secrets", "join-code")
        self.fabric_state = j("data", "onemind", "etc", "fabric.json")  # written by `onemind fabric join`
        self.hosts = j("etc", "hosts")                                   # a bind mount from /data on the image
        self.state = j("data", "onemind", "firstboot", "state.json")
        self.esp_conf = j("boot", "efi", "onemind.conf")
        self.esp_boot = j("boot", "efi", "EFI", "BOOT")                  # grub.cfg, grubenv and user.cfg live here
        self.esp_user_cfg = j("boot", "efi", "EFI", "BOOT", "user.cfg")  # the boot menu lock (os/assemble/grub.cfg.in)
        self.cloud_userdata = j("var", "lib", "cloud", "instance", "user-data.txt")
        self.seed_mnt = j("run", "onemind", "seed")
        self.run = j("run", "onemind")
        self.console = j("dev", "console")
        self.lib = j("usr", "lib", "onemind")
        self.custodian = j("data", "onemind", "custodian")              # the gateway's backup job key (IMG-BACKUP-01)
        self.job_key = j("data", "onemind", "custodian", "job.key")
        self.backup = j("data", "onemind", "backup")                     # the agent's state; agent.json is its settings
        self.backup_conf = j("data", "onemind", "backup", "agent.json")
        self.backup_export = j("data", "onemind", "gateway", "backup-export")  # the built-ins' export (#616)
        self.rescue_tls = j("data", "onemind", "tls")   # https.crt/https.key for onemind-rescue (CORE-UPDATE-9)
        self.files = j("data", "onemind", "files")      # the gateway's ONEMIND_FILES_ROOT (and Samba's shares)
        self.k3s_data = j("data", "k3s")                # k3s --data-dir (a leaf removes it, retire_k3s)
        self.k3s_run = j("run", "k3s")                  # tmpfs: exists only if k3s started on this boot


# ------------------------------------------------------------------ settings
def parse_conf(text: str) -> dict:
    """key = value lines; '#' comments; unknown keys rejected so a typo is not silently ignored."""
    out = {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ConfigError(f"line {n}: expected key = value")
        k, v = (s.strip() for s in line.split("=", 1))
        k = k.lower().replace("-", "_")
        if k not in KEYS:
            raise ConfigError(f"line {n}: unknown key {k!r} (known: {', '.join(KEYS)})")
        out[k] = v.strip("\"'")
    return out


def parse_userdata(text: str) -> dict | None:
    """The `onemind:` mapping of a #cloud-config document, or None when it has none."""
    if not text.lstrip().startswith("#cloud-config"):
        return None
    import yaml  # in the gateway venv
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"user-data is not valid YAML: {exc.__class__.__name__}") from exc
    if not isinstance(doc, dict) or "onemind" not in doc:
        return None
    om = doc["onemind"]
    if not isinstance(om, dict):
        raise ConfigError("user-data: 'onemind' must be a mapping")
    out = {}
    for k, v in om.items():
        k = str(k).lower().replace("-", "_")
        if k not in KEYS:
            raise ConfigError(f"user-data: unknown key onemind.{k}")
        out[k] = "" if v is None else str(v)
    return out


def parse_join_code(text: str) -> dict:
    """Check a join code as strictly as `onemind fabric join` does (internal/fabric/join.go ParseQR and
    Ticket.Validate), before anything is written. The '#' of a conf comment never appears in a code."""
    text = text.strip()
    if not JOIN_CODE_RE.match(text):
        raise ConfigError("join_code: expected the onemind-join:v1?... text from `onemind fabric ticket` or the dashboard")
    try:
        q = parse_qs(text.split("?", 1)[1], keep_blank_values=False, strict_parsing=True)
    except ValueError:
        raise ConfigError("join_code: malformed") from None
    if set(q) - {"code", "ca", "role", "hub"} or any(len(v) != 1 for v in q.values()):
        raise ConfigError("join_code: unexpected or repeated fields")
    t = {k: q.get(k, [""])[0] for k in ("code", "ca", "role", "hub")}
    if not TICKET_RE.match(t["code"]):
        raise ConfigError("join_code: the one-time code must look like 7KQ4-M2XP-9D3F")
    if not SHA_RE.match(t["ca"]):
        raise ConfigError("join_code: the box CA fingerprint must be 64 hex characters")
    if t["role"] not in ("", "worker", "leaf"):
        raise ConfigError("join_code: role must be worker or leaf")
    u = urlsplit(t["hub"])
    if (u.scheme != "https" or not u.hostname or u.username or u.password or u.path not in ("", "/")
            or u.query or u.fragment or not (HOSTNAME_RE.match(u.hostname) or _is_ip(u.hostname))):
        raise ConfigError("join_code: the hub must be an https URL such as https://box.local")
    t["ca"] = t["ca"].lower()
    return t


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def validate(cfg: dict) -> dict:
    role = cfg.get("role", "").strip().lower()
    if role not in ROLES:
        raise ConfigError(f"role must be one of {', '.join(ROLES)} (got {role!r})")
    out = {"role": role, "name": cfg.get("name", "").strip() or "OneMind"}
    if not NAME_RE.match(out["name"]):
        raise ConfigError("name: 1-64 printable characters, no quotes or backslashes")
    code, addr = cfg.get("join_code", "").strip(), cfg.get("hub_addr", "").strip()
    if role == "hub":
        if code or addr:
            raise ConfigError("join_code and hub_addr are for a worker or leaf; a hub makes join codes")
        return out
    if not code:
        raise ConfigError("join_code: required for this role. On the hub run `onemind fabric ticket` "
                          "(or Add a device on the dashboard) and copy the onemind-join:v1?... code")
    t = parse_join_code(code)
    if t["role"] and t["role"] != role:
        raise ConfigError(f"join_code: this code is for a {t['role']}, but role is {role}")
    out["join_code"] = code
    if addr:
        if not _is_ip(addr):
            raise ConfigError("hub_addr: the hub's IP address (used when <box>.local does not resolve)")
        out["hub_addr"] = str(ipaddress.ip_address(addr))
    return out


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def find_seed_device() -> str | None:
    for label in ("cidata", "CIDATA"):
        p = f"/dev/disk/by-label/{label}"
        if os.path.exists(p):
            return p
    return None


def read_nocloud(p: Paths, mount: bool = True) -> dict | None:
    text = _read(p.cloud_userdata)
    if text is None and mount:
        dev = None
        for _ in range(10):                 # udev may still be naming disks this early
            dev = find_seed_device()
            if dev:
                break
            time.sleep(1)
        if dev:
            os.makedirs(p.seed_mnt, exist_ok=True)
            if subprocess.run(["mount", "-o", "ro", dev, p.seed_mnt], capture_output=True).returncode == 0:
                try:
                    text = _read(os.path.join(p.seed_mnt, "user-data"))
                finally:
                    subprocess.run(["umount", p.seed_mnt], capture_output=True)
    return parse_userdata(text) if text else None


def find_config(p: Paths, mount: bool = True) -> tuple[dict | None, str | None]:
    cfg = read_nocloud(p, mount)
    if cfg is not None:
        return validate(cfg), "nocloud"
    text = _read(p.esp_conf)
    if text is not None:
        cfg = parse_conf(text)
        if cfg.get("role"):
            return validate(cfg), "esp"
    return None, None


# ------------------------------------------------------------------ files
def run_dir(p: "Paths") -> None:
    """/run/onemind, mode 0711: other users may pass through to a socket they are allowed on (the
    gateway to /run/onemind/host.sock and storage.sock) but cannot list it; the files in it stay 0600.
    A folder an earlier boot step made 0700 is loosened to 0711, never tightened or widened further."""
    os.makedirs(p.run, mode=0o711, exist_ok=True)
    os.chmod(p.run, 0o711)


def write(path: str, data: str, mode: int = 0o600, owner: tuple[int, int] | None = None) -> bool:
    """Atomic write: a power cut leaves the old file or the new one, never half of one.
    Returns False (and touches nothing) when the file already has exactly this content, mode and owner."""
    try:
        st = os.stat(path)
        if ((st.st_mode & 0o7777) == mode and (owner is None or (st.st_uid, st.st_gid) == owner)
                and _read(path) == data):
            return False
    except OSError:
        pass
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        if owner:
            os.chown(tmp, *owner)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


def user_ids(name: str) -> tuple[int, int] | None:
    """uid/gid of a system user made at image build time (onemind 961, onemind-nats 962,
    onemind-headscale 963); None where it does not exist (tests, a developer machine)."""
    try:
        pw = pwd.getpwnam(name)
        return pw.pw_uid, pw.pw_gid
    except KeyError:
        return None


def onemind_ids() -> tuple[int, int] | None:
    return user_ids("onemind")


def chown_tree(path: str, ids: tuple[int, int] | None) -> None:
    """Re-own a tree. A file that is gone by the time it is reached is skipped: something else may be working
    in the tree (k3s unpacks its binaries into a *-tmp folder and renames it), and one vanished file must not
    fail first boot, which would leave the box without its role units (cloud C4 reboot, issue #391)."""
    if not ids or not os.path.isdir(path):
        return
    for dirpath, _dirs, files in os.walk(path):
        for n in [dirpath, *(os.path.join(dirpath, f) for f in files)]:
            try:
                os.chown(n, *ids)
            except FileNotFoundError:
                pass


def token() -> str:
    return secrets.token_hex(32)


# ------------------------------------------------------------------ boot menu lock
# GRUB's menu is locked (os/assemble/grub.cfg.in): the A/B entries boot with no password, but editing an
# entry's command line or opening the GRUB shell needs the superuser "onemind". The password is made here,
# once per box, so no two boxes share one and none ships in the image. Only its PBKDF2 hash goes on the ESP
# (GRUB format, the one grub-mkpasswd-pbkdf2 prints); the password is shown once on the console.
BOOT_USER = "onemind"
BOOT_PW_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i: it is typed at a bare console
BOOT_PW_GROUPS = 5                                     # 5 groups of 4 from 31 symbols: about 99 bits
GRUB_PBKDF2_ROUNDS = 10000                             # grub-mkpasswd-pbkdf2's default


def boot_password() -> str:
    return "-".join("".join(secrets.choice(BOOT_PW_ALPHABET) for _ in range(4)) for _ in range(BOOT_PW_GROUPS))


def grub_pbkdf2(password: str, salt: bytes | None = None, rounds: int = GRUB_PBKDF2_ROUNDS) -> str:
    """`grub.pbkdf2.sha512.<rounds>.<salt hex>.<hash hex>`, as GRUB's password_pbkdf2 command expects
    (grub-core/lib/crypto.c, grub_crypto_pbkdf2 with HMAC-SHA512 and a 64-byte hash)."""
    salt = salt if salt is not None else secrets.token_bytes(64)
    h = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, rounds, 64)
    return f"grub.pbkdf2.sha512.{rounds}.{salt.hex().upper()}.{h.hex().upper()}"


def ensure_boot_lock(p: Paths) -> str | None:
    """Give this box its boot menu password the first time. Returns the password to show, or None when it
    already has one or the box has no GRUB ESP (a board that boots another way). Never raises: a full or
    read-only ESP must not stop first boot (the menu then stays locked with no password: nobody can edit it)."""
    if not os.path.isdir(p.esp_boot) or os.path.exists(p.esp_user_cfg):
        return None
    pw = boot_password()
    try:
        write(p.esp_user_cfg, f"password_pbkdf2 {BOOT_USER} {grub_pbkdf2(pw)}\n", mode=0o600)
    except OSError as exc:
        log(f"could not write the boot menu password hash ({exc}); the boot menu stays locked for everyone")
        return None
    return pw


def lan_addr() -> str | None:
    """The IPv4 address this box's default route leaves from, read once (at first boot, or by `mesh`
    if the network was not up yet) and kept in /data/onemind/etc/lan-addr. connect() on a UDP socket
    sends no packet: it only asks the kernel which route and source address it would use.
    192.0.2.1 is TEST-NET-1 (RFC 5737), an address no real host has.
    A LAN without a router (offline, or QEMU's restrict=on network) gives no default route; then the
    box's one global IPv4 address on a real interface is its LAN address, if it has exactly one."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        addr = s.getsockname()[0]
    except OSError:
        addr = ""
    finally:
        s.close()
    if addr and not addr.startswith(("0.", "127.")):
        return addr
    try:
        r = run_cmd(["ip", "-4", "-o", "addr", "show", "scope", "global"])
    except OSError:
        return None
    return only_lan_addr(r.stdout) if r.returncode == 0 else None


# Interfaces that are never the LAN: the mesh, k3s (flannel, CNI, pods), containers, bridges.
VIRTUAL_IFACES = ("lo", "tailscale", "flannel", "cni", "veth", "kube", "docker", "virbr", "br-")


def only_lan_addr(ip_addr_out: str) -> str | None:
    """From `ip -4 -o addr show scope global`, the single LAN IPv4 address; None if none or several."""
    found = set()
    for line in ip_addr_out.splitlines():
        f = line.split()                       # "2: enp0s1    inet 192.0.2.10/24 brd ... scope global ..."
        if len(f) < 4 or f[2] != "inet" or f[1].startswith(VIRTUAL_IFACES):
            continue
        try:
            ip = ipaddress.IPv4Address(f[3].split("/")[0])
        except ValueError:
            continue
        if not (ip.is_loopback or ip.is_link_local or ip in MESH_V4):
            found.add(str(ip))
    return found.pop() if len(found) == 1 else None


def known_lan(p: Paths) -> str | None:
    v = (_read(p.lan_file) or "").strip()
    try:
        return str(ipaddress.IPv4Address(v))
    except ValueError:
        return None


# ------------------------------------------------------------------ the box CA and NATS keys (onemind_core)
def box_ca(p: Paths, box: str):
    """The gateway's own box CA (core/onemind_core/ca.py), in the gateway's tls dir. One CA signs the
    HTTPS certificate, Headscale's control certificate and the NATS leaf listener (IMG-MESH-01)."""
    from pathlib import Path

    from onemind_core.ca import BoxCA  # the gateway venv
    return BoxCA(Path(p.tls), box)


def make_ca(p: Paths, box: str) -> str:
    """Create (or keep) the box CA with the HTTPS and control certificates, then publish its
    certificate as /data/onemind/identity/ca.pem, the file tailscaled trusts (SSL_CERT_FILE).
    The CA key stays in the gateway's tls dir only. Returns the CA's sha256 fingerprint."""
    ca = box_ca(p, box)
    ca.ensure_https_cert()
    ca.ensure_control_cert()
    os.makedirs(p.identity, mode=0o755, exist_ok=True)
    os.chmod(p.identity, 0o755)
    write(os.path.join(p.identity, "ca.pem"), _read(os.path.join(p.tls, "ca.crt")), 0o644)
    return ca.ca_fingerprint()


def nats_service_keys(p: Paths) -> None:
    """Service nkeys for the hub's own NATS clients (CORE-SEC-4, #161), as deploy/install.sh nats_install:
    the keys dir is root's, so the gateway can read its own seed but cannot replace onemindd's."""
    from pathlib import Path

    from onemind_core import natsconf
    os.makedirs(p.nats_keys, mode=0o755, exist_ok=True)
    os.chmod(os.path.dirname(p.nats_keys), 0o755)
    os.chmod(p.nats_keys, 0o755)
    for name in ("gateway", "onemindd"):
        natsconf.make_service_key(Path(p.nats_keys), name)
    ids = onemind_ids()
    if ids:
        os.chown(os.path.join(p.nats_keys, "gateway.nk"), *ids)
    # The first accounts file (hub account with the two service keys); the gateway owns and rewrites it.
    os.environ.setdefault("ONEMIND_FABRIC_JETSTREAM_MAX_BYTES", str(jetstream_max_bytes(p)))
    natsconf.main([p.accounts, p.nats_keys])


# The hub NATS reads copies of these from its runtime dir (onemind-nats.service, onemind-nats-files).
NATS_RUN = "/run/onemind-nats"
# The hub's JetStream store: the bind mount /var/lib/onemind-nats (fstab), on the data disk.
JETSTREAM_MOUNT = "/var/lib/onemind-nats"
JETSTREAM_DIR = JETSTREAM_MOUNT + "/jetstream"


def jetstream_max_bytes(p: Paths) -> int:
    """The hub's JetStream cap: a share of the data disk (core/onemind_core/jetstream.py, #601), never a
    fixed size. Read from the disk's total size, so the same disk always gives the same cap. A disk too
    small for JetStream raises: the hub is not set up with an uncapped or a useless store."""
    from onemind_core import jetstream  # the gateway venv (stdlib only at import)
    d = os.path.dirname(p.data)  # /data
    while not os.path.exists(d) and os.path.dirname(d) != d:
        d = os.path.dirname(d)   # not mounted yet (or a test root): the disk that will hold it
    return jetstream.cap_for_path(d)


# onemind-nats.service waits for the mesh address only when this line is in nats.conf. A box set up before
# IMG-MESH-01 has its own `leafnodes {` block (no mesh), so matching that would make it wait and fail.
MESH_LEAF_MARKER = "# onemind: mesh leaf listener"


def hub_nats_conf(mesh_ip: str | None = None, js_max_bytes: int | None = None) -> str:
    """The hub NATS as deploy/install.sh nats_install writes it: clients on loopback only, each with its
    own nkey (the included accounts file); with the mesh, the leaf-node listener on the hub's mesh
    address with TLS from the box CA, and nodes must present a certificate from it (verify).
    `js_max_bytes` is the JetStream cap (default: jetstream_max_bytes of /data); 0 or less is refused (#601)."""
    if js_max_bytes is None:
        js_max_bytes = jetstream_max_bytes(Paths("/"))
    if isinstance(js_max_bytes, bool) or not isinstance(js_max_bytes, int) or js_max_bytes <= 0:
        raise ValueError("hub nats.conf: JetStream without a cap is refused (#601)")
    out = ("# Written by onemind-firstboot (docs/leap/core/IMAGES.md §3; NETWORKING.md §7). Do not edit.\n"
           "# No shared secret: every client signs in with its own nkey (nats-accounts.conf, public keys only).\n"
           "server_name: hub\nlisten: 127.0.0.1:4222\nhttp: 127.0.0.1:8222\nmax_payload: 1MB\n"
           "# A dead leaf link shows within about a minute instead of 3-7 (FB-3 lab, observation \"outage detection\").\n"
           'ping_interval: "20s"\nping_max: 2\nwrite_deadline: "10s"\n'
           "# JetStream for app event streams (streams.py): file store only on the data disk, capped\n"
           "# in total; the ONEMIND account gets the same cap in nats-accounts.conf (natsconf.py).\n"
           f'jetstream {{\n  store_dir: "{JETSTREAM_DIR}"\n  max_file_store: {js_max_bytes}\n  max_memory_store: 0\n}}\n')
    if mesh_ip:
        out += (f"{MESH_LEAF_MARKER}\n"
                "leafnodes {\n"
                f'  listen: "{mesh_ip}:7422"\n'
                "  tls {\n"
                f'    cert_file: "{NATS_RUN}/nats.crt"\n'
                f'    key_file: "{NATS_RUN}/nats.key"\n'
                f'    ca_file: "{NATS_RUN}/ca.crt"\n'
                "    verify: true\n"
                "    timeout: 5\n"
                "  }\n}\n")
    else:
        out += "# No leaf-node listener yet: `onemind-firstboot mesh` adds it on the hub's mesh address.\n"
    return out + 'include "nats-accounts.conf"\n'


def gateway_env(p: Paths, st: dict, mesh_ip: str | None = None, js_max_bytes: int | None = None) -> str:
    """gateway.env, as deploy/install.sh gateway_env, from the state and what `mesh` found."""
    g, box, lan = p.gateway, st["box"], known_lan(p)
    js_max_bytes = jetstream_max_bytes(p) if js_max_bytes is None else js_max_bytes
    out = ("# Written by onemind-firstboot (core/README.md \"Environment\"; deploy/install.sh gateway_env)\n"
           f"ONEMIND_TOKENS_FILE={g}/tokens.yaml\nONEMIND_DATA_DIR={g}\n"
           f"ONEMIND_DB_URL=sqlite:///{g}/onemind.db\nONEMIND_AUDIT_PATH={g}/audit.jsonl\n"
           "ONEMIND_APPS_DIR=/usr/lib/onemind/apps\nONEMIND_CATALOG_DIR=/data/onemind/catalog\nONEMIND_APP_SCHEMA=/usr/lib/onemind/sdk/schema/onemind.app.schema.json\n"
           "ONEMIND_SANDBOX_RULES=/usr/lib/onemind/sdk/policy/app-objects.yaml\n"
           "ONEMIND_DASHBOARD_DIST=/usr/lib/onemind/dashboard\nONEMIND_EXECUTOR=kubernetes\n"
           f"ONEMIND_KUBECTL=/usr/lib/onemind/bin/kubectl\nKUBECONFIG={g}/kubeconfig\n"
           "ONEMIND_NATS_URL=nats://127.0.0.1:4222\n"
           "# Files (core/onemind_core/files) live on the data partition, not in the read-only root; storage\n"
           "# actions talk to onemind-storage.service (onemindd storage serve) on /run/onemind/storage.sock.\n"
           "ONEMIND_FILES_ROOT=/data/onemind/files\nONEMIND_STORAGE_ENABLED=1\n"
           f"ONEMIND_NODE_ID={st['node_id']}\nONEMIND_INSTANCE_NAME={st['name']}\n"
           "# Plain HTTP :8080 is loopback only once ONEMIND_NET_TLS=1 (H-05, serve.py): local tools and the gate.\n"
           "ONEMIND_HOST=0.0.0.0\nONEMIND_PORT=8080\nONEMIND_GATEWAY_URL=http://onemind.local:8080\n"
           "# Networking (core/onemind_core/netconf.py; NETWORKING.md): HTTPS with the box CA on 443 and 8443,\n"
           "# onemind.local and <box>.local over mDNS (avahi).\n"
           f"ONEMIND_NET_BOX_NAME={box}\n"
           + (f"ONEMIND_NET_LAN_ADDR={lan}\n" if lan else "")
           + f"ONEMIND_NET_TLS=1\nONEMIND_NET_TLS_DIR={p.tls}\nONEMIND_NET_MDNS=1\n"
           "# Fabric joins (owner-approved). ONEMIND_FABRIC_K3S stays off: image workers have no k3s agent yet.\n"
           f"ONEMIND_FABRIC_HUB_URL=https://{box}.local\n"
           f"ONEMIND_FABRIC_NATS_ACCOUNTS_FILE={p.accounts}\n"
           f"ONEMIND_FABRIC_NATS_SERVICE_KEYS={p.nats_keys}\n"
           f"ONEMIND_FABRIC_NATS_NKEY_SEED={p.nats_keys}/gateway.nk\n"
           f"ONEMIND_FABRIC_JETSTREAM_MAX_BYTES={js_max_bytes}\nONEMIND_FABRIC_JETSTREAM_PATH={JETSTREAM_MOUNT}\n")
    out += backup_gateway_env(p)
    if mesh_ip:
        out += ("# The mesh (written by `onemind-firstboot mesh` once the hub has its mesh address).\n"
                "ONEMIND_MESH_ENABLED=1\n"
                f"ONEMIND_MESH_HEADSCALE_URL=https://127.0.0.1:{HS_PORT}\n"
                f"ONEMIND_MESH_CONTROL_URL={CONTROL_URL}\n"
                f"ONEMIND_MESH_HEADSCALE_KEY_FILE={p.hs_key}\n"
                f"ONEMIND_MESH_HUB_IP={mesh_ip}\n")
    return out


# Keys gateway_env() writes only some of the time: an old line of these is first boot's own, never kept.
FIRSTBOOT_GATEWAY_KEYS = frozenset({"ONEMIND_NET_LAN_ADDR", "ONEMIND_BACKUPS_ENABLED", "ONEMIND_BACKUPS_JOB_KEY_FILE",
                                    "ONEMIND_BACKUPS_EXPORT_DIR", "ONEMIND_BACKUPS_AGENT_DIRS",
                                    "ONEMIND_BACKUPS_AGENT_PATHS"})
_ENV_KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=")


def keep_operator_env(old: str | None, new: str) -> str:
    """A rewrite of gateway.env keeps every setting first boot never writes, word for word: the operator's
    own lines, such as the Photos hard-off (ONEMIND_PHOTOS_ENABLED=0) or a relocated ONEMIND_PHOTOS_DIR.
    Without this the mesh step's rewrite would switch Photos back on with its default library."""
    ours = {m.group(1) for m in map(_ENV_KEY.match, new.splitlines()) if m} | FIRSTBOOT_GATEWAY_KEYS
    kept = [line for line in (old or "").splitlines()
            if (m := _ENV_KEY.match(line)) and m.group(1) not in ours]
    if not kept:
        return new
    return new + "# Kept from the earlier gateway.env: settings onemind-firstboot does not write.\n" + "\n".join(kept) + "\n"


# ------------------------------------------------------------------ hub: backups (IMG-BACKUP-01)
# restic ships in the image (/usr/lib/onemind/restic). The agent runs inside onemindd and starts when
# agent.json exists; the gateway drives it when ONEMIND_BACKUPS_ENABLED=1. No destination is set here:
# the owner adds one and approves it, and setup stays gated on the emergency (recovery) kit.
K3S_BACKUP_VERSION = "v1.37.2-k3s1"     # os/versions.lock.yaml k3s.version, "+" written as "-"


def backup_system_paths(p: Paths) -> list[str]:
    """What the agent's `system` unit copies as files: settings, the box CA, NATS keys, and (#616) the
    built-ins' table export the gateway writes before each run plus the built-in folders on this box."""
    return [p.etc, p.tls, p.nats_keys, p.backup_export, p.files, p.photos]


def agent_paths_line(p: Paths) -> str:
    """ONEMIND_BACKUPS_AGENT_PATHS: the folders agent.json's system unit really copies. The gateway counts a
    built-in folder as backed up only inside one of them, so a relocated library reads as outside the backup."""
    try:
        paths = json.loads(_read(p.backup_conf) or "{}")["units"]["system"]["paths"]
    except (KeyError, TypeError, ValueError):
        paths = None
    if not isinstance(paths, list) or not all(isinstance(x, str) for x in paths):
        paths = backup_system_paths(p)
    return f"ONEMIND_BACKUPS_AGENT_PATHS={','.join(paths)}\n"


def builtin_backup_env(p: Paths) -> str:
    """Tells the gateway where to write the built-ins' export and which default folders the agent copies."""
    return ("# Built-in apps' data in the system unit (#616; core/onemind_core/backups/units.py).\n"
            f"ONEMIND_BACKUPS_EXPORT_DIR={p.backup_export}\n"
            "ONEMIND_BACKUPS_AGENT_DIRS=ONEMIND_FILES_ROOT,ONEMIND_PHOTOS_DIR\n" + agent_paths_line(p))


def backup_gateway_env(p: Paths) -> str:
    """The gateway's backup lines; empty until the job key and agent.json both exist, so a half-done setup
    (a failed key, or an agent with no settings to start from) never reports backups as on."""
    if not (os.path.exists(p.job_key) and os.path.exists(p.backup_conf)):
        return ""
    return ("# Backups (core/onemind_core/backups; onemind-firstboot ensure_backup).\n"
            f"ONEMIND_BACKUPS_ENABLED=1\nONEMIND_BACKUPS_JOB_KEY_FILE={p.job_key}\n" + builtin_backup_env(p))


def backup_agent_conf(p: Paths, node_id: str) -> dict:
    """agent.json for the image (the same keys deploy/backup.sh writes for the developer install)."""
    s = p.backup
    return {
        "box_id": node_id, "node_id": node_id, "generation": 0,
        "state_dir": s, "scratch_dir": f"{s}/scratch", "device_key_file": f"{s}/secrets/device.key",
        "restic": {"binary": "/usr/lib/onemind/restic", "cache_dir": f"{s}/cache"},
        "sqlite3_binary": "/usr/bin/sqlite3",
        "listen": "127.0.0.1:7480",
        "job_pubkey_file": f"{s}/job.pub",
        "storage_roots": ["/data/k3s/storage"],
        "schedule": {"minute": -1, "maintenance_hour": 3, "verify_weekday": 0, "verify_min_age": "1h",
                     "gateway_hourly": True},
        "retention": {"hourly": 24, "daily": 7, "weekly": 4, "monthly": 12},
        "targets": [],
        "units": {
            "system": {"paths": backup_system_paths(p),
                       "sqlite": [{"path": f"{p.gateway}/onemind.db", "name": "gateway.db"}],
                       "audit_log": f"{p.gateway}/audit.jsonl"},
            "k3s": {"paths": ["/data/k3s/server/token", "/data/k3s/server/tls",
                              "/data/k3s/server/cred"],
                    "state_db": "/data/k3s/server/db/state.db", "version": K3S_BACKUP_VERSION},
        },
    }


def _append_missing(path: str, key: str, text: str) -> None:
    """Append text to an env file unless it already sets key (the file is 0600, so keep the mode)."""
    old = _read(path)
    if old is None or re.search(rf"(?m)^{key}=", old):
        return
    write(path, old + ("" if old.endswith("\n") else "\n") + text)


def upgrade_agent_conf(p: Paths) -> None:
    """A box set up before #616 keeps its agent.json; add the system paths it lacks, change nothing else."""
    conf = json.loads(_read(p.backup_conf) or "{}")
    system = conf.get("units", {}).get("system")
    if not isinstance(system, dict):
        return
    paths = list(system.get("paths") or [])
    missing = [x for x in backup_system_paths(p) if x not in paths]
    if missing:
        system["paths"] = paths + missing
        write(p.backup_conf, json.dumps(conf, indent=2) + "\n")


def upgrade_backup_gateway_env(p: Paths) -> None:
    """Upgrade the old generated folder list, preserving operator-managed backup settings, and keep
    ONEMIND_BACKUPS_AGENT_PATHS equal to what agent.json copies now."""
    path = os.path.join(p.etc, "gateway.env")
    old = _read(path)
    if old is None or not re.search(r"(?m)^ONEMIND_BACKUPS_ENABLED=", old):
        return
    new = old
    if not re.search(r"(?m)^ONEMIND_PHOTOS_DIR=", old):
        new = re.sub(r"(?m)^ONEMIND_BACKUPS_AGENT_DIRS=ONEMIND_FILES_ROOT$",
                     "ONEMIND_BACKUPS_AGENT_DIRS=ONEMIND_FILES_ROOT,ONEMIND_PHOTOS_DIR", new)
    line, seen = agent_paths_line(p), []
    if re.search(r"(?m)^ONEMIND_BACKUPS_AGENT_PATHS=", new):   # one line, where the first one was
        new = re.sub(r"(?m)^ONEMIND_BACKUPS_AGENT_PATHS=.*\n?",
                     lambda _m: "" if seen else (seen.append(1) or line), new)
    else:
        new += ("" if new.endswith("\n") else "\n") + line
    if new != old:
        write(path, new)


def make_gateway_dir(path: str, ids: tuple[int, int] | None, mode: int = 0o700) -> None:
    """Make a folder in the gateway's own tree for the gateway, as root, without switching user (the
    wizard's helper has no CAP_SETUID/CAP_SETGID) and without following a link the gateway placed there:
    the parent and the folder are opened with O_NOFOLLOW, so a symlink raises instead of being followed."""
    parent, name = os.path.split(path.rstrip("/"))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    pfd = os.open(parent, flags)
    try:
        made = False
        try:
            os.mkdir(name, mode, dir_fd=pfd)
            made = True
        except FileExistsError:
            pass
        fd = os.open(name, flags, dir_fd=pfd)
        try:
            if made:
                os.fchmod(fd, mode)
                if ids:
                    os.fchown(fd, *ids)
        finally:
            os.close(fd)
    finally:
        os.close(pfd)


def ensure_backup(p: Paths, st: dict) -> None:
    """Make a hub able to back up: the gateway's job key (its public half for the agent), agent.json and the
    two env files. Idempotent, so boxes set up before backups get it on their next boot. Any failure is
    logged and leaves backups off; it never stops the box from booting."""
    if st.get("role") != "hub":
        return
    try:
        ids = onemind_ids()
        for d, mode, owner in ((p.custodian, 0o700, ids), (p.backup, 0o700, None)):
            os.makedirs(d, mode=mode, exist_ok=True)
            os.chmod(d, mode)
            if owner:
                os.chown(d, *owner)
        if not os.path.exists(p.job_key):
            from onemind_core.backups.jobs import load_or_create_job_key  # the gateway venv
            load_or_create_job_key(pathlib.Path(p.job_key))
        if ids:
            chown_tree(p.custodian, ids)
        pub = os.path.join(p.backup, "job.pub")
        with open(os.path.join(p.custodian, "job.pub"), encoding="utf-8") as f:
            write(pub, f.read(), 0o644)
        # The gateway writes the built-ins' export here; the agent must find it at its first run (#616).
        os.makedirs(p.backup_export, mode=0o700, exist_ok=True)
        os.chmod(p.backup_export, 0o700)
        if ids:
            os.chown(p.backup_export, *ids)
        # The agent requires every configured source to exist, even before the first upload. The gateway
        # owns this folder and its parent: made for it without following a link it may have put there.
        os.makedirs(p.gateway, mode=0o750, exist_ok=True)
        make_gateway_dir(p.photos, ids)
        if not os.path.exists(p.backup_conf):
            write(p.backup_conf, json.dumps(backup_agent_conf(p, st["node_id"]), indent=2) + "\n")
        else:
            upgrade_agent_conf(p)
        _append_missing(os.path.join(p.etc, "onemindd.env"), "ONEMIND_BACKUP_CONF",
                        f"# Backups (IMG-BACKUP-01): onemindd starts the backup agent from this file.\n"
                        f"ONEMIND_BACKUP_CONF={p.backup_conf}\n")
        _append_missing(os.path.join(p.etc, "gateway.env"), "ONEMIND_BACKUPS_ENABLED", backup_gateway_env(p))
        _append_missing(os.path.join(p.etc, "gateway.env"), "ONEMIND_BACKUPS_EXPORT_DIR", builtin_backup_env(p))
        upgrade_backup_gateway_env(p)
    except Exception as e:  # noqa: BLE001
        log(f"backups not set up: {e}")


def headscale_config(lan: str) -> str:
    """deploy/install.sh headscale_install's config, port 8444, with the image's state directory."""
    return f"""# Written by onemind-firstboot (NETWORKING.md §4.2; same as deploy/install.sh). Do not edit.
server_url: {CONTROL_URL}
listen_addr: 0.0.0.0:{HS_PORT}
metrics_listen_addr: 127.0.0.1:9091
grpc_listen_addr: 127.0.0.1:50443
grpc_allow_insecure: false
tls_cert_path: /run/onemind-headscale/tls.crt
tls_key_path: /run/onemind-headscale/tls.key
noise:
  private_key_path: /var/lib/onemind-headscale/noise_private.key
prefixes:
  v4: 100.64.0.0/10
  v6: fd7a:115c:a1e0::/48
  allocation: sequential
derp:
  server:
    enabled: true
    region_id: 999
    region_code: onemind-hub
    region_name: OneMind hub
    verify_clients: true
    stun_listen_addr: 0.0.0.0:3478
    private_key_path: /var/lib/onemind-headscale/derp_server_private.key
    automatically_add_embedded_derp_region: true
    ipv4: {lan}
  urls: []
  paths: []
  auto_update_enabled: false
disable_check_updates: true
ephemeral_node_inactivity_timeout: 30m
database:
  type: sqlite
  sqlite:
    path: /var/lib/onemind-headscale/db.sqlite
    write_ahead_log: true
policy:
  mode: database
dns:
  magic_dns: true
  base_domain: onemind.internal
  override_local_dns: false
  nameservers:
    global: []
unix_socket: /run/onemind-headscale/headscale.sock
unix_socket_permission: "0770"
logtail:
  enabled: false
log:
  level: info
"""


def set_hosts(path: str, addr: str) -> bool:
    """The managed block of deploy/install.sh hosts_block: the coordinator names point at addr.
    /etc/hosts is a file bind mount on the image, which a rename cannot replace, so it is rewritten
    in place (as internal/fabric does). Returns True if it changed."""
    old = _read(path) or ""
    keep, skip = [], False
    for line in old.splitlines():
        if line == HOSTS_BEGIN:
            skip = True
        elif line == HOSTS_END:
            skip = False
        elif not skip:
            keep.append(line)
    new = "\n".join(keep + [HOSTS_BEGIN, f"{addr} control.onemind.internal join.onemind.internal", HOSTS_END]) + "\n"
    if new == old:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
        f.flush()
        os.fsync(f.fileno())
    return True


# ------------------------------------------------------------------ rescue console TLS (CORE-UPDATE-9)
def issue_rescue_cert(p: Paths, hostname: str) -> str:
    """Hub only (CORE-UPDATE-9): the HTTPS pair for the rescue console on :7443, signed by the box CA.
    Kept if present. The key stays root-only: the rescue unit runs as root, the gateway never reads it.
    Returns "kept" or "created"."""
    d = p.rescue_tls
    key, csr, crt = (os.path.join(d, f) for f in ("https.key", "https.csr", "https.crt"))
    if os.path.exists(key) and os.path.exists(crt):
        return "kept"
    # The box CA: in the gateway's tls dir since IMG-MESH-01 (box_ca); a box set up before the mesh keeps
    # it in identity/.
    ca_dir = p.tls if os.path.exists(os.path.join(p.tls, "ca.key")) else p.identity
    ca_key = os.path.join(ca_dir, "ca.key")
    ca_crt = os.path.join(ca_dir, "ca.crt" if ca_dir == p.tls else "ca.pem")
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    ext = os.path.join(d, "https.ext")
    if ca_dir == p.tls:
        # The mesh-era box CA has name constraints (core/onemind_core/ca.py): it may sign only onemind.local,
        # <box>.local, onemind.internal and mesh addresses. A name outside them (bare host, localhost,
        # 127.0.0.1) makes every verifier reject the whole certificate, so ask only for permitted names.
        san = f"DNS:{hostname}.local,DNS:onemind.local"
    else:
        san = f"DNS:{hostname},DNS:{hostname}.local,DNS:onemind.local,DNS:localhost,IP:127.0.0.1"
    write(ext, f"subjectAltName={san}\nextendedKeyUsage=serverAuth\n", 0o600)
    run = lambda *a: subprocess.run(a, check=True, capture_output=True)
    try:
        run("openssl", "req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
            "-subj", f"/O=OneMind/CN={hostname}", "-keyout", key, "-out", csr)
        run("openssl", "x509", "-req", "-in", csr, "-CA", ca_crt,
            "-CAkey", ca_key, "-CAcreateserial", "-days", "825", "-sha256",
            "-extfile", ext, "-out", crt)
    finally:
        for f in (csr, ext):
            if os.path.exists(f):
                os.remove(f)
    os.chmod(key, 0o600)
    os.chmod(crt, 0o644)
    return "created"


def ensure_rescue_tls(p: Paths) -> None:
    """Never fatal: without the pair the rescue unit refuses to start and the rest of the box is unaffected."""
    try:
        name = box_name(socket.gethostname())   # the same DNS-safe name the box CA uses
    except Exception:  # noqa: BLE001 - a name problem must not stop the box
        name = "onemind"
    try:
        issue_rescue_cert(p, name)
    except (OSError, subprocess.CalledProcessError) as e:
        log(f"rescue console certificate not made: {e}")



# ------------------------------------------------------------------ configure
def configure(p: Paths, cfg: dict, source: str) -> str | None:
    """Write role, secrets and service settings. Returns the owner token (hub) or None.
    state.json is written last: until it exists, the next boot configures again from scratch."""
    role = cfg["role"]
    # /data/onemind/etc is 0711: services running as their own users (onemind-headscale, onemind-nats,
    # the gateway's onemind) may open the files meant for them by name, but nobody can list the dir.
    # Every secret in it stays 0600.
    for d, mode in ((p.etc, 0o711), (p.secrets, 0o700)):
        os.makedirs(d, mode=mode, exist_ok=True)
        os.chmod(d, mode)
    node_id = hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:12]
    write(os.path.join(p.etc, "node-id"), node_id + "\n", 0o644)
    st = {"schema": SCHEMA, "role": role, "name": cfg["name"], "source": source, "node_id": node_id, "mesh": 1}
    owner = None
    if role == "hub":
        box = box_name(socket.gethostname())
        lan = lan_addr()
        if lan:
            write(p.lan_file, lan + "\n", 0o644)
        st["box"] = box
        st["ca_sha256"] = make_ca(p, box)
        ensure_rescue_tls(p)                # CORE-UPDATE-9: needs the box CA above
        nats_service_keys(p)
        write(os.path.join(p.etc, "nats.conf"), hub_nats_conf(None, jetstream_max_bytes(p)))
        write(os.path.join(p.etc, "onemindd.env"),
              "# Written by onemind-firstboot (contract §1)\n"
              "ONEMIND_NATS_URL=nats://127.0.0.1:4222\n"
              f"ONEMIND_NATS_NKEY_SEED={p.nats_keys}/onemindd.nk\n"
              f"ONEMIND_NODE_ROLE=hub\nONEMIND_NODE_ID={node_id}\nONEMIND_DISK_PATH=/data\n")
        ids = onemind_ids()
        os.makedirs(p.gateway, mode=0o750, exist_ok=True)
        if ids:
            os.chown(p.gateway, *ids)
        owner = token()
        h = hashlib.sha256(owner.encode()).hexdigest()
        write(os.path.join(p.gateway, "tokens.yaml"),
              "# OneMind gateway principals (written by onemind-firstboot; only sha256 of each token).\n"
              f"tokens:\n  \"sha256:{h}\": {{id: owner, kind: person, role: owner, retire_on_setup: true}}\n", 0o600, ids)
        ensure_backup(p, st)
        write(os.path.join(p.etc, "gateway.env"), gateway_env(p, st))
        chown_tree(p.gateway, ids)          # BoxCA and natsconf ran as root: the gateway must own its tree
    else:
        # Until the join, onemindd has no bus; `onemind fabric join` points it at the local leaf.
        write(os.path.join(p.etc, "onemindd.env"),
              "# Written by onemind-firstboot (contract §1); `onemind fabric join` updates it\n"
              "ONEMIND_NATS_URL=nats://127.0.0.1:4222\nONEMIND_NODE_ROLE=node\n"
              f"ONEMIND_NODE_ID={node_id}\nONEMIND_DISK_PATH=/data\n")
        # tailscaled trusts /data/onemind/identity/ca.pem (its unit's SSL_CERT_FILE and Condition); the join
        # writes the box CA to $ONEMIND_ETC_DIR/identity/ca.pem before it restarts tailscaled, so this
        # link makes both names one file.
        if not os.path.lexists(p.identity):
            os.symlink(os.path.join("etc", "identity"), p.identity)
        write(p.join_code, cfg["join_code"] + "\n")
        if cfg.get("hub_addr"):
            st["hub_addr"] = cfg["hub_addr"]
        st["hub"] = parse_join_code(cfg["join_code"])["hub"]
    write(os.path.join(p.etc, "role"), role + "\n", 0o644)
    st["configured_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write(p.state, json.dumps(st, indent=2) + "\n", 0o644)
    return owner


def box_name(hostname: str) -> str:
    from onemind_core.ca import box_name_from_hostname
    return box_name_from_hostname(hostname)


def load_state(p: Paths) -> dict | None:
    text = _read(p.state)
    if not text:
        return None
    try:
        st = json.loads(text)
    except json.JSONDecodeError:
        return None
    return st if isinstance(st, dict) and st.get("role") in ROLES else None


# ------------------------------------------------------------------ side effects on the box
def console(p: Paths, msg: str) -> None:
    """To the console only (the owner token must never land in the journal)."""
    try:
        with open(p.console, "a") as c:
            c.write(msg + "\n")
    except OSError:
        pass


def log(msg: str) -> None:
    print(f"onemind-firstboot: {msg}", flush=True)


def systemctl(*args: str) -> int:
    return subprocess.run(["systemctl", *args], check=False).returncode


def run_cmd(argv: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a helper with its output captured (never printed: some of it is a key)."""
    return subprocess.run(argv, capture_output=True, text=True, env=env, check=False)


def run_stream(argv: list[str], env: dict, on_line) -> int:
    """Run a command, handing each output line to on_line as it comes (the join's progress)."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    assert proc.stdout is not None
    for line in proc.stdout:
        on_line(line.rstrip("\n"))
    return proc.wait()


def ensure_files_root(p: Paths) -> None:
    """Make the files root (ONEMIND_FILES_ROOT) before the gateway starts. Its unit lists the folder in
    ReadWritePaths=, and systemd refuses to start a unit whose read-write path is missing (226/NAMESPACE):
    the mount namespace is set up before any ExecStartPre= runs, even a "+" one, so the unit cannot make it
    itself. Only the folder is (re-)owned, never its contents. Every boot, so updated boxes get it too."""
    os.makedirs(p.files, mode=0o750, exist_ok=True)
    os.chmod(p.files, 0o750)
    ids = onemind_ids()
    if ids:
        os.chown(p.files, *ids)


# What k3s writes under its --data-dir. /data/k3s itself and /data/k3s/storage are made on every box by
# onemind-data-layout.service and tmpfiles.d/onemind-backup.conf, so they stay.
K3S_WRITES = ("server", "agent", "data")


def retire_k3s(p: Paths) -> None:
    """An edge (role leaf, #751) never runs a k3s server, yet the image boots one before the box has a role.
    k3s.service skips itself once the role file says leaf (k3s.service.d/20-onemind-leaf.conf); this stops the
    one that ran on the boot the role was picked, and on a later boot, when k3s never started (no /run/k3s, a
    tmpfs), removes what it left on /data: its own server token, certificates and datastore. Never while k3s
    may still hold the folder. Pods it started keep running until the next restart (KillMode=process).
    Only a k3s that is already running is stopped: a stop sent while its start job still waits (for
    network-online.target) would cancel that job, so k3s would never reach its condition and the skip would
    not show (CRITERIA-EDGE.md EG2 found this)."""
    try:
        state = run_cmd(["systemctl", "show", "-p", "ActiveState", "--value", "k3s.service"]).stdout.strip()
    except OSError:
        state = "unknown"                  # no systemctl: never remove anything on a guess
    running = os.path.lexists(p.k3s_run) or state in ("active", "activating", "reloading")
    if running:
        systemctl("stop", "--no-block", "k3s.service")
    left = [os.path.join(p.k3s_data, d) for d in K3S_WRITES if os.path.lexists(os.path.join(p.k3s_data, d))]
    if running or state not in ("inactive", "failed") or not left:
        return
    for d in left:
        shutil.rmtree(d, ignore_errors=True)
    msg = "ONEMIND-FIRSTBOOT: edge: removed the k3s state left from before the role was picked"
    log(msg); console(p, msg)


def start_units(p: Paths, st: dict) -> None:
    role = st["role"]
    if role == "leaf":
        retire_k3s(p)
    if role == "hub":
        ensure_files_root(p)               # before the gateway: its sandbox needs the folder to exist
        ensure_rescue_tls(p)               # boxes configured before CORE-UPDATE-9 get their pair now
        # uid of "onemind" is fixed in the image (961), but re-own after an update anyway.
        chown_tree(p.gateway, onemind_ids())
        ensure_backup(p, st)               # boxes configured before IMG-BACKUP-01 get backups on this boot
    units = ROLE_UNITS if st.get("mesh") else LEGACY_ROLE_UNITS
    systemctl("start", "--no-block", *units[role])


def apply(p: Paths) -> int:
    st = load_state(p)
    if st:
        msg = f"ONEMIND-FIRSTBOOT: already configured role={st['role']} node_id={st.get('node_id', '?')}"
        log(msg); console(p, msg)
        if not st.get("mesh"):
            msg = ("ONEMIND-FIRSTBOOT: this box was set up before the mesh (IMG-MESH-01) and keeps running as it is; "
                   "to put it on the mesh, reinstall it (docs/leap/core/IMAGES.md §3)")
            log(msg); console(p, msg)
        start_units(p, st)
        return 0
    try:
        cfg, source = find_config(p)
    except ConfigError as exc:
        msg = f"ONEMIND-FIRSTBOOT: invalid settings ({exc}); waiting for the setup wizard"
        log(msg); console(p, msg)
        systemctl("start", "--no-block", "onemind-setup.service")
        return 0
    if cfg is None:
        msg = "ONEMIND-FIRSTBOOT: not configured; waiting for the setup wizard at http://onemind.local:8080/"
        log(msg); console(p, msg)
        systemctl("start", "--no-block", "onemind-setup.service")
        return 0
    return finish(p, cfg, source)


def join_hint(p: Paths) -> str:
    lan = known_lan(p) or "<this hub's LAN address>"
    return ("ONEMIND-FIRSTBOOT: to join a worker or leaf: on this hub run `onemind fabric ticket` (or Add a device "
            "on the dashboard) for a join code, then put `join_code = <the code>` and "
            f"`hub_addr = {lan}` in onemind.conf on the new box (LAN address of this hub: {lan})")


def finish(p: Paths, cfg: dict, source: str) -> int:
    owner = configure(p, cfg, source)
    if source == "esp":
        try:
            os.replace(p.esp_conf, p.esp_conf + ".applied")
        except OSError:
            pass
    st = load_state(p)
    msg = f"ONEMIND-FIRSTBOOT: configured role={cfg['role']} source={source} node_id={st['node_id']}"
    log(msg); console(p, msg)
    boot_pw = ensure_boot_lock(p)
    if boot_pw:
        console(p, f"ONEMIND BOOT MENU PASSWORD (user {BOOT_USER}, shown once, only its hash is stored): {boot_pw}")
        run_dir(p)
        write(os.path.join(p.run, "boot-menu-password"), boot_pw + "\n")   # tmpfs: for the recovery kit, gone at reboot
    if owner:
        console(p, "ONEMIND-FIRSTBOOT: the owner token below is shown once; only its sha256 is stored.")
        console(p, f"ONEMIND OWNER TOKEN: {owner}")
        run_dir(p)
        write(os.path.join(p.run, "owner-token"), owner + "\n")  # tmpfs: for the wizard, gone at reboot
        ca = f"ONEMIND-FIRSTBOOT: box CA sha256 {st.get('ca_sha256', '?')} (https://{st.get('box')}.local/v1/tls/ca.crt)"
        log(ca); console(p, ca)
        hint = join_hint(p)
        log(hint); console(p, hint)
    start_units(p, st)
    return 0


# ------------------------------------------------------------------ hub: the mesh
class MeshError(RuntimeError):
    pass


def _hs(p: Paths, *args: str) -> subprocess.CompletedProcess:
    return run_cmd([HEADSCALE, "-c", p.hs_conf, *args])


def _json(r: subprocess.CompletedProcess, what: str):
    if r.returncode != 0:
        raise MeshError(f"{what} failed (exit {r.returncode})")    # stdout/stderr may hold a key: not logged
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise MeshError(f"{what}: output is not JSON") from None


def mesh(p: Paths, sleep=time.sleep) -> int:
    """Hub only, every boot (onemind-mesh-setup.service): what deploy/install.sh does in
    headscale_install, mesh_hub, box_certs (NATS certificate) and nats_install, skipping what is done."""
    st = load_state(p)
    if not st or st["role"] != "hub":
        log("mesh: not a hub; nothing to do")
        return 0
    if not st.get("mesh"):
        log("mesh: this box was set up before the mesh (IMG-MESH-01); reinstall to use it")
        return 0
    try:
        ip = _mesh(p, st, sleep)
    except MeshError as exc:
        msg = f"ONEMIND-FIRSTBOOT: mesh setup failed: {exc}; it is tried again at the next boot (journalctl -u onemind-mesh-setup)"
        log(msg); console(p, msg)
        return 1
    msg = f"ONEMIND-FIRSTBOOT: mesh up: hub {ip} on the mesh, LAN address {known_lan(p)}"
    log(msg); console(p, msg)
    return 0


def _mesh(p: Paths, st: dict, sleep) -> str:
    # 1. The LAN address: read at first boot, or now if the network was not up then.
    lan = known_lan(p)
    if not lan:
        # The box can be "online" before its DHCPv4 lease: an IPv6 router advertisement is enough for
        # network-online.target unless the .network file says otherwise, and DHCP servers can be slow.
        for _ in range(LAN_WAIT_S):
            lan = lan_addr()
            if lan:
                break
            sleep(1)
        else:
            raise MeshError(f"this box got no LAN IPv4 address in {LAN_WAIT_S} s (no default route and no single LAN address), so none for the mesh relay")
        write(p.lan_file, lan + "\n", 0o644)
        log(f"mesh: LAN address {lan}")
    # 2. Headscale's config; its user reads it, nobody else needs it (no secret in it).
    hs_ids = user_ids("onemind-headscale")
    hs_dir = os.path.dirname(p.hs_conf)
    os.makedirs(hs_dir, mode=0o750, exist_ok=True)
    os.chmod(hs_dir, 0o750)
    if hs_ids:
        os.chown(hs_dir, *hs_ids)
    if write(p.hs_conf, headscale_config(lan), 0o640, hs_ids):
        log("mesh: Headscale config written")
        systemctl("restart", "onemind-headscale.service")
    else:
        systemctl("start", "onemind-headscale.service")
    # 3. Wait for its local socket.
    for _ in range(60):
        if os.path.exists(p.hs_sock) and _hs(p, "users", "list", "-o", "json").returncode == 0:
            break
        sleep(1)
    else:
        raise MeshError("Headscale did not start (journalctl -u onemind-headscale)")
    log("mesh: Headscale is up")
    # 4. The coordinator names point at this hub (deploy/install.sh hosts_block 127.0.0.1).
    if set_hosts(p.hosts, "127.0.0.1"):
        log("mesh: /etc/hosts block written")
    # 5. tailscaled, then the hub joins its own coordinator with a key minted over the local socket.
    systemctl("start", "tailscaled.service")
    # A hub that joined before (tailscaled has state) gets its address back by itself; give it time
    # instead of minting a new key, which would register the hub a second time.
    first_wait = "60s" if os.path.exists(p.ts_state) else "5s"
    if run_cmd([ONEMINDD, "mesh", "wait-ip", "--timeout", first_wait]).returncode != 0:
        users = _json(_hs(p, "users", "list", "-o", "json"), "headscale users list") or []
        if not any(u.get("name") == "onemind-machines" for u in users):
            if _hs(p, "users", "create", "onemind-machines").returncode != 0:
                raise MeshError("headscale users create failed")
            users = _json(_hs(p, "users", "list", "-o", "json"), "headscale users list") or []
        uid = next((u.get("id") for u in users if u.get("name") == "onemind-machines"), None)
        if uid is None:
            raise MeshError("Headscale user onemind-machines is missing")
        key = _json(_hs(p, "preauthkeys", "create", "--user", str(uid), "--tags", "tag:onemind-hub,tag:onemind-k3s",
                        "--expiration", "10m", "-o", "json"), "headscale preauthkeys create").get("key", "")
        if not key:
            raise MeshError("Headscale returned no pre-auth key")
        run_dir(p)
        keyfile = os.path.join(p.run, "hub-authkey")
        write(keyfile, key)
        del key
        log("mesh: the hub joins its own coordinator")
        try:
            r = run_cmd([TAILSCALE, "up", "--reset", "--login-server", CONTROL_URL, "--auth-key", f"file:{keyfile}",
                         "--hostname", "hub", "--accept-routes=false", "--accept-dns=false", "--ssh=false",
                         "--timeout", "60s"])
        finally:
            os.remove(keyfile)
        if r.returncode != 0:
            raise MeshError(f"tailscale up failed (exit {r.returncode}): {r.stderr.strip()[-300:]}")
    # 6. The hub's mesh address.
    r = run_cmd([ONEMINDD, "mesh", "wait-ip", "--timeout", "60s"])
    ip = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ""
    try:
        if ipaddress.IPv4Address(ip) not in MESH_V4:
            raise ValueError
    except ValueError:
        raise MeshError("the hub did not get a mesh address (tailscale status)") from None
    log(f"mesh: hub is {ip} on the mesh")
    # 7. The NATS leaf listener's certificate for that address, from the same box CA.
    box_ca(p, st["box"]).ensure_nats_cert(ip)
    chown_tree(p.tls, onemind_ids())
    # 8. The gateway's Headscale API key (approved joins mint node keys with it).
    if not (_read(p.hs_key) or "").strip():
        r = _hs(p, "apikeys", "create", "--expiration", "90d")
        lines = r.stdout.strip().splitlines() if r.returncode == 0 else []
        if not lines or not lines[-1].strip():
            raise MeshError(f"headscale apikeys create failed (exit {r.returncode})")
        write(p.hs_key, lines[-1].strip() + "\n", 0o600, onemind_ids())
        log("mesh: gateway Headscale API key written")
    # 9. NATS gets its leaf listener; the gateway its mesh settings. Restart what changed.
    changed = []
    if write(os.path.join(p.etc, "nats.conf"), hub_nats_conf(ip, jetstream_max_bytes(p))):
        changed.append("onemind-nats.service")
    gw_env = os.path.join(p.etc, "gateway.env")
    if write(gw_env, keep_operator_env(_read(gw_env), gateway_env(p, st, ip))):
        changed.append("onemind-gateway.service")
    if changed:
        log("mesh: restarting " + " ".join(changed))
        systemctl("try-restart", *changed)
    return ip


# ------------------------------------------------------------------ worker / leaf: the join
def join(p: Paths) -> int:
    """`onemind fabric join` with the code from onemind.conf (onemind-fabric-join.service). The code is
    one-use and expires; the owner approves the request on the hub. The CLI reads it from its 0600
    file (--code-file), so it never shows in the process list, the journal or the console."""
    st = load_state(p)
    if not st or st["role"] == "hub":
        return 0
    if os.path.exists(p.fabric_state):
        if os.path.exists(p.join_code):
            os.remove(p.join_code)
        log("join: already joined")
        return 0
    code = (_read(p.join_code) or "").strip()
    if not code:
        log("join: no join code saved; nothing to do")
        return 0
    try:
        parse_join_code(code)
    except ConfigError as exc:
        msg = f"ONEMIND-FIRSTBOOT: the saved join code is not valid ({exc})"
        log(msg); console(p, msg)
        return 1
    argv = [ONEMIND_CLI, "fabric", "join", "--code-file", p.join_code, "--timeout", JOIN_TIMEOUT]
    if st.get("hub_addr"):
        argv += ["--hub-addr", st["hub_addr"]]
    msg = ("ONEMIND-FIRSTBOOT: joining the hub; approve this box on the hub's dashboard (Approvals) "
           f"after checking that the code below matches, within {JOIN_TIMEOUT}")
    log(msg); console(p, msg)
    env = dict(os.environ, ONEMIND_ETC_DIR=p.etc)

    def show(line: str) -> None:
        log("join: " + line)
        console(p, "ONEMIND-JOIN: " + line)

    rc = run_stream(argv, env, show)
    if rc == 0:
        os.remove(p.join_code)
        msg = "ONEMIND-FIRSTBOOT: joined the hub"
        log(msg); console(p, msg)
        return 0
    msg = ("ONEMIND-FIRSTBOOT: the join did not finish. If the owner did not approve in time, or the code "
           "expired or was used, make a new one on the hub (`onemind fabric ticket` or Add a device), write it to "
           "/data/onemind/secrets/join-code (one line, mode 0600) and run `systemctl start onemind-fabric-join`, "
           "or reboot. Details: journalctl -u onemind-fabric-join")
    log(msg); console(p, msg)
    return 1


# ------------------------------------------------------------------ hub: k3s kubeconfig for the gateway
KUBECONFIG = """apiVersion: v1
kind: Config
clusters: [{{name: k3s, cluster: {{server: "https://127.0.0.1:6443", certificate-authority-data: "{ca}"}}}}]
users: [{{name: onemind-gateway, user: {{token: "{token}"}}}}]
contexts: [{{name: onemind-gateway, context: {{cluster: k3s, user: onemind-gateway}}}}]
current-context: onemind-gateway
"""


KUBECONFIG_POLL_S = 2  # k3s issues the token seconds after the API is up; 10 s polls added up to 10 s


def kubeconfig(p: Paths, timeout: int = 3600) -> int:
    """The gateway's ServiceAccount (manifests/onemind-gateway.yaml) -> its own kubeconfig."""
    dst = os.path.join(p.gateway, "kubeconfig")
    if os.path.exists(dst):
        return 0
    k = ["/usr/local/bin/k3s", "kubectl", "--kubeconfig", "/run/k3s/k3s.yaml", "-n", "onemind-system",
         "get", "secret", "onemind-gateway-token", "-o"]
    end = time.time() + timeout
    while time.time() < end:
        r1 = subprocess.run(k + ["jsonpath={.data.token}"], capture_output=True, text=True)
        r2 = subprocess.run(k + ["jsonpath={.data.ca\\.crt}"], capture_output=True, text=True)
        if r1.returncode == 0 and r1.stdout and r2.stdout:
            import base64
            tok = base64.b64decode(r1.stdout).decode()
            write(dst, KUBECONFIG.format(ca=r2.stdout.strip(), token=tok), 0o600, onemind_ids())
            log("gateway kubeconfig written")
            return 0
        time.sleep(KUBECONFIG_POLL_S)
    log("k3s did not issue the gateway's ServiceAccount token in time")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="onemind-firstboot", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("ONEMIND_FIRSTBOOT_ROOT", "/"))
    sp = ap.add_subparsers(dest="cmd", required=True)
    for c in ("apply", "kubeconfig", "mesh", "join"):
        sp.add_parser(c)
    c = sp.add_parser("configure")
    for k in KEYS:
        c.add_argument("--" + k.replace("_", "-"), required=k == "role")
    a = ap.parse_args(argv)
    p = Paths(a.root)
    if a.cmd in ("apply", "kubeconfig", "mesh", "join"):
        return {"apply": apply, "kubeconfig": kubeconfig, "mesh": mesh, "join": join}[a.cmd](p)
    if load_state(p):
        print("already configured", file=sys.stderr)
        return 2
    try:
        cfg = validate({k: getattr(a, k) or "" for k in KEYS})
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return finish(p, cfg, "wizard")


if __name__ == "__main__":
    sys.exit(main())
