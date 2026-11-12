#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, USB installer (I1-I5). Criteria: test/qemu/CRITERIA-INSTALLER.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's VM driver.

Two disks: the installer stick (`make installer`, USB mass storage, copy-on-write so the file never
changes) and a fresh, all-zero 40 GiB NVMe target. Everything goes through the installer's serial
menu and its LAN page (forwarded to 127.0.0.1); the installed box is checked from outside only
(console + forwarded :8080), because the shipped image has no login. Runs in the tools container:

  python3 -I installer.py --stick-dir DIR --image-dir DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, importlib.util, json, os, platform, re, struct, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("battery", os.path.join(HERE, "run-tests.py"))
battery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(battery)

PORT = 18080
URL = f"http://127.0.0.1:{PORT}"
READY = r"ONEMIND-INSTALLER: ready disks=(\d+)"
PROMPT = r"Install OneMind on disk number: "
AFTER = r"(ONEMIND-FIRSTBOOT: configured role=\w+ source=\w+[^\n]*|ONEMIND-INSTALLER: ready)"
TOKEN = re.compile(r"ONEMIND OWNER TOKEN: ([0-9a-f]{64})")
TARGET_GIB = 40
WRITE_BUDGET = 3600   # CRITERIA-INSTALLER.md §1: write + verify from the confirmation
TCG_SLACK = 4         # TCG only: wait this many budgets, then report BLOCKED (TCG timing) with the time (§3)
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


class InstVM(battery.VM):
    """The battery's VM driver with the installer's disks: USB stick + NVMe target."""

    def __init__(self, work, logf, stick, target):
        super().__init__("x86_64-efi", work, logf, work)
        self.stick, self.target, self.with_stick = stick, target, True

    def start(self):
        c = self.cfg
        cmd = [c["qemu"], "-machine", c["machine"], "-accel", self.accel, "-cpu", self.cpu,
               "-smp", "4", "-m", "3072", "-nodefaults", "-display", "none", "-vga", "none",
               "-nic", f"user,model=virtio-net-pci,restrict=on,hostfwd=tcp:127.0.0.1:{PORT}-:8080",
               "-device", "i6300esb", "-action", "watchdog=reset",
               "-drive", f"if=pflash,format=raw,readonly=on,file={c['code']}",
               "-drive", f"if=pflash,format=raw,file={self.vars}",
               "-drive", f"if=none,id=tgt,format=raw,cache=writeback,discard=unmap,detect-zeroes=unmap,file={self.target}",
               "-device", "nvme,drive=tgt,serial=onemind-target,bootindex=1"]
        if self.with_stick:
            cmd += ["-device", "qemu-xhci,id=xhci",
                    "-drive", f"if=none,id=stick,format=raw,snapshot=on,file={self.stick}",
                    "-device", "usb-storage,bus=xhci.0,drive=stick,bootindex=0"]
        cmd += ["-serial", "stdio", "-monitor", "none"]
        self.mark(f"QEMU START {' '.join(cmd)}")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, bufsize=0)
        import threading
        threading.Thread(target=self._reader, daemon=True).start()


def http(method, path, token=None, data=None, timeout=20):
    req = urllib.request.Request(URL + path, method=method, data=data)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def poll(method, path, until, timeout, token=None):
    end, last = time.time() + timeout, (0, "")
    while time.time() < end:
        last = http(method, path, token)
        if until(*last):
            break
        time.sleep(5)
    return last


def blocks(path):
    return os.stat(path).st_blocks


def answer(vm, prompt, text, timeout=120):
    vm.expect(prompt, timeout)
    time.sleep(0.5)
    vm.send(text)


def gpt(path):
    """[(index, label, partuuid, first, last)] and the primary header's backup LBA."""
    rows = []
    for i in range(1, 129):
        o = subprocess.run(["sgdisk", "-i", str(i), path], capture_output=True, text=True).stdout
        m = re.search(r"^Partition unique GUID: (\S+)", o, re.M)
        if not m or "does not exist" in o:
            break
        g = lambda rx: re.search(rx, o, re.M).group(1)
        rows.append((i, g(r"^Partition name: '([^']*)'"), m.group(1).upper(),
                     int(g(r"^First sector: (\d+)")), int(g(r"^Last sector: (\d+)"))))
    with open(path, "rb") as f:
        f.seek(512)
        hdr = f.read(92)
    alt = struct.unpack_from("<Q", hdr, 32)[0] if hdr[:8] == b"EFI PART" else -1
    return rows, alt


