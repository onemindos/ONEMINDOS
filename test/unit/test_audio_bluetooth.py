# SPDX-License-Identifier: Apache-2.0
"""Step 3, audio and Bluetooth on the boards with a screen (lane s3-audio-bluetooth).

Static facts about the image definition (no VM): which boards carry PipeWire and BlueZ, that the Bluetooth
settings keep the adapter off and pairing closed by default, that pairings sit on /data, and the verdict logic of the
first-boot checks F16, F16r and F16u (test/qemu/firstboot.py) fed canned guest output. The QEMU run itself is CI's
`image` workflow; a real radio and a real speaker are the Dell all-in-one's job.
"""
import configparser, contextlib, glob, importlib.util, io, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ONEMIND = os.path.join(ROOT, "os", "rootfs", "layers", "onemind")
SCREEN = ("x86_64-efi", "rpi5")
PKGS = {"alsa-ucm-conf", "bluez", "dbus-user-session", "libspa-0.2-bluetooth", "pipewire", "pipewire-bin",
        "pipewire-pulse", "pulseaudio-utils", "wireplumber"}


def words(path):
    """The package names of a list file, comments stripped the way os/rootfs/Containerfile strips them."""
    out = []
    for line in open(path):
        out += re.sub(r"#.*", "", line).split()
    return out


