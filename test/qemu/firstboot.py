#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, first boot (F0-F25, F29-F32, F34, FP1-FP3; F26-F28 are powercut.py's). Criteria:
test/qemu/CRITERIA-FIRSTBOOT.md
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
_spec = importlib.util.spec_from_file_location("netcheck", os.path.join(HERE, "netcheck.py"))
netcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(netcheck)       # NW1-NW4, CRITERIA-NETWORK.md
_spec = importlib.util.spec_from_file_location("netset", os.path.join(HERE, "netset.py"))
netset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(netset)         # NS1-NS3, CRITERIA-NETWORK-SET.md

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


def reboot_and_wait(vm, timeout=900, gate_timeout=1800):
    """Reboot a configured box; return (segment start, its first-boot line, its gate result).

    On a committed boot the health gate decides at once (os/gate/onemind-health-gate, "committed-boot"), and
    nothing orders onemind-health-gate.service against onemind-firstboot.service, which waits for cloud-init.
    So on a fast host the gate's line can come BEFORE "already configured". expect() moves the read position past
    the line it matched, so waiting for the gate after ALREADY skipped that boot's only gate line and hung for
    wait_gate's 1800 s (#1159). Search for the gate from the reboot on instead, as F1 (vm.pos = 0), edge.py and
    cloudboot.py already do. Both lines are still required, and both must come from this boot."""
    seg = vm.here()
    vm.send("systemctl reboot")
    al = vm.expect(ALREADY, timeout).group(0)
    vm.pos = seg                # this boot's buffer only: the earlier boots' gate lines lie before seg
    return seg, al, vm.wait_gate(gate_timeout)


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
        vm.expect(r"root@[a-z0-9-]+:~# ", 120)  # any name: F21 renames the box
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
    """Step 2 PRs 4 and 7: the disk and admin tools run on the booted image (CRITERIA-FIRSTBOOT.md section 9; its smartd-masked clause is replaced by F25, section 19)."""
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
         "bash_completion": get("BASHCOMP_RC") == "0"}  # smartd is no longer masked: CRITERIA-FIRSTBOOT.md section 19 (F25)
    record("F13", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" disk={get('DISK')} tools={tools}")

# F15's pseudo-terminal login, run in the guest (section 11): what a getty on tty2 does, with login(1) and PAM.
# The password arrives in the environment (F15_PW) and is never printed; only the parsed results are.
F15_PY = r"""
import os, pty, select, sys, time
pw = os.environ["F15_PW"]
def login(password, shell):
    pid, fd = pty.fork()
    if pid == 0:
        os.execv("/bin/login", ["login", "admin"])
    buf = b""
    def read_until(marks, t):
        nonlocal buf
        end = time.time() + t
        while time.time() < end:
            if any(m in buf for m in marks):
                return True
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                try:
                    d = os.read(fd, 4096)
                except OSError:
                    return any(m in buf for m in marks)
                if not d:
                    return any(m in buf for m in marks)
                buf += d
        return any(m in buf for m in marks)
    got = {"prompt": read_until([b"assword:"], 60)}
    os.write(fd, password.encode() + b"\n")
    if shell:
        got["shell"] = read_until([b"$ ", b"# "], 60)
        os.write(fd, b"echo WHO=$(id -un) MARK$((1+1))\n")
        got["who"] = read_until([b"MARK2"], 30)
        os.write(fd, ("echo SUDOID=$(echo '%s' | sudo -S -p '' id -u) DONE$((2+3))\n" % password).encode())
        got["sudo"] = read_until([b"DONE5"], 60)
        os.write(fd, b"exit\n")
    else:
        got["denied"] = read_until([b"Login incorrect"], 60)
        got["shell"] = b"MARK2" in buf
    text = buf.decode("utf-8", "replace")
    import re
    who = re.search(r"WHO=(\S+) MARK2", text)
    sud = re.search(r"SUDOID=(\S+) DONE5", text)
    try:
        os.kill(pid, 9)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass
    return {"who": who and who.group(1), "sudo": sud and sud.group(1), "denied": b"Login incorrect" in buf,
            "reached_shell": bool(who)}
good = login(pw, True)
bad = login(pw + "-wrong", False)
print("F15LOGIN good_who=%s good_sudo=%s bad_denied=%s bad_shell=%s" % (good["who"], good["sudo"], bad["denied"], bad["reached_shell"]))
"""

F15_SSHO = "-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o LogLevel=ERROR"


def f15_judge(out):
    """F15's verdict from the guest's output (pure, so test/unit can feed it canned text)."""
    g = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    cfg = {k: v for k, v in re.findall(r"^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|"
                                        r"authenticationmethods|allowusers) (.*?)\s*$", out, re.M)}
    login = re.findall(r"^F15LOGIN good_who=(\S+) good_sudo=(\S+) bad_denied=(\S+) bad_shell=(\S+)\s*$", out, re.M)
    lw, ls, bd, bs = login[-1] if login else ("", "", "", "")
    pkgs = set(g("PKG").split())
    c = {
        "packages": {"openssh-server", "sudo", "libpam-systemd"} <= pkgs,
        "admin_uid1000_bash": re.fullmatch(r"admin:x:1000:\d+:[^:]*:/home/admin:/bin/bash", g("ADMIN")) is not None,
        "no_baked_password": g("SHADOWLINE") == "0" and g("EXTRASH") == "0",
        "no_slot_hostkeys": g("SLOTKEYS0") == "0" and g("SLOTKEYS1") == "0",
        "no_key_sshd_inactive": g("SSH0") != "active" and g("SSH0") != "",
        "no_key_nothing_listens": g("LISTEN0") == "0" and g("NFT0") == "0",
        "key_added": g("ADDRC") == "0",
        "key_starts_sshd": g("SSH1") == "active" and g("LISTEN1") != "" and int(g("LISTEN1") or 0) >= 1,
        "firewall_opens_22": (g("NFT1") or "0").isdigit() and int(g("NFT1")) >= 1,
        "hostkeys_on_data": g("HK") == "/data/onemind/ssh/ssh_host_ed25519_key",
        "key_login": g("KEYLOGIN") == "admin",
        "password_set": g("PWRC") == "0",
        "password_refused": g("PWRC2") not in ("", "0") and "Permission denied (publickey)" in g("PWOUT"),
        "sshd_config": cfg.get("passwordauthentication") == "no" and cfg.get("kbdinteractiveauthentication") == "no"
        and cfg.get("permitrootlogin") == "no" and cfg.get("authenticationmethods") == "publickey"
        and cfg.get("allowusers") == "admin",
        "tty2_enabled": g("TTY2") == "enabled",
        "tty2_login": lw == "admin" and ls == "0",
        "tty2_wrong_password_refused": bd == "True" and bs == "False",
        "kiosk_starts": g("KIOSK") == "active" and g("SESS") != "" and int(g("SESS") or 0) >= 1,
    }
    return c


def f15(vm):
    """The owner shell (section 11): no key and sshd stays down; the first key starts it; key login works, password
    login is refused; a tty2 style login works with the console password; the kiosk still starts."""
    PYL = PY
    parts = []
    _, o = vm.run(
        "echo PKG=$(dpkg-query -W -f='${Package} ' openssh-server sudo libpam-systemd 2>&1); "
        "echo ADMIN=$(getent passwd admin); echo SHADOWLINE=$(grep -c '^admin:' /etc/shadow); "
        "echo EXTRASH=$(cat /var/lib/extrausers/shadow 2>/dev/null | grep -c '^admin:'); "
        "echo SLOTKEYS0=$(ls /etc/ssh/ssh_host_* 2>/dev/null | wc -l); "
        "echo SSH0=$(systemctl is-active ssh.service); "
        "echo LISTEN0=$(ss -ltn 'sport = :22' | grep -c LISTEN); "
        "echo NFT0=$(nft list chain inet onemind_host ssh | grep -c 'dport 22'); true", 120)
    parts.append(o)
    _, o = vm.run(
        "mkdir -p /run/f15 && rm -f /run/f15/k /run/f15/k.pub && ssh-keygen -q -t ed25519 -N '' -f /run/f15/k; "
        "/usr/lib/onemind/onemind-owner key-add /run/f15/k.pub; echo ADDRC=$?; "
        "t0=$SECONDS; while [ \"$(systemctl is-active ssh.service)\" != active ] && [ $((SECONDS - t0)) -lt 60 ]; do sleep 1; done; "
        "echo SSH1=$(systemctl is-active ssh.service); "
        "echo LISTEN1=$(ss -ltn 'sport = :22' | grep -c LISTEN); "
        "echo NFT1=$(nft list chain inet onemind_host ssh | grep -c 'tcp dport 22 accept'); "
        "echo HK=$(ls /data/onemind/ssh/ssh_host_ed25519_key); echo SLOTKEYS1=$(ls /etc/ssh/ssh_host_* 2>/dev/null | wc -l); "
        f"echo KEYLOGIN=$(ssh {F15_SSHO} -i /run/f15/k admin@127.0.0.1 'id -un' 2>&1 | tail -1); true", 240)
    parts.append(o)
    _, o = vm.run(
        "export F15_PW=$(head -c 18 /dev/urandom | base64 | tr -d '/+=\\n'); "
        "printf '%s\\n' \"$F15_PW\" | /usr/lib/onemind/onemind-owner password >/dev/null; echo PWRC=$?; "
        f"R=$(ssh {F15_SSHO} -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive "
        "admin@127.0.0.1 true 2>&1); echo PWRC2=$?; echo PWOUT=$(echo \"$R\" | tail -1); "
        "sshd -T 2>/dev/null | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|"
        "authenticationmethods|allowusers) '; "
        "echo TTY2=$(systemctl is-enabled getty@tty2.service 2>&1 | head -1); "
        "cat > /run/f15.py <<'PYEOF'\n" + F15_PY + "\nPYEOF\n"
        f"{PYL} -I /run/f15.py; unset F15_PW; rm -f /run/f15.py", 400)
    parts.append(o)
    _, o = vm.run(
        "mkdir -p /data/onemind/kiosk; touch /data/onemind/kiosk/enabled; systemctl start onemind-kiosk-apply.service; "
        "t0=$SECONDS; while [ \"$(systemctl is-active onemind-kiosk.service)\" != active ] && [ $((SECONDS - t0)) -lt 30 ]; do sleep 1; done; "
        "sleep 3; echo KIOSK=$(systemctl is-active onemind-kiosk.service); "
        "echo SESS=$(loginctl list-sessions --no-legend --no-pager | grep -c onemind-kiosk); "
        "journalctl -u onemind-kiosk.service -n 12 --no-pager -o cat | sed 's/^/KLOG /'; "
        "rm -f /data/onemind/kiosk/enabled; systemctl start onemind-kiosk-apply.service; rm -rf /run/f15; true", 180)
    parts.append(o)
    c = f15_judge("\n".join(parts))
    record("F15", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()))