def check_layout(target, image):
    src, _ = gpt(image)
    dst, alt = gpt(target)
    total = os.path.getsize(target) // 512
    same = [(r[1], r[2]) for r in src] == [(r[1], r[2]) for r in dst] and len(src) > 0
    data = [r for r in dst if r[1] == "onemind-data"]
    grown = bool(data) and data[0][4] >= total - 34 - 2048
    esp = [r for r in dst if r[1] == "onemind-esp"]
    conf = ""
    if esp:
        for name in ("onemind.conf.applied", "onemind.conf"):
            r = subprocess.run(["mtype", "-i", f"{target}@@{esp[0][3] * 512}", f"::/{name}"], capture_output=True, text=True)
            if r.returncode == 0 and re.search(r"^role = hub\s*$", r.stdout, re.M):
                conf = name
                break
    ok = same and alt == total - 1 and grown and bool(conf)
    return ok, (f"labels_uuids_same={same} parts={len(dst)} backup_lba={alt} disk_last_lba={total - 1} "
                f"data_last={data[0][4] if data else None} grown={grown} role_file={conf or 'missing'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stick-dir", required=True)
    ap.add_argument("--image-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    stick = os.path.join(a.stick_dir, open(os.path.join(a.stick_dir, "SHA256SUMS")).read().split()[1])
    sums = open(os.path.join(a.image_dir, "SHA256SUMS")).read()
    m = re.search(r"^([0-9a-f]{64})  (onemind-x86_64-efi-\S+\.img)$", sums, re.M)
    want_sha, image = m.group(1), os.path.join(a.image_dir, m.group(2))
    target = os.path.join(a.work, "target.img")
    if os.path.exists(target):
        os.remove(target)
    with open(target, "wb") as f:
        f.truncate(TARGET_GIB << 30)
    logf = open(a.log, "w")
    vm = InstVM(a.work, logf, stick, target)
    env = {"board": "installer-x86_64", "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(),
           "host_machine": platform.machine(), "upto": "I5", "target_gib": TARGET_GIB, "expected_sha256": want_sha}
    print(f"ENV {json.dumps(env)}", flush=True)
    t0 = time.time()
    try:
        vm.mark("I1 installer boots from the USB stick")
        seg = vm.here(); vm.start()
        n = vm.expect(READY, 600).group(1)
        vm.expect(PROMPT, 60)
        menu = vm.since(seg)
        offered = re.findall(r"^\s*\[(\d+)\] (/dev/\S+)\s+([\d.]+ [GT]B)", menu, re.M)
        code_m = re.findall(r"one-time code: (\d{8})", menu)
        st, page = poll("GET", "/", lambda c, b: c == 200, 180)
        nvme_ok = len(offered) == 1 and offered[0][1].startswith("/dev/nvme") and offered[0][2] == f"{TARGET_GIB * 2**30 / 1e9:.1f} GB"
        page_ok = st == 200 and offered and offered[0][1] in page and "erased" in page and "/dev/sd" not in page.split("Not offered")[0]
        record("I1", nvme_ok and bool(page_ok),
               f"disks={n} offered={offered} stick_not_offered={not any('/dev/sd' in o[1] for o in offered)} "
               f"page={st} page_names_target={bool(offered) and offered[0][1] in page} code_shown={bool(code_m)} t={time.time() - t0:.0f}s")

        vm.mark("I2 erase needs explicit confirmation")
        form = urllib.parse.urlencode({"disk": offered[0][1] if offered else "", "role": "hub", "confirm": "ERASE",
                                       "code": "00000000" if not code_m or code_m[-1] != "00000000" else "11111111"}).encode()
        web_code, _ = http("POST", "/install", data=form)
        b_web = blocks(target)
        vm.send("1")
        answer(vm, r"Role: [^\n]*: ", "hub")
        answer(vm, r"Name shown in the dashboard[^\n]*: ", "")
        answer(vm, r"Type ERASE to erase this disk and install OneMind: ", "yes")
        refused = vm.expect(r"ONEMIND-INSTALLER: not confirmed; nothing was written", 60) is not None
        vm.expect(PROMPT, 120)
        b_word = blocks(target)
        record("I2", web_code == 403 and b_web == 0 and refused and b_word == 0,
               f"web_without_code={web_code} blocks_after_web={b_web} wrong_word_refused={refused} blocks_after_wrong_word={b_word}")

        vm.mark("I3 write with verification")
        seg = vm.here(); t3 = time.time()
        vm.send("1")
        answer(vm, r"Role: [^\n]*: ", "hub")
        answer(vm, r"Name shown in the dashboard[^\n]*: ", "")
        answer(vm, r"Type ERASE to erase this disk and install OneMind: ", "ERASE")
        slack = 1 if vm.accel == "kvm" else TCG_SLACK
        pv = vm.expect(r"ONEMIND-INSTALLER: payload verified sha256=[0-9a-f]{64}", WRITE_BUDGET * slack).group(0)
        ver = vm.expect(r"ONEMIND-INSTALLER: verified sha256=([0-9a-f]{64}) bytes=(\d+)", WRITE_BUDGET * slack)
        t_ver = time.time() - t3
        done = vm.expect(r"ONEMIND-INSTALLER: done target=(\S+) role=(\S+)[^\n]*", 600).group(0)
        rb = vm.expect(r"reboot: Restarting system", 300) is not None
        out = vm.since(seg)
        nb = re.findall(r"ONEMIND-INSTALLER: (firmware boot entry[^\n]*|could not add[^\n]*|no EFI[^\n]*)", out)
        grown = re.findall(r"ONEMIND-INSTALLER: (onemind-data grown[^\n]*|WARNING: onemind-data[^\n]*)", out)
        ok3 = ver.group(1) == want_sha and rb and "role=hub" in done
        record("I3", ("BLOCKED (TCG timing)" if t_ver > WRITE_BUDGET else True) if ok3 else False,
               f"'{pv[:60]}...' readback_sha={ver.group(1)} expected={want_sha} bytes={ver.group(2)} '{done}' "
               f"rebooted={rb} next_boot={nb} data={grown} confirm_to_verified_s={t_ver:.0f} budget_s={WRITE_BUDGET} accel={vm.accel}")

        vm.mark("I5 installed disk boots into OneMind")
        seg = vm.here()
        first = vm.expect(AFTER, 900).group(0)
        how = "stick left in; firmware next boot = target"
        if first.startswith("ONEMIND-INSTALLER"):
            how = "stick removed (the firmware booted the stick again)"
            vm.kill(); vm.with_stick = False; vm.restart("I5 restart without the stick")
            seg = 0
            first = vm.expect(AFTER, 900).group(0)
        # The gate may decide before or after the first-boot line (both are console lines).
        gm = re.search(battery.GATE, vm.since(seg))
        g = (gm.group(1), gm.group(2), gm.group(3)) if gm else vm.wait_gate(1800)
        time.sleep(3)
        toks = TOKEN.findall(vm.since(seg))
        token = toks[0] if toks else ""
        hz = poll("GET", "/healthz", lambda c, b: c == 200, 900)[0]
        nst, nbody = poll("GET", "/v1/nodes", lambda c, b: c == 200 and '"hub"' in b, 600, token=token)
        try:
            nodes = [(x["node_id"], x["role"], x["status"]) for x in json.loads(nbody)] if nst == 200 else []
        except (ValueError, KeyError, TypeError):
            nodes = []
        noauth = http("GET", "/v1/nodes")[0]
        rst, rbody = http("GET", "/")
        record("I5", first.startswith("ONEMIND-FIRSTBOOT: configured role=hub source=esp") and len(toks) == 1
               and g[0] == "committed-boot" and g[1] == "A" and hz == 200 and any(r == "hub" for _, r, _ in nodes)
               and noauth == 401 and rst == 200 and "<html" in rbody.lower(),
               f"boot={how} '{first[:90]}' tokens_printed={len(toks)} gate={g} healthz={hz} nodes={nodes} "
               f"unauth={noauth} root={rst} t={time.time() - t0:.0f}s")
        vm.kill()
        ok4, d4 = check_layout(target, image)
        record("I4", ok4, d4)
    except (TimeoutError, RuntimeError, AttributeError) as e:
        record("HARNESS", False, f"aborted: {e}")
        if vm.proc and vm.proc.poll() is None:
            vm.kill()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in sorted(RESULTS, key=lambda r: r["test"]):
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-INSTALLER.md",
                   "results": sorted(RESULTS, key=lambda r: r["test"])}, open(a.results, "w"), indent=2)
    return 0 if RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
