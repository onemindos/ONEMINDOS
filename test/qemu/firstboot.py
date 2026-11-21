#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, first boot (F0-F10). Criteria: test/qemu/CRITERIA-FIRSTBOOT.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's VM driver.

Input: the battery's fixtures (`make fixtures`: disk.img = slot A v1 + test overlay, bundles.img with
good.raucb = v2). The disk is copied (sparse) into --work so the T-battery fixtures stay untouched;
a NoCloud seed (label CIDATA, `onemind: {role: hub}`) is made there. Runs in the tools container:

  python3 -I firstboot.py --board x86_64-efi --fixtures DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, importlib.util, json, os, platform, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(os.path.dirname(HERE))
_spec = importlib.util.spec_from_file_location("battery", os.path.join(HERE, "run-tests.py"))
battery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(battery)

PY = "/usr/lib/onemind/gateway/venv/bin/python3"
GW = "http://127.0.0.1:8080"
CONFIGURED = r"ONEMIND-FIRSTBOOT: configured role=hub source=nocloud[^\n]*"
ALREADY = r"ONEMIND-FIRSTBOOT: already configured role=hub[^\n]*"
TOKEN = re.compile(r"ONEMIND OWNER TOKEN: ([0-9a-f]{64})")
UNITS = ["onemind-firstboot", "onemind-gateway", "onemind-nats", "onemindd", "onemind-update"]
ARCH = {"x86_64-efi": "amd64", "vm": "amd64", "vm-do": "amd64", "arm64-efi": "arm64"}
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def make_work(fx, work):
    os.makedirs(work, exist_ok=True)
    subprocess.run(["cp", "--sparse=always", os.path.join(fx, "disk.img"), os.path.join(work, "disk.img")], check=True)
    for f in ("bundles.img",):
        dst = os.path.join(work, f)
        if os.path.lexists(dst):
            os.remove(dst)
        os.symlink(os.path.abspath(os.path.join(fx, f)), dst)
    seed = os.path.join(work, "seed.img")
    d = os.path.join(work, "seed")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "meta-data"), "w").write("instance-id: onemind-f1\nlocal-hostname: onemind\n")
    open(os.path.join(d, "user-data"), "w").write("#cloud-config\nonemind:\n  role: hub\n")
    if os.path.exists(seed):
        os.remove(seed)
    subprocess.run(["mkfs.fat", "-n", "CIDATA", "-C", seed, "2048"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["mcopy", "-i", seed, os.path.join(d, "meta-data"), os.path.join(d, "user-data"), "::/"], check=True)


def http_code(vm, url, token=None, timeout=900):
    """Poll until HTTP 200 or the timeout; returns the last code seen."""
    auth = f"-H 'Authorization: Bearer {token}' " if token else ""
    # Fail fast: a gateway in a crash loop (NRestarts, Restart=always) will not answer; stop waiting (failfast.py).
    lim = battery.failfast.RESTART_LIMIT
    _, out = vm.run(f"t0=$SECONDS; while :; do c=$(curl -s -o /dev/null -w '%{{http_code}}' {auth}{url}); "
                    f"[ \"$c\" = 200 ] || [ $((SECONDS - t0)) -ge {timeout} ] && break; "
                    f"n=$(systemctl show -p NRestarts --value {battery.failfast.GATEWAY_UNIT} 2>/dev/null); "
                    f"[ \"${{n:-0}}\" -ge {lim} ] 2>/dev/null && {{ c=crashloop-$n; break; }}; sleep 5; done; echo CODE=$c",
                    timeout + 60)
    m = re.findall(r"CODE=(\S+)", out)
    return m[-1] if m else "none"


def diagnose(vm, why):
    """Best effort: put the journal of the unit that failed (named in `why`, if any) and the gateway's into
    the log (the serial log and stdout) so the cause is visible."""
    units = [battery.failfast.GATEWAY_UNIT]
    m = re.search(r"Failed to start (?:\x1b?\[[0-9;]*m)?(onemind[\w@.-]*)", why)    # systemd colours the name
    unit = m and m.group(1).removesuffix(".service") + ".service"
    if unit and unit not in units:
        units.insert(0, unit)
    vm.mark(f"DIAGNOSE ({why}): journal of {' '.join(units)}")
    vm.failfast = False
    try:
        # The fatal sign can come before the console has logged in; a command sent then is lost.
        vm.send("")
        vm.expect(r"root@onemind:~# ", 120)
    except (TimeoutError, RuntimeError, OSError) as e:
        vm.mark(f"DIAGNOSE: no shell prompt ({e}); trying anyway")
    for unit in units:
        try:
            _, out = vm.run(battery.failfast.dump_cmd(unit), 90)
            print(out[-6000:], flush=True)
        except (TimeoutError, RuntimeError, OSError) as e:
            vm.mark(f"DIAGNOSE failed: {e}")


def nodes(vm, token, want_id, timeout=600):
    """Poll /v1/nodes until want_id is listed; returns [(node_id, role, status)] of the last answer."""
    script = (f"t0=$SECONDS; while :; do curl -s -H 'Authorization: Bearer {token}' {GW}/v1/nodes > /run/f-nodes.json; "
              f"grep -q '\"{want_id}\"' /run/f-nodes.json || [ $((SECONDS - t0)) -lt {timeout} ] || break; "
              f"grep -q '\"{want_id}\"' /run/f-nodes.json && break; sleep 5; done; "
              f"{PY} -I -c 'import json; [print(\"NODE\", n[\"node_id\"], n[\"role\"], n[\"status\"]) "
              f"for n in json.load(open(\"/run/f-nodes.json\"))]' || echo NODES-UNREADABLE")
    _, out = vm.run(script, timeout + 60)
    return re.findall(r"^NODE (\S+) (\S+) (\S+)\s*$", out, re.M)


def ident(vm):
    _, out = vm.run("echo ID=$(cat /data/onemind/etc/node-id); "
                    "echo TOK=$(sha256sum /data/onemind/gateway/tokens.yaml | cut -c1-64); "
                    "echo STATE=$(sha256sum /data/onemind/firstboot/state.json | cut -c1-64)")
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or [""])[-1]
    return {"node_id": get("ID"), "tokens_sha256": get("TOK"), "state_sha256": get("STATE")}


