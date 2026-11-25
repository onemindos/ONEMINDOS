#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, power cut in the first minute (F13, F14). Criteria: test/qemu/CRITERIA-FIRSTBOOT.md §9
(pre-registered; never edited to make a result pass). VM 501 bug 1 (2026-11-25): a power cut about 45 s after the
first boot left k3s's keys, certificates, token and node password empty and k3s never came back. Refs #234.

A power cut is SIGKILL of QEMU (guest memory is lost, the disk image keeps what the guest flushed).
  F13  first boot as a hub (NoCloud seed, as F1); 25 s after the "configured" console line, power cut; boot again:
       same box, no new owner token, committed boot, k3s healthy, no empty k3s file.
  F14  on that healthy box: write owner/app/gateway markers, stop k3s, empty every k3s file, power cut, boot again:
       the repair ran, k3s healthy, markers and token intact, the damaged files kept in the quarantine.

Needs the battery's fixtures (`make fixtures`). Run: make powercut BOARD=x86_64-efi (Linux with KVM).
"""
import argparse, hashlib, importlib.util, json, os, platform, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load("firstboot_h", "firstboot.py")
battery = fb.battery

CUT_AFTER_S = 25                      # CRITERIA-FIRSTBOOT.md §9, F13
HEALTHY_S = 900
RECOVERY = re.compile(r"ONEMIND-K3S-RECOVERY: [^\n]*")
NODE_ID = re.compile(r"node_id=(\w+)")
# The k3s files of CRITERIA-FIRSTBOOT.md §9. One shell list, used to check and to empty them.
K3S_FILES = ("/data/k3s/server/token /data/k3s/server/tls/*.crt /data/k3s/server/tls/*.key /data/k3s/agent/*.crt "
             "/data/k3s/agent/*.key /data/k3s/agent/kubelet.kubeconfig /etc/rancher/node/password "
             "/data/k3s/agent/etc/containerd/config.toml")
MARKERS = {"owner": "/data/onemind/f14-owner-marker", "volume": "/data/k3s/storage/f14-pv/marker",
           "gateway": "/data/onemind/gateway/f14-gateway-marker"}
RESULTS = []
record = fb.record
fb.RESULTS = RESULTS


def k3s_healthy(vm, timeout=HEALTHY_S):
    """The gate's own check (G1-G6) until it prints ok. Returns (ok, last line)."""
    _, out = vm.run(f"t0=$SECONDS; while :; do r=$(/usr/lib/onemind/onemind-k3s-check 2>&1); "
                    f"case \"$r\" in ok*) echo K3S=ok; break;; esac; "
                    f"[ $((SECONDS - t0)) -ge {timeout} ] && {{ echo K3S=timeout; break; }}; sleep 5; done; echo LAST=\"$r\"",
                    timeout + 90)
    ok = re.search(r"^K3S=ok\s*$", out, re.M) is not None
    last = (re.findall(r"^LAST=(.*)$", out, re.M) or [""])[-1]
    return ok, last


def empty_k3s_files(vm):
    """Names of the k3s files that are empty or missing (the F13 'none empty' check), and how many were looked at."""
    _, out = vm.run(f"n=0; for f in {K3S_FILES}; do [ -e \"$f\" ] || {{ echo BAD $f missing; continue; }}; n=$((n+1)); "
                    "[ -s \"$f\" ] || echo BAD $f empty; done; echo CHECKED=$n")
    bad = re.findall(r"^BAD (\S+ \w+)\s*$", out, re.M)
    n = int((re.findall(r"^CHECKED=(\d+)", out, re.M) or ["0"])[-1])
    return bad, n


def diagnose(vm, why):
    vm.mark(f"DIAGNOSE ({why}): k3s journal and the repair's files")
    try:
        _, out = vm.run("journalctl -u k3s --no-pager -n 60 -o cat | cut -c1-220; ls -la /data/k3s/server/tls /data/onemind/k3s-recovery "
                        "2>&1 | head -40; cat /data/onemind/k3s-recovery/last.json 2>&1 | head -30", 120)
        print(out[-6000:], flush=True)
    except (TimeoutError, RuntimeError, OSError) as e:
        vm.mark(f"DIAGNOSE failed: {e}")


def boot_again(vm, tag):
    """Start QEMU on the same disk after the power cut; returns once the box has the shell and the gate has decided."""
    vm.restart(tag)
    al = vm.expect(fb.ALREADY, 900).group(0)
    vm.pos = 0                       # first boot's line and the gate's can come in either order
    g = vm.wait_gate()
    vm.shell_ready()
    return al, g


