# SPDX-License-Identifier: Apache-2.0
"""NetworkManager on the hardware boards: NW1-NW4 (first-boot battery) and FW5 (firewall battery).
Criteria: test/qemu/CRITERIA-NETWORK.md (pre-registered; never edited to make a result pass).

Imported by firstboot.py (NW1-NW4 around the F3 reboot) and firewall.py (FW5). It needs only the battery's VM
object (`vm.run(cmd, timeout)` returns (rc, output) from the guest's root shell) and the caller's `record`."""
import re

PROFILE = "onemind-nw-probe"
PROFILE_DIR = "/data/state/etc-NetworkManager-system-connections"
PROFILE_FILE = f"{PROFILE_DIR}/{PROFILE}.nmconnection"
UNMANAGED = ("flannel*", "cni0", "veth*", "tailscale0")


def kv(out, key):
    """The last `KEY=value` line of a command's output (the serial echo of the command itself never matches)."""
    return (re.findall(rf"^{key}=(.*?)\s*$", out, re.M) or [""])[-1]


# One shell fragment that prints K3SFIRST=<seconds since boot of the first k3s journal line this boot>.
K3S_FIRST = ("echo K3SFIRST=$(journalctl -b -u k3s.service -o short-monotonic -q --no-pager | head -1 "
             "| sed -n 's/^\\[ *\\([0-9]*\\.[0-9]*\\)\\].*/\\1/p')")
# ... and the two monotonic stamps (microseconds) NW2 and FW5 compare.
STAMPS = ("echo NMSTART=$(systemctl show NetworkManager.service -p ActiveEnterTimestampMonotonic --value); "
          "echo WOEND=$(systemctl show NetworkManager-wait-online.service -p ActiveEnterTimestampMonotonic --value)")


def seconds(us):
    return int(us) / 1e6 if us.isdigit() and int(us) > 0 else None


def nw1(vm, record):
    wait_up = ("for i in $(seq 1 45); do nmcli -t -f TYPE,STATE device | grep -q '^ethernet:connected$' && break; sleep 2; done; "
               "DEV=$(nmcli -t -f DEVICE,TYPE,STATE device | awk -F: '$2==\"ethernet\" && $3==\"connected\" {print $1; exit}'); ")
    _, out = vm.run(
        "echo STACK=$(cat /usr/lib/onemind/network-stack); "
        "echo NMEN=$(systemctl is-enabled NetworkManager.service); echo WOEN=$(systemctl is-enabled NetworkManager-wait-online.service); "
        "echo NDACT=$(systemctl is-active systemd-networkd.service); echo NMACT=$(systemctl is-active NetworkManager.service); "
        + wait_up +
        "echo ETH=$DEV; echo IP4=$(ip -4 -o addr show dev $DEV scope global | awk '{print $4}' | head -1); "
        "echo METHOD=$(nmcli -g ipv4.method connection show \"$(nmcli -g GENERAL.CONNECTION device show $DEV)\"); "
        "echo LEASE=$(( $(nmcli -t device show $DEV | grep -Ec 'DHCP4\\.OPTION\\[[0-9]+\\]:ip_address = [0-9]') + "
        "$(grep -l '^ADDRESS=' /var/lib/NetworkManager/*.lease 2>/dev/null | wc -l) )); "
        "echo DNSCONF=$(NetworkManager --print-config | grep -c '^dns=systemd-resolved'); "
        "echo DNSMODE=$(busctl get-property org.freedesktop.NetworkManager /org/freedesktop/NetworkManager/DnsManager "
        "org.freedesktop.NetworkManager.DnsManager Mode | sed 's/^s //; s/\"//g'); "
        "echo RESOLVED=$(systemctl is-active systemd-resolved.service); echo RESOLV=$(readlink /etc/resolv.conf); "
        "echo WPA=$(wpa_supplicant -v 2>&1 | head -1); echo IW=$(iw --version 2>&1 | head -1); rfkill list >/dev/null 2>&1; echo RFKILL=$?; "
        "echo REGDB=$(dpkg-query -W -f='${Status}' wireless-regdb 2>&1); echo REGDBFILE=$(ls /lib/firmware/regulatory.db 2>&1)", 300)
    g = lambda k: kv(out, k)
    c = {"stack": g("STACK") == "networkmanager",
         "enabled": g("NMEN") == "enabled" and g("WOEN") == "enabled" and g("NMACT") == "active",
         "networkd_not_active": g("NDACT") != "active",
         "ethernet_connected": bool(g("ETH")),
         "ipv4": re.match(r"\d+\.\d+\.\d+\.\d+/\d+$", g("IP4")) is not None,
         "dhcp_lease": g("METHOD") == "auto" and g("LEASE").isdigit() and int(g("LEASE")) >= 1,
         "dns_is_resolved": g("DNSCONF") == "1" and g("DNSMODE") == "systemd-resolved" and g("RESOLVED") == "active"
         and g("RESOLV").endswith("stub-resolv.conf"),
         "wifi_tools": g("WPA").startswith("wpa_supplicant") and g("IW").startswith("iw version") and g("RFKILL") == "0",
         "regdb": "install ok installed" in g("REGDB") and g("REGDBFILE") == "/lib/firmware/regulatory.db"}
    detail = " ".join(f"{k}={v}" for k, v in c.items()) + f" eth={g('ETH')} ip4={g('IP4')} dnsmode={g('DNSMODE')!r} wpa={g('WPA')!r} iw={g('IW')!r}"
    if not all(c.values()):     # what a person would ask for first, so a red run explains itself
        _, dg = vm.run("ip -4 route; echo ---; ls -l /var/lib/NetworkManager; echo ---; nmcli -t device show $(nmcli -t -f DEVICE,TYPE device | awk -F: '$2==\"ethernet\" {print $1; exit}') | grep -E 'DHCP4|IP4' | head -30; echo ---; nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device; echo ---; resolvectl status | head -30; "
                       "echo ---; journalctl -b -u NetworkManager --no-pager -o cat | tail -25", 120)
        detail += " DIAG=" + dg.replace("\n", " | ")[-1800:]
    record("NW1", all(c.values()), detail)


