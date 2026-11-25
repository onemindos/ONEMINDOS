#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, power cut in the first minute (F13-F15). Criteria: test/qemu/CRITERIA-FIRSTBOOT.md §9
(pre-registered; never edited to make a result pass). VM 501 bug 1 (2026-11-25): a power cut about 45 s after the
first boot left k3s's keys, certificates, token and node password empty and k3s never came back. Refs #234.

A power cut is SIGKILL of QEMU (guest memory is lost, the disk image keeps what the guest flushed).
  F13  first boot as a hub (NoCloud seed, as F1); 25 s after the "configured" console line, power cut; boot again:
       same box, no new owner token, committed boot, k3s healthy, no empty k3s file.
  F14  on that healthy box (the fixture's test app deleted, §10): write owner/app/gateway markers, stop k3s, empty
       every k3s file, power cut, boot again: the repair ran, k3s healthy, markers and token intact, damaged files kept.
  F15  with an app in the cluster (the fixture's app is back): the same damage is NOT repaired by itself; the owner
       approves "Reset k3s state" in the rescue console, then k3s is healthy and the markers are intact.

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
    """Names of the k3s files that are empty or missing (the F13 'none empty' check), and how many were looked at."""
    _, out = vm.run(f"n=0; for f in {K3S_FILES}; do [ -e \"$f\" ] || {{ echo BAD $f missing; continue; }}; n=$((n+1)); "
                    "[ -s \"$f\" ] || echo BAD $f empty; done; echo CHECKED=$n")
    bad = re.findall(r"^BAD (\S+ \w+)\s*$", out, re.M)
    n = int((re.findall(r"^CHECKED=(\d+)", out, re.M) or ["0"])[-1])
    return bad, n


def diagnose(vm, why):
    vm.mark(f"DIAGNOSE ({why}): k3s journal and the repair's files")
    try:
        _, out = vm.run("k3s kubectl get pods -A 2>&1 | cut -c1-160; k3s kubectl -n kube-system describe pod -l k8s-app=kube-dns 2>&1 | tail -30 | cut -c1-200; "
                        "k3s kubectl -n kube-system logs -l k8s-app=kube-dns --previous --tail=25 2>&1 | cut -c1-200; "
                        "ls -la /data/k3s/server/manifests 2>&1 | cut -c1-120; "
                        "journalctl -u k3s --no-pager -n 40 -o cat | cut -c1-220; ls -la /data/k3s/server/tls /data/onemind/k3s-recovery "
                        "2>&1 | head -30; "
                        f"{fb.PY} -I -c 'import json; d=json.load(open(\"/data/onemind/k3s-recovery/last.json\")); d.pop(\"damaged\", None); print(d)' 2>&1 | cut -c1-1500", 120)
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


def write_markers(vm):
    """Three files of random content (owner data, an app's volume, the gateway's folder), synced. Returns sha256s."""
    script = ""
    for path in MARKERS.values():
        script += f"mkdir -p $(dirname {path}); head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n' > {path}; "
    script += "sync; "
    for name, path in MARKERS.items():
        script += f"echo MARK-{name}=$(sha256sum {path} | cut -c1-64); "
    _, out = vm.run(script.rstrip("; "), 120)
    return {n: (re.findall(rf"^MARK-{n}=(\w+)", out, re.M) or [""])[-1] for n in MARKERS}


def read_markers(vm):
    _, out = vm.run("; ".join(f"echo MARK2-{n}=$(sha256sum {p} | cut -c1-64)" for n, p in MARKERS.items()))
    return {n: (re.findall(rf"^MARK2-{n}=(\w+)", out, re.M) or [""])[-1] for n in MARKERS}


def empty_and_cut(vm):
    """Stop k3s, empty every k3s file, sync, power cut. Returns how many files were emptied."""
    _, out = vm.run(f"systemctl stop k3s; n=0; for f in {K3S_FILES}; do [ -e \"$f\" ] || continue; : > \"$f\"; n=$((n+1)); done; "
                    "sync; echo EMPTIED=$n")
    emptied = int((re.findall(r"^EMPTIED=(\d+)", out, re.M) or ["0"])[-1])
    vm.kill()
    return emptied


def quarantine_dirs(vm):
    _, out = vm.run("echo QDIRS=$(ls -d /data/onemind/k3s-recovery/*/ 2>/dev/null | wc -l); "
                    "echo QEMPTY=$(find /data/onemind/k3s-recovery -mindepth 2 -type f -size 0 2>/dev/null | wc -l); "
                    f"echo LASTACTION=$({fb.PY} -I -c 'import json; print(json.load(open(\"/data/onemind/k3s-recovery/last.json\"))[\"action\"])' 2>/dev/null || echo none)")
    get = lambda k: (re.findall(rf"^{k}=(\S*)\s*$", out, re.M) or [""])[-1]
    return int(get("QDIRS") or 0), int(get("QEMPTY") or 0), get("LASTACTION")


RESCUE = ("curl -s --cacert /data/onemind/identity/ca.pem --resolve onemind.local:7443:127.0.0.1 "
          "-w '\\nHTTP=%{http_code}\\n' ")


def rescue_post(vm, token, csrf, confirm="reset k3s", with_token=True):
    auth = f"-H 'Authorization: Bearer {token}' " if with_token else ""
    form = (f"--data-urlencode 'csrf={csrf}' " if csrf else "") + f"--data-urlencode 'confirm={confirm}' "
    _, out = vm.run(f"{RESCUE}{auth}{form}https://onemind.local:7443/reset-k3s")
    return (re.findall(r"^HTTP=(\d+)", out, re.M) or ["0"])[-1]


def rescue_status(vm, token):
    """The rescue console's status.json for the owner: (k3s_recovery action, csrf token)."""
    _, out = vm.run("curl -s --cacert /data/onemind/identity/ca.pem --resolve onemind.local:7443:127.0.0.1 "
                    f"-H 'Authorization: Bearer {token}' -o /run/pc-status.json https://onemind.local:7443/status.json; "
                    f"{fb.PY} -I -c 'import json; d=json.load(open(\"/run/pc-status.json\")); "
                    "print(\"ACTION=\" + str((d.get(\"k3s_recovery\") or {}).get(\"action\")), \"CSRF=\" + d.get(\"csrf\", \"\"))' 2>&1; "
                    "rm -f /run/pc-status.json")
    m = re.search(r"^ACTION=(\S+) CSRF=(\w*)\s*$", out, re.M)
    return (m.group(1), m.group(2)) if m else ("", "")


def owner_ok(vm, token):
    return fb.http_code(vm, f"{fb.GW}/v1/nodes", token, timeout=600) == "200"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=sorted(battery.BOARDS))
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    ap.add_argument("--only-f13", action="store_true", help="debugging: stop after F13")
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

        if a.only_f13:
            raise SystemExit(0 if RESULTS and RESULTS[-1]["verdict"] == "PASS" else 1)
        # ---- F14: corrupt k3s state on a healthy box with no owner app (the fixture's test app deleted, §10)
        vm.mark("F14 corrupt k3s state, power cut, repair")
        ids = fb.ident(vm)
        vm.run("k3s kubectl -n apps delete deployment broken-app --wait=true --timeout=90s 2>&1 | tail -2", 150)
        marks = write_markers(vm)
        emptied = empty_and_cut(vm)
        al, g = boot_again(vm, "F14 boot after the corrupted k3s state")
        rec = RECOVERY.search(vm.since(0))
        healthy, last = k3s_healthy(vm)
        if not healthy:
            diagnose(vm, f"k3s not healthy after repair: {last}")
        bad, checked = empty_k3s_files(vm)
        marks2 = read_markers(vm)
        qd, qe, action = quarantine_dirs(vm)
        ids2 = fb.ident(vm)
        tok_200 = bool(token) and owner_ok(vm, token)
        hz = fb.http_code(vm, f"{fb.GW}/healthz", timeout=600)
        c = {"emptied_enough": emptied >= 8, "recovery_line": rec is not None, "k3s_healthy": healthy, "none_empty": not bad and checked >= 8,
             "markers_kept": all(len(v) == 64 for v in marks.values()) and marks == marks2,
             "token_200": tok_200, "healthz_200": hz == "200", "damaged_files_kept": qd >= 1 and qe >= 1,
             "last_json_repaired": action == "repaired", "ids_unchanged": ids2 == ids and bool(ids["node_id"])}
        record("F14", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
               + f" emptied={emptied} recovery={rec.group(0)[:110] if rec else None} gate={g} t={time.time() - t0:.0f}s")

        # ---- F15: an owner's app in the cluster: no automatic repair; the owner approves the reset (§10)
        vm.mark("F15 owner app in the cluster: needs approval, then Reset k3s state")
        _, out = vm.run("t0=$SECONDS; until k3s kubectl -n apps get deployment broken-app >/dev/null 2>&1; do "
                        "[ $((SECONDS - t0)) -ge 300 ] && break; sleep 5; done; "
                        "echo APP=$(k3s kubectl -n apps get deployment broken-app -o name 2>&1 | head -1)", 360)
        app = (re.findall(r"^APP=(.*)$", out, re.M) or [""])[-1]
        ids = fb.ident(vm)
        qd0, _, _ = quarantine_dirs(vm)
        marks = write_markers(vm)
        emptied = empty_and_cut(vm)
        al, g = boot_again(vm, "F15 boot after the corrupted k3s state, owner app present")
        time.sleep(90)
        notrep = re.search(r"ONEMIND-K3S-RECOVERY: NOT repaired[^\n]*", vm.since(0))
        qd1, _, action = quarantine_dirs(vm)
        still_bad, _ = empty_k3s_files(vm)
        status_action, csrf = rescue_status(vm, token)
        no_token = rescue_post(vm, token, csrf, with_token=False)
        no_csrf = rescue_post(vm, token, "")
        _, _, action_after_refused = quarantine_dirs(vm)
        approved = rescue_post(vm, token, csrf)
        healthy, last = k3s_healthy(vm)
        if not healthy:
            diagnose(vm, f"k3s not healthy after the approved reset: {last}")
        bad, checked = empty_k3s_files(vm)
        marks2 = read_markers(vm)
        qd2, qe2, action2 = quarantine_dirs(vm)
        _, out = vm.run("echo GWKUBE=$([ -s /data/onemind/gateway/kubeconfig ] && echo yes || echo no)")
        gwkube = "GWKUBE=yes" in out
        ids2 = fb.ident(vm)
        tok_200 = bool(token) and owner_ok(vm, token)
        hz = fb.http_code(vm, f"{fb.GW}/healthz", timeout=600)
        c = {"app_present": "broken-app" in app, "emptied_enough": emptied >= 8, "not_repaired_line": notrep is not None,
             "needs_approval_record": action == "needs-approval" and action_after_refused == "needs-approval",
             "nothing_moved": qd1 == qd0 and len(still_bad) >= 8, "status_json_says_so": status_action == "needs-approval",
             "no_token_401": no_token == "401", "no_csrf_403": no_csrf == "403", "approved_200": approved == "200",
             "k3s_healthy": healthy, "none_empty": not bad and checked >= 8, "record_reset": action2 == "reset",
             "damaged_files_kept": qd2 == qd0 + 1 and qe2 >= 1,
             "markers_kept": all(len(v) == 64 for v in marks.values()) and marks == marks2,
             "token_200": tok_200, "healthz_200": hz == "200", "gateway_kubeconfig": gwkube,
             "ids_unchanged": ids2 == ids and bool(ids["node_id"])}
        record("F15", all(c.values()), " ".join(f"{k}={v}" for k, v in c.items())
               + f" notrepaired={notrep.group(0)[:100] if notrep else None} gate={g} t={time.time() - t0:.0f}s")
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
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-FIRSTBOOT.md sections 9 and 10",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    shutil.rmtree(os.path.join(a.work, "seed"), ignore_errors=True)
    return 0 if RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
