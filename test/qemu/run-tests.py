#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery (brief 30 B13 item 1; D-B1.6). Port of
research-output/evidence/lab/rauc-1152/scripts/run-tests.py, parameterised by board.
Criteria: test/qemu/CRITERIA.md (pre-registered; never edited to make a result pass).

Boots the board's test disk under QEMU with user-mode networking (restrict=on: no route out) and
an i6300esb watchdog, drives the serial console, runs T1..T11 (+ TC1 on cloud boards).
Power cut = SIGKILL of the QEMU process. Runs in the tools container (QEMU + firmware pinned):

  python3 -I run-tests.py --board x86_64-efi --fixtures DIR --log serial.log [--upto T5] [--results r.json]
"""
import argparse, json, os, platform, re, shutil, subprocess, sys, threading, time

ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-B]|\r")
GATE = r"HEALTH-GATE: \S+ RESULT (\S+) slot=(\w) version=(\S+)([^\n]*)"
ENV = "grub-editenv /boot/efi/EFI/BOOT/grubenv list"
B = "/run/onemind-test/bundles"
ORDER = ["T1", "TC1", "T2", "T11", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]

BOARDS = {  # QEMU settings per board (CRITERIA.md §3 item 6)
    "x86_64-efi": dict(qemu="qemu-system-x86_64", machine="q35", arch="x86_64", console="ttyS0",
                       code="/usr/share/OVMF/OVMF_CODE_4M.fd", vars="/usr/share/OVMF/OVMF_VARS_4M.fd"),
    "vm": dict(qemu="qemu-system-x86_64", machine="q35", arch="x86_64", console="ttyS0",
               code="/usr/share/OVMF/OVMF_CODE_4M.fd", vars="/usr/share/OVMF/OVMF_VARS_4M.fd"),
    "vm-do": dict(qemu="qemu-system-x86_64", machine="q35", arch="x86_64", console="ttyS0",
                  code=None, vars=None),   # SeaBIOS: QEMU's default firmware, no pflash
    "arm64-efi": dict(qemu="qemu-system-aarch64", machine="virt", arch="aarch64", console="ttyAMA0",
                      code="/usr/share/AAVMF/AAVMF_CODE.fd", vars="/usr/share/AAVMF/AAVMF_VARS.fd"),
}


def envkv(out):
    # Compare only grubenv KEY=VALUE lines; escape fragments split across serial reads can leak
    # into captured text (lab rauc-1152 deviation 4).
    out = re.sub(r"\x1b?\[\?[0-9;]*[A-Za-z]|\x1b\[[0-9;]*[A-Za-z]", "", out)
    return sorted(x.strip() for x in re.findall(r"^(?:ORDER=[AB ]+|[AB]_(?:OK|TRY)=\d+)[ \t]*$", out, re.M))


def accel_for(cfg):
    if os.environ.get("ONEMIND_QEMU_ACCEL"):      # local debugging only, e.g. "hvf" on a Mac
        return os.environ["ONEMIND_QEMU_ACCEL"], "host"
    host = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}.get(platform.machine())
    if host == cfg["arch"] and os.access("/dev/kvm", os.R_OK | os.W_OK):
        return "kvm", "host"
    return "tcg,thread=multi", "max"


class VM:
    def __init__(self, board, fx, log, workdir):
        self.cfg, self.fx, self.logf = dict(BOARDS[board]), fx, log
        for k in ("code", "vars"):                 # local debugging only: firmware outside the container
            if os.environ.get(f"ONEMIND_FW_{k.upper()}"):
                self.cfg[k] = os.environ[f"ONEMIND_FW_{k.upper()}"]
        self.buf, self.pos, self.lock, self.proc = "", 0, threading.Lock(), None
        self.accel, self.cpu = accel_for(self.cfg)
        self.vars = None
        if self.cfg["vars"]:
            self.vars = os.path.join(workdir, "VARS.fd")
            shutil.copy(self.cfg["vars"], self.vars)

    def start(self):
        c = self.cfg
        cmd = [c["qemu"], "-machine", c["machine"], "-accel", self.accel, "-cpu", self.cpu,
               "-smp", "4", "-m", "3072", "-nodefaults", "-display", "none", "-vga", "none",
               "-nic", "user,model=virtio-net-pci,restrict=on",
               "-device", "i6300esb", "-action", "watchdog=reset"]
        if c["code"]:
            cmd += ["-drive", f"if=pflash,format=raw,readonly=on,file={c['code']}",
                    "-drive", f"if=pflash,format=raw,file={self.vars}"]
        cmd += ["-drive", f"if=virtio,format=raw,cache=writeback,file={self.fx}/disk.img",
                "-drive", f"if=virtio,format=raw,readonly=on,file={self.fx}/bundles.img"]
        if os.path.exists(f"{self.fx}/seed.img"):
            cmd += ["-drive", f"if=virtio,format=raw,readonly=on,file={self.fx}/seed.img"]
        cmd += ["-serial", "stdio", "-monitor", "none"]
        self.mark(f"QEMU START {' '.join(cmd)}")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, bufsize=0)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while True:
            b = self.proc.stdout.read(4096)
            if not b:
                break
            t = ANSI.sub(b"", b).decode("utf-8", "replace")
            with self.lock:
                self.buf += t
            self.logf.write(t); self.logf.flush()

    def mark(self, msg):
        line = f"\n##### [{time.strftime('%H:%M:%S')}] {msg}\n"
        self.logf.write(line); self.logf.flush(); print(line.strip(), flush=True)

    def here(self):
        with self.lock:
            return len(self.buf)

    def since(self, i):
        with self.lock:
            return self.buf[i:]

    def expect(self, pattern, timeout):
        rx, end = re.compile(pattern), time.time() + timeout
        while time.time() < end:
            with self.lock:
                m = rx.search(self.buf, self.pos)
                if m:
                    self.pos = m.end()
                    return m
            if self.proc.poll() is not None:
                raise RuntimeError(f"QEMU exited (rc={self.proc.returncode}) while waiting for {pattern!r}")
            time.sleep(0.2)
        raise TimeoutError(f"timeout {timeout}s waiting for {pattern!r}")

    def send(self, s):
        self.proc.stdin.write((s + "\n").encode()); self.proc.stdin.flush()

    def run(self, cmd, timeout=180):
        start = self.here()
        self.send(f"{cmd}; echo __R''C=$?__")
        m = self.expect(r"__RC=(\d+)__", timeout)
        with self.lock:
            out = self.buf[start:m.start()]
        # Escape fragments split across serial reads survive ANSI stripping (lab deviation 4).
        return int(m.group(1)), re.sub(r"\x1b?\[\?[0-9;]*[A-Za-z]|\x1b\[[0-9;]*[A-Za-z]", "", out)

    def wait_gate(self, timeout=1800):
        m = self.expect(GATE, timeout)
        self.last_gate = m.group(0)
        return m.group(1), m.group(2), m.group(3)

    def shell_ready(self):
        time.sleep(2); self.send("")
        self.expect(r"root@onemind:~# ", 300)
        self.run("bind 'set enable-bracketed-paste off' 2>/dev/null; stty cols 200; export SYSTEMD_PAGER= SYSTEMD_COLORS=0 KUBECONFIG=/run/k3s/k3s.yaml")
        self.run("mkdir -p /run/onemind-test && (mountpoint -q /run/onemind-test || "
                 "mount -o ro /dev/disk/by-label/onemind-test /run/onemind-test)")

    def kill(self):
        self.mark("POWER CUT: SIGKILL qemu")
        self.proc.kill(); self.proc.wait()

    def restart(self, tag):
        self.mark(tag); self.buf, self.pos = "", 0; self.start()

    def poweroff(self):
        self.send("systemctl poweroff")
        try:
            self.proc.wait(240)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait()
        self.mark("QEMU EXIT (poweroff)")


RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def state(vm, tag):
    vm.run("echo '--- state:" + tag + "'; grep ONEMIND_VERSION /usr/lib/os-release; " + ENV +
           "; rauc status 2>&1 | grep -E 'Booted from|boot status|rootfs\\.[01]'; "
           "cat /data/onemind/pending 2>/dev/null || echo 'pending: none'; "
           "k3s kubectl get pods -A --no-headers 2>&1 | head -8")
    return vm.run(ENV)[1]


def install(vm, bundle, timeout=2400):
    t = time.time()
    rc, out = vm.run(f"rauc install {B}/{bundle} 2>&1 | tail -4; test ${{PIPESTATUS[0]}} -eq 0", timeout)
    vm.mark(f"install {bundle} rc={rc} in {time.time()-t:.0f}s")
    return rc, out


def wait_fresh(vm, timeout=1500):
    return vm.expect(r"K3S-FRESH (ok|ALERT)[^\n]*", timeout).group(0).strip()


def update_and_reboot(vm, bundle):
    rc, _ = install(vm, bundle)
    seg = vm.here()
    vm.send("systemctl reboot")
    return rc, seg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(BOARDS))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--upto", default="T5", choices=ORDER)
    ap.add_argument("--results")
    a = ap.parse_args()
    upto = ORDER.index(a.upto)
    want = lambda t: ORDER.index(t) <= upto
    logf = open(a.log, "w")
    t0 = time.time()
    vm = VM(a.board, a.fixtures, logf, os.path.dirname(os.path.abspath(a.log)))
    env_info = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(),
                "host_machine": platform.machine(), "upto": a.upto}
    print(f"ENV {json.dumps(env_info)}", flush=True)

    # T0 build: checks made by mkfixtures.sh on the build it just did.
    t0r = json.load(open(os.path.join(a.fixtures, "t0.json")))
    record("T0", t0r["pass"], " ".join(f"{k}={v}" for k, v in t0r["checks"].items()))

    # T1 first boot: committed slot A v1, k3s passes the fresh check
    vm.mark("T1 first boot"); vm.start()
    try:
        g = vm.wait_gate()
        f = wait_fresh(vm)
        vm.shell_ready(); state(vm, "T1")
        _, apps = vm.run("k3s kubectl -n apps get pods --no-headers")
        _, ver = vm.run("rauc --version; grep bundle-formats /etc/rauc/system.conf; dpkg-query -W rauc 2>&1 | tail -1")
        v1152 = re.search(r"^rauc v?1\.15\.2\s*$", ver, re.M) is not None
        verity = "bundle-formats=verity" in ver
        record("T1", g == ("committed-boot", "A", "1") and f.startswith("K3S-FRESH ok") and "0/1" in apps and v1152 and verity,
               f"gate={g} {f[:90]} apps_not_ready={'0/1' in apps} rauc_1.15.2={v1152} verity_policy={verity} t={time.time()-t0:.0f}s")
    except (TimeoutError, RuntimeError) as e:
        record("T1", False, f"first boot did not complete: {e}")
        finish(vm, a, env_info, t0, logf, alive=False)
        return 1

    if want("TC1") and os.path.exists(os.path.join(a.fixtures, "seed.img")):
        vm.mark("TC1 cloud first boot (NoCloud seed)")
        _, st = vm.run("cloud-init status --wait --long 2>&1 | head -12", 900)
        _, keys = vm.run("grep -c onemind-tc1 /home/admin/.ssh/authorized_keys")
        _, ssh = vm.run("systemctl is-active ssh.service")
        _, hk = vm.run("ls /data/onemind/ssh/ssh_host_ed25519_key; echo SLOTKEYS=$(ls /etc/ssh/ssh_host_* 2>/dev/null | wc -l)")
        done = re.search(r"^status: done", st, re.M) is not None
        key = re.search(r"^1\s*$", keys, re.M) is not None
        active = re.search(r"^active\s*$", ssh, re.M) is not None
        hostkeys = "/data/onemind/ssh/ssh_host_ed25519_key" in hk and "SLOTKEYS=0" in hk
        record("TC1", done and key and active and hostkeys,
               f"cloud_init_done={done} key_installed={key} sshd_active={active} hostkeys_on_data_only={hostkeys}")

    if want("T2"):
        vm.mark("T2 wrong-key bundle")
        before = vm.run(ENV)[1]
        rc, out = install(vm, "wrong-key.raucb", 900)
        after = vm.run(ENV)[1]
        sig = re.search(r"(?i)signature|verif|certificate", out) is not None
        _, pend = vm.run("cat /data/onemind/pending 2>/dev/null || echo none")
        record("T2", rc != 0 and sig and envkv(before) == envkv(after) != [] and "none" in pend,
               f"rc={rc} sig_error={sig} env_unchanged={envkv(before)==envkv(after)!=[]} marker_written={'none' not in pend}")

    if want("T11"):
        vm.mark("T11 plain-format bundle, valid signature, verity-only policy")
        before = vm.run(ENV)[1]
        rc, out = install(vm, "plain-good.raucb", 900)
        after = vm.run(ENV)[1]
        fmt = "Bundle format 'plain' not allowed" in out
        _, pend = vm.run("cat /data/onemind/pending 2>/dev/null || echo none")
        record("T11", rc != 0 and fmt and envkv(before) == envkv(after) != [] and "none" in pend,
               f"rc={rc} format_error={fmt} env_unchanged={envkv(before)==envkv(after)!=[]} marker_written={'none' not in pend}")

    try:
        if want("T3"):
            vm.mark("T3 good update -> B")
            rc, seg = update_and_reboot(vm, "good.raucb")
            g = vm.wait_gate(); s = vm.since(seg)
            passes = len(re.findall(r"CHECK pass \d/3", s)); fails = re.findall(r"CHECK fail at \d+s: ([^\n]*)", s)
            apps = re.search(r"APPS \(excluded from gate\): ([^\n]*)", s)
            vm.shell_ready(); state(vm, "T3-after-commit")
            vm.send("systemctl reboot")
            g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T3-second-reboot")
            apps_s = apps.group(1) if apps else ""
            record("T3", rc == 0 and g == ("mark-good", "B", "2") and passes >= 3 and "0/1" in apps_s
                   and g2 == ("committed-boot", "B", "2"),
                   f"rc={rc} trial={g} passes={passes} first_fails={fails[:2]} apps='{apps_s[:60]}' reboot={g2}")

        for tid, bundle, ver in (("T4", "bad-k3s.raucb", "3"), ("T5", "bad-noagent.raucb", "4")):
            if not want(tid):
                continue
            vm.mark(f"{tid} {bundle} -> A")
            rc, seg = update_and_reboot(vm, bundle)
            ts = time.time()
            g1 = vm.wait_gate(); line1 = vm.last_gate; dt = time.time() - ts
            s = vm.since(seg); last = re.findall(r"CHECK fail at \d+s: ([^\n]*)", s)
            g2 = vm.wait_gate(); f = wait_fresh(vm)
            vm.shell_ready(); env = state(vm, f"{tid}-end")
            record(tid, rc == 0 and g1 == ("mark-bad", "A", ver) and g2 == ("committed-boot", "B", "2")
                   and "A_OK=0" in env and f.startswith("K3S-FRESH ok"),
                   f"rc={rc} trial={g1} decided_after~{dt:.0f}s(since reboot) last_fail='{last[-1] if last else ''}' then={g2} {f[:40]}")
            verdict = re.search(r"verdict=(\S+)", line1)
            record(tid + "v", verdict is not None and verdict.group(1) == "image-bad",
                   f"verdict={verdict.group(1) if verdict else None}")

        for tid, bundle, mark in (("T6", "bad-boot.raucb", "BAD-BOOT: broken init exiting"),
                                  ("T7", "bad-hang.raucb", "BAD-HANG: arming watchdog")):
            if not want(tid):
                continue
            vm.mark(f"{tid} {bundle} -> A")
            rc, seg = update_and_reboot(vm, bundle)
            ts = time.time()
            g = vm.wait_gate(3000); s = vm.since(seg)
            attempts = s.count(mark); grub = re.findall(r"GRUB-RAUC: [^\n]*", s)
            vm.shell_ready(); env = state(vm, f"{tid}-end")
            seg2 = vm.here(); vm.send("systemctl reboot")
            g2 = vm.wait_gate(); s2 = vm.since(seg2)
            retried = mark in s2
            vm.shell_ready()
            record(tid, rc == 0 and attempts == 3 and g == ("fell-back", "B", "2") and "A_OK=0" in env
                   and not retried and g2 == ("committed-boot", "B", "2"),
                   f"rc={rc} attempts={attempts} in {time.time()-ts:.0f}s grub={grub[-1] if grub else ''} result={g} retried_next_boot={retried}")

        if want("T8"):
            vm.mark("T8 power cut during write (target A)")
            vm.send("journalctl -f -n0 -o cat -u rauc.service > /dev/console 2>&1 &")
            time.sleep(2)
            vm.send(f"rauc install {B}/good.raucb")
            vm.expect(r"trial marker slot=A", 900)
            vm.expect(r"Marking target slot rootfs\.0 as non-bootable", 900)
            vm.expect(r"Copying image|writing data to device", 900)
            time.sleep(6)
            pct = re.findall(r"(\d+)% Copying image", vm.since(0))
            activated = "as bootable (active/primary)" in vm.since(vm.pos)
            vm.kill()
            vm.restart("T8 restart after power cut")
            g = vm.wait_gate(); vm.shell_ready(); env = state(vm, "T8-after-cut")
            _, pend = vm.run("cat /data/onemind/pending 2>/dev/null || echo none")
            rc2, seg = update_and_reboot(vm, "good.raucb")
            g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T8-after-reinstall")
            record("T8", not activated and g == ("fell-back", "B", "2") and "A_OK=0" in env and "none" in pend
                   and rc2 == 0 and g2 == ("mark-good", "A", "2"),
                   f"cut_at={pct[-1] if pct else '?'}% activated_before_cut={activated} after_cut={g} "
                   f"marker_cleared={'none' in pend} reinstall_rc={rc2} then={g2}")

        if want("T9"):
            vm.mark("T9 power cut in commit window (target B)")
            rc, seg = update_and_reboot(vm, "good.raucb")
            vm.expect(r"HEALTH-GATE: \S+ start slot=B version=2 mode=trial", 1500)
            vm.expect(r"CHECK (pass|fail)", 900)
            committed_before = "RESULT mark-good" in vm.since(seg)
            vm.kill()
            vm.restart("T9 restart")
            grub = vm.expect(r"GRUB-RAUC: [^\n]*", 300).group(0)
            g = vm.wait_gate(); vm.shell_ready(); state(vm, "T9-end")
            record("T9", rc == 0 and not committed_before and "B_TRY=2" in grub and g == ("mark-good", "B", "2"),
                   f"rc={rc} killed_before_commit={not committed_before} next_boot='{grub.strip()}' result={g}")

        if want("T10"):
            vm.mark("T10 naive gate observation (target A)")
            rc, seg = update_and_reboot(vm, "naive-noagent.raucb")
            g = vm.wait_gate(); s = vm.since(seg)
            npass = re.findall(r"CHECK pass \d/3 at (\d+)s: ([^\n]*)", s)
            record("T10", "OBSERVED", f"naive gate result={g} passes={[p[0] for p in npass]} "
                   f"=> {'COMMITTED A BROKEN SYSTEM' if g[0] == 'mark-good' else 'did not commit'}")
            if g[0] == "mark-bad":
                g = vm.wait_gate()
            vm.shell_ready(); state(vm, "T10-after")
            rc2, seg2 = update_and_reboot(vm, "good.raucb")
            g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T10r-end")
            tgt = "B" if g[1] == "A" else "A"
            record("T10r", rc2 == 0 and g2 == ("mark-good", tgt, "2"), f"recovery install rc={rc2} result={g2}")
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
        finish(vm, a, env_info, t0, logf, alive=False)
        return 1
    return finish(vm, a, env_info, t0, logf, alive=True)


def finish(vm, a, env_info, t0, logf, alive):
    if alive:
        vm.run("echo '--- gate log'; cut -c1-220 /data/onemind/gate.log; echo '--- bad-releases'; cat /data/onemind/bad-releases 2>/dev/null")
        vm.poweroff()
    elif vm.proc and vm.proc.poll() is None:
        vm.kill()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env_info["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env_info, "minutes": round(total, 1), "results": RESULTS}, open(a.results, "w"), indent=2)
    return 0 if RESULTS and all(r["verdict"] in ("PASS", "OBSERVED") for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
