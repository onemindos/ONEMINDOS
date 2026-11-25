#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, first boot (F0-F15). Criteria: test/qemu/CRITERIA-FIRSTBOOT.md
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
    nats = lock["onemind_layer"]["nats_server"]
    want = nats[ARCH[board]]["binary"]
    # The version comes from the same lock the image build reads (fetch-onemind.sh), so a pin bump cannot
    # leave a stale hard-coded string here.
    nats_ver = re.escape(str(nats["version"]))
    _, out = vm.run("onemindd -version; onemind version; nats-server --version; "
                    "echo NATSSHA=$(sha256sum /usr/bin/nats-server | cut -c1-64); "
                    f"{PY} -I -c 'import onemind_core; print(\"GATEWAY-IMPORT ok\")'; "
                    "test -f /usr/lib/onemind/dashboard/index.html && echo DASH ok; test -d /usr/lib/onemind/tuf && echo TUF ok; "
                    "for u in " + " ".join(UNITS) + "; do echo UNIT $u $(systemctl is-enabled $u.service 2>&1 | head -1); done")
    c = {
        "onemindd": re.search(r"^onemindd \S+", out, re.M) is not None,
        "onemind_cli": re.search(r"^onemind \S+", out, re.M) is not None,
        "nats_server_runs": re.search(rf"nats-server: {nats_ver}\s*$", out, re.M) is not None,
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


def f10(vm, token):
    """The rescue console answers with k3s stopped: 401 without the owner token, 200 with it (section 6)."""
    base = ("curl -s -o /dev/null -w '%{http_code}' --cacert /data/onemind/identity/ca.pem "
            "--resolve onemind.local:7443:127.0.0.1")
    url = "https://onemind.local:7443"
    auth = f"-H 'Authorization: Bearer {token}'"
    _, out = vm.run("echo ENABLED=$(systemctl is-enabled onemind-rescue); echo ACTIVE=$(systemctl is-active onemind-rescue); "
                    "systemctl stop k3s; echo K3S=$(systemctl is-active k3s); "
                    # the unit may still be starting after first boot: give it a minute to answer
                    f"for i in $(seq 1 30); do c=$({base} {url}/); [ \"$c\" = 401 ] && break; sleep 2; done; echo NOAUTH=$c; "
                    f"echo WITH=$({base} {auth} {url}/); "
                    f"echo JSON=$({base} {auth} {url}/status.json); "
                    f"{base.replace('-o /dev/null', '-o /run/f10.json')} {auth} {url}/status.json >/dev/null; "
                    f"echo JSONOK=$({PY} -I -c 'import json; json.load(open(\"/run/f10.json\")); print(\"yes\")' 2>/dev/null || echo no); "
                    "rm -f /run/f10.json; systemctl start k3s; echo AFTER=$(systemctl is-active onemind-rescue)", 400)
    g = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or [""])[-1]
    # The image's root is read-only: first boot starts the unit at runtime on every boot, never enables it in
    # /etc (F0 holds only onemind-firstboot enabled). So "not enabled, yet active" is the expected state here;
    # deploy/install.sh is the path that enables it.
    c = {"runtime_started": g("ENABLED") not in ("", "enabled", "not-found", "masked") and g("ACTIVE") == "active",
         "active": g("ACTIVE") == "active", "k3s_stopped": g("K3S") != "active",
         "noauth_401": g("NOAUTH") == "401", "token_200": g("WITH") == "200", "json_200": g("JSON") == "200",
         "json_valid": g("JSONOK") == "yes", "still_active": g("AFTER") == "active"}
    record("F10", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" out={out.strip()[-200:]!r}")