# F16 (CRITERIA-FIRSTBOOT.md section 10): audio and Bluetooth on the boards with a screen.
SCREEN_BOARDS = {"x86_64-efi", "rpi5"}
F16_PKGS = ["pipewire", "pipewire-pulse", "wireplumber", "bluez", "libspa-0.2-bluetooth"]
F16_CONF = "/usr/lib/onemind/bluetooth/main.conf"
# The session user is the image's "onemind" account (uid 961): its user manager is started by hand, as the screen
# session's own user does not exist in every image. Commands run as that user with setpriv, no PAM, nothing written to /etc.
F16_UID = 961
F16_UNIT = f"user@{F16_UID}.service"      # the user manager of uid 961
F16_AS = ("setpriv --reuid=onemind --regid=onemind --clear-groups env XDG_RUNTIME_DIR=/run/user/961 "
          "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/961/bus ")


def f16_pairing_state(vm, token=None):
    """The pairing directory facts, as a dict of booleans plus the marker token read back. With a token, write it first."""
    write = (f"printf %s {token} > /var/lib/bluetooth/f16-marker; sync; " if token else "")
    _, out = vm.run(write +
        'echo MNT=$(findmnt -no FSROOT /var/lib/bluetooth 2>/dev/null | head -1); '
        'echo MNTFS=$(findmnt -no SOURCE /var/lib/bluetooth 2>/dev/null | head -1 | sed "s/\\[.*//"); '
        'echo DATAFS=$(findmnt -no SOURCE /data 2>/dev/null | head -1 | sed "s/\\[.*//"); '
        'echo DROOT=$(findmnt -no FSROOT /data 2>/dev/null | head -1); '
        'echo MARK=$(cat /var/lib/bluetooth/f16-marker 2>/dev/null); '
        'echo DMARK=$(cat /data/state/var-lib-bluetooth/f16-marker 2>/dev/null); '
        'echo BTACTIVE=$(systemctl is-active bluetooth.service 2>&1 | head -1)', 60)
    g = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    # FSROOT of /data is "/" on ext4 and "/@" on the btrfs layout (#152, @ is the default subvolume), so the bind's
    # root is compared with where /data itself starts, not with a fixed path.
    droot = g("DROOT").rstrip("/") if g("DROOT") != "?" else None
    return {"bind_of_data_dir": droot is not None and g("MNT") == droot + "/state/var-lib-bluetooth" and g("MNTFS") == g("DATAFS") != "?",
            "marker": g("MARK"), "marker_on_data": g("DMARK") == g("MARK") != "",
            "bluetooth_active": g("BTACTIVE") == "active"}


def f16(vm, board):
    """Step 3: PipeWire and BlueZ run on a screen board; the pairing directory is on /data; a no-screen board has neither."""
    if board not in SCREEN_BOARDS:
        _, out = vm.run("dpkg-query -W -f='${Package} ${Status}\\n' pipewire wireplumber bluez 2>/dev/null | grep -c 'install ok installed'; "
                        "echo MOUNT_RC=$(mountpoint -q /var/lib/bluetooth; echo $?); "
                        "echo BTENABLED=$(systemctl is-enabled bluetooth.service 2>&1 | head -1)", 60)
        installed = (re.findall(r"^(\d+)\s*$", out, re.M) or ["?"])[0]
        g = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
        c = {"none_installed": installed == "0", "not_a_mount": g("MOUNT_RC") == "1", "bluetooth_not_enabled": g("BTENABLED") != "enabled"}
        record("F16", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" board={board}")
        return None
    token = os.urandom(16).hex()
    _, out = vm.run(
        "for p in " + " ".join(F16_PKGS) + "; do dpkg-query -W -f='PKG ${Package} ${Status}\\n' $p 2>&1; done; "
        "echo GLOBAL=$(systemctl --global is-enabled pipewire.socket pipewire-pulse.socket wireplumber.service 2>&1 | tr '\\n' ',' ); "
        "echo BTENABLED=$(systemctl is-enabled bluetooth.service 2>&1 | head -1); "
        "echo BTCMD=$(tr '\\0' ' ' < /proc/$(systemctl show -p MainPID --value bluetooth.service)/cmdline 2>/dev/null | grep -a bluetoothd); "
        "busctl --system status org.bluez >/dev/null 2>&1; echo BUS_RC=$?; "
        f"grep -qE '^AutoEnable *= *false' {F16_CONF}; echo AUTO_RC=$?; "
        f"grep -qE '^AlwaysPairable *= *false' {F16_CONF}; echo ALWAYS_RC=$?; "
        f"grep -qE '^DiscoverableTimeout *= *[1-9]' {F16_CONF}; echo DISC_RC=$?; "
        f"grep -qE '^PairableTimeout *= *[1-9]' {F16_CONF}; echo PAIR_RC=$?; "
        "grep -qE '^ *AutoEnable *= *true' /etc/bluetooth/main.conf; echo ETCAUTO_RC=$?; "
        "echo ADAPTERS=$(timeout 15 bluetoothctl list 2>/dev/null | grep -c '^Controller')", 90)
    g = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or ["?"])[-1]
    pkgs = re.findall(r"^PKG (\S+) install ok installed", out, re.M)
    st = f16_pairing_state(vm, token)
    # The session user's manager, started by hand; the three daemons come up through the image's own user units.
    _, out2 = vm.run(
        f"systemctl start {F16_UNIT}; "
        f"{F16_AS}systemctl --user start pipewire.socket pipewire-pulse.socket; "
        f"{F16_AS}systemctl --user start wireplumber.service pipewire-pulse.service; "
        "t0=$SECONDS; while [ $((SECONDS - t0)) -lt 90 ]; do "
        f"a=$({F16_AS}systemctl --user is-active pipewire.service pipewire-pulse.service wireplumber.service 2>&1 | tr '\\n' ' '); "
        f"s=$({F16_AS}pactl list short sinks 2>&1); "
        "[ \"$a\" = 'active active active ' ] && echo \"$s\" | grep -q onemind-stream-sink && break; sleep 2; done; "
        "echo DAEMONS=$a; echo SINKS=$(echo \"$s\" | tr '\\n' ';'); "
        f"{F16_AS}pactl info 2>&1 | grep -E '^Server Name' ; "
        f"systemctl stop {F16_UNIT}; echo DONE=1", 200)
    g2 = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out2, re.M) or ["?"])[-1]
    c = {"packages": sorted(pkgs) == sorted(F16_PKGS),
         "user_units_enabled": g("GLOBAL") == "enabled,enabled,enabled,",
         "bluetooth_enabled": g("BTENABLED") == "enabled", "bluetooth_active": st["bluetooth_active"],
         "bluetoothd_config": f"-f {F16_CONF}" in g("BTCMD"), "dbus_org_bluez": g("BUS_RC") == "0",
         "no_adapter_in_vm": g("ADAPTERS") == "0",
         "adapter_off_by_default": g("AUTO_RC") == "0" and g("ETCAUTO_RC") == "1",
         "pairing_needs_agent": g("ALWAYS_RC") == "0", "timeouts": g("DISC_RC") == "0" and g("PAIR_RC") == "0",
         "pairing_dir_on_data": st["bind_of_data_dir"] and st["marker_on_data"] and st["marker"] == token,
         "audio_daemons_active": g2("DAEMONS") == "active active active",
         "virtual_sink": "onemind-stream-sink" in g2("SINKS")}
    if not all(c.values()):
        vm.run("systemctl status bluetooth.service var-lib-bluetooth.mount --no-pager 2>&1 | head -40; "
               "journalctl -u bluetooth.service -u var-lib-bluetooth.mount -b --no-pager 2>&1 | tail -25; "
               "findmnt /var/lib/bluetooth; ls -la /var/lib/bluetooth /data/state | head -30", 60)
    record("F16", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" adapters={g('ADAPTERS')}(none expected in QEMU) daemons={g2('DAEMONS')!r} sinks={g2('SINKS')[:120]!r} btcmd={g('BTCMD')[:100]!r}")
    return token