def nw2(vm, record):
    _, out = vm.run("echo AFTER=$(systemctl show k3s -p After --value); echo WANTS=$(systemctl show k3s -p Wants --value); "
                    + STAMPS + "; " + K3S_FIRST, 120)
    wo, first = seconds(kv(out, "WOEND")), kv(out, "K3SFIRST")
    first = float(first) if re.match(r"\d+\.\d+$", first) else None
    c = {"after": "NetworkManager-wait-online.service" in kv(out, "AFTER").split(),
         "wants": "NetworkManager-wait-online.service" in kv(out, "WANTS").split(),
         "wait_online_ran": wo is not None, "k3s_first_start_seen": first is not None,
         "k3s_after_wait_online": wo is not None and first is not None and wo <= first}
    record("NW2", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" wait_online_end={wo} k3s_first_start={first}")


def nw3(vm, record):
    names = ["flannelnw0", "cni0", "vethnw0", "tailscale0"]
    mk = ("ip link add flannelnw0 type dummy; ip link add vethnw0 type dummy; "
          "ip link show cni0 >/dev/null 2>&1 && echo MADE_CNI=0 || { ip link add cni0 type dummy && echo MADE_CNI=1; }; "
          "ip link show tailscale0 >/dev/null 2>&1 && echo MADE_TS=0 || { ip link add tailscale0 type dummy && echo MADE_TS=1; }; "
          "sleep 5; ")
    st = "".join(f"echo ST_{n}=$(nmcli -g GENERAL.STATE device show {n} 2>&1 | head -1); " for n in names)
    clean = ("ip link del flannelnw0; ip link del vethnw0; [ \"$MADE_CNI\" = 1 ] && ip link del cni0; "
             "[ \"$MADE_TS\" = 1 ] && ip link del tailscale0; true")
    # MADE_* are read back from this command's own output, so the cleanup is a second command.
    _, out = vm.run(mk + st + "echo CONF=$(NetworkManager --print-config | grep '^unmanaged-devices=')", 120)
    vm.run(("MADE_CNI=%s MADE_TS=%s; " % (kv(out, "MADE_CNI") or 0, kv(out, "MADE_TS") or 0)) + clean, 60)
    conf = kv(out, "CONF")
    c = {f"conf_{n}": f"interface-name:{n}" in conf for n in UNMANAGED}
    c.update({f"unmanaged_{n}": "unmanaged" in kv(out, f"ST_{n}") for n in names})
    record("NW3", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" conf={conf!r}")