def f0(vm, board):
    import yaml
    lock = yaml.safe_load(open(os.path.join(SRC, "os", "versions.lock.yaml")))
    want = lock["onemind_layer"]["nats_server"][ARCH[board]]["binary"]
    _, out = vm.run("onemindd -version; onemind version; nats-server --version; "
                    "echo NATSSHA=$(sha256sum /usr/bin/nats-server | cut -c1-64); "
                    f"{PY} -I -c 'import onemind_core; print(\"GATEWAY-IMPORT ok\")'; "
                    "test -f /usr/lib/onemind/dashboard/index.html && echo DASH ok; test -d /usr/lib/onemind/tuf && echo TUF ok; "
                    "for u in " + " ".join(UNITS) + "; do echo UNIT $u $(systemctl is-enabled $u.service 2>&1 | head -1); done")
    c = {
        "onemindd": re.search(r"^onemindd \S+", out, re.M) is not None,
        "onemind_cli": re.search(r"^onemind \S+", out, re.M) is not None,
        "nats_server_runs": re.search(r"nats-server: v2\.15\.2", out) is not None,
        "nats_sha256_pinned": f"NATSSHA={want}" in out,
        "gateway_imports": "GATEWAY-IMPORT ok" in out,
        "dashboard": "DASH ok" in out,
        "tuf_dir": "TUF ok" in out,
    }
    units = dict(re.findall(r"^UNIT (onemind[\w-]*) ([\w-]+)\s*$", out, re.M))
    c["units_exist"] = all(units.get(u) not in (None, "", "not-found") for u in UNITS) and len(units) == len(UNITS)
    c["only_firstboot_enabled"] = units.get("onemind-firstboot") == "enabled" and all(
        units.get(u) != "enabled" for u in UNITS if u != "onemind-firstboot")
    record("F0", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" units={units}")


