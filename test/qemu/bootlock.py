#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, boot menu lock (B1-B6). Criteria: test/qemu/CRITERIA-BOOTLOCK.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's VM driver and firstboot.py's fixtures.

Why: with no GRUB password anyone at the console can press `e`, add `init=/bin/sh` to the kernel command line
and get a root shell. The image sets a GRUB superuser; its per-box password is made at first boot.
This test boots the box, reads the password from the console, then plays the attacker at the GRUB menu.

  python3 -I bootlock.py --board x86_64-efi --fixtures DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, importlib.util, json, os, platform, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(os.path.dirname(HERE))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load("firstboot_harness", "firstboot.py")     # make_work, CONFIGURED, ALREADY (its battery import is run-tests.py)
battery = fb.battery
PW_LINE = re.compile(r"ONEMIND BOOT MENU PASSWORD \(user onemind[^)]*\): ([a-z2-9]{4}(?:-[a-z2-9]{4}){4})")
USER_PROMPT = r"Enter username:"
EDITOR = r"Minimum Emacs-like screen editing"
DENIED = r"access denied"
BOOTED = r"Welcome to |onemind login:|HEALTH-GATE"       # the kernel and systemd are up: the keystroke did not stop the boot
RESULTS = []
ESP = "/boot/efi/EFI/BOOT"
# B1 "grub.cfg has no password_pbkdf2 line of its own" / "a hash baked into the image's grub.cfg" (CRITERIA-BOOTLOCK.md):
# a line that runs the password or password_pbkdf2 command, or any grub.pbkdf2 hash. grub.cfg.in's
# `insmod password_pbkdf2` only loads the module that command lives in; it sets no password, so it must not count.
CFG_PASSWORD_ERE = r"^[[:space:]]*password(_pbkdf2)?[[:space:]]|grub\.pbkdf2\."
# GRUB sleeps before it refuses a login, and the sleep doubles after every refusal until a login succeeds
# (grub-core/normal/auth.c, grub_auth_check_authentication: punishment_delay 1 s, 2 s, 4 s ...). B4 is the first
# refusal (1 s), B5 the second (2 s), so a fixed wait after the password misses B5's answer. Wait for the answer
# instead, within the criteria's 60 s per GRUB prompt.
ANSWER_TIMEOUT = 60


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def raw(vm, text):
    """Keystrokes as typed: no newline added (vm.send adds one). GRUB's serial console takes CR as Enter."""
    vm.proc.stdin.write(text.encode()); vm.proc.stdin.flush()


def seen(vm, start, pattern):
    return re.search(pattern, vm.since(start)) is not None


def poke(vm, key, want, timeout=60):
    """Send `key` every 0.4 s until GRUB prints `want`. Returns (found, booted). The first key stops the menu's
    1 s countdown; sending it again is harmless until the prompt is up, and each caller clears the line after."""
    start, end = vm.here(), time.time() + timeout
    while time.time() < end:
        raw(vm, key)
        time.sleep(0.4)
        if seen(vm, start, want):
            return True, False
        if seen(vm, start, BOOTED):
            return False, True
    return False, False


def answered(vm, start, pattern, timeout=ANSWER_TIMEOUT):
    """True once `pattern` shows up after `start`; False if `timeout` seconds pass first."""
    end = time.time() + timeout
    while True:
        if seen(vm, start, pattern):
            return True
        if time.time() >= end:
            return False
        time.sleep(0.2)


def login(vm, user, password, answer):
    """Type the login, then wait until GRUB answers with a match of `answer` (see ANSWER_TIMEOUT)."""
    start = vm.here()
    raw(vm, "\x15")                  # Ctrl-U: drop any extra keystroke typed before the prompt came up
    raw(vm, user + "\r"); time.sleep(0.5)
    raw(vm, password + "\r")
    answered(vm, start, answer)


