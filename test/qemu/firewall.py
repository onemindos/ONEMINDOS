#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, host firewall (FW1-FW4, FWP1). Criteria: test/qemu/CRITERIA-FIREWALL.md (pre-registered).
FW6-FW8 (owner allow rules with automatic revert, P-09 part 2; pre-registered as FW5-FW7, renumbered because
netcheck.py owns FW5) follow in the same session; criteria: test/qemu/CRITERIA-FIREWALL-ALLOW.md (pre-registered).

Two VMs boot the fixture image: the box (hub seed) and a scanner (no seed, so no role: the setup wizard runs).
A QEMU socket link joins them with two address pairs, a LAN one and a documentation-range "public" one. The
scanner probes the box from both; the box counts what its firewall dropped (counting rules at the end of the
input chain), so the verdict does not depend on the scanner reading silence correctly. Then the box probes the
scanner's wizard port from both addresses. Run: make firewall BOARD=x86_64-efi (CI image workflow; first run there).
"""
import argparse, importlib.util, json, os, platform, re, shlex, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load("firstboot_h", "firstboot.py")
battery = fb.battery

LINK_PORT = int(os.environ.get("ONEMIND_QEMU_LINK_PORT", "18770"))
MAC = {"box": "52:54:00:fe:00:01", "scan": "52:54:00:fe:00:02"}
ADDR = {"lan": {"box": "192.168.77.1", "scan": "192.168.77.2"}, "pub": {"box": "198.51.100.1", "scan": "198.51.100.2"}}
TCP = [22, 80, 443, 445, 631, 4222, 6443, 7422, 7443, 8080, 8443, 8444, 10250]
UDP = [3478, 5353, 8472, 9999, 41641, 51820]
WANT_LAN = {("tcp", p) for p in (443, 631, 7443, 8443, 8444)} | {("udp", p) for p in (3478, 5353, 41641)}
PROBE_PY = r'''
import socket, sys, threading
src, dst, tcp, udp = sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3].split(",") if x], [int(x) for x in sys.argv[4].split(",") if x]
def t(p):
    s = socket.socket(); s.settimeout(1.5); s.bind((src, 0))
    try:
        s.connect((dst, p)); r = "open"
    except ConnectionRefusedError:
        r = "refused"
    except OSError:
        r = "timeout"
    print("T", p, r, flush=True)
def u(p):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(1.5); s.bind((src, 0))
    for _ in range(2):
        s.sendto(b"x", (dst, p))
    print("U", p, "sent", flush=True)
th = [threading.Thread(target=t, args=(p,)) for p in tcp] + [threading.Thread(target=u, args=(p,)) for p in udp]
[x.start() for x in th]; [x.join() for x in th]
print("PROBE-DONE", flush=True)
'''
LISTEN_PY = r'''
import socket, threading, time
def serve(p):
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("0.0.0.0", p)); s.listen(16)
    while True:
        c, _ = s.accept(); c.close()
for p in (39091, 39092, 39093):
    threading.Thread(target=serve, args=(p,), daemon=True).start()
time.sleep(1800)
'''
ALLOW_TTL_S = 60
HOST_SOCK = "/run/onemind/host.sock"
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def link_args(who):
    nd = f"socket,id=fwlink,{'listen' if who == 'box' else 'connect'}=127.0.0.1:{LINK_PORT}"
    return ["-netdev", nd, "-device", f"virtio-net-pci,netdev=fwlink,mac={MAC[who]}"]


def addr_cmd(who):
    """Bring up the link NIC (found by MAC) with both of this side's addresses."""
    a = [ADDR[k][who] for k in ("lan", "pub")]
    return (f"IF=$(ip -o link | awk '/{MAC[who]}/ {{sub(\":\",\"\",$2); print $2; exit}}'); echo IF=$IF; "
            # NetworkManager boards: the test link is not the box's network, so NetworkManager must leave it alone (else its
            # default DHCP profile re-activates the NIC and flushes the addresses set here while the scan runs)
            f"if command -v nmcli >/dev/null; then nmcli device set $IF managed no; fi; "
            f"ip link set $IF up && ip addr add {a[0]}/24 dev $IF && ip addr add {a[1]}/24 dev $IF; echo ADDR-RC=$?")


def probe(vm, src, dst, tcp, udp):
    fb.send_file(vm, "/run/fwprobe.py", PROBE_PY)
    _, out = vm.run(f"{fb.PY} -I /run/fwprobe.py {src} {dst} '{','.join(map(str, tcp))}' '{','.join(map(str, udp))}'; rm -f /run/fwprobe.py", 120)
    return out