PRIV_POD = ("apiVersion: v1\\nkind: Pod\\nmetadata: {name: f5-priv}\\nspec:\\n  containers:\\n"
            "  - {name: c, image: registry.invalid/f5:1, securityContext: {privileged: true}}\\n")
PLAIN_POD = ("apiVersion: v1\\nkind: Pod\\nmetadata: {name: f5-plain}\\nspec:\\n  containers:\\n"
             "  - {name: c, image: registry.invalid/f5:1}\\n")


def f5(vm):
    """H-01: the booted k3s enforces the cluster-wide Pod Security default (CRITERIA-FIRSTBOOT.md section 4)."""
    k = "k3s kubectl -n default apply --dry-run=server -f -"
    # The pod admission chain looks up the namespace's default ServiceAccount first; on a fast boot (CI) the
    # controller has not created it yet, which would refuse both pods for that reason and not for policy.
    _, out = vm.run("for i in $(seq 1 90); do k3s kubectl -n default get serviceaccount default >/dev/null 2>&1 && break; sleep 2; done; "
                    f"printf '{PRIV_POD}' | {k} 2>&1; echo PRIV_RC=$?; "
                    f"printf '{PLAIN_POD}' | {k} 2>&1; echo PLAIN_RC=$?; "
                    "echo UNIT=$(systemctl cat k3s.service | grep -c 'admission-control-config-file=/etc/rancher/k3s/psa.yaml')", 300)
    priv_rc = (re.findall(r"PRIV_RC=(\d+)", out) or ["?"])[-1]
    plain_rc = (re.findall(r"PLAIN_RC=(\d+)", out) or ["?"])[-1]
    unit = (re.findall(r"UNIT=(\d+)", out) or ["0"])[-1]
    refused = "violates PodSecurity" in out and "baseline" in out
    record("F5", priv_rc != "0" and priv_rc != "?" and refused and plain_rc == "0" and unit != "0",
           f"privileged_rc={priv_rc} violates_PodSecurity_baseline={refused} plain_rc={plain_rc} unit_has_psa_flag={unit != '0'} "
           f"out={out.strip()[-300:]!r}")


def f6(vm):
    """H-12: Secrets are encrypted at rest in the k3s datastore (CRITERIA-FIRSTBOOT.md section 4)."""
    db = "/data/k3s/server/db/state.db"
    _, out = vm.run("k3s secrets-encrypt status --data-dir /data/k3s 2>&1 | head -12; echo SEC-STATUS-E''ND; "
                    "v=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n'); "
                    "k3s kubectl -n default create secret generic f6-probe --from-literal=v=$v >/dev/null 2>&1; echo CREATE_RC=$?; "
                    "echo READBACK=$([ \"$(k3s kubectl -n default get secret f6-probe -o jsonpath='{.data.v}' | base64 -d)\" = \"$v\" ] && echo yes || echo no); "
                    f"sync; echo DBSIZE=$(stat -c %s {db} 2>/dev/null || echo 0); "
                    f"echo PLAIN=$(cat {db} {db}-wal 2>/dev/null | grep -a -c \"$v\"); "
                    f"echo ENVELOPE=$(cat {db} {db}-wal 2>/dev/null | grep -a -c 'k8s:enc:aescbc:v1:'); "
                    "k3s kubectl -n default delete secret f6-probe >/dev/null 2>&1; echo DELETE_RC=$?", 300)
    g = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or [""])[-1]
    status = out.split("SEC-STATUS-END")[0]
    enabled = re.search(r"Encryption Status:\s*Enabled", status) is not None
    record("F6", enabled and g("CREATE_RC") == "0" and g("READBACK") == "yes" and int(g("DBSIZE") or 0) > 0
           and g("PLAIN") == "0" and int(g("ENVELOPE") or 0) >= 1 and g("DELETE_RC") == "0",
           f"status_enabled={enabled} create_rc={g('CREATE_RC')} readback={g('READBACK')} db_bytes={g('DBSIZE')} "
           f"plaintext_hits={g('PLAIN')} envelope_hits={g('ENVELOPE')} delete_rc={g('DELETE_RC')} status={status.strip()[:160]!r}")


