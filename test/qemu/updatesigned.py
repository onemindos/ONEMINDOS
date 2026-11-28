#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU, a signed update through the real update path (US0-US6). Criteria: test/qemu/CRITERIA-UPDATE-SIGNED.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's VM driver and firstboot.py's fixtures.

The fixture disk (made with SIGNED=1) ships a throwaway TUF root at /usr/lib/onemind/tuf/security/root.json. This
harness serves the channels that test/qemu/usrepo.py published (C1, C2, CK, CO, plus their target files) over HTTP on
the host; QEMU forwards the guest address 10.0.2.100:8000 to it (usrelay.py), and socat in the guest listens on
127.0.0.1:8000, the only plain-HTTP address the updater accepts. On the box it runs the owner's break-glass path,
`onemind update check|apply --local --no-reboot --config <file on /data>`: the box's own engine, go-tuf, the download
check, `rauc install` and the gate. Every request the server answers is logged, so a test can tell whether a bundle
was fetched; the tampered case flips one byte of the bundle while serving it.

  python3 -I updatesigned.py --board x86_64-efi --fixtures DIR --channels DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, http.server, importlib.util, json, os, platform, re, shutil, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load("firstboot_harness", "firstboot.py")     # make_work, CONFIGURED (its battery import is run-tests.py)
battery = fb.battery
RESULTS = []
CONF = "/data/onemind/us-update.conf"
ROOT = "/usr/lib/onemind/tuf/security/root.json"
GUEST_FWD = "10.0.2.100"
APPLY_TIMEOUT = 1800


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def val(out, name):
    """Last NAME=value line the guest printed (the echoed command shows NAME=$(...), never a real value)."""
    vals = [v for v in re.findall(rf"^{re.escape(name)}=(.*?)\s*$", out, re.M) if v and "$(" not in v]
    return vals[-1] if vals else ""


class Channel:
    """The host side: a threaded HTTP server for one channel at a time. Metadata comes from <channels>/<name>/, every
    other file from <channels>/files/. `tamper` names a file whose middle byte is flipped while it is served."""

    def __init__(self, root):
        self.root, self.name, self.tamper, self.log, self.lock = root, "C1", None, [], threading.Lock()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                name = os.path.basename(self.path.split("?", 1)[0])
                with outer.lock:
                    ch, tamper = outer.name, outer.tamper
                    outer.log.append(name)
                p = os.path.join(outer.root, ch, name)
                if not os.path.isfile(p):
                    p = os.path.join(outer.root, "files", name)
                if not name or not os.path.isfile(p):
                    self.send_error(404)
                    return
                size = os.path.getsize(p)
                flip = size // 2 if name == tamper else -1
                self.send_response(200)
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                pos = 0
                try:
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(1 << 20), b""):
                            if pos <= flip < pos + len(chunk):
                                b = bytearray(chunk)
                                b[flip - pos] ^= 0xFF
                                chunk = bytes(b)
                            self.wfile.write(chunk)
                            pos += len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass                                    # the box stopped reading (it may refuse early)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def serve(self, name, tamper=None):
        with self.lock:
            self.name, self.tamper, self.log = name, tamper, []

    def fetched(self, suffix=".raucb"):
        with self.lock:
            return [n for n in self.log if n.endswith(suffix)]


def relay(vm):
    """socat in the guest: 127.0.0.1:8000 -> the forwarded host address. Transient, so it is started after every boot."""
    vm.run("systemctl stop us-relay 2>/dev/null; systemd-run --unit=us-relay --collect "
           f"socat TCP-LISTEN:8000,bind=127.0.0.1,reuseaddr,fork TCP:{GUEST_FWD}:8000 >/dev/null 2>&1; sleep 1")
    _, out = vm.run("echo HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8000/timestamp.json)", 60)
    return val(out, "HTTP")


def box(vm):
    """(booted slot, ONEMIND_VERSION, pending marker present, bundle files under /data/rauc). /data/rauc is also RAUC's own
    data-directory (its status file), so only *.raucb and *.raucb.part count; the names are printed in the log."""
    _, out = vm.run("echo BOOTED=$(sed -n 's/.*rauc\\.slot=\\([AB]\\).*/\\1/p' /proc/cmdline); "
                    "echo VER=$(. /usr/lib/os-release; echo $ONEMIND_VERSION); "
                    "echo PENDING=$(test -s /data/onemind/pending && echo yes || echo no); "
                    "echo RAUCLIST=$(ls -A /data/rauc 2>/dev/null | tr '\\n' ' '); "
                    "echo RAUCFILES=$(ls -A /data/rauc 2>/dev/null | grep -cE '\\.raucb(\\.part)?$')")
    return val(out, "BOOTED"), val(out, "VER"), val(out, "PENDING"), val(out, "RAUCFILES")


