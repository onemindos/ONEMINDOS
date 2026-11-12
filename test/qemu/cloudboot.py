#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, cloud images (C0-C6). Criteria: test/qemu/CRITERIA-CLOUD.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's console reader.

Boots the artifact a cloud imports (raw, disk.raw in a tar.gz, fixed VHD, qcow2), unmodified, through
a copy-on-write overlay 8 GiB larger, with a NoCloud seed shaped like that cloud's metadata. The guest
is driven like a cloud instance: serial console, SSH as `admin` (throwaway key made here), HTTP to the
gateway, all through ports forwarded on 127.0.0.1 (user networking, restrict=on). Tools container:

  python3 -I cloudboot.py --cloud aws --image-dir /out/image-cloud-aws --work DIR --log serial.log \
      [--tests C0,C1,C2,C3,C4,C5,C6] [--results r.json]
"""
import argparse, hashlib, importlib.util, json, os, platform, re, secrets, shutil, socket, subprocess, sys
import tarfile, time, urllib.error, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(os.path.dirname(HERE))
MAC = "52:54:00:4f:4d:01"
GIB = 1 << 30
GROW = 8 * GIB
CONFIGURED = r"ONEMIND-FIRSTBOOT: configured role=hub source=nocloud[^\n]*"
ALREADY = r"ONEMIND-FIRSTBOOT: already configured role=hub[^\n]*"
WIZARD = r"ONEMIND-FIRSTBOOT: not configured; waiting for the setup wizard[^\n]*"
TOKEN = re.compile(r"ONEMIND OWNER TOKEN: ([0-9a-f]{64})")
GATE = r"HEALTH-GATE: \S+ RESULT (\S+) slot=(\w) version=(\S+)"

# CRITERIA-CLOUD.md §3. `artifact` is the file name suffix; `fmt` the qemu-img format of the bytes
# booted; `key_in` where that cloud delivers the SSH key; `net` the network-config shape.
PROFILES = {
    "aws": dict(artifact="raw", fmt="raw", firmware="ovmf", machine="q35", bus="nvme",
                datasources=["Ec2", "NoCloud", "None"], key_in="meta-data", net=None),
    "gcp": dict(artifact="tar.gz", fmt="raw", firmware="ovmf", machine="q35", bus="virtio-scsi",
                datasources=["GCE", "NoCloud", "None"], key_in="meta-data", net="gce-mtu"),
    "azure": dict(artifact="vhd", fmt="vpc", firmware="ovmf", machine="q35", bus="virtio-scsi",
                  datasources=["Azure", "NoCloud", "None"], key_in="meta-data", net=None),
    "hetzner": dict(artifact="raw", fmt="raw", firmware="seabios", machine="pc", bus="virtio-scsi",
                    datasources=["Hetzner", "NoCloud", "None"], key_in="meta-data", net="hetzner-v1"),
    "proxmox": dict(artifact="qcow2", fmt="qcow2", firmware="ovmf", machine="q35", bus="virtio-scsi",
                    datasources=["NoCloud", "ConfigDrive", "None"], key_in="user-data", net="proxmox-v1"),
}
REQUIRED = {"C0", "C1", "C2", "C3", "C4"}            # §5: plus C5 on hetzner, C6 on aws
EXTRA = {"hetzner": {"C5"}, "aws": {"C6"}}
HETZNER_V6 = "2001:db8::1/64"                       # RFC 3849 documentation prefix


def expect_from(vm, pattern, start, timeout):
    """vm.expect, but searching from a known point of the console log (a gate line may come before
    or after the first-boot line)."""
    vm.pos = start
    return vm.expect(pattern, timeout)


def default_tests(cloud):
    return sorted(REQUIRED | EXTRA.get(cloud, set()))


def instance_id(cloud, rnd):
    """An instance id in the cloud's own format; rnd is 16 random bytes."""
    n = int.from_bytes(rnd, "big")
    return {"aws": "i-%017x" % (n % 16 ** 17),
            "gcp": str(10 ** 18 + n % (9 * 10 ** 18)),
            "azure": str(uuid.UUID(bytes=rnd)),
            "hetzner": str(10 ** 7 + n % (9 * 10 ** 7)),
            "proxmox": hashlib.sha1(rnd).hexdigest()}[cloud]