HS = "headscale -c /data/onemind/etc/headscale/config.yaml"
MESH_RE = re.compile(r"^MESHIP=(100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.\d{1,3}\.\d{1,3})\s*$", re.M)  # 100.64.0.0/10


def mesh_ip(vm, timeout=600):
    """Poll `tailscale ip -4` until onemind-mesh-setup has put the hub on its mesh; '' if never."""
    _, out = vm.run(f"t0=$SECONDS; while :; do a=$(tailscale ip -4 2>/dev/null | head -1); "
                    f"case $a in 100.*) break;; esac; [ $((SECONDS - t0)) -ge {timeout} ] && break; sleep 5; done; "
                    "echo MESHIP=$a", timeout + 60)
    m = MESH_RE.search(out)
    return m.group(1) if m else ""


def f7(vm):
    """The hub is on its own mesh, serves HTTPS with the box CA, and Headscale refuses a made-up key (section 5)."""
    ip = mesh_ip(vm)
    if not ip:
        _, out = vm.run("systemctl status --no-pager -n 20 onemind-mesh-setup onemind-headscale tailscaled 2>&1 | tail -40", 60)
        print(out[-3000:], flush=True)
    url = "https://onemind.local:8443/healthz"
    _, out = vm.run(f"t0=$SECONDS; while :; do c=$(curl -s -o /dev/null -w '%{{http_code}}' --cacert /data/onemind/identity/ca.pem "
                    f"--resolve onemind.local:8443:127.0.0.1 {url}); [ \"$c\" = 200 ] || [ $((SECONDS - t0)) -ge 300 ] && break; "
                    "sleep 5; done; echo HTTPS=$c", 400)
    https = (re.findall(r"HTTPS=(\S+)", out) or ["none"])[-1]
    # A second Tailscale client, userspace networking (it never touches tailscale0 or the firewall), state in /run,
    # trusting only the box CA, tries to enroll with a key of the right shape that Headscale never issued.
    count = (f"{HS} nodes list -o json 2>/dev/null | {PY} -I -c 'import json,sys; d=json.load(sys.stdin) or []; "
             "print(len(d), sum(1 for n in d if \"f7-intruder\" in json.dumps(n)))'")
    _, out = vm.run(
        f"echo BEFORE=$({count}); rm -rf /run/f7; mkdir -m 0700 /run/f7; "
        "SSL_CERT_FILE=/data/onemind/identity/ca.pem TS_NO_LOGS_NO_SUPPORT=true /usr/sbin/tailscaled --no-logs-no-support "
        "--tun=userspace-networking --statedir=/run/f7 --socket=/run/f7/ts.sock --port=0 >/run/f7/log 2>&1 & "
        "for i in $(seq 1 30); do [ -S /run/f7/ts.sock ] && break; sleep 1; done; "
        "k=hskey-auth-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \\n'); "
        "timeout 60 tailscale --socket=/run/f7/ts.sock up --login-server=https://control.onemind.internal:8444 "
        "--auth-key=$k --hostname=f7-intruder --accept-dns=false --timeout=30s >/run/f7/up 2>&1; echo UP_RC=$?; "
        "tail -c 300 /run/f7/up | tr '\\n' ' '; echo; "
        f"pkill -f 'tailscaled.*--socket=/run/f7/ts.sock'; sleep 2; rm -rf /run/f7; echo AFTER=$({count})", 180)
    g = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    before, after, up_rc = g("BEFORE").split(), g("AFTER").split(), g("UP_RC")
    refused = up_rc not in ("", "0")
    same = len(before) == 2 and before[0] == (after[:1] or [None])[0] and after[1:] == ["0"]
    record("F7", bool(ip) and https == "200" and refused and same,
           f"mesh_ip={ip or 'none'} https_healthz={https} madeup_key_up_rc={up_rc} nodes_before={before} "
           f"nodes_after={after} out={out.strip()[-300:]!r}")
    return ip