def load_firstboot():
    spec = importlib.util.spec_from_file_location("firstboot", os.path.join(ROOT, "test", "qemu", "firstboot.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Packages(unittest.TestCase):
    def test_screen_boards_install_the_set_sorted(self):
        for b in SCREEN:
            w = words(os.path.join(ROOT, "os", "boards", b, "packages-debian.txt"))
            self.assertTrue(PKGS <= set(w), (b, PKGS - set(w)))
            tail = w[w.index("alsa-ucm-conf"):]
            self.assertEqual(tail, sorted(tail), f"{b}: keep the audio line sorted so merges stay trivial")

    def test_no_other_board_and_no_common_list_installs_them(self):
        for path in glob.glob(os.path.join(ROOT, "os", "boards", "*", "packages-*.txt")) + \
                glob.glob(os.path.join(ROOT, "os", "rootfs", "packages", "*.txt")):
            board = os.path.basename(os.path.dirname(path))
            if board in SCREEN and path.endswith("packages-debian.txt"):
                continue
            self.assertFalse({"pipewire", "wireplumber", "bluez"} & set(words(path)), path)

    def test_containerfile_reads_the_board_list(self):
        cf = open(os.path.join(ROOT, "os", "rootfs", "Containerfile")).read()
        self.assertIn("packages-${LEG}.txt", cf)


class BluetoothSettings(unittest.TestCase):
    CONF = os.path.join(ONEMIND, "usr", "lib", "onemind", "bluetooth", "main.conf")

    def parse(self):
        cp = configparser.ConfigParser(inline_comment_prefixes=None)
        cp.read(self.CONF)
        return cp

    def test_adapter_off_and_pairing_closed_by_default(self):
        cp = self.parse()
        self.assertEqual(cp["Policy"]["AutoEnable"], "false")
        self.assertEqual(cp["General"]["AlwaysPairable"], "false")
        self.assertEqual(cp["General"]["JustWorksRepairing"], "never")
        for k in ("DiscoverableTimeout", "PairableTimeout"):
            self.assertTrue(0 < int(cp["General"][k]) <= 300, k)   # 0 would mean open forever

    def test_dropin_points_bluetoothd_at_it_and_needs_the_data_mount(self):
        d = open(os.path.join(ONEMIND, "usr/lib/systemd/system/bluetooth.service.d/10-onemind.conf")).read()
        self.assertIn("ConditionPathIsDirectory=\n", d)            # Debian's adapter-present condition is cleared
        self.assertIn("Requires=var-lib-bluetooth.mount", d)
        self.assertIn("After=var-lib-bluetooth.mount", d)
        self.assertIn("ExecStart=\nExecStart=/usr/libexec/bluetooth/bluetoothd -f /usr/lib/onemind/bluetooth/main.conf", d)

    def test_pairings_are_a_bind_mount_of_a_data_directory(self):
        m = open(os.path.join(ONEMIND, "usr/lib/systemd/system/var-lib-bluetooth.mount")).read()
        for line in ("What=/data/state/var-lib-bluetooth", "Where=/var/lib/bluetooth", "Options=bind",
                     "RequiresMountsFor=/data", "ConditionPathExists=/usr/libexec/bluetooth/bluetoothd"):
            self.assertIn(line, m)
        self.assertNotIn("WantedBy", m)           # never part of local-fs: a dead data disk must not hold the boot
        for b in SCREEN:
            t = open(os.path.join(ROOT, "os/boards", b, "rootfs/usr/lib/tmpfiles.d/onemind-bluetooth.conf")).read()
            self.assertIn("d /data/state/var-lib-bluetooth 0700 root root", t)

    def test_bluetooth_is_started_only_on_the_screen_boards(self):
        for b in glob.glob(os.path.join(ROOT, "os", "boards", "*")):
            name = os.path.basename(b)
            post = os.path.join(b, "post-install.sh")
            text = open(post).read() if os.path.exists(post) else ""
            wired = "systemctl add-wants multi-user.target bluetooth.service" in text
            self.assertEqual(wired, name in SCREEN, name)
            self.assertFalse(os.path.exists(os.path.join(b, "rootfs/usr/lib/tmpfiles.d/onemind-bluetooth.conf")) != (name in SCREEN), name)
            # a symlink into the image's own /usr would dangle in the repo and break tools that read every file
            for root, _, files in os.walk(os.path.join(b, "rootfs")):
                for f in files:
                    p = os.path.join(root, f)
                    if os.path.islink(p):
                        self.assertTrue(os.path.exists(p), p)
        self.assertTrue(os.access(os.path.join(ROOT, "os/boards/x86_64-efi/post-install.sh"), os.X_OK))


class UbuntuHedge(unittest.TestCase):
    """nightly.yml builds board x86_64-efi with leg ubuntu; that leg gets no audio or Bluetooth packages (its
    packages-ubuntu.txt, when present, carries only the VA-API drivers of #1114), so the board's post-install step
    must skip its Debian-only checks there instead of failing the image build."""
    def test_no_audio_on_the_ubuntu_leg_and_post_install_skips_other_legs(self):
        board = os.path.join(ROOT, "os/boards/x86_64-efi")
        ubuntu = os.path.join(board, "packages-ubuntu.txt")
        if os.path.exists(ubuntu):
            self.assertFalse(PKGS & set(words(ubuntu)), "the Ubuntu leg must not install the audio set")
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as d:
            sh = os.path.join(d, "bin"); os.mkdir(sh)
            for tool in ("test", "systemctl"):          # would fail or record if reached
                open(os.path.join(sh, tool), "w").write("#!/bin/sh\necho reached >> " + os.path.join(d, "hit") + "\nexit 1\n")
                os.chmod(os.path.join(sh, tool), 0o755)
            env = {"PATH": sh + ":/usr/bin:/bin", "LEG": "ubuntu"}
            r = subprocess.run(["/bin/sh", os.path.join(board, "post-install.sh")], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("skipped", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(d, "hit")))
            env["LEG"] = "debian"                        # the Debian leg still runs (and here fails on the stub)
            r = subprocess.run(["/bin/sh", os.path.join(board, "post-install.sh")], env=env, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)

    def test_leg_reaches_the_script(self):
        text = open(os.path.join(ROOT, "os/rootfs/Containerfile")).read()
        self.assertRegex(text, r"(?m)^ARG LEG=debian")
        self.assertIn("/tmp/onemind/board/post-install.sh", text)


class VirtualSink(unittest.TestCase):
    def test_always_present_and_never_preferred_over_real_hardware(self):
        t = open(os.path.join(ONEMIND, "usr/share/pipewire/pipewire.conf.d/50-onemind-stream-sink.conf")).read()
        for needle in ("support.null-audio-sink", 'node.name              = "onemind-stream-sink"',
                       "media.class            = Audio/Sink", "priority.session       = 1"):
            self.assertIn(needle, t)


class FakeVM:
    """Answers each vm.run from a queue; the pairing-state call echoes back the marker it was asked to write."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.cmds = []

    def run(self, cmd, timeout=None):
        self.cmds.append(cmd)
        out = self.replies.pop(0) if self.replies else ""       # the failure diagnostics ask for more
        m = re.search(r"printf %s (\w+) >", cmd)
        if callable(out):
            out = out(m.group(1) if m else None)
        return 0, out


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


def pairing(token, root="/state/var-lib-bluetooth", active="active", dmark=None, droot="/"):
    return (f"MNT={root}\nMNTFS=/dev/vda3\nDATAFS=/dev/vda3\nDROOT={droot}\nMARK={token}\nDMARK={dmark if dmark is not None else token}\n"
            f"BTACTIVE={active}\n")


QUERY = ("".join(f"PKG {p} install ok installed\n" for p in ("pipewire", "pipewire-pulse", "wireplumber", "bluez", "libspa-0.2-bluetooth"))
         + "GLOBAL=enabled,enabled,enabled,\nBTENABLED=enabled\nBTCMD=/usr/libexec/bluetooth/bluetoothd -f /usr/lib/onemind/bluetooth/main.conf \n"
         "BUS_RC=0\nAUTO_RC=0\nALWAYS_RC=0\nDISC_RC=0\nPAIR_RC=0\nETCAUTO_RC=1\nADAPTERS=0\n")
AUDIO = "DAEMONS=active active active\nSINKS=0\tonemind-stream-sink\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED;\nDONE=1\n"


class F16Verdicts(unittest.TestCase):
    def setUp(self):
        self.fb = load_firstboot()
        self.fb.RESULTS.clear()

    def run_f16(self, query=QUERY, audio=AUDIO, pair=lambda t: pairing(t)):
        vm = FakeVM([query, pair, audio])
        tok = quiet(self.fb.f16, vm, "x86_64-efi")
        return tok, self.fb.RESULTS[-1], vm

    def test_all_good_passes_and_returns_the_marker(self):
        tok, r, vm = self.run_f16()
        self.assertEqual(r["verdict"], "PASS", r["detail"])
        self.assertEqual(len(tok), 32)
        self.assertIn("adapters=0", r["detail"])
        self.assertIn("systemctl start " + self.fb.F16_UNIT, vm.cmds[2])           # the session user's manager, stopped again at the end
        self.assertTrue(vm.cmds[2].rstrip().endswith("echo DONE=1"))
        self.assertIn("systemctl stop " + self.fb.F16_UNIT, vm.cmds[2])

    def test_a_controller_listed_in_the_vm_fails(self):
        _, r, _ = self.run_f16(query=QUERY.replace("ADAPTERS=0", "ADAPTERS=1"))
        self.assertEqual(r["verdict"], "FAIL")
        _, r, _ = self.run_f16(query=QUERY.replace("ADAPTERS=0", "ADAPTERS=?"))
        self.assertEqual(r["verdict"], "FAIL")

    def test_adapter_that_powers_on_by_itself_fails(self):
        _, r, _ = self.run_f16(query=QUERY.replace("AUTO_RC=0", "AUTO_RC=1"))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("adapter_off_by_default=False", r["detail"])

    def test_autoenable_in_etc_fails(self):
        _, r, _ = self.run_f16(query=QUERY.replace("ETCAUTO_RC=1", "ETCAUTO_RC=0"))
        self.assertEqual(r["verdict"], "FAIL")

    def test_pairing_directory_off_data_fails(self):
        _, r, _ = self.run_f16(pair=lambda t: pairing(t, root="/"))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("pairing_dir_on_data=False", r["detail"])

    def test_btrfs_layout_passes_but_a_bind_of_the_wrong_folder_fails(self):
        # On btrfs /data is the default subvolume @, so the bind's root is /@/state/...
        _, r, _ = self.run_f16(pair=lambda t: pairing(t, root="/@/state/var-lib-bluetooth", droot="/@"))
        self.assertEqual(r["verdict"], "PASS", r["detail"])
        _, r, _ = self.run_f16(pair=lambda t: pairing(t, root="/@/state/other", droot="/@"))
        self.assertEqual(r["verdict"], "FAIL")
        _, r, _ = self.run_f16(pair=lambda t: pairing(t, root="/state/var-lib-bluetooth", droot="/@"))
        self.assertEqual(r["verdict"], "FAIL")

    def test_marker_not_on_data_fails(self):
        _, r, _ = self.run_f16(pair=lambda t: pairing(t, dmark=""))
        self.assertEqual(r["verdict"], "FAIL")

    def test_missing_package_fails(self):
        _, r, _ = self.run_f16(query=QUERY.replace("PKG bluez install ok installed\n", ""))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("packages=False", r["detail"])

    def test_wrong_bluetoothd_config_fails(self):
        _, r, _ = self.run_f16(query=QUERY.replace(" -f /usr/lib/onemind/bluetooth/main.conf", ""))
        self.assertEqual(r["verdict"], "FAIL")

    def test_no_virtual_sink_fails(self):
        _, r, _ = self.run_f16(audio="DAEMONS=active active active\nSINKS=\nDONE=1\n")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("virtual_sink=False", r["detail"])

    def test_daemon_not_active_fails(self):
        _, r, _ = self.run_f16(audio=AUDIO.replace("active active active", "active inactive active"))
        self.assertEqual(r["verdict"], "FAIL")

    def test_no_screen_board_passes_only_with_nothing_installed(self):
        vm = FakeVM(["0\nMOUNT_RC=1\nBTENABLED=disabled\n"])
        self.assertIsNone(quiet(self.fb.f16, vm, "arm64-efi"))
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "PASS")
        vm = FakeVM(["3\nMOUNT_RC=1\nBTENABLED=disabled\n"])
        quiet(self.fb.f16, vm, "vm-do")
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "FAIL")

    def test_reboot_and_update_checks(self):
        tok = "ab" * 16
        quiet(self.fb.f16_after, FakeVM([pairing(tok)]), "F16r", tok)
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "PASS")
        quiet(self.fb.f16_after, FakeVM([pairing("cd" * 16, dmark="cd" * 16)]), "F16u", tok)
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "FAIL")          # a different marker: state was lost
        quiet(self.fb.f16_after, FakeVM([pairing(tok, active="inactive")]), "F16u", tok)
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "FAIL")

    def test_wired_in_between_f12_and_the_reboot(self):
        src = open(os.path.join(ROOT, "test", "qemu", "firstboot.py")).read()
        main = src[src.index("def main("):]
        self.assertLess(main.index("f12(vm, token)"), main.index("f16(vm, a.board)"))
        self.assertLess(main.index("f16(vm, a.board)"), main.index('vm.mark("F3 reboot keeps state")'))
        self.assertIn('f16_after(vm, "F16r"', main)
        self.assertIn('f16_after(vm, "F16u"', main)


if __name__ == "__main__":
    unittest.main()
