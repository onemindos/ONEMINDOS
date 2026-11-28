# SPDX-License-Identifier: Apache-2.0
"""A wired address change with an automatic rollback: NS1-NS3 (first-boot battery, around the F3 reboot).
Criteria: test/qemu/CRITERIA-NETWORK-SET.md (pre-registered; never edited to make a result pass).

Imported by firstboot.py. It needs only the battery's VM object (`vm.run(cmd, timeout)` returns (rc, output) from the
guest's root shell) and the caller's `record`. It calls the host service on its socket (curl --unix-socket): the owner
approval and the gateway routes are judged by unit tests, not here (criteria section 1)."""
import ipaddress
import re

SOCK = "/run/onemind/host.sock"
PY = "/usr/lib/onemind/gateway/venv/bin/python3"  # the image has no system python; the gateway venv has one
PROFILE_DIR = "/data/state/etc-NetworkManager-system-connections"
DNS = "192.0.2.53"


def kv(out, key):
    """The last `KEY=value` line of a command's output (the serial echo of the command itself never matches)."""
    return (re.findall(rf"^{key}=(.*?)\s*$", out, re.M) or [""])[-1]


def sh(vm, cmd, timeout):
    """vm.run appends `; echo __RC=...`, so a command must not end in a semicolon (`; ;` is a syntax error)."""
    return vm.run(cmd.rstrip().rstrip(";").rstrip(), timeout)


def call(method, path, body=None, tag="R"):
    """Shell for one host-service call: prints <tag>CODE=<http status>; the body is left in /tmp/ns-<tag>.json."""
    data = f" -H 'Content-Type: application/json' -d '{body}'" if body else ""
    return (f"echo {tag}CODE=$(curl -s -o /tmp/ns-{tag}.json -w '%{{http_code}}' --unix-socket {SOCK} -X {method} "
            f"http://host{path}{data}); ")


# Prints PENDING=<interface|none> and LAST=<result|none> from GET /v1/network/changes.
STATE = (f"curl -s --unix-socket {SOCK} http://host/v1/network/changes | {PY} -c 'import sys,json;d=json.load(sys.stdin);"
         "p=d[\"pending\"];l=d[\"last\"];print(\"PENDING=\"+(p[\"interface\"] if p else \"none\"));"
         "print(\"LAST=\"+(l[\"result\"] if l else \"none\"))'; ")
FIND = ("for i in $(seq 1 45); do nmcli -t -f TYPE,STATE device | grep -q '^ethernet:connected$' && break; sleep 2; done; "
        "DEV=$(nmcli -t -f DEVICE,TYPE,STATE device | awk -F: '$2==\"ethernet\" && $3==\"connected\" {print $1; exit}'); "
        "CON=$(nmcli -g GENERAL.CONNECTION device show $DEV); ")
SNAP = ("echo ADDRS=$(ip -4 -o addr show dev $DEV scope global | awk '{print $4}' | tr '\\n' ,); "
        "echo METHOD=$(nmcli -g ipv4.method connection show \"$CON\"); ")


def diagnose(vm):
    """What a person would ask for first when a change was refused: the answer, the host service's log, and whether
    nmcli runs under the host unit's own sandbox settings."""
    _, out = sh(vm, "echo PBODY=$(head -c 400 /tmp/ns-P.json 2>&1); echo CBODY=$(head -c 300 /tmp/ns-C.json 2>&1); echo ---; journalctl -u onemind-host.service --no-pager -o cat | tail -12; echo ---; "
                "systemd-run --wait --pipe -q -p MemoryDenyWriteExecute=yes -p NoNewPrivileges=yes -p CapabilityBoundingSet=CAP_DAC_READ_SEARCH "
                "-p SystemCallFilter=@system-service -p SystemCallFilter=~@privileged -p RestrictAddressFamilies='AF_INET AF_INET6 AF_UNIX AF_NETLINK' "
                "nmcli -t -g RUNNING general 2>&1 | tail -3; echo ---; "
                "NM=org.freedesktop.NetworkManager; DEVP=$(busctl --system call $NM /org/freedesktop/NetworkManager $NM GetDeviceByIpIface s "
                "$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2==\"ethernet\" {print $1; exit}') 2>&1); echo DEVP=$DEVP; "
                "P=$(echo $DEVP | sed -n 's/^o \"\\(.*\\)\"$/\\1/p'); "
                "for F in 1 0; do echo FLAGS=$F: $(busctl --system call $NM /org/freedesktop/NetworkManager $NM CheckpointCreate aouu 1 \"$P\" 20 $F 2>&1); done; "
                "echo CPS: $(busctl --system get-property $NM /org/freedesktop/NetworkManager $NM Checkpoints 2>&1); nmcli --version 2>&1 | head -1", 120)
    return " DIAG=" + out.replace("\n", " | ")[-1500:]


