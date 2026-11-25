#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, power cut in the first minute (F17). Criteria: test/qemu/CRITERIA-FIRSTBOOT.md §12
(pre-registered; never edited to make a result pass). VM 501 bug 1 (2026-11-25): a power cut about 45 s after the
first boot left k3s's keys, certificates, token and node password empty and k3s never came back. Refs #234.

A power cut is SIGKILL of QEMU (guest memory is lost, the disk image keeps what the guest flushed).
What this does NOT model: the disk is opened with cache=writeback, and the host itself does not crash, so writes
the guest had already sent to its virtual disk but not flushed still reach the image (the host keeps them). A real
disk can lose such writes from its own cache. The test therefore proves what is lost with the guest's page cache
(the VM 501 bug: files k3s never wrote back), not losses inside a drive's write cache; fsync and syncfs, which the
fix relies on, send a flush that a real drive honours.
  F17  first boot as a hub (NoCloud seed, as F1); 25 s after the "configured" console line, power cut; boot again:
       same box, no new owner token, committed boot, k3s healthy, no empty k3s file.
F18 and F19 (repairing k3s state that is already damaged, §12 and §13) join with the repair itself.

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

CUT_AFTER_S = 25                      # CRITERIA-FIRSTBOOT.md §12, F17
HEALTHY_S = 900
RECOVERY = re.compile(r"ONEMIND-K3S-RECOVERY: [^\n]*")   # recorded in F17, not required
NODE_ID = re.compile(r"node_id=(\w+)")
# The k3s files of CRITERIA-FIRSTBOOT.md §12. One shell list, used to check and to empty them.
K3S_FILES = ("/data/k3s/server/token /data/k3s/server/tls/*.crt /data/k3s/server/tls/*.key /data/k3s/agent/*.crt "
             "/data/k3s/agent/*.key /data/k3s/agent/kubelet.kubeconfig /etc/rancher/node/password "
             "/data/k3s/agent/etc/containerd/config.toml")
RESULTS = []
record = fb.record
fb.RESULTS = RESULTS


HEALTHY_TIMEOUT = [HEALTHY_S]        # --healthy-timeout shortens it for debugging runs only; the criterion is HEALTHY_S


def k3s_healthy(vm, timeout=None):
    """The gate's own check (G1-G6) until it prints ok. Returns (ok, last line)."""
    timeout = timeout or HEALTHY_TIMEOUT[0]
    _, out = vm.run(f"t0=$SECONDS; while :; do r=$(/usr/lib/onemind/onemind-k3s-check 2>&1); "
                    f"case \"$r\" in ok*) echo K3S=ok; break;; esac; "
                    f"[ $((SECONDS - t0)) -ge {timeout} ] && {{ echo K3S=timeout; break; }}; sleep 5; done; echo LAST=\"$r\"",
                    timeout + 90)
    ok = re.search(r"^K3S=ok\s*$", out, re.M) is not None
    last = (re.findall(r"^LAST=(.*)$", out, re.M) or [""])[-1]
    return ok, last


def empty_k3s_files(vm):
    """Names of the k3s files that are empty or missing (the F17 'none empty' check), and how many were looked at."""
    _, out = vm.run(f"n=0; for f in {K3S_FILES}; do [ -e \"$f\" ] || {{ echo BAD $f missing; continue; }}; n=$((n+1)); "
                    "[ -s \"$f\" ] || echo BAD $f empty; done; echo CHECKED=$n")
    bad = re.findall(r"^BAD (\S+ \w+)\s*$", out, re.M)
    n = int((re.findall(r"^CHECKED=(\d+)", out, re.M) or ["0"])[-1])
    return bad, n


