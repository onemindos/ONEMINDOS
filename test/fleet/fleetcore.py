# SPDX-License-Identifier: Apache-2.0
"""Virtual fleet test (#864): the judge and the lab guards. Pure Python, no VM, no network.

fleet.py drives the lab; everything that decides what it may touch, whether a check passed and what the
report says lives here, so it is unit-tested on every PR (test/unit/test_virtual_fleet.py).
"""
import json
import re

# The checks, in run order. Every one must PASS for a green run (issue #864 "Spec" and "Acceptance test").
CHECKS = [
    ("F0", "preflight: lab guards hold, the release image's checksum verifies"),
    ("F1", "first boot: hub and three nodes boot the same image; the hub starts a new OneMind"),
    ("F2", "join: each node joins with the hub's QR code (v2, else v1) through `onemind fabric join`; match codes agree"),
    ("F3", "nodes: the hub's Nodes list (/v1/nodes) shows the hub and all three nodes online"),
    ("F4", "bus: every node's NATS leaf link to the hub is up"),
    ("F5", "one dashboard: the hub's HTTPS dashboard answers and its node list shows all four"),
    ("F6", "placement: an app the hub schedules on a node runs on that node"),
    ("F7", "failover: a stopped node is marked offline in time, work moves as designed, it rejoins"),
    ("F8", "staged update: the good bundle rolls to all four, one at a time, each healthy on the new slot"),
    ("F9", "rollback: a forced-bad update on one node rolls back by itself; the other three stay healthy"),
]
CHECK_IDS = [c for c, _ in CHECKS]
RESULTS = ("PASS", "FAIL", "BLOCKED")

# Lab guards (issue #864 and the lab rules): only VM ids 500-509, never the lab's own machines,
# at most three 4 GiB VMs' worth of memory at once, and stop when the host has less than 8 GiB free.
VMID_MIN, VMID_MAX = 500, 509
PROTECTED = frozenset({110, 200, 210, 300, 400})
MAX_VM_MIB = 4096
BUDGET_MIB = 3 * MAX_VM_MIB
HOST_FLOOR_GIB = 8
NAME_PREFIX = "onemind-fleet-"

# core/onemind_core/nodes.py: a node is offline 120 s after its last heartbeat. The heartbeat interval
# and the poll add slack; more than this is a FAIL.
OFFLINE_AFTER_S = 120
OFFLINE_SLACK_S = 45

ENV = {
    "ONEMIND_FLEET_PVE": "ssh target of the Proxmox host (empty: run qm here, on the host)",
    "ONEMIND_FLEET_BRIDGE": "bridge the four VMs share",
    "ONEMIND_FLEET_ADDRS": "four addresses in CIDR form, hub first, comma-separated",
    "ONEMIND_FLEET_GW": "gateway (and DNS server) for those addresses",
    "ONEMIND_FLEET_STORAGE": "Proxmox storage for the VM disks",
    "ONEMIND_FLEET_SNIPPETS": "Proxmox storage with the snippets content type",
    "ONEMIND_FLEET_SNIPPETS_DIR": "that storage's folder on the host (snippets/ is added)",
}
OPTIONAL = {"ONEMIND_FLEET_PVE"}


class GuardError(Exception):
    """The run would break a lab rule; nothing is touched."""


def parse_env(env):
    missing = [k for k in ENV if k not in OPTIONAL and not env.get(k, "").strip()]
    if missing:
        raise GuardError("missing environment: " + ", ".join(missing))
    addrs = [a.strip() for a in env["ONEMIND_FLEET_ADDRS"].split(",") if a.strip()]
    if len(addrs) != 4 or not all(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}/\d{1,2}", a) for a in addrs):
        raise GuardError("ONEMIND_FLEET_ADDRS: need four addresses like 192.0.2.10/24, hub first")
    if len(set(addrs)) != 4:
        raise GuardError("ONEMIND_FLEET_ADDRS: addresses repeat")
    cfg = {k: env.get(k, "").strip() for k in ENV}
    cfg["addrs"] = addrs
    return cfg


def plan(base=VMID_MIN, hub_mib=MAX_VM_MIB, node_mib=2048):
    """The four VMs: (vmid, name, role, memory MiB). Raises GuardError if a lab rule would break."""
    vms = [(base, NAME_PREFIX + "hub", "hub", hub_mib)]
    vms += [(base + i, f"{NAME_PREFIX}node{i}", "node", node_mib) for i in (1, 2, 3)]
    for vmid, _, _, mib in vms:
        if not VMID_MIN <= vmid <= VMID_MAX or vmid in PROTECTED:
            raise GuardError(f"VM id {vmid} is outside {VMID_MIN}-{VMID_MAX}")
        if not 1024 <= mib <= MAX_VM_MIB:
            raise GuardError(f"VM {vmid}: {mib} MiB is outside 1024-{MAX_VM_MIB}")
    total = sum(m for *_, m in vms)
    if total > BUDGET_MIB:
        raise GuardError(f"the fleet needs {total} MiB; the lab budget is {BUDGET_MIB} MiB (three 4 GiB VMs)")
    return vms


