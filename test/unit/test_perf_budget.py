# SPDX-License-Identifier: Apache-2.0
"""test/perf/perf.py: the parts that do not need a running hub (docs/testing/PERF-BUDGET.md)."""
import importlib.util, json, os, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("perf", ROOT / "test" / "perf" / "perf.py")
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)

UID_ADDON = "11111111-2222-3333-4444-555555555555"
UID_APP = "66666666-7777-8888-9999-aaaaaaaaaaaa"
UID_NEW = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
MIB = 1 << 20


def cg(path, anon_mib, usec, inactive_mib=0):
    path.mkdir(parents=True, exist_ok=True)
    (path / "memory.current").write_text(f"{(anon_mib + inactive_mib + 1) * MIB}\n")
    (path / "memory.stat").write_text(f"anon {anon_mib * MIB}\nfile {inactive_mib * MIB}\ninactive_file {inactive_mib * MIB}\n")
    (path / "cpu.stat").write_text(f"usage_usec {usec}\nuser_usec {usec}\n")


class Discovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.root, self.logs = t / "cg", t / "pods"
        sysd = self.root / "system.slice"
        cg(sysd / "k3s.service", 500, 1_000_000, inactive_mib=200)
        cg(sysd / "onemind-gateway.service", 80, 0)
        cg(sysd / "onemind-perf-sim-1.service", 10, 0)
        burst = self.root / "kubepods.slice" / "kubepods-burstable.slice"
        pod = burst / f"kubepods-burstable-pod{UID_ADDON.replace('-', '_')}.slice"
        cg(pod, 30, 0)
        cg(pod / "cri-containerd-abc.scope", 30, 0)  # a container: already in the pod's totals
        cg(self.root / "kubepods" / "besteffort" / f"pod{UID_APP}", 40, 0)  # cgroupfs driver layout
        cg(burst / f"kubepods-burstable-pod{UID_NEW.replace('-', '_')}.slice", 5, 0)  # no log dir yet
        for d in (f"kube-system_coredns-abc_{UID_ADDON}", f"app-ntfy_ntfy-xyz_{UID_APP}", "not-a-pod-dir"):
            (self.logs / d).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_groups(self):
        g = perf.groups(self.root, self.logs)
        names = lambda c: [p.name for p in g[c]]
        self.assertEqual(names("k3s"), ["k3s.service"])
        self.assertEqual(names("gateway"), ["onemind-gateway.service"])
        self.assertEqual(g["onemindd"], [])
        self.assertEqual(g["mesh"], [])
        self.assertEqual(names("sim-nodes"), ["onemind-perf-sim-1.service"])
        self.assertEqual(len(g["k3s-addons"]), 1)
        self.assertIn(UID_ADDON.replace("-", "_"), g["k3s-addons"][0].name)
        self.assertEqual(names("apps"), [f"pod{UID_APP}"])
        self.assertEqual(len(g["other-pods"]), 1)

    def test_sample_counts_anon_not_cache(self):
        s = perf.sample(self.root, self.logs, proc=self._proc())
        self.assertEqual(s["groups"]["k3s"]["anon"], 500 * MIB)
        self.assertEqual(s["groups"]["k3s"]["ws"], 501 * MIB)  # current minus inactive_file
        self.assertEqual(s["groups"]["k3s-addons"]["anon"], 30 * MIB)  # pod only, container not added twice

    def _proc(self):
        p = Path(self.tmp.name) / "proc"
        p.mkdir(exist_ok=True)
        (p / "meminfo").write_text("MemTotal: 4000000 kB\nMemFree: 1000 kB\nMemAvailable: 3000000 kB\n")
        (p / "stat").write_text("cpu  100 0 50 800 10 0 0 5 0 0\ncpu0 1 1 1 1\n")
        return str(p)


def mk(t, comps, used=1000 * MIB, busy=0, idle=0):
    return {"t": t, "box": {"used": used, "total": 4000 * MIB, "cpu_total": busy + idle, "cpu_idle": idle, "cpu_steal": 0},
            "groups": {c: {"anon": a * MIB, "ws": a * MIB, "cpu": cpu} for c, (a, cpu) in comps.items()}}


class Summaries(unittest.TestCase):
    def test_percentile(self):
        v = list(range(1, 101))
        self.assertEqual([perf.percentile(v, q) for q in (50, 95, 99, 100)], [50, 95, 99, 100])
        self.assertEqual(perf.percentile([7.5], 95), 7.5)
        self.assertEqual(perf.percentile([3, 1, 2], 50), 2)

    def test_cpu_with_pods_coming_and_going(self):
        s = [mk(0, {"apps": (0, {"a": 1_000_000})}),
             mk(10, {"apps": (0, {"a": 2_000_000, "b": 500_000})}),  # b is new: all of it counts
             mk(20, {"apps": (0, {"b": 1_500_000})})]                # a is gone: stops counting
        self.assertAlmostEqual(perf.cpu_seconds(s, "apps"), 1.0 + 0.5 + 1.0)

    def test_summarize_hub_total(self):
        s = [mk(0, {"k3s": (500, {"k": 0}), "gateway": (80, {"g": 0}), "sim-nodes": (30, {"s": 0})}, busy=0, idle=0),
             mk(10, {"k3s": (520, {"k": 1_000_000}), "gateway": (90, {"g": 500_000}), "sim-nodes": (30, {"s": 0})},
                busy=300, idle=700)]
        r = perf.summarize(s)
        c = r["components"]
        self.assertEqual(c["k3s"]["anon_mib"], {"mean": 510.0, "max": 520.0})
        self.assertEqual(c["k3s"]["cpu_pct"], 10.0)
        self.assertEqual(c["hub-total"]["anon_mib"]["max"], 610.0)  # sim nodes are not the hub
        self.assertEqual(c["hub-total"]["cpu_pct"], 15.0)
        self.assertEqual(r["box"]["cpu_busy_pct_of_all_cores"], 30.0)
        with self.assertRaises(ValueError):
            perf.summarize(s[:1])

    def test_latency_summary(self):
        lat = perf.Latency()
        for i in range(1, 21):
            lat.add("GET /v1/nodes", float(i), True)
        lat.add("GET /healthz", 100.0, False)
        lat.add("approve", 900.0, True)
        s = lat.summary()
        self.assertEqual(s["read"]["n"], 21)
        self.assertEqual(s["read"]["errors"], 1)
        self.assertEqual(s["GET /v1/nodes"]["p95"], 19.0)
        self.assertNotIn("approve", [k for k in s if k.startswith("GET")])
        self.assertEqual(s["approve"]["max"], 900.0)


