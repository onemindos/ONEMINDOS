#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, edge profile (EG1-EG7, #751). Criteria: test/qemu/CRITERIA-EDGE.md (pre-registered).

The same image as every box, first booted as an edge: a NoCloud seed with role leaf and a well-formed join code
for a hub that does not exist (TEST-NET-1), so the join never completes and nothing depends on it. Then one
restart, the checks that no hub service runs and no hub secret exists, the gate's leaf check, a good update and
a bad one (bad-leaf: onemindd exits at start), and the box's memory against the 300 MiB edge target.
Needs fixtures made with EDGE=1. Run: make edge BOARD=x86_64-efi (Linux with KVM).
"""
import argparse, importlib.util, json, os, platform, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load("firstboot_h", "firstboot.py")
battery = fb.battery

ORDER = ["EG1", "EG2", "EG3", "EG4", "EG5", "EG6", "EG7"]
HUB_UNITS = ["k3s", "onemind-gateway", "onemind-gateway-kube", "onemind-nats", "onemind-headscale",
             "onemind-mesh-setup", "onemind-starting"]
HUB_SECRETS = ["/data/onemind/gateway/tokens.yaml", "/data/onemind/identity/ca.key", "/data/onemind/gateway/tls/ca.key",
               "/data/onemind/nats/keys", "/data/onemind/etc/headscale.key", "/data/k3s/server/token", "/data/k3s/server/tls"]
K3S_WRITES = ["/data/k3s/server", "/data/k3s/agent", "/data/k3s/data"]      # CRITERIA-EDGE.md §4
HUB_PORTS = [6443, 10250, 8080, 8443, 8444, 7422]
EDGE_UNITS = ["onemindd", "onemind-nats-leaf", "tailscaled", "onemind-fabric-join", "onemind-local-api", "onemind-firstboot"]
TARGET_MIB = 300
HUB_ADDR = "192.0.2.10"                                                     # TEST-NET-1 (RFC 5737)
JOIN_CODE = ("onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=" + "ab" * 32 +
             "&role=leaf&hub=https%3A%2F%2Fhub.invalid")                    # .invalid never resolves (RFC 2606)
CONFIGURED = r"ONEMIND-FIRSTBOOT: configured role=leaf source=nocloud[^\n]*"
ALREADY = r"ONEMIND-FIRSTBOOT: already configured role=leaf[^\n]*"
FRESH = r"HEALTH-GATE: \S+ (LEAF|K3S)-FRESH (ok|ALERT)[^\n]*"
PASS_LINE = re.compile(r"CHECK pass (\d)/3 at \d+s: ok \(fresh: onemindd")
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def seed_userdata():
    return f'#cloud-config\nonemind:\n  role: leaf\n  join_code: "{JOIN_CODE}"\n  hub_addr: {HUB_ADDR}\n'


def make_seed(work):
    """Replace firstboot.py's hub seed with the edge seed (same NoCloud layout, label CIDATA)."""
    d, seed = os.path.join(work, "seed"), os.path.join(work, "seed.img")
    open(os.path.join(d, "meta-data"), "w").write("instance-id: onemind-edge\nlocal-hostname: onemind\n")
    open(os.path.join(d, "user-data"), "w").write(seed_userdata())
    os.remove(seed)
    subprocess.run(["mkfs.fat", "-n", "CIDATA", "-C", seed, "2048"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["mcopy", "-i", seed, os.path.join(d, "meta-data"), os.path.join(d, "user-data"), "::/"], check=True)


def used_mib(meminfo):
    kv = {k: int(v) for k, v in re.findall(r"^(\w+):\s+(\d+) kB", meminfo, re.M)}
    return round((kv["MemTotal"] - kv["MemAvailable"]) / 1024)


def kv_lines(out, tag):
    return dict(re.findall(rf"^{tag} (\S+) (\S*)\s*$", out, re.M))


def reboot(vm):
    seg = vm.here()
    vm.pos = seg
    vm.send("systemctl reboot")
    return seg


def eg2_eg3_eg4(vm, seg):
    units = " ".join(HUB_UNITS)
    _, o = vm.run(f"for u in {units}; do echo \"UNIT $u $(systemctl is-active $u 2>/dev/null)\"; done; "
                  "echo \"K3SRESULT $(systemctl show -p Result --value k3s)\"; "
                  "ss -H -ltn | awk '{n=split($4,a,\":\"); print \"LISTEN \" a[n]}'; "
                  f"for d in {' '.join(K3S_WRITES)}; do [ -e $d ] && echo \"K3SDIR $d present\"; done; true", 120)
    active = sorted(u for u, s in kv_lines(o, "UNIT").items() if s == "active")
    seen = kv_lines(o, "UNIT")
    k3s_result = (re.findall(r"^K3SRESULT (\S*)", o, re.M) or ["?"])[-1]
    listening = {int(p) for p in re.findall(r"^LISTEN (\d+)\s*$", o, re.M)}
    k3s_dirs = re.findall(r"^K3SDIR (\S+) present", o, re.M)
    record("EG2", len(seen) == len(HUB_UNITS) and not active and k3s_result == "exec-condition"
           and not listening & set(HUB_PORTS) and not k3s_dirs,
           f"hub_active={active} k3s_result={k3s_result} hub_ports_listening={sorted(listening & set(HUB_PORTS))} "
           f"k3s_dirs={k3s_dirs}")
    _, o = vm.run("echo \"ACTIVE $(systemctl is-active onemindd)\"; echo \"BOOT $(cat /proc/sys/kernel/random/boot_id)\"; "
                  "echo \"HZ $(curl -s -m 5 http://127.0.0.1:7480/healthz)\"; "
                  f"for s in {' '.join(HUB_SECRETS)}; do [ -e $s ] && echo \"SECRET $s present\"; done; true", 120)
    boot = (re.findall(r"^BOOT (\S+)", o, re.M) or ["?"])[-1]
    hz = (re.findall(r"^HZ (.*)$", o, re.M) or [""])[-1]
    secrets = re.findall(r"^SECRET (\S+) present", o, re.M)
    on = "ACTIVE active" in o
    match = len(boot) == 36 and ('"boot_id":"%s"' % boot) in hz
    record("EG3", on and match and not secrets,
           f"onemindd_active={on} healthz_boot_id_matches={match} hub_secrets_present={secrets}")
    text = vm.since(seg)
    fresh = re.findall(FRESH, text)
    rc, o = vm.run("/usr/lib/onemind/onemind-leaf-check; echo LEAFCHECK-RC=$?", 120)
    line = (re.findall(r"^(ok \(.*|fail G\d.*)$", o, re.M) or ["none"])[-1]
    record("EG4", ("LEAF", "ok") in fresh and not any(w == "K3S" for w, _ in fresh) and "LEAFCHECK-RC=0" in o
           and line.startswith("ok ("), f"fresh={fresh} hand_run={line[:160]}")


def eg7(vm):
    time.sleep(60)
    units = " ".join(EDGE_UNITS)
    _, o = vm.run(f"grep -E '^(MemTotal|MemAvailable):' /proc/meminfo; for u in {units}; do "
                  "echo \"MEM $u $(systemctl show -p MemoryCurrent --value $u 2>/dev/null)\"; done; true", 120)
    try:
        used = used_mib(o)
    except KeyError:
        record("EG7", "BLOCKED", "could not read /proc/meminfo")
        return
    per = {u: int(v) for u, v in kv_lines(o, "MEM").items() if v.isdigit()}
    units_mib = round(sum(per.values()) / 1048576)
    record("EG7", "RECORDED", f"box_used_mib={used} {'within' if used <= TARGET_MIB else 'over'} target_mib={TARGET_MIB} "
           f"edge_units_mib={units_mib} per_unit_mib={ {u: round(v / 1048576, 1) for u, v in per.items()} }")


def update(vm, bundle):
    """Install a bundle, reboot, and return (install rc, the trial's gate result, its whole line, leaf passes)."""
    rc, seg = battery.update_and_reboot(vm, bundle)
    vm.pos = seg
    g = vm.wait_gate()
    return rc, g, vm.last_gate, PASS_LINE.findall(vm.since(seg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(battery.BOARDS))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    fb.make_work(a.fixtures, a.work)
    make_seed(a.work)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    # No fail-fast: the join to a hub that does not exist fails on purpose, and EG6 breaks onemindd on purpose.
    rc = 1
    try:
        vm.mark("EG1 first boot as an edge (role leaf)")
        vm.start()
        g1 = vm.wait_gate()
        vm.pos = 0
        vm.expect(CONFIGURED, 900)
        vm.shell_ready()
        token = "ONEMIND OWNER TOKEN" in vm.since(0)
        record("EG1", g1 == ("committed-boot", "A", "1") and not token, f"gate={g1} owner_token_printed={token}")

        vm.mark("EG2-EG4, EG7 after one restart")
        seg = reboot(vm)
        vm.expect(ALREADY, 900)
        vm.pos = seg                     # first boot's line and the gate's can come in either order
        vm.wait_gate()
        vm.expect(FRESH, 900)            # always after the gate's result (watch_only)
        vm.shell_ready()
        eg2_eg3_eg4(vm, seg)
        eg7(vm)

        vm.mark("EG5 good update on an edge")
        rc5, g5, _, passes = update(vm, "good.raucb")
        record("EG5", rc5 == 0 and g5 == ("mark-good", "B", "2") and len(passes) >= 3,
               f"install_rc={rc5} gate={g5} leaf_check_passes={len(passes)}")
        vm.shell_ready()

        vm.mark("EG6 bad update on an edge (bad-leaf: onemindd exits at start)")
        _, o = vm.run(f"test -f {battery.B}/bad-leaf.raucb && echo HAVE-BAD-LEAF", 60)
        if "HAVE-BAD-LEAF" not in o:
            record("EG6", False, "bad-leaf.raucb missing from the fixtures (make fixtures EDGE=1)")
        else:
            rc6, g6, line6, _ = update(vm, "bad-leaf.raucb")
            verdict = (re.findall(r"verdict=(\S+)", line6) or [None])[0]
            back = vm.wait_gate()
            vm.shell_ready()
            grub = battery.envkv(vm.run(battery.ENV)[1])
            record("EG6", rc6 == 0 and g6 == ("mark-bad", "A", "8") and verdict == "image-bad"
                   and back == ("committed-boot", "B", "2") and "A_OK=0" in grub,
                   f"install_rc={rc6} gate={g6} verdict={verdict} then={back} grubenv={grub}")
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
    if vm.proc and vm.proc.poll() is None:
        vm.kill() if rc else vm.poweroff()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-EDGE.md", "results": RESULTS},
                  open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    judged = [r for r in RESULTS if r["verdict"] != "RECORDED"]
    return 0 if judged and all(r["verdict"] == "PASS" for r in judged) and len(RESULTS) == len(ORDER) else 1


if __name__ == "__main__":
    sys.exit(main())
