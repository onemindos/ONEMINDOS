# SPDX-License-Identifier: Apache-2.0
"""The edge profile (#751): the same image, role `leaf` picked at install, no hub services, the same RAUC gate.

An edge runs onemindd, the NATS leaf and the health gate. It never runs a k3s server: k3s.service skips
itself on a leaf (ExecCondition on /data/onemind/etc/role), first boot stops the k3s that ran while the box
had no role and later removes the state it left, and the gate judges a leaf with onemind-leaf-check instead of
the k3s check (which would reject every update on a box without k3s). The QEMU harness is test/qemu/edge.py
(criteria test/qemu/CRITERIA-EDGE.md); these tests are the CI part that needs no VM.
"""
import hashlib, io, json, os, platform, re, shutil, stat, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
sys.path.insert(0, LIB)
import onemind_firstboot as fb  # noqa: E402



def rd(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


def put(path, text):
    with open(path, "w") as f:
        f.write(text)

DROPIN = ("os", "rootfs", "layers", "base", "usr", "lib", "systemd", "system", "k3s.service.d", "20-onemind-leaf.conf")
LEAF_CHECK = os.path.join(ROOT, "os", "gate", "onemind-leaf-check")
GATE = os.path.join(ROOT, "os", "gate", "onemind-health-gate")
HUB_UNITS = ("k3s.service", "onemind-gateway.service", "onemind-gateway-kube.service", "onemind-nats.service",
             "onemind-headscale.service", "onemind-mesh-setup.service", "onemind-starting.service")
CA_SHA = "ab" * 32
LEAF_JOIN = f"onemind-join:v1?code=7KQ4-M2XP-9D3F&ca={CA_SHA}&role=leaf&hub=https%3A%2F%2Fhome-box.local"
LINUX = platform.system() == "Linux" and shutil.which("bash") is not None


class K3sSkipsOnALeaf(unittest.TestCase):
    """k3s.service is enabled in the image (every box boots it before it has a role); on a leaf it must skip."""

    def condition(self):
        t = rd(*DROPIN)
        self.assertRegex(t, r"(?m)^\[Service\]$")
        lines = re.findall(r"(?m)^ExecCondition=(.+)$", t)
        self.assertEqual(len(lines), 1, "exactly one ExecCondition")
        self.assertNotIn("$", lines[0], "systemd would expand $ in an Exec line")
        return lines[0]

    def run_condition(self, role):
        cmd = self.condition()
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "role")
            if role is not None:
                put(f, role + "\n")
            argv = [a.strip("'") for a in re.findall(r"'[^']*'|\S+", cmd.replace("/data/onemind/etc/role", f))]
            return subprocess.run(argv, check=False).returncode

    def test_reads_the_role_file_first_boot_writes(self):
        self.assertIn("/data/onemind/etc/role", self.condition())
        self.assertIn('os.path.join(p.etc, "role")', rd("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind",
                                                        "onemind_firstboot.py"))

    @unittest.skipUnless(shutil.which("sh") and shutil.which("grep"), "needs sh and grep")
    def test_skips_only_on_a_leaf(self):
        self.assertNotEqual(self.run_condition("leaf"), 0)        # 1-254: skipped, not failed, not restarted
        self.assertLess(self.run_condition("leaf"), 255)
        for role in ("hub", "worker", None):                      # None: no role yet (battery, wizard)
            self.assertEqual(self.run_condition(role), 0, role)