def diagnose(vm, why):
    vm.mark(f"DIAGNOSE ({why}): k3s journal and the repair's files")
    try:
        # The k3s journal first and the pods' own words last, so a cut tail keeps what explains a crash loop.
        _, out = vm.run("journalctl -u k3s --no-pager -n 25 -o cat | cut -c1-220; "
                        "journalctl -u k3s --no-pager -o cat | grep -iE 'x509|certificate|unauthorized|token' | tail -8 | cut -c1-220; "
                        "ls -la /data/k3s/server/tls /data/onemind/k3s-recovery 2>&1 | head -30; "
                        f"{fb.PY} -I -c 'import json; d=json.load(open(\"/data/onemind/k3s-recovery/last.json\")); d.pop(\"damaged\", None); print(d)' 2>&1 | cut -c1-1500; "
                        "ls -la /data/k3s/server/manifests 2>&1 | cut -c1-120; "
                        "k3s crictl ps -a 2>&1 | cut -c1-160 | head -20; "
                        "k3s kubectl get pods -A 2>&1 | cut -c1-160; "
                        "k3s kubectl get pods -A --no-headers 2>/dev/null | awk '$4 ~ /CrashLoop|Error/ {print $1, $2}' | head -4 | "
                        "while read ns pod; do echo \"== logs --previous $ns/$pod\"; k3s kubectl -n $ns logs $pod --all-containers --previous --tail=15 2>&1 | cut -c1-240; "
                        "k3s kubectl -n $ns get pod $pod -o jsonpath='{range .status.containerStatuses[*]}{.name} {.lastState.terminated.reason} exit={.lastState.terminated.exitCode} {.lastState.terminated.message}{\"\\n\"}{end}' 2>&1 | cut -c1-300; done", 180)
        print(out[-12000:], flush=True)
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
    ap.add_argument("--healthy-timeout", type=int, default=HEALTHY_S, help="debugging only; the criterion is 900 s")
    a = ap.parse_args()
    HEALTHY_TIMEOUT[0] = a.healthy_timeout
    fb.make_work(a.fixtures, a.work)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    rc = 1
    try:
        # ---- F17: the cut, 25 s after first boot configured the box
        vm.mark("F17 first boot as hub, power cut 25 s after the configured line")
        vm.start()
        cfg = vm.expect(fb.CONFIGURED, 900).group(0)
        seen = time.time()
        node1 = (NODE_ID.findall(cfg) or [""])[0]
        time.sleep(3)
        toks = fb.TOKEN.findall(vm.since(0))
        time.sleep(max(0, CUT_AFTER_S - (time.time() - seen)))
        vm.kill()
        token = toks[0] if toks else ""
        al, g = boot_again(vm, "F17 second boot after the power cut")
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
        # Recorded, not judged: the filesystem and options of /data (nodelalloc on ext4, flushoncommit on btrfs, set by
        # data-durable) and whether onemind-k3s-settle wrote its marker on this boot (it waits for the OS's own pods).
        _, out = vm.run("for i in $(seq 1 30); do test -s /data/onemind/firstboot/k3s-settled && break; sleep 2; done; "
                        "echo DATAFS=$(findmnt -no FSTYPE --mountpoint /data); echo DATAOPTS=$(findmnt -no OPTIONS --mountpoint /data); "
                        "echo SETTLED=$(test -s /data/onemind/firstboot/k3s-settled && echo yes || echo no)", 120)
        data_fs = (re.findall(r"^DATAFS=(\S*)", out, re.M) or ["?"])[-1]
        data_opts = (re.findall(r"^DATAOPTS=(\S*)", out, re.M) or ["?"])[-1]
        settled = (re.findall(r"^SETTLED=(\S*)", out, re.M) or ["?"])[-1]
        record("F17", len(toks) == 1 and bool(node1) and node1 == node2 and new_tok == 0 and g == ("committed-boot", "A", "1")
               and healthy and not bad and checked >= 8 and tok_in_file and tok_200,
               f"tokens_first_boot={len(toks)} node_id={node1}/{node2} new_tokens={new_tok} gate={g} k3s_healthy={healthy} "
               f"empty_or_missing={bad} files_checked={checked} token_hash_in_file={tok_in_file} token_200={tok_200} "
               f"recovery_ran={recovered.group(0)[:90] if recovered else None} data_fs={data_fs} data_opts={data_opts} "
               f"k3s_settled={settled} t={time.time() - t0:.0f}s")
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
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-FIRSTBOOT.md section 12 (F17)",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    return 0 if RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