# F34 (CRITERIA-FIRSTBOOT.md section 27): the box's own monitor shows the OneMind desktop by default (kiosk on).
F34_NO_MONITOR = "kiosk: no monitor is connected; showing the text screen until one is"
F34_FACTS = (
    "echo PKGS=$(dpkg-query -W -f='${Package}:${Status} ' cage chromium 2>/dev/null | grep -o '[a-z]*:install ok installed' | cut -d: -f1 | sort | tr '\\n' ' '); "
    "echo BINS=$(test -x /usr/bin/cage && test -x /usr/bin/chromium && echo yes || echo no); "
    "echo FLAG=$(test -e /data/onemind/kiosk/enabled && echo yes || echo no); "
    "echo DIROWNER=$(stat -c %U /data/onemind/kiosk 2>/dev/null); "
    "echo MARKER=$(test -e /data/onemind/firstboot/kiosk-default && echo yes || echo no); "
    "echo KIOSK=$(systemctl is-active onemind-kiosk.service 2>&1 | head -1); "
    "echo SCREEN=$(systemctl is-active onemind-screen.service 2>&1 | head -1); "
    "echo TEXTPROC=$(grep -l onemind_screen.py $(sed 's#^#/proc/#; s#$#/cmdline#' /sys/fs/cgroup/system.slice/onemind-kiosk.service/cgroup.procs 2>/dev/null) 2>/dev/null | wc -l); "
    "echo CHROMIUM=$(pgrep -x chromium 2>/dev/null | wc -l); "
    "journalctl -u onemind-kiosk.service -b --no-pager -o cat 2>/dev/null | sed 's/^/KLOG /'; true")


def f34_judge(out, board, after_reboot=False):
    """F34's or F34r's verdict from the guest's output (pure, so test/unit can feed it canned text)."""
    g = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    klog = "\n".join(re.findall(r"^KLOG (.*)$", out, re.M))
    pkgs = set(g("PKGS").split())
    if after_reboot:
        return {"owner_off_kept": g("FLAG") == "no", "text_screen_active": g("SCREEN") == "active",
                "kiosk_not_active": g("KIOSK") != "active" and g("KIOSK") != ""}
    if board not in SCREEN_BOARDS:
        return {"no_kiosk_packages": not ({"cage", "chromium"} & pkgs),
                "no_flag": g("FLAG") == "no", "text_screen_active": g("SCREEN") == "active"}
    return {"image_packages": {"cage", "chromium"} <= pkgs and g("BINS") == "yes",
            "default_on": g("FLAG") == "yes" and g("DIROWNER") == "onemind" and g("MARKER") == "yes",
            "kiosk_active": g("KIOSK") == "active", "text_unit_skipped": g("SCREEN") not in ("active", ""),
            "no_monitor_fallback": F34_NO_MONITOR in klog and (g("TEXTPROC") or "0").isdigit() and int(g("TEXTPROC") or 0) >= 1
            and g("CHROMIUM") == "0",
            "nothing_secret": re.search(r"\b[0-9a-f]{64}\b", klog) is None and "ONEMIND OWNER TOKEN" not in klog}


def f34(vm, board, tid="F34", after_reboot=False):
    """Kiosk on by default on a screen board, the text screen inside it with no monitor; none on a no-screen board.
    F34r: after the reboot, the owner's "off" (F15 removed the flag) is kept."""
    # Give the kiosk unit a moment after boot: it starts after first boot and waits on nothing else here.
    _, out = vm.run("t0=$SECONDS; while [ $((SECONDS - t0)) -lt 60 ] && ! systemctl -q is-active onemind-kiosk.service "
                    "&& ! systemctl -q is-active onemind-screen.service; do sleep 2; done; sleep 5; " + F34_FACTS, 120)
    c = f34_judge(out, board, after_reboot)
    record(tid, all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" board={board}")


def f16_after(vm, tid, token):
    """F16r / F16u: the same pairing directory and marker after a reboot or an A/B update."""
    st = f16_pairing_state(vm)
    c = {"bind_of_data_dir": st["bind_of_data_dir"], "marker_kept": st["marker"] == token and st["marker_on_data"],
         "bluetooth_active": st["bluetooth_active"]}
    record(tid, all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()))

def f14(vm):
    """CLI polish (#882): onemind completion and man pages are installed and work (CRITERIA-FIRSTBOOT.md section 10)."""
    _, out = vm.run(
        'B=/usr/share/bash-completion/completions/onemind; test -s $B; echo BASHFILE_RC=$?; '
        'test -s /usr/share/zsh/vendor-completions/_onemind; echo ZSH_RC=$?; '
        'test -s /usr/share/fish/vendor_completions.d/onemind.fish; echo FISH_RC=$?; '
        'bash -c ". /usr/share/bash-completion/bash_completion; . $B; complete -p onemind" 2>&1 | head -2; '
        'echo COMPLETE_FN=$(bash -c ". /usr/share/bash-completion/bash_completion; . $B; complete -p onemind" 2>/dev/null | grep -c "_onemind"); '
        'onemind __complete ap > /tmp/f14.c 2>&1; echo CAND_RC=$?; echo CAND_APPS=$(grep -c "^apps" /tmp/f14.c); '
        'echo MANW1=$(man -w onemind 2>&1 | head -1); echo MANW2=$(man -w onemind-apps 2>&1 | head -1); '
        'MANPAGER=cat MANWIDTH=80 man onemind > /tmp/f14.m 2>&1; echo MAN_RC=$?; '
        'echo MAN_NAME=$(grep -ci onemind /tmp/f14.m); echo MAN_SYN=$(grep -c "SYNOPSIS" /tmp/f14.m); rm -f /tmp/f14.c /tmp/f14.m', 120)
    get = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or ["?"])[-1]
    c = {"bash_file": get("BASHFILE_RC") == "0", "zsh_file": get("ZSH_RC") == "0", "fish_file": get("FISH_RC") == "0",
         "complete_registered": get("COMPLETE_FN") not in ("0", "?"),
         "cobra_candidates": get("CAND_RC") == "0" and get("CAND_APPS") not in ("0", "?"),
         "man_w_root": get("MANW1").startswith("/usr/share/man/man1/"),
         "man_w_sub": get("MANW2").startswith("/usr/share/man/man1/"),
         "man_renders": get("MAN_RC") == "0" and get("MAN_NAME") not in ("0", "?") and get("MAN_SYN") not in ("0", "?")}
    record("F14", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" manw={get('MANW1')!r}")

def f17(vm):
    """The clock is Debian's own: systemd-timesyncd runs, tzdata is there, LANG is C.UTF-8 (section 12)."""
    _, out = vm.run("echo ENABLED=$(systemctl is-enabled systemd-timesyncd.service 2>&1 | head -1); "
                    "echo ACTIVE=$(systemctl is-active systemd-timesyncd.service 2>&1 | head -1); "
                    "echo ZONE=$(test -r /usr/share/zoneinfo/UTC && echo ok || echo missing); "
                    "echo LOCALE=$(grep -v '^#' /etc/locale.conf 2>/dev/null | head -1); "
                    "for i in $(seq 1 30); do [ \"$(timedatectl show -p NTPSynchronized --value 2>/dev/null)\" = yes ] && break; sleep 2; done; "
                    "echo SYNC=$(timedatectl show -p NTPSynchronized --value 2>&1 | head -1); "
                    "echo SERVER=$(timedatectl timesync-status 2>/dev/null | sed -n 's/^ *Server: *//p' | head -1)", 200)
    get = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    sync, server = get("SYNC"), get("SERVER")
    c = {"timesyncd_enabled": get("ENABLED") == "enabled", "timesyncd_active": get("ACTIVE") == "active",
         "tzdata": get("ZONE") == "ok", "lang_c_utf8": get("LOCALE") == "LANG=C.UTF-8"}
    # user-mode networking may not reach any NTP server: then the unit being enabled and running is the proof, and
    # the detail says so. If a server was reached, the clock must report synchronised (what node-check.sh asks).
    c["synchronised_if_reachable"] = sync == "yes" or not server or server.startswith("n/a")
    record("F17", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" NTPSynchronized={sync} ntp_server={server!r}" + ("" if sync == "yes" else " (NTP server unreachable from the VM)"))


HOSTSOCK = "curl -s --max-time 10 --unix-socket /run/onemind/host.sock"


def zone_probe(vm):
    """What the box says its zone is now: the symlink's target, the UTC offset, and the host's own GET /v1/time."""
    _, out = vm.run("echo LINK=$(readlink -f /etc/localtime); echo OFFSET=$(date +%z); "
                    f"echo TIME=$({HOSTSOCK} http://host/v1/time | tr -d '\\n')", 60)
    get = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    try:
        host_zone = json.loads(get("TIME")).get("zone")
    except ValueError:
        host_zone = None
    return get("LINK"), get("OFFSET"), host_zone


def f18(vm):
    """The host applies a time zone now: the symlink on /data is swapped, the offset changes, an unknown zone is refused (section 13)."""
    before = zone_probe(vm)
    _, out = vm.run(
        f"{HOSTSOCK} -o /dev/null -w 'POST=%{{http_code}}\\n' -X POST http://host/v1/operations "
        "-d '{\"action_id\":\"f14-tz\",\"kind\":\"set-timezone\",\"zone\":\"Pacific/Auckland\"}'; "
        "for i in $(seq 1 30); do "
        f"S=$({HOSTSOCK} http://host/v1/operations/f14-tz | sed -n 's/.*\"state\":\"\\([a-z_]*\\)\".*/\\1/p'); "
        "[ \"$S\" = succeeded ] || [ \"$S\" = failed ] && break; sleep 1; done; echo STATE=$S; "
        f"{HOSTSOCK} -w '\\nBAD=%{{http_code}}\\n' -X POST http://host/v1/operations "
        "-d '{\"action_id\":\"f14-bad\",\"kind\":\"set-timezone\",\"zone\":\"Mars/Olympus\"}'", 90)
    get = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    after = zone_probe(vm)
    c = {"started_utc": before[0].startswith("/usr/share/zoneinfo/") and before[2] == "UTC",
         "accepted": get("POST") in ("200", "202"), "succeeded": get("STATE") == "succeeded",
         "link_auckland": after[0].endswith("zoneinfo/Pacific/Auckland"), "offset_plus_1300": after[1] == "+1300",
         "host_reports_zone": after[2] == "Pacific/Auckland",
         "unknown_refused": get("BAD") == "409" and "unknown_zone" in out}
    record("F18", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" before={before} after={after}")