def available_gib(free_g_text):
    """The host's available memory from `free -g` (the "available" column, else "free")."""
    lines = free_g_text.strip().splitlines()
    head = lines[0].split()
    for ln in lines[1:]:
        if ln.startswith("Mem:"):
            vals = ln.split()[1:]
            col = head.index("available") if "available" in head else head.index("free")
            return int(vals[col])
    raise ValueError("no Mem: line in free -g output")


def may_start(free_g_text, vm_mib):
    """True when starting a VM of vm_mib still leaves the host HOST_FLOOR_GIB available."""
    return available_gib(free_g_text) - (vm_mib + 1023) // 1024 >= HOST_FLOOR_GIB


def foreign(qm_list_text, vms):
    """VM ids from the plan that exist on the host under a name that is not ours (never touched)."""
    want = {vmid: name for vmid, name, *_ in vms}
    out = []
    for ln in qm_list_text.splitlines()[1:]:
        f = ln.split()
        if len(f) >= 2 and f[0].isdigit() and int(f[0]) in want and f[1] != want[int(f[0])]:
            out.append(int(f[0]))
    return out


def ours(qm_list_text):
    """Fleet VMs present on the host (by id and exact name), for teardown."""
    out = []
    for ln in qm_list_text.splitlines()[1:]:
        f = ln.split()
        if len(f) >= 2 and f[0].isdigit() and VMID_MIN <= int(f[0]) <= VMID_MAX and f[1].startswith(NAME_PREFIX):
            out.append(int(f[0]))
    return out


GATE = re.compile(r"RESULT (\S+) slot=(\w)\b(?: version=([^\s;]+))?")


def gate_results(text):
    """(result, slot, version) for every health-gate RESULT line (os/gate/onemind-health-gate)."""
    return [m.groups() for m in GATE.finditer(text)]


def nodes_list(payload):
    """GET /v1/nodes answers a list or {"nodes": [...]}: node_id -> status."""
    items = payload.get("nodes", []) if isinstance(payload, dict) else payload
    return {n.get("node_id"): n.get("status") for n in items if isinstance(n, dict)}


def pending_join(fabric, hostname):
    """The awaiting join for hostname in GET /v1/fabric (under "joining" or "pending")."""
    waiting = [j for j in fabric.get("joining", []) + fabric.get("pending", [])
               if j.get("state") in ("awaiting_approval", "pending")]
    named = [j for j in waiting if j.get("hostname") == hostname]
    # Joins run one at a time: a single waiting request is this node's even if its label differs.
    return named[0] if named else (waiting[0] if len(waiting) == 1 else None)


def offline_in_time(seconds):
    return seconds <= OFFLINE_AFTER_S + OFFLINE_SLACK_S


class Redactor:
    """Masks lab addresses, host names, tokens and join codes before anything is printed or saved."""

    def __init__(self, extra=()):
        self.extra = sorted({e for e in extra if e}, key=len, reverse=True)

    def __call__(self, text):
        s = str(text)
        for e in self.extra:
            s = s.replace(e, "<lab>")
        s = re.sub(r"onemind-join:v\d\?[^\s'\"]+", "<join-code>", s)
        s = re.sub(r"\b[0-9a-f]{64}\b", "<hex64>", s)
        s = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?\b", "<addr>", s)
        return s


def verdict(results, expect_join_fail=False):
    """GREEN: every check PASS. A broken-image run is NEGATIVE-OK only when the join check FAILED."""
    if expect_join_fail:
        return "NEGATIVE-OK" if results.get("F2", {}).get("result") == "FAIL" else "NEGATIVE-MISSED"
    if all(results.get(c, {}).get("result") == "PASS" for c in CHECK_IDS):
        return "GREEN"
    return "RED"


def streak(history_lines, image_sha):
    """Green runs in a row at the end of the history (JSON lines), on this image only."""
    n = 0
    for ln in reversed([x for x in history_lines if x.strip()]):
        r = json.loads(ln)
        if r.get("verdict") != "GREEN" or r.get("image_sha256") != image_sha:
            break
        n += 1
    return n


def report(run):
    """The plain report (Markdown): one row per check, the verdict, the streak."""
    res = run["results"]
    out = [f"# Virtual fleet run: {run['verdict']}", "",
           f"- image: `{run['image']}` (sha256 `{run['image_sha256'][:16]}...`)",
           f"- started {run['started']}, {run['minutes']} min; mode: {run['mode']}",
           f"- green runs in a row on this image: {run['streak']} (acceptance: 3)", "",
           "| Check | What | Result | Evidence |", "|---|---|---|---|"]
    for cid, what in CHECKS:
        r = res.get(cid, {"result": "BLOCKED", "evidence": "not reached"})
        ev = r["evidence"].replace("|", "/").replace("\n", " ")
        out.append(f"| {cid} | {what} | {r['result']} | {ev} |")
    return "\n".join(out) + "\n"