def status(vm):
    """(state, last_result) from `onemind update status --json`."""
    _, out = vm.run(f"S=$(onemind update status --json --config {CONF} | tr -d '\\n'); "
                    "echo ST=$(echo \"$S\" | grep -o '\"state\": *\"[a-z_]*\"' | head -n1 | sed 's/.*\"\\([a-z_]*\\)\"$/\\1/'); "
                    "echo LR=$(echo \"$S\" | grep -o '\"last_result\": *\"[^\"]*\"' | head -n1 | sed 's/^\"last_result\": *\"//; s/\"$//')")
    return val(out, "ST"), val(out, "LR")


def engine(vm, sub, timeout=APPLY_TIMEOUT):
    """Run `onemind update <sub>` (check, or apply --local --no-reboot) against CONF: (exit code, its output)."""
    extra = " --local --no-reboot" if sub == "apply" else ""
    rc, out = vm.run(f"onemind update {sub}{extra} --config {CONF} > /tmp/us.out 2>&1; R=$?; "
                     "grep -E '^(decision:|  skipped )' /tmp/us.out; grep -iE 'error|fail|refus' /tmp/us.out | tail -3 | cut -c1-300; "
                     "echo URC=$R", timeout)
    return int(val(out, "URC") or -1), out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=["x86_64-efi"])
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--channels", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    summary = json.load(open(os.path.join(a.channels, "summary.json")))
    good, wrongca, old = (summary["bundles"][v] for v in ("2", "3", "1"))
    ch = Channel(a.channels)
    fb.make_work(a.fixtures, a.work)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    vm.nic_extra = f",guestfwd=tcp:{GUEST_FWD}:8000-cmd:python3 -I {HERE}/usrelay.py {ch.port}"
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    vm.failfast = True
    blocked = None
    try:
        vm.mark("US0 first boot; the image carries the rehearsal root; check against C1")
        vm.start()
        vm.expect(fb.CONFIGURED, 900)
        time.sleep(3)
        vm.pos = 0                      # the gate line may have been printed before the first-boot line
        g0 = vm.wait_gate()
        vm.shell_ready()
        _, out = vm.run(f"echo ROOTSHA=$(sha256sum {ROOT} 2>/dev/null | cut -d' ' -f1)")
        rootsha = val(out, "ROOTSHA")
        vm.run(f"printf 'channel = security\\nurl = http://127.0.0.1:8000\\nwindow = any\\npolicy = auto\\n' > {CONF}; cat {CONF}")
        http0 = relay(vm)
        ch.serve("C1")
        rc0, out0 = engine(vm, "check", 300)
        ok0 = (g0 == ("committed-boot", "A", "1") and rootsha == summary["root_sha256"] and http0 == "200"
               and rc0 == 0 and "decision: install" in out0 and not ch.fetched())
        record("US0", ok0, f"gate={g0} root_sha_matches={rootsha == summary['root_sha256']} relay_http={http0} check_rc={rc0} "
                           f"decision_install={'decision: install' in out0} bundle_fetched={ch.fetched()}")
        if not ok0:
            raise RuntimeError("US0 failed: US1-US6 cannot run" +
                               ("" if rootsha == summary["root_sha256"] else " (fixtures not made with SIGNED=1 for these channels?)"))

        vm.mark("US1 a tampered bundle is refused")
        ch.serve("C1", tamper=good)
        rc1, _ = engine(vm, "apply")
        st1, lr1 = status(vm)
        b1 = box(vm)
        record("US1", rc1 != 0 and good in ch.fetched() and st1 == "error" and lr1.startswith("download")
               and b1 == ("A", "1", "no", "0"),
               f"apply_rc={rc1} fetched={ch.fetched()} state={st1} last_result={lr1[:160]!r} box(slot,ver,marker,rauc_files)={b1}")

        vm.mark("US2 metadata signed by keys the root does not trust is refused")
        ch.serve("CK")
        rc2, _ = engine(vm, "apply")
        st2, lr2 = status(vm)
        b2 = box(vm)
        record("US2", rc2 != 0 and lr2.startswith("check failed") and not ch.fetched() and b2[:3] == ("A", "1", "no"),
               f"apply_rc={rc2} last_result={lr2[:160]!r} fetched={ch.fetched()} box={b2}")

        vm.mark("US3 the good signed update installs, boots and passes health")
        ch.serve("C1")
        rc3, out3 = engine(vm, "apply")
        st3, lr3 = status(vm)
        _, out = vm.run("echo MARKER=$(cat /data/onemind/pending 2>/dev/null | tr ' ' '_')")
        marker = val(out, "MARKER")
        vm.send("systemctl reboot")
        g3 = vm.wait_gate()
        vm.shell_ready()
        relay(vm)
        b3 = box(vm)
        rc3c, _ = engine(vm, "check", 300)
        st3c, lr3c = status(vm)
        record("US3", rc3 == 0 and "decision: install" in out3 and st3 == "pending_reboot" and marker.endswith("_2")
               and g3 == ("mark-good", "B", "2") and b3[:2] == ("B", "2") and rc3c == 0 and st3c == "committed",
               f"apply_rc={rc3} state_before_reboot={st3} marker={marker!r} gate={g3} box={b3} check_rc={rc3c} "
               f"state={st3c} last_result={lr3c[:120]!r}")
        if b3[:2] != ("B", "2"):
            raise RuntimeError("US3 failed: the box does not run V2, US4-US6 cannot run")

        vm.mark("US4 a bundle signed by a wrong RAUC key is refused even when the channel lists it")
        ch.serve("C2")
        rc4, _ = engine(vm, "apply")
        st4, lr4 = status(vm)
        b4 = box(vm)
        _, out = vm.run("echo NEXT=$(rauc status --output-format=json | tr -d '\\n ' | grep -o '\"boot_primary\":\"[^\"]*\"' | head -n1)")
        record("US4", rc4 != 0 and wrongca in ch.fetched() and lr4.startswith("rauc install") and b4[:3] == ("B", "2", "no"),
               f"apply_rc={rc4} fetched={ch.fetched()} state={st4} last_result={lr4[:200]!r} box={b4} {val(out, 'NEXT')}")

        vm.mark("US5 rollback is refused: a replay of older metadata, then an older version on newer metadata")
        ch.serve("C1")
        rc5a, _ = engine(vm, "apply")
        _, lr5a = status(vm)
        fetched5a = ch.fetched()
        ch.serve("CO")
        rc5b, out5b = engine(vm, "apply")
        fetched5b = ch.fetched()
        b5 = box(vm)
        skip_old = bool(re.search(rf"skipped \S*{re.escape(old)}: not newer than 2", out5b))
        record("US5", rc5a != 0 and lr5a.startswith("check failed") and not fetched5a
               and rc5b == 0 and "decision: nothing" in out5b and skip_old and not fetched5b
               and summary["publisher_refused_old"] and b5[:3] == ("B", "2", "no"),
               f"replay: rc={rc5a} last_result={lr5a[:140]!r} fetched={fetched5a}; older: rc={rc5b} "
               f"nothing={'decision: nothing' in out5b} skip_line={skip_old} fetched={fetched5b}; "
               f"publisher_refused_old={summary['publisher_refused_old']}; box={b5}")

        vm.mark("US6 the refusals left the box as it was")
        vm.send("systemctl reboot")
        g6 = vm.wait_gate()
        vm.shell_ready()
        relay(vm)
        ch.serve("CO")
        rc6, out6 = engine(vm, "check", 300)
        st6, _ = status(vm)
        record("US6", g6 == ("committed-boot", "B", "2") and rc6 == 0 and "decision: nothing" in out6
               and st6 not in ("pending_reboot", "trial", "rolled_back", ""),
               f"gate={g6} check_rc={rc6} nothing={'decision: nothing' in out6} state={st6}")
    except (TimeoutError, RuntimeError) as e:
        blocked = str(e)
        record("HARNESS", False, f"aborted: {e}")
    try:
        vm.poweroff()
    except Exception:
        vm.kill()
    ch.httpd.shutdown()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-UPDATE-SIGNED.md",
                   "channels": summary, "results": RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    need = {f"US{i}" for i in range(7)}
    got = {r["test"] for r in RESULTS if r["verdict"] == "PASS"}
    return 0 if need <= got and all(r["verdict"] == "PASS" for r in RESULTS) and blocked is None else 1


if __name__ == "__main__":
    sys.exit(main())
