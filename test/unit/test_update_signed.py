# SPDX-License-Identifier: Apache-2.0
"""The signed-update QEMU test (test/qemu/updatesigned.py, CRITERIA-UPDATE-SIGNED.md US0-US6): pre-registration, the
make/fixture wiring, the guest-to-host relay and the channel server's tamper and request log. Stdlib only; the TUF side
(test/qemu/usrepo.py with the box's go-tuf verifier) is os/update/tests/test_tuf_usrepo.py."""
import hashlib, importlib.util, os, socket, subprocess, sys, tempfile, threading, unittest, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def harness():
    sp = importlib.util.spec_from_file_location("updatesigned", os.path.join(ROOT, "test/qemu/updatesigned.py"))
    m = importlib.util.module_from_spec(sp)
    try:
        sp.loader.exec_module(m)
    except ModuleNotFoundError as e:       # firstboot.py needs PyYAML only inside f0, not at import
        raise unittest.SkipTest(str(e))
    return m


class Wiring(unittest.TestCase):
    def test_criteria_hash_is_registered(self):
        h = hashlib.sha256(open(os.path.join(ROOT, "test/qemu/CRITERIA-UPDATE-SIGNED.md"), "rb").read()).hexdigest()
        self.assertIn(h + "  CRITERIA-UPDATE-SIGNED.md", rd("test/qemu/PREREGISTRATION.sha256"))

    def test_make_target_builds_keys_fixtures_channels_then_runs_the_harness(self):
        mk = rd("Makefile")
        body = mk[mk.index("\nupdate-signed:"):mk.index("# Memory pressure")]
        order = ["usrepo.py keys", "fixtures BOARD=$(BOARD) SIGNED=1", "usrepo.py channels", "updatesigned.py"]
        pos = [body.index(s) for s in order]
        self.assertEqual(pos, sorted(pos))
        self.assertIn("--require-hashes", body)
        self.assertIn("-e SIGNED=$(SIGNED) -e US_OVERLAY=/out/us-$(BOARD)/overlay", mk)

    def test_fixtures_keep_the_signed_bundles_off_bundles_img_and_t0(self):
        fx = rd("test/qemu/mkfixtures.sh")
        self.assertIn('rm -rf "$W" "$OUT/us"', fx)                    # never stale: remade or removed every run
        self.assertIn("--overlay ${US_OVERLAY:?", fx)
        block = fx[fx.index('if [ "${SIGNED:-0}" = 1 ]; then'):fx.index('log "T0 checks"')]
        self.assertIn("bundle v 3 us-wrongca wrong", block)
        self.assertIn("bundle v 1 us-old dev", block)
        self.assertIn('mv "$W/bundles/us-wrongca.raucb" "$W/bundles/us-old.raucb" "$OUT/us/"', block)

    def test_the_vm_nic_is_unchanged_unless_a_harness_adds_to_it(self):
        rt = rd("test/qemu/run-tests.py")
        self.assertIn('self.nic_extra = ""', rt)
        self.assertIn('restrict=on,hostfwd=tcp:127.0.0.1:{self.fwd}-:8080{self.nic_extra}"', rt)

    def test_the_updater_config_never_overrides_the_trust_root(self):
        h = rd("test/qemu/updatesigned.py")
        conf = h[h.index("printf 'channel = security"):].split("\n", 1)[0]
        self.assertNotIn("tuf_root_dir", conf)
        self.assertIn("url = http://127.0.0.1:8000", conf)


class Relay(unittest.TestCase):
    def test_bytes_go_both_ways(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)

        def echo():
            c, _ = srv.accept()
            data = b""
            while True:
                b = c.recv(65536)
                if not b:
                    break
                data += b
            c.sendall(data[::-1])
            c.close()
        threading.Thread(target=echo, daemon=True).start()
        payload = os.urandom(300000)
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "test/qemu/usrelay.py"), str(srv.getsockname()[1])],
                           input=payload, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, payload[::-1])
        srv.close()


class Server(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        for p in ("C1", "files"):
            os.makedirs(os.path.join(self.d, p))
        open(os.path.join(self.d, "C1", "timestamp.json"), "w").write("{}")
        self.blob = os.urandom(3 * 1024 * 1024 + 7)
        open(os.path.join(self.d, "files", "b.raucb"), "wb").write(self.blob)
        self.ch = harness().Channel(self.d)
        self.addCleanup(self.ch.httpd.shutdown)

    def get(self, name):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.ch.port}/{name}") as r:
            return r.read()

    def test_metadata_from_the_channel_files_from_files_and_a_log(self):
        self.ch.serve("C1")
        self.assertEqual(self.get("timestamp.json"), b"{}")
        self.assertEqual(self.get("b.raucb"), self.blob)
        self.assertEqual(self.ch.fetched(), ["b.raucb"])
        with self.assertRaises(urllib.error.HTTPError):
            self.get("nope.json")
        self.ch.serve("C1")                                         # a new channel starts a new log
        self.assertEqual(self.ch.fetched(), [])

    def test_tamper_flips_exactly_one_byte_and_leaves_the_file(self):
        self.ch.serve("C1", tamper="b.raucb")
        got = self.get("b.raucb")
        self.assertEqual(len(got), len(self.blob))
        diff = [i for i in range(len(got)) if got[i] != self.blob[i]]
        self.assertEqual(diff, [len(self.blob) // 2])
        self.assertEqual(open(os.path.join(self.d, "files", "b.raucb"), "rb").read(), self.blob)


if __name__ == "__main__":
    unittest.main()