def counters_script():
    lines = []
    for tag in ("lan", "pub"):
        for proto, ports in (("tcp", TCP), ("udp", UDP)):
            for p in ports:
                lines.append(f'add rule inet onemind_host input ip saddr {ADDR[tag]["scan"]} {proto} dport {p} '
                             f'counter comment "scan-{tag}-{proto}-{p}"')
    return "\n".join(lines) + "\n"


def read_counters(vm):
    _, out = vm.run("nft list chain inet onemind_host input | awk '/scan-/ {p=\"\"; for(i=1;i<=NF;i++) if($i==\"packets\") p=$(i+1); "
                    "match($0,/scan-[a-z]+-[a-z]+-[0-9]+/); print \"CNT \" substr($0,RSTART,RLENGTH), p}'")
    c = {}
    for tag, proto, port, n in re.findall(r"^CNT scan-(\w+)-(\w+)-(\d+) (\d+)\s*$", out, re.M):
        c[(tag, proto, int(port))] = int(n)
    return c


def host_api(vm, method, path, body=None):
    """One call on the host service's own socket, as root on the box (what the gateway does after an approval)."""
    data = f"-H 'Content-Type: application/json' -d {shlex.quote(json.dumps(body))}" if body is not None else ""
    _, out = vm.run(f"curl -s -o /run/fwapi.out -w 'HTTP=%{{http_code}}' --unix-socket {HOST_SOCK} -X {method} {data} http://host{path}; echo; "
                    "cat /run/fwapi.out; echo; rm -f /run/fwapi.out", 30)
    m = re.search(r"^HTTP=(\d{3})\s*$", out, re.M)
    code = int(m.group(1)) if m else 0
    j = re.search(r"^(\{.*\})\s*$", out, re.M)
    try:
        doc = json.loads(j.group(1)) if j else None
    except ValueError:
        doc = None
    return code, doc


def open_ports(scan, tag, box, ports):
    """The ports of `ports` the scanner reaches on the box from this address (tag: lan or pub)."""
    out = probe(scan, ADDR[tag]["scan"], ADDR[tag]["box"], ports, [])
    return {int(p) for p in re.findall(r"^T (\d+) open", out, re.M)}


def owner_chain(box, name):
    _, out = box.run(f"nft list chain inet onemind_host {name}")
    return out