def f19(vm):
    """The zone survives the reboot (section 13)."""
    link, offset, host_zone = zone_probe(vm)
    c = {"link_auckland": link.endswith("zoneinfo/Pacific/Auckland"), "offset_plus_1300": offset == "+1300",
         "host_reports_zone": host_zone == "Pacific/Auckland"}
    record("F19", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" link={link} offset={offset} host_zone={host_zone}")

# F20's helper, run in the guest (section 14): file a restart, approve it, and read the ledger after the reboot.
F20_PY = r"""
import json, sys, time, urllib.error, urllib.request
phase, token = sys.argv[1], sys.argv[2]
def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("http://127.0.0.1:8080" + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, ValueError):
        return None, None
boot = lambda: open("/proc/sys/kernel/random/boot_id").read().strip()
if phase == "file":
    b0 = boot()
    code, a = call("POST", "/v1/system/actions", {"type": "system.restart", "reason": "F20", "idempotency_key": "f20"})
    time.sleep(10)
    json.dump({"id": (a or {}).get("id"), "boot": b0}, open("/data/onemind/f20-state", "w"))
    print("RESULT file " + json.dumps({"code": code, "state": (a or {}).get("state"), "id": (a or {}).get("id"),
                                       "same_boot": boot() == b0, "boot": b0}))
elif phase == "approve":
    st = json.load(open("/data/onemind/f20-state"))
    code, _ = call("POST", "/v1/actions/" + st["id"] + "/approve", {})
    json.dump({**st, "approve": code}, open("/data/onemind/f20-state", "w"))
    time.sleep(600)
else:
    st = json.load(open("/data/onemind/f20-state"))
    t0, state = time.time(), None
    while time.time() - t0 < 120:
        code, a = call("GET", "/v1/actions/" + st["id"])
        state = (a or {}).get("state")
        if state in ("succeeded", "failed", "outcome_unknown"):
            break
        time.sleep(3)
    print("RESULT after " + json.dumps({"state": state, "approve": st.get("approve"), "was_boot": st["boot"], "boot": boot()}))
"""


def f20(vm, token):
    """An approved restart reboots the box, and the ledger action ends succeeded (section 14)."""
    _, out = vm.run("cat > /run/f20.py <<'PYEOF'\n" + F20_PY + "\nPYEOF\n" + f"{PY} -I /run/f20.py file '{token}'", 120)
    filed = json.loads((re.findall(r"^RESULT file (\{.*\})\s*$", out, re.M) or ["{}"])[-1])
    seg = vm.here()
    vm.send(f"{PY} -I /run/f20.py approve '{token}'")
    al = vm.expect(ALREADY, 900).group(0)
    g = vm.wait_gate(); vm.shell_ready()
    new_toks = TOKEN.findall(vm.since(seg))
    hz = http_code(vm, f"{GW}/healthz", timeout=900)
    if hz != "200":
        diagnose(vm, f"healthz={hz} after the approved restart")
    _, out = vm.run("cat > /run/f20.py <<'PYEOF'\n" + F20_PY + "\nPYEOF\n" + f"{PY} -I /run/f20.py after '{token}'; rm -f /run/f20.py /data/onemind/f20-state", 240)
    after = json.loads((re.findall(r"^RESULT after (\{.*\})\s*$", out, re.M) or ["{}"])[-1])
    c = {"filed": filed.get("code") == 202 and filed.get("state") == "awaiting_approval" and bool(filed.get("id")),
         "nothing_before_approval": filed.get("same_boot") is True,
         "approved_200": after.get("approve") == 200,
         "rebooted": bool(after.get("boot")) and after.get("boot") != after.get("was_boot") == filed.get("boot"),
         "no_new_token": not new_toks, "healthz": hz == "200", "succeeded": after.get("state") == "succeeded"}
    record("F20", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" '{al[:60]}' gate={g} ledger={after.get('state')}")

NEW_NAME = "omtest-new"


def f21(vm):
    """P-05: a set-hostname request to the host helper renames the running system and avahi answers <name>.local."""
    sock = "curl -s --unix-socket /run/onemind/host.sock -w ' CODE=%{http_code}'"
    post = lambda body: f"{sock} -X POST -H 'Content-Type: application/json' -d '{body}' http://host/v1/operations"
    good = json.dumps({"action_id": "f21-rename", "kind": "set-hostname", "hostname": NEW_NAME})
    bad = json.dumps({"action_id": "f21-bad", "kind": "set-hostname", "hostname": "Bad Name"})
    _, out = vm.run(f"echo POST=$({post(good)}); "
                    f"for i in $(seq 1 30); do s=$({sock} http://host/v1/operations/f21-rename | grep -o '\"state\":\"[a-z_]*\"'); "
                    "case \"$s\" in *succeeded*|*failed*) break;; esac; sleep 2; done; echo STATE=$s; "
                    "echo HOST=$(cat /proc/sys/kernel/hostname); echo FILE=$(cat /data/onemind/etc/hostname); "
                    "echo HOSTS=$(grep '^127.0.1.1' /etc/hosts | tr -s ' \\t' ' '); "
                    f"echo STATUS=$({sock} http://host/v1/status | grep -o '\"hostname\":\"[^\"]*\"'); "
                    f"for i in $(seq 1 30); do r=$(avahi-resolve -n {NEW_NAME}.local 2>/dev/null); [ -n \"$r\" ] && break; sleep 2; done; echo MDNS=$r; "
                    f"echo BAD=$({post(bad)}); echo AFTER=$(cat /proc/sys/kernel/hostname)", 400)
    g = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    c = {"accepted": g("POST").endswith(("CODE=202", "CODE=200")), "succeeded": "succeeded" in g("STATE"),
         "running_name": g("HOST") == NEW_NAME, "saved_on_data": g("FILE") == NEW_NAME,
         "hosts_line": g("HOSTS") == f"127.0.1.1 {NEW_NAME}", "status_name": g("STATUS") == f'"hostname":"{NEW_NAME}"',
         "mdns_answers": g("MDNS").startswith(f"{NEW_NAME}.local"), "bad_name_400": g("BAD").endswith("CODE=400"),
         "name_kept": g("AFTER") == NEW_NAME}
    record("F21", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" out={out.strip()[-400:]!r}")


def f22(vm):
    """P-05: the new name is still the box's name after a reboot, and avahi still answers it."""
    _, out = vm.run(f"for i in $(seq 1 60); do r=$(avahi-resolve -n {NEW_NAME}.local 2>/dev/null); [ -n \"$r\" ] && break; sleep 2; done; "
                    "echo HOST=$(cat /proc/sys/kernel/hostname); echo FILE=$(cat /data/onemind/etc/hostname); echo MDNS=$r", 300)
    g = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    c = {"running_name": g("HOST") == NEW_NAME, "saved_on_data": g("FILE") == NEW_NAME, "mdns_answers": g("MDNS").startswith(f"{NEW_NAME}.local")}
    record("F22", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" out={out.strip()[-300:]!r}")


