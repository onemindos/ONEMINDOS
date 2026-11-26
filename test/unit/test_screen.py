# SPDX-License-Identifier: Apache-2.0
"""UX-07 (#242): the box's own screen. The QR encoder is checked against a real decoder (zbar) when the PR is
made and pinned here by known answers; view()/render() are pure functions of the facts the box has."""
import hashlib, importlib.util, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib")
spec = importlib.util.spec_from_file_location("onemind_screen", os.path.join(LIB, "onemind", "onemind_screen.py"))
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)
def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()

# sha256 of the rows ("0"/"1" per module, newline between rows) of codes zbar decoded back to their text.
KNOWN = [("http://192.0.2.10:8080/", "M"), ("http://onemind.local:8080/", "L"), ("A", "M"),
         ("http://box-with-a-long-name.example.test:8080/some/path?code=12345678", "M"), ("x" * 100, "L")]


def digest(text, level):
    return hashlib.sha256("\n".join("".join(map(str, r)) for r in sc.qr_matrix(text, level)).encode()).hexdigest()


class Qr(unittest.TestCase):
    def test_sizes_follow_the_version(self):
        self.assertEqual(len(sc.qr_matrix("A", "M")), 21)
        self.assertEqual(len(sc.qr_matrix("http://192.0.2.10:8080/", "M")), 25)
        self.assertEqual(len(sc.qr_matrix("x" * 100, "L")), 37)
        with self.assertRaises(ValueError):
            sc.qr_matrix("x" * 200, "L")

    def test_fixed_patterns(self):
        m = sc.qr_matrix("http://192.0.2.10:8080/", "M")
        n = len(m)
        for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
            ring = [[m[r0 + r][c0 + c] for c in range(7)] for r in range(7)]
            self.assertEqual(ring[0], [1] * 7)
            self.assertEqual(ring[3][3], 1)
            self.assertEqual(ring[1][1:6], [0] * 5)
        self.assertEqual([m[6][i] for i in range(8, n - 8)], [1 - i % 2 for i in range(8, n - 8)])   # timing
        self.assertEqual(m[n - 8][8], 1)                                                              # dark module
        self.assertEqual([m[18][16:21], m[16][16:21]], [[1, 0, 1, 0, 1], [1, 1, 1, 1, 1]])            # alignment (v2)

    def test_known_answers(self):
        got = {k: digest(*k) for k in KNOWN}
        self.assertEqual(len(set(got.values())), len(got))        # different texts, different codes
        self.assertEqual(got, EXPECTED)

    def test_terminal_rows_are_black_on_white_with_a_quiet_zone(self):
        lines = sc.qr_lines("A")
        self.assertTrue(all(l.startswith("\x1b[30;47m") and l.endswith("\x1b[0m") for l in lines))
        body = re.sub(r"\x1b\[[0-9;]*m", "", lines[0])
        self.assertEqual(len(body), 21 + 4)
        self.assertEqual(len(lines), (21 + 4 + 1) // 2)
        self.assertTrue(body.startswith("  "))                    # top-left quiet zone is blank (white)


FACTS = {"host": "onemind", "name": None, "addrs": ["192.0.2.10"], "role": None, "setup_open": False, "ready": False}


class View(unittest.TestCase):
    def test_a_fresh_box_says_how_to_finish_setup(self):
        head, lines, url = sc.view({**FACTS, "setup_open": True})
        self.assertEqual(head, "FINISH SETUP")
        text = "\n".join(lines)
        self.assertIn("http://192.0.2.10:8080/", text)
        self.assertIn("onemind.local:8080", text)
        self.assertEqual(url, "http://192.0.2.10:8080/")

    def test_setup_shows_the_one_time_code(self):
        text = "\n".join(sc.view({**FACTS, "setup_open": True, "setup_code": "12345678"})[1])
        self.assertIn("Setup code (the page asks for it): 12345678", text)
        self.assertNotIn("Setup code", "\n".join(sc.view({**FACTS, "setup_open": True})[1]))

    def test_a_box_before_anything_answers_is_treated_as_setup(self):
        self.assertEqual(sc.view(FACTS)[0], "FINISH SETUP")

    def test_without_a_network_address_it_says_so_and_draws_no_qr(self):
        head, lines, url = sc.view({**FACTS, "addrs": [], "setup_open": True})
        self.assertIsNone(url)
        self.assertIn("no network yet", "\n".join(lines))

    def test_a_running_hub_shows_the_dashboard_address(self):
        head, lines, url = sc.view({**FACTS, "role": "hub", "ready": True})
        self.assertEqual(head, "ONEMIND IS RUNNING")
        self.assertEqual(url, "https://192.0.2.10/")
        text = "\n".join(lines)
        self.assertIn("https://onemind.local/", text)
        self.assertNotIn("8080", text)

    def test_tls_on_a_non_hub_role_value_still_shows_https(self):
        head, lines, url = sc.view({**FACTS, "role": "standalone", "tls": True, "ready": True})
        self.assertEqual(url, "https://192.0.2.10/")
        self.assertNotIn("8080", "\n".join(lines))

    def test_the_setup_wizard_stays_on_8080_even_with_tls_set(self):
        self.assertEqual(sc.view({**FACTS, "tls": True, "setup_open": True})[2], "http://192.0.2.10:8080/")

    def test_gather_reads_tls_from_gateway_env(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "data", "onemind", "etc"))
            self.assertFalse(sc.gather(d)["tls"])
            with open(os.path.join(d, "data", "onemind", "etc", "gateway.env"), "w") as f:
                f.write("ONEMIND_NET_TLS=1\n")
            self.assertTrue(sc.gather(d)["tls"])

    def test_a_hub_that_is_still_starting(self):
        self.assertEqual(sc.view({**FACTS, "role": "hub"})[0], "ONEMIND IS STARTING")

    def test_workers_point_at_the_hub_and_draw_no_code(self):
        head, lines, url = sc.view({**FACTS, "role": "worker", "ready": True})
        self.assertIsNone(url)
        self.assertIn("hub", "\n".join(lines))

    def test_the_screen_never_shows_a_token(self):
        for facts in (FACTS, {**FACTS, "setup_open": True}, {**FACTS, "role": "hub", "ready": True}):
            out = sc.render(facts)
            self.assertNotRegex(out, r"(?i)owner token:|join_token|[A-Za-z0-9_-]{32,}")
            self.assertIn("never shown on this screen", sc.render({**FACTS, "setup_open": True}))

    def test_render_includes_the_qr_only_with_an_address(self):
        self.assertIn("\x1b[30;47m", sc.render({**FACTS, "setup_open": True}))
        self.assertNotIn("\x1b[30;47m", sc.render({**FACTS, "addrs": [], "setup_open": True}))