class FirstBootRetiresK3s(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = fb.Paths(self.tmp.name)
        os.makedirs(os.path.join(self.tmp.name, "dev"))
        put(self.p.console, "")
        self.calls = []
        self.k3s = "inactive"                              # k3s.service ActiveState as systemctl shows it
        show = lambda argv, env=None: subprocess.CompletedProcess(argv, 0, self.k3s + "\n", "")
        for pt in (mock.patch.object(fb, "systemctl", lambda *a: self.calls.append(a) or 0),
                   mock.patch.object(fb, "run_cmd", show),
                   mock.patch.object(fb, "find_seed_device", lambda: None),
                   mock.patch.object(fb, "lan_addr", lambda: "192.0.2.10"),
                   mock.patch.object(fb, "ensure_boot_lock", lambda p: None),
                   mock.patch("sys.stdout", io.StringIO())):
            pt.start()
            self.addCleanup(pt.stop)

    def leaf(self):
        os.makedirs(os.path.dirname(self.p.esp_conf), exist_ok=True)
        put(self.p.esp_conf, f"role = leaf\njoin_code = {LEAF_JOIN}\n")
        self.assertEqual(fb.apply(self.p), 0)

    def k3s_state(self):
        for d in ("server/tls", "server/db", "agent/images"):
            os.makedirs(os.path.join(self.p.k3s_data, d), exist_ok=True)
        put(os.path.join(self.p.k3s_data, "server", "token"), "not-a-real-token\n")

    def test_paths(self):
        self.assertEqual(self.p.k3s_data, os.path.join(self.tmp.name, "data", "k3s"))
        self.assertEqual(self.p.k3s_run, os.path.join(self.tmp.name, "run", "k3s"))

    def test_configure_boot_stops_k3s_and_keeps_its_state_while_it_ran(self):
        self.k3s_state()
        os.makedirs(self.p.k3s_run)                    # k3s ran on this boot (before the role was picked)
        self.k3s = "active"
        self.leaf()
        stops = [c for c in self.calls if c[0] == "stop"]
        self.assertEqual(len(stops), 1)
        self.assertIn("k3s.service", stops[0])
        self.assertLess(self.calls.index(stops[0]), len(self.calls) - 1, "stop comes before the leaf units start")
        self.assertEqual(self.calls[-1][:2], ("start", "--no-block"))
        self.assertIn("onemindd.service", self.calls[-1])
        self.assertTrue(os.path.isfile(os.path.join(self.p.k3s_data, "server", "token")),
                        "never removed while k3s may still hold it")

    def test_next_boot_removes_the_k3s_state(self):
        self.leaf()
        self.k3s_state()                               # left by the unconfigured first boot
        self.calls.clear()
        os.makedirs(os.path.join(self.p.k3s_data, "storage"))   # data-layout and tmpfiles make these on every box
        self.assertEqual(fb.apply(self.p), 0)          # the restart: k3s skipped itself, /run/k3s is gone
        for d in fb.K3S_WRITES:
            self.assertFalse(os.path.exists(os.path.join(self.p.k3s_data, d)), d)
        self.assertTrue(os.path.isdir(os.path.join(self.p.k3s_data, "storage")))
        self.assertIn("removed the k3s state", self.console())
        self.calls.clear()
        self.assertEqual(fb.apply(self.p), 0)          # nothing left: a quiet no-op
        self.assertFalse([c for c in self.calls if c[0] == "stop"])

    def test_a_waiting_k3s_is_left_to_its_condition(self):
        """The restart: k3s's start job still waits for the network. A stop now would cancel it, and k3s would
        never reach the ExecCondition that skips it (CRITERIA-EDGE.md EG2)."""
        self.leaf()
        self.calls.clear()
        self.k3s = "inactive"
        self.assertEqual(fb.apply(self.p), 0)
        self.assertFalse([c for c in self.calls if c[0] == "stop"], self.calls)

    def test_activating_k3s_is_stopped_and_its_state_kept(self):
        self.leaf()
        self.k3s_state()
        self.calls.clear()
        self.k3s = "activating"                        # started before the role file existed
        self.assertEqual(fb.apply(self.p), 0)
        self.assertTrue([c for c in self.calls if c[0] == "stop" and "k3s.service" in c])
        self.assertTrue(os.path.isfile(os.path.join(self.p.k3s_data, "server", "token")))
        self.assertNotIn("removed the k3s state", self.console())

    def test_no_hub_unit_is_started_on_a_leaf(self):
        self.leaf()
        started = {u for c in self.calls if c[0] == "start" for u in c}
        self.assertFalse(started & set(HUB_UNITS), started & set(HUB_UNITS))

    def test_hub_and_worker_never_stop_k3s(self):
        for role in ("hub", "worker"):
            with self.subTest(role=role):
                self.calls.clear()
                os.makedirs(self.p.k3s_data, exist_ok=True)
                with mock.patch.object(fb, "ensure_files_root", lambda p: None), \
                        mock.patch.object(fb, "ensure_rescue_tls", lambda p: None), \
                        mock.patch.object(fb, "ensure_backup", lambda p, st: None), \
                        mock.patch.object(fb, "chown_tree", lambda *a: None):
                    fb.start_units(self.p, {"role": role, "mesh": 1})
                self.assertFalse([c for c in self.calls if c[0] == "stop"])
                self.assertTrue(os.path.isdir(self.p.k3s_data))

    def console(self):
        return rd(self.p.console)


class GateUsesTheLeafCheck(unittest.TestCase):
    def test_gate_picks_the_check_by_role(self):
        g = rd(GATE)
        self.assertRegex(g, r'grep -qsx leaf "\$STATE/etc/role"')
        self.assertIn("/usr/lib/onemind/onemind-leaf-check", g)
        # the k3s check is only ever called through check(), so no path judges a leaf with it
        self.assertEqual(g.count("/usr/lib/onemind/onemind-k3s-check"), 1)
        self.assertIn("r=$(check)", g)
        self.assertIn('${WHAT}-FRESH ok', g)
        self.assertIn("WHAT=LEAF", g)

    def test_image_ships_the_leaf_check(self):
        c = rd("os", "rootfs", "Containerfile")
        self.assertRegex(c, r"COPY --chmod=755 [^\n]*\\\n[^\n]*os/gate/onemind-leaf-check|"
                            r"COPY --chmod=755 [^\n]*os/gate/onemind-leaf-check")
        self.assertTrue(os.access(LEAF_CHECK, os.X_OK), "executable in git")

    def test_leaf_check_has_no_freshness_switch(self):
        t = rd(LEAF_CHECK)
        self.assertNotIn("NAIVE", t)
        self.assertNotRegex(t, r"fail G4", "G4 means environment-bad (re-offered); a leaf has no core pods")
        for g in ("fail 1", "fail 2", "fail 3", "fail 5", "fail 6"):
            self.assertIn(g, t)


class EdgeJoinedBeforeG1TakesTheUpdate(unittest.TestCase):
    """An edge that joined before the local sign-in (G1) has a leaf.conf the gate refuses (G3). The update
    that ships G1 must repair it on its own trial boot before the gate looks, or the slot rolls back and
    the release lands on the bad-releases list. The repair itself is tested in internal/fabric
    (TestUpgradeLocalRepairsAPreG1Join); here: the image ships it, enables it and orders it before the gate."""
    UNIT = ("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-leaf-local.service")

    def test_unit_runs_the_upgrade_before_the_gate(self):
        u = rd(*self.UNIT)
        self.assertRegex(u, r"(?m)^Before=[^\n]*\bonemind-health-gate\.service\b")
        self.assertRegex(u, r"(?m)^Before=[^\n]*\bonemindd\.service\b")
        self.assertRegex(u, r"(?m)^After=[^\n]*\bonemind-data-layout\.service\b")
        self.assertIn("RequiresMountsFor=/data", u)
        self.assertIn("ConditionPathExists=/data/onemind/etc/leaf-config.json", u)
        self.assertIn("Environment=ONEMIND_ETC_DIR=/data/onemind/etc", u)
        self.assertRegex(u, r"(?m)^Type=oneshot$")
        self.assertRegex(u, r"(?m)^ExecStart=/usr/bin/onemind fabric upgrade-local$")
        self.assertRegex(u, r"(?m)^WantedBy=multi-user\.target$")

    def test_image_enables_it(self):
        c = rd("os", "rootfs", "Containerfile")
        self.assertRegex(c, r"systemctl enable [^>]*\bonemind-leaf-local\.service\b")

    def test_not_inside_onemindd(self):
        """onemindd's sandbox (ProtectSystem=strict) cannot write /data/onemind/etc; a separate unit can."""
        self.assertIn("ProtectSystem=strict", rd("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemindd.service"))
        # It has its own sandbox instead, with exactly one writable place.
        u = rd(*self.UNIT)
        self.assertRegex(u, r"(?m)^ProtectSystem=strict$")
        self.assertRegex(u, r"(?m)^ReadWritePaths=/data/onemind/etc$")

    def test_old_open_conf_is_what_the_gate_refuses(self):
        t = rd(LEAF_CHECK)
        self.assertIn("no local nkey users", t)
        self.assertIn("no_auth_user", t)


@unittest.skipUnless(LINUX, "runs the bash check with GNU date (Linux, as in CI)")
class LeafCheckRuns(unittest.TestCase):
    """onemind-leaf-check against a fake root: stub curl, systemctl and findmnt on PATH."""
    BOOT_ID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        r = self.root = self.tmp.name
        self.btime = 1_800_000_000
        for d in ("proc/sys/kernel/random", "data/onemind/etc/nats", "bin"):
            os.makedirs(os.path.join(r, d), exist_ok=True)
        put(os.path.join(r, "proc/stat"), f"cpu 1 2 3\nbtime {self.btime}\n")
        put(os.path.join(r, "proc/sys/kernel/random/boot_id"), self.BOOT_ID + "\n")
        self.active = {"onemindd.service"}
        self.urls = {"http://127.0.0.1:7480/healthz": json.dumps({"ok": True, "boot_id": self.BOOT_ID}),
                     "http://127.0.0.1:7070/health": f"ok boot_id={self.BOOT_ID}"}
        self.rw = "rw,noatime"

    def stub(self, name, body):
        f = os.path.join(self.root, "bin", name)
        put(f, "#!/bin/bash\n" + body)
        os.chmod(f, 0o755)

    def run_check(self):
        urls = "\n".join(f'  "{u}") printf %s {json.dumps(b)} ;;' for u, b in self.urls.items())
        self.stub("curl", f'u="${{@: -1}}"\ncase "$u" in\n{urls}\n  *) exit 7 ;;\nesac\n')
        act = " ".join(sorted(self.active))
        self.stub("systemctl", f'[ "$1" = is-active ] || exit 3\nu="${{@: -1}}"\nfor a in {act}; do\n'
                               f'  [ "$a" = "$u" ] || [ "$a" = "$u.service" ] && {{ [ "$2" = --quiet ] || echo active; exit 0; }}\n'
                               'done\n[ "$2" = --quiet ] || echo inactive\nexit 3\n')
        self.stub("findmnt", f"echo {self.rw}\n")
        env = dict(os.environ, PATH=os.path.join(self.root, "bin") + ":/usr/bin:/bin", ONEMIND_GATE_ROOT=self.root)
        p = subprocess.run(["bash", LEAF_CHECK], capture_output=True, text=True, env=env, timeout=30)
        return p.returncode, p.stdout.strip()

    # The nkey is a public key with no secret in it (gitleaks:allow).
    AUTH = ('# no_auth_user is gone (this comment must not trip the check)\n'
            'authorization {\n  users: [\n    {nkey: "UBSMVUZ4GQXTXWP5H5SMM4LPEZAIBCEU54ADTY25RCHRECSM2O5KJ25J", '  # gitleaks:allow
            'permissions: {publish: {allow: ["onemind.node.abc.status"]}}}  # onemindd\n  ]\n}\n')

    def leaf_conf(self, start, auth=None):
        put(os.path.join(self.root, "data/onemind/etc/nats/leaf.conf"),
            'server_name: "node-abc"\nlisten: "127.0.0.1:4222"\nhttp: "127.0.0.1:8222"\n' + (self.AUTH if auth is None else auth))
        self.active.add("onemind-nats-leaf.service")
        self.urls["http://127.0.0.1:8222/healthz?js-enabled-only=true"] = '{"status":"ok"}'
        self.urls["http://127.0.0.1:8222/varz"] = json.dumps({"server_name": "node-abc", "start": start})

    def iso(self, t):
        return subprocess.run(["date", "-u", "-d", f"@{t}", "+%Y-%m-%dT%H:%M:%S.123456789Z"],
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_healthy_unjoined_edge(self):
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertTrue(out.startswith("ok ("), out)
        self.assertIn("onemindd", out)
        self.assertIn("not joined", out)
        probe = rd(self.root, "data/onemind/.rw-probe")
        self.assertIn(self.BOOT_ID, probe)

    def test_healthy_joined_edge(self):
        self.leaf_conf(self.iso(self.btime + 20))
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertIn("leaf", out)

    def test_onemindd_down_or_stale(self):
        self.active.discard("onemindd.service")
        self.assertEqual(self.run_check(), (1, "fail G1: onemindd is not active"))
        self.active.add("onemindd.service")
        self.urls["http://127.0.0.1:7480/healthz"] = json.dumps({"ok": True, "boot_id": "an-old-boot"})
        rc, out = self.run_check()
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("fail G1:"), out)
        del self.urls["http://127.0.0.1:7480/healthz"]
        rc, out = self.run_check()
        self.assertTrue(out.startswith("fail G1:"), out)

    def test_any_hub_service_running_fails(self):
        for unit in HUB_UNITS:
            with self.subTest(unit=unit):
                self.active = {"onemindd.service", unit}
                rc, out = self.run_check()
                self.assertEqual(rc, 1)
                self.assertEqual(out, f"fail G2: hub service {unit.removesuffix('.service')} is running on an edge")

    def test_leaf_without_local_sign_in_fails(self):
        """G1: a leaf any local program can use (no nkey users, or a passwordless user) is a bad leaf."""
        for what, auth in (("no authorization block", ""),
                           ("a passwordless user", self.AUTH + 'no_auth_user: "sensor"\n')):
            with self.subTest(what):
                self.leaf_conf(self.iso(self.btime + 20), auth=auth)
                rc, out = self.run_check()
                self.assertEqual(rc, 1, out)
                self.assertTrue(out.startswith("fail G3:") and "local" in out, out)

    def test_leaf_nats_unhealthy_or_stale(self):
        self.leaf_conf(self.iso(self.btime + 20))
        self.active.discard("onemind-nats-leaf.service")
        rc, out = self.run_check()
        self.assertTrue(out.startswith("fail G3:"), out)
        self.active.add("onemind-nats-leaf.service")
        del self.urls["http://127.0.0.1:8222/healthz?js-enabled-only=true"]
        rc, out = self.run_check()
        self.assertTrue(out.startswith("fail G3:"), out)
        self.leaf_conf(self.iso(self.btime - 600))      # a start time from before this boot
        rc, out = self.run_check()
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("fail G3:") and "stale" in out, out)

    def test_data_and_local_api(self):
        self.rw = "ro,noatime"
        self.assertEqual(self.run_check(), (1, "fail G5: /data not mounted rw"))
        self.rw = "rw"
        self.urls["http://127.0.0.1:7070/health"] = "ok boot_id=an-old-boot"
        self.assertEqual(self.run_check(), (1, "fail G6: local OneMind API not answering for this boot"))


