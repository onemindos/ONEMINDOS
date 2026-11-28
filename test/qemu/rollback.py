#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, go back to the previous OS version (RB0-RB4). Criteria: test/qemu/CRITERIA-ROLLBACK.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's VM driver and firstboot.py's fixtures.

The box runs V2 in slot B after a good update, V1 waits committed in slot A. The host service is asked for
`os-rollback` the way the gateway does after an owner's passkey approval (that part is tested in
core/tests/test_os_rollback_passkey.py): over /run/onemind/host.sock, with the action id, the kind and the
approved version. The real RAUC, the real host service and the real health gate do the rest.

  python3 -I rollback.py --board x86_64-efi --fixtures DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, importlib.util, json, os, platform, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load("firstboot_harness", "firstboot.py")     # make_work, CONFIGURED (its battery import is run-tests.py)
battery = fb.battery
RESULTS = []
SOCK = "/run/onemind/host.sock"
V1, V2 = "1", "2"                                   # the fixture's versions (run-tests.py T1, T3)
CURL = f"curl -s --unix-socket {SOCK}"


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def val(out, name):
    """Last NAME=value line the guest printed (the echoed command shows NAME=$(...), never a real value)."""
    vals = [v for v in re.findall(rf"^{re.escape(name)}=(.*?)\s*$", out, re.M) if v and "$(" not in v]
    return vals[-1] if vals else ""


def host_status(vm):
    """(rollback available?, its reason, boot id) from GET /v1/status."""
    _, out = vm.run(f"S=$({CURL} http://h/v1/status | tr -d '\\n'); "
                    "echo AVAIL=$(echo \"$S\" | grep -o '\"kind\":\"os-rollback\",\"available\":[a-z]*' | grep -o '[a-z]*$'); "
                    "echo REASON=$(echo \"$S\" | grep -o '\"kind\":\"os-rollback\",\"available\":false,\"unavailable_reason\":\"[^\"]*\"' | sed 's/.*\"unavailable_reason\":\"//; s/\"$//'); "
                    "echo BOOT=$(cat /proc/sys/kernel/random/boot_id)")
    return val(out, "AVAIL") == "true", val(out, "REASON"), val(out, "BOOT")


def post(vm, action_id, version):
    """POST /v1/operations os-rollback: (HTTP code, reason or '')."""
    body = json.dumps({"action_id": action_id, "kind": "os-rollback", "version": version})
    _, out = vm.run(f"R=$({CURL} -o /tmp/rb.json -w '%{{http_code}}' -X POST -H 'Content-Type: application/json' "
                    f"-d '{body}' http://h/v1/operations); echo CODE=$R; echo RBODY=$(tr -d '\\n' < /tmp/rb.json)")
    reason = re.search(r'"reason":"([^"]*)"', val(out, "RBODY"))
    return val(out, "CODE"), (reason.group(1) if reason else "") + " " + val(out, "RBODY")[:160]


def op_state(vm, action_id, wait=60):
    """(state, reason) of a journaled operation, polled until it is final or `wait` seconds pass."""
    end, st, reason = time.time() + wait, "", ""
    while time.time() < end:
        _, out = vm.run(f"O=$({CURL} http://h/v1/operations/{action_id} | tr -d '\\n'); "
                        "echo ST=$(echo \"$O\" | grep -o '\"state\":\"[a-z_]*\"' | sed 's/.*:\"//; s/\"//'); "
                        "echo RE=$(echo \"$O\" | grep -o '\"reason\":\"[^\"]*\"' | sed 's/.*:\"//; s/\"//')")
        st, reason = val(out, "ST"), val(out, "RE")
        if st in ("succeeded", "failed"):
            break
        time.sleep(3)
    return st, reason


def slots(vm):
    """(booted slot, inactive slot's boot_status, pending marker present, bad-releases text)."""
    _, out = vm.run("echo BOOTED=$(sed -n 's/.*rauc\\.slot=\\([AB]\\).*/\\1/p' /proc/cmdline); "
                    "echo OTHERSTATUS=$(rauc status --output-format=json | tr -d '\\n ' | grep -o '\"bootname\":\"[AB]\",\"state\":\"inactive\"[^}]*' | grep -o '\"boot_status\":\"[a-z]*\"' | head -n1 | sed 's/.*:\"//; s/\"//'); "
                    "echo PENDING=$(test -s /data/onemind/pending && echo yes || echo no); "
                    "echo BAD=$(tr '\\n' ';' < /data/onemind/bad-releases 2>/dev/null | tr ' ' '_')")
    return val(out, "BOOTED"), val(out, "OTHERSTATUS"), val(out, "PENDING"), val(out, "BAD")