def seed_files(cloud, pubkey, iid, role=True):
    """meta-data, user-data and (if the cloud has one) network-config of the emulating NoCloud seed."""
    p = PROFILES[cloud]
    md = [f"instance-id: {iid}", f"local-hostname: onemind-{cloud}"]
    if p["key_in"] == "meta-data":
        md += ["public-keys:", f"  - {json.dumps(pubkey)}"]
    ud = ["#cloud-config"]
    if role:
        ud += ["onemind:", "  role: hub", f"  name: {json.dumps('OneMind ' + cloud)}"]
    if p["key_in"] == "user-data":
        ud += ["ssh_authorized_keys:", f"  - {json.dumps(pubkey)}"]
    files = {"meta-data": "\n".join(md) + "\n", "user-data": "\n".join(ud) + "\n"}
    if p["net"] == "gce-mtu":
        files["network-config"] = ("version: 2\nethernets:\n  nic0:\n"
                                   f"    match: {{macaddress: \"{MAC}\"}}\n    dhcp4: true\n    mtu: 1460\n")
    elif p["net"] == "hetzner-v1":
        files["network-config"] = ("version: 1\nconfig:\n  - type: physical\n    name: eth0\n"
                                   f"    mac_address: \"{MAC}\"\n    subnets:\n"
                                   "      - {type: dhcp, ipv4: true}\n"
                                   f"      - {{type: static, address: \"{HETZNER_V6}\", gateway: \"fe80::1\", ipv6: true}}\n")
    elif p["net"] == "proxmox-v1":
        files["network-config"] = ("version: 1\nconfig:\n  - type: physical\n    name: eth0\n"
                                   f"    mac_address: \"{MAC}\"\n    subnets:\n      - type: dhcp4\n")
    return files


def qemu_cmd(cloud, disk, seed, extra_disks, ports, accel, cpu):
    """The QEMU command line for a cloud profile (no firmware drives: added by the VM)."""
    p = PROFILES[cloud]
    qemu = ["qemu-system-x86_64", "-machine", p["machine"], "-accel", accel, "-cpu", cpu, "-smp", "4", "-m", "4096",
            "-nodefaults", "-display", "none", "-vga", "none",
            "-nic", f"user,model=virtio-net-pci,mac={MAC},restrict=on,"
                    f"hostfwd=tcp:127.0.0.1:{ports['ssh']}-:22,hostfwd=tcp:127.0.0.1:{ports['http']}-:8080",
            "-drive", f"if=none,id=root,format=qcow2,cache=writeback,file={disk}"]
    if p["bus"] == "nvme":
        qemu += ["-device", "nvme,drive=root,serial=onemindroot,bootindex=0"]
    else:
        qemu += ["-device", "virtio-scsi-pci,id=scsi0", "-device", "scsi-hd,drive=root,bus=scsi0.0,bootindex=0"]
    for i, d in enumerate([seed] + list(extra_disks)):
        qemu += ["-drive", f"if=none,id=x{i},format=raw,readonly=on,file={d}", "-device", f"virtio-blk-pci,drive=x{i}"]
    return qemu + ["-serial", "stdio", "-monitor", "none"]


def artifact(image_dir, cloud):
    suf = PROFILES[cloud]["artifact"]
    hits = sorted(f for f in os.listdir(image_dir)
                  if re.fullmatch(rf"onemind-cloud-{cloud}-[^/]+\.{re.escape(suf)}", f) and "-next" not in f)
    if len(hits) != 1:
        raise RuntimeError(f"expected one *.{suf} in {image_dir}, found {hits}")
    return os.path.join(image_dir, hits[0])


