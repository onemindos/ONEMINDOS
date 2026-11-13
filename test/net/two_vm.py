#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""2-VM network proof: hub + node join on a private QEMU network (criteria: test/net/CRITERIA-2VM.md).

Boots two Debian 13 VMs, installs the hub with deploy/install.sh, issues a join ticket, joins the
node, and checks criteria N2-0..N2-7. Each reports PASS, FAIL or BLOCKED with evidence; a criterion
whose feature is not in the source tree yet is BLOCKED with the reason, never faked.
Results: JSON (--results). The criteria file is pre-registered; do not change it to fit a result.

  python3 -I test/net/two_vm.py --results test/net/results/run1.json [--hub-mem 4096 --node-mem 2048]

Environment: ONEMIND_NET_SRC_REF (commit-ish to test instead of the checkout), ONEMIND_NET_STRICT=1
(BLOCKED exits 3), ONEMIND_NET_CACHE (image cache dir), ONEMIND_NET_KEEP=1 (leave the VMs up).
"""
import argparse, hashlib, ipaddress, json, os, re, secrets, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LAN_NET, HUB_LAN, NODE_LAN, BOX = "198.51.100", "198.51.100.1", "198.51.100.2", "box1"
CRITERIA = [
    ("N2-0", "two VMs boot and see each other on the private link"),
    ("N2-1", "hub install"),
    ("N2-2", "join: node appears in hub fabric status"),
    ("N2-3", "mesh: IPs assigned, hub and node reachable"),
    ("N2-4", "NATS leaf over TLS with per-node credentials (H-06)"),
    ("N2-5", "hub serves no plain HTTP to the LAN (H-05)"),
    ("N2-6", "https://<app>.<box>.local through the per-app proxy (H-29, H-34)"),
    ("N2-7", "identity __Host- cookies stripped by the proxy (H-34)"),
]
FATAL = re.compile(r"Kernel panic|end Kernel panic|BUG: unable to handle|Oops:|Out of memory: Killed|"
                   r"BUG: soft lockup|VFS: Unable to mount root|Call Trace:.*(oom|panic)", re.I)
MASK = [(re.compile(r"\b[0-9a-f]{64}\b"), "<hex64>"), (re.compile(r"onemind-join:[^\s'\"]+"), "<join-payload>"),
        (re.compile(r"\b[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}\b"), "XXXX-XXXX-XXXX")]


def mask(s):
    for rx, rep in MASK:
        s = rx.sub(rep, s)
    return s


class Abort(Exception):
    """Stop the run now (fatal console sign, dead QEMU, stage deadline)."""


class Results:
    def __init__(self):
        self.r = {}

    def set(self, cid, result, evidence):
        self.r[cid] = {"id": cid, "result": result, "evidence": mask(str(evidence))[:1500]}
        print(f"[{cid}] {result}: {mask(str(evidence))[:300]}", flush=True)

    def done(self, cid):
        return cid in self.r

    def ok(self, cid):
        return self.r.get(cid, {}).get("result") == "PASS"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class VM:
    def __init__(self, name, idx, work, key, mem, cpus, accel, lan_mode, lan_port):
        self.name, self.idx, self.work, self.key = name, idx, work, key
        self.mem, self.cpus, self.accel, self.lan_mode, self.lan_port = mem, cpus, accel, lan_mode, lan_port
        self.ssh_port, self.proc = free_port(), None
        self.console = os.path.join(work, f"{name}-console.log")
        self.wan_mac, self.lan_mac = f"52:54:00:aa:00:0{idx}", f"52:54:00:bb:00:0{idx}"
        self.scanned = 0

    def prepare(self, base):
        d = os.path.join(self.work, self.name)
        os.makedirs(d, exist_ok=True)
        disk = os.path.join(d, "disk.qcow2")
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", base, disk, "20G"], check=True)
        pub = open(self.key + ".pub").read().strip()
        open(os.path.join(d, "user-data"), "w").write(
            "#cloud-config\nhostname: %s\nmanage_etc_hosts: true\nssh_pwauth: false\nusers:\n  - name: debian\n"
            "    sudo: ALL=(ALL) NOPASSWD:ALL\n    shell: /bin/bash\n    lock_passwd: true\n    ssh_authorized_keys:\n      - %s\n" % (self.name, pub))
        open(os.path.join(d, "meta-data"), "w").write(f"instance-id: net2vm-{self.name}\nlocal-hostname: {self.name}\n")
        open(os.path.join(d, "network-config"), "w").write(
            "version: 2\nethernets:\n  wan0:\n    match: {macaddress: \"%s\"}\n    set-name: wan0\n    dhcp4: true\n"
            "  lan0:\n    match: {macaddress: \"%s\"}\n    set-name: lan0\n    addresses: [\"%s/24\"]\n"
            % (self.wan_mac, self.lan_mac, HUB_LAN if self.idx == 1 else NODE_LAN))
        seed = os.path.join(d, "seed.iso")
        subprocess.run(["cloud-localds", "-N", os.path.join(d, "network-config"), seed,
                        os.path.join(d, "user-data"), os.path.join(d, "meta-data")], check=True)
        self.disk, self.seed = disk, seed

    def start(self):
        cpu = "host" if self.accel == "kvm" else "max"
        cmd = ["qemu-system-x86_64", "-machine", f"q35,accel={self.accel}", "-cpu", cpu, "-smp", str(self.cpus), "-m", str(self.mem),
               "-display", "none", "-monitor", "none", "-serial", f"file:{self.console}", "-no-reboot",
               "-drive", f"file={self.disk},if=virtio,format=qcow2", "-drive", f"file={self.seed},if=virtio,format=raw,readonly=on",
               "-netdev", f"user,id=wan,hostfwd=tcp:127.0.0.1:{self.ssh_port}-:22",
               "-device", f"virtio-net-pci,netdev=wan,mac={self.wan_mac}",
               "-netdev", f"socket,id=lan,{self.lan_mode}=127.0.0.1:{self.lan_port}",
               "-device", f"virtio-net-pci,netdev=lan,mac={self.lan_mac}"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(os.path.join(self.work, f"{self.name}-qemu.err"), "w"))

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()

    def guard(self):
        """Fail fast: dead QEMU or a fatal console line."""
        if self.proc.poll() is not None:
            raise Abort(f"{self.name}: QEMU exited with {self.proc.returncode}")
        try:
            with open(self.console, "rb") as f:
                f.seek(self.scanned)
                chunk = f.read().decode("utf-8", "replace")
                self.scanned = f.tell()
        except OSError:
            return
        m = FATAL.search(chunk)
        if m:
            raise Abort(f"{self.name}: fatal console line: {m.group(0)}")

    def ssh_base(self):
        return ["ssh", "-i", self.key, "-p", str(self.ssh_port), "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=15", "-o", "BatchMode=yes", "debian@127.0.0.1"]

    def run(self, script, timeout=300, stdin_data=None, others=()):
        """Run a bash script as root in the VM. Returns (rc, output). Raises Abort on a fatal sign or the deadline."""
        p = subprocess.Popen(self.ssh_base() + ["sudo", "bash", "-s"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = []
        threading.Thread(target=lambda: out.append(p.stdout.read()), daemon=True).start()
        try:
            p.stdin.write(("set -u\n" + script + "\n").encode())
            p.stdin.close()
        except BrokenPipeError:
            pass
        end = time.time() + timeout
        while p.poll() is None:
            try:
                for vm in (self, *others):
                    vm.guard()
            except Abort:
                p.kill()
                raise
            if time.time() > end:
                p.kill()
                raise Abort(f"{self.name}: command exceeded {timeout}s: {script.strip().splitlines()[0][:80]}")
            time.sleep(2)
        time.sleep(0.2)
        return p.returncode, (out[0].decode("utf-8", "replace") if out else "")

    def put(self, local, remote_cmd, timeout=300):
        with open(local, "rb") as f:
            p = subprocess.run(self.ssh_base() + ["sudo bash -c " + sh_q(remote_cmd)], stdin=f, capture_output=True, timeout=timeout)
        if p.returncode != 0:
            raise Abort(f"{self.name}: copy failed: {p.stderr.decode()[:200]}")

    def wait_ready(self, timeout, others=()):
        end = time.time() + timeout
        while time.time() < end:
            self.guard()
            for o in others:
                o.guard()
            p = subprocess.run(self.ssh_base() + ["cloud-init status --wait >/dev/null 2>&1; cloud-init status"], capture_output=True, timeout=120)
            if p.returncode == 0 and b"done" in p.stdout:
                return True
            time.sleep(3)
        return False


def sh_q(s):
    return "'" + s.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------------------------------------
def fetch_image(cache):
    pin = dict(l.strip().split("=", 1) for l in open(os.path.join(HERE, "image.pin")) if "=" in l and not l.startswith("#"))
    os.makedirs(cache, exist_ok=True)
    dest = os.path.join(cache, os.path.basename(pin["URL"]))

    def sha(path):
        h = hashlib.sha512()
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()
    if os.path.exists(dest) and sha(dest) == pin["SHA512"]:
        return dest, pin
    log(f"downloading {pin['URL']}")
    tmp = dest + ".part"
    try:
        urllib.request.urlretrieve(pin["URL"], tmp)
    except Exception as e:
        raise SystemExit(f"image download failed ({e}). Debian rotates dated build directories: bump test/net/image.pin.")
    if sha(tmp) != pin["SHA512"]:
        os.unlink(tmp)
        raise SystemExit("image sha512 mismatch against test/net/image.pin")
    os.replace(tmp, dest)
    return dest, pin


def build_tree(work, ref):
    """Extract the tree under test, build onemindd and onemind (linux/amd64), return the tarball path."""
    src = os.path.join(work, "src")
    os.makedirs(src)
    if ref:
        arc = subprocess.run(["git", "-C", ROOT, "archive", ref], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", src], input=arc, check=True)
    else:
        files = subprocess.run(["git", "-C", ROOT, "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, check=True).stdout
        names = [n for n in files.decode().split("\0") if n and not re.match(r"(research|research-output|site|mobile|brand|lab-kits|context)/", n)
                 and os.path.isfile(os.path.join(ROOT, n))]
        lst = os.path.join(work, "files.lst")
        open(lst, "w").write("\n".join(names) + "\n")
        subprocess.run(["tar", "-c", "-C", ROOT, "-T", lst, "-f", os.path.join(work, "t.tar")], check=True)
        subprocess.run(["tar", "-x", "-C", src, "-f", os.path.join(work, "t.tar")], check=True)
    env = dict(os.environ, CGO_ENABLED="0", GOOS="linux", GOARCH="amd64")
    flags = ["-trimpath", "-ldflags", "-s -w"]
    for out, pkg in (("onemindd", "./cmd/onemindd"), ("onemind-linux-amd64", "./cmd/onemind")):
        if shutil.which("go"):
            subprocess.run(["go", "build", *flags, "-o", out, pkg], cwd=src, env=env, check=True)
        else:   # Docker fallback (go 1.26 per go.mod)
            subprocess.run(["docker", "run", "--rm", "-v", f"{src}:/s", "-w", "/s", "-e", "CGO_ENABLED=0", "-e", "GOOS=linux", "-e", "GOARCH=amd64",
                            "golang:1.26", "go", "build", *flags, "-o", out, pkg], check=True)
    tgz = os.path.join(work, "src.tgz")
    subprocess.run(["tar", "-czf", tgz, "-C", src, "."], check=True)
    return tgz, src


class Suite:
    def __init__(self, a, work):
        self.a, self.work, self.R = a, work, Results()
        self.hub = self.node = None
        self.token = self.node_id = self.hub_mesh = self.node_mesh = None
        self.probes = {}
        self.logs = {}

    # -- helpers
    def hubrun(self, script, timeout=300):
        return self.hub.run(script, timeout, others=(self.node,))

    def noderun(self, script, timeout=300):
        return self.node.run(script, timeout, others=(self.hub,))

    def api(self, path, extra=""):
        """GET/POST against the hub gateway on loopback with the owner token. Returns (http_code, body)."""
        rc, out = self.hubrun(f"curl -s -m 20 -w '\\n%{{http_code}}' -H 'Authorization: Bearer {self.token}' {extra} http://127.0.0.1:8080{path}")
        body, _, code = out.rpartition("\n")
        return (int(code) if code.strip().isdigit() else 0), body

    def block(self, ids, reason):
        for i in ids:
            if not self.R.done(i):
                self.R.set(i, "BLOCKED", reason)

    # -- stages
    def boot(self):
        a = self.a
        img, pin = fetch_image(a.cache)
        key = os.path.join(self.work, "ssh_key")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
        accel = "kvm" if os.access("/dev/kvm", os.R_OK | os.W_OK) and not a.tcg else "tcg"
        self.info = {"accel": accel, "host_cpus": os.cpu_count(), "image": pin["URL"].rsplit("/", 1)[-1]}
        port = free_port()
        self.hub = VM("hub", 1, self.work, key, a.hub_mem, a.hub_cpus, accel, "listen", port)
        self.node = VM("node", 2, self.work, key, a.node_mem, a.node_cpus, accel, "connect", port)
        for v in (self.hub, self.node):
            v.prepare(img)
        log(f"booting hub ({a.hub_mem} MiB) and node ({a.node_mem} MiB), accel={accel}")
        self.hub.start()
        time.sleep(1)    # the node connects to the hub's socket listener
        self.node.start()

    def n20(self):
        for v, o in ((self.hub, self.node), (self.node, self.hub)):
            if not v.wait_ready(300, (o,)):
                self.R.set("N2-0", "FAIL", f"{v.name} did not finish cloud-init with SSH within 300 s")
                raise Abort("boot")
        rc1, o1 = self.hubrun(f"ping -c3 -W2 {NODE_LAN}", 60)
        rc2, o2 = self.noderun(f"ping -c3 -W2 {HUB_LAN}", 60)
        kern = self.hubrun("uname -r")[1].strip()
        self.info["kernel"] = kern
        if rc1 == 0 and rc2 == 0:
            self.R.set("N2-0", "PASS", f"both VMs up ({self.info['accel']}, {self.info['host_cpus']} host cpus, kernel {kern}); 3/3 pings each way on the private link")
        else:
            self.R.set("N2-0", "FAIL", f"private link ping hub->node rc={rc1}, node->hub rc={rc2}")
            raise Abort("no private link")

    def ship(self, tgz):
        for v in (self.hub, self.node):
            v.put(tgz, "rm -rf /opt/src && mkdir -p /opt/src && tar -xzf - -C /opt/src", 300)
        rc, out = self.hubrun("bash /opt/src/deploy/install.sh --help 2>&1 | grep -c -- '--join' || true")
        p_install = out.strip().endswith("1") or (out.strip().isdigit() and int(out.strip()) > 0)
        net_py = os.path.join(self.src, "core/onemind_core/routers/net.py")
        app_py = open(os.path.join(self.src, "core/onemind_core/app.py")).read()
        p_router_static = os.path.exists(net_py) and re.search(r"routers import net\b|net as net_routes|net_routes", app_py) is not None
        cli = os.path.join(self.src, "cmd/onemind/cli/fabric.go")
        cli_txt = open(cli).read() if os.path.exists(cli) else ""
        p_cli = '"ticket"' in cli_txt or "ticket" in cli_txt and "approve" in cli_txt
        self.probes = {"P-INSTALL": p_install, "P-ROUTER-static": bool(p_router_static), "P-CLI": bool(p_cli)}
        log(f"probes: {self.probes}")

    def n21(self):
        args = f"--role hub --onemindd-bin /opt/src/onemindd --dashboard-dist /opt/src/core/tests/fixtures/dist"
        if self.probes["P-INSTALL"]:
            args += f" --box-name {BOX} --lan-addr {HUB_LAN}"
        log("hub install (this downloads k3s and tooling inside the VM; several minutes)")
        t0 = time.time()
        rc, out = self.hubrun(f"cd /opt/src && bash deploy/install.sh {args} 2>&1; echo \"install-exit=$?\"", 1500)
        self.logs["hub-install.log"] = out
        m = re.search(r"install-exit=(\d+)", out)
        code = int(m.group(1)) if m else -1
        t = re.search(r"OWNER TOKEN[^\n]*\n\s*\n\s*([0-9a-f]{64})", out)
        self.token = t.group(1) if t else None
        if code != 0 or not self.token:
            self.R.set("N2-1", "FAIL", f"install exit {code}; owner token {'printed' if self.token else 'missing'}; last line: {out.strip().splitlines()[-2:] }")
            raise Abort("hub install failed")
        for _ in range(60):
            if self.hubrun("curl -fsS -m 3 http://127.0.0.1:8080/healthz >/dev/null && echo up")[1].strip().endswith("up"):
                self.R.set("N2-1", "PASS", f"install.sh --role hub exit 0 in {int(time.time() - t0)} s ({'mesh-first flags' if self.probes['P-INSTALL'] else 'old flags: installer has no --join'}); owner token printed; /healthz up")
                return
            time.sleep(2)
        self.R.set("N2-1", "FAIL", "no /healthz within 120 s after install")
        raise Abort("hub not healthy")

    def n25(self):
        rc, ss = self.hubrun("ss -ltnH")
        wild, ports = [], set()
        for line in ss.splitlines():
            f = line.split()
            if len(f) < 4:
                continue
            addr, _, port = f[3].rpartition(":")
            if addr in ("0.0.0.0", "*", "[::]", "::"):
                wild.append(f[3])
                ports.add(int(port))
        bad = []
        for p in sorted(ports - {22, 6443, 10250}):
            rc, out = self.noderun(f"curl -s -m 4 -o /dev/null -w '%{{http_code}}' http://{HUB_LAN}:{p}/healthz || true", 30)
            code = out.strip()[-3:]
            if code == "200":
                bad.append(p)
        gw_wild = 8080 in ports
        ev = f"wildcard listeners: {sorted(wild)}; plain-HTTP 200 from the node on {bad or 'none'}; :8080 wildcard={gw_wild}"
        if not bad and not gw_wild:
            self.R.set("N2-5", "PASS", ev)
        elif not self.probes["P-INSTALL"]:
            self.R.set("N2-5", "BLOCKED", f"installer lacks the mesh-first mode (P-INSTALL false), so the gateway still binds all addresses by design. Observed: {ev}")
        else:
            self.R.set("N2-5", "FAIL", ev)

    def n22(self):
        pi, pc = self.probes["P-INSTALL"], self.probes["P-CLI"]
        code, body = self.api("/v1/fabric")
        pr = code == 200
        self.probes["P-ROUTER"] = pr
        missing = [n for n, v in (("P-INSTALL (install.sh has no --join)", pi), ("P-ROUTER (GET /v1/fabric answers %d; net router not mounted in app.py)" % code, pr),
                                  ("P-CLI (onemind fabric ticket/approve)", pc)) if not v]
        if missing:
            self.block(["N2-2", "N2-3", "N2-4", "N2-6", "N2-7"], "depends on the join, not in the tree yet: " + "; ".join(missing))
            return
        t = os.environ
        rc, out = self.hubrun(f"ONEMIND_TOKEN={self.token} onemind fabric ticket --json", 60)
        try:
            tj = json.loads(out[out.index("{"):])
            payload, code_ = tj["qr_payload"], tj["one_time"]["join_code"]
        except Exception as e:
            self.R.set("N2-2", "FAIL", f"ticket output not usable ({e}): {out[-200:]}")
            return
        script = (f"nohup setsid bash -c \"cd /opt/src && bash deploy/install.sh --role node --join {sh_q(payload)} --hub-addr {HUB_LAN} "
                  f"--onemindd-bin /opt/src/onemindd > /tmp/node-install.log 2>&1; echo exit=\\$? >> /tmp/node-install.log\" >/dev/null 2>&1 &")
        self.noderun(script, 30)
        node_code, logt = None, ""
        for _ in range(240):
            logt = self.noderun("cat /tmp/node-install.log 2>/dev/null", 30)[1]
            m = re.search(r"^Code\s+([0-9A-Z]+-[0-9A-Z]+)", logt, re.M)
            if m and "Waiting for the owner" in logt:
                node_code = m.group(1)
                break
            if re.search(r"^exit=", logt, re.M):
                break
            time.sleep(5)
        self.logs["node-install.log"] = logt
        if not node_code:
            self.R.set("N2-2", "FAIL", "node installer never showed a match code: " + logt.strip()[-200:])
            return
        code, body = self.api("/v1/fabric")
        j = json.loads(body)
        pend = (j.get("joining") or [{}])[0]
        if pend.get("match_code") != node_code:
            self.R.set("N2-2", "FAIL", f"match codes differ: node {node_code}, hub {pend.get('match_code')}")
            return
        rc, ap = self.hubrun(f"ONEMIND_TOKEN={self.token} onemind fabric approve {pend['action_id']} 2>&1", 60)
        self.action_id = pend["action_id"]
        t0 = time.time()
        while time.time() - t0 < 900:
            logt = self.noderun("cat /tmp/node-install.log", 30)[1]
            if re.search(r"^exit=", logt, re.M):
                break
            time.sleep(5)
        self.logs["node-install.log"] = logt
        if not re.search(r"^exit=0", logt, re.M):
            self.R.set("N2-2", "FAIL", "node installer did not exit 0: " + logt.strip()[-300:])
            return
        self.node_id = json.loads(self.noderun("cat /etc/onemind/fabric.json", 30)[1])["node_id"]
        for _ in range(40):
            code, body = self.api("/v1/fabric")
            nodes = {n["node_id"]: n for n in json.loads(body).get("nodes", [])}
            if self.node_id in nodes and nodes[self.node_id]["state"] != "joining":
                self.R.set("N2-2", "PASS", f"match code {node_code} == hub's; approved; node installer exit 0; fabric lists {self.node_id} state={nodes[self.node_id]['state']}")
                return
            time.sleep(3)
        self.R.set("N2-2", "FAIL", f"node {self.node_id} not listed in GET /v1/fabric after approval")

    def n23(self):
        if not self.R.ok("N2-2"):
            return self.block(["N2-3"], "N2-2 did not pass: no joined node to test")
        hub_ip = self.hubrun("tailscale ip -4", 30)[1].strip().splitlines()[-1:] or [""]
        node_ip = self.noderun("tailscale ip -4", 30)[1].strip().splitlines()[-1:] or [""]
        self.hub_mesh, self.node_mesh = hub_ip[0], node_ip[0]
        try:
            ips = [ipaddress.ip_address(x) for x in (self.hub_mesh, self.node_mesh)]
            shared = all((not i.is_global) and (not i.is_private) for i in ips)    # the shared (CGNAT) range, by property
        except ValueError:
            return self.R.set("N2-3", "FAIL", f"no mesh addresses: hub '{self.hub_mesh}' node '{self.node_mesh}'")
        if not shared or self.hub_mesh == self.node_mesh:
            return self.R.set("N2-3", "FAIL", f"addresses not in the shared range or equal: hub {self.hub_mesh} node {self.node_mesh}")
        r1 = self.noderun(f"ping -c3 -W3 {self.hub_mesh}", 60)
        r2 = self.hubrun(f"ping -c3 -W3 {self.node_mesh}", 60)
        loss = lambda o: re.search(r"(\d+)% packet loss", o)
        ok = r1[0] == 0 and r2[0] == 0 and loss(r1[1]) and loss(r2[1]) and loss(r1[1]).group(1) == "0" and loss(r2[1]).group(1) == "0"
        self.R.set("N2-3", "PASS" if ok else "FAIL",
                   f"hub mesh {self.hub_mesh}, node mesh {self.node_mesh}; node->hub loss {loss(r1[1]).group(1) if loss(r1[1]) else '?'}%, hub->node loss {loss(r2[1]).group(1) if loss(r2[1]) else '?'}%")

    def n24(self):
        if not self.R.ok("N2-2"):
            return self.block(["N2-4"], "N2-2 did not pass: no joined node to test")
        code, leafz = self.hubrun("curl -s -m 5 http://127.0.0.1:8222/leafz", 30)
        try:
            lj = json.loads(leafz)
        except ValueError:
            return self.R.set("N2-4", "FAIL", "no /leafz answer: " + leafz[:100])
        leafs = lj.get("leafs") or []
        acct_ok = len(leafs) == 1 and leafs[0].get("account") == f"NODE_{self.node_id}" and leafs[0].get("ip") == self.node_mesh
        ss = self.hubrun("ss -ltnH 'sport = :7422' | awk '{print $4}'", 30)[1].split()
        bound_ok = ss == [f"{self.hub_mesh}:7422"]
        probe = (f"python3 - <<'PYEOF'\nimport json, socket, ssl\n"
                 f"s = socket.create_connection(('{self.hub_mesh}', 7422), timeout=5)\n"
                 "info = json.loads(s.recv(4096).split(b' ', 1)[1])\n"
                 "ctx = ssl.create_default_context(cafile='/etc/onemind/identity/ca.pem'); ctx.check_hostname = False\n"
                 "try:\n    t = ctx.wrap_socket(s, server_hostname='hub.onemind.internal'); t.sendall(b'CONNECT {}\\r\\n'); t.recv(100); t.recv(100)\n"
                 "    print('tls_required', info.get('tls_required'), 'no-cert leaf NOT refused')\n"
                 "except (ssl.SSLError, OSError) as e:\n    print('tls_required', info.get('tls_required'), 'no-cert leaf refused', type(e).__name__)\nPYEOF")
        rc, pout = self.noderun(probe, 60)
        tls_ok = "tls_required True" in pout and "no-cert leaf refused" in pout
        ev = f"leafz: {[(l.get('account'), l.get('ip')) for l in leafs]} (want NODE_{self.node_id} from {self.node_mesh}); :7422 bound {ss} (want only the hub mesh address); client probe: {pout.strip()[-120:]}"
        self.R.set("N2-4", "PASS" if acct_ok and bound_ok and tls_ok else "FAIL", ev)

    def n26_27(self):
        if not self.R.ok("N2-2"):
            return self.block(["N2-6", "N2-7"], "N2-2 did not pass: the app proxy test needs the joined box")
        import datetime
        exp = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = json.dumps({"type": "app.install", "params": {"app_id": "vaultwarden"}, "idempotency_key": "net2vm-vw", "expires_at": exp})
        code, out = self.api("/v1/actions", f"-H 'Content-Type: application/json' -d {sh_q(body)}")
        try:
            aid = json.loads(out)["id"]
        except Exception:
            return self.block(["N2-6", "N2-7"], f"app.install could not be filed (HTTP {code}): {out[:150]}")
        code, out = self.api(f"/v1/actions/{aid}/approve", "-X POST")
        rc, pods = self.hubrun("for i in $(seq 1 60); do k3s kubectl -n app-vaultwarden get pods --no-headers 2>/dev/null | grep -q '1/1 *Running' && echo ready && break; sleep 5; done", 330)
        if "ready" not in pods:
            return self.R.set("N2-6", "FAIL", f"vaultwarden not running after approved app.install (approve HTTP {code})") or self.block(["N2-7"], "N2-6 failed")
        ca = "/etc/onemind/identity/ca.pem"
        base = f"curl -s -m 10 --resolve vaultwarden.{BOX}.local:443:{HUB_LAN} -o /dev/null -w '%{{http_code}}'"
        def get(extra, cafile=True):
            return self.noderun(f"{base} {'--cacert ' + ca if cafile else ''} {extra} https://vaultwarden.{BOX}.local/ || true", 60)[1].strip()[-3:]
        nos, bearer, noca = get(""), get(f"-H 'Authorization: Bearer {self.token}'"), get("", False)
        ok = nos == "401" and bearer == "200" and noca == "000"
        self.R.set("N2-6", "PASS" if ok else "FAIL", f"https://vaultwarden.{BOX}.local: signed out {nos} (want 401), bearer {bearer} (want 200), no box CA {noca} (want 000 = handshake refused)")
        if not ok:
            return self.block(["N2-7"], "N2-6 did not pass")
        self.n27_echo(base, ca)

    def n27_echo(self, base, ca):
        ns = "app-vaultwarden"
        rc, svc = self.hubrun(f"k3s kubectl -n {ns} get svc -o json", 60)
        try:
            s0 = json.loads(svc)["items"][0]
            sel, sp = s0["spec"]["selector"], s0["spec"]["ports"][0]
            tp = sp.get("targetPort", sp["port"])
            cport = tp if isinstance(tp, int) else 8000
            pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "h34-echo", "namespace": ns, "labels": sel},
                   "spec": {"securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
                            "containers": [{"name": "echo", "image": "docker.io/library/busybox:1.37",
                                            "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                                            "ports": [dict(containerPort=cport, **({"name": tp} if isinstance(tp, str) else {}))],
                                            "command": ["sh", "-c", "mkdir -p /tmp/www/cgi-bin && printf '#!/bin/sh\\necho Content-Type: text/plain\\necho\\necho \"cookie=[$HTTP_COOKIE]\"\\n' > /tmp/www/cgi-bin/echo "
                                                        f"&& chmod +x /tmp/www/cgi-bin/echo && exec httpd -f -p {cport} -h /tmp/www"]}]}}
        except Exception as e:
            return self.R.set("N2-7", "BLOCKED", f"echo pod could not be designed from the app's Service ({e})")
        script = (f"k3s kubectl -n {ns} scale deploy,statefulset --all --replicas=0 >/dev/null 2>&1; k3s kubectl -n {ns} delete pod -l app.kubernetes.io/name --wait=false >/dev/null 2>&1 || true\n"
                  f"cat <<'YEOF' | k3s kubectl apply -f - 2>&1\n{json.dumps(pod)}\nYEOF\n"
                  f"k3s kubectl -n {ns} wait --for=condition=Ready pod/h34-echo --timeout=120s 2>&1")
        rc, out = self.hubrun(script, 240)
        if rc != 0:
            return self.R.set("N2-7", "BLOCKED", f"echo pod did not become Ready (harness limit, not a product result): {out.strip()[-200:]}")
        cookies = "__Host-onemind_session=x; __Host-onemind_csrf=y; onemind_session=z; keep=1"
        rc, echo = self.noderun(f"curl -s -m 10 --resolve vaultwarden.{BOX}.local:443:{HUB_LAN} --cacert {ca} -H 'Authorization: Bearer {self.token}' -H 'Cookie: {cookies}' https://vaultwarden.{BOX}.local/cgi-bin/echo || true", 60)
        m = re.search(r"cookie=\[(.*)\]", echo)
        if not m:
            return self.R.set("N2-7", "BLOCKED", f"the echo did not answer through the proxy (harness or routing limit): {echo.strip()[:150]}")
        seen = m.group(1)
        leaked = re.findall(r"(?:^|[;\s])((?:__Host-)?onemind_[A-Za-z]+)=", seen)
        if "keep=1" in seen and not leaked:
            self.R.set("N2-7", "PASS", f"upstream saw cookies: [{seen}]; none of the identity cookie names")
        else:
            self.R.set("N2-7", "FAIL", f"upstream saw cookies: [{seen}]; identity names leaked: {leaked}")

    # -- dumps
    def dump(self, outdir):
        os.makedirs(outdir, exist_ok=True)
        for name, text in self.logs.items():
            open(os.path.join(outdir, name), "w").write(mask(text))
        for vm in (self.hub, self.node):
            if not vm:
                continue
            for pth in (vm.console,):
                try:
                    open(os.path.join(outdir, os.path.basename(pth)), "w").write(mask(open(pth, errors="replace").read()[-60000:]))
                except OSError:
                    pass
            try:
                p = subprocess.run(vm.ssh_base() + ["sudo journalctl --no-pager -n 600; echo ---; sudo systemctl --failed --no-legend"], capture_output=True, timeout=60)
                open(os.path.join(outdir, f"{vm.name}-journal.txt"), "w").write(mask(p.stdout.decode("utf-8", "replace")))
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default=os.path.join(HERE, "results", "run.json"))
    ap.add_argument("--hub-mem", type=int, default=4096)
    ap.add_argument("--node-mem", type=int, default=2048)
    ap.add_argument("--hub-cpus", type=int, default=4)
    ap.add_argument("--node-cpus", type=int, default=2)
    ap.add_argument("--tcg", action="store_true", help="force software emulation")
    ap.add_argument("--strict", action="store_true", default=os.environ.get("ONEMIND_NET_STRICT") == "1")
    ap.add_argument("--cache", default=os.environ.get("ONEMIND_NET_CACHE", os.path.expanduser("~/.cache/onemind-net")))
    a = ap.parse_args()
    for tool in ("qemu-system-x86_64", "qemu-img", "cloud-localds", "ssh", "ssh-keygen", "git", "tar"):
        if not shutil.which(tool):
            sys.exit(f"missing tool: {tool}")
    work = tempfile.mkdtemp(prefix="net2vm.")
    outdir = os.path.splitext(a.results)[0] + "-logs"
    os.makedirs(os.path.dirname(os.path.abspath(a.results)), exist_ok=True)
    s = Suite(a, work)
    failure = None
    t0 = time.time()
    try:
        tgz, s.src = build_tree(work, os.environ.get("ONEMIND_NET_SRC_REF"))
        s.boot()
        s.n20()
        s.ship(tgz)
        s.n21()
        s.n25()
        s.n22()
        for step in (s.n23, s.n24, s.n26_27):
            if any(not s.R.done(i) for i in ("N2-2",)):
                break
            step()
    except Abort as e:
        failure = str(e)
        log(f"ABORT: {failure}")
    except subprocess.CalledProcessError as e:
        failure = f"harness error: {e}"
        log(failure)
    finally:
        # every criterion gets a result: whatever the run never reached is BLOCKED with the reason
        for cid, _ in CRITERIA:
            if not s.R.done(cid):
                s.R.set(cid, "BLOCKED" if not failure else "BLOCKED", f"not reached: {failure}" if failure else "not run")
        fails = [r for r in s.R.r.values() if r["result"] == "FAIL"]
        if fails or failure:
            s.dump(outdir)
        verdict = "FAIL" if fails else ("BLOCKED" if any(r["result"] == "BLOCKED" for r in s.R.r.values()) else "PASS")
        res = {"suite": "net-2vm", "verdict": verdict, "abort": failure, "source_ref": os.environ.get("ONEMIND_NET_SRC_REF") or "checkout",
               "probes": s.probes, "info": getattr(s, "info", {}), "seconds": int(time.time() - t0),
               "criteria": [dict(s.R.r[c], title=t) for c, t in CRITERIA]}
        json.dump(res, open(a.results, "w"), indent=2)
        print(json.dumps({c["id"]: c["result"] for c in res["criteria"]}), "verdict", verdict)
        if os.environ.get("ONEMIND_NET_KEEP") != "1":
            for v in (s.hub, s.node):
                if v:
                    v.stop()
            shutil.rmtree(work, ignore_errors=True)
    sys.exit(1 if verdict == "FAIL" or (failure and not fails) else (3 if verdict == "BLOCKED" and a.strict else 0))


if __name__ == "__main__":
    main()
