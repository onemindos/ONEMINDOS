#!/usr/bin/env python3
"""LAB-secureboot-1152 test E1 (pre-registered here; first run as exploratory in
../../secureboot-rauc). Adds the T9/H4 slot-detection probe in the E1 state.

Question: if neither OneMind boot entry can start, the firmware walks BootOrder
into its own auto-created entries. The removable-media entry boots the ESP's
factory loader (signed UKI-A v1). Does that old, validly signed kernel boot
under Secure Boot against whatever root filesystem slot A now holds, and does
the TPM (PCR 7) still unlock the data?

Runs on the end state of a finished run-tests.py run directory.
  python3 -I e1-factory-fallback.py --run /var/lab/sbrun2 --log e1.log
"""
import argparse, importlib.util, os, re, sys

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rt", os.path.join(here, "run-tests.py"))
rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)

ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--log", required=True)
a = ap.parse_args()
vm = rt.VM(a.run, open(a.log, "w"))
vm.mark("E1 boot normally (Secure Boot on)"); vm.start(f"{a.run}/OVMF_VARS.fd")
vm.gate(); vm.shell()
_, eo = vm.run("efibootmgr")
auto = re.search(r"Boot([0-9A-F]{4})\* UEFI Misc Device\s", eo)
vm.mark(f"E1 simulate 'both OneMind entries unbootable': BootNext -> firmware auto entry {auto.group(1)}")
vm.run(f"efibootmgr -q -n {auto.group(1)}")
i = vm.here(); vm.send("systemctl reboot")
g = vm.gate(); vm.shell(); seg = vm.since(i)
_, st = vm.run("cat /etc/onemind-release; cat /proc/cmdline; mokutil --sb-state; mountpoint /data")
kv = re.search(r"onemind\.version=(\d+)", seg); rv = re.search(r"ONEMIND_VERSION=(\d+)", st)
res = (f"E1 RESULT: kernel(UKI) version={kv.group(1) if kv else '?'} rootfs version={rv.group(1) if rv else '?'} "
       f"SecureBoot={'enabled' if 'SecureBoot enabled' in st else 'NOT enabled'} "
       f"data={'UNLOCKED' if 'UNLOCK OK' in seg else 'locked'} gate={g}")
vm.mark(res)
_, rv2 = vm.run("rauc --version; rauc status 2>&1 | grep -E '^Booted from|^Activated'; efibootmgr | grep -E '^Boot(Current|Order)'")
vm.mark("E1 rauc view: " + " | ".join(l for l in rv2.splitlines() if l.strip() and "__R" not in l)[:400])
pout, pst = rt.probe(vm, "E1 state")
vm.mark("E1 PROBE status with rauc.slot hidden: " + pst.replace(chr(10), " / "))
vm.stop()
