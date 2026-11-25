#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, memory pressure (M0-M1). Criteria: test/qemu/CRITERIA-MEMORY.md
(pre-registered; never edited to make a result pass). Reuses firstboot.py (hub first boot) and
run-tests.py's VM driver. Needs an 8 GiB VM: the Makefile target sets ONEMIND_QEMU_MEM=8192.

  python3 -I memorypressure.py --board x86_64-efi --fixtures DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, importlib.util, json, os, platform, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("firstboot", os.path.join(HERE, "firstboot.py"))
fb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fb)
battery = fb.battery

CONTROL = ["k3s", "onemind-nats", "onemind-gateway", "onemindd"]
HOG_GIB = 6
HOLD_S = 90
MIN_PROBES = 30
# The hog allocates HOG_GIB of memory, fills it (half zeros, half random, so zram can compress it), holds it.
HOG = ("import os,time;n=%d<<30;b=bytearray(n);blk=os.urandom(512<<10)+bytes(512<<10);"
       "[b.__setitem__(slice(i,i+len(blk)),blk) for i in range(0,n,len(blk))];time.sleep(%d)" % (HOG_GIB, HOLD_S))


def parse_probes(text):
    """Lines 'PROBE <seconds> <http code>' -> (count, [codes that are not 200])."""
    codes = re.findall(r"^PROBE \d+ (\S+)\s*$", text, re.M)
    return len(codes), [c for c in codes if c != "200"]


def unit_state(text, tag):
    """Lines '<tag> <unit> pid=<n> restarts=<n>' -> {unit: (pid, restarts)}."""
    return {u: (p, r) for u, p, r in re.findall(r"^%s (\S+) pid=(\d+) restarts=(\d+)\s*$" % tag, text, re.M)}


def oom_victims(text):
    """Process names the kernel OOM killer killed, from 'Out of memory: Killed process N (name)' lines."""
    return re.findall(r"Out of memory: Killed process \d+ \(([^)]*)\)", text)


def control_victims(names):
    return [n for n in names if n in ("k3s", "k3s-server", "nats-server", "onemindd")]


def state_cmd(tag):
    return ("for u in %s; do echo %s $u pid=$(systemctl show -p MainPID --value $u.service) "
            "restarts=$(systemctl show -p NRestarts --value $u.service); done" % (" ".join(CONTROL), tag))


def m0(vm):
    _, out = vm.run(
        "echo MEMKB=$(awk '/MemTotal/{print $2}' /proc/meminfo); echo SWAP=$(swapon --noheadings --show=NAME | tr '\\n' ' '); "
        "echo SWAPPINESS=$(sysctl -n vm.swappiness); "
        "for u in " + " ".join(CONTROL) + "; do p=$(systemctl show -p MainPID --value $u.service); "
        "echo OOM $u $(cat /proc/$p/oom_score_adj) $(cat /sys/fs/cgroup/system.slice/$u.service/memory.min); done; "
        "echo CAPALLOC=$(k3s kubectl get node -o jsonpath='{.items[0].status.capacity.memory} {.items[0].status.allocatable.memory}'); "
        "echo DATAOPTS=$(findmnt -n -o OPTIONS /data); echo JOURNAL=$(grep -h SystemMaxUse /etc/systemd/journald.conf.d/*.conf)", 120)
    get = lambda k: (re.findall(r"^%s=(.*)$" % k, out, re.M) or [""])[-1].strip()
    mem_ok = int(get("MEMKB") or 0) >= int(7.5 * 1024 * 1024)
    swap_ok = "zram" in get("SWAP")
    oom = {u: (a, m) for u, a, m in re.findall(r"^OOM (\S+) (-?\d+) (\d+)\s*$", out, re.M)}
    oom_ok = all(u in oom and oom[u][0] == "-900" and int(oom[u][1]) > 0 for u in CONTROL)
    ca = re.findall(r"(\d+)Ki", get("CAPALLOC"))
    res_ok = len(ca) == 2 and int(ca[0]) - int(ca[1]) >= 1024 * 1024
    data_ok = "noatime" in get("DATAOPTS").split(",")
    jr_ok = get("JOURNAL").replace(" ", "") == "SystemMaxUse=500M"
    fb.record("M0", mem_ok and swap_ok and get("SWAPPINESS") == "100" and oom_ok and res_ok and data_ok and jr_ok,
              f"mem_ok={mem_ok} swap='{get('SWAP')}' swappiness={get('SWAPPINESS')} oom={oom} cap_alloc='{get('CAPALLOC')}' "
              f"data='{get('DATAOPTS')[:80]}' journal='{get('JOURNAL')}'")


