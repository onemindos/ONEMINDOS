#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, setup wizard on the booted image (WZ1-WZ5). Criteria: test/qemu/CRITERIA-WIZARD.md
(pre-registered).

Two VMs boot the fixture image without a seed, so both run the wizard (#578: an unprivileged web part and a
root helper behind a socket). A QEMU socket link joins them on a LAN pair. B probes A's wizard from the LAN
(code required, a flood of requests), then sets A up as the hub from the LAN with the code from A's screen.
A mints a join code and B sets itself up as a worker on its own box screen (loopback). Run:
make wizard BOARD=x86_64-efi (Linux with KVM).
"""
import argparse, importlib.util, json, math, os, platform, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load("firstboot_h", "firstboot.py")
fw = _load("firewall_h", "firewall.py")
battery = fb.battery

LINK_PORT = int(os.environ.get("ONEMIND_QEMU_WIZ_LINK_PORT", "18771"))
MAC = {"a": "52:54:00:fe:01:01", "b": "52:54:00:fe:01:02"}
LAN = {"a": fw.ADDR["lan"]["box"], "b": fw.ADDR["lan"]["scan"]}   # the firewall battery's LAN pair
A_WIZ = f"http://{LAN['a']}:8080"
LOOP = "http://127.0.0.1:8080"
SOCK = "/run/onemind-setup-helper.sock"
CODE_FILE = "/run/onemind/setup-code"
FLOOD_N, FLOOD_PAR, SOCK_FLOOD_N = 2000, 16, 300
STATUS_TTL_S = 5
FLOOD_PY = r'''
import http.client, json, sys, threading, time
host, n, par = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
codes, lock = {}, threading.Lock()
def w(k):
    for _ in range(k):
        try:
            c = http.client.HTTPConnection(host, 8080, timeout=15); c.request("GET", "/")
            r = c.getresponse(); r.read(); code = str(r.status); c.close()
        except Exception as e:
            code = type(e).__name__
        with lock:
            codes[code] = codes.get(code, 0) + 1
t0 = time.time()
th = [threading.Thread(target=w, args=(n // par,)) for _ in range(par)]
[t.start() for t in th]; [t.join() for t in th]
print("FLOOD", round(time.time() - t0, 1), json.dumps(codes, sort_keys=True), flush=True)
'''
SOCK_FLOOD_PY = r'''
import socket, sys
ok = err = 0
for _ in range(int(sys.argv[2])):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(2)
    try:
        s.connect(sys.argv[1]); ok += 1
    except OSError:
        err += 1
    finally:
        s.close()
print("SOCKFLOOD", ok, err, flush=True)
'''
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def link_args(who):
    nd = f"socket,id=wzlink,{'listen' if who == 'a' else 'connect'}=127.0.0.1:{LINK_PORT}"
    return ["-netdev", nd, "-device", f"virtio-net-pci,netdev=wzlink,mac={MAC[who]}"]


def addr_cmd(who):
    return (f"IF=$(ip -o link | awk '/{MAC[who]}/ {{sub(\":\",\"\",$2); print $2; exit}}'); echo IF=$IF; "
            f"ip link set $IF up && ip addr add {LAN[who]}/24 dev $IF; echo ADDR-RC=$?")


def val(out, key, default=""):
    m = re.findall(rf"^{key}=(.*?)\s*$", out, re.M)
    return m[-1] if m else default


def wizard_up(vm, timeout=900):
    _, out = vm.run(f"t0=$SECONDS; while :; do b=$(curl -s --max-time 5 {LOOP}/healthz); "
                    f"[ \"$b\" = setup ] || [ $((SECONDS - t0)) -ge {timeout} ] && break; sleep 3; done; echo WIZ=$b",
                    timeout + 60)
    return val(out, "WIZ") == "setup"


def sock_show(vm):
    _, out = vm.run("systemctl show onemind-setup-helper.socket -p ActiveState -p Result -p NAccepted -p NConnections "
                    "-p NRefused | sed 's/^/SOCK_/'")
    return {k: val(out, f"SOCK_{k}") for k in ("ActiveState", "Result", "NAccepted", "NConnections", "NRefused")}


def drain(vm, timeout=180):
    """Wait until no helper connection is open (the root flood is queued and accepted slowly on purpose)."""
    vm.run(f"t0=$SECONDS; while [ \"$(systemctl show -p NConnections --value onemind-setup-helper.socket)\" != 0 ] "
           f"&& [ $((SECONDS - t0)) -lt {timeout} ]; do sleep 2; done", timeout + 30)


def wz1(a):
    _, out = a.run("pid=$(systemctl show -p MainPID --value onemind-setup); echo PID=$pid; "
                   "awk '/^Uid:/ {print \"UIDS=\" $2 \",\" $3} /^CapEff:/ {print \"CAPEFF=\" $2}' /proc/$pid/status; "
                   "echo SOCKACT=$(systemctl is-active onemind-setup-helper.socket); "
                   f"test -S {SOCK} && echo SOCKFILE=yes; echo CODESTAT=$(stat -c '%a %U' {CODE_FILE} 2>&1); "
                   f"echo CODE=$(cat {CODE_FILE} 2>/dev/null)")
    uids = val(out, "UIDS").split(",")
    c = {"uid_not_root": len(uids) == 2 and all(u.isdigit() and u != "0" for u in uids),
         "no_caps": re.fullmatch(r"0+", val(out, "CAPEFF")) is not None,
         "socket_active": val(out, "SOCKACT") == "active" and val(out, "SOCKFILE") == "yes",
         "code_file": val(out, "CODESTAT") == "600 root" and re.fullmatch(r"[2-9A-HJ-NP-Z]{10}", val(out, "CODE")) is not None}
    record("WZ1", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" uids={val(out, 'UIDS')}")
    return val(out, "CODE")


def wz2(a, b):
    _, out = b.run(f"curl -s -o /run/wz-form.html -w 'GET=%{{http_code}}\\n' --max-time 30 {A_WIZ}/; "
                   "grep -c 'name=\"code\"' /run/wz-form.html | sed 's/^/CODEFIELD=/'; "
                   f"curl -s -o /dev/null -w 'POST=%{{http_code}}\\n' --max-time 30 --data 'role=hub&name=Lab' {A_WIZ}/setup")
    _, st = a.run("test -e /data/onemind/firstboot/state.json && echo STATE=yes || echo STATE=no")
    c = {"get": val(out, "GET") == "200", "asks_code": val(out, "CODEFIELD", "0") != "0",
         "post_no_code": val(out, "POST") == "403", "not_configured": val(st, "STATE") == "no"}
    record("WZ2", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" get={val(out, 'GET')} post={val(out, 'POST')}")


def wz3(a, b):
    before = sock_show(a)
    fb.send_file(b, "/run/wzflood.py", FLOOD_PY)
    _, out = b.run(f"{fb.PY} -I /run/wzflood.py {LAN['a']} {FLOOD_N} {FLOOD_PAR}", 900)
    after_lan = sock_show(a)
    m = re.search(r"^FLOOD ([0-9.]+) (\{.*\})\s*$", out, re.M)
    secs, codes = (float(m.group(1)), json.loads(m.group(2))) if m else (0.0, {"none": 1})
    fb.send_file(a, "/run/wzsock.py", SOCK_FLOOD_PY)
    _, sf = a.run(f"{fb.PY} -I /run/wzsock.py {SOCK} {SOCK_FLOOD_N}", 600)
    drain(a)
    time.sleep(3)
    after = sock_show(a)
    _, lo = a.run(f"echo LOOP=$(curl -s --max-time 10 {LOOP}/healthz)")
    _, ln = b.run(f"curl -s -o /dev/null -w 'LAN=%{{http_code}}\\n' --max-time 30 {A_WIZ}/")
    try:
        used = int(after_lan["NAccepted"]) - int(before["NAccepted"])
    except ValueError:
        used = -1
    bound = math.ceil(secs / STATUS_TTL_S) + 3
    sock_ok = (re.findall(r"^SOCKFLOOD (\d+ \d+)", sf, re.M) or [sf.strip()[-40:]])[-1]
    c = {"socket_alive": after["ActiveState"] == "active" and after["Result"] == "success",
         "bounded": m is not None and 0 <= used <= bound,
         "answers": m is not None and sum(codes.values()) == FLOOD_N and set(codes) <= {"200", "403"},
         "still_serving": val(lo, "LOOP") == "setup" and val(ln, "LAN") == "200"}
    record("WZ3", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" flood_s={secs} codes={codes} helper_conns={used} bound={bound} sockflood={sock_ok!r}"
           f" socket={after}")


def wz4(a, b):
    _, cf = a.run(f"echo CODE=$(cat {CODE_FILE} 2>/dev/null)")
    code = val(cf, "CODE")
    _, out = b.run(f"curl -s -o /run/wz-done.html -w 'HTTP=%{{http_code}}\\n' --max-time 300 --data-urlencode role=hub "
                   f"--data-urlencode name=Lab --data-urlencode 'code={code}' {A_WIZ}/setup; "
                   "echo TOKEN=$(grep -o '<code>[0-9a-f]\\{64\\}</code>' /run/wz-done.html | head -1 | sed 's/<[/]*code>//g')",
                   400)
    token = val(out, "TOKEN")
    _, st = a.run(f"{fb.PY} -I -c 'import json; s=json.load(open(\"/data/onemind/firstboot/state.json\")); "
                  "print(\"ROLE=\" + s[\"role\"]); print(\"SOURCE=\" + s[\"source\"])' 2>&1; "
                  f"test -e {CODE_FILE} && echo CODEGONE=no || echo CODEGONE=yes", 60)
    _, wz = a.run("sleep 5; echo WIZACT=$(systemctl is-active onemind-setup)")
    hz = fb.http_code(a, f"{fb.GW}/healthz", timeout=900)      # the gateway's: the wizard has left :8080
    fab = fb.http_code(a, f"{fb.GW}/v1/fabric", token=token, timeout=120) if token else "no-token"
    if hz != "200":
        fb.diagnose(a, f"healthz={hz}")
    c = {"page": val(out, "HTTP") == "200" and bool(token), "state": val(st, "ROLE") == "hub" and val(st, "SOURCE") == "wizard",
         "code_spent": val(st, "CODEGONE") == "yes", "wizard_gone": val(wz, "WIZACT") != "active",
         "gateway": hz == "200" and val(wz, "WIZACT") != "active", "token_works": fab == "200"}
    record("WZ4", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" http={val(out, 'HTTP')} role={val(st, 'ROLE')} healthz={hz} fabric={fab}")
    return token


def wz5(a, b, token):
    # The wizard takes the full onemind-join:v1?... text: the ticket's qr_payload (`onemind fabric ticket` prints
    # it in its join command; one_time.join_code is only the short code inside it).
    _, t = a.run(f"curl -s -X POST -H 'Authorization: Bearer {token}' -H 'Content-Type: application/json' "
                 f"-d '{{\"role\":\"worker\",\"expires_in_s\":900}}' {fb.GW}/v1/fabric/join-tickets > /run/wz-ticket.json; "
                 f"{fb.PY} -I -c 'import json; print(\"JOIN=\" + json.load(open(\"/run/wz-ticket.json\"))[\"qr_payload\"])' "
                 "2>/dev/null || echo JOIN=", 60)
    join = val(t, "JOIN")
    if not join.startswith("onemind-join:v1?"):
        record("WZ5", False, f"no join code from the hub: {t.strip()[-200:]!r}")
        return
    _, out = b.run(f"curl -s -o /run/wz-w.html -w 'HTTP=%{{http_code}}\\n' --max-time 300 --data-urlencode role=worker "
                   f"--data-urlencode 'join_code={join}' --data-urlencode hub_addr={LAN['a']} {LOOP}/setup; "
                   "echo APPROVALS=$(grep -c Approvals /run/wz-w.html)", 400)
    _, st = b.run(f"{fb.PY} -I -c 'import json; s=json.load(open(\"/data/onemind/firstboot/state.json\")); "
                  "print(\"ROLE=\" + s[\"role\"]); print(\"SOURCE=\" + s[\"source\"]); print(\"HUBADDR=\" + s.get(\"hub_addr\", \"\"))' 2>&1", 60)
    _, j = a.run(f"t0=$SECONDS; while :; do curl -s -H 'Authorization: Bearer {token}' {fb.GW}/v1/fabric > /run/wz-fabric.json; "
                 f"n=$({fb.PY} -I -c 'import json; print(len(json.load(open(\"/run/wz-fabric.json\")).get(\"joining\", [])))' 2>/dev/null); "
                 "[ \"${n:-0}\" -gt 0 ] || [ $((SECONDS - t0)) -ge 600 ] && break; sleep 5; done; echo JOINING=${n:-0}", 700)
    if val(j, "JOINING", "0") == "0":
        _, jr = b.run("journalctl -b --no-pager -n 30 -u onemind-fabric-join 2>&1 | tail -30", 60)
        print(jr[-3000:], flush=True)
    c = {"page": val(out, "HTTP") == "200" and val(out, "APPROVALS", "0") != "0",
         "state": val(st, "ROLE") == "worker" and val(st, "SOURCE") == "wizard" and val(st, "HUBADDR") == LAN["a"],
         "hub_sees_request": val(j, "JOINING", "0") not in ("", "0")}
    record("WZ5", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
           + f" http={val(out, 'HTTP')} role={val(st, 'ROLE')} joining={val(j, 'JOINING')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(battery.BOARDS))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a_ = ap.parse_args()
    dirs = {w: os.path.join(a_.work, w) for w in ("a", "b")}
    for d in dirs.values():
        fb.make_work(a_.fixtures, d)
        os.remove(os.path.join(d, "seed.img"))              # no seed: no role, the wizard runs
    logf = open(a_.log, "w")
    t0 = time.time()
    a = battery.VM(a_.board, dirs["a"], logf, dirs["a"])
    b = battery.VM(a_.board, dirs["b"], logf, dirs["b"])
    env = {"board": a_.board, "accel": a.accel, "cpu": a.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    b.fwd = battery.FWD + 1
    a.extra_args, b.extra_args = link_args("a"), link_args("b")
    rc = 1
    try:
        # One after the other, like firewall.py: B's socket NIC connects to A's only once A is up.
        a.mark("A: boot with no role"); a.start(); a.shell_ready()
        b.mark("B: boot with no role"); b.start(); b.shell_ready()
        _, o = a.run(addr_cmd("a")); _, o2 = b.run(addr_cmd("b"))
        if "ADDR-RC=0" not in o or "ADDR-RC=0" not in o2:
            raise RuntimeError(f"link NIC not configured: a={o[-120:]!r} b={o2[-120:]!r}")
        if not (wizard_up(a) and wizard_up(b)):
            fb.diagnose(a, "Failed to start onemind-setup.service")
            raise RuntimeError("the wizard did not come up on both VMs")
        _, lk = b.run(f"t0=$SECONDS; while :; do c=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 {A_WIZ}/healthz); "
                      "[ \"$c\" != 000 ] || [ $((SECONDS - t0)) -ge 120 ] && break; sleep 3; done; echo LINK=$c", 200)
        if val(lk, "LINK", "000") == "000":
            raise RuntimeError("no LAN link between the VMs: B cannot reach A's 8080 at all")
        a.mark("WZ1-WZ3 on A")
        wz1(a)
        wz2(a, b)
        wz3(a, b)
        a.mark("WZ4 A becomes the hub from the LAN")
        token = wz4(a, b)
        a.mark("WZ5 B becomes a worker on its own screen")
        if token:
            wz5(a, b, token)
        else:
            record("WZ5", False, "no owner token from WZ4, so no join code")
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
    for vm in (a, b):
        if vm.proc and vm.proc.poll() is None:
            vm.kill() if rc else vm.poweroff()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a_.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-WIZARD.md", "results": RESULTS},
                  open(a_.results, "w"), indent=2)
    for d in dirs.values():
        shutil.rmtree(os.path.join(d, "seed"), ignore_errors=True)
        try:
            os.remove(os.path.join(d, "disk.img"))
        except OSError:
            pass
    return 0 if RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