# F8's client, run in the guest with the gateway venv's Python (stdlib + cryptography + onemind_core).
# NATS speaks a line protocol: INFO from the server (with a nonce), CONNECT from the client; a leaf
# connection reads the plain-text INFO, then upgrades to TLS (nats-server's default for leaf nodes).
F8_PY = r'''
import base64, datetime, json, os, socket, ssl, sys
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from onemind_core import natsconf
from onemind_core.ca import BoxCA
IP, D, CA = sys.argv[1], "/run/f8", "/data/onemind/identity/ca.pem"

def client(seed=None):
    s = socket.create_connection(("127.0.0.1", 4222), 5); f = s.makefile("rb")
    info = json.loads(f.readline().split(b" ", 1)[1])
    c = {"verbose": False, "pedantic": False, "protocol": 1, "name": "f8"}
    if seed:
        pub, sign = natsconf.load_seed(Path(seed))
        # The same signature the gateway sends (core/onemind_core/bus.py, through nats-py's signature_cb).
        c.update(nkey=pub, sig=base64.b64encode(sign(info["nonce"].encode())).decode())
    s.sendall(b"CONNECT " + json.dumps(c).encode() + b"\r\nPING\r\n")
    for _ in range(5):
        line = f.readline().decode().strip()
        if line.startswith(("PONG", "-ERR")):
            break
    s.close()
    return line

def pem(obj, key=False):
    if key:
        return obj.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return obj.public_bytes(serialization.Encoding.PEM)

def save(name, data):
    p = os.path.join(D, name); open(p, "wb").write(data); return p

def foreign():
    """A CA that is not the box CA, and a client certificate from it."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cak, k = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    name = lambda n: x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, n)])
    ca = (x509.CertificateBuilder().subject_name(name("f8 other CA")).issuer_name(name("f8 other CA"))
          .public_key(cak.public_key()).serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(cak, hashes.SHA256()))
    crt = (x509.CertificateBuilder().subject_name(name("node-f8other")).issuer_name(ca.subject)
           .public_key(k.public_key()).serial_number(2).not_valid_before(now).not_valid_after(now + datetime.timedelta(hours=1))
           .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False).sign(cak, hashes.SHA256()))
    return save("other.crt", pem(crt) + pem(ca)), save("other.key", pem(k, True))

def boxca_client():
    """A client certificate the box CA signs, as for an approved node (the control: this one must pass TLS)."""
    box = next(l.split("=", 1)[1].strip() for l in open("/data/onemind/etc/gateway.env") if l.startswith("ONEMIND_NET_BOX_NAME="))
    k = ec.generate_private_key(ec.SECP256R1())
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "node-f8probe")])).sign(k, hashes.SHA256())
    crt = BoxCA(Path("/data/onemind/gateway/tls"), box).sign_node_csr(pem(csr), "f8probe")
    return save("box.crt", pem(crt)), save("box.key", pem(k, True))

def leaf(cert=None):
    """'refused' (TLS alert, handshake error or close within 3 s) or 'accepted' (TLS up, server waits for CONNECT)."""
    s = socket.create_connection((IP, 7422), 5)
    info = s.makefile("rb").readline()
    if not info.startswith(b"INFO"):
        return "no-info"
    ctx = ssl.create_default_context(cafile=CA); ctx.check_hostname = False
    if cert:
        ctx.load_cert_chain(*cert)
    try:
        t = ctx.wrap_socket(s); t.settimeout(3)
        return "accepted-data" if t.recv(1) else "refused"
    except socket.timeout:
        return "accepted"
    except (ssl.SSLError, OSError):
        return "refused"
    finally:
        s.close()

os.makedirs(D, mode=0o700, exist_ok=True)
try:
    print("NOKEY=" + client())
    print("WITHKEY=" + client("/data/onemind/nats/keys/onemindd.nk"))
    print("LEAF_NOCERT=" + leaf())
    print("LEAF_FOREIGN=" + leaf(foreign()))
    print("LEAF_BOXCA=" + leaf(boxca_client()))
finally:
    for f in os.listdir(D):
        os.remove(os.path.join(D, f))
    os.rmdir(D)
'''