# F23's script, run in the guest with the gateway's Python (section 16): the owner's SSH keys and switch through the
# real chain (gateway API, owner approval, host service, onemind-ssh-apply.service, sshd). Keys are made here for
# this test only. It prints "F23 NAME=value" lines; f23_judge reads them. No token or private key is printed.
F23_PY = r"""
import json, os, subprocess, sys, time, urllib.error, urllib.request
GW = "http://127.0.0.1:8080"
TOKEN = sys.argv[1]
SSHO = "-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o LogLevel=ERROR"
def out(k, v): print("F23 %s=%s" % (k, v), flush=True)
def api(method, path, body=None, token=TOKEN):
    h = {"Content-Type": "application/json"}
    if token: h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(GW + path, method=method, headers=h, data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=150) as r: return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"null")
        except Exception: return e.code, None
def sh(cmd, t=150):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)
    return p.returncode, (p.stdout + p.stderr).strip()
def login(key):
    rc, o = sh("ssh %s -i %s admin@127.0.0.1 'id -un' 2>&1" % (SSHO, key))
    return rc, (o.splitlines() or [""])[-1]
def active(): return sh("systemctl is-active ssh.service")[1]
def listening(): return int(sh("ss -ltn 'sport = :22' | grep -c LISTEN")[1] or 0)
def wait(cond, t=60):
    end = time.time() + t
    while time.time() < end:
        if cond(): return True
        time.sleep(1)
    return cond()
def settle(a):
    end = time.time() + 120
    while time.time() < end:
        c, d = api("GET", "/v1/actions/" + a["id"])
        if c == 200 and d["state"] in ("succeeded", "failed", "outcome_unknown"): return d["state"]
        time.sleep(1)
    return "timeout"
def approve(a):
    c, d = api("POST", "/v1/actions/%s/approve" % a["id"])
    return settle(a) if c == 200 else "approve_%s" % c
def fp(pub): return sh("ssh-keygen -l -f %s | cut -d' ' -f2" % pub)[1]

sh("rm -rf /run/f20 && mkdir -p /run/f20 && ssh-keygen -q -t ed25519 -N '' -f /run/f20/k1 && ssh-keygen -q -t ed25519 -N '' -C second -f /run/f20/k2")
K1, K2 = "/run/f20/k1", "/run/f20/k2"
out("noauth", api("GET", "/v1/ssh", token="")[0])
c, v = api("GET", "/v1/ssh"); s = (v or {}).get("service", {})
out("get", c); out("available", s.get("available")); out("password_login", s.get("password_login")); out("port", s.get("port")); out("user", s.get("user"))

c, a = api("POST", "/v1/ssh/keys", {"public_key": open(K1 + ".pub").read().strip()})
out("b_code", c); out("b_state", (a or {}).get("state")); out("b_type", (a or {}).get("type"))
out("b_pre_login", login(K1)[1])
out("c_state", approve(a))
wait(lambda: active() == "active" and listening() >= 1)
out("c_login", login(K1)[1])
c, ks = api("GET", "/v1/ssh/keys")
out("c_listed", fp(K1 + ".pub") in [k["fingerprint"] for k in (ks or {}).get("keys", [])])

c, a2 = api("POST", "/v1/ssh/keys", {"public_key": open(K2 + ".pub").read().strip()})
out("d_add_code", c); out("d_add_state", approve(a2)); out("d_k2_login", login(K2)[1])
c, ks = api("GET", "/v1/ssh/keys")
kid = [k["id"] for k in (ks or {}).get("keys", []) if k["fingerprint"] == fp(K2 + ".pub")]
c, d = api("DELETE", "/v1/ssh/keys/" + (kid[0] if kid else "missing"))
out("d_del_code", c); out("d_del_state0", (d or {}).get("state")); out("d_k2_before_approval", login(K2)[1])
out("d_del_state", approve(d) if c == 202 else "none")
rc, o = sh("ssh %s -i %s admin@127.0.0.1 'id -un' 2>&1" % (SSHO, K2))
out("d_k2_after_rc", rc); out("d_k2_after_denied", "Permission denied (publickey)" in o)
out("d_k1_still", login(K1)[1])
c, ks = api("GET", "/v1/ssh/keys")
fps = [k["fingerprint"] for k in (ks or {}).get("keys", [])]
out("d_k2_listed", fp(K2 + ".pub") in fps); out("d_k1_listed", fp(K1 + ".pub") in fps)

def limit_ok():
    # Both limit rules (IPv4 and IPv6) are in the chain and come before the accept rule.
    lines = sh("nft list chain inet onemind_host ssh")[1].splitlines()
    lim = [i for i, l in enumerate(lines) if "dport 22" in l and "limit rate over 6/minute" in l]
    acc = [i for i, l in enumerate(lines) if l.strip().startswith("tcp dport 22 accept")]
    return len(lim) == 2 and bool(acc) and max(lim) < acc[0]
out("e_limit_first", limit_ok())

c, a = api("PUT", "/v1/ssh", {"enabled": False})
out("f_code", c); out("f_state0", (a or {}).get("state")); out("f_listen_before", listening())
out("f_state", approve(a))
wait(lambda: listening() == 0 and active() != "active")
out("f_active", active()); out("f_listen", listening())
out("f_nft", sh("nft list chain inet onemind_host ssh | grep -c 'dport 22'")[1])
out("f_flag", os.path.exists("/data/onemind/ssh/disabled")); out("f_login_rc", login(K1)[0])
sh("systemctl start ssh.service; sleep 2"); out("f_restart_active", active())

c, a = api("PUT", "/v1/ssh", {"enabled": True})
out("g_state", approve(a))
wait(lambda: active() == "active" and listening() >= 1)
out("g_active", active()); out("g_listen", listening()); out("g_flag", os.path.exists("/data/onemind/ssh/disabled")); out("g_login", login(K1)[1])
# (e) again after SSH went off and on (the second start of ssh.service), and after a firewall restart (host.nft reloads,
# the ssh chain empties, sshd restarts with it). The limit must come back each time (section 17 amendment).
out("e_limit_after_on", limit_ok())
sh("systemctl restart onemind-firewall.service")
wait(lambda: active() == "active" and listening() >= 1 and limit_ok())
out("e_limit_after_fw", limit_ok()); out("e_fw_login", login(K1)[1])

before = len(api("GET", "/v1/actions")[1] or [])
c, _ = api("POST", "/v1/ssh/keys", {"public_key": 'command="id" ' + open(K1 + ".pub").read().strip()})
out("i_code", c); out("i_filed", len(api("GET", "/v1/actions")[1] or []) - before)
sh("rm -rf /run/f20")
"""


def f23_judge(out):
    """F23's verdict from the guest's output (pure, so test/unit can feed it canned text). (h), an agent's request,
    is skipped: the first boot mints no agent token."""
    g = lambda k: (re.findall(rf"^F23 {k}=(.*?)\s*$", out, re.M) or [""])[-1]
    t, isint = "True", lambda k: g(k).isdigit()
    c = {
        "reads": g("get") == "200" and g("available") == t and g("password_login") == "False" and g("port") == "22"
        and g("user") == "admin" and g("noauth") == "401",
        "request_waits": g("b_code") == "202" and g("b_state") == "awaiting_approval" and g("b_type") == "ssh.key.add"
        and g("b_pre_login") != "admin",
        "approval_adds": g("c_state") == "succeeded" and g("c_login") == "admin" and g("c_listed") == t,
        "second_key": g("d_add_code") == "202" and g("d_add_state") == "succeeded" and g("d_k2_login") == "admin",
        "removal_waits": g("d_del_code") == "202" and g("d_del_state0") == "awaiting_approval" and g("d_k2_before_approval") == "admin",
        "removal_refuses": g("d_del_state") == "succeeded" and isint("d_k2_after_rc") and g("d_k2_after_rc") != "0"
        and g("d_k2_after_denied") == t and g("d_k1_still") == "admin" and g("d_k2_listed") == "False" and g("d_k1_listed") == t,
        "rate_limit_rule": g("e_limit_first") == t and g("e_limit_after_on") == t and g("e_limit_after_fw") == t and g("e_fw_login") == "admin",
        "off_waits": g("f_code") == "202" and g("f_state0") == "awaiting_approval" and isint("f_listen_before") and int(g("f_listen_before")) >= 1,
        "off_closes_port": g("f_state") == "succeeded" and g("f_active") != "active" and g("f_active") != "" and g("f_listen") == "0"
        and g("f_nft") == "0" and g("f_flag") == t and isint("f_login_rc") and g("f_login_rc") != "0",
        "off_holds": g("f_restart_active") != "active" and g("f_restart_active") != "",
        "on_opens_it": g("g_state") == "succeeded" and g("g_active") == "active" and isint("g_listen") and int(g("g_listen")) >= 1
        and g("g_flag") == "False" and g("g_login") == "admin",
        "bad_key_refused": g("i_code") == "422" and g("i_filed") == "0",
    }
    return c


def f23(vm, token):
    """SSH keys and the SSH switch through the approval queue (section 16)."""
    _, o = vm.run("cat > /run/f23.py <<'PYEOF'\n" + F23_PY + f"\nPYEOF\n{PY} -I /run/f23.py '{token}'; rm -f /run/f23.py", 900)
    c = f23_judge(o)
    record("F23", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + " agent_request=skipped(no agent token at first boot)")


BOX_BINDS = {"/var/lib/fwupd": "var-lib-fwupd", "/var/cache/fwupd": "var-cache-fwupd",
             "/var/lib/rasdaemon": "var-lib-rasdaemon", "/var/lib/udisks2": "var-lib-udisks2"}


def f24(vm, board):
    """Step 2b: box care for a 24/7 machine (CRITERIA-FIRSTBOOT.md section 18). Returns the marker content."""
    marker = "f24-" + os.urandom(8).hex()
    cmds = [
        "fwupdmgr --version >/dev/null 2>&1; echo FWUPD_RC=$?",
        "sensors -v >/dev/null 2>&1; echo SENSORS_RC=$?",
        "ras-mc-ctl --help >/dev/null 2>&1; echo RASCTL_RC=$?",
        "udisksctl help >/dev/null 2>&1; echo UDISKSCTL_RC=$?",
        "timeout 90 fwupdmgr get-devices --no-unreported-check >/tmp/f24.fw 2>&1; echo FWDEV_RC=$?; echo FWDEV_HEAD=$(head -c 80 /tmp/f24.fw | tr -d '\\n' | tr ' ' '_')",
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
        "echo DROOT=$(findmnt -no FSROOT /data | head -1)",
    ]
    for path, src in BOX_BINDS.items():
        cmds.append(f"echo BIND {path} $(findmnt -no SOURCE {path} | head -1 | tr -d ' ') "
                    f"MARK=$(echo {marker} > {path}/onemind-f24 && sync && cat /data/state/{src}/onemind-f24)")
    _, out = vm.run("; ".join(cmds), 240)
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    state = {u: st for u, st in re.findall(r"^STATE (\S+) (\S+)", out, re.M)}
    amd = ARCH.get(board) == "amd64"
    binds = {p: (m.group(1), m.group(2)) for p, m in
             ((p, re.search(rf"^BIND {re.escape(p)} (\S*) MARK=(\S*)\s*$", out, re.M)) for p in BOX_BINDS) if m}
    absent = dict(re.findall(r"^ABSENT (\S+) (\d+)\s*$", out, re.M))
    droot = get("DROOT").rstrip("/") if get("DROOT") != "?" else None
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
         # /data starts at "/" on ext4 and at "/@" on the btrfs layout (#152): the bind's root is "<that>/state/<dir>"
         "binds_on_data": droot is not None and len(binds) == 4 and all(f"[{droot}/state/{BOX_BINDS[p]}]" in v[0] for p, v in binds.items())
                          and all(v[1] == marker for v in binds.values()),
         "watchdog_30s": get("WATCHDOG") == "30s" if amd else True,
         "no_automount_helpers": len(absent) == 3 and all(v != "0" for v in absent.values())}
    # The loop device: detected, never mounted by itself, mounted read-only only when asked.
    _, out2 = vm.run(
        "truncate -s 64M /run/f24.img && mkfs.ext4 -q -F /run/f24.img && L=$(losetup --find --show /run/f24.img) && echo LOOP=$L; "
        "udevadm trigger --name-match=$L; udevadm settle --timeout=30; sleep 3; "
        "echo AUTO=$(udevadm info -q property -n $L | grep -c '^UDISKS_AUTO=0$'); "
        "echo MOUNTED_BEFORE=$(findmnt -S $L -n | wc -l)$(lsblk -no MOUNTPOINT $L | grep -c .); "
        "udisksctl info -b $L >/dev/null 2>&1; echo INFO_RC=$?; "
        "udisksctl mount -b $L -o ro >/tmp/f24.mnt 2>&1; echo MOUNT_RC=$?; cat /tmp/f24.mnt; "
        "echo RO=$(findmnt -S $L -no OPTIONS | tr ',' '\\n' | grep -c '^ro$'); "
        "udisksctl unmount -b $L >/dev/null 2>&1; echo UNMOUNT_RC=$?; losetup -d $L; rm -f /run/f24.img", 240)
    g2 = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out2, re.M) or ["?"])[-1]
    c.update({"loop_has_auto0": g2("AUTO") == "1", "loop_not_automounted": g2("MOUNTED_BEFORE") == "00",
              "udisks_info": g2("INFO_RC") == "0", "owner_mount_ro": g2("MOUNT_RC") == "0" and g2("RO") == "1",
              "owner_unmount": g2("UNMOUNT_RC") == "0"})
    record("F24", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" states={state} fwdev={get('FWDEV_RC')}/{get('FWDEV_HEAD')} binds={binds}"
           + ("" if all(c.values()) else f" mount_out={out2[-700:]!r}"))
    return marker