# ------------------------------------------------------------------ runtime (tools container)
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def sh(*cmd, **kw):
    return subprocess.run(list(cmd), capture_output=True, text=True, **kw)


def sha256(path=None, stream=None):
    h = hashlib.sha256()
    f = stream or open(path, "rb")
    for buf in iter(lambda: f.read(1 << 20), b""):
        h.update(buf)
    if not stream:
        f.close()
    return h.hexdigest()


def c0(cloud, image_dir):
    c = {}
    r = sh("sha256sum", "-c", "SHA256SUMS", cwd=image_dir)
    c["sha256sums_ok"] = r.returncode == 0 and "FAILED" not in r.stdout
    art = artifact(image_dir, cloud)
    if cloud in ("aws", "hetzner"):
        c["raw_16GiB"] = os.path.getsize(art) == 16 * GIB
        xz = subprocess.Popen(["xz", "-dc", art + ".xz"], stdout=subprocess.PIPE)
        c["xz_same_bytes"] = sha256(stream=xz.stdout) == sha256(art) and xz.wait() == 0
    elif cloud == "gcp":
        with tarfile.open(art) as t:
            m = t.getmembers()
        c["one_member_disk_raw"] = [x.name for x in m] == ["disk.raw"]
        c["whole_GiB"] = bool(m) and m[0].size % GIB == 0
    elif cloud == "azure":
        # A fixed VHD has its only footer at the end, so qemu-img never auto-probes it (it says "raw");
        # -f vpc makes qemu-img open it as VHD, which fails unless the footer is valid.
        r = sh("qemu-img", "info", "-f", "vpc", "--output=json", art)
        info = json.loads(r.stdout) if r.returncode == 0 else {}
        vs = info.get("virtual-size", 0)
        c["vpc"] = info.get("format") == "vpc"
        with open(art, "rb") as f:
            f.seek(-512, 2)
            foot = f.read(512)
        c["footer_conectix_fixed"] = foot[:8] == b"conectix" and int.from_bytes(foot[60:64], "big") == 2
        c["fixed_footer"] = os.path.getsize(art) == vs + 512
        c["whole_MiB"] = vs > 0 and vs % (1 << 20) == 0
    elif cloud == "proxmox":
        c["qcow2_check_clean"] = sh("qemu-img", "check", art).returncode == 0
    record("C0", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()))
    return art


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(port, path, token=None, timeout=10):
    """(status, body) or (None, error) when no HTTP response came."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (OSError, urllib.error.URLError) as e:
        return None, repr(e).encode()


def wait_http(port, path, token=None, timeout=900):
    end, last = time.time() + timeout, (None, b"")
    while time.time() < end:
        last = http(port, path, token)
        if last[0] == 200:
            break
        time.sleep(5)
    return last


class Run:
    def __init__(self, a, battery):
        self.a, self.battery, self.p = a, battery, PROFILES[a.cloud]
        self.key = os.path.join(a.work, "id_ed25519")
        self.ports = {"ssh": free_port(), "http": free_port()}
        self.logf = open(a.log, "a")
        self.vm = None

    def prepare(self, base, tag, role=True, extra=()):
        a = self.a
        if not os.path.exists(self.key):
            sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "onemind-cloudboot", "-f", self.key, check=True)
        disk = os.path.join(a.work, f"{tag}.qcow2")
        if os.path.exists(disk):
            os.remove(disk)
        size = int(json.loads(sh("qemu-img", "info", "--output=json", "-f", self.p["fmt"], base).stdout)["virtual-size"])
        sh("qemu-img", "create", "-q", "-f", "qcow2", "-F", self.p["fmt"], "-b", os.path.abspath(base), disk,
           str(size + GROW), check=True)
        self.iid = instance_id(a.cloud, secrets.token_bytes(16))
        files = seed_files(a.cloud, open(self.key + ".pub").read().strip(), self.iid, role)
        d = os.path.join(a.work, f"seed-{tag}")
        os.makedirs(d, exist_ok=True)
        for n, t in files.items():
            open(os.path.join(d, n), "w").write(t)
        seed = os.path.join(a.work, f"seed-{tag}.img")
        if os.path.exists(seed):
            os.remove(seed)
        sh("mkfs.fat", "-n", "CIDATA", "-C", seed, "2048", check=True)
        sh("mcopy", "-i", seed, *[os.path.join(d, n) for n in files], "::/", check=True)
        self.disk_size = size + GROW
        return disk, seed, list(extra)

    def boot(self, disk, seed, extra):
        b = self.battery
        vm = b.VM("vm-do" if self.p["firmware"] == "seabios" else "x86_64-efi", self.a.work, self.logf, self.a.work)
        cmd = qemu_cmd(self.a.cloud, disk, seed, extra, self.ports, vm.accel, vm.cpu)
        if vm.cfg["code"]:
            i = cmd.index("-nodefaults")
            cmd[i:i] = ["-drive", f"if=pflash,format=raw,readonly=on,file={vm.cfg['code']}",
                        "-drive", f"if=pflash,format=raw,file={vm.vars}"]
        vm.mark(f"QEMU START {' '.join(cmd)}")
        vm.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        import threading
        threading.Thread(target=vm._reader, daemon=True).start()
        self.vm = vm
        return vm

    def ssh(self, cmd, timeout=300):
        r = subprocess.run(["ssh", "-q", "-i", self.key, "-p", str(self.ports["ssh"]), "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                            "-o", "ConnectTimeout=20", "admin@127.0.0.1", cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr

    def ssh_ready(self, timeout=900):
        end = time.time() + timeout
        while time.time() < end:
            try:
                rc, out = self.ssh("sudo -n true && echo SSH-OK", 60)
                if rc == 0 and "SSH-OK" in out:
                    return True
            except subprocess.TimeoutExpired:
                pass
            time.sleep(10)
        return False

    def node_id(self):
        _, out = self.ssh("echo ID=$(sudo cat /data/onemind/etc/node-id); "
                          "echo TOK=$(sudo sha256sum /data/onemind/gateway/tokens.yaml | cut -c1-64)")
        get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or [""])[-1]
        return get("ID"), get("TOK")

    def listed(self, token, nid, timeout=600):
        end, rows = time.time() + timeout, []
        while time.time() < end:
            code, body = http(self.ports["http"], "/v1/nodes", token)
            if code == 200:
                try:
                    rows = [(n["node_id"], n["role"], n["status"]) for n in json.loads(body)]
                except (ValueError, KeyError, TypeError):
                    rows = []
                if any(r[0] == nid for r in rows):
                    break
            time.sleep(5)
        return rows

    def datasource_list(self):
        """The image's configured order: /etc/cloud/cloud.cfg merged with cloud.cfg.d (what ds-identify
        reads). /run/cloud-init/cloud.cfg, ds-identify's per-boot pick, is reported, not compared."""
        _, out = self.ssh("sudo python3 -I -c 'import json; from cloudinit import util; "
                          "print(\"DSL=\" + json.dumps(util.read_conf_with_confd(\"/etc/cloud/cloud.cfg\")"
                          ".get(\"datasource_list\")))'; echo PICK=$(grep -h datasource_list /run/cloud-init/cloud.cfg)")
        m = re.findall(r"^DSL=(.*)$", out, re.M)
        self.pick = (re.findall(r"^PICK=(.*)$", out, re.M) or [""])[-1].strip()
        return json.loads(m[-1]) if m else None

    def poweroff(self):
        try:
            self.ssh("sudo systemctl poweroff", 30)
        except subprocess.TimeoutExpired:
            pass
        try:
            self.vm.proc.wait(240)
        except subprocess.TimeoutExpired:
            self.vm.proc.kill(); self.vm.proc.wait()
        self.vm.mark("QEMU EXIT")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", required=True, choices=sorted(PROFILES))
    ap.add_argument("--image-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--tests", help="comma list; default: CRITERIA-CLOUD.md §5 for this cloud")
    ap.add_argument("--results")
    a = ap.parse_args()
    tests = a.tests.split(",") if a.tests else default_tests(a.cloud)
    os.makedirs(a.work, exist_ok=True)
    open(a.log, "w").close()
    spec = importlib.util.spec_from_file_location("battery", os.path.join(HERE, "run-tests.py"))
    battery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(battery)
    R = Run(a, battery)
    t0 = time.time()
    env = {"cloud": a.cloud, "board": f"cloud-{a.cloud}", "upto": ",".join(tests), "accel": battery.accel_for({"arch": "x86_64"})[0], "host_cpus": os.cpu_count(),
           "host_machine": platform.machine(), "tests": tests}
    print(f"ENV {json.dumps(env)}", flush=True)
    try:
        art = c0(a.cloud, a.image_dir)
        base = art
        if a.cloud == "gcp":
            sh("tar", "-xSzf", art, "-C", a.work, "disk.raw", check=True)
            base = os.path.join(a.work, "disk.raw")
        extra = []
        if "C6" in tests:
            nxt = [f for f in os.listdir(a.image_dir) if f.endswith("-next.raucb")]
            bd = os.path.join(a.work, "bdisk", "bundles")
            os.makedirs(bd, exist_ok=True)
            shutil.copy(os.path.join(a.image_dir, nxt[0]), os.path.join(bd, "next.raucb"))
            bimg = os.path.join(a.work, "bundles.img")
            mib = os.path.getsize(os.path.join(bd, "next.raucb")) // (1 << 20) + 256
            sh("mke2fs", "-q", "-F", "-t", "ext4", "-L", "onemind-test", "-d", os.path.dirname(bd), bimg, f"{mib}M", check=True)
            extra = [bimg]
        if tests != ["C0"]:
            boot_main(R, base, tests, extra)
        if "C5" in tests:
            boot_wizard(R, base)
    except (TimeoutError, RuntimeError, subprocess.SubprocessError) as e:
        record("HARNESS", False, f"aborted: {e}")
        if R.vm and R.vm.proc and R.vm.proc.poll() is None:
            R.vm.kill()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    R.logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-CLOUD.md",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    for f in os.listdir(a.work):
        if f.endswith((".qcow2", ".img", ".raw")) or f.startswith(("seed-", "bdisk", "id_ed25519")):
            p = os.path.join(a.work, f)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    ran = {r["test"] for r in RESULTS}
    return 0 if RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) and set(tests) <= ran else 1


