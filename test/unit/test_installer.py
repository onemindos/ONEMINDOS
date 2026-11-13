# SPDX-License-Identifier: Apache-2.0
"""OneMind USB installer (os/boards/installer-x86_64): disk choice, role file, write + verify, LAN checks."""
import hashlib, io, json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "boards", "installer-x86_64", "rootfs", "usr", "lib", "onemind-installer"))
sys.path.insert(0, os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind"))
import onemind_installer as ins  # noqa: E402
import onemind_firstboot as fb  # noqa: E402

GB = 10 ** 9
LSBLK = {"blockdevices": [
    {"name": "sda", "path": "/dev/sda", "size": 8 * GB, "type": "disk", "ro": False, "model": "USB Stick", "tran": "usb",
     "children": [{"name": "sda1", "partlabel": "onemind-installer-esp", "mountpoints": [None]},
                  {"name": "sda2", "partlabel": "onemind-installer-root", "mountpoints": ["/"]}]},
    {"name": "nvme0n1", "path": "/dev/nvme0n1", "size": 500 * GB, "type": "disk", "ro": False,
     "model": "Fast <SSD>", "serial": "S1", "tran": "nvme"},
    {"name": "sdb", "path": "/dev/sdb", "size": 16 * GB, "type": "disk", "ro": False, "model": "Small"},
    {"name": "sdc", "path": "/dev/sdc", "size": 64 * GB, "type": "disk", "ro": True},
    {"name": "sdd", "path": "/dev/sdd", "size": 64 * GB, "type": "disk", "ro": False,
     "children": [{"name": "sdd1", "mountpoint": "/mnt"}]},
    {"name": "loop0", "path": "/dev/loop0", "size": 64 * GB, "type": "loop"},
    {"name": "sr0", "path": "/dev/sr0", "size": 64 * GB, "type": "disk"},
]}


class Disks(unittest.TestCase):
    def test_only_safe_disks_offered(self):
        t, s = ins.classify_disks(LSBLK, 32 * 2 ** 30)
        self.assertEqual([d["path"] for d in t], ["/dev/nvme0n1"])
        why = {d["path"]: d["reason"] for d in s}
        self.assertEqual(why["/dev/sda"], "this installer stick")
        self.assertTrue(why["/dev/sdb"].startswith("too small"))
        self.assertEqual(why["/dev/sdc"], "read-only")
        self.assertEqual(why["/dev/sdd"], "in use (mounted)")
        self.assertNotIn("/dev/loop0", why)
        self.assertNotIn("/dev/sr0", why)

    def test_page_escapes_and_warns(self):
        t, s = ins.classify_disks(LSBLK, 32 * 2 ** 30)
        page = ins.render_page({"version": "1", "board": "x86_64-efi"}, t, s, "idle")
        self.assertIn("Fast &lt;SSD&gt;", page)
        self.assertNotIn("<SSD>", page)
        self.assertIn("erased", page)
        self.assertIn('value="/dev/nvme0n1"', page)
        self.assertNotIn('value="/dev/sda"', page)


class Settings(unittest.TestCase):
    def roundtrip(self, s):
        """What the installer writes must be accepted by onemind-firstboot unchanged."""
        return fb.validate(fb.parse_conf(ins.render_conf(s)))

    def test_hub(self):
        s = ins.make_settings("hub", name="Home Lab")
        self.assertEqual(self.roundtrip(s), {"role": "hub", "name": "Home Lab"})

    def test_worker_and_leaf(self):
        for role in ("worker", "leaf"):
            s = ins.make_settings(role, hub="onemind.local", join_token="A" * 40)
            self.assertEqual(self.roundtrip(s), {"role": role, "name": "OneMind", "hub": "onemind.local", "join_token": "A" * 40})

    def test_setup_means_no_file(self):
        self.assertIsNone(ins.make_settings("setup"))
        self.assertIsNone(ins.make_settings(""))

    def test_rejects(self):
        for args in (("admin",), ("worker",), ("leaf", "", "onemind.local", "short"),
                     ("worker", "", "bad host!", "A" * 40), ("hub", "a#b"), ("hub", 'q"')):
            with self.assertRaises(ins.InstallError, msg=args):
                ins.make_settings(*args)


class Write(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(ins, "CHUNK", 4096)
        p.start(); self.addCleanup(p.stop)
        self.img = os.urandom(4096) + bytes(8192) + os.urandom(1000) + bytes(24)  # zero chunk in the middle
        self.sha = hashlib.sha256(self.img).hexdigest()
        self.dst = os.path.join(self.tmp.name, "disk")
        with open(self.dst, "wb") as f:
            f.write(b"\xff" * 32768)   # old data everywhere, larger than the image

    def fd(self):
        fd = os.open(self.dst, os.O_RDWR)
        self.addCleanup(os.close, fd)
        return fd

    def test_write_and_read_back(self):
        fd = self.fd()
        seen = []
        self.assertEqual(ins.write_image(io.BytesIO(self.img), fd, len(self.img), self.sha, lambda *a: seen.append(a)), self.sha)
        self.assertEqual(ins.read_back(fd, len(self.img)), self.sha)
        data = open(self.dst, "rb").read()
        self.assertEqual(data[:len(self.img)], self.img)          # zero chunk really zeroed, not skipped
        self.assertEqual(data[len(self.img):], b"\xff" * (32768 - len(self.img)))
        self.assertEqual(seen[-1], ("writing", len(self.img), len(self.img)))

    def test_mismatch_short_long(self):
        with self.assertRaisesRegex(ins.InstallError, "sha256"):
            ins.write_image(io.BytesIO(self.img), self.fd(), len(self.img), "0" * 64)
        with self.assertRaisesRegex(ins.InstallError, "early"):
            ins.write_image(io.BytesIO(self.img[:-1]), self.fd(), len(self.img), self.sha)
        with self.assertRaisesRegex(ins.InstallError, "longer"):
            ins.write_image(io.BytesIO(self.img + b"x"), self.fd(), len(self.img), self.sha)

    def test_read_back_detects_change(self):
        fd = self.fd()
        ins.write_image(io.BytesIO(self.img), fd, len(self.img), self.sha)
        os.pwrite(fd, b"\0", 5)
        self.assertNotEqual(ins.read_back(fd, len(self.img)), self.sha)


class Payload(unittest.TestCase):
    def test_load_and_validate(self):
        with tempfile.TemporaryDirectory() as d:
            good = {"board": "x86_64-efi", "version": "1", "image": "a.img", "image_size": 1024,
                    "image_sha256": "a" * 64, "file": "a.img.zst", "file_sha256": "b" * 64}
            for bad in ({"image_size": 1000}, {"file": "../x"}, {"image_sha256": "A" * 64}):
                json.dump(dict(good, **bad), open(os.path.join(d, "payload.json"), "w"))
                with self.assertRaises(ins.InstallError, msg=bad):
                    ins.load_payload(d)
            json.dump(good, open(os.path.join(d, "payload.json"), "w"))
            self.assertEqual(ins.load_payload(d)["path"], os.path.join(d, "a.img.zst"))


class Sgdisk(unittest.TestCase):
    def test_parse(self):
        text = ("Partition GUID code: 0FC63DAF-8483-4772-8E79-3D69D8477DE4 (Linux filesystem)\n"
                "Partition unique GUID: 1B4E28BA-2FA1-11D2-883F-B9A761BDE3FB\n"
                "First sector: 50335744 (at 24.0 GiB)\nLast sector: 67106815 (at 32.0 GiB)\n"
                "Partition name: 'onemind-data'\n")
        self.assertEqual(ins.parse_sgdisk_info(text), {"type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                         "guid": "1B4E28BA-2FA1-11D2-883F-B9A761BDE3FB", "first": 50335744, "last": 67106815,
                         "name": "onemind-data"})


class Web(unittest.TestCase):
    def setUp(self):
        self.t, _ = ins.classify_disks(LSBLK, 32 * 2 ** 30)
        self.st = ins.WebState("12345678")
        self.form = {"code": "12345678", "confirm": "ERASE", "disk": "/dev/nvme0n1", "role": "hub"}

    def test_accepts_complete_request(self):
        code, _, req = self.st.check(self.form, self.t)
        self.assertEqual(code, 202)
        self.assertEqual(req["disk"]["path"], "/dev/nvme0n1")
        self.assertEqual(req["settings"]["role"], "hub")

    def test_refusals(self):
        for change, want in (({"confirm": "yes"}, 400), ({"disk": "/dev/sda"}, 400), ({"role": "admin"}, 400)):
            code, _, req = self.st.check(dict(self.form, **change), self.t)
            self.assertEqual((code, req), (want, None), change)

    def test_wrong_code_and_lockout(self):
        for _ in range(ins.MAX_WEB_ATTEMPTS):
            self.assertEqual(self.st.check(dict(self.form, code="00000000"), self.t)[0], 403)
        code, msg, req = self.st.check(self.form, self.t)   # right code, but locked out now
        self.assertEqual((code, req), (403, None))
        self.assertIn("too many", msg)


class Menu(unittest.TestCase):
    PAYLOAD = {"version": "1", "board": "x86_64-efi", "image_size": 32 * 2 ** 30}

    def run_menu(self, answers, lock_ok=True):
        it = iter(answers)
        lines, calls = [], []
        ui = ins.PlainUI(inp=lambda prompt: next(it), out=lines.append)
        lock = mock.Mock(); lock.acquire.return_value = lock_ok
        with mock.patch.object(ins, "lan_hint", lambda: "LAN"), mock.patch.object(ins, "say", lines.append):
            res = ins.tui_once(ui, self.PAYLOAD, scan=lambda n: ins.classify_disks(LSBLK, n),
                               do_install=lambda *a: calls.append(a) or {"ok": 1}, lock=lock)
        return res, calls, "\n".join(lines)

    def test_confirmed_install(self):
        res, calls, text = self.run_menu(["1", "hub", "Home", "ERASE"])
        self.assertEqual(calls, [("/dev/nvme0n1", {"role": "hub", "name": "Home"}, self.PAYLOAD)])
        self.assertIn("WILL BE ERASED", text)
        self.assertIn("[1] /dev/nvme0n1", text)
        self.assertNotIn("] /dev/sda", text)

    def test_anything_but_the_word_writes_nothing(self):
        for word in ("yes", "erase", "", "ERASE!"):
            res, calls, text = self.run_menu(["1", "hub", "", word])
            self.assertEqual((res, calls), (None, []), word)
            self.assertIn("nothing was written", text)

    def test_bad_choice_and_lock_busy(self):
        self.assertEqual(self.run_menu(["9"])[1], [])
        res, calls, text = self.run_menu(["1", "setup", "ERASE"], lock_ok=False)
        self.assertEqual(calls, [])
        self.assertIn("already running", text)


if __name__ == "__main__":
    unittest.main()