class BoxCode(unittest.TestCase):
    """D-028, N-1 b: the code that proves a person stands at the box, shown only on this screen."""

    def write(self, d, doc):
        os.makedirs(os.path.join(d, "data", "onemind", "gateway"), exist_ok=True)
        with open(os.path.join(d, *sc.BOX_CODE), "w") as f:
            f.write(doc if isinstance(doc, str) else __import__("json").dumps(doc))

    def test_a_live_code_is_the_headline(self):
        head, lines, _ = sc.view({**FACTS, "role": "hub", "ready": True,
                                  "box_code": {"code": "482913", "what": "approve backup.restore"}})
        self.assertEqual(head, "CONFIRM AT THE BOX")
        text = "\n".join(lines)
        self.assertIn("Code:  482 913", text)
        self.assertIn("approve backup.restore", text)
        self.assertIn("https://192.0.2.10/", text)  # the usual lines stay below it

    def test_gather_reads_only_a_live_well_formed_code(self):
        import tempfile, time as t
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(sc.gather(d)["box_code"])
            self.write(d, {"code": "123456", "what": "x", "expires_at": int(t.time()) + 60})
            self.assertEqual(sc.gather(d)["box_code"], {"code": "123456", "what": "x"})
            self.write(d, {"code": "123456", "what": "x", "expires_at": int(t.time()) - 1})
            self.assertIsNone(sc.gather(d)["box_code"])  # expired: gone from the screen
            for bad in ("not json", "[]", '{"code": "12ab56", "expires_at": 9999999999}'):
                self.write(d, bad)
                self.assertIsNone(sc.gather(d)["box_code"])

    def test_the_gateway_unit_names_the_file_the_screen_reads(self):
        unit = read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-gateway.service")
        self.assertIn("ONEMIND_IDENTITY_BOX_CODE_FILE=/" + "/".join(sc.BOX_CODE), unit)


class Wiring(unittest.TestCase):
    def test_unit_takes_tty1_from_the_login_prompt_and_is_enabled_by_symlink(self):
        unit = read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-screen.service")
        self.assertIn("Conflicts=getty@tty1.service", unit)
        self.assertIn("Restart=always", unit)
        self.assertIn("ExecStart=/usr/lib/onemind/onemind-screen", unit)
        link = os.path.join(LIB, "systemd", "system", "multi-user.target.wants", "onemind-screen.service")
        self.assertEqual(os.readlink(link), "../onemind-screen.service")
        self.assertTrue(os.access(os.path.join(LIB, "onemind", "onemind-screen"), os.X_OK))

    def test_wrapper_uses_the_gateway_python(self):
        self.assertIn("/usr/lib/onemind/gateway/venv/bin/python3 -I /usr/lib/onemind/onemind_screen.py",
                      read("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind-screen"))

    def test_the_screen_only_reads(self):
        src = read("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind_screen.py")
        self.assertNotRegex(src, r"owner-token|secrets|join-token")


EXPECTED = {
    ("http://192.0.2.10:8080/", "M"): "eee1c7a307c6e74f734c8d9622a63c56d14a4fd4f58fc50c81bac7cde7d42edb",
    ("http://onemind.local:8080/", "L"): "89c97db9c098a8be1430cfe1c543f32ce8fe6c61a73d562a3007660b1f3f9791",
    ("A", "M"): "bc9009ae87ca68f1d256b69eb26362086d73d9f0b95f1e9f3dccae752626c3b6",
    ("http://box-with-a-long-name.example.test:8080/some/path?code=12345678", "M"): "ccdcb5c96c8dfd06d4bc8e89ef9f6a71842dfeb3fadc566003a7dcbcfcb49cbf",
    ("x" * 100, "L"): "8329f9290d7ddd42f689b11d49a87d8bfd8f0f431685f76b1392a6d5bad9bc6d",
}

if __name__ == "__main__":
    unittest.main()