def send_file(vm, path, text, chunk=800):
    """Put a file into the guest over the serial shell: base64 in short lines, then decoded."""
    import base64
    b64 = base64.b64encode(text.encode()).decode()
    vm.run(f"rm -f {path}.b64")
    for i in range(0, len(b64), chunk):
        vm.run(f"printf %s '{b64[i:i + chunk]}' >> {path}.b64")
    vm.run(f"base64 -d {path}.b64 > {path} && rm -f {path}.b64")


def f8(vm, ip):
    """Hub NATS refuses clients without a key and leaf connections without a box-CA certificate (section 5)."""
    send_file(vm, "/run/f8.py", F8_PY)
    _, out = vm.run(f"{PY} -I /run/f8.py {ip or '0.0.0.0'} 2>&1 | tail -20; rm -f /run/f8.py; "
                    "echo PW=$(grep -c password /data/onemind/etc/nats.conf)", 120)
    g = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    c = {"nokey_refused": "Authorization Violation" in g("NOKEY"), "onemindd_key_pong": g("WITHKEY") == "PONG",
         "leaf_nocert_refused": g("LEAF_NOCERT") == "refused", "leaf_foreign_refused": g("LEAF_FOREIGN") == "refused",
         "leaf_boxca_accepted": g("LEAF_BOXCA").startswith("accepted"), "no_password": g("PW") == "0"}
    record("F8", bool(ip) and all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" mesh_ip={ip or 'none'} out={out.strip()[-400:]!r}")


def f9(vm):
    """One box CA: identity/ca.pem is the gateway's CA, no CA key outside the gateway's tls dir (section 5)."""
    t = "/data/onemind/gateway/tls"
    _, out = vm.run("echo ID=$(sha256sum /data/onemind/identity/ca.pem | cut -c1-64); "
                    f"echo GW=$(sha256sum {t}/ca.crt | cut -c1-64); "
                    "echo KEY=$(test -e /data/onemind/identity/ca.key && echo present || echo absent); "
                    f"openssl verify -CAfile /data/onemind/identity/ca.pem {t}/https.crt {t}/control.crt {t}/nats.crt 2>&1 | "
                    "sed 's/^/VERIFY /'")
    g = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or [""])[-1]
    oks = re.findall(r"^VERIFY \S+\.crt: OK\s*$", out, re.M)
    record("F9", len(g("ID")) == 64 and g("ID") == g("GW") and g("KEY") == "absent" and len(oks) == 3,
           f"identity_sha={g('ID')[:16]} gateway_ca_sha={g('GW')[:16]} identity_ca_key={g('KEY')} verified={len(oks)}/3 "
           f"out={out.strip()[-300:]!r}")


# F10's probe, run in the guest (section 6): connect to :443 every 100 ms; the first answer from the gateway itself ends it.
F10_PY = r'''
import json, socket, ssl, sys, time
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
t0, ev, ok_once, bad = time.time(), [], False, []
while time.time() - t0 < 180:
    try:
        raw = socket.create_connection(("127.0.0.1", 443), 3)
        with ctx.wrap_socket(raw) as s:
            s.sendall(b"GET /healthz HTTP/1.1\r\nHost: onemind.local\r\nConnection: close\r\n\r\n")
            buf = b""
            while True:
                c = s.recv(4096)
                if not c: break
                buf += c
        ok_once = True
        head = buf.split(b"\r\n\r\n")[0].decode("latin-1")
        code = head.split(" ")[1] if head.startswith("HTTP/") else "?"
        marker = "x-onemind-starting: 1" in head.lower()
        ev.append("page" if marker else "gw")
        if marker and code != "503": bad.append("marker-status-" + code)
        if not marker and code == "200":
            print("RESULT " + json.dumps({"seconds": round(time.time() - t0, 1), "page_seen": "page" in ev, "first": ev[0],
                                          "bad": bad, "n": len(ev)})); sys.exit(0)
    except (ConnectionRefusedError, ConnectionResetError, socket.timeout, ssl.SSLError, OSError) as e:
        if ok_once: bad.append(type(e).__name__)
    time.sleep(0.1)
print("RESULT " + json.dumps({"seconds": None, "page_seen": "page" in ev, "first": ev[0] if ev else None, "bad": bad, "n": len(ev)}))
'''