# NetworkManager's own list of checkpoints, right now.
CPS = ("echo CPS=$(busctl --system get-property org.freedesktop.NetworkManager /org/freedesktop/NetworkManager "
       "org.freedesktop.NetworkManager Checkpoints 2>&1); ")


def static_body(action_id, addr, gw, seconds=20):
    return '{"action_id":"%s","mode":"static","address":"%s","gateway":"%s","dns":["%s"],"rollback_seconds":%d}' % (action_id, addr, gw, DNS, seconds)


def where(vm):
    _, out = sh(vm, FIND + "echo DEV=$DEV; echo CON=\"$CON\"; echo A0=$(ip -4 -o addr show dev $DEV scope global | awk '{print $4}' | head -1); "
                    + SNAP, 200)
    return {"dev": kv(out, "DEV"), "con": kv(out, "CON"), "a0": kv(out, "A0"), "addrs": kv(out, "ADDRS"), "method": kv(out, "METHOD")}


def ns1(vm, record):
    w = where(vm)
    if not (w["dev"] and re.match(r"\d+\.\d+\.\d+\.\d+/\d+$", w["a0"])):
        return record("NS1", False, f"no wired device with a DHCP address: {w}")
    dev, a0 = w["dev"], w["a0"]
    _, out = sh(vm,
        f"DEV={dev}; CON=\"{w['con']}\"; " + call("PUT", f"/v1/network/{dev}", static_body("ns1", "192.0.2.50/24", "192.0.2.1"), "P")
        + "sleep 2; echo APPLIED=$(ip -4 -o addr show dev $DEV | grep -cF 192.0.2.50/24); "
        f"echo OLDGONE=$(ip -4 -o addr show dev $DEV | grep -cF {a0}); " + STATE + SNAP, 120)
    during = {"put": kv(out, "PCODE"), "applied": kv(out, "APPLIED"), "oldgone": kv(out, "OLDGONE"), "pending": kv(out, "PENDING"),
              "method": kv(out, "METHOD")}
    # No confirm. The box has 20 s; wait for the static address to go, then for the lease to come back.
    _, out = sh(vm,
        f"DEV={dev}; CON=\"{w['con']}\"; "
        "for i in $(seq 1 60); do ip -4 -o addr show dev $DEV | grep -qF 192.0.2.50/24 || break; sleep 1; done; "
        "for i in $(seq 1 60); do ip -4 -o addr show dev $DEV scope global | grep -q inet && break; sleep 1; done; "
        "echo STATIC_LEFT=$(ip -4 -o addr show dev $DEV | grep -cF 192.0.2.50/24); " + SNAP
        + "echo CONADDRS=$(nmcli -g ipv4.addresses connection show \"$CON\"); " + STATE, 200)
    after = {"static_left": kv(out, "STATIC_LEFT"), "addrs": kv(out, "ADDRS"), "method": kv(out, "METHOD"),
             "conaddrs": kv(out, "CONADDRS"), "pending": kv(out, "PENDING"), "last": kv(out, "LAST")}
    c = {"applied": during["put"] == "200" and during["applied"] == "1" and during["oldgone"] == "0",
         "pending_during": during["pending"] == dev and during["method"] == "manual",
         "rolled_back_address": after["static_left"] == "0" and after["addrs"] == a0 + ",",
         "method_auto": after["method"] == "auto" and after["conaddrs"] == "",
         "nothing_pending": after["pending"] == "none", "last_rolled_back": after["last"] == "rolled_back"}
    detail = " ".join(f"{k}={v}" for k, v in c.items()) + f" dev={dev} a0={a0} during={during} after={after}"
    record("NS1", all(c.values()), detail + ("" if during["put"] == "200" else diagnose(vm)))


def ns2_before(vm, record):
    """Static address = ADDR0 itself (criteria section 4), confirmed; it must outlive the window. Returns what ns2_after uses."""
    w = where(vm)
    try:
        ifc = ipaddress.ip_interface(w["a0"])
        gw = str(ifc.network.network_address + 2)
    except ValueError:
        record("NS2", False, f"no wired device with a DHCP address: {w}")
        return None
    dev = w["dev"]
    _, out = sh(vm,
        f"DEV={dev}; CON=\"{w['con']}\"; T0=$(date +%s); " + call("PUT", f"/v1/network/{dev}", static_body("ns2-static", w["a0"], gw), "P")
        + "echo PUT_SECONDS=$(( $(date +%s) - T0 )); " + CPS
        + call("POST", f"/v1/network/{dev}/confirm", '{"action_id":"ns2-static"}', "C") + STATE
        + "sleep 30; " + SNAP + "echo DNS=$(nmcli -g ipv4.dns connection show \"$CON\"); "
        f"F=$(grep -lx \"id=$CON\" {PROFILE_DIR}/*.nmconnection | head -1); echo MODE=$(stat -c %a \"$F\" 2>&1); " + STATE, 200)
    got = {"put": kv(out, "PCODE"), "confirm": kv(out, "CCODE"), "addrs": kv(out, "ADDRS"), "method": kv(out, "METHOD"),
           "dns": kv(out, "DNS"), "mode": kv(out, "MODE"), "pending": kv(out, "PENDING"), "last": kv(out, "LAST")}
    got["put_seconds"], got["cps_after_put"] = kv(out, "PUT_SECONDS"), kv(out, "CPS")
    if got["confirm"] != "200":
        got["diag"] = diagnose(vm)
    return {"dev": dev, "con": w["con"], "a0": w["a0"], "gw": gw, "before": got}