def m1(vm):
    _, before = vm.run(state_cmd("BEFORE"), 60)
    kmark = vm.run("echo KLINES=$(journalctl -k --no-pager | wc -l)", 60)[1]
    skip = int((re.findall(r"KLINES=(\d+)", kmark) or ["0"])[-1])
    # The probe loop runs in the background until the stop file appears; the hog is its own transient unit.
    vm.run("rm -f /run/m1-stop /run/m1-probe.log; (while [ ! -e /run/m1-stop ]; do "
           "echo PROBE $SECONDS $(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/healthz) >> /run/m1-probe.log; "
           "sleep 2; done) >/dev/null 2>&1 &", 30)
    time.sleep(10)
    vm.run("systemd-run --unit=onemind-memhog --quiet --collect %s -c '%s'" % (fb.PY, HOG), 30)
    t0 = time.time()
    while time.time() - t0 < HOLD_S + 240:        # the hog unit ends by itself or is OOM killed
        _, o = vm.run("echo ACTIVE=$(systemctl is-active onemind-memhog.service)", 60)
        if "ACTIVE=active" not in o and "ACTIVE=activating" not in o:
            break
        time.sleep(5)
    time.sleep(20)
    vm.run("touch /run/m1-stop; sleep 3", 30)
    _, probes = vm.run("cat /run/m1-probe.log", 60)
    _, after = vm.run(state_cmd("AFTER"), 60)
    _, klog = vm.run(f"journalctl -k --no-pager | tail -n +{skip + 1} | grep -i 'out of memory\\|oom' | head -40; echo END", 60)
    _, hog = vm.run("echo HOG=$(systemctl show -p Result --value onemind-memhog.service) "
                    "MAXMEM=$(systemctl show -p MemoryPeak --value onemind-memhog.service); "
                    "echo SWAPUSED=$(free -m | awk '/Swap/{print $3}')MiB", 60)
    n, bad = parse_probes(probes)
    b, a = unit_state(before, "BEFORE"), unit_state(after, "AFTER")
    victims = oom_victims(klog)
    final = fb.http_code(vm, f"{fb.GW}/healthz", timeout=60)
    record_ok = (n >= MIN_PROBES and not bad and set(b) == set(CONTROL) and b == a
                 and not control_victims(victims) and final == "200")
    fb.record("M1", record_ok, f"probes={n} non200={bad[:5]} units_same={b == a} before={b} after={a} "
              f"oom_killed={victims} final_healthz={final} info: {' '.join(hog.split())[:200]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(battery.BOARDS))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    os.environ.setdefault("ONEMIND_QEMU_MEM", "8192")
    fb.make_work(a.fixtures, a.work)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(),
           "host_machine": platform.machine(), "mem_mib": os.environ["ONEMIND_QEMU_MEM"]}
    print(f"ENV {json.dumps(env)}", flush=True)
    rc = 1
    vm.failfast = True
    try:
        vm.mark("M-0 first boot as hub on the big VM"); vm.start()
        vm.expect(fb.CONFIGURED, 900)
        time.sleep(3)
        vm.pos = 0
        vm.wait_gate(); vm.shell_ready()
        hz = fb.http_code(vm, f"{fb.GW}/healthz", timeout=900)
        if hz != "200":
            fb.diagnose(vm, f"healthz={hz}")
            raise RuntimeError(f"healthz={hz} before the load")
        vm.mark("M0 protection in place"); m0(vm)
        vm.mark("M1 6 GiB hog, control plane must stay up"); vm.failfast = False; m1(vm)
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        fb.record("HARNESS", False, f"aborted: {e}")
    if rc == 0:
        vm.poweroff()
    elif vm.proc and vm.proc.poll() is None:
        vm.kill()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in fb.RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-MEMORY.md",
                   "results": fb.RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    return 0 if fb.RESULTS and all(r["verdict"] == "PASS" for r in fb.RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
