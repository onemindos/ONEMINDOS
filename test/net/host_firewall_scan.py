#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Port scan of the host firewall (os/.../onemind/host.nft) from a second machine, with real nftables.

A "box" network namespace gets the ruleset and a listener on every port we care about. Two "client"
namespaces stand in for second machines: one on a LAN address, one on a public address. Each port is probed:
a listener that answers means the firewall let it through, silence (timeout) means it was dropped. A
refused connection would mean "no listener", which is why every port has one. Needs root, `ip` and `nft`:

  sudo python3 -I test/net/host_firewall_scan.py          (exit 0 = every expectation held)
"""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES = os.path.join(ROOT, "os/rootfs/layers/onemind/usr/lib/onemind/host.nft")
TCP = [22, 80, 445, 443, 8080, 8443, 8444, 7443, 6443, 10250, 4222, 7422]
UDP = [5353, 3478, 41641, 8472, 51820, 9999]
# Expected from each client (everything else must be dropped).
LAN_TCP, LAN_UDP = {443, 8443, 8444, 7443}, {5353, 3478, 41641}
PUB_TCP, PUB_UDP = set(), set()
NS = {"box": "ofw-box", "lan": "ofw-lan", "pub": "ofw-pub"}


def sh(*a, check=True, **k):
    return subprocess.run(a, check=check, capture_output=True, text=True, **k)


def ns(name, *cmd, **k):
    return sh("ip", "netns", "exec", NS[name], *cmd, **k)


def setup():
    for n in NS.values():
        sh("ip", "netns", "add", n)
    for peer, net, box_ip, cl_ip in (("lan", "172.31.250", "172.31.250.1", "172.31.250.2"),
                                     ("pub", "198.51.100", "198.51.100.1", "198.51.100.2")):
        sh("ip", "link", "add", f"v{peer}b", "type", "veth", "peer", "name", f"v{peer}c")
        sh("ip", "link", "set", f"v{peer}b", "netns", NS["box"])
        sh("ip", "link", "set", f"v{peer}c", "netns", NS[peer])
        ns("box", "ip", "addr", "add", box_ip + "/24", "dev", f"v{peer}b")
        ns(peer, "ip", "addr", "add", cl_ip + "/24", "dev", f"v{peer}c")
        for n, dev in (("box", f"v{peer}b"), (peer, f"v{peer}c")):
            ns(n, "ip", "link", "set", dev, "up")
            ns(n, "ip", "link", "set", "lo", "up")
    ns("box", "nft", "-f", RULES)


def teardown():
    for n in NS.values():
        sh("ip", "netns", "delete", n, check=False)


LISTENER = r"""
import socket, selectors, sys
sel = selectors.DefaultSelector()
for p in %r:
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("0.0.0.0", p)); s.listen(8)
    sel.register(s, selectors.EVENT_READ, "t")
for p in %r:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("0.0.0.0", p)); sel.register(s, selectors.EVENT_READ, "u")
print("ready", flush=True)
while True:
    for k, _ in sel.select():
        if k.data == "t":
            k.fileobj.accept()[0].close()
        else:
            d, a = k.fileobj.recvfrom(64); k.fileobj.sendto(d, a)
"""


def probe(client, ip):
    got_t, got_u = set(), set()
    for p in TCP:
        c = ns(client, sys.executable, "-I", "-c",
               f"import socket;s=socket.socket();s.settimeout(1.5)\n"
               f"try: s.connect(('{ip}',{p}));print('open')\nexcept Exception: print('closed')")
        if c.stdout.strip() == "open":
            got_t.add(p)
    for p in UDP:
        c = ns(client, sys.executable, "-I", "-c",
               f"import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(1.5)\n"
               f"s.sendto(b'x',('{ip}',{p}))\n"
               f"try: s.recvfrom(8);print('open')\nexcept Exception: print('closed')")
        if c.stdout.strip() == "open":
            got_u.add(p)
    return got_t, got_u


def tcp_open(client, ip, port):
    c = ns(client, sys.executable, "-I", "-c",
           f"import socket;s=socket.socket();s.settimeout(1.5)\n"
           f"try: s.connect(('{ip}',{port}));print('open')\nexcept Exception: print('closed')")
    return c.stdout.strip() == "open"


def setup_wizard_phase():
    """The wizard (8080) is open to the LAN only while onemind-setup.service has its rule in the setup chain."""
    ok = True
    for label, rule, want_lan in (("no role yet (wizard running)", True, True), ("wizard exited", False, False)):
        if rule:
            ns("box", "nft", "add", "rule", "inet", "onemind_host", "setup", "tcp", "dport", "8080", "accept")
        else:
            ns("box", "nft", "flush", "chain", "inet", "onemind_host", "setup")
        lan, pub = tcp_open("lan", "172.31.250.1", 8080), tcp_open("pub", "198.51.100.1", 8080)
        good = lan == want_lan and not pub
        ok &= good
        print(f"8080 {label}: lan={lan} want={want_lan} public={pub} want=False -> {'PASS' if good else 'FAIL'}")
    return ok


def main():
    if os.geteuid() != 0:
        print("needs root"); return 2
    teardown()
    ok = True
    try:
        setup()
        srv = subprocess.Popen(["ip", "netns", "exec", NS["box"], sys.executable, "-I", "-c", LISTENER % (TCP, UDP)],
                               stdout=subprocess.PIPE, text=True)
        assert srv.stdout.readline().strip() == "ready"
        time.sleep(0.3)
        for client, ip, wt, wu in (("lan", "172.31.250.1", LAN_TCP, LAN_UDP), ("pub", "198.51.100.1", PUB_TCP, PUB_UDP)):
            t, u = probe(client, ip)
            good = t == wt and u == wu
            ok &= good
            print(f"{client}: tcp open={sorted(t)} want={sorted(wt)} udp open={sorted(u)} want={sorted(wu)} -> "
                  f"{'PASS' if good else 'FAIL'}")
        ok &= setup_wizard_phase()
        srv.kill()
    finally:
        teardown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
