#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Hub performance budget: measure a hub that deploy/install.sh installed, and check the numbers
against test/perf/budget.json. What each number means and how the budget was set:
docs/testing/PERF-BUDGET.md.

Runs on the hub, as root (it reads every service's cgroup and edits the tokens file), with the
Python standard library only. For throwaway test hubs only: it adds an owner principal and starts
extra onemindd processes that pretend to be nodes.

  perf.py token --out FILE                    add owner principal "perf-probe"; its token -> FILE (0600)
  perf.py sims start|stop [--count 3]         simulated nodes: onemindd units heartbeating to the hub NATS
  perf.py ready --token-file F [--boot]       wait until the hub is ready (k3s, add-ons, gateway, hub node)
  perf.py boot-probe --token-file F --out O   enable a unit that runs "ready --boot" on the next boots
  perf.py idle --token-file F --out FILE      settle, sample memory and CPU per component, then API latency
  perf.py load --token-file F --out FILE      approvals, app installs, heartbeats: latency, memory, CPU
  perf.py disk --out FILE                     disk used by each piece of the install
  perf.py check --budget B [--keys K,..] R..  compare reports with the budget; exit 1 if over or missing

Memory is the cgroup v2 "anon" counter (memory.stat): private memory that cannot be dropped
without swap. Page cache is left out because the kernel gives it back under pressure; the working
set (memory.current - inactive_file) is reported next to it for reference. CPU is the cgroup's
usage_usec over the window, in % of one core.
"""
import argparse
import datetime
import hashlib
import http.client
import json
import math
import os
import re
import secrets
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")
PODLOGS = Path("/var/log/pods")
K3S = "/usr/local/bin/k3s"
ONEMINDD = "/usr/local/bin/onemindd"
TOKENS = Path("/etc/onemind/tokens.yaml")
GATEWAY = "http://127.0.0.1:8080"
MIB = 1 << 20

# Component -> systemd units whose cgroups it adds up. Units that do not exist are skipped.
UNITS = {
    "k3s": ("k3s.service", "k3s-agent.service"),  # k3s, its containerd and the pods' containerd shims
    "gateway": ("onemind-gateway.service",),
    "onemindd": ("onemindd.service",),
    "nats": ("onemind-nats.service",),
    "mesh": ("tailscaled.service", "headscale.service"),  # deploy/install.sh does not install one yet
}
# Pods, grouped by namespace (first match wins).
POD_GROUPS = (
    ("k3s-addons", lambda ns: ns == "kube-system"),
    ("apps", lambda ns: ns.startswith("app-")),
    ("other-pods", lambda ns: True),
)
HUB = ("k3s", "k3s-addons", "gateway", "onemindd", "nats", "mesh")  # what "hub-total" adds up
SIM_UNIT = "onemind-perf-sim-{}.service"
READS = ("/healthz", "/v1/instance", "/v1/nodes", "/v1/apps", "/v1/actions")  # what the dashboard polls
ADDONS = ("coredns", "local-path-provisioner", "metrics-server", "traefik")  # k3s default add-ons
ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
POD_RE = re.compile(r"pod([0-9a-f]{8}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{12})(?:\.slice)?$")


def log(msg):
    print(f"perf: {msg}", file=sys.stderr, flush=True)


def write_json(path, doc):
    Path(path).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    log(f"wrote {path}")


# ---------------------------------------------------------------------------------------------
# cgroups
# ---------------------------------------------------------------------------------------------
def pod_namespaces(podlogs=PODLOGS):
    """Pod uid -> namespace, from the kubelet's <podlogs>/<namespace>_<name>_<uid> directories."""
    try:
        names = os.listdir(podlogs)
    except OSError:
        return {}
    out = {}
    for n in names:
        parts = n.split("_")
        if len(parts) == 3:
            out[parts[2]] = parts[0]
    return out


def pod_cgroups(root=CGROUP):
    """Pod uid -> its cgroup directory (systemd or cgroupfs cgroup driver)."""
    out = {}
    for top in ("kubepods.slice", "kubepods"):
        base = Path(root) / top
        if not base.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(base):
            for d in list(dirnames):
                m = POD_RE.search(d)
                if m:
                    out[m.group(1).replace("_", "-")] = Path(dirpath) / d
                    dirnames.remove(d)  # its containers are already in the pod's totals
    return out


def groups(root=CGROUP, podlogs=PODLOGS):
    """Component -> list of cgroup directories."""
    sysd = Path(root) / "system.slice"
    g = {c: [sysd / u for u in units if (sysd / u).is_dir()] for c, units in UNITS.items()}
    g["sim-nodes"] = sorted(p for p in sysd.glob(SIM_UNIT.format("*")) if p.is_dir())
    for name, _ in POD_GROUPS:
        g[name] = []
    ns = pod_namespaces(podlogs)
    for uid, path in sorted(pod_cgroups(root).items()):
        n = ns.get(uid, "")
        for name, match in POD_GROUPS:
            if match(n):
                g[name].append(path)
                break
    return g


def read_kv(path):
    try:
        with open(path) as f:
            return {k: int(v) for k, v in (line.split() for line in f if line.strip())}
    except (OSError, ValueError):
        return {}


def cg_sample(path):
    """anon, working set and cumulative CPU of one cgroup; None if it went away."""
    try:
        cur = int((Path(path) / "memory.current").read_text())
    except (OSError, ValueError):
        return None
    st = read_kv(Path(path) / "memory.stat")
    cpu = read_kv(Path(path) / "cpu.stat").get("usage_usec", 0)
    return {"anon": st.get("anon", 0), "ws": max(0, cur - st.get("inactive_file", 0)), "cpu": cpu}


def box_sample(proc="/proc"):
    mi = {}
    with open(f"{proc}/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            mi[k] = int(v.split()[0]) * 1024
    with open(f"{proc}/stat") as f:
        c = [int(x) for x in f.readline().split()[1:]]
    # user nice system idle iowait irq softirq steal (guest time is already in user)
    return {"used": mi["MemTotal"] - mi["MemAvailable"], "total": mi["MemTotal"],
            "cpu_total": sum(c[:8]), "cpu_idle": c[3] + c[4], "cpu_steal": c[7]}


def sample(root=CGROUP, podlogs=PODLOGS, proc="/proc"):
    s = {"t": time.monotonic(), "groups": {}, "box": box_sample(proc)}
    for comp, paths in groups(root, podlogs).items():
        anon = ws = 0
        cpu = {}
        for p in paths:
            v = cg_sample(p)
            if v is None:
                continue
            anon += v["anon"]
            ws += v["ws"]
            cpu[str(p)] = v["cpu"]
        s["groups"][comp] = {"anon": anon, "ws": ws, "cpu": cpu}
    return s


def cpu_seconds(samples, comp):
    """CPU seconds a component used between the first and the last sample. A cgroup that appears
    counts from zero (it was created inside the interval); one that disappears stops counting."""
    used = 0
    for a, b in zip(samples, samples[1:]):
        ca, cb = a["groups"][comp]["cpu"], b["groups"][comp]["cpu"]
        used += sum(max(0, v - ca[p]) if p in ca else v for p, v in cb.items())
    return used / 1e6


def percentile(values, q):
    """Nearest-rank percentile, q in (0, 100]."""
    v = sorted(values)
    return v[max(1, math.ceil(q / 100 * len(v))) - 1]


def summarize(samples):
    """Per component: anon and working set in MiB (mean and max of the samples), CPU in % of one
    core, and how many cgroups it had. Plus hub-total and the whole box."""
    if len(samples) < 2:
        raise ValueError("need at least two samples")
    span = samples[-1]["t"] - samples[0]["t"]
    r1 = lambda x: round(x, 1)
    comps = {}
    for comp in samples[0]["groups"]:
        anon = [s["groups"][comp]["anon"] for s in samples]
        ws = [s["groups"][comp]["ws"] for s in samples]
        comps[comp] = {
            "anon_mib": {"mean": r1(statistics.mean(anon) / MIB), "max": r1(max(anon) / MIB)},
            "working_set_mib": {"mean": r1(statistics.mean(ws) / MIB), "max": r1(max(ws) / MIB)},
            "cpu_pct": r1(cpu_seconds(samples, comp) / span * 100),
            "cgroups": max(len(s["groups"][comp]["cpu"]) for s in samples),
        }
    present = [c for c in HUB if c in comps]
    anon = [sum(s["groups"][c]["anon"] for c in present) for s in samples]
    ws = [sum(s["groups"][c]["ws"] for c in present) for s in samples]
    comps["hub-total"] = {
        "anon_mib": {"mean": r1(statistics.mean(anon) / MIB), "max": r1(max(anon) / MIB)},
        "working_set_mib": {"mean": r1(statistics.mean(ws) / MIB), "max": r1(max(ws) / MIB)},
        "cpu_pct": r1(sum(comps[c]["cpu_pct"] for c in present)),
        "cgroups": sum(comps[c]["cgroups"] for c in present),
    }
    a, b = samples[0]["box"], samples[-1]["box"]
    dt = max(1, b["cpu_total"] - a["cpu_total"])
    used = [s["box"]["used"] for s in samples]
    box = {"mem_total_mib": r1(b["total"] / MIB),
           "mem_used_mib": {"mean": r1(statistics.mean(used) / MIB), "max": r1(max(used) / MIB)},
           "cpu_busy_pct_of_all_cores": r1((dt - (b["cpu_idle"] - a["cpu_idle"])) / dt * 100),
           "cpu_steal_pct": r1((b["cpu_steal"] - a["cpu_steal"]) / dt * 100)}
    return {"seconds": r1(span), "samples": len(samples), "components": comps, "box": box}


class Sampler(threading.Thread):
    def __init__(self, interval):
        super().__init__(daemon=True)
        self.interval, self.samples, self._stop_evt = interval, [], threading.Event()

    def run(self):
        while True:
            self.samples.append(sample())
            if self._stop_evt.wait(self.interval):
                self.samples.append(sample())
                return

    def stop(self):
        self._stop_evt.set()
        self.join()

    def window(self, t0, t1):
        return [s for s in self.samples if t0 <= s["t"] <= t1]


# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
class Api:
    """One keep-alive connection to the gateway (like a dashboard tab). Not thread-safe."""

    def __init__(self, base, token=None, timeout=600):
        u = urllib.parse.urlsplit(base)
        self.host, self.port, self.token, self.timeout, self.conn = u.hostname, u.port or 80, token, timeout, None

    def call(self, method, path, body=None):
        """-> (status, parsed JSON or None, milliseconds). Status 0 means no answer."""
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        for attempt in (0, 1):  # one retry: the server may have closed an idle keep-alive connection
            if self.conn is None:
                self.conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
            t0 = time.perf_counter()
            try:
                self.conn.request(method, path, body=data, headers=headers)
                r = self.conn.getresponse()
                raw = r.read()
            except (OSError, http.client.HTTPException):
                self.conn.close()
                self.conn = None
                if attempt:
                    return 0, None, (time.perf_counter() - t0) * 1000
                continue
            ms = (time.perf_counter() - t0) * 1000
            try:
                doc = json.loads(raw) if raw else None
            except ValueError:
                doc = None
            return r.status, doc, ms
        return 0, None, 0.0


class Latency:
    def __init__(self):
        self.rows, self.lock = [], threading.Lock()

    def add(self, name, ms, ok):
        with self.lock:
            self.rows.append((name, ms, ok))

    def summary(self):
        with self.lock:
            rows = list(self.rows)
        sets = {n: [r for r in rows if r[0] == n] for n in sorted({r[0] for r in rows})}
        sets["read"] = [r for r in rows if r[0].startswith("GET ")]
        out = {}
        for name, rs in sets.items():
            if rs:
                ms = [r[1] for r in rs]
                out[name] = {"n": len(ms), "errors": sum(1 for r in rs if not r[2]),
                             **{f"p{q}": round(percentile(ms, q), 1) for q in (50, 95, 99)},
                             "max": round(max(ms), 1)}
        return out


def read_once(api, lat, i):
    path = READS[i % len(READS)]
    st, _, ms = api.call("GET", path)
    lat.add("GET " + path, ms, st == 200)


def probe(api, lat, n, rate):
    """n reads of the dashboard endpoints, round robin, at `rate` per second."""
    for i in range(n):
        read_once(api, lat, i)
        time.sleep(1 / rate)


def read_loop(api, lat, stop, rate):
    i, nxt = 0, time.monotonic()
    while not stop.is_set():
        read_once(api, lat, i)
        i += 1
        nxt += 1 / rate
        d = nxt - time.monotonic()
        if d > 0:
            stop.wait(d)
        else:
            nxt = time.monotonic()


def rfc3339(seconds):
    t = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def create(api, lat, typ, app_id):
    body = {"type": typ, "params": {"app_id": app_id}, "idempotency_key": "perf-" + uuid.uuid4().hex[:16],
            "expires_at": rfc3339(900)}
    st, d, ms = api.call("POST", "/v1/actions", body)
    lat.add("create", ms, st == 201)
    aid = (d or {}).get("id") if st == 201 else None
    return aid if isinstance(aid, str) and ID_RE.fullmatch(aid) else None


def decide(api, lat, aid, verb):
    st, d, ms = api.call("POST", f"/v1/actions/{aid}/{verb}")
    # An approve the scan gate refuses (409 stale_precondition) still made the round trip.
    lat.add(verb, ms, st == 200 or (verb == "approve" and st == 409))
    return st, d or {}


def read_token(path):
    tok = Path(path).read_text().strip()
    if not re.fullmatch(r"[A-Za-z0-9._~-]{16,512}", tok):
        sys.exit(f"perf: {path} does not hold a token")
    return tok


# ---------------------------------------------------------------------------------------------
# k3s and the box
# ---------------------------------------------------------------------------------------------
def kubectl_json(*args, timeout=60):
    try:
        cp = subprocess.run([K3S, "kubectl", *args, "-o", "json"], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if cp.returncode != 0:
        return None
    try:
        return json.loads(cp.stdout)
    except ValueError:
        return None


def is_ready(obj):
    return any(c.get("type") == "Ready" and c.get("status") == "True" for c in obj.get("status", {}).get("conditions", []))


def pods_ready(ns):
    d = kubectl_json("-n", ns, "get", "pods")
    pods = [p for p in (d or {}).get("items", []) if p.get("status", {}).get("phase") != "Succeeded"]
    return bool(pods) and all(is_ready(p) for p in pods)


def wait_for(fn, timeout, step=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fn():
            return True
        time.sleep(step)
    return False


def uptime():
    with open("/proc/uptime") as f:
        return float(f.read().split()[0])


def first_line(argv):
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        return (cp.stdout or cp.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def host_info(api):
    osr = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                osr[k] = v.strip('"')
    except OSError:
        pass
    _, inst, _ = api.call("GET", "/v1/instance")
    return {"arch": os.uname().machine, "kernel": os.uname().release, "cpus": os.cpu_count(),
            "mem_total_mib": round(box_sample()["total"] / MIB), "os": osr.get("PRETTY_NAME"),
            "k3s": first_line([K3S, "--version"]), "nats": first_line(["/usr/local/bin/nats-server", "--version"]),
            "onemindd": first_line([ONEMINDD, "-version"]), "gateway": (inst or {}).get("version")}


# ---------------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------------
def add_principal(path, principal="perf-probe"):
    """Append an owner principal to the gateway's tokens file (it reloads on mtime change) and
    return its token. An earlier entry with the same id is replaced."""
    path = Path(path)
    text = path.read_text()
    top = [l for l in text.splitlines() if l.strip() and not l.startswith((" ", "\t", "#"))]
    if not top or top[-1].rstrip() != "tokens:":
        sys.exit(f"perf: {path}: expected 'tokens:' as the last top-level key (deploy/install.sh layout)")
    token = secrets.token_hex(32)
    h = hashlib.sha256(token.encode()).hexdigest()
    keep = [l for l in text.splitlines() if f"{{id: {principal}," not in l]
    keep.append(f'  "sha256:{h}": {{id: {principal}, kind: person, role: owner}}')
    st = path.stat()
    tmp = path.with_name(path.name + ".perf-tmp")
    tmp.write_text("\n".join(keep) + "\n")
    os.chown(tmp, st.st_uid, st.st_gid)
    os.chmod(tmp, st.st_mode & 0o7777)
    os.replace(tmp, path)
    return token


def cmd_token(a):
    token = add_principal(a.tokens)
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token + "\n")
    api = Api(a.url, token)
    if not wait_for(lambda: api.call("GET", "/v1/instance")[0] == 200, 30, 1):
        sys.exit("perf: the gateway did not accept the new principal within 30 s")
    log(f"owner principal perf-probe added; token in {a.out}")


def cmd_sims(a):
    for i in range(1, a.count + 1):
        unit = SIM_UNIT.format(i)
        subprocess.run(["systemctl", "stop", unit], capture_output=True)
        subprocess.run(["systemctl", "reset-failed", unit], capture_output=True)
        if a.action == "start":
            subprocess.run(["systemd-run", "--quiet", f"--unit={unit}", "--property=DynamicUser=yes",
                            f"--setenv=ONEMIND_NODE_ID=perf-sim-{i}", "--setenv=ONEMIND_NODE_ROLE=node",
                            f"--setenv=ONEMIND_NATS_URL={a.nats}", f"--setenv=ONEMIND_AGENT_ADDR=127.0.0.1:{7480 + i}",
                            ONEMINDD], check=True)
    log(f"{a.action}: {a.count} simulated node(s)")


def check_ready(api, token, done, addons):
    """Fill `done` (milestone -> uptime seconds) with each readiness milestone reached now."""
    up = uptime()
    if "k3s_node_ready" not in done:
        d = kubectl_json("get", "nodes", timeout=20)
        if d and d.get("items") and all(is_ready(n) for n in d["items"]):
            done["k3s_node_ready"] = up
    if "k3s_addons_available" not in done and "k3s_node_ready" in done:
        d = kubectl_json("-n", "kube-system", "get", "deployments", timeout=20)
        avail = {x["metadata"]["name"] for x in (d or {}).get("items", [])
                 if x.get("status", {}).get("availableReplicas", 0) >= x.get("spec", {}).get("replicas", 1)}
        if set(addons) <= avail:
            done["k3s_addons_available"] = up
    if "gateway_healthz" not in done and api.call("GET", "/healthz")[0] == 200:
        done["gateway_healthz"] = up
    if token and "hub_node_online" not in done and "gateway_healthz" in done:
        st, inst, _ = api.call("GET", "/v1/instance")
        st2, nodes, _ = api.call("GET", "/v1/nodes")
        hub = (inst or {}).get("hub_node_id")
        if st == st2 == 200 and isinstance(nodes, list) and any(
                isinstance(n, dict) and n.get("node_id") == hub and n.get("status") == "online" for n in nodes):
            done["hub_node_online"] = up


def cmd_ready(a):
    token = read_token(a.token_file) if a.token_file else None
    api = Api(a.url, token, timeout=10)
    want = {"k3s_node_ready", "k3s_addons_available", "gateway_healthz"} | ({"hub_node_online"} if token else set())
    done, t0 = {}, time.monotonic()
    while not want <= set(done):
        check_ready(api, token, done, a.addons.split(",") if a.addons else ())
        if time.monotonic() - t0 > a.timeout:
            sys.exit(f"perf: not ready after {a.timeout} s; missing {sorted(want - set(done))}")
        time.sleep(1)
    rep = {"kind": "ready", "boot": a.boot, "milestones_uptime_s": {k: round(v, 1) for k, v in done.items()},
           "waited_s": round(time.monotonic() - t0, 1)}
    if a.boot:  # uptime counts from kernel start; firmware/bootloader time is not in it
        rep["boot_to_ready_s"] = round(max(done.values()), 1)
        rep["systemd_analyze"] = first_line(["systemd-analyze", "time"])
    log(f"ready: {rep['milestones_uptime_s']}")
    if a.out:
        write_json(a.out, rep)


def cmd_boot_probe(a):
    script = Path(__file__).resolve()
    out = Path(a.out).resolve()
    tokf = Path(a.token_file).resolve()
    Path("/etc/systemd/system/onemind-perf-ready.service").write_text(f"""\
# Written by test/perf/perf.py boot-probe (throwaway test hubs only).
[Unit]
Description=OneMind perf: record boot-to-ready
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
ExecStartPre=/usr/bin/install -d -m0700 {out.parent}
ExecStart={sys.executable} -I {script} ready --boot --token-file {tokf} --out {out} --timeout 900

[Install]
WantedBy=multi-user.target
""")
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "onemind-perf-ready.service"], check=True, capture_output=True)
    log(f"boot probe enabled; after the next boot see {out}")


def cmd_idle(a):
    api = Api(a.url, read_token(a.token_file))
    if a.settle:
        log(f"settling for {a.settle} s")
        time.sleep(a.settle)
    log(f"sampling for {a.seconds} s")
    smp = Sampler(a.interval)
    smp.start()
    time.sleep(a.seconds)
    smp.stop()
    lat = Latency()
    log(f"latency probe: {a.probe} reads at {a.rate}/s")
    probe(api, lat, a.probe, a.rate)
    write_json(a.out, {"kind": "idle", "host": host_info(api), "window": summarize(smp.samples),
                       "latency": lat.summary()})


def cmd_load(a):
    token = read_token(a.token_file)
    api, reader_api, lat, stop = Api(a.url, token), Api(a.url, token), Latency(), threading.Event()
    smp = Sampler(a.interval)
    smp.start()
    reader = threading.Thread(target=read_loop, args=(reader_api, lat, stop, a.rate), daemon=True)
    reader.start()
    log(f"{a.cycles} approval cycles (create + deny)")
    for _ in range(a.cycles):
        aid = create(api, lat, "app.install", a.cycle_app)
        if aid:
            decide(api, lat, aid, "deny")
        time.sleep(a.gap)
    apps = []
    for app in a.apps:
        log(f"install {app}")
        rec, t0 = {"id": app}, time.monotonic()
        aid = create(api, lat, "app.install", app)
        st, d = decide(api, lat, aid, "approve") if aid else (0, {})
        rec.update(approve_status=st, state=d.get("state") or d.get("error"))
        if rec["state"] == "succeeded":
            rec["ready_s"] = (round(time.monotonic() - t0, 1)
                              if wait_for(lambda: pods_ready(f"app-{app}"), a.app_timeout) else None)
        apps.append(rec)
    t_steady = time.monotonic()
    if a.steady:
        log(f"steady state for {a.steady} s")
        time.sleep(a.steady)
    t_end = time.monotonic()
    for rec in apps:
        if rec["state"] == "succeeded":
            log(f"remove {rec['id']}")
            t0 = time.monotonic()
            aid = create(api, lat, "app.remove", rec["id"])
            st, d = decide(api, lat, aid, "approve") if aid else (0, {})
            rec["remove_state"] = d.get("state") or d.get("error")
            gone = wait_for(lambda: kubectl_json("get", "namespace", f"app-{rec['id']}") is None, a.app_timeout)
            rec["removed_s"] = round(time.monotonic() - t0, 1) if gone else None
    stop.set()
    reader.join()
    smp.stop()
    windows = {"load": summarize(smp.samples)}
    steady = smp.window(t_steady, t_end)
    if a.apps and len(steady) >= 2:
        windows["steady_with_apps"] = summarize(steady)
    write_json(a.out, {"kind": "load", "host": host_info(api), "windows": windows, "latency": lat.summary(),
                       "apps": apps, "cycles": a.cycles, "read_rate_per_s": a.rate,
                       "sim_nodes": len(groups()["sim-nodes"])})


# Piece -> (paths, part of the runtime footprint?). Toolchains and caches exist only because the
# developer install builds from source; an image ships the built artifacts.
DISK = {
    "k3s binary": (["/usr/local/bin/k3s"], True),
    "k3s data (images, datastore, pods)": (["/var/lib/rancher/k3s"], True),
    "nats-server": (["/usr/local/bin/nats-server"], True),
    "onemindd and onemind CLI": (["/usr/local/bin/onemindd", "/usr/local/bin/onemind"], True),
    "gateway (Python, venv, core, apps, schema)": (
        ["/opt/onemind/python", "/opt/onemind/venv", "/opt/onemind/core", "/opt/onemind/apps",
         "/opt/onemind/sdk", "/opt/onemind/bin"], True),
    "dashboard": (["/opt/onemind/dashboard"], True),
    "gateway data (database, audit)": (["/var/lib/onemind"], True),
    "config": (["/etc/onemind", "/etc/rancher"], True),
    "toolchains (developer install only)": (["/opt/onemind/toolchain"], False),
    "download and build cache (developer install only)": (["/var/cache/onemind"], False),
}


def du(paths):
    paths = [p for p in paths if os.path.lexists(p)]
    if not paths:
        return 0
    cp = subprocess.run(["du", "-sxcB1", *paths], capture_output=True, text=True)
    return int(cp.stdout.strip().splitlines()[-1].split()[0]) if cp.stdout.strip() else 0


def cmd_disk(a):
    pieces = {name: round(du(paths) / MIB, 1) for name, (paths, _) in DISK.items()}
    images = round(du(["/var/lib/rancher/k3s/agent/containerd"]) / MIB, 1)
    st = os.statvfs("/")
    write_json(a.out, {
        "kind": "disk", "pieces_mib": pieces, "containerd_mib": images,
        "runtime_mib": round(sum(v for n, v in pieces.items() if DISK[n][1]), 1),
        "build_only_mib": round(sum(v for n, v in pieces.items() if not DISK[n][1]), 1),
        "root_fs": {"size_mib": round(st.f_blocks * st.f_frsize / MIB),
                    "used_mib": round((st.f_blocks - st.f_bfree) * st.f_frsize / MIB)}})


def measured(reports):
    """Flatten reports into the metric names budget.json uses."""
    m = {}
    for r in reports:
        kind = r.get("kind")
        if kind == "idle":
            for c, v in r["window"]["components"].items():
                if v["cgroups"]:
                    m[f"idle_memory_mib.{c}"] = v["anon_mib"]["max"]
                    m[f"idle_cpu_pct.{c}"] = v["cpu_pct"]
            read = r["latency"].get("read", {})
            if read:
                m["api_p95_ms.idle"], m["api_read_errors.idle"] = read["p95"], read["errors"]
        elif kind == "load":
            read = r["latency"].get("read", {})
            if read:
                m["api_p95_ms.load"], m["api_read_errors.load"] = read["p95"], read["errors"]
            if "approve" in r["latency"]:
                m["approve_p95_ms"] = r["latency"]["approve"]["p95"]
            for c, v in r["windows"].get("steady_with_apps", {}).get("components", {}).items():
                if v["cgroups"]:
                    m[f"loaded_memory_mib.{c}"] = v["anon_mib"]["max"]
        elif kind == "ready" and r.get("boot_to_ready_s") is not None:
            m["boot_to_ready_s"] = r["boot_to_ready_s"]
        elif kind == "cold":
            m["gateway_cold_start_s"] = r["gateway_cold_start_s"]
        elif kind == "disk":
            m["disk_runtime_mib"] = r["runtime_mib"]
    return m


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[f"{prefix}{k}"] = v
    return out


def check(budget, metrics, keys=None):
    """-> (rows, ok). Each row: (metric, limit, measured or None, result). With `keys` (metric name
    prefixes), only those budgets are checked and each of them must have been measured."""
    rows, ok = [], True
    for name, limit in sorted(flatten(budget).items()):
        if keys and not any(name == k or name.startswith(k + ".") for k in keys):
            continue
        got = metrics.get(name)
        if got is None:
            res = "not measured"
            ok = ok and not keys
        elif got > limit:
            res, ok = "OVER", False
        else:
            res = "ok"
        rows.append((name, limit, got, res))
    return rows, ok


def cmd_check(a):
    budget = json.loads(Path(a.budget).read_text())
    reports = [json.loads(Path(p).read_text()) for p in a.reports]
    rows, ok = check(budget, measured(reports), [k for k in a.keys.split(",") if k] if a.keys else None)
    print("| Metric | Budget | Measured | Result |\n|---|---:|---:|---|")
    for name, limit, got, res in rows:
        print(f"| `{name}` | {limit} | {'–' if got is None else got} | {res} |")
    print(f"\n{'PASS' if ok else 'FAIL'}: {sum(r[3] == 'ok' for r in rows)} of {len(rows)} within budget")
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--url", default=GATEWAY, help="gateway URL (default %(default)s)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("token")
    s.add_argument("--out", required=True)
    s.add_argument("--tokens", default=str(TOKENS))
    s = sub.add_parser("sims")
    s.add_argument("action", choices=("start", "stop"))
    s.add_argument("--count", type=int, default=3)
    s.add_argument("--nats", default="nats://127.0.0.1:4222")
    s = sub.add_parser("ready")
    s.add_argument("--token-file")
    s.add_argument("--boot", action="store_true", help="started at boot: report seconds since kernel start")
    s.add_argument("--addons", default=",".join(ADDONS))
    s.add_argument("--timeout", type=float, default=600)
    s.add_argument("--out")
    s = sub.add_parser("boot-probe")
    s.add_argument("--token-file", required=True)
    s.add_argument("--out", required=True)
    for name in ("idle", "load"):
        s = sub.add_parser(name)
        s.add_argument("--token-file", required=True)
        s.add_argument("--out", required=True)
        s.add_argument("--interval", type=float, default=5, help="memory/CPU sample interval (s)")
        s.add_argument("--rate", type=float, default=10 if name == "idle" else 5, help="reads per second")
    s = sub.choices["idle"]
    s.add_argument("--settle", type=float, default=180, help="wait first (s), so start-up work is over")
    s.add_argument("--seconds", type=float, default=120, help="idle sampling window (s)")
    s.add_argument("--probe", type=int, default=300, help="reads in the latency probe after the window")
    s = sub.choices["load"]
    s.add_argument("--cycles", type=int, default=30, help="approval cycles: create + deny")
    s.add_argument("--cycle-app", default="ntfy")
    s.add_argument("--gap", type=float, default=0.5, help="pause between approval cycles (s)")
    s.add_argument("--apps", type=lambda v: [x for x in v.split(",") if x], default=[],
                   help="comma-separated app ids to install, wait for, then remove")
    s.add_argument("--app-timeout", type=float, default=900)
    s.add_argument("--steady", type=float, default=120, help="steady state with the apps running (s)")
    s = sub.add_parser("disk")
    s.add_argument("--out", required=True)
    s = sub.add_parser("check")
    s.add_argument("--budget", required=True)
    s.add_argument("--keys", help="comma-separated metric prefixes to check; each must be measured")
    s.add_argument("reports", nargs="+")
    a = p.parse_args(argv)
    if a.cmd == "check":
        return cmd_check(a)
    if os.geteuid() != 0:
        sys.exit("perf: run as root")
    {"token": cmd_token, "sims": cmd_sims, "ready": cmd_ready, "boot-probe": cmd_boot_probe,
     "idle": cmd_idle, "load": cmd_load, "disk": cmd_disk}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