def ns2_after(vm, record, st, rebooted=True):
    if st is None:
        return
    b = st["before"]
    _, out = sh(vm,
        FIND + "echo DEV2=$DEV; " + SNAP + "echo DNS=$(nmcli -g ipv4.dns connection show \"$CON\"); "
        + call("PUT", f"/v1/network/{st['dev']}", '{"action_id":"ns2-dhcp","mode":"dhcp","rollback_seconds":20}', "P")
        + call("POST", f"/v1/network/{st['dev']}/confirm", '{"action_id":"ns2-dhcp"}', "C")
        + "for i in $(seq 1 60); do nmcli -g IP4.ADDRESS device show $DEV | grep -q . && break; sleep 1; done; sleep 3; "
        "echo BACKADDRS=$(ip -4 -o addr show dev $DEV scope global | awk '{print $4}' | tr '\\n' ,); "
        "echo BACKMETHOD=$(nmcli -g ipv4.method connection show \"$CON\"); "
        "echo BACKCONADDRS=$(nmcli -g ipv4.addresses connection show \"$CON\"); echo BACKDNS=$(nmcli -g ipv4.dns connection show \"$CON\"); " + STATE, 300)
    c = {"changed_ok": b["put"] == "200" and b["confirm"] == "200" and b["pending"] == "none" and b["last"] == "confirmed",
         "static_after_window": b["method"] == "manual" and st["a0"] in b["addrs"] and b["dns"] == DNS,
         "mode_600": b["mode"] == "600",
         "static_after_reboot": kv(out, "DEV2") == st["dev"] and kv(out, "METHOD") == "manual" and st["a0"] in kv(out, "ADDRS")
         and kv(out, "DNS") == DNS,
         "dhcp_again": kv(out, "PCODE") == "200" and kv(out, "CCODE") == "200" and kv(out, "BACKMETHOD") == "auto",
         "profile_clean": kv(out, "BACKCONADDRS") == "" and kv(out, "BACKDNS") == "",
         "lease_back": kv(out, "BACKADDRS") == st["a0"] + ",", "confirmed": kv(out, "PENDING") == "none" and kv(out, "LAST") == "confirmed"}
    record("NS2", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" rebooted={rebooted} before={b}")


def ns3(vm, record):
    w = where(vm)
    dev = w["dev"]
    if not dev:
        return record("NS3", False, f"no wired device: {w}")
    ok = '{"action_id":"ns3","mode":"static","address":"192.0.2.50/24","gateway":"192.0.2.1"}'
    cases = [("lo", ok), ("nosuch0", ok), (dev, '{"action_id":"ns3","mode":"static","address":"192.0.2.50/24"}'),
             (dev, '{"action_id":"ns3","mode":"static","address":"192.0.2.50/24","gateway":"198.51.100.1"}')]
    shell = f"DEV={dev}; CON=\"{w['con']}\"; " + SNAP
    for i, (name, body) in enumerate(cases):
        shell += call("PUT", f"/v1/network/{name}", body, f"R{i}")
    shell += call("POST", f"/v1/network/{dev}/confirm", '{"action_id":"ns3"}', "R4") + f"echo REASON=$({PY} -c 'import json;print(json.load(open(\"/tmp/ns-R4.json\")).get(\"reason\"))'); " \
        "echo AFTER; " + SNAP.replace("ADDRS", "ADDRS2").replace("METHOD", "METHOD2")
    _, out = sh(vm, shell, 200)
    codes = [kv(out, f"R{i}CODE") for i in range(5)]
    c = {"all_refused": all(re.match(r"4\d\d$", x) for x in codes), "confirm_409_no_pending": codes[4] == "409" and kv(out, "REASON") == "no_pending_change",
         "unchanged": kv(out, "ADDRS") == kv(out, "ADDRS2") != "" and kv(out, "METHOD") == kv(out, "METHOD2")}
    record("NS3", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" codes={codes} addrs={kv(out, 'ADDRS')} method={kv(out, 'METHOD')}")
