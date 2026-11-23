#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, signed host extensions only (T-W19-01, X0-X7, O1-O2). Criteria: test/qemu/CRITERIA-SYSEXT.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's VM driver and firstboot.py's fixtures.

Why: host add-ons (plugin socket E3) reach the read-only image as systemd system and configuration extensions.
Founder decision Z-22 lets other developers publish them in release 1 only if an unsigned or wrongly signed
extension never merges after a reboot or an A/B slot switch. This test builds signed, wrongly signed, unsigned,
naked and directory extensions inside the guest with throwaway keys, plays a one-time root, reboots and switches
slots, and checks what merged.

  python3 -I sysextguard.py --board x86_64-efi --fixtures DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, base64, binascii, importlib.util, json, os, platform, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RESULTS = []
SYSEXT = ("good", "wrong", "unsigned", "naked", "plaindir")
CONFEXT = ("confgood", "confunsigned", "confdir")
NEGATIVE = ("wrong", "unsigned", "naked", "confunsigned")     # must never merge
DATA = "/data/onemind-tw19"          # images and public test certificates (persistent, not an extension folder)
KEYS = "/run/tw19-keys"              # throwaway private keys: RAM only, gone at the next boot
SLOT = "/run/tw19-slot"              # a non-recursive bind of / while the slot root is remounted read-write
KIT = "/run/tw19-kit"                # the seed disk (CIDATA), where the image builder script travels
CERT = "/usr/lib/verity.d/onemind-tw19-test.crt"
DROPIN = "systemd/system/systemd-sysext.service.d/99-tw19-plant.conf"
PLANT = r"[Service]\nExecStartPre=\nExecStart=\nExecStart=systemd-sysext refresh\n"
SX_POLICY = "ExecStart=systemd-sysext refresh --mutable=no --image-policy=root=signed+absent:usr=signed+absent"
CX_POLICY = "ExecStart=systemd-confext refresh --mutable=no --image-policy=root=signed+absent"
ARCH = {"x86_64-efi": "x86-64"}