def wait_host_service(box, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        code, doc = host_api(box, "GET", "/v1/status")
        if code == 200:
            return True
        time.sleep(2)
    return False


K3S_PORTS = {6443, 10250}
LISTEN_RE = re.compile(r"^LISTEN (?:\*|0\.0\.0\.0|\[::\]|::):(\d+)\s*$", re.M)
SS_CMD = "ss -H -ltn | awk '{print \"LISTEN \" $4}'"


def wildcard_listening(ss):
    """Ports a `LISTEN <addr>:<port>` listing shows bound to every address (not just loopback)."""
    return {int(x) for x in LISTEN_RE.findall(ss)}


def wait_k3s_listening(vm, timeout=600, step=5, clock=time.time, sleep=time.sleep):
    """k3s (Type=notify, starts after the gateway is healthy) opens 6443 and 10250 some time after first boot, so
    the scan must not run before it. Poll the box for both wildcard listeners, bounded; return (listening, ss)."""
    end, ss = clock() + timeout, ""
    while True:
        _, ss = vm.run(SS_CMD)
        have = wildcard_listening(ss)
        if K3S_PORTS <= have or clock() >= end:
            return have, ss
        sleep(step)


def allow_tests(box, scan):
    """FW6-FW8 (CRITERIA-FIREWALL-ALLOW.md): owner allow rules, their automatic revert, and their scope."""
    box.mark("allow rules: short deadline, restart the host service, start three listeners")
    box.run("mkdir -p /run/systemd/system/onemind-host.service.d && printf '[Service]\\nEnvironment=ONEMIND_HOST_FIREWALL_TTL=%ss\\n' "
            f"{ALLOW_TTL_S} > /run/systemd/system/onemind-host.service.d/ttl.conf && systemctl daemon-reload && systemctl restart onemind-host; echo RESTART-RC=$?", 60)
    if not wait_host_service(box):
        record("FW6", "BLOCKED", "the host service did not answer on its socket after the restart")
        return
    code, view = host_api(box, "GET", "/v1/firewall")
    supported = code == 200 and isinstance(view, dict) and (view.get("allow") or {}).get("supported") is True
    fb.send_file(box, "/run/fwlisten.py", LISTEN_PY)
    box.run(f"(nohup {fb.PY} -I /run/fwlisten.py >/dev/null 2>&1 &)", 10)
    time.sleep(2)
    rule = lambda i, port, scope: {"id": i, "proto": "tcp", "port": port, "scope": scope}
    a = host_api(box, "POST", "/v1/firewall/allow", rule("fwa-1", 39091, "lan"))
    b = host_api(box, "POST", "/v1/firewall/allow", rule("fwb-1", 39092, "lan"))
    c = host_api(box, "POST", "/v1/firewall/allow", rule("fwc-1", 39093, "mesh"))
    pending = all(x[0] == 200 and (x[1] or {}).get("state") == "pending" for x in (a, b, c))
    bad_scopes = [host_api(box, "POST", "/v1/firewall/allow", {"id": f"fwx-{i}", "proto": "tcp", "port": 9094, "scope": sc})[0]
                  for i, sc in enumerate(("wan", "any", "0.0.0.0/0"))]
    no_wan = all(x == 409 for x in bad_scopes) and "9094" not in owner_chain(box, "owner_lan") + owner_chain(box, "owner_mesh")
    ports = [39091, 39092, 39093]
    lan0, pub0 = open_ports(scan, "lan", box, ports), open_ports(scan, "pub", box, ports)
    cb = host_api(box, "POST", "/v1/firewall/allow/fwb-1/confirm")
    time.sleep(ALLOW_TTL_S + 10)
    lan1 = open_ports(scan, "lan", box, ports)
    lan_chain = owner_chain(box, "owner_lan")
    ca = host_api(box, "POST", "/v1/firewall/allow/fwa-1/confirm")
    record("FW6", supported and pending and lan0 == {39091, 39092} and cb[0] == 200 and lan1 == {39092}
           and "39092" in lan_chain and "39091" not in lan_chain and ca[0] == 404,
           f"supported={supported} add={[x[0] for x in (a, b, c)]} pending={pending} open_at_first={sorted(lan0)} confirm_b={cb[0]} "
           f"open_after_deadline={sorted(lan1)} chain_has_39091={'39091' in lan_chain} chain_has_39092={'39092' in lan_chain} confirm_a_after_revert={ca[0]}")
    host_api(box, "POST", "/v1/firewall/allow", rule("fwd-1", 39091, "lan"))
    box.run("systemctl restart onemind-host; echo RESTART-RC=$?", 60)
    back = wait_host_service(box)
    lan2 = open_ports(scan, "lan", box, ports)
    chain2 = owner_chain(box, "owner_lan")
    rm = host_api(box, "DELETE", "/v1/firewall/allow/fwb-1")
    lan3 = open_ports(scan, "lan", box, ports)
    record("FW7", back and lan2 == {39092} and "39092" in chain2 and "39091" not in chain2 and rm[0] == 200 and not lan3,
           f"host_back={back} open_after_restart={sorted(lan2)} chain_has_39092={'39092' in chain2} chain_has_39091={'39091' in chain2} "
           f"remove_b={rm[0]} open_after_remove={sorted(lan3)}")
    lan4 = open_ports(scan, "lan", box, ports)
    record("FW8", not pub0 and 39093 not in lan0 and 39093 not in lan1 and no_wan,
           f"open_from_public_while_allowed={sorted(pub0)} mesh_rule_open_from_lan={39093 in lan0 or 39093 in lan1} "
           f"bad_scope_answers={bad_scopes} wan_in_chain={not no_wan} open_from_lan_at_end={sorted(lan4)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(battery.BOARDS))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    box_dir, scan_dir = os.path.join(a.work, "box"), os.path.join(a.work, "scanner")
    fb.make_work(a.fixtures, box_dir)
    fb.make_work(a.fixtures, scan_dir)
    os.remove(os.path.join(scan_dir, "seed.img"))          # no seed: no role, the wizard runs
    logf = open(a.log, "w")
    t0 = time.time()
    box = battery.VM(a.board, box_dir, logf, box_dir)
    scan = battery.VM(a.board, scan_dir, logf, scan_dir)
    env = {"board": a.board, "accel": box.accel, "cpu": box.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    scan.fwd = battery.FWD + 1
    box.extra_args, scan.extra_args = link_args("box"), link_args("scan")
    box.failfast = True
    rc = 1
    try:
        box.mark("box: first boot as hub")
        box.start()
        box.expect(fb.CONFIGURED, 900)
        box.pos = 0
        box.wait_gate()
        box.shell_ready()
        hz = fb.http_code(box, f"{fb.GW}/healthz", timeout=900)
        if hz != "200":
            fb.diagnose(box, f"healthz={hz}")
            raise RuntimeError(f"gateway /healthz={hz}")
        box.mark("box: wait for k3s to listen (bounded)")
        have, _ = wait_k3s_listening(box)
        if not K3S_PORTS <= have:
            box.mark(f"k3s not listening after wait: {sorted(have)}")
        box.mark("scanner: boot with no role")
        scan.start()
        scan.shell_ready()
        _, o = box.run(addr_cmd("box")); _, o2 = scan.run(addr_cmd("scan"))
        if "ADDR-RC=0" not in o or "ADDR-RC=0" not in o2:
            raise RuntimeError(f"link NIC not configured: box={o[-120:]!r} scanner={o2[-120:]!r}")
        fb.send_file(box, "/run/fwcount.nft", counters_script())
        rc_n, o = box.run("nft -f /run/fwcount.nft; echo NFT-RC=$?")
        _, ping = scan.run(f"ping -c 2 -W 2 {ADDR['lan']['box']} >/dev/null 2>&1; echo PING=$?")
        box.mark("scan the box from the LAN and the public address")
        for tag in ("lan", "pub"):
            probe(scan, ADDR[tag]["scan"], ADDR[tag]["box"], TCP, UDP)
        time.sleep(2)
        cnt = read_counters(box)
        _, ss = box.run(SS_CMD)
        reach = {t: {(p, n) for (tg, p, n), v in cnt.items() if tg == t and v == 0} for t in ("lan", "pub")}
        complete = all(len([k for k in cnt if k[0] == t]) == len(TCP) + len(UDP) for t in ("lan", "pub"))
        alive = any(v > 0 for v in cnt.values())    # the link works: something was dropped
        record("FW1", complete and alive and reach["lan"] == WANT_LAN,
               f"reachable_from_lan={sorted(reach['lan'])} want={sorted(WANT_LAN)} counters={len(cnt)} ping={'ok' if 'PING=0' in ping else 'no'}")
        record("FW2", complete and alive and not reach["pub"], f"reachable_from_public={sorted(reach['pub'])}")
        listening = wildcard_listening(ss)
        k3s = K3S_PORTS
        record("FW3", k3s <= listening and not any(("tcp", p) in reach[t] for p in k3s for t in reach),
               f"k3s_listening_wildcard={sorted(k3s & listening)} reachable_lan={sorted(p for p in k3s if ('tcp', p) in reach['lan'])} "
               f"reachable_public={sorted(p for p in k3s if ('tcp', p) in reach['pub'])}")
        fb.netcheck.fw5(box, record)
        _, w = scan.run("systemctl is-active onemind-setup; echo WIZ=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/)")
        wiz_up = "WIZ=200" in w and re.search(r"^active\s*$", w, re.M) is not None
        res = {}
        for tag in ("lan", "pub"):
            out = probe(box, ADDR[tag]["box"], ADDR[tag]["scan"], [8080], [])
            res[tag] = (re.findall(r"^T 8080 (\w+)", out, re.M) or ["none"])[-1]
        record("FW4", wiz_up and res["lan"] == "open" and res["pub"] != "open" and ("tcp", 8080) not in reach["lan"],
               f"wizard_running={wiz_up} 8080_from_lan={res['lan']} 8080_from_public={res['pub']} box_8080_from_lan={'open' if ('tcp', 8080) in reach['lan'] else 'dropped'}")
        code = lambda src, dst, path: scan.run(
            f"echo CODE=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 8 --interface {src} http://{dst}:631{path})")[1]
        cc = lambda o: (re.findall(r"^CODE=(\d+)", o, re.M) or ["none"])[-1]
        lan = {p: cc(code(ADDR["lan"]["scan"], ADDR["lan"]["box"], p)) for p in ("/", "/admin", "/admin/conf", "/admin/log")}
        pub = cc(code(ADDR["pub"]["scan"], ADDR["pub"]["box"], "/"))
        record("FWP1", complete and lan["/"] == "200" and all(lan[p] == "403" for p in ("/admin", "/admin/conf", "/admin/log"))
               and pub == "000" and ("tcp", 631) in reach["lan"] and ("tcp", 631) not in reach["pub"],
               f"lan={lan} public={pub} counter_lan_accepts_631={('tcp', 631) in reach['lan']} counter_public_accepts_631={('tcp', 631) in reach['pub']}")
        allow_tests(box, scan)
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
    for vm in (box, scan):
        if vm.proc and vm.proc.poll() is None:
            vm.kill() if rc else vm.poweroff()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-FIREWALL.md", "results": RESULTS},
                  open(a.results, "w"), indent=2)
    for d in (box_dir, scan_dir):
        shutil.rmtree(os.path.join(d, "seed"), ignore_errors=True)
        try:
            os.remove(os.path.join(d, "disk.img"))
        except OSError:
            pass
    return 0 if RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
