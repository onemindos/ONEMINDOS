# SPDX-License-Identifier: Apache-2.0
"""MACH-2 (#281): the machines layer's pins are one set of numbers in three places and a safe layout.

os/versions.lock.yaml, os/rootfs/fetch-machines.sh and the layer's extension.json must agree, the
image build must fetch and place the manifests, and nothing may switch on software emulation.
"""
import json
import os
import re
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rd(*p):
    return open(os.path.join(ROOT, *p)).read()


LAYER = ("os", "rootfs", "layers", "machines", "usr", "lib", "onemind", "extensions", "machines", "extension.json")


class MachinesLayerPins(unittest.TestCase):
    def setUp(self):
        self.lock = yaml.safe_load(rd("os", "versions.lock.yaml"))["machines_extension"]
        self.ext = json.loads(rd(*LAYER))
        self.fetch = rd("os", "rootfs", "fetch-machines.sh")

    def test_extension_json_equals_the_lock(self):
        lock = {**self.lock["kubevirt"]["files"], **self.lock["cdi"]["files"]}
        self.assertEqual(self.ext["files"], lock)
        self.assertEqual((self.ext["kubevirt"], self.ext["cdi"]), (self.lock["kubevirt"]["version"], self.lock["cdi"]["version"]))

    def test_fetch_script_uses_the_locked_versions_and_hashes(self):
        for name, sha in self.ext["files"].items():
            self.assertRegex(self.fetch, rf"{re.escape(name)}\s+\"\$\w+\"\s+{sha}\b")
        self.assertIn(f"KUBEVIRT_VERSION={self.lock['kubevirt']['version']}", self.fetch)
        self.assertIn(f"CDI_VERSION={self.lock['cdi']['version']}", self.fetch)

    def test_both_licences_were_read_at_the_pinned_tag(self):
        self.assertEqual((self.lock["kubevirt"]["licence"].split()[0], self.lock["cdi"]["licence"].split()[0]), ("Apache-2.0", "Apache-2.0"))

    def test_image_build_fetches_and_places_the_layer(self):
        c = rd("os", "rootfs", "Containerfile")
        self.assertIn("fetch-machines /opt/machines", c)
        self.assertIn("COPY os/rootfs/layers/machines/ /", c)
        self.assertIn("COPY --from=machines-fetch /opt/machines/ /usr/lib/onemind/extensions/machines/", c)

    def test_no_pinned_file_or_layer_file_asks_for_software_emulation(self):
        self.assertNotIn("useEmulation", self.fetch)
        self.assertNotIn("useEmulation", rd(*LAYER))


if __name__ == "__main__":
    unittest.main()