def boot_main(R, base, tests, extra):
    disk, seed, extra = R.prepare(base, "main", True, extra)
    vm = R.boot(disk, seed, extra)
    vm.mark("C1 first boot as hub")
    cfg = vm.expect(CONFIGURED, 900).group(0)
    time.sleep(3)
    gate = expect_from(vm, GATE, 0, 1800).groups()
    toks = TOKEN.findall(vm.since(0))
    record("C1", len(toks) == 1 and gate[0] == "committed-boot" and gate[1] == "A",
           f"config='{cfg[:80]}' tokens_printed={len(toks)} gate={gate}")
    token = toks[0] if toks else ""
    ok_ssh = R.ssh_ready()

    # C2: cloud-init as that cloud
    c = {"ssh_admin_sudo": ok_ssh}
    _, st = R.ssh("cloud-init status --wait --long 2>&1 | head -12", 960)
    # `--wait` prints its progress dots and then "status: done" on the same line.
    c["cloud_init_done"] = re.search(r"(^|\.)status: done\s*$", st, re.M) is not None
    _, out = R.ssh("echo IID=$(cloud-init query v1.instance_id); echo PLAT=$(cloud-init query v1.platform)")
    c["instance_id"] = f"IID={R.iid}" in out
    c["platform_nocloud"] = re.search(r"^PLAT=nocloud\s*$", out, re.M) is not None
    dsl = R.datasource_list()
    c["datasource_list"] = dsl == R.p["datasources"]
    _, hk = R.ssh("echo SLOTKEYS=$(ls /etc/ssh/ssh_host_* 2>/dev/null | wc -l); sudo test -s /data/onemind/ssh/ssh_host_ed25519_key && echo DATAKEY")
    c["hostkeys_on_data_only"] = "SLOTKEYS=0" in hk and "DATAKEY" in hk
    # CRITERIA-CLOUD.md §6: the interface with the seed's MAC (restrict=on gives no default route).
    _, net = R.ssh(f"dev=$(ip -o link | awk '/link\\/ether {MAC} /{{sub(\":\",\"\",$2); print $2; exit}}'); "
                   "echo DEV=$dev; ip -o link show dev $dev; ip -o -4 addr show dev $dev; ip -o -6 addr show dev eth0 2>/dev/null")
    dev = (re.findall(r"^DEV=(\S*)\s*$", net, re.M) or [""])[-1]
    if R.p["net"] == "gce-mtu":
        c["net_mtu_1460"] = bool(dev) and re.search(rf"^\d+: {re.escape(dev)}: .*\bmtu 1460\b", net, re.M) is not None
    elif R.p["net"] == "hetzner-v1":
        c["net_eth0_v6"] = re.search(r"\beth0\s+inet6 " + re.escape(HETZNER_V6), net) is not None
    else:
        c["net_dhcp_ipv4"] = bool(dev) and re.search(rf"\b{re.escape(dev)}\s+inet \d+\.\d+\.\d+\.\d+/", net) is not None
    record("C2", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" dev={dev} dsl={dsl} ds_identify='{R.pick}'")

    # C3: OneMind answers through the forwarded port
    nid, tok_sha = R.node_id()
    hz = wait_http(R.ports["http"], "/healthz")[0]
    rows = R.listed(token, nid) if token and hz == 200 else []
    me = [r for r in rows if r[0] == nid]
    noauth = http(R.ports["http"], "/v1/nodes")[0]
    code, body = http(R.ports["http"], "/")
    _, idx = R.ssh("sha256sum /usr/lib/onemind/dashboard/index.html | cut -c1-64")
    dash = code == 200 and hashlib.sha256(body).hexdigest() in idx
    # Reported, not judged: the SSH path to the token (clouds whose console users cannot see ttyS0).
    _, rt = R.ssh("sudo cat /run/onemind/owner-token 2>/dev/null | sha256sum | cut -c1-64")
    run_tok = bool(token) and hashlib.sha256((token + "\n").encode()).hexdigest() in rt
    record("C3", hz == 200 and bool(me) and me[0][1] == "hub" and noauth == 401 and dash and bool(nid),
           f"healthz={hz} node_id={nid} listed={rows} unauth={noauth} dashboard={dash} "
           f"(info: /run/onemind/owner-token over ssh matches console={run_tok})")

    # C4: data grew; a reboot keeps state
    _, g = R.ssh("d=$(readlink -f /dev/disk/by-partlabel/onemind-data); p=$(basename $d); "
                 "disk=$(basename $(readlink -f /sys/class/block/$p/..)); "
                 "echo DISK=$(cat /sys/class/block/$disk/size) START=$(cat /sys/class/block/$p/start) "
                 "PSIZE=$(cat /sys/class/block/$p/size); "
                 "sudo dumpe2fs -h $d 2>/dev/null | grep -E '^(Block count|Block size):'")
    v = dict(re.findall(r"(DISK|START|PSIZE)=(\d+)", g))
    bc = re.search(r"Block count:\s+(\d+)", g); bs = re.search(r"Block size:\s+(\d+)", g)
    grown = False
    if len(v) == 3 and bc and bs:
        disk_b, end_b, part_b = int(v["DISK"]) * 512, (int(v["START"]) + int(v["PSIZE"])) * 512, int(v["PSIZE"]) * 512
        grown = disk_b == R.disk_size and disk_b - end_b <= (1 << 20) and int(bc.group(1)) * int(bs.group(1)) >= 0.98 * part_b
    seg = vm.here()
    try:
        R.ssh("sudo systemctl reboot", 30)
    except subprocess.TimeoutExpired:
        pass
    al = vm.expect(ALREADY, 900).group(0)
    g4 = expect_from(vm, GATE, seg, 1800).groups()
    R.ssh_ready()
    new_toks = TOKEN.findall(vm.since(seg))
    nid2, tok_sha2 = R.node_id()
    hz2 = wait_http(R.ports["http"], "/healthz")[0]
    rows2 = R.listed(token, nid)
    record("C4", grown and not new_toks and nid2 == nid and tok_sha2 == tok_sha and hz2 == 200
           and any(r[0] == nid for r in rows2),
           f"grown={grown} sizes={v} '{al[:60]}' new_tokens={len(new_toks)} same_node={nid2 == nid} "
           f"same_tokens_file={tok_sha2 == tok_sha} healthz={hz2} listed={rows2} gate={g4}")

    if "C6" in tests:
        vm.mark("C6 A/B update keeps the cloud")
        t = time.time()
        rc, out = R.ssh("sudo mkdir -p /run/b && sudo mount -o ro /dev/disk/by-label/onemind-test /run/b && "
                        "sudo rauc install /run/b/bundles/next.raucb 2>&1 | tail -4; test ${PIPESTATUS[0]} -eq 0", 2460)
        vm.mark(f"install rc={rc} in {time.time() - t:.0f}s: {out.strip()[-200:]}")
        seg = vm.here()
        try:
            R.ssh("sudo systemctl reboot", 30)
        except subprocess.TimeoutExpired:
            pass
        g6 = expect_from(vm, GATE, seg, 1800).groups()
        R.ssh_ready()
        s = vm.since(seg)
        dsl6 = R.datasource_list()
        nid6, _ = R.node_id()
        hz6 = wait_http(R.ports["http"], "/healthz")[0]
        rows6 = R.listed(token, nid)
        record("C6", rc == 0 and g6[0] == "mark-good" and g6[1] == "B" and dsl6 == R.p["datasources"]
               and re.search(ALREADY, s) is not None and not TOKEN.search(s) and nid6 == nid and hz6 == 200
               and any(r[0] == nid for r in rows6),
               f"install_rc={rc} gate={g6} dsl={dsl6} already={re.search(ALREADY, s) is not None} "
               f"new_token={bool(TOKEN.search(s))} same_node={nid6 == nid} healthz={hz6}")
    R.poweroff()


def boot_wizard(R, base):
    disk, seed, extra = R.prepare(base, "wizard", False)
    vm = R.boot(disk, seed, extra)
    vm.mark("C5 no role: the wizard answers only inside the instance")
    w = vm.expect(WIZARD, 900).group(0)
    R.ssh_ready()
    _, out = R.ssh("for i in $(seq 60); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/); "
                   "[ \"$c\" = 200 ] && break; sleep 5; done; echo INSIDE=$c")
    inside = re.search(r"^INSIDE=200\s*$", out, re.M) is not None
    outside = http(R.ports["http"], "/", timeout=15)
    record("C5", inside and outside[0] is None,
           f"'{w[:70]}' inside_200={inside} outside={outside[0]} ({outside[1][:60]!r})")
    R.poweroff()


if __name__ == "__main__":
    sys.exit(main())