# F11's probe, run in the guest (section 7): connect to :443 every 100 ms; the first answer from the gateway itself ends it.
F11_PY = r'''
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


def f11(vm, results_dir):
    """The starting page holds :443 while the gateway starts, then hands over with no refused connection (section 7)."""
    unit = "/usr/lib/systemd/system/onemind-gateway.service"
    _, out = vm.run(f"grep -E '^(After|Wants|Requires)=' {unit}; echo ---; "
                    "systemctl stop onemind-gateway.service onemind-starting.service; "
                    "cat > /run/f10.py <<'PYEOF'\n" + F11_PY + "\nPYEOF\n"
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
    record("F11", ok, f"time_to_dashboard_s={sec} budget={limit} page_seen={r.get('page_seen')} first={r.get('first')} "
                      f"probes={r.get('n')} bad={r.get('bad')} gateway_order={order.strip()!r}")



# F12's reader, run in the guest (section 8): the gateway's GET /v1/status (and, with the helper gone, GET /v1/os/updates).
F12_PY = r"""
import json, sys, time, urllib.error, urllib.request
phase, token, wait = sys.argv[1], sys.argv[2], float(sys.argv[3])
def get(path):
    req = urllib.request.Request("http://127.0.0.1:8080" + path, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, ValueError):
        return None, None
t0 = time.time()
while True:
    code, body = get("/v1/status")
    host = (body or {}).get("host") or {}
    if phase == "down" or (code == 200 and host.get("helper") == "reachable") or time.time() - t0 >= wait:
        break
    time.sleep(3)
out = {"code": code, "helper": host.get("helper"), "state": host.get("state"), "hostname": host.get("hostname"),
       "summary": host.get("summary"), "seconds": round(time.time() - t0, 1)}
if phase == "down":
    c2, upd = get("/v1/os/updates")
    out.update({"updates_code": c2, "install": (upd or {}).get("install")})
print("RESULT " + phase + " " + json.dumps(out))
"""


def f12(vm, token):
    """The gateway reaches the host helper over /run/onemind/host.sock; without it, it says missing and the
    install is refused with a plain sentence; started again, it is reachable (section 8)."""
    read = lambda phase, wait: f"{PY} -I /run/f12.py {phase} '{token}' {wait}; "
    _, out = vm.run("cat > /run/f12.py <<'PYEOF'\n" + F12_PY + "\nPYEOF\n"
                    "echo BOX=$(hostname); " + read("up", 120) +
                    "systemctl stop onemind-host.service onemind-host.socket; rm -f /run/onemind/host.sock; "
                    "echo SOCK=$(test -e /run/onemind/host.sock && echo present || echo gone); " + read("down", 0) +
                    "systemctl start onemind-host.socket; " + read("again", 60) + "rm -f /run/f12.py", 400)
    box = (re.findall(r"^BOX=(\S+)\s*$", out, re.M) or [""])[-1]
    res = {m[0]: json.loads(m[1]) for m in re.findall(r"^RESULT (up|down|again) (\{.*\})\s*$", out, re.M)}
    up, down, again = res.get("up", {}), res.get("down", {}), res.get("again", {})
    inst = down.get("install") or {}
    msg = inst.get("message") if isinstance(inst.get("message"), str) else ""
    summary = down.get("summary") if isinstance(down.get("summary"), str) else ""
    c = {"up_reachable": up.get("code") == 200 and up.get("helper") == "reachable" and up.get("state") == "ok",
         "hostname_matches": bool(box) and up.get("hostname") == box,
         "socket_gone": "SOCK=gone" in out,
         "down_missing": down.get("code") == 200 and down.get("helper") == "missing" and down.get("state") != "ok"
         and down.get("hostname") is None and summary.startswith("host helper: missing") and "/run/" not in summary,
         "install_refused": down.get("updates_code") == 200 and inst.get("available") is False
         and inst.get("reason") == "engine_unreachable" and bool(msg)
         and not any(x in msg for x in ("Traceback", "Errno", "/run/")),
         "again_reachable": again.get("code") == 200 and again.get("helper") == "reachable"}
    record("F12", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" box={box!r} up={up} down_summary={summary[:80]!r} engine_unreachable={inst.get('reason')}")

def f13(vm):
    """Step 2 PRs 4 and 7: the disk and admin tools run on the booted image (CRITERIA-FIRSTBOOT.md section 9; its smartd-masked clause is replaced by F15, section 11)."""
    _, out = vm.run(
        'D=$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" 2>/dev/null | head -1); '
        '[ -n "$D" ] || D=$(lsblk -dno NAME,TYPE | awk \'$2=="disk"{print $1; exit}\'); D=/dev/$D; echo DISK=$D; '
        'smartctl --version >/dev/null 2>&1; echo SMARTV_RC=$?; smartctl --scan >/dev/null 2>&1; echo SCAN_RC=$?; '
        'smartctl -H $D 2>&1 | head -3; echo SMARTH_BANNER=$(smartctl -H $D 2>&1 | grep -c "^smartctl"); '
        'sgdisk -p $D >/tmp/f13.sg 2>&1; echo SGDISK_RC=$?; echo SGDISK_TABLE=$(grep -c "^Number" /tmp/f13.sg); '
        'btrfs --version >/dev/null 2>&1; echo BTRFS_RC=$?; '
        'for t in jq htop rsync nano less ethtool dmidecode lspci lsusb; do $t --version >/dev/null 2>&1; echo TOOL $t $?; done; '
        'ping -V >/dev/null 2>&1; echo TOOL ping $?; '
        'test -r /usr/share/bash-completion/bash_completion; echo BASHCOMP_RC=$?', 120)
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    tools = dict((t, rc) for t, rc in re.findall(r"^TOOL (\S+) (\d+)\s*$", out, re.M))
    want = ["jq", "htop", "rsync", "nano", "less", "ethtool", "dmidecode", "lspci", "lsusb", "ping"]
    c = {"smartctl_version": get("SMARTV_RC") == "0", "smartctl_scan": get("SCAN_RC") == "0",
         "smartctl_H_runs": get("SMARTH_BANNER") not in ("0", "?"),
         "sgdisk_p": get("SGDISK_RC") == "0" and get("SGDISK_TABLE") not in ("0", "?"),
         "btrfs": get("BTRFS_RC") == "0",
         "admin_tools": all(tools.get(t) == "0" for t in want),
         "bash_completion": get("BASHCOMP_RC") == "0"}  # smartd is no longer masked: CRITERIA-FIRSTBOOT.md section 11 (F15)
    record("F13", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" disk={get('DISK')} tools={tools}")
BOX_BINDS = {"/var/lib/fwupd": "var-lib-fwupd", "/var/cache/fwupd": "var-cache-fwupd",
             "/var/lib/rasdaemon": "var-lib-rasdaemon", "/var/lib/udisks2": "var-lib-udisks2"}


def f14(vm, board):
    """Step 2b: box care for a 24/7 machine (CRITERIA-FIRSTBOOT.md section 10). Returns the marker content."""
    marker = "f14-" + os.urandom(8).hex()
    cmds = [
        "fwupdmgr --version >/dev/null 2>&1; echo FWUPD_RC=$?",
        "sensors -v >/dev/null 2>&1; echo SENSORS_RC=$?",
        "ras-mc-ctl --help >/dev/null 2>&1; echo RASCTL_RC=$?",
        "udisksctl help >/dev/null 2>&1; echo UDISKSCTL_RC=$?",
        "timeout 90 fwupdmgr get-devices --no-unreported-check >/tmp/f14.fw 2>&1; echo FWDEV_RC=$?; echo FWDEV_HEAD=$(head -c 80 /tmp/f14.fw | tr -d '\\n' | tr ' ' '_')",
        "timeout 60 udisksctl status >/dev/null 2>&1; echo UDSTATUS_RC=$?",
        "for u in fwupd-refresh.timer fwupd-refresh.service; do echo STATE $u $(systemctl is-enabled $u 2>&1 | head -1); done",
        "echo STATE fwupd.service $(systemctl is-enabled fwupd.service 2>&1 | head -1)",
        "echo STATE fstrim.timer $(systemctl is-enabled fstrim.timer 2>&1 | head -1)",
        "echo STATE rasdaemon.service $(systemctl is-enabled rasdaemon.service 2>&1 | head -1)",
        "echo STATE thermald.service $(systemctl is-enabled thermald.service 2>&1 | head -1); echo ACTIVE=$(systemctl is-active thermald.service 2>&1 | head -1)",
        "echo THERMALD_PKG=$(dpkg -s thermald >/dev/null 2>&1 && echo yes || echo no)",
        "echo FSTRIM_LAST=$(systemctl cat fstrim.service | grep '^ExecStart=' | tail -1 | tr ' ' '_')",
        "systemctl start fstrim.service; echo FSTRIM_RC=$?",
        "echo WATCHDOG=$(systemctl show -p RuntimeWatchdogUSec --value)",
        "for p in gvfs-udisks2-volume-monitor udiskie polkitd; do dpkg -s $p >/dev/null 2>&1; echo ABSENT $p $?; done",
    ]
    for path, src in BOX_BINDS.items():
        cmds.append(f"echo BIND {path} $(findmnt -no SOURCE {path} | head -1 | tr -d ' ') "
                    f"MARK=$(echo {marker} > {path}/onemind-f14 && sync && cat /data/state/{src}/onemind-f14)")
    _, out = vm.run("; ".join(cmds), 240)
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    state = {u: st for u, st in re.findall(r"^STATE (\S+) (\S+)", out, re.M)}
    amd = ARCH.get(board) == "amd64"
    binds = {p: (m.group(1), m.group(2)) for p, m in
             ((p, re.search(rf"^BIND {re.escape(p)} (\S*) MARK=(\S*)\s*$", out, re.M)) for p in BOX_BINDS) if m}
    absent = dict(re.findall(r"^ABSENT (\S+) (\d+)\s*$", out, re.M))
    c = {"fwupdmgr": get("FWUPD_RC") == "0", "sensors": get("SENSORS_RC") == "0",
         "ras_mc_ctl": get("RASCTL_RC") == "0", "udisksctl": get("UDISKSCTL_RC") == "0",
         "fwupd_get_devices_runs": get("FWDEV_RC") in ("0", "2"), "udisks_status_runs": get("UDSTATUS_RC") == "0",
         "refresh_masked": state.get("fwupd-refresh.timer") == "masked" and state.get("fwupd-refresh.service") == "masked",
         "fwupd_not_enabled": state.get("fwupd.service") != "enabled",
         "fstrim_enabled": state.get("fstrim.timer") == "enabled",
         "fstrim_data_only": get("FSTRIM_LAST").endswith("fstrim_--verbose_--quiet-unsupported_/data"),
         "fstrim_runs": get("FSTRIM_RC") == "0",
         "rasdaemon_enabled": state.get("rasdaemon.service") == "enabled",
         "thermald": (state.get("thermald.service") == "enabled" and get("ACTIVE") != "active") if amd
                     else get("THERMALD_PKG") == "no",
         "binds_on_data": len(binds) == 4 and all(("/state/" + BOX_BINDS[p] + "]") in v[0] for p, v in binds.items()) and all(v[1] == marker for v in binds.values()),
         "watchdog_30s": get("WATCHDOG") == "30s" if amd else True,
         "no_automount_helpers": len(absent) == 3 and all(v != "0" for v in absent.values())}
    # The loop device: detected, never mounted by itself, mounted read-only only when asked.
    _, out2 = vm.run(
        "truncate -s 64M /run/f14.img && mkfs.ext4 -q -F /run/f14.img && L=$(losetup --find --show /run/f14.img) && echo LOOP=$L; "
        "udevadm trigger --name-match=$L; udevadm settle --timeout=30; sleep 3; "
        "echo AUTO=$(udevadm info -q property -n $L | grep -c '^UDISKS_AUTO=0$'); "
        "echo MOUNTED_BEFORE=$(findmnt -S $L -n | wc -l)$(lsblk -no MOUNTPOINT $L | grep -c .); "
        "udisksctl info -b $L >/dev/null 2>&1; echo INFO_RC=$?; "
        "udisksctl mount -b $L -o ro >/tmp/f14.mnt 2>&1; echo MOUNT_RC=$?; cat /tmp/f14.mnt; "
        "echo RO=$(findmnt -S $L -no OPTIONS | tr ',' '\\n' | grep -c '^ro$'); "
        "udisksctl unmount -b $L >/dev/null 2>&1; echo UNMOUNT_RC=$?; losetup -d $L; rm -f /run/f14.img", 240)
    g2 = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out2, re.M) or ["?"])[-1]
    c.update({"loop_has_auto0": g2("AUTO") == "1", "loop_not_automounted": g2("MOUNTED_BEFORE") == "00",
              "udisks_info": g2("INFO_RC") == "0", "owner_mount_ro": g2("MOUNT_RC") == "0" and g2("RO") == "1",
              "owner_unmount": g2("UNMOUNT_RC") == "0"})
    record("F14", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" states={state} fwdev={get('FWDEV_RC')}/{get('FWDEV_HEAD')} binds={binds}"
           + ("" if all(c.values()) else f" mount_out={out2[-700:]!r}"))
    return marker


def f14_again(vm, tid, marker):
    """F14b (after the reboot) and F14c (after the A/B update): the box-care state is still there."""
    cmds = []
    for path, src in BOX_BINDS.items():
        cmds.append(f"echo BIND {path} $(findmnt -no SOURCE {path} | head -1 | tr -d ' ') MARK=$(cat {path}/onemind-f14 2>&1)")
    cmds += ["echo STATE fstrim.timer $(systemctl is-enabled fstrim.timer 2>&1 | head -1)",
             "echo STATE rasdaemon.service $(systemctl is-enabled rasdaemon.service 2>&1 | head -1)"]
    _, out = vm.run("; ".join(cmds), 120)
    state = {u: st for u, st in re.findall(r"^STATE (\S+) (\S+)", out, re.M)}
    marks = {p: m.group(1) for p, m in
             ((p, re.search(rf"^BIND {re.escape(p)} \S* MARK=(\S*)\s*$", out, re.M)) for p in BOX_BINDS) if m}
    mounted = all(re.search(rf"^BIND {re.escape(p)} \S*/state/{BOX_BINDS[p]}\S* ", out, re.M) for p in BOX_BINDS)
    c = {"markers_kept": len(marks) == 4 and all(v == marker for v in marks.values()), "binds_mounted": mounted,
         "fstrim_enabled": state.get("fstrim.timer") == "enabled", "rasdaemon_enabled": state.get("rasdaemon.service") == "enabled"}
    record(tid, all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()))

# Runs in the guest as root: reads the host service the way the gateway does (CRITERIA-FIRSTBOOT.md section 11).
F15_PY = r"""
import http.client, json, socket, sys, time

class U(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("host", timeout=20)
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(20)
        self.sock.connect("/run/onemind/host.sock")

def call(method, path, body=None):
    c = U()
    try:
        c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
        r = c.getresponse()
        raw = r.read()
        try:
            return r.status, json.loads(raw or b"null")
        except ValueError:
            return r.status, None
    finally:
        c.close()

res = {}
for _ in range(30):  # the socket starts the service on the first request
    try:
        res["hk_code"], res["hk"] = call("GET", "/v1/storage/housekeeping")
        break
    except OSError:
        time.sleep(2)
res["st_code"], st = call("GET", "/v1/status")
res["kinds"] = [o.get("kind") for o in (st or {}).get("operations", [])]
if sys.argv[1] == "full":
    res["eject_code"], res["eject"] = call("POST", "/v1/operations", {"action_id": "f15-root-disk", "kind": "eject", "device": sys.argv[2]})
    res["ops_code"], ops = call("GET", "/v1/operations/f15-root-disk")
print("RESULT " + json.dumps(res))
"""


def f15(vm):
    """P-10: storage housekeeping is on the image and the host service reports it (CRITERIA-FIRSTBOOT.md section 11)."""
    marker = "f15-" + os.urandom(6).hex()
    feed = "/var/lib/smartmontools/onemind-alerts.jsonl"
    env = f"SMARTD_DEVICE=/dev/vda SMARTD_FAILTYPE=FailedHealthCheck SMARTD_MESSAGE={marker} SMARTD_TFIRSTEPOCH=1700000000"
    _, out = vm.run(
        "cat > /run/f15.py <<'PYEOF'\n" + F15_PY + "\nPYEOF\n"
        f"rm -f {feed}; "
        "echo STATE smartmontools.service $(systemctl is-enabled smartmontools.service 2>&1 | head -1); "
        "echo STATE smartd.service $(systemctl is-enabled smartd.service 2>&1 | head -1); "
        "echo CONF_NOMAILER=$(grep -E '^DEVICESCAN' /etc/smartd.conf | grep -c -- '-m <nomailer>'); "
        "echo CONF_EXEC=$(grep -E '^DEVICESCAN' /etc/smartd.conf | grep -c -- '-M exec /usr/lib/onemind/smartd-notify'); "
        "smartd -q onecheck -c /etc/smartd.conf >/run/f15.smartd 2>&1; echo SMARTD_RC=$?; "
        "echo SMARTD_CONF_ERRORS=$(grep -ciE 'fatal syntax|Directive:|unknown directive' /run/f15.smartd); "
        "echo NOTIFY_X=$(test -x /usr/lib/onemind/smartd-notify && echo yes || echo no); "
        f"env {env} /usr/lib/onemind/smartd-notify; env {env} /usr/lib/onemind/smartd-notify; "
        f"echo LINES_AFTER_TWO=$(wc -l < {feed}); echo HAS_MARKER=$(grep -c {marker} {feed}); "
        "SMARTD_DEVICE=/dev/disk/by-id/x SMARTD_FAILTYPE=Health SMARTD_MESSAGE=bad /usr/lib/onemind/smartd-notify; "
        f"echo LINES_AFTER_BAD=$(wc -l < {feed}); "
        "echo BIND=$(findmnt -no SOURCE /var/lib/smartmontools | head -1 | tr -d ' '); "
        "systemctl start fstrim.service; echo FSTRIM_RC=$?; "
        "ROOT=/dev/$(lsblk -no PKNAME \"$(findmnt -no SOURCE /)\" 2>/dev/null | head -1); echo ROOTDISK=$ROOT; "
        f"{PY} -I /run/f15.py full $ROOT; rm -f /run/f15.py", 300)
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    state = {u: st for u, st in re.findall(r"^STATE (\S+) (\S+)", out, re.M)}
    m = re.findall(r"^RESULT (\{.*\})\s*$", out, re.M)
    res = json.loads(m[-1]) if m else {}
    hk = res.get("hk") or {}
    trim, smart = hk.get("trim") or {}, hk.get("smart") or {}
    eject = res.get("eject") or {}
    c = {"smartd_enabled_not_masked": state.get("smartmontools.service") == "enabled" and state.get("smartd.service") != "masked",
         "conf_nomailer": get("CONF_NOMAILER") == "1", "conf_exec": get("CONF_EXEC") == "1",
         "conf_parses": get("SMARTD_CONF_ERRORS") == "0", "notify_executable": get("NOTIFY_X") == "yes",
         "one_line_for_a_reminder": get("LINES_AFTER_TWO") == "1" and get("HAS_MARKER") == "1",
         "plain_nodes_only": get("LINES_AFTER_BAD") == "1",
         "bind_on_data": get("BIND").startswith("/data/") or "/state/var-lib-smartmontools" in get("BIND"),
         "fstrim_ran": get("FSTRIM_RC") == "0",
         "housekeeping_200": res.get("hk_code") == 200 and trim.get("enabled") is True
         and bool(trim.get("last_run_at")) and bool(trim.get("next_run_at")),
         "alert_listed": any(a.get("id") == "1700000000-vda-FailedHealthCheck" and marker in a.get("message", "")
                             for a in smart.get("alerts") or []),
         "removable_is_a_list": isinstance(hk.get("removable"), list),
         "eject_kind_listed": "eject" in (res.get("kinds") or []),
         "root_disk_refused": res.get("eject_code") == 409 and eject.get("reason") == "not_removable" and res.get("ops_code") == 404}
    record("F15", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" rootdisk={get('ROOTDISK')} trim={trim} eject={eject} smartd_rc={get('SMARTD_RC')}")
    return marker


def f15_again(vm, tid, marker):
    """F15b (after the reboot) and F15c (after the A/B update): the warning and its state are still there."""
    feed = "/var/lib/smartmontools/onemind-alerts.jsonl"
    _, out = vm.run(
        "cat > /run/f15.py <<'PYEOF'\n" + F15_PY + "\nPYEOF\n"
        "echo BIND=$(findmnt -no SOURCE /var/lib/smartmontools | head -1 | tr -d ' '); "
        f"echo HAS_MARKER=$(grep -c {marker} {feed} 2>&1); "
        "echo STATE smartmontools.service $(systemctl is-enabled smartmontools.service 2>&1 | head -1); "
        f"{PY} -I /run/f15.py read; rm -f /run/f15.py", 200)
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    state = {u: st for u, st in re.findall(r"^STATE (\S+) (\S+)", out, re.M)}
    m = re.findall(r"^RESULT (\{.*\})\s*$", out, re.M)
    res = json.loads(m[-1]) if m else {}
    alerts = ((res.get("hk") or {}).get("smart") or {}).get("alerts") or []
    c = {"bind_mounted": "/state/var-lib-smartmontools" in get("BIND") or get("BIND").startswith("/data/"),
         "feed_kept": get("HAS_MARKER") == "1", "host_lists_it": any(marker in a.get("message", "") for a in alerts),
         "smartd_enabled": state.get("smartmontools.service") == "enabled"}
    record(tid, all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()))


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
        vm.mark("F10 rescue console with k3s stopped (CORE-UPDATE-9)"); f10(vm, token)
        vm.mark("F11 starting page, then the gateway, never a refused connection"); f11(vm, (os.path.dirname(a.results) or ".") if a.results else None)
        vm.mark("F12 the gateway reaches the host helper, and says missing without it (#875)"); f12(vm, token)
        vm.mark("F13 disk and admin tools run (Step 2)"); f13(vm)
        vm.mark("F14 box care: fwupd, fstrim, sensors, rasdaemon, udisks2 without automount (Step 2b)"); box_marker = f14(vm, a.board)
        vm.mark("F15 storage housekeeping: TRIM status, smartd warnings, eject refusal (P-10)"); smart_marker = f15(vm)

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
            vm.mark("F14b box-care state after the reboot"); f14_again(vm, "F14b", box_marker)
            vm.mark("F15b storage-housekeeping state after the reboot"); f15_again(vm, "F15b", smart_marker)
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
            vm.mark("F14c box-care state after the A/B update"); f14_again(vm, "F14c", box_marker)
            vm.mark("F15c storage-housekeeping state after the A/B update"); f15_again(vm, "F15c", smart_marker)
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
