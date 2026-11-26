# SPDX-License-Identifier: Apache-2.0
"""The personal vault spike (gateway permissions design 25g): criteria registered, every check reported."""

import hashlib
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPIKE = os.path.join(ROOT, "test", "qemu", "vaultspike")


def rd(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class VaultSpike(unittest.TestCase):
    def test_criteria_hash_is_registered(self):
        h = hashlib.sha256(open(os.path.join(ROOT, "test/qemu/CRITERIA-RECOVERY-VAULT.md"), "rb").read()).hexdigest()
        self.assertIn(h + "  CRITERIA-RECOVERY-VAULT.md", rd("test/qemu/PREREGISTRATION.sha256"))

    def test_every_pre_registered_check_is_reported_by_the_guest(self):
        ids = sorted(set(re.findall(r"^\| (RC\d) \|", rd("test/qemu/CRITERIA-RECOVERY-VAULT.md"), re.M)))
        self.assertEqual(ids, [f"RC{i}" for i in range(8)])
        guest = rd("test/qemu/vaultspike/guest.sh")
        for rc in ids:
            self.assertRegex(guest, rf"res {rc} ", rc)

    def test_keys_reach_the_guest_only_through_fw_cfg(self):
        inside, guest = rd("test/qemu/vaultspike/inside.sh"), rd("test/qemu/vaultspike/guest.sh")
        self.assertIn("-fw_cfg name=opt/onemind/vaultkey", inside)
        self.assertIn("/sys/firmware/qemu_fw_cfg/by_name/opt/onemind/", guest)
        # The guest copies keys only to tmpfs (/run) and never writes one under /data or /root.
        self.assertNotRegex(guest, r"(vaultkey|recoverykey)[^\n]*> */(data|root)/")
        # RC3's locked checks run before the guest reads a key in boot 2.
        boot2 = guest.split("# ---- boot 2.")[1]
        self.assertLess(boot2.index("readable=$(grep"), boot2.index("key vaultkey"))

    def test_naive_mode_exists_so_the_checks_can_fail(self):
        self.assertIn("--naive", rd("test/qemu/vaultspike/run.sh"))
        self.assertIn('MODE" = naive', rd("test/qemu/vaultspike/guest.sh"))


if __name__ == "__main__":
    unittest.main()