def f10(vm, results_dir):
    """The starting page holds :443 while the gateway starts, then hands over with no refused connection (section 6)."""
    unit = "/usr/lib/systemd/system/onemind-gateway.service"
    _, out = vm.run(f"grep -E '^(After|Wants|Requires)=' {unit}; echo ---; "
                    "systemctl stop onemind-gateway.service onemind-starting.service; "
                    "cat > /run/f10.py <<'PYEOF'\n" + F10_PY + "\nPYEOF\n"
                    "systemctl start --no-block onemind-starting.service; sleep 1; systemctl start --no-block onemind-gateway.service; "
                    f"{PY} -I /run/f10.py; rm -f /run/f10.py", 300)
    order = out.split("---")[0]
    m = re.findall(r"^RESULT (\{.*\})\s*$", out, re.M)
    r = json.loads(m[-1]) if m else {}
    sec = r.get("seconds")
    budget = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "perf", "budget.json")))
    limit = budget.get("time_to_dashboard_s")
    ok = (sec is not None and not r.get("bad") and "network-online" not in order and limit is not None and sec <= limit)
    if ok and results_dir:
        json.dump({"kind": "dashboard", "time_to_dashboard_s": sec}, open(os.path.join(results_dir, "perf-dashboard.json"), "w"))
    record("F10", ok, f"time_to_dashboard_s={sec} budget={limit} page_seen={r.get('page_seen')} first={r.get('first')} "
                      f"probes={r.get('n')} bad={r.get('bad')} gateway_order={order.strip()!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(battery.BOARDS))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--upto", default="F4", choices=["F2", "F3", "F4"])
    ap.add_argument("--results")
    a = ap.parse_args()
    make_work(a.fixtures, a.work)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(),
           "host_machine": platform.machine(), "upto": a.upto}
    print(f"ENV {json.dumps(env)}", flush=True)
    rc = 1
    vm.failfast = True          # stop at the first fatal console sign instead of waiting out the timeouts
    try:
        vm.mark("F1 first boot as hub (NoCloud seed)"); vm.start()
        cfg = vm.expect(CONFIGURED, 900).group(0)
        time.sleep(3)
        toks = TOKEN.findall(vm.since(0))
        vm.pos = 0              # on a fast host the gate line comes before CONFIGURED; this boot's buffer only
        g = vm.wait_gate()
        vm.shell_ready()
        f0(vm, a.board)
        token = toks[0] if toks else ""
        ids = ident(vm)
        hz = http_code(vm, f"{GW}/healthz", timeout=900)
        if hz != "200":
            diagnose(vm, f"healthz={hz}")
        listed = nodes(vm, token, ids["node_id"]) if token and hz == "200" else []
        _, out = vm.run(f"curl -s -o /dev/null -w 'NOAUTH=%{{http_code}}\\n' {GW}/v1/nodes")
        noauth = "NOAUTH=401" in out
        me = [n for n in listed if n[0] == ids["node_id"]]
        record("F1", len(toks) == 1 and hz == "200" and bool(me) and me[0][1] == "hub" and noauth
               and g == ("committed-boot", "A", "1"),
               f"config='{cfg[:90]}' tokens_printed={len(toks)} healthz={hz} node_id={ids['node_id']} "
               f"listed={listed} unauth_401={noauth} gate={g} t={time.time() - t0:.0f}s")

        _, out = vm.run(f"echo BODY=$(curl -s {GW}/ | sha256sum | cut -c1-64) CODE=$(curl -s -o /dev/null -w '%{{http_code}}' {GW}/); "
                        "echo FILE=$(sha256sum /usr/lib/onemind/dashboard/index.html | cut -c1-64)")
        body = (re.findall(r"BODY=(\w+) CODE=(\d+)", out) or [("", "")])[-1]
        fil = (re.findall(r"^FILE=(\w+)", out, re.M) or [""])[-1]
        record("F2", body[1] == "200" and body[0] == fil and len(fil) == 64,
               f"code={body[1]} body_sha={body[0][:16]} index_sha={fil[:16]}")

        vm.mark("F5 PSA admission (H-01)"); f5(vm)
        vm.mark("F6 secrets encrypted at rest (H-12)"); f6(vm)
        vm.mark("F7 the hub on its own mesh, HTTPS with the box CA (IMG-MESH-01)"); ip = f7(vm)
        vm.mark("F8 hub NATS: own keys only, leaf port needs the box CA"); f8(vm, ip)
        vm.mark("F9 one box CA"); f9(vm)
        vm.mark("F10 starting page, then the gateway, never a refused connection"); f10(vm, (os.path.dirname(a.results) or ".") if a.results else None)

        if a.upto in ("F3", "F4"):
            vm.mark("F3 reboot keeps state")
            seg = vm.here(); vm.send("systemctl reboot")
            al = vm.expect(ALREADY, 900).group(0)
            g3 = vm.wait_gate(); vm.shell_ready()
            new_toks = TOKEN.findall(vm.since(seg))
            ids3 = ident(vm)
            hz3 = http_code(vm, f"{GW}/healthz", timeout=900)
            if hz3 != "200":
                diagnose(vm, f"healthz={hz3} after reboot")
            listed3 = nodes(vm, token, ids["node_id"])
            same = [n for n in listed3 if n[0] == ids["node_id"]]
            record("F3", not new_toks and ids3 == ids and hz3 == "200" and bool(same) and bool(token),
                   f"'{al[:70]}' new_tokens={len(new_toks)} same_ids={ids3 == ids} healthz={hz3} listed={listed3} gate={g3}")

        if a.upto == "F4":
            vm.mark("F4 A/B update keeps /data")
            _, out = vm.run("head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n' > /data/onemind/f4-marker; sync; "
                            "echo MARK=$(sha256sum /data/onemind/f4-marker | cut -c1-64)")
            mark = (re.findall(r"^MARK=(\w+)", out, re.M) or [""])[-1]
            rc_i, seg = battery.update_and_reboot(vm, "good.raucb")
            g4 = vm.wait_gate(); s = vm.since(seg)
            vm.shell_ready()
            _, out = vm.run("echo MARK=$(sha256sum /data/onemind/f4-marker | cut -c1-64); grep ONEMIND_VERSION /usr/lib/os-release")
            mark2 = (re.findall(r"^MARK=(\w+)", out, re.M) or [""])[-1]
            ver2 = re.search(r'^ONEMIND_VERSION="?2"?\s*$', out, re.M) is not None
            ids4 = ident(vm)
            hz4 = http_code(vm, f"{GW}/healthz", timeout=900)
            if hz4 != "200":
                diagnose(vm, f"healthz={hz4} after update")
            listed4 = nodes(vm, token, ids["node_id"])
            same = [n for n in listed4 if n[0] == ids["node_id"]]
            already = re.search(ALREADY, s) is not None
            record("F4", rc_i == 0 and g4 == ("mark-good", "B", "2") and mark == mark2 and len(mark) == 64 and ver2
                   and already and not TOKEN.search(s) and ids4 == ids and hz4 == "200" and bool(same),
                   f"install_rc={rc_i} gate={g4} marker_kept={mark == mark2} version2={ver2} already_configured={already} "
                   f"new_token={bool(TOKEN.search(s))} same_ids={ids4 == ids} healthz={hz4} listed={listed4}")
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
        if "fatal sign" in str(e) and "Kernel panic" not in str(e) and vm.proc and vm.proc.poll() is None:
            diagnose(vm, f"fatal console sign: {e}")
    if rc == 0:
        vm.poweroff()
    elif vm.proc and vm.proc.poll() is None:
        vm.kill()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-FIRSTBOOT.md",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    return 0 if RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