def f24_again(vm, tid, marker):
    """F24b (after the reboot) and F24c (after the A/B update): the box-care state is still there."""
    cmds = []
    for path, src in BOX_BINDS.items():
        cmds.append(f"echo BIND {path} $(findmnt -no SOURCE {path} | head -1 | tr -d ' ') MARK=$(cat {path}/onemind-f24 2>&1)")
    cmds += ["echo STATE fstrim.timer $(systemctl is-enabled fstrim.timer 2>&1 | head -1)",
             "echo STATE rasdaemon.service $(systemctl is-enabled rasdaemon.service 2>&1 | head -1)",
             "echo DROOT=$(findmnt -no FSROOT /data | head -1)"]
    _, out = vm.run("; ".join(cmds), 120)
    droot = (re.findall(r"^DROOT=(\S*)\s*$", out, re.M) or [None])[-1]
    droot = droot.rstrip("/") if droot is not None else None
    state = {u: st for u, st in re.findall(r"^STATE (\S+) (\S+)", out, re.M)}
    marks = {p: m.group(1) for p, m in
             ((p, re.search(rf"^BIND {re.escape(p)} \S* MARK=(\S*)\s*$", out, re.M)) for p in BOX_BINDS) if m}
    mounted = droot is not None and all(re.search(rf"^BIND {re.escape(p)} \S*\[{re.escape(droot)}/state/{BOX_BINDS[p]}\] ", out, re.M) for p in BOX_BINDS)
    c = {"markers_kept": len(marks) == 4 and all(v == marker for v in marks.values()), "binds_mounted": mounted,
         "fstrim_enabled": state.get("fstrim.timer") == "enabled", "rasdaemon_enabled": state.get("rasdaemon.service") == "enabled"}
    record(tid, all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()))


# Runs in the guest as root: reads the host service the way the gateway does (CRITERIA-FIRSTBOOT.md section 19).
F25_PY = r"""
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
    res["eject_code"], res["eject"] = call("POST", "/v1/operations", {"action_id": "f25-root-disk", "kind": "eject", "device": sys.argv[2]})
    res["ops_code"], ops = call("GET", "/v1/operations/f25-root-disk")
print("RESULT " + json.dumps(res))
"""


def f25(vm):
    """P-10: storage housekeeping is on the image and the host service reports it (CRITERIA-FIRSTBOOT.md section 19)."""
    marker = "f25-" + os.urandom(6).hex()
    feed = "/var/lib/smartmontools/onemind-alerts.jsonl"
    env = f"SMARTD_DEVICE=/dev/vda SMARTD_FAILTYPE=FailedHealthCheck SMARTD_MESSAGE={marker} SMARTD_TFIRSTEPOCH=1700000000"
    _, out = vm.run(
        "cat > /run/f25.py <<'PYEOF'\n" + F25_PY + "\nPYEOF\n"
        f"rm -f {feed}; "
        "echo STATE smartmontools.service $(systemctl is-enabled smartmontools.service 2>&1 | head -1); "
        "echo STATE smartd.service $(systemctl is-enabled smartd.service 2>&1 | head -1); "
        "echo CONF_NOMAILER=$(grep -E '^DEVICESCAN' /etc/smartd.conf | grep -c -- '-m <nomailer>'); "
        "echo CONF_EXEC=$(grep -E '^DEVICESCAN' /etc/smartd.conf | grep -c -- '-M exec /usr/lib/onemind/smartd-notify'); "
        "smartd -q onecheck -c /etc/smartd.conf >/run/f25.smartd 2>&1; echo SMARTD_RC=$?; "
        "echo SMARTD_CONF_ERRORS=$(grep -ciE 'fatal syntax|Directive:|unknown directive' /run/f25.smartd); "
        "echo NOTIFY_X=$(test -x /usr/lib/onemind/smartd-notify && echo yes || echo no); "
        f"env {env} /usr/lib/onemind/smartd-notify; env {env} /usr/lib/onemind/smartd-notify; "
        f"echo LINES_AFTER_TWO=$(wc -l < {feed}); echo HAS_MARKER=$(grep -c {marker} {feed}); "
        "SMARTD_DEVICE=/dev/disk/by-id/x SMARTD_FAILTYPE=Health SMARTD_MESSAGE=bad /usr/lib/onemind/smartd-notify; "
        f"echo LINES_AFTER_BAD=$(wc -l < {feed}); "
        "echo BIND=$(findmnt -no SOURCE /var/lib/smartmontools | head -1 | tr -d ' '); echo DROOT=$(findmnt -no FSROOT /data | head -1); "
        "systemctl start fstrim.service; echo FSTRIM_RC=$?; "
        "ROOT=/dev/$(lsblk -no PKNAME \"$(findmnt -no SOURCE /)\" 2>/dev/null | head -1); echo ROOTDISK=$ROOT; "
        f"{PY} -I /run/f25.py full $ROOT; rm -f /run/f25.py", 300)
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
         # /data starts at "/" on ext4 and "/@" on the btrfs layout (#152): the bind's root is "<that>/state/..."
         "bind_on_data": get("DROOT") not in ("", "?") and f"[{get('DROOT').rstrip('/')}/state/var-lib-smartmontools]" in get("BIND"),
         "fstrim_ran": get("FSTRIM_RC") == "0",
         "housekeeping_200": res.get("hk_code") == 200 and trim.get("enabled") is True
         and bool(trim.get("last_run_at")) and bool(trim.get("next_run_at")),
         "alert_listed": any(a.get("id") == "1700000000-vda-FailedHealthCheck" and marker in a.get("message", "")
                             for a in smart.get("alerts") or []),
         "removable_is_a_list": isinstance(hk.get("removable"), list),
         "eject_kind_listed": "eject" in (res.get("kinds") or []),
         "root_disk_refused": res.get("eject_code") == 409 and eject.get("reason") == "not_removable" and res.get("ops_code") == 404}
    record("F25", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" rootdisk={get('ROOTDISK')} trim={trim} eject={eject} smartd_rc={get('SMARTD_RC')}")
    return marker


def f25_again(vm, tid, marker):
    """F25b (after the reboot) and F25c (after the A/B update): the warning and its state are still there."""
    feed = "/var/lib/smartmontools/onemind-alerts.jsonl"
    _, out = vm.run(
        "cat > /run/f25.py <<'PYEOF'\n" + F25_PY + "\nPYEOF\n"
        "echo BIND=$(findmnt -no SOURCE /var/lib/smartmontools | head -1 | tr -d ' '); echo DROOT=$(findmnt -no FSROOT /data | head -1); "
        f"echo HAS_MARKER=$(grep -c {marker} {feed} 2>&1); "
        "echo STATE smartmontools.service $(systemctl is-enabled smartmontools.service 2>&1 | head -1); "
        f"{PY} -I /run/f25.py read; rm -f /run/f25.py", 200)
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    state = {u: st for u, st in re.findall(r"^STATE (\S+) (\S+)", out, re.M)}
    m = re.findall(r"^RESULT (\{.*\})\s*$", out, re.M)
    res = json.loads(m[-1]) if m else {}
    alerts = ((res.get("hk") or {}).get("smart") or {}).get("alerts") or []
    c = {"bind_mounted": get("DROOT") not in ("", "?") and f"[{get('DROOT').rstrip('/')}/state/var-lib-smartmontools]" in get("BIND"),
         "feed_kept": get("HAS_MARKER") == "1", "host_lists_it": any(marker in a.get("message", "") for a in alerts),
         "smartd_enabled": state.get("smartmontools.service") == "enabled"}
    record(tid, all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()))

