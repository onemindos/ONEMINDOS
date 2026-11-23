#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Virtual fleet test (#864): one hub and three nodes from the same release image, on the Proxmox lab.

Makes VMs 500-503 from the release's vm-do image, boots them (the hub starts a new OneMind; each node
joins with a QR v2 code through `onemind fabric join`), checks F0-F9 (test/fleet/fleetcore.py CHECKS),
writes a plain report and tears the VMs down. Lab facts come only from the environment (README.md).

  python3 -I test/fleet/fleet.py --release dev-20261122-96333e9 --results DIR [--broken-node-image] [--keep]
"""
import argparse, datetime, json, os, re, shlex, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fleetcore as core  # noqa: E402

REPO = "https://github.com/onemindos/ONEMINDOS/releases/download"
HOST_DIR = "import/onemind-fleet"           # under the snippets storage's folder on the host
GW = "http://127.0.0.1:8080"                # the hub gateway on loopback (plain HTTP stays local, H-05)
TOK = "/data/onemind-fleet/owner-token"     # the disposable hub's owner token; never leaves that VM
CON = "/run/onemind-fleet"                  # serial console logs, on the Proxmox host, for the run's evidence


def user_data(role, pubkey):
    ud = "#cloud-config\n"
    if role == "hub":
        ud += "onemind:\n  role: hub\n  name: Fleet hub\n"
    return ud + f"ssh_authorized_keys:\n  - {pubkey}\n"


def create_cmd(cfg, vm, image, idx):
    vmid, name, _, mib = vm
    st = cfg["ONEMIND_FLEET_STORAGE"]
    return (f"qm create {vmid} --name {name} --ostype l26 --cores 2 --memory {mib} --cpu host "
            f"--scsihw virtio-scsi-single --scsi0 {st}:0,import-from={image},discard=on --boot order=scsi0 "
            f"--net0 virtio,bridge={cfg['ONEMIND_FLEET_BRIDGE']} --serial0 socket --vga serial0 "
            f"--ide2 {st}:cloudinit --citype nocloud --ciuser admin "
            f"--cicustom user={cfg['ONEMIND_FLEET_SNIPPETS']}:snippets/{core.NAME_PREFIX}{vmid}.yaml "
            f"--ipconfig0 ip={cfg['addrs'][idx]},gw={cfg['ONEMIND_FLEET_GW']} --nameserver {cfg['ONEMIND_FLEET_GW']} "
            f"--agent 0 --description 'OneMind virtual fleet (test/fleet), disposable'")


class Fleet:
    def __init__(self, cfg, args):
        self.cfg, self.a = cfg, args
        self.vms = core.plan(hub_mib=args.hub_mem, node_mib=args.node_mem)
        self.ip = {vm[0]: cfg["addrs"][i].split("/")[0] for i, vm in enumerate(self.vms)}
        self.red = core.Redactor([cfg["ONEMIND_FLEET_PVE"], cfg["ONEMIND_FLEET_GW"], cfg["ONEMIND_FLEET_BRIDGE"],
                                  cfg["ONEMIND_FLEET_SNIPPETS_DIR"], *self.ip.values()])
        self.results, self.tmp = {}, tempfile.mkdtemp(prefix="fleet-")
        self.key = os.path.join(self.tmp, "id")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "onemind-fleet", "-f", self.key], check=True)
        self.hostdir = os.path.join(cfg["ONEMIND_FLEET_SNIPPETS_DIR"], HOST_DIR)
        self.node_id = {}

    # -- plumbing
    def log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] {self.red(msg)}", flush=True)

    def set(self, cid, result, evidence):
        self.results[cid] = {"result": result, "evidence": self.red(evidence)[:480]}
        self.log(f"[{cid}] {result}: {evidence}")

    def sh(self, argv, inp=None, timeout=600):
        p = subprocess.run(argv, input=inp, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()

    def pve(self, cmd, timeout=900):
        h = self.cfg["ONEMIND_FLEET_PVE"]
        return self.sh(["ssh", "-o", "BatchMode=yes", h, cmd] if h else ["bash", "-c", cmd], timeout=timeout)

    def guest(self, vmid, cmd, inp=None, timeout=300):
        o = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
             "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10", "-i", self.key]
        if self.cfg["ONEMIND_FLEET_PVE"]:
            o += ["-o", "ProxyJump=" + self.cfg["ONEMIND_FLEET_PVE"]]
        try:
            return self.sh(["ssh", *o, f"admin@{self.ip[vmid]}", cmd], inp=inp, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, "timeout"

    def hub(self, cmd, timeout=120):
        return self.guest(self.vms[0][0], f"sudo bash -c {shlex.quote('T=$(cat ' + TOK + '); ' + cmd)}", timeout=timeout)

    def api(self, path, method="GET", body=None):
        data = f"-H 'Content-Type: application/json' -d {shlex.quote(json.dumps(body))}" if body is not None else ""
        rc, out = self.hub(f'curl -fsS -X {method} -H "Authorization: Bearer $T" {data} {GW}{path}')
        if rc:
            raise RuntimeError(f"{method} {path}: {out[:200]}")
        return json.loads(out)

    def wait(self, what, fn, timeout, every=10):
        t0 = time.time()
        while time.time() - t0 < timeout:
            v = fn()
            if v:
                return v
            time.sleep(every)
        self.log(f"gave up waiting for {what} after {timeout}s")
        return None

    def memory_guard(self, mib):
        rc, out = self.pve("free -g")
        if rc or not core.may_start(out, mib):
            raise core.GuardError(f"host memory would fall under {core.HOST_FLOOR_GIB} GiB: not starting a VM")

    def start(self, vmid, mib):
        """qm start, then record its serial console on the host from the first second (evidence for F1, F9)."""
        self.memory_guard(mib)
        self.pve(f"mkdir -p {CON} && qm start {vmid} && (nohup timeout 4h socat -u "
                 f"UNIX-CONNECT:/var/run/qemu-server/{vmid}.serial0 OPEN:{CON}/{vmid}.log,creat,append "
                 f">/dev/null 2>&1 &)")

    def console(self, vmid, pattern=r"cloud-init|network|eth0|FIRSTBOOT|HEALTH-GATE|FLEET-BAD|panic|GRUB-RAUC"):
        rc, out = self.pve(f"grep -aE {shlex.quote(pattern)} {CON}/{vmid}.log 2>/dev/null | tail -6")
        return out

    def gate(self, vmid):
        return core.gate_results(self.guest(vmid, "sudo cat /data/onemind/gate.log")[1])

    def statuses(self):
        try:
            return core.nodes_list(self.api("/v1/nodes"))
        except Exception as e:  # noqa: BLE001 - a hub that does not answer is "no statuses"
            self.log(f"/v1/nodes: {e}")
            return {}

    def fleet_online(self):
        st = self.statuses()
        return len(st) >= 4 and all(v == "online" for v in st.values()) and st

    # -- F0: guards and the image
    def preflight(self):
        rel = self.a.release
        rc, sums = self.pve(f"mkdir -p {self.hostdir} && cd {self.hostdir} && curl -fsSL {REPO}/{rel}/SHA256SUMS")
        names = dict(reversed(ln.split()) for ln in sums.splitlines() if len(ln.split()) == 2) if rc == 0 else {}
        img = next((n for n in names if n.startswith("onemind-vm-do-") and n.endswith(".qcow2")), None)
        bundle = next((n for n in names if n.endswith("-next.raucb")), None)
        if not img or not bundle:
            raise core.GuardError(f"release {rel}: no vm-do qcow2 and -next.raucb in SHA256SUMS")
        self.image, self.sha, self.bundle, self.bundle_sha = img, names[img], bundle, names[bundle]
        self.version = img[len("onemind-vm-do-"):-len(".qcow2")]
        rc, qml = self.pve("qm list")
        if core.foreign(qml, self.vms):
            raise core.GuardError(f"VM ids {core.foreign(qml, self.vms)} belong to someone else")
        self.teardown()
        busy = [ip for ip in self.ip.values() if self.pve(f"ping -c1 -W1 {ip}")[0] == 0]
        if busy:
            raise core.GuardError(f"{len(busy)} fleet address(es) already answer: pick free ones")
        self.memory_guard(sum(v[3] for v in self.vms))
        path = os.path.join(self.hostdir, img)
        rc, out = self.pve(f"cd {self.hostdir} && {{ [ -s {img} ] || curl -fsSL -o {img} {REPO}/{rel}/{img}; }} "
                           f"&& echo '{self.sha}  {img}' | sha256sum -c -", timeout=3600)
        if rc:
            raise core.GuardError(f"image checksum: {out[-200:]}")
        self.set("F0", "PASS", f"VM ids {[v[0] for v in self.vms]} free; {sum(v[3] for v in self.vms)} MiB within "
                 f"budget; host stays over {core.HOST_FLOOR_GIB} GiB; {img} sha256 OK")
        return path

    # -- F1: create and first boot
    def create(self, path):
        pub = open(self.key + ".pub").read().strip()
        for i, vm in enumerate(self.vms):
            snip = os.path.join(self.cfg["ONEMIND_FLEET_SNIPPETS_DIR"], "snippets", f"{core.NAME_PREFIX}{vm[0]}.yaml")
            self.pve(f"mkdir -p {os.path.dirname(snip)} && cat > {snip} <<'EOF'\n{user_data(vm[2], pub)}EOF")
            rc, out = self.pve(create_cmd(self.cfg, vm, path, i) + f" && qm resize {vm[0]} scsi0 +8G")
            if rc:
                raise RuntimeError(f"qm create {vm[0]}: {out[-300:]}")
            if self.a.broken_node_image and vm[2] == "node":
                # The negative control: the node's copy of the image loses its partition table and boot code.
                self.pve(f"dd if=/dev/zero of=$(pvesm path $(qm config {vm[0]} | sed -n 's/^scsi0: \\([^,]*\\).*/\\1/p')) "
                         f"bs=1M count=8 conv=notrunc,fsync")

    def boot(self):
        hub = self.vms[0][0]
        self.start(hub, self.vms[0][3])
        up = self.wait("hub ssh + owner token", lambda: self.guest(
            hub, f"sudo test -s /run/onemind/owner-token && sudo install -D -m600 /run/onemind/owner-token {TOK} "
                 f"&& curl -fsS {GW}/healthz")[0] == 0, 1200)
        for vm in self.vms[1:]:
            self.start(vm[0], vm[3])
        self.hub_up = bool(up)
        ok = {vm[0]: False for vm in self.vms[1:]}

        def reach():
            ok.update({n: True for n in ok if not ok[n] and self.guest(n, "true")[0] == 0})
            return all(ok.values())
        self.wait("nodes ssh", reach, 600)
        g = self.gate(hub) if up else []
        if up and all(ok.values()) and g and g[0][0] == "committed-boot":
            self.set("F1", "PASS", f"hub up (gate {g[0][0]} slot={g[0][1]} v{g[0][2]}, gateway healthy); "
                     f"3 nodes reachable; all four from {self.image}")
            return True
        dark = [n for n, v in ok.items() if not v] or ([] if up else [hub])
        tail = " / ".join(self.console(dark[0]).splitlines()[-4:]) if dark else ""
        self.set("F1", "FAIL", f"hub up={bool(up)} gate={g[:1]}; nodes reachable={ok}; console of {dark[:1]}: {tail}")
        return False

    # -- F2: join with QR v2 through the CLI
    def join(self, vmid, name):
        """The image's own enrolment flow, as the setup wizard runs it: `onemind-firstboot configure --role
        worker --join-code ...` saves the code (0600) and starts onemind-fabric-join.service, which runs
        `onemind fabric join --code-file` with ONEMIND_ETC_DIR on /data (the root is read-only)."""
        t = self.api("/v1/fabric/join-tickets", "POST", {"role": "worker", "expires_in_s": 900})
        hub_ip, tried = self.ip[self.vms[0][0]], []
        for qr in (t.get("qr_payload_v2"), t.get("qr_payload")):   # v2 first; the code is not used until it validates
            if not qr or not qr.startswith("onemind-join:v"):
                continue
            ver = qr[len("onemind-join:"):].split("?")[0]
            rc, out = self.guest(vmid, f"sudo /usr/lib/onemind/onemind-firstboot configure --role worker --name {name} "
                                       f"--join-code {shlex.quote(qr)} --hub-addr {hub_ip}")
            tried.append(f"{ver}" + (f" refused: {out[-90:]}" if rc else ""))
            if rc == 0:
                break
        else:
            return False, "the image refused every QR the hub minted (" + "; ".join(tried) + ")"
        jlog = lambda: self.guest(vmid, "sudo journalctl -u onemind-fabric-join -o cat --no-pager")[1]
        node_code = self.wait(f"{name} match code", lambda: (re.findall(r"Code\s+(\S+)\s+<-", jlog()) or [None])[-1], 300, 5)
        pend = self.wait(f"{name} pending join", lambda: core.pending_join(self.api("/v1/fabric"), name), 300, 5)
        if not node_code or not pend:
            errs = [ln.split("join: ", 1)[-1] for ln in jlog().splitlines() if "join: onemind:" in ln]
            return False, f"code={node_code} pending={bool(pend)}: {(errs or [jlog()[-120:]])[-1][:160]}"
        if pend.get("match_code") != node_code:
            return False, f"match codes differ: node {node_code}, hub {pend.get('match_code')}"
        rc, out = self.hub(f"ONEMIND_TOKEN=$T onemind fabric approve {shlex.quote(pend['action_id'])} --hub {GW}")
        done = self.wait(f"{name} join done", lambda: "joined the hub" in jlog() or "Done. This node is a" in jlog(), 900)
        self.node_id[vmid] = pend.get("node_id")
        return bool(done), (f"QR {'; '.join(tried)}; code {node_code} matched; approve rc={rc}; joined={bool(done)}"
                            + ("" if done else f": {jlog()[-160:]}"))

    def joins(self, booted):
        if not getattr(self, "hub_up", False):
            return self.set("F2", "BLOCKED", "the hub never came up, so no join could be tried (F1)")
        if not booted:
            return self.set("F2", "FAIL", "a node never came up on its image, so it could not join (F1)")
        ev, ok = [], True
        for vmid, name, *_ in self.vms[1:]:
            j, why = self.join(vmid, name)
            ok &= j
            ev.append(f"{name}: {why}")
        self.set("F2", "PASS" if ok else "FAIL", "; ".join(ev))

    # -- F3-F6: one system
    def one_system(self):
        st = self.wait("all four online", self.fleet_online, 300) or self.statuses()
        good = len(st) >= 4 and all(v == "online" for v in st.values())
        self.set("F3", "PASS" if good else "FAIL", f"/v1/nodes: {sorted(st.values())}")
        fab = self.api("/v1/fabric")
        links = {n.get("hostname"): n.get("leaf_link") for n in fab.get("nodes", [])}
        self.set("F4", "PASS" if len(links) >= 3 and set(links.values()) == {"up"} else "FAIL", f"leaf links: {links}")
        rc, page = self.hub("curl -ksS -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/ && echo && "
                            "curl -ksS -H \"Authorization: Bearer $T\" https://127.0.0.1:8443/v1/nodes")
        lines = page.splitlines()
        seen = core.nodes_list(json.loads(lines[1])) if rc == 0 and len(lines) > 1 else {}
        self.set("F5", "PASS" if lines[:1] and lines[0][:1] in "23" and len(seen) >= 4 else "FAIL",
                 f"dashboard HTTP {lines[:1]}; HTTPS node list shows {len(seen)}")
        rc, kn = self.hub("KUBECONFIG=/run/k3s/k3s.yaml k3s kubectl get nodes --no-headers 2>&1 | grep -cw Ready")
        ready = int(kn) if kn.isdigit() else 0
        if ready < 4:
            return self.set("F6", "BLOCKED", f"k3s sees {ready} ready node(s): image workers run no k3s agent yet "
                            "(os firstboot leaves ONEMIND_FABRIC_K3S off), so nothing can be scheduled on a node")
        app = os.environ.get("ONEMIND_FLEET_APP", "")
        if not app:
            return self.set("F6", "BLOCKED", "set ONEMIND_FLEET_APP to an app whose placement is 'elsewhere'")
        where = self.api(f"/v1/apps/{app}/placement")
        exp = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
        act = self.api("/v1/actions", "POST", {"type": "app.install", "params": {"app_id": app},
                                               "idempotency_key": f"fleet-{app}-{int(time.time())}", "expires_at": exp})
        self.api(f"/v1/actions/{act['id']}/approve", "POST")
        names = {self.node_id.get(v): n for v, n, *_ in self.vms}       # node_id -> hostname (the k3s node name)
        node = names.get(where.get("node_id"))
        on = self.wait(f"{app} on {node}", lambda: node and node in self.hub(
            f"KUBECONFIG=/run/k3s/k3s.yaml k3s kubectl get pods -A -o wide 2>/dev/null | grep -i {shlex.quote(app)} | grep -w Running")[1], 900)
        self.set("F6", "PASS" if on else "FAIL", f"{app}: placement {where.get('verdict')} -> {node}; running there={bool(on)}")

    # -- F7: failover
    def failover(self):
        vmid, name = self.vms[3][0], self.vms[3][1]
        nid = self.node_id.get(vmid)
        self.pve(f"qm stop {vmid}")
        t0 = time.time()
        down = self.wait(f"{name} offline", lambda: self.statuses().get(nid) == "offline", 600, 5)
        took = int(time.time() - t0)
        others = {k: v for k, v in self.statuses().items() if k != nid}
        self.start(vmid, self.vms[3][3])
        back = self.wait(f"{name} back online", lambda: self.statuses().get(nid) == "online", 900)
        good = bool(down) and core.offline_in_time(took) and set(others.values()) == {"online"} and bool(back)
        self.set("F7", "PASS" if good else "FAIL", f"{name} offline after {took}s (limit {core.OFFLINE_AFTER_S}+"
                 f"{core.OFFLINE_SLACK_S}s); others stayed {sorted(set(others.values()))}; no workload on workers to move "
                 f"(F6); rejoined={bool(back)}")

    # -- F8: staged update, F9: forced-bad rollback
    def install(self, vmid, break_it=False):
        url = f"{REPO}/{self.a.release}/{self.bundle}"
        brk = ""
        if break_it:   # the T6 fixture's broken init (test/qemu/bad-boot-init), written into the slot just installed
            brk = ("d=$(rauc status --output-format=json | python3 -c 'import json,sys; s=json.load(sys.stdin); "
                   "p=s[\"boot_primary\"]; print([v for x in s[\"slots\"] for k,v in x.items() if k==p][0][\"device\"])') "
                   "&& m=/run/onemind-fleet-bad && mkdir -p $m && mount $d $m && rm -f $m/sbin/init && "
                   "printf '#!/bin/sh\\necho \"<2>FLEET-BAD: broken init\" >/dev/kmsg; exit 1\\n' >$m/sbin/init "
                   "&& chmod 755 $m/sbin/init && umount $m && ")
        cmd = (f"mkdir -p /data/onemind-fleet && cd /data/onemind-fleet && {{ [ -s b.raucb ] || curl -fsSL -o b.raucb {url}; }} "
               f"&& echo '{self.bundle_sha}  b.raucb' | sha256sum -c - && rauc install b.raucb && {brk}"
               f"systemd-run --on-active=5s /usr/bin/systemctl reboot")    # the reboot comes after ssh returns
        return self.guest(vmid, f"sudo bash -c {shlex.quote(cmd)}", timeout=1800)

    def settled(self, vmid, n_before):
        g = self.gate(vmid)
        return len(g) > n_before and g[-1][0] in ("mark-good", "fell-back", "mark-bad", "unhealthy") and g

    def staged_update(self):
        want = self.version + "-next"
        ev, ok = [], True
        for vmid, name, *_ in [*self.vms[1:], self.vms[0]]:          # nodes first, the hub last
            before = len(self.gate(vmid))
            rc, out = self.install(vmid)
            g = rc == 0 and self.wait(f"{name} gate", lambda v=vmid: self.settled(v, before), 1500, 15)
            last = g[-1] if g else None
            good = bool(last) and last[0] == "mark-good" and last[2] == want
            ev.append(f"{name}: {last[0] + ' slot=' + last[1] if last else 'install rc=' + str(rc) + ' ' + out[-80:]}")
            ok &= good and bool(self.wait("fleet online", self.fleet_online, 600))
            if not ok:
                break                                               # a staged rollout stops at the first failure
        self.set("F8", "PASS" if ok else "FAIL", f"to {want}: " + "; ".join(ev))
        return ok

    def rollback(self):
        vmid, name = self.vms[2][0], self.vms[2][1]
        before = len(self.gate(vmid))
        rc, out = self.install(vmid, break_it=True)
        g = rc == 0 and self.wait(f"{name} fall back", lambda: self.settled(vmid, before), 2400, 20)
        last = g[-1] if g else None
        others = all((self.gate(v) or [("none",)])[-1][0] == "mark-good" for v, *_ in self.vms if v != vmid)
        online = self.wait("fleet online", self.fleet_online, 900)
        good = bool(last) and last[0] == "fell-back" and others and bool(online)
        self.set("F9", "PASS" if good else "FAIL", f"{name}: {last or 'install rc=' + str(rc) + ' ' + out[-80:]}; "
                 f"others still mark-good={others}; all four online={bool(online)}")

    def teardown(self):
        rc, qml = self.pve("qm list")
        for vmid in core.ours(qml):
            self.pve(f"qm stop {vmid} --skiplock 1 >/dev/null 2>&1; qm destroy {vmid} --purge 1 --destroy-unreferenced-disks 1")
            self.pve(f"rm -f {self.cfg['ONEMIND_FLEET_SNIPPETS_DIR']}/snippets/{core.NAME_PREFIX}{vmid}.yaml {CON}/{vmid}.log")

    def run(self):
        steps = [lambda b: self.joins(b), lambda b: self.one_system(), lambda b: self.failover(),
                 lambda b: self.staged_update() and self.rollback()]
        # One fleet run at a time on a lab host: a lock folder there (a lock older than 6 h is a dead run's).
        lock = "/run/lock/onemind-fleet"
        if self.pve(f"mkdir {lock} 2>/dev/null || {{ [ $(( $(date +%s) - $(stat -c %Y {lock}) )) -gt 21600 ] "
                    f"&& touch {lock}; }}")[0]:
            return self.set("F0", "FAIL", "guard: another fleet run holds the lab lock")
        try:
            path = self.preflight()
            self.create(path)
            booted = self.boot()
            for i, step in enumerate(steps):
                if i and not all(self.results.get(c, {}).get("result") == "PASS" for c in ("F1", "F2")):
                    break
                step(booted)
        except core.GuardError as e:
            self.set("F0", "FAIL", f"guard: {e}")
        except Exception as e:  # noqa: BLE001 - recorded in the report, the VMs are still torn down
            self.log(f"run stopped: {type(e).__name__}: {e}")
        finally:
            if not self.a.keep:
                self.teardown()
            self.pve(f"rmdir {lock}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--release", required=True, help="GitHub release tag carrying the vm-do image and -next bundle")
    ap.add_argument("--results", default=os.path.join(HERE, "results"))
    ap.add_argument("--broken-node-image", action="store_true", help="negative control: the join check must FAIL")
    ap.add_argument("--keep", action="store_true", help="leave the VMs up (they are torn down at the next run)")
    ap.add_argument("--hub-mem", type=int, default=4096)
    ap.add_argument("--node-mem", type=int, default=2048)
    a = ap.parse_args()
    try:
        cfg = core.parse_env(os.environ)
        f = Fleet(cfg, a)
    except core.GuardError as e:
        print(f"fleet: {e} (see test/fleet/README.md)", file=sys.stderr)
        return 2
    t0 = time.time()
    started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    f.run()
    os.makedirs(a.results, exist_ok=True)
    hist = os.path.join(a.results, "history.jsonl")
    v = core.verdict(f.results, a.broken_node_image)
    sha = getattr(f, "sha", "")
    lines = open(hist).read().splitlines() if os.path.exists(hist) else []
    if not a.broken_node_image:
        lines.append(json.dumps({"verdict": v, "image_sha256": sha, "started": started}))
        with open(hist, "w") as h:
            h.write("\n".join(lines) + "\n")
    run = {"verdict": v, "image": getattr(f, "image", "?"), "image_sha256": sha or "?" * 16, "started": started,
           "minutes": round((time.time() - t0) / 60, 1), "mode": "broken-node-image" if a.broken_node_image else "normal",
           "streak": core.streak(lines, sha), "results": f.results}
    stamp = started.replace(":", "")
    with open(os.path.join(a.results, f"fleet-{stamp}.json"), "w") as h:
        json.dump(run, h, indent=2)
    with open(os.path.join(a.results, f"fleet-{stamp}.md"), "w") as h:
        h.write(core.report(run))
    print(core.report(run))
    return 0 if v in ("GREEN", "NEGATIVE-OK") else 1


if __name__ == "__main__":
    sys.exit(main())