class EdgeHarness(unittest.TestCase):
    def test_criteria_preregistered(self):
        with open(os.path.join(ROOT, "test", "qemu", "CRITERIA-EDGE.md"), "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        self.assertIn(f"{h}  CRITERIA-EDGE.md", rd("test", "qemu", "PREREGISTRATION.sha256"))

    def test_bad_leaf_bundle_is_opt_in(self):
        m = rd("test", "qemu", "mkfixtures.sh")
        self.assertRegex(m, r'if \[ "\$\{EDGE:-0\}" = 1 \]; then')
        self.assertIn("bundle v 8 bad-leaf dev", m)
        mk = rd("Makefile")
        self.assertIn("-e EDGE=$(EDGE)", mk)
        self.assertRegex(mk, r"(?m)^edge:")
        self.assertIn("/src/test/qemu/edge.py", mk)

    def test_harness_matches_the_criteria(self):
        import importlib.util
        sp = importlib.util.spec_from_file_location("edge", os.path.join(ROOT, "test", "qemu", "edge.py"))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        crit = rd("test", "qemu", "CRITERIA-EDGE.md")
        self.assertEqual(m.ORDER, ["EG1", "EG2", "EG3", "EG4", "EG5", "EG6", "EG7"])
        for u in m.HUB_UNITS:
            self.assertIn(f"`{u}`", crit)
        for s in m.HUB_SECRETS:
            self.assertIn(f"`{s}`", crit)
        self.assertEqual(m.TARGET_MIB, 300)
        seed = m.seed_userdata()
        self.assertIn("role: leaf", seed)
        self.assertEqual(fb.validate({"role": "leaf", "join_code": m.JOIN_CODE, "hub_addr": m.HUB_ADDR})["role"], "leaf")
        self.assertEqual(m.used_mib("MemTotal:  3000000 kB\nMemAvailable: 2795200 kB\n"), 200)


if __name__ == "__main__":
    unittest.main()
