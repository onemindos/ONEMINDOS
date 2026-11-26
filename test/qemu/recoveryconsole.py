# SPDX-License-Identifier: Apache-2.0
"""Owner recovery on the box: RC1 (first-boot battery). Criteria: test/qemu/CRITERIA-RECOVERY.md (pre-registered;
never edited to make a result pass).

Imported by firstboot.py (RC1 right after F15, on the slot-A boot). It needs only the battery's VM object
(`vm.run(cmd, timeout)` returns (rc, output) from the guest's root shell) and the caller's `record`. It types nothing
on any console: what a person would see on ttyN is read from /dev/vcsN."""
import re

UNIT = "onemind-recovery-console.service"
MENU = ("Press Enter to start", "OneMind owner recovery")


def kv(out, key):
    """The last `KEY=value` line of a command's output (the serial echo of the command itself never matches)."""
    return (re.findall(rf"^{key}=(.*?)\s*$", out, re.M) or [""])[-1]


# Wait up to $2 seconds for /dev/vcs$1 to contain the fixed string $3; print 1 if it did, else 0.
WAIT_VCS = ('wv() { i=0; while [ $i -lt "$2" ]; do tr -s " " < /dev/vcs$1 2>/dev/null | grep -aqF "$3" && { echo 1; return; }; '
            'sleep 1; i=$((i+1)); done; echo 0; }; ')

# The image has no kbd package, so no chvt binary: the same two ioctls chvt makes (VT_ACTIVATE 0x5606, then
# VT_WAITACTIVE 0x5607 on /dev/tty0), with the image's own python3. A chvt that exists is used as it is.
CHVT = ("command -v chvt >/dev/null 2>&1 || chvt() { timeout 10 python3 -c 'import fcntl, os, sys; "
        "fd = os.open(\"/dev/tty0\", os.O_RDWR | os.O_NOCTTY); n = int(sys.argv[1]); "
        "fcntl.ioctl(fd, 0x5606, n); fcntl.ioctl(fd, 0x5607, n)' \"$1\"; }; ")

SCRIPT = (
    WAIT_VCS + CHVT +
    f"echo EN=$(systemctl is-enabled {UNIT} 2>&1 | head -1); "
    f"i=0; while [ $i -lt 60 ] && [ \"$(systemctl is-active {UNIT})\" != active ]; do sleep 1; i=$((i+1)); done; "
    f"echo ACT=$(systemctl is-active {UNIT}); echo NR=$(systemctl show -p NRestarts --value {UNIT}); "
    "chvt 3; "
    f"echo MENU1=$(wv 3 30 '{MENU[0]}'); echo MENU2=$(wv 3 1 '{MENU[1]}'); "
    "echo G3=$(systemctl is-active getty@tty3.service)/$(systemctl is-active autovt@tty3.service); "
    "C=$(systemd-analyze cat-config systemd/logind.conf 2>/dev/null | grep -v '^[#;]' | tr -d ' '); "
    "echo NAUTO=$(echo \"$C\" | sed -n 's/^NAutoVTs=//p' | tail -1); "
    "echo RESV=$(echo \"$C\" | sed -n 's/^ReserveVT=//p' | tail -1); "
    "echo G2EN=$(systemctl is-enabled getty@tty2.service 2>&1 | head -1); echo G2ACT=$(systemctl is-active getty@tty2.service); "
    "chvt 2; echo LOGIN2=$(wv 2 30 'login:'); "
    "chvt 4; sleep 5; echo G4=$(systemctl is-active autovt@tty4.service)/$(systemctl is-active getty@tty4.service); "
    "echo LOGIN4=$(wv 4 1 'login:'); "
    "chvt 1; echo RCDONE=1"
)


def rc1_judge(out):
    """RC1's verdict from the guest's output (pure, so test/unit can feed it canned text)."""
    nr = kv(out, "NR")
    g3, g4 = kv(out, "G3").split("/"), kv(out, "G4").split("/")
    return {
        "unit_enabled": kv(out, "EN") == "enabled",
        "unit_active": kv(out, "ACT") == "active",
        "no_crash_loop": nr in ("0", "1"),
        "menu_on_tty3": kv(out, "MENU1") == "1" and kv(out, "MENU2") == "1",
        "no_getty_tty3": len(g3) == 2 and "active" not in g3 and g3 != [""],
        "logind_vts": kv(out, "NAUTO") == "2" and kv(out, "RESV") == "0",
        "tty2_getty": kv(out, "G2EN") == "enabled" and kv(out, "G2ACT") == "active",
        "tty2_login_prompt": kv(out, "LOGIN2") == "1",
        "no_login_tty4": len(g4) == 2 and "active" not in g4 and g4 != [""] and kv(out, "LOGIN4") == "0",
        "finished": kv(out, "RCDONE") == "1",
    }


def rc1(vm, record):
    _, out = vm.run(SCRIPT, 180)
    c = rc1_judge(out)
    record("RC1", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items()) + f" nrestarts={kv(out, 'NR')!r}")