def printing(vm, tid, mode):
    """Printing (CRITERIA-FIRSTBOOT.md section 20): FP1 on the first boot, FP2 after the reboot, FP3 after the update.
    test/qemu/print-proof.sh runs in the guest as root (the owner) and prints KEY=value lines; judged here."""
    send_file(vm, "/run/print-proof.sh", open(os.path.join(HERE, "print-proof.sh")).read())
    for source, target in (("../printing/approve.py", "print-approve.py"),
                           ("../../core/tests/soft_authenticator.py", "print-authenticator.py")):
        with open(os.path.join(HERE, source)) as f:
            send_file(vm, f"/run/{target}", f.read())
        vm.run(f"chmod 644 /run/{target}")
    _, out = vm.run(f"sh /run/print-proof.sh {mode}; rm -f /run/print-proof.sh /run/onemind-print-test.ppd "
                    "/run/print-approve.py /run/print-authenticator.py", 420)
    g = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
    mnt = {m: g("MNT_" + m) for m in ("etc_cups", "var_spool_cups", "var_cache_cups", "var_lib_ipp_usb")}
    ctl = g("CTL")
    c = {"packages": g("PKGS") == "ok", "no_browsed": g("BROWSED") == "absent", "tools": g("BINS") == "ok",
         "active": g("ACTIVE") == "active",
         "listening": bool(re.search(r"(^|,)(\*|0\.0\.0\.0|\[::\]|::):631(,|$)", g("LISTEN"))),
         "on_data": g("DROOT") != "" and all(re.search(r"\[" + re.escape(g("DROOT").rstrip("/")) + r"/state/" + n.replace("_", "-") + r"\]$", v)
                                              for n, v in mnt.items()),
         "defaults_off": all(f"_{k}=0" in ctl for k in ("remote_admin", "remote_any", "share_printers", "user_cancel_any")),
         "web_200": g("HTTP_ROOT") == "200", "admin_401": g("HTTP_ADMIN") == "401",
         "direct_denied": g("DIRECT_SUBMIT_RC") not in ("", "0") and g("DIRECT_RELEASE_RC") not in ("", "0"),
         "queued_owner_release": g("QUEUED_OWNER_RELEASE") == "ok",
         "filedevice_off_before": g("FILEDEV_BEFORE") == "0", "printed": g("LP_RC") == "0" and g("OUT_HEAD") == "%PDF"
         and g("OUT_SIZE").isdigit() and int(g("OUT_SIZE")) >= 1000,
         "filedevice_off_after": g("FILEDEV_AFTER") == "0", "finished": "PRINT-PROOF-DONE" in out}
    if mode == "baseline":
        c["non_owner_refused"] = g("NONOWNER_RC") not in ("", "0") and g("NONOWNER_QUEUE") == "absent"
        c["queue_added"] = g("ADD_RC") == "0"
    else:
        c["queue_kept"] = g("QUEUE").startswith("printer OneMindTest ") and g("DESC") == "OneMind QEMU proof queue"
    record(tid, all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" listen={g('LISTEN')!r} mounts={mnt} ctl={ctl!r} out={g('OUT_HEAD')!r}/{g('OUT_SIZE')} queue={g('QUEUE')!r}")


# Boards that ship VA-API (os/boards/<board>/packages-*.txt); F29 runs only on these (CRITERIA-FIRSTBOOT.md section 23: "the x86 box").
VAAPI_BOARDS = ("x86_64-efi", "x86_64-efi-nvidia")

def f29(vm):
    """Step 3: VA-API packages and drivers are on the x86 box and vainfo starts (CRITERIA-FIRSTBOOT.md section 23).
    QEMU has no GPU with VA-API, so no decode profile is listed here; that is proven on real hardware only."""
    d = "/usr/lib/x86_64-linux-gnu/dri"
    _, out = vm.run(
        'for p in vainfo intel-media-va-driver mesa-va-drivers; do echo PKG $p $(dpkg-query -W -f=\'${Status}\' $p 2>&1 | grep -c "install ok installed"); '
        'echo LISTED $p $(grep -c "^$p " /usr/lib/onemind/packages.txt); done; '
        f'for f in iHD radeonsi; do test -f {d}/${{f}}_drv_video.so; echo DRV $f $?; echo MISSING $f $(ldd {d}/${{f}}_drv_video.so 2>&1 | grep -c "not found"); done; '
        'command -v vainfo >/dev/null; echo HAVE=$?; vainfo >/tmp/f29.out 2>&1; echo VAINFO_RC=$?; '
        'echo BANNER=$(grep -c -E "^(vainfo|error):" /tmp/f29.out); head -3 /tmp/f29.out', 120)
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    pk = dict(re.findall(r"^PKG (\S+) (\d+)\s*$", out, re.M))
    ls = dict(re.findall(r"^LISTED (\S+) (\d+)\s*$", out, re.M))
    drv = dict(re.findall(r"^DRV (\S+) (\d+)\s*$", out, re.M))
    miss = dict(re.findall(r"^MISSING (\S+) (\d+)\s*$", out, re.M))
    names = ("vainfo", "intel-media-va-driver", "mesa-va-drivers")
    c = {"packages": all(pk.get(n) == "1" for n in names), "listed": all(ls.get(n) == "1" for n in names),
         "driver_files": drv == {"iHD": "0", "radeonsi": "0"}, "no_missing_libs": miss == {"iHD": "0", "radeonsi": "0"},
         "vainfo_found": get("HAVE") == "0", "vainfo_exit_0_or_1": get("VAINFO_RC") in ("0", "1"),
         "vainfo_banner": get("BANNER") not in ("0", "?")}
    record("F29", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" vainfo_rc={get('VAINFO_RC')} (no GPU in QEMU) out={out.strip()[-160:]!r}")


# What the kernel maps keycode 21 to (the Y key on a US keyboard, Z on a German one): the full table (no -1) has one "keycode  21 = +y +Y ..." line.
CONSOLE_STATE = (r"""echo LAYOUT=$(sed -n 's/^XKBLAYOUT="\(.*\)"$/\1/p' /data/onemind/console/keyboard); """
                 r"""echo UNIT=$(systemctl is-active onemind-console-keyboard.service); """
                 r"""echo KEY21=$(dumpkeys -C /dev/tty0 2>&1 | grep -m1 -E '^keycode +21 *=' | sed -n 's/^keycode *21 *= *+*\([A-Za-z]\).*/\1/p'); echo RAW=$(dumpkeys -C /dev/tty0 2>&1 | grep -m1 -E 'keycode +21 *=|rror' | cut -c1-60 | tr ' ' '_')""")


def console_state(vm):
    _, out = vm.run(CONSOLE_STATE, 60)
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or ["?"])[-1]
    st = (get("LAYOUT"), get("UNIT"), get("KEY21"))
    if st[2] in ("", "?"):
        print(f"  console_state: no key for keycode 21, dumpkeys said {get('RAW')!r}")
    return st


def f30_before(vm):
    """The seed is US and loaded; the owner's file is then changed to de and the unit re-run (judged after the F3 reboot)."""
    _, out = vm.run("echo MASK=$(systemctl is-enabled console-setup.service 2>&1 | head -1)/$(systemctl is-enabled keyboard-setup.service 2>&1 | head -1)", 60)
    mask = (re.findall(r"^MASK=(\S+)", out, re.M) or ["?"])[-1]
    us = console_state(vm)
    vm.run("sed -i 's/^XKBLAYOUT=.*/XKBLAYOUT=\"de\"/' /data/onemind/console/keyboard; sync; "
           "systemctl restart onemind-console-keyboard.service", 60)
    de = console_state(vm)
    return {"masked": mask == "masked/masked", "seed_us": us == ("us", "active", "y"), "applied_de": de == ("de", "active", "z")}, f"mask={mask} us={us} de={de}"


def f30_after(vm, pre):
    c, note = pre
    _, out = vm.run("echo FAILED=$(systemctl --failed --no-legend 2>/dev/null | grep -c -E 'console-setup|keyboard-setup')", 60)
    failed = (re.findall(r"^FAILED=(\d+)", out, re.M) or ["?"])[-1]
    st = console_state(vm)
    c = dict(c, kept_de_after_reboot=st == ("de", "active", "z"), no_failed_setup_units=failed == "0")
    record("F30", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" {note} after_reboot={st} failed_setup_units={failed}")


def f31(vm):
    st = console_state(vm)
    record("F31", st == ("de", "active", "z"), f"after_ab_update layout/unit/keycode21={st}")


HOST_SOCK = "curl -s --unix-socket /run/onemind/host.sock -H 'Content-Type: application/json'"


def host_post(vm, aid, body):
    """POST /v1/operations on the host socket as root (the peer check admits root). Returns (http_code, json)."""
    _, out = vm.run(f"{HOST_SOCK} -o /tmp/f32.out -w 'CODE=%{{http_code}}\\n' -d '{json.dumps(dict(body, action_id=aid))}' http://h/v1/operations; "
                    "echo BODY=$(tr -d '\\n' < /tmp/f32.out); rm -f /tmp/f32.out", 60)
    code = (re.findall(r"^CODE=(\d+)", out, re.M) or ["?"])[-1]
    raw = (re.findall(r"^BODY=(.*)$", out, re.M) or ["{}"])[-1]
    try:
        return code, json.loads(raw)
    except ValueError:
        return code, {}


def host_wait(vm, aid, secs=120):
    """Poll GET /v1/operations/{id} until it is succeeded or failed; the last Op."""
    end, op = time.time() + secs, {}
    while time.time() < end:
        _, out = vm.run(f"echo OP=$({HOST_SOCK} http://h/v1/operations/{aid} | tr -d '\\n')", 30)
        try:
            op = json.loads((re.findall(r"^OP=(.*)$", out, re.M) or ["{}"])[-1])
        except ValueError:
            op = {}
        if op.get("state") in ("succeeded", "failed"):
            break
        time.sleep(2)
    return op


def keyboard_view(vm):
    """GET /v1/keyboard on the host socket: (schema, current layout, variant, seeded, de offers nodeadkeys)."""
    _, out = vm.run(f"echo KB=$({HOST_SOCK} http://h/v1/keyboard | tr -d '\\n')", 60)
    try:
        v = json.loads((re.findall(r"^KB=(.*)$", out, re.M) or ["{}"])[-1])
    except ValueError:
        v = {}
    cur = v.get("current") or {}
    de = next((l for l in v.get("layouts") or [] if l.get("id") == "de"), {})
    return (v.get("schema"), cur.get("layout"), cur.get("variant"), v.get("seeded"),
            any(x.get("id") == "nodeadkeys" for x in de.get("variants") or []))