def ensure_bundles(vm):
    """shell_ready() mounts the bundles disk once; right after first boot udev may not have made the label link yet."""
    vm.run("for i in $(seq 60); do mountpoint -q /run/onemind-test && break; udevadm settle -t 5 2>/dev/null; "
           "mount -o ro /dev/disk/by-label/onemind-test /run/onemind-test 2>/dev/null; sleep 2; done; "
           "mountpoint -q /run/onemind-test", 240)


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
    vm.failfast = True
    blocked = None
    try:
        vm.mark("RB0 first boot, then a good update: V2 in slot B, V1 waits in slot A")
        vm.start()
        vm.expect(fb.CONFIGURED, 900)
        time.sleep(3)
        vm.pos = 0                      # the gate line may have been printed before the first-boot line (bootlock.py does the same)
        g0 = vm.wait_gate()
        vm.shell_ready()
        ensure_bundles(vm)
        rc, _ = battery.update_and_reboot(vm, "good.raucb")
        g = vm.wait_gate()
        gate_detail = vm.last_gate
        vm.shell_ready()
        booted, other_status, pending, bad = slots(vm)
        ok0 = (g0 == ("committed-boot", "A", V1) and rc == 0 and g == ("mark-good", "B", V2)
               and booted == "B" and other_status == "good" and pending == "no")
        detail = (f"first={g0} install_rc={rc} update_gate={g} booted={booted} "
                  f"inactive_slot_status={other_status} marker={pending}")
        if not ok0:
            detail += f" gate_detail={gate_detail!r}"
        record("RB0", ok0, detail)
        if not ok0:
            raise RuntimeError("RB0 failed: RB1-RB4 cannot run")
        vm.run("systemctl start onemind-host.socket", 60)
        # Slot A was written by the image builder, so RAUC has no record of its version (CRITERIA-ROLLBACK.md §4).
        # The update engine notes the version it replaced when it commits an update; this update was installed by
        # hand with `rauc install` (as in T3), so the same note is written here, as status.json, in the engine's format.
        note = json.dumps({"channel": "security", "current_version": V2, "available_version": None, "state": "committed", "last_check": None,
                           "last_result": f"committed {V2} (health gate passed)", "previous_version": V1, "from_version": V1, "target_version": V2})
        vm.run(f"mkdir -p /data/onemind/update && echo '{note}' > /data/onemind/update/status.json; sync")

        vm.mark("RB1 offered only when the other slot is known good")
        up, reason, boot1 = host_status(vm)
        vm.run("echo RAUCJSON=$(rauc status --output-format=json | tr -d '\\n ' | cut -c1-900); cat /data/onemind/bad-releases 2>&1 | head -3; "
               "grep -c . /etc/onemind/update.conf; cat /data/onemind/update/status.json 2>&1 | head -c 400")
        vm.run("rauc status mark-bad other")
        up_bad, reason_bad, _ = host_status(vm)
        code, why = post(vm, "rb-bad", V1)
        time.sleep(30)
        booted_after, _, boot_after = slots(vm)[0], None, host_status(vm)[2]
        vm.run("rauc status mark-good other")
        up_again, _, _ = host_status(vm)
        record("RB1", up and not up_bad and "not marked good" in reason_bad and code == "409"
               and boot_after == boot1 and booted_after == "B" and up_again,
               f"offered={up} first_reason={reason!r} offered_with_bad_slot={up_bad} reason={reason_bad!r} post={code}/{why} same_boot={boot_after == boot1} "
               f"booted={booted_after} offered_after_repair={up_again}")

        vm.mark("RB4 a version the owner did not approve is not run")
        code4, _ = post(vm, "rb-wrong", "9.9.9")
        st4, re4 = op_state(vm, "rb-wrong", 60)
        _, _, boot4 = host_status(vm)
        record("RB4", code4 == "202" and st4 == "failed" and re4 == "version_changed" and boot4 == boot1 and slots(vm)[0] == "B",
               f"post={code4} state={st4} reason={re4} same_boot={boot4 == boot1}")

        vm.mark("RB2 an approved rollback boots the previous slot and the gate commits it")
        seg = vm.here()
        code2, _ = post(vm, "rb-go", V1)
        g2 = vm.wait_gate()
        vm.shell_ready()
        booted2, status2, pending2, bad2 = slots(vm)
        st2, re2 = op_state(vm, "rb-go", 120)
        gate_lines = vm.since(seg)
        installed = "rauc install" in gate_lines
        record("RB2", code2 == "202" and g2 == ("committed-boot", "A", V1) and booted2 == "A" and pending2 == "no"
               and f"version={V2}_verdict=owner-rollback" in bad2 and st2 == "succeeded" and not installed,
               f"post={code2} gate={g2} booted={booted2} marker={pending2} bad_releases={bad2!r} op={st2}/{re2} install_ran={installed}")

        vm.mark("RB3 going back twice does not swap the slots")
        up3, reason3, boot3 = host_status(vm)
        code3, _ = post(vm, "rb-fwd", V2)
        time.sleep(30)
        _, _, boot3b = host_status(vm)
        record("RB3", not up3 and "rolled back earlier" in reason3 and code3 == "409" and boot3b == boot3 and slots(vm)[0] == "A",
               f"offered={up3} reason={reason3!r} post={code3} same_boot={boot3b == boot3}")
    except (TimeoutError, RuntimeError) as e:
        blocked = str(e)
        record("HARNESS", False, f"aborted: {e}")
    try:
        vm.poweroff()
    except Exception:
        vm.kill()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-ROLLBACK.md",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    need = {"RB0", "RB1", "RB2", "RB3", "RB4"}
    got = {r["test"] for r in RESULTS if r["verdict"] == "PASS"}
    return 0 if need <= got and all(r["verdict"] == "PASS" for r in RESULTS) and blocked is None else 1


if __name__ == "__main__":
    sys.exit(main())