# GPT partition types (Discoverable Partitions Specification; checked with `systemd-id128 show` on Debian 13).
PARTS = {
    "x86-64": dict(usr="8484680c-9521-48c6-9c11-b0720656f69e", usrv="77ff5f63-e7b6-4633-acf4-1565b864c0e6",
                   usrs="e7bb33fb-06cf-4e81-8273-e543b413e2e2", root="4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                   rootv="2c7357ed-ebd2-46d9-aec1-23d437ec2bf5", roots="41092b05-9fc8-4523-994f-2def0408b176"),
    "arm64": dict(usr="b0e01050-ee5f-4390-949a-9101b17104e9", usrv="6e11a4e7-fbca-4ded-b9e9-e1a512bb664e",
                  usrs="c23ce4ff-44bd-4b00-b2d4-b41b3419e02a", root="b921b045-1df0-41c3-af44-4c6f280d3fae",
                  rootv="df3300ce-d69f-4c92-978c-9bfb0f38d820", roots="6db69de6-29f4-4758-a7a5-962190f00ce3"),
}


def kit_script(arch):
    """The in-guest image builder (POSIX sh; the image has no system Python). Arguments: OUT KEYS WORK.
    Makes two throwaway key pairs, then good/wrong/unsigned (GPT + dm-verity [+ signature]), naked (bare
    squashfs) and plaindir (directory) sysexts, and confgood/confunsigned/confdir confexts."""
    p = PARTS[arch]
    return f"""#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# T-W19-01 test extension builder (test/qemu/sysextguard.py). Throwaway keys only.
set -eu
O=$1; K=$2; W=$3
mkdir -p "$O/img" "$K" "$W"; chmod 700 "$K"
for k in trusted wrong; do
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -sha256 -keyout "$K/$k.key" -out "$K/$k.crt" \\
    -subj "/O=OneMind TEST/CN=tw19-$k" 2>/dev/null
  cp "$K/$k.crt" "$O/$k.crt"
done
uuid() {{ echo "$1" | sed -E 's/^(.{{8}})(.{{4}})(.{{4}})(.{{4}})(.{{12}}).*/\\1-\\2-\\3-\\4-\\5/'; }}
mib() {{ echo $(( ($(stat -c %s "$1") + 1048575) / 1048576 )); }}
tree() {{ # NAME sysext|confext -> $W/tree-NAME
  t="$W/tree-$1"; rm -rf "$t"
  if [ "$2" = sysext ]; then
    mkdir -p "$t/usr/lib/extension-release.d" "$t/usr/lib/onemind-tw19"
    printf 'ID=debian\\nSYSEXT_LEVEL=1\\n' > "$t/usr/lib/extension-release.d/extension-release.$1"
    echo "$1" > "$t/usr/lib/onemind-tw19/$1"
  else
    mkdir -p "$t/etc/extension-release.d" "$t/etc/onemind-tw19"
    printf 'ID=debian\\nCONFEXT_LEVEL=1\\n' > "$t/etc/extension-release.d/extension-release.$1"
    echo "$1" > "$t/etc/onemind-tw19/$1"
  fi
}}
start() {{ sfdisk -d "$1" | grep '^/' | sed -n "$2p" | sed 's/.*start= *\\([0-9]*\\),.*/\\1/'; }}
ddi() {{ # NAME sysext|confext trusted|wrong|none
  tree "$1" "$2"; t="$W/tree-$1"; f="$W/$1"
  mksquashfs "$t" "$f.fs" -noappend -quiet -all-root >/dev/null
  veritysetup format "$f.fs" "$f.vy" > "$f.vs"
  rh=$(sed -n 's/^Root hash:[[:space:]]*//p' "$f.vs"); [ "${{#rh}}" -eq 64 ]
  if [ "$2" = sysext ]; then D={p['usr']}; V={p['usrv']}; S={p['usrs']}
  else D={p['root']}; V={p['rootv']}; S={p['roots']}; fi
  ds=$(mib "$f.fs"); hs=$(mib "$f.vy"); n=$((1 + ds + hs + 2))
  img="$O/img/$1.raw"; rm -f "$img"; truncate -s "${{n}}M" "$img"
  {{ echo "label: gpt"
    echo "size=${{ds}}MiB, type=$D, uuid=$(uuid "$(echo "$rh" | cut -c1-32)")"
    echo "size=${{hs}}MiB, type=$V, uuid=$(uuid "$(echo "$rh" | cut -c33-64)")"
    if [ "$3" != none ]; then echo "size=1MiB, type=$S"; fi
  }} | sfdisk -q "$img"
  dd if="$f.fs" of="$img" bs=512 seek="$(start "$img" 1)" conv=notrunc status=none
  dd if="$f.vy" of="$img" bs=512 seek="$(start "$img" 2)" conv=notrunc status=none
  if [ "$3" != none ]; then
    printf %s "$rh" > "$f.rh"
    openssl smime -sign -nocerts -noattr -binary -in "$f.rh" -inkey "$K/$3.key" -signer "$K/$3.crt" -outform der -out "$f.p7s"
    printf '{{"rootHash":"%s","signature":"%s"}}' "$rh" "$(base64 -w0 "$f.p7s")" > "$f.sig"
    dd if="$f.sig" of="$img" bs=512 seek="$(start "$img" 3)" conv=notrunc status=none
  fi
  echo "TW19-KIT: built $1 kind=$2 signer=$3 roothash=$rh"
}}
ddi good sysext trusted; ddi wrong sysext wrong; ddi unsigned sysext none
ddi confgood confext trusted; ddi confunsigned confext none
tree naked sysext; mksquashfs "$W/tree-naked" "$O/img/naked.raw" -noappend -quiet -all-root >/dev/null
tree plaindir sysext; rm -rf "$O/img/plaindir"; cp -a "$W/tree-plaindir" "$O/img/plaindir"
tree confdir confext; rm -rf "$O/img/confdir"; cp -a "$W/tree-confdir" "$O/img/confdir"
rm -rf "$W"
echo "TW19-KIT: ok $(ls "$O/img" | tr '\\n' ' ')"
"""


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def tag(out, name):
    """Last NAME=value line the guest printed (the echoed command holds NAME=$(...), never a value)."""
    vals = [v for v in re.findall(rf"^{re.escape(name)}=([^\s$]*)", out, re.M) if v]
    return vals[-1] if vals else ""


def listed(b64):
    """Extension names in `systemd-sysext status --json=short` (base64 on one line; "none" when nothing merged)."""
    try:
        data = json.loads(base64.b64decode(b64 or "W10=").decode() or "[]")
    except (ValueError, binascii.Error):
        return set()
    names = set()
    for h in data if isinstance(data, list) else []:
        ext = h.get("extensions") if isinstance(h, dict) else None
        if isinstance(ext, list):
            names.update(str(e) for e in ext)
    return names


def merged_from(out):
    """{name: merged}. Merged = marker file visible AND listed by systemd-*ext status (CRITERIA-SYSEXT.md §1)."""
    names = listed(tag(out, "SXJ")) | listed(tag(out, "CXJ"))
    return {n: tag(out, f"M_{n}") == "1" and n in names for n in SYSEXT + CONFEXT}


def state(vm):
    cmd = ("for n in " + " ".join(SYSEXT) + "; do echo \"M_$n=$(test -e /usr/lib/onemind-tw19/$n && echo 1 || echo 0)\"; done; "
           "for n in " + " ".join(CONFEXT) + "; do echo \"M_$n=$(test -e /etc/onemind-tw19/$n && echo 1 || echo 0)\"; done; "
           "echo \"SXJ=$(systemd-sysext status --json=short 2>/dev/null | base64 -w0)\"; "
           "echo \"CXJ=$(systemd-confext status --json=short 2>/dev/null | base64 -w0)\"; "
           "echo \"VERITY=$(for d in /sys/block/dm-*/dm; do [ -e $d/uuid ] && { grep -q '^CRYPT-VERITY-' $d/uuid || grep -q -- '-verity$' $d/name; } && echo v; done | grep -c v)\"; "
           "echo \"SX_UNIT=$(systemctl is-active systemd-sysext.service)\"; echo \"CX_UNIT=$(systemctl is-active systemd-confext.service)\"; "
           "echo \"SX_AT=$(systemctl show -p ActiveEnterTimestampMonotonic --value systemd-sysext.service)\"; "
           "echo \"K3S_AT=$(systemctl show -p InactiveExitTimestampMonotonic --value k3s.service)\"; "
           "echo \"REFUSED=$(journalctl -b -o cat --no-pager -u systemd-sysext.service -u systemd-confext.service | grep -c 'ONEMIND-SYSEXT-GUARD: refused')\"; "
           "echo \"R_plaindir=$(journalctl -b -o cat --no-pager -u systemd-sysext.service | grep -c 'refused sysext path=/var/lib/extensions/plaindir ')\"; "
           "echo \"R_confdir=$(journalctl -b -o cat --no-pager -u systemd-confext.service | grep -c 'refused confext path=/var/lib/confexts/confdir ')\"; "
           "echo \"SLOTNOW=$(sed -n 's/.*rauc\\.slot=\\([AB]\\).*/\\1/p' /proc/cmdline)\"")
    _, out = vm.run(cmd, 300)
    vm.run("journalctl -b -o cat --no-pager -u systemd-sysext.service -u systemd-confext.service | tail -n 20", 120)
    m = merged_from(out)
    extra = {k: tag(out, k) for k in ("VERITY", "SX_UNIT", "CX_UNIT", "SX_AT", "K3S_AT", "REFUSED", "R_plaindir", "R_confdir", "SLOTNOW")}
    return m, extra


def short(m):
    return ",".join(n for n, v in m.items() if v) or "none"


def slot_write(vm, script):
    """The slot-rewriting one-time root: remount the slot root read-write and run `script` with $S = a
    non-recursive bind of / (the slot itself: no /usr or /etc overlay, no /data). Remounted read-only after."""
    rc, out = vm.run(f"mount -o remount,rw / && mkdir -p {SLOT} && mount --bind / {SLOT} && S={SLOT} && ( {script} ); "
                     f"rc=$?; umount {SLOT}; mount -o remount,ro / 2>/dev/null; test $rc -eq 0", 120)
    return rc == 0


def trust(vm):
    return slot_write(vm, f"mkdir -p $S/usr/lib/verity.d && cp {DATA}/trusted.crt $S{CERT}")


def reboot(vm, tag_):
    vm.mark(tag_)
    vm.send("systemctl reboot")
    g = vm.wait_gate()
    vm.shell_ready()
    return g


def place(vm, sx=(), cx=()):
    cmds = [f"cp -a {DATA}/img/{n}{'' if n.endswith('dir') else '.raw'} /var/lib/extensions/" for n in sx]
    cmds += [f"cp -a {DATA}/img/{n}{'' if n.endswith('dir') else '.raw'} /var/lib/confexts/" for n in cx]
    rc, _ = vm.run(" && ".join(cmds), 120) if cmds else (0, "")
    return rc == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(ARCH))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    fb = _load("firstboot_harness", "firstboot.py")     # make_work, CONFIGURED (its battery import is run-tests.py)
    battery = fb.battery
    fb.make_work(a.fixtures, a.work)
    kit = os.path.join(a.work, "tw19-mkddi.sh")
    open(kit, "w").write(kit_script(ARCH[a.board]))
    subprocess.run(["mcopy", "-o", "-i", os.path.join(a.work, "seed.img"), kit, "::/tw19-mkddi.sh"], check=True)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    vm.failfast = True
    alive = False
    try:
        vm.mark("X0 first boot: the image is wired for signed-only extensions")
        vm.start()
        vm.expect(fb.CONFIGURED, 900)
        g = vm.wait_gate()
        vm.shell_ready()
        alive = True
        _, out = vm.run(
            "echo \"LVL=$(grep -c -x -E 'SYSEXT_LEVEL=1|CONFEXT_LEVEL=1' /usr/lib/os-release)\"; "
            "echo \"EN=$(systemctl is-enabled systemd-sysext.service systemd-confext.service | tr '\\n' ,)\"; "
            f"echo \"SXPOL=$(systemctl cat systemd-sysext.service | grep -c -x -F '{SX_POLICY}')\"; "
            f"echo \"CXPOL=$(systemctl cat systemd-confext.service | grep -c -x -F '{CX_POLICY}')\"; "
            "echo \"SXG=$(systemctl cat systemd-sysext.service | grep -c -x -F 'ExecStartPre=/usr/lib/onemind/sysext-guard sysext')\"; "
            "echo \"CXG=$(systemctl cat systemd-confext.service | grep -c -x -F 'ExecStartPre=/usr/lib/onemind/sysext-guard confext')\"; "
            "echo \"EXT=$(test -d /var/lib/extensions && readlink -f /var/lib/extensions)\"; "
            "echo \"CONF=$(test -d /var/lib/confexts && readlink -f /var/lib/confexts)\"; "
            "echo \"BEF=$(systemctl show -p Before --value systemd-sysext.service | tr ' ' '\\n' | grep -c -x k3s.service)\"; "
            "echo \"KEYDIRS=$(ls -d /etc/verity.d /run/verity.d 2>/dev/null | wc -l)\"", 120)
        x0 = {k: tag(out, k) for k in ("LVL", "EN", "SXPOL", "CXPOL", "SXG", "CXG", "EXT", "CONF", "BEF", "KEYDIRS")}
        record("X0", x0["LVL"] == "2" and x0["EN"] == "enabled,enabled," and x0["SXPOL"] == "1" and x0["CXPOL"] == "1"
               and x0["SXG"] == "1" and x0["CXG"] == "1" and x0["EXT"] == "/data/state/var-lib-extensions"
               and x0["CONF"] == "/data/state/var-lib-confexts" and x0["BEF"] == "1" and x0["KEYDIRS"] == "0",
               f"gate={g} {x0}")

        vm.mark("build the test extensions in the guest (throwaway keys)")
        rc, out = vm.run(f"mkdir -p {KIT} && (mountpoint -q {KIT} || mount -o ro LABEL=CIDATA {KIT}) && "
                         f"sh {KIT}/tw19-mkddi.sh {DATA} {KEYS} /run/tw19-work 2>&1 | tail -n 12; test ${{PIPESTATUS[0]}} -eq 0", 900)
        if rc != 0 or "TW19-KIT: ok" not in out:
            raise RuntimeError("the in-guest extension builder failed (see the serial log)")

        vm.mark("X1 positive control: only the signed images, trusted certificate in /usr")
        ok = trust(vm) and place(vm, ["good"], ["confgood"])
        g = reboot(vm, "X1 reboot")
        m, e = state(vm)
        before_k3s = e["SX_AT"].isdigit() and e["K3S_AT"].isdigit() and 0 < int(e["SX_AT"]) <= int(e["K3S_AT"])
        record("X1", ok and m["good"] and m["confgood"] and int(e["VERITY"] or 0) >= 1 and before_k3s,
               f"setup={ok} gate={g} merged={short(m)} verity_devices={e['VERITY']} sysext_active_at={e['SX_AT']} "
               f"k3s_started_at={e['K3S_AT']} units={e['SX_UNIT']}/{e['CX_UNIT']}")

        vm.mark("X2 wrongly signed, unsigned and naked raw images")
        ok = place(vm, ["wrong", "unsigned", "naked"], ["confunsigned"])
        g = reboot(vm, "X2 reboot")
        m, e = state(vm)
        record("X2", ok and not any(m[n] for n in NEGATIVE),
               f"setup={ok} gate={g} merged={short(m)} (good/confgood recorded only) units={e['SX_UNIT']}/{e['CX_UNIT']}")

        vm.mark("X3 plain one-time root plants a key and a drop-in")
        _, out = vm.run(f"mkdir -p /run/verity.d /run/systemd/system/systemd-sysext.service.d && "
                        f"cp {DATA}/wrong.crt /run/verity.d/tw19-wrong.crt && printf '{PLANT}' > /run/{DROPIN}; "
                        f"echo \"RUNPLANT=$(test -f /run/verity.d/tw19-wrong.crt && test -f /run/{DROPIN} && echo 1)\"; "
                        f"echo \"ETCKEY=$( (mkdir -p /etc/verity.d && cp {DATA}/wrong.crt /etc/verity.d/tw19-wrong.crt) 2>/dev/null && echo written || echo refused)\"; "
                        f"echo \"ETCDROP=$( (mkdir -p /etc/systemd/system/systemd-sysext.service.d && printf '{PLANT}' > /etc/{DROPIN}) 2>/dev/null && echo written || echo refused)\"", 120)
        plant = {k: tag(out, k) for k in ("RUNPLANT", "ETCKEY", "ETCDROP")}
        _, out = vm.run("systemctl daemon-reload; systemctl restart systemd-sysext.service; "
                        "echo \"O1=$(test -e /usr/lib/onemind-tw19/wrong && echo merged || echo not-merged)\"", 300)
        record("O1", "OBSERVED", f"with the plant in place, a run-time restart: wrong {tag(out, 'O1')}")
        g = reboot(vm, "X3 reboot")
        _, out = vm.run(f"echo \"GONE=$(ls /run/verity.d/tw19-wrong.crt /run/{DROPIN} /etc/verity.d /etc/{DROPIN} 2>/dev/null | wc -l)\"", 60)
        m, e = state(vm)
        record("X3", plant["RUNPLANT"] == "1" and plant["ETCKEY"] == "refused" and plant["ETCDROP"] == "refused"
               and tag(out, "GONE") == "0" and not any(m[n] for n in NEGATIVE),
               f"plant={plant} gate={g} planted_files_left={tag(out, 'GONE')} merged={short(m)}")

        vm.mark("X4 plain directories")
        ok = place(vm, ["plaindir"], ["confdir"])
        g = reboot(vm, "X4 reboot")
        m, e = state(vm)
        record("X4", ok and not any(m.values()) and e["R_plaindir"] not in ("", "0") and e["R_confdir"] not in ("", "0"),
               f"setup={ok} gate={g} merged={short(m)} refusals={e['REFUSED']} plaindir_refused={e['R_plaindir']} "
               f"confdir_refused={e['R_confdir']} units={e['SX_UNIT']}/{e['CX_UNIT']}")

        vm.mark("X5 slot-rewriting one-time root on slot A, then a slot switch to B")
        rc, _ = vm.run("rm -rf /var/lib/extensions/plaindir /var/lib/confexts/confdir", 60)
        planted = slot_write(vm, f"mkdir -p $S/etc/verity.d $S/etc/systemd/system/systemd-sysext.service.d && "
                                 f"cp {DATA}/wrong.crt $S/etc/verity.d/tw19-wrong.crt && printf '{PLANT}' > $S/etc/{DROPIN}")
        irc, _ = battery.install(vm, "good.raucb")
        g = reboot(vm, "X5 reboot into the other slot")
        _, out = vm.run(f"echo \"LEFT=$(ls /etc/verity.d /etc/{DROPIN} /usr/lib/verity.d 2>/dev/null | wc -l)\"", 60)
        m, e = state(vm)
        record("X5", rc == 0 and planted and irc == 0 and g == ("mark-good", "B", "2") and e["SLOTNOW"] == "B"
               and tag(out, "LEFT") == "0" and not any(m.values()),
               f"planted_on_A={planted} install_rc={irc} gate={g} slot={e['SLOTNOW']} files_on_B={tag(out, 'LEFT')} merged={short(m)}")

        vm.mark("X6 slot B trusts the test key; only the signed images present")
        held = f"{DATA}/held"
        rc, _ = vm.run(f"mkdir -p {held} && mv /var/lib/extensions/wrong.raw /var/lib/extensions/unsigned.raw "
                       f"/var/lib/extensions/naked.raw /var/lib/confexts/confunsigned.raw {held}/", 60)
        ok = rc == 0 and trust(vm)
        g = reboot(vm, "X6 reboot")
        m, e = state(vm)
        record("X6", ok and m["good"] and m["confgood"], f"setup={ok} gate={g} merged={short(m)} verity_devices={e['VERITY']}")

        vm.mark("X7 the negative images back on slot B")
        rc, _ = vm.run(f"mv {held}/wrong.raw {held}/unsigned.raw {held}/naked.raw /var/lib/extensions/ && "
                       f"mv {held}/confunsigned.raw /var/lib/confexts/", 60)
        g = reboot(vm, "X7 reboot")
        m, e = state(vm)
        record("X7", rc == 0 and not any(m[n] for n in NEGATIVE), f"setup={rc == 0} gate={g} merged={short(m)} (good/confgood recorded only)")

        vm.mark("O2 slot-rewriting one-time root on the running slot B, same-slot reboot")
        planted = slot_write(vm, f"mkdir -p $S/etc/verity.d $S/etc/systemd/system/systemd-sysext.service.d && "
                                 f"cp {DATA}/wrong.crt $S/etc/verity.d/tw19-wrong.crt && printf '{PLANT}' > $S/etc/{DROPIN}")
        g = reboot(vm, "O2 reboot")
        m, e = state(vm)
        record("O2", "OBSERVED", f"planted={planted} gate={g} merged={short(m)}: wrong {'merged' if m['wrong'] else 'not merged'} "
               "(a root that rewrites the running slot is the job of a dm-verity root and Secure Boot, #148)")
    except (TimeoutError, RuntimeError) as err:
        record("HARNESS", False, f"aborted: {err}")
        alive = False
    if alive:
        vm.poweroff()
    elif vm.proc and vm.proc.poll() is None:
        vm.kill()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-SYSEXT.md",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    return 0 if verdict_ok(RESULTS) else 1


def verdict_ok(results):
    """T-W19-01 passes when X0-X7 are all PASS and nothing FAILed (CRITERIA-SYSEXT.md §4)."""
    need = {f"X{i}" for i in range(8)}
    got = {r["test"] for r in results if r["verdict"] == "PASS"}
    return need <= got and all(r["verdict"] in ("PASS", "OBSERVED") for r in results)


if __name__ == "__main__":
    sys.exit(main())