def reboot_and_wait(vm, timeout=900, gate_timeout=1800):
    """Reboot the configured box; return (segment start, its first-boot line, its gate result).

    On a committed boot the health gate decides at once (os/gate/onemind-health-gate, "committed-boot"), and
    nothing orders onemind-health-gate.service against onemind-firstboot.service, which waits for cloud-init.
    So on a fast host the gate's line can come BEFORE "already configured". expect() moves the read position past
    the line it matched, so waiting for the gate after ALREADY skipped that boot's only gate line and B2 hung for
    wait_gate's 1800 s on an unmodified image (#1150, #1159). Search for the gate from the reboot on instead, as
    B1 (vm.pos = 0), edge.py and cloudboot.py already do. Both lines are still required, both from this boot."""
    seg = vm.here()
    vm.send("systemctl reboot")
    al = vm.expect(fb.ALREADY, timeout).group(0)
    vm.pos = seg                # this boot's buffer only: B1's gate line lies before seg
    return seg, al, vm.wait_gate(gate_timeout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=["x86_64-efi"])
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    fb.make_work(a.fixtures, a.work)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    rc = 1
    vm.failfast = True
    try:
        vm.mark("B1 first boot makes the per-box password; only its hash is stored")
        vm.start()
        vm.expect(fb.CONFIGURED, 900)
        time.sleep(3)
        pws = PW_LINE.findall(vm.since(0))
        vm.pos = 0
        vm.wait_gate()
        vm.shell_ready()
        pw = pws[0] if pws else ""
        _, out = vm.run(f"echo USERCFG=$(cat {ESP}/user.cfg 2>/dev/null | tr -d '\\r' | head -c 400); "
                        f"echo USERLINES=$(wc -l < {ESP}/user.cfg); "
                        f"echo PWINFILES=$(grep -c -F '{pw}' {ESP}/user.cfg {ESP}/grub.cfg | tr '\\n' ' '); "
                        f"echo CFGHASH=$(grep -c -E '{CFG_PASSWORD_ERE}' {ESP}/grub.cfg); "
                        f"echo SHA=$(sha256sum {ESP}/user.cfg | cut -c1-64)")
        get = lambda k: (re.findall(rf"^{k}=(.*?)\s*$", out, re.M) or [""])[-1]
        sha1 = get("SHA")
        hash_line = re.fullmatch(r"password_pbkdf2 onemind grub\.pbkdf2\.sha512\.\d+\.[0-9A-F]{128}\.[0-9A-F]{128}", get("USERCFG"))
        pw_clear = bool(pw) and any(not x.endswith(":0") for x in get("PWINFILES").split())
        record("B1", len(pws) == 1 and bool(hash_line) and get("USERLINES") == "1" and not pw_clear and get("CFGHASH") == "0",
               f"passwords_printed={len(pws)} hash_line_ok={bool(hash_line)} lines={get('USERLINES')} "
               f"password_in_files={pw_clear} hash_in_grub_cfg={get('CFGHASH')}")

        vm.mark("B2 a normal boot needs nothing")
        seg, al, g2 = reboot_and_wait(vm)
        vm.shell_ready()
        _, out = vm.run(f"echo SHA=$(sha256sum {ESP}/user.cfg | cut -c1-64)")
        sha2 = (re.findall(r"^SHA=(\w+)", out, re.M) or [""])[-1]
        record("B2", g2[0] == "committed-boot" and g2[1] == "A" and sha1 == sha2 and len(sha1) == 64
               and not seen(vm, seg, USER_PROMPT) and not PW_LINE.search(vm.since(seg)),
               f"'{al[:60]}' gate={g2} user_cfg_unchanged={sha1 == sha2} login_prompt_seen={seen(vm, seg, USER_PROMPT)}")

        # B3-B6 in one GRUB session (each boot attempt counts against the slot's TRY budget, so use one).
        vm.mark("reboot to the GRUB menu and play the attacker")
        vm.send("systemctl reboot")
        vm.expect(r"GRUB-RAUC: [^\n]*", 300)
        ok3, booted3 = poke(vm, "e", USER_PROMPT)
        record("B3", ok3 and not booted3, f"login_prompt={ok3} kernel_booted_past_keystroke={booted3}")
        if not ok3:
            raise RuntimeError("no GRUB login prompt: B4-B6 cannot run")

        s4 = vm.here()
        login(vm, "onemind", "wrong-password", f"{DENIED}|{EDITOR}")
        denied4, editor4 = seen(vm, s4, DENIED), seen(vm, s4, EDITOR)
        record("B4", denied4 and not editor4, f"access_denied={denied4} editor_opened={editor4}")
        raw(vm, " "); time.sleep(1)      # "press any key": back to the menu

        s5 = vm.here()
        ok5, _ = poke(vm, "c", USER_PROMPT)
        login(vm, "onemind", "wrong-password", f"{DENIED}|grub> ") if ok5 else None
        shell5 = seen(vm, s5, r"grub> ")
        record("B5", ok5 and seen(vm, s5, DENIED) and not shell5, f"login_prompt={ok5} access_denied={seen(vm, s5, DENIED)} grub_shell={shell5}")
        raw(vm, " "); time.sleep(1)

        s6 = vm.here()
        ok6, _ = poke(vm, "e", USER_PROMPT)
        if ok6:
            login(vm, "onemind", pw, f"{EDITOR}|{DENIED}")
        editor6 = seen(vm, s6, EDITOR)
        record("B6", ok6 and editor6 and bool(pw), f"login_prompt={ok6} editor_opened={editor6}")
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
    if vm.proc and vm.proc.poll() is None:
        vm.kill()           # at the GRUB menu there is no shell to power off from
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-BOOTLOCK.md",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    need = {"B1", "B2", "B3", "B4", "B5", "B6"}
    got = {r["test"] for r in RESULTS if r["verdict"] == "PASS"}
    return 0 if need <= got and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
