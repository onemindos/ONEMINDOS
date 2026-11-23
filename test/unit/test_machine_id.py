# SPDX-License-Identifier: Apache-2.0
"""#943: every machine built from one image must get its own machine-id (os/assemble/assemble.py).

The lab fleet test (#864) found that the image shipped a filled /var/lib/dbus/machine-id. On a read-only root with an
empty /etc/machine-id, systemd seeds the transient id from that D-Bus copy at every boot, so every machine from one
image booted with the same id and only the first one could join a hub (409 duplicate_node_id).
"""
import os, re, secrets, shutil, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))
import assemble  # noqa: E402

BUILD_ID = "0123456789abcdef0123456789abcdef\n"   # the id the build container happened to have
VALID = re.compile(r"^[0-9a-f]{32}$")


def resolve_in(tree, path):
    """Follow symlinks inside the tree (an absolute link target means the tree's own root, as on the booted machine)."""
    for _ in range(8):
        full = os.path.join(tree, path.lstrip("/"))
        if not os.path.islink(full):
            return full
        target = os.readlink(full)
        path = target if target.startswith("/") else os.path.join(os.path.dirname(path), target)
    raise AssertionError("symlink loop")


def read_in(tree, path):
    try:
        with open(resolve_in(tree, path)) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def boot(tree):
    """What systemd does at boot when /etc/machine-id is empty on a read-only root (machine-id(5), "Initialization";
    systemd src/shared/machine-id-setup.c): use a valid /var/lib/dbus/machine-id if there is one, else make a random
    id. It is transient, so this runs again at every boot."""
    if VALID.match(read_in(tree, "/etc/machine-id")):
        return read_in(tree, "/etc/machine-id")
    dbus = read_in(tree, "/var/lib/dbus/machine-id")
    return dbus if VALID.match(dbus) else secrets.token_hex(16)


class MachineId(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)

    def built_tree(self, name, dbus_as_link=False):
        tree = os.path.join(self.d, name)
        os.makedirs(os.path.join(tree, "etc"))
        os.makedirs(os.path.join(tree, "var", "lib", "dbus"))
        with open(os.path.join(tree, "etc", "machine-id"), "w") as f:
            f.write(BUILD_ID)
        mid = os.path.join(tree, "var", "lib", "dbus", "machine-id")
        if dbus_as_link:
            os.symlink("/etc/machine-id", mid)
        else:
            with open(mid, "w") as f:
                f.write(BUILD_ID)
        return tree

    def test_etc_machine_id_is_empty_not_missing(self):
        tree = self.built_tree("t")
        assemble.reset_machine_id(tree)
        p = os.path.join(tree, "etc", "machine-id")
        self.assertTrue(os.path.isfile(p) and not os.path.islink(p))
        self.assertEqual(os.path.getsize(p), 0)

    def test_dbus_copy_is_the_upstream_symlink(self):
        tree = self.built_tree("t")
        assemble.reset_machine_id(tree)
        mid = os.path.join(tree, "var", "lib", "dbus", "machine-id")
        self.assertTrue(os.path.islink(mid))
        self.assertEqual(os.readlink(mid), "/etc/machine-id")
        self.assertEqual(read_in(tree, "/var/lib/dbus/machine-id"), "")

    def test_no_build_id_is_left_in_the_tree(self):
        tree = self.built_tree("t")
        assemble.reset_machine_id(tree)
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            self.assertNotIn(BUILD_ID.strip(), read_in(tree, path), path)

    def test_already_a_symlink_and_no_dbus_dir_both_work(self):
        tree = self.built_tree("linked", dbus_as_link=True)
        assemble.reset_machine_id(tree)
        self.assertEqual(os.readlink(os.path.join(tree, "var", "lib", "dbus", "machine-id")), "/etc/machine-id")
        bare = os.path.join(self.d, "bare")
        os.makedirs(os.path.join(bare, "etc"))
        assemble.reset_machine_id(bare)
        self.assertEqual(os.readlink(os.path.join(bare, "var", "lib", "dbus", "machine-id")), "/etc/machine-id")

    def test_two_machines_from_one_image_get_different_ids(self):
        tree = self.built_tree("image")
        assemble.reset_machine_id(tree)
        a, b = os.path.join(self.d, "machine-a"), os.path.join(self.d, "machine-b")
        shutil.copytree(tree, a, symlinks=True)
        shutil.copytree(tree, b, symlinks=True)
        ida, idb = boot(a), boot(b)
        self.assertRegex(ida, VALID)
        self.assertNotEqual(ida, idb)
        self.assertNotEqual(ida, BUILD_ID.strip())

    def test_the_old_layout_really_collides(self):
        # The guard for the test itself: a tree that kept the D-Bus copy boots every machine with the same id.
        tree = self.built_tree("old")
        open(os.path.join(tree, "etc", "machine-id"), "w").close()
        self.assertEqual(boot(tree), boot(tree))
        self.assertEqual(boot(tree), BUILD_ID.strip())

    def test_finalize_calls_it(self):
        src = open(os.path.join(ROOT, "os", "assemble", "assemble.py")).read()
        body = src[src.index("def finalize("):]
        body = body[:body.index("\n\n\n")]
        self.assertIn("reset_machine_id(tree)", body)


if __name__ == "__main__":
    unittest.main()