def key13(vm):
    """The key left of Backspace on a German keyboard: a dead key (dead_acute) on plain de, a plain acute on nodeadkeys."""
    _, out = vm.run(r"""echo KEY13=$(dumpkeys -C /dev/tty0 2>&1 | grep -m1 -E '^keycode +13 *=' | tr -s ' ' '_')""", 60)
    return (re.findall(r"^KEY13=(\S*)\s*$", out, re.M) or ["?"])[-1]


def f32_before(vm):
    """P-11: set-keymap through the host socket (what the gateway does after an owner approves): the layout is written
    to /data and loaded into the console. Run right after f30_before, which left the console on de."""
    c = {}
    _, out = vm.run(f"echo KINDS=$({HOST_SOCK} http://h/v1/status | tr -d '\\n' | grep -o '\"kind\":\"set-keymap\",\"available\":true' | wc -l)", 60)
    c["kind_available"] = (re.findall(r"^KINDS=(\d+)", out, re.M) or ["0"])[-1] == "1"
    c["view_before"] = keyboard_view(vm) == ("onemind.keyboard/v1", "de", "", False, True)
    plain = key13(vm)
    code, op = host_post(vm, "f32-set", {"kind": "set-keymap", "layout": "de", "variant": "nodeadkeys"})
    c["accepted"] = code == "202"
    done = host_wait(vm, "f32-set")
    c["succeeded"] = done.get("state") == "succeeded"
    if not c["succeeded"]:  # evidence for the failure detail only; it changes no verdict
        _, dbg = vm.run("echo DBG-START; systemctl list-jobs --no-pager 2>&1 | head -8; ps -eo pid,args | grep -E 'systemctl|ckbcomp|loadkeys' | grep -v grep | head -5; "
                        "journalctl -u onemind-host.service -u onemind-console-keyboard.service -n 25 --no-pager 2>&1 | cut -c1-200; echo DBG-END", 60)
        print("F32-DEBUG " + dbg.replace("\n", " | ")[-2500:], flush=True)
    st = console_state(vm)
    c["applied"] = st == ("de", "active", "z")
    c["variant_in_file"] = keyboard_view(vm)[1:3] == ("de", "nodeadkeys")
    nodead = key13(vm)
    c["variant_loaded"] = "dead_" in plain and nodead != plain and "dead_" not in nodead
    bad_code, bad = host_post(vm, "f32-bad", {"kind": "set-keymap", "layout": "zz"})
    c["unknown_refused"] = bad_code == "409" and bad.get("reason") == "unknown_layout"
    shape_code, _ = host_post(vm, "f32-shape", {"kind": "set-keymap", "layout": "de;reboot"})
    c["bad_shape_400"] = shape_code == "400"
    c["refusal_changed_nothing"] = keyboard_view(vm)[1:3] == ("de", "nodeadkeys") and console_state(vm) == ("de", "active", "z")
    return c, f"plain13={plain} nodeadkeys13={nodead} op={done.get('state')}/{done.get('message')!r}"


def f32_state(vm):
    return keyboard_view(vm)[1:4], console_state(vm), key13(vm)


def f32_record(pre, mid, final):
    """One verdict: the checks before the reboot, then (when the run got that far) after the F3 reboot and after the F4 update."""
    c, note = pre
    ok = ("de", "nodeadkeys", False)
    if mid is not None:
        c = dict(c, kept_after_reboot=mid[0] == ok and mid[1] == ("de", "active", "z") and mid[2] == pre_key(note))
    if final is not None:
        c = dict(c, kept_after_ab_update=final[0] == ok and final[1] == ("de", "active", "z") and final[2] == mid[2])
    record("F32", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" {note}" + (f" after_reboot={mid}" if mid else "") + (f" after_ab_update={final}" if final else ""))


def pre_key(note):
    return (re.findall(r"nodeadkeys13=(\S+)", note) or ["?"])[0]


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
        vm.mark("F13 disk and admin tools run (Step 2; smartd is no longer masked, F25)"); f13(vm)
        vm.mark("NW1-NW4 NetworkManager: wired DHCP, k3s order, unmanaged k3s links, saved profile")
        netcheck.nw1(vm, record); netcheck.nw2(vm, record); netcheck.nw3(vm, record)
        nw4 = netcheck.nw4_before(vm)
        vm.mark("F34 the box's own monitor shows the desktop by default (kiosk on)"); f34(vm, a.board)
        vm.mark("F15 the owner shell: key-only SSH, tty2 login, no baked password"); f15(vm)
        vm.mark("F16 audio and Bluetooth on the screen boards (Step 3)"); btmark = f16(vm, a.board)
        vm.mark("F14 onemind completion and man pages (#882)"); f14(vm)
        # round-2 integration: the checks of the skipped OS PRs, in ID order (F20 reboots the box, so it is last)
        vm.mark("F17 the clock: timesyncd, tzdata, C.UTF-8"); f17(vm)
        vm.mark("F18 the host applies a time zone (P-04)"); f18(vm)
        vm.mark("F21 renaming the box: hostnamed, the data partition and avahi (P-05)"); f21(vm)
        # the host restarts the gateway a few seconds after a rename (P-05): the next checks need it answering again
        time.sleep(10); http_code(vm, f"{GW}/healthz", timeout=300)
        vm.mark("F23 SSH keys and the SSH switch through the approval queue (P-06)"); f23(vm, token)
        vm.mark("F24 box care: fwupd, fstrim, sensors, rasdaemon, udisks2 without automount (Step 2b)"); box_marker = f24(vm, a.board)
        vm.mark("F25 storage housekeeping: TRIM status, smartd warnings, eject refusal (P-10)"); smart_marker = f25(vm)
        vm.mark("FP1 printing: CUPS, locked down, on /data, prints a test page (Step 3)"); printing(vm, "FP1", "baseline")
        if a.board in VAAPI_BOARDS:
            vm.mark("F29 VA-API packages and vainfo (Step 3; no GPU in QEMU)"); f29(vm)
        vm.mark("F30 console layout from /data, changed to de before the reboot"); pre30 = f30_before(vm)
        vm.mark("F32 set-keymap through the host socket: de nodeadkeys, then a refused layout (P-11)"); pre32 = f32_before(vm)
        mid32 = final32 = None
        vm.mark("NS1-NS3 a wired address change rolls back by itself, a confirmed one sticks (P-08)")
        netset.ns3(vm, record); netset.ns1(vm, record)
        ns2 = netset.ns2_before(vm, record)
        # F20 reboots the box: it stays the last check before F3
        vm.mark("F20 an approved restart reboots the box and the ledger says succeeded (W1)"); f20(vm, token)

        if a.upto in ("F3", "F4"):
            vm.mark("F3 reboot keeps state")
            seg, al, g3 = reboot_and_wait(vm); vm.shell_ready()
            new_toks = TOKEN.findall(vm.since(seg))
            ids3 = ident(vm)
            hz3 = http_code(vm, f"{GW}/healthz", timeout=900)
            if hz3 != "200":
                diagnose(vm, f"healthz={hz3} after reboot")
            listed3 = nodes(vm, token, ids["node_id"])
            same = [n for n in listed3 if n[0] == ids["node_id"]]
            vm.mark("F24b box-care state after the reboot"); f24_again(vm, "F24b", box_marker)
            vm.mark("F25b storage-housekeeping state after the reboot"); f25_again(vm, "F25b", smart_marker)
            vm.mark("F19 the zone survives the reboot (P-04)"); f19(vm)
            record("F3", not new_toks and ids3 == ids and hz3 == "200" and bool(same) and bool(token),
                   f"'{al[:70]}' new_tokens={len(new_toks)} same_ids={ids3 == ids} healthz={hz3} listed={listed3} gate={g3}")
            vm.mark("F30 the layout is still de after the reboot"); f30_after(vm, pre30)
            mid32 = f32_state(vm)
            vm.mark("FP2 the printer and CUPS settings survive the reboot"); printing(vm, "FP2", "again")
            vm.mark("F22 the new name survives the reboot (P-05)"); f22(vm)
            netcheck.nw4_after(vm, record, nw4)
            if a.board in SCREEN_BOARDS:
                f34(vm, a.board, "F34r", after_reboot=True)
            if btmark:
                f16_after(vm, "F16r", btmark)
            netset.ns2_after(vm, record, ns2)
        else:
            netcheck.nw4_after(vm, record, nw4, rebooted=False)
            netset.ns2_after(vm, record, ns2, rebooted=False)

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
            vm.mark("F24c box-care state after the A/B update"); f24_again(vm, "F24c", box_marker)
            vm.mark("F25c storage-housekeeping state after the A/B update"); f25_again(vm, "F25c", smart_marker)
            record("F4", rc_i == 0 and g4 == ("mark-good", "B", "2") and mark == mark2 and len(mark) == 64 and ver2
                   and already and not TOKEN.search(s) and ids4 == ids and hz4 == "200" and bool(same),
                   f"install_rc={rc_i} gate={g4} marker_kept={mark == mark2} version2={ver2} already_configured={already} "
                   f"new_token={bool(TOKEN.search(s))} same_ids={ids4 == ids} healthz={hz4} listed={listed4}")
            vm.mark("F31 the layout is still de after the A/B update"); f31(vm)
            final32 = f32_state(vm)
            vm.mark("FP3 the printer and CUPS settings survive the A/B update"); printing(vm, "FP3", "again")
            if btmark:
                f16_after(vm, "F16u", btmark)
        f32_record(pre32, mid32, final32)
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
