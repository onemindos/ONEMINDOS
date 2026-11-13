#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""LAB-machines-spike M5: sample memory and CPU of pods or cgroups (root, inside the lab VM only).

  measure.py --label NAME --out DIR [--ns kubevirt,cdi] [--pod NS/PREFIX ...] [--cgroup LABEL=PATH ...]
             [--settle 120] [--window 600] [--interval 30]

Per target and sample: summed Pss (smaps_rollup) of every PID in the target's cgroup tree, the part
of it in processes whose name starts with "qemu", cgroup memory.current and anon. CPU is the
cgroup's cpu.stat usage_usec over the window. Node MemAvailable is sampled at the same times.
"""
import argparse, csv, json, os, statistics, subprocess, time

def kubectl_json(*a):
    return json.loads(subprocess.run(["kubectl", *a, "-o", "json"], capture_output=True, text=True, check=True).stdout)

def pod_cgroup(uid):
    want = (f"pod{uid}", f"pod{uid.replace('-', '_')}.slice")
    for root, dirs, _ in os.walk("/sys/fs/cgroup"):
        for d in dirs:
            if d.endswith(want):
                return os.path.join(root, d)
        dirs[:] = [d for d in dirs if d.startswith("kubepods")]   # pods live under kubepods*
    raise SystemExit(f"cgroup for pod uid {uid} not found")

def targets(a):
    out = []
    for ns in filter(None, (a.ns or "").split(",")):
        for p in kubectl_json("get", "pods", "-n", ns)["items"]:
            if p["status"].get("phase") == "Running":
                out.append((f"{ns}/{p['metadata']['name']}", pod_cgroup(p["metadata"]["uid"]), p))
    for spec in a.pod or []:
        ns, prefix = spec.split("/", 1)
        for p in kubectl_json("get", "pods", "-n", ns)["items"]:
            if p["metadata"]["name"].startswith(prefix) and p["status"].get("phase") == "Running":
                out.append((f"{ns}/{p['metadata']['name']}", pod_cgroup(p["metadata"]["uid"]), p))
    for spec in a.cgroup or []:
        label, path = spec.split("=", 1)
        out.append((label, path, None))
    if not out:
        raise SystemExit("no targets")
    return out

def pids(cg):
    s = set()
    for root, _, files in os.walk(cg):
        if "cgroup.procs" in files:
            with open(os.path.join(root, "cgroup.procs")) as f:
                s |= {int(x) for x in f.read().split()}
    return s

def pss_kib(pid):
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0

def comm(pid):
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except OSError:
        return "?"

def cg_int(cg, name, key=None):
    try:
        with open(os.path.join(cg, name)) as f:
            text = f.read()
    except OSError:
        return None
    if key is None:
        v = text.split()[0]
        return int(v) if v.isdigit() else None
    for line in text.splitlines():
        k, v = line.split()[:2]
        if k == key:
            return int(v)
    return None

def mem_available_kib():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])

def requests(p):
    if not p:
        return None
    r = {"containers": {}}
    for c in p["spec"].get("containers", []) + p["spec"].get("initContainers", []):
        r["containers"][c["name"]] = c.get("resources", {})
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--ns"); ap.add_argument("--pod", action="append"); ap.add_argument("--cgroup", action="append")
    ap.add_argument("--settle", type=int, default=120); ap.add_argument("--window", type=int, default=600)
    ap.add_argument("--interval", type=int, default=30)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    time.sleep(a.settle)
    tg = targets(a)
    cpu0 = {lbl: cg_int(cg, "cpu.stat", "usage_usec") for lbl, cg, _ in tg}
    t0 = time.time(); rows = []; last = {}
    while True:
        now = time.time()
        avail = mem_available_kib()
        for lbl, cg, _ in tg:
            ps = pids(cg)
            per = {pid: pss_kib(pid) for pid in ps}
            q = sum(v for pid, v in per.items() if comm(pid).startswith("qemu"))
            rows.append({"t": round(now - t0, 1), "target": lbl, "pss_kib": sum(per.values()), "qemu_pss_kib": q,
                         "mem_current_kib": (cg_int(cg, "memory.current") or 0) // 1024,
                         "anon_kib": (cg_int(cg, "memory.stat", "anon") or 0) // 1024,
                         "mem_max": open(os.path.join(cg, "memory.max")).read().strip() if os.path.exists(os.path.join(cg, "memory.max")) else "",
                         "nprocs": len(ps), "node_memavailable_kib": avail})
            last[lbl] = sorted(((comm(pid), v) for pid, v in per.items()), key=lambda x: -x[1])
        if now - t0 >= a.window:
            break
        time.sleep(a.interval)
    dt = time.time() - t0
    with open(os.path.join(a.out, f"{a.label}-samples.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summ = {"label": a.label, "window_s": round(dt), "interval_s": a.interval, "settle_s": a.settle, "targets": {}}
    tot = {}
    for lbl, cg, p in tg:
        rs = [r for r in rows if r["target"] == lbl]
        c1 = cg_int(cg, "cpu.stat", "usage_usec")
        summ["targets"][lbl] = {
            "pss_mib_mean": round(statistics.mean(r["pss_kib"] for r in rs) / 1024, 1),
            "pss_mib_max": round(max(r["pss_kib"] for r in rs) / 1024, 1),
            "qemu_pss_mib_mean": round(statistics.mean(r["qemu_pss_kib"] for r in rs) / 1024, 1),
            "mem_current_mib_mean": round(statistics.mean(r["mem_current_kib"] for r in rs) / 1024, 1),
            "anon_mib_mean": round(statistics.mean(r["anon_kib"] for r in rs) / 1024, 1),
            "memory_max": rs[-1]["mem_max"],
            "cpu_pct_of_one_vcpu": round((c1 - cpu0[lbl]) / (dt * 1e6) * 100, 2) if c1 is not None and cpu0[lbl] is not None else None,
            "processes_pss_kib_last": last[lbl], "resources": requests(p)}
        for r in rs:
            tot.setdefault(r["t"], 0); tot[r["t"]] += r["pss_kib"]
    summ["total_pss_mib_mean"] = round(statistics.mean(tot.values()) / 1024, 1)
    summ["total_pss_mib_max"] = round(max(tot.values()) / 1024, 1)
    summ["total_cpu_pct_of_one_vcpu"] = round(sum(v["cpu_pct_of_one_vcpu"] or 0 for v in summ["targets"].values()), 2)
    summ["node_memavailable_mib_mean"] = round(statistics.mean(r["node_memavailable_kib"] for r in rows) / 1024, 1)
    with open(os.path.join(a.out, f"{a.label}-summary.json"), "w") as f:
        json.dump(summ, f, indent=1)
    print(json.dumps({k: v for k, v in summ.items() if k != "targets"}))

if __name__ == "__main__":
    main()