class Budget(unittest.TestCase):
    BUDGET = {"_doc": "x", "idle_memory_mib": {"k3s": 700, "gateway": 100}, "api_p95_ms": {"idle": 50, "load": 80},
              "boot_to_ready_s": 120}

    def test_check(self):
        m = {"idle_memory_mib.k3s": 650.0, "idle_memory_mib.gateway": 120.0, "api_p95_ms.idle": 20.0}
        rows, ok = perf.check(self.BUDGET, m)
        res = {r[0]: r[3] for r in rows}
        self.assertFalse(ok)
        self.assertEqual(res["idle_memory_mib.gateway"], "OVER")
        self.assertEqual(res["idle_memory_mib.k3s"], "ok")
        self.assertEqual(res["boot_to_ready_s"], "not measured")
        rows, ok = perf.check(self.BUDGET, {**m, "idle_memory_mib.gateway": 90.0})
        self.assertTrue(ok)  # without --keys a missing measurement is only reported

    def test_keys_must_be_measured(self):
        m = {"idle_memory_mib.k3s": 1.0, "idle_memory_mib.gateway": 1.0, "api_p95_ms.idle": 1.0}
        rows, ok = perf.check(self.BUDGET, m, ["idle_memory_mib", "api_p95_ms"])
        self.assertFalse(ok)  # api_p95_ms.load was selected but not measured
        self.assertEqual([r[0] for r in rows], ["api_p95_ms.idle", "api_p95_ms.load",
                                                "idle_memory_mib.gateway", "idle_memory_mib.k3s"])
        rows, ok = perf.check(self.BUDGET, {**m, "api_p95_ms.load": 2.0}, ["idle_memory_mib", "api_p95_ms"])
        self.assertTrue(ok)

    def test_measured_from_reports(self):
        comp = lambda a, n=1: {"anon_mib": {"mean": a, "max": a}, "cpu_pct": 1.0, "cgroups": n}
        lat = {"read": {"p95": 12.0, "errors": 0}, "approve": {"p95": 800.0}}
        reports = [{"kind": "idle", "window": {"components": {"k3s": comp(600), "mesh": comp(0, 0)}}, "latency": lat},
                   {"kind": "load", "windows": {"load": {}}, "latency": lat},
                   {"kind": "ready", "boot_to_ready_s": 55.0}, {"kind": "ready", "waited_s": 3},
                   {"kind": "disk", "runtime_mib": 1500.0}]
        m = perf.measured(reports)
        self.assertEqual(m["idle_memory_mib.k3s"], 600)
        self.assertNotIn("idle_memory_mib.mesh", m)  # not installed, so not measured
        self.assertEqual((m["api_p95_ms.idle"], m["api_p95_ms.load"], m["approve_p95_ms"]), (12.0, 12.0, 800.0))
        self.assertEqual((m["boot_to_ready_s"], m["disk_runtime_mib"]), (55.0, 1500.0))

    def test_repo_budget_file(self):
        b = json.loads((ROOT / "test" / "perf" / "budget.json").read_text())
        flat = perf.flatten(b)
        for key in ("idle_memory_mib.hub-total", "idle_memory_mib.k3s", "idle_memory_mib.gateway",
                    "api_p95_ms.idle", "api_p95_ms.load"):
            self.assertIn(key, flat)
        self.assertTrue(all(v >= 0 for v in flat.values()))


class Tokens(unittest.TestCase):
    def test_add_principal(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "tokens.yaml"
            f.write_text('# comment\ntokens:\n  "sha256:%s": {id: owner, kind: person, role: owner}\n' % ("a" * 64))
            os.chmod(f, 0o640)
            t1 = perf.add_principal(f)
            t2 = perf.add_principal(f)
            text = f.read_text()
            self.assertNotEqual(t1, t2)
            self.assertEqual(text.count("id: perf-probe,"), 1)  # the second call replaced the first
            self.assertIn("id: owner,", text)
            self.assertEqual(os.stat(f).st_mode & 0o777, 0o640)
            try:
                import yaml
            except ImportError:
                return
            doc = yaml.safe_load(text)
            self.assertEqual(len(doc["tokens"]), 2)

    def test_refuses_other_layout(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "tokens.yaml"
            f.write_text("tokens:\n  x: {}\nother:\n  y: 1\n")
            with self.assertRaises(SystemExit):
                perf.add_principal(f)


if __name__ == "__main__":
    unittest.main()
