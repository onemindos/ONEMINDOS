# SPDX-License-Identifier: Apache-2.0
"""OneMind first boot (docs/leap/core/IMAGES.md §3): role, per-box secrets, role services.

Runs on every boot as onemind-firstboot.service, with the gateway venv's Python (stdlib + PyYAML).

  onemind-firstboot apply        configure once (role + secrets on /data), then start the role's units
  onemind-firstboot configure    used by the setup wizard: --role R [--name N] [--hub H] [--join-token T]
  onemind-firstboot kubeconfig   hub: wait for k3s, write the gateway's ServiceAccount kubeconfig

Where the settings come from, first match wins:
  1. a cloud-init / NoCloud seed: `onemind:` mapping in the #cloud-config user-data
     (cloud-init's copy on cloud boards, else a filesystem labelled CIDATA/cidata, read-only)
  2. /boot/efi/onemind.conf: key = value lines a user edits after flashing (renamed .applied after use)
  3. none: start the local setup wizard (onemind-setup.service, http://onemind.local:8080/)

The root filesystem is read-only, so all state is under /data/onemind and every unit is started
at runtime (`systemctl start`), never enabled in /etc. The owner token is printed once on the
console (never into the journal) and handed to the wizard through /run (tmpfs).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROLES = ("hub", "worker", "leaf")
ROLE_UNITS = {
    "hub": ["onemind-nats.service", "onemindd.service", "onemind-gateway.service", "onemind-gateway-kube.service"],
    "worker": ["onemindd.service"],
    "leaf": ["onemind-nats.service", "onemindd.service"],
}
KEYS = ("role", "name", "hub", "join_token", "nats_tls")
HOST_RE = re.compile(r"^(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9]{32,128}$")
NAME_RE = re.compile(r"^[^\x00-\x1f\"\\]{1,64}$")
SCHEMA = "onemind.firstboot/v1"


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
        self.state = j("data", "onemind", "firstboot", "state.json")
        self.esp_conf = j("boot", "efi", "onemind.conf")
        self.cloud_userdata = j("var", "lib", "cloud", "instance", "user-data.txt")
        self.seed_mnt = j("run", "onemind", "seed")
        self.run = j("run", "onemind")
        self.console = j("dev", "console")
        self.lib = j("usr", "lib", "onemind")


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


def validate(cfg: dict) -> dict:
    role = cfg.get("role", "").strip().lower()
    if role not in ROLES:
        raise ConfigError(f"role must be one of {', '.join(ROLES)} (got {role!r})")
    out = {"role": role, "name": cfg.get("name", "").strip() or "OneMind"}
    if not NAME_RE.match(out["name"]):
        raise ConfigError("name: 1-64 printable characters, no quotes or backslashes")
    if role in ("worker", "leaf"):
        hub = cfg.get("hub", "").strip()
        hub = re.sub(r"^[a-z]+://", "", hub).split("/", 1)[0]
        if hub.startswith("["):
            hub = hub.split("]", 1)[0] + "]"
        else:
            hub = hub.split(":", 1)[0]
        if not HOST_RE.match(hub):
            raise ConfigError("hub: a host name or address of the hub is required for this role")
        tok = cfg.get("join_token", "").strip()
        if not TOKEN_RE.match(tok):
            raise ConfigError("join_token: the hub's join token (32-128 letters and digits) is required for this role")
        out.update(hub=hub, join_token=tok)
    if cfg.get("nats_tls", "").strip().lower() in ("1", "yes", "true", "on"):
        out["nats_tls"] = True
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
def write(path: str, data: str, mode: int = 0o600, owner: tuple[int, int] | None = None) -> None:
    """Atomic write: a power cut leaves the old file or the new one, never half of one."""
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


def onemind_ids() -> tuple[int, int] | None:
    try:
        pw = pwd.getpwnam("onemind")
        return pw.pw_uid, pw.pw_gid
    except KeyError:
        return None


def token() -> str:
    return secrets.token_hex(32)


# Where the NATS unit finds the TLS files: onemind-nats.service copies them into its own runtime
# directory for the throw-away user, while the key stays 0600 root on /data.
NATS_TLS_CRED = "/run/onemind-nats"


def nats_conf(role: str, pw: dict, cfg: dict, tls: bool = False) -> str:
    """tls=True (cfg "nats_tls", off by default until the mesh branch proves hub + node join, B3):
    the leaf-node port 7422, the one other boxes reach over the LAN, speaks TLS with a cert from the
    box CA, and a leaf trusts only that CA (docs/leap/core/NETWORKING.md; SECURITY.md CORE-SEC-4)."""
    q = lambda s: json.dumps(s)  # NATS config accepts JSON strings
    head = ("# Written by onemind-firstboot. User/password auth; leaf-node TLS "
            + ("on" if tls else "off (cfg nats_tls)") + " (docs/leap/core/IMAGES.md §5).\n")
    if role == "hub":
        users = ", ".join(f"{{user: {q(u)}, password: {q(pw[u])}}}" for u in ("gateway", "onemindd"))
        ltls = (f"tls {{ cert_file: {q(NATS_TLS_CRED + '/nats-server.pem')}, key_file: {q(NATS_TLS_CRED + '/nats-server.key')}, "
                f"timeout: 5 }}, " if tls else "")
        return (head + "listen: 0.0.0.0:4222\nhttp: 127.0.0.1:8222\nmax_payload: 1MB\n"
                f"authorization {{ users = [ {users}, {{user: \"node\", password: {q(pw['node'])}}} ] }}\n"
                f"leafnodes {{ listen: 0.0.0.0:7422, {ltls}authorization {{ user: \"node\", password: {q(pw['node'])} }} }}\n")
    if role == "leaf":
        remote = f"nats-leaf://node:{cfg['join_token']}@{cfg['hub']}:7422"
        rtls = f", tls: {{ ca_file: {q(NATS_TLS_CRED + '/nats-ca.pem')} }}" if tls else ""
        return (head + "listen: 127.0.0.1:4222\nmax_payload: 1MB\n"
                f"authorization {{ users = [ {{user: \"onemindd\", password: {q(pw['onemindd'])}}} ] }}\n"
                f"leafnodes {{ remotes = [ {{ url: {q(remote)}{rtls} }} ] }}\n")
    raise ValueError(role)


def issue_nats_cert(p: Paths, hostname: str) -> None:
    """Hub only: a server cert for the leaf-node port, signed by the box CA (made by make_ca).
    The CA key never leaves /data/onemind/identity; the cert and key land beside nats.conf."""
    d = p.etc
    key, csr, crt = (os.path.join(d, f) for f in ("nats-server.key", "nats-server.csr", "nats-server.pem"))
    ext = os.path.join(d, "nats-server.ext")
    write(ext, f"subjectAltName=DNS:{hostname},DNS:{hostname}.local,DNS:onemind.local\nextendedKeyUsage=serverAuth\n", 0o600)
    run = lambda *a: subprocess.run(a, check=True, capture_output=True)
    run("openssl", "req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
        "-subj", f"/O=OneMind/CN={hostname}", "-keyout", key, "-out", csr)
    run("openssl", "x509", "-req", "-in", csr, "-CA", os.path.join(p.identity, "ca.pem"),
        "-CAkey", os.path.join(p.identity, "ca.key"), "-CAcreateserial", "-days", "825", "-sha256",
        "-extfile", ext, "-out", crt)
    for f in (csr, ext):
        os.remove(f)
    os.chmod(key, 0o600)
    os.chmod(crt, 0o644)
    shutil.copyfile(os.path.join(p.identity, "ca.pem"), os.path.join(d, "nats-ca.pem"))


def make_ca(p: Paths) -> str:
    """Per-box CA under /data/onemind/identity (the path NETWORKING.md §8 uses). Kept if present,
    so a later CA module (net branch) that creates it first owns it."""
    crt = os.path.join(p.identity, "ca.pem")
    if os.path.exists(crt):
        return "kept"
    os.makedirs(p.identity, mode=0o700, exist_ok=True)
    key = os.path.join(p.identity, "ca.key")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                    "-nodes", "-days", "3650", "-sha256", "-subj", "/O=OneMind/CN=OneMind box CA",
                    "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
                    "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                    "-keyout", key, "-out", crt], check=True, capture_output=True)
    os.chmod(key, 0o600)
    os.chmod(crt, 0o644)
    return "created"


def configure(p: Paths, cfg: dict, source: str, make_ca_fn=make_ca) -> str | None:
    """Write role, secrets and service settings. Returns the owner token (hub) or None.
    state.json is written last: until it exists, the next boot configures again from scratch."""
    role = cfg["role"]
    for d, mode in ((p.etc, 0o700), (p.secrets, 0o700)):
        os.makedirs(d, mode=mode, exist_ok=True)
        os.chmod(d, mode)
    node_id = hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:12]
    write(os.path.join(p.etc, "node-id"), node_id + "\n", 0o644)
    pw = {u: token() for u in ("gateway", "onemindd")}
    owner = None
    if role == "hub":
        pw["node"] = token()
        write(os.path.join(p.secrets, "join-token"), pw["node"] + "\n")
        nats_local = "127.0.0.1"
    elif role == "leaf":
        nats_local = "127.0.0.1"
    tls = bool(cfg.get("nats_tls")) and role in ("hub", "leaf")
    if tls and role == "leaf" and not os.path.exists(os.path.join(p.etc, "nats-ca.pem")):
        raise ConfigError("nats_tls on a leaf needs the hub's CA at /data/onemind/etc/nats-ca.pem (join bundle, B3)")
    if tls and role == "hub":
        make_ca_fn(p)                       # idempotent: kept if it exists
        host = socket.gethostname()
        issue_nats_cert(p, host if HOST_RE.match(host) else "onemind")
    if role in ("hub", "leaf"):
        write(os.path.join(p.etc, "nats.conf"), nats_conf(role, pw, cfg, tls))
        nats_url = f"nats://onemindd:{pw['onemindd']}@{nats_local}:4222"
    else:
        nats_url = f"nats://node:{cfg['join_token']}@{cfg['hub']}:4222"
    write(os.path.join(p.etc, "onemindd.env"),
          "# Written by onemind-firstboot (contract §1)\n"
          f"ONEMIND_NATS_URL={nats_url}\nONEMIND_NODE_ROLE={'hub' if role == 'hub' else 'node'}\n"
          f"ONEMIND_NODE_ID={node_id}\nONEMIND_DISK_PATH=/data\n")
    ca = make_ca_fn(p)
    if role == "hub":
        ids = onemind_ids()
        os.makedirs(p.gateway, mode=0o750, exist_ok=True)
        if ids:
            os.chown(p.gateway, *ids)
        owner = token()
        h = hashlib.sha256(owner.encode()).hexdigest()
        write(os.path.join(p.gateway, "tokens.yaml"),
              "# OneMind gateway principals (written by onemind-firstboot; only sha256 of each token).\n"
              f"tokens:\n  \"sha256:{h}\": {{id: owner, kind: person, role: owner}}\n", 0o600, ids)
        write(os.path.join(p.etc, "gateway.env"),
              "# Written by onemind-firstboot (core/README.md \"Environment\")\n"
              f"ONEMIND_TOKENS_FILE={p.gateway}/tokens.yaml\nONEMIND_DATA_DIR={p.gateway}\n"
              f"ONEMIND_DB_URL=sqlite:///{p.gateway}/onemind.db\nONEMIND_AUDIT_PATH={p.gateway}/audit.jsonl\n"
              "ONEMIND_APPS_DIR=/usr/lib/onemind/apps\nONEMIND_APP_SCHEMA=/usr/lib/onemind/sdk/schema/onemind.app.schema.json\n"
              "ONEMIND_SANDBOX_RULES=/usr/lib/onemind/sdk/policy/app-objects.yaml\n"
              "ONEMIND_DASHBOARD_DIST=/usr/lib/onemind/dashboard\nONEMIND_EXECUTOR=kubernetes\n"
              f"ONEMIND_KUBECTL=/usr/lib/onemind/bin/kubectl\nKUBECONFIG={p.gateway}/kubeconfig\n"
              f"ONEMIND_NATS_URL=nats://gateway:{pw['gateway']}@127.0.0.1:4222\n"
              f"ONEMIND_NODE_ID={node_id}\nONEMIND_INSTANCE_NAME={cfg['name']}\n"
              "ONEMIND_HOST=0.0.0.0\nONEMIND_PORT=8080\nONEMIND_GATEWAY_URL=http://onemind.local:8080\n")
    write(os.path.join(p.etc, "role"), role + "\n", 0o644)
    state = {"schema": SCHEMA, "role": role, "name": cfg["name"], "source": source, "node_id": node_id,
             "ca": ca, "configured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if role != "hub":
        state["hub"] = cfg["hub"]
    write(p.state, json.dumps(state, indent=2) + "\n", 0o644)
    return owner


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


def systemctl(*args: str) -> None:
    subprocess.run(["systemctl", *args], check=False)


def start_units(p: Paths, role: str) -> None:
    ids = onemind_ids()
    if role == "hub" and ids and os.path.isdir(p.gateway):
        # uid of "onemind" is fixed in the image (961), but re-own after an update anyway.
        for dirpath, _dirs, files in os.walk(p.gateway):
            for n in [dirpath, *(os.path.join(dirpath, f) for f in files)]:
                os.chown(n, *ids)
    systemctl("start", "--no-block", *ROLE_UNITS[role])


def apply(p: Paths) -> int:
    st = load_state(p)
    if st:
        msg = f"ONEMIND-FIRSTBOOT: already configured role={st['role']} node_id={st.get('node_id', '?')}"
        log(msg); console(p, msg)
        start_units(p, st["role"])
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
    if owner:
        console(p, "ONEMIND-FIRSTBOOT: the owner token below is shown once; only its sha256 is stored.")
        console(p, f"ONEMIND OWNER TOKEN: {owner}")
        os.makedirs(p.run, mode=0o700, exist_ok=True)
        write(os.path.join(p.run, "owner-token"), owner + "\n")  # tmpfs: for the wizard, gone at reboot
        join = _read(os.path.join(p.secrets, "join-token")) or ""
        console(p, f"ONEMIND-FIRSTBOOT: join a worker or leaf with hub=onemind.local join_token={join.strip()}")
    start_units(p, cfg["role"])
    return 0


KUBECONFIG = """apiVersion: v1
kind: Config
clusters: [{{name: k3s, cluster: {{server: "https://127.0.0.1:6443", certificate-authority-data: "{ca}"}}}}]
users: [{{name: onemind-gateway, user: {{token: "{token}"}}}}]
contexts: [{{name: onemind-gateway, context: {{cluster: k3s, user: onemind-gateway}}}}]
current-context: onemind-gateway
"""


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
        time.sleep(10)
    log("k3s did not issue the gateway's ServiceAccount token in time")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="onemind-firstboot", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("ONEMIND_FIRSTBOOT_ROOT", "/"))
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("apply")
    sp.add_parser("kubeconfig")
    c = sp.add_parser("configure")
    for k in KEYS:
        c.add_argument("--" + k.replace("_", "-"), required=k == "role")
    a = ap.parse_args(argv)
    p = Paths(a.root)
    if a.cmd == "apply":
        return apply(p)
    if a.cmd == "kubeconfig":
        return kubeconfig(p)
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