def owner_ok(vm, token):
    return fb.http_code(vm, f"{fb.GW}/v1/nodes", token, timeout=600) == "200"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(battery.BOARDS))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    fb.make_work(a.fixtures, a.work)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    rc = 1
    try:
        # ---- F13: the cut, 25 s after first boot configured the box
        vm.mark("F13 first boot as hub, power cut 25 s after the configured line")
        vm.start()
        cfg = vm.expect(fb.CONFIGURED, 900).group(0)
        seen = time.time()
        node1 = (NODE_ID.findall(cfg) or [""])[0]
        time.sleep(3)
        toks = fb.TOKEN.findall(vm.since(0))
        time.sleep(max(0, CUT_AFTER_S - (time.time() - seen)))
        vm.kill()
        token = toks[0] if toks else ""
        al, g = boot_again(vm, "F13 second boot after the power cut")
        node2 = (NODE_ID.findall(al) or [""])[0]
        new_tok = len(fb.TOKEN.findall(vm.since(0)))
        healthy, last = k3s_healthy(vm)
        if not healthy:
            diagnose(vm, f"k3s not healthy: {last}")
        bad, checked = empty_k3s_files(vm)
        sha = hashlib.sha256(token.encode()).hexdigest()
        _, out = vm.run(f"echo TOKSHA=$(grep -c {sha} /data/onemind/gateway/tokens.yaml)")
        tok_in_file = "TOKSHA=1" in out
        tok_200 = bool(token) and owner_ok(vm, token)
        recovered = RECOVERY.search(vm.since(0))
        record("F13", len(toks) == 1 and bool(node1) and node1 == node2 and new_tok == 0 and g == ("committed-boot", "A", "1")
               and healthy and not bad and checked >= 8 and tok_in_file and tok_200,
               f"tokens_first_boot={len(toks)} node_id={node1}/{node2} new_tokens={new_tok} gate={g} k3s_healthy={healthy} "
               f"empty_or_missing={bad} files_checked={checked} token_hash_in_file={tok_in_file} token_200={tok_200} "
               f"recovery_ran={recovered.group(0)[:90] if recovered else None} t={time.time() - t0:.0f}s")

        # ---- F14: corrupt k3s state on a healthy box
        vm.mark("F14 corrupt k3s state, power cut, repair")
        ids = fb.ident(vm)
        script = ""
        for name, path in MARKERS.items():
            script += (f"mkdir -p $(dirname {path}); head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n' > {path}; ")
        script += "sync; "
        for name, path in MARKERS.items():
            script += f"echo MARK-{name}=$(sha256sum {path} | cut -c1-64); "
        _, out = vm.run(script, 120)
        marks = {n: (re.findall(rf"^MARK-{n}=(\w+)", out, re.M) or [""])[-1] for n in MARKERS}
        _, out = vm.run(f"systemctl stop k3s; n=0; for f in {K3S_FILES}; do [ -e \"$f\" ] || continue; : > \"$f\"; n=$((n+1)); done; "
                        "sync; echo EMPTIED=$n")
        emptied = int((re.findall(r"^EMPTIED=(\d+)", out, re.M) or ["0"])[-1])
        vm.kill()
        al, g = boot_again(vm, "F14 boot after the corrupted k3s state")
        rec = RECOVERY.search(vm.since(0))
        healthy, last = k3s_healthy(vm)
        if not healthy:
            diagnose(vm, f"k3s not healthy after repair: {last}")
        bad, checked = empty_k3s_files(vm)
        script = "; ".join(f"echo MARK2-{n}=$(sha256sum {p} | cut -c1-64)" for n, p in MARKERS.items())
        _, out = vm.run(script)
        marks2 = {n: (re.findall(rf"^MARK2-{n}=(\w+)", out, re.M) or [""])[-1] for n in MARKERS}
        _, out = vm.run("echo QDIRS=$(ls -d /data/onemind/k3s-recovery/*/ 2>/dev/null | wc -l); "
                        "echo QEMPTY=$(find /data/onemind/k3s-recovery -mindepth 2 -type f -size 0 2>/dev/null | wc -l); "
                        f"echo LASTACTION=$({fb.PY} -I -c 'import json; print(json.load(open(\"/data/onemind/k3s-recovery/last.json\"))[\"action\"])' 2>/dev/null || echo none)")
        get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or [""])[-1]
        ids2 = fb.ident(vm)
        tok_200 = bool(token) and owner_ok(vm, token)
        hz = fb.http_code(vm, f"{fb.GW}/healthz", timeout=600)
        c = {"emptied_enough": emptied >= 8, "recovery_line": rec is not None, "k3s_healthy": healthy, "none_empty": not bad and checked >= 8,
             "markers_kept": all(len(v) == 64 for v in marks.values()) and marks == marks2,
             "token_200": tok_200, "healthz_200": hz == "200", "damaged_files_kept": int(get("QDIRS") or 0) >= 1 and int(get("QEMPTY") or 0) >= 1,
             "last_json_repaired": get("LASTACTION") == "repaired", "ids_unchanged": ids2 == ids and bool(ids["node_id"])}
        record("F14", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
               + f" emptied={emptied} recovery={rec.group(0)[:110] if rec else None} gate={g} t={time.time() - t0:.0f}s")
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
    if rc == 0:
        vm.poweroff()
    elif vm.proc and vm.proc.poll() is None:
        vm.kill()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-FIRSTBOOT.md section 9",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    return 0 if RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