def nw4_before(vm):
    """Save a profile; returns what NW4 compares after the reboot."""
    _, out = vm.run(
        f"nmcli connection add type ethernet ifname nwprobe0 con-name {PROFILE} autoconnect no "
        "ipv4.method manual ipv4.addresses 192.0.2.77/24 >/dev/null; echo ADD_RC=$?; sync; "
        f"echo MODE=$(stat -c %a {PROFILE_FILE} 2>&1); echo SHA=$(sha256sum {PROFILE_FILE} 2>&1 | cut -c1-64); "
        "echo MNT1=$(findmnt -n -o SOURCE /etc/NetworkManager/system-connections); echo MNT2=$(findmnt -n -o SOURCE /var/lib/NetworkManager); echo DROOT=$(findmnt -n -o FSROOT /data | head -1)", 120)
    # /data starts at "/" on ext4 and at "/@" on the btrfs layout (#152), so the bind's root is "<where /data starts>/state/...".
    droot = kv(out, "DROOT").rstrip("/") if kv(out, "DROOT") else None
    return {"add_rc": kv(out, "ADD_RC"), "mode": kv(out, "MODE"), "sha": kv(out, "SHA"),
            "bind1": droot is not None and f"[{droot}/state/etc-NetworkManager-system-connections]" in kv(out, "MNT1"),
            "bind2": droot is not None and f"[{droot}/state/var-lib-NetworkManager]" in kv(out, "MNT2")}


def nw4_after(vm, record, before, rebooted=True):
    """After the F3 reboot (or, when the run stops before F3, right away): the profile is still there; then delete it."""
    _, out = vm.run(
        "for i in $(seq 1 45); do nmcli -t -f TYPE,STATE device | grep -q '^ethernet:connected$' && break; sleep 2; done; "
        "echo NAMES=,$(nmcli -g NAME connection show | tr '\\n' ,); "
        f"echo SHA=$(sha256sum {PROFILE_FILE} 2>&1 | cut -c1-64); echo MODE=$(stat -c %a {PROFILE_FILE} 2>&1); "
        "echo UP=$(nmcli -t -f TYPE,STATE device | grep -c '^ethernet:connected$'); "
        f"nmcli connection delete {PROFILE} >/dev/null; echo DEL_RC=$?; echo LEFT=$(ls {PROFILE_DIR} | grep -c {PROFILE})", 300)
    c = {"added": before.get("add_rc") == "0",
         "mode_600": before.get("mode") == "600" and kv(out, "MODE") == "600",
         "bind_mounts_from_data": before.get("bind1") and before.get("bind2"),
         "listed": f",{PROFILE}," in kv(out, "NAMES"),
         "file_unchanged": len(before.get("sha", "")) == 64 and kv(out, "SHA") == before.get("sha"),
         "wired_up": kv(out, "UP") not in ("", "0"),
         "deleted": kv(out, "DEL_RC") == "0" and kv(out, "LEFT") == "0"}
    record("NW4", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" rebooted={rebooted}")


def fw5(vm, record):
    """The firewall battery's box has a second NIC with a link and no DHCP server (CRITERIA-NETWORK.md FW5)."""
    _, out = vm.run(STAMPS + "; " + K3S_FIRST + "; echo NICS=$(nmcli -t -f TYPE device | grep -c '^ethernet$')", 120)
    nm, wo = seconds(kv(out, "NMSTART")), seconds(kv(out, "WOEND"))
    first = kv(out, "K3SFIRST")
    first = float(first) if re.match(r"\d+\.\d+$", first) else None
    span = None if nm is None or wo is None else wo - nm
    c = {"two_ethernet_devices": kv(out, "NICS").isdigit() and int(kv(out, "NICS")) >= 2,
         "span_at_most_30s": span is not None and span <= 30,
         "k3s_within_10s_of_online": wo is not None and first is not None and first <= wo + 10}
    detail = " ".join(f"{k}={v}" for k, v in c.items()) + f" nm_start={nm} online_end={wo} span={span} k3s_first={first}"
    if not all(c.values()):
        _, dg = vm.run("nmcli general status; echo ---; nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device; echo ---; "
                       "journalctl -b -u NetworkManager-wait-online --no-pager -o cat | tail -5; echo ---; "
                       "journalctl -b -u NetworkManager --no-pager -o cat | grep -E 'state is now|dhcp4|Activation|startup' | tail -20", 120)
        detail += " DIAG=" + dg.replace("\n", " | ")[-1800:]
    record("FW5", all(c.values()), detail)
