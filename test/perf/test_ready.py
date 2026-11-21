# SPDX-License-Identifier: Apache-2.0
"""perf.py ready: each milestone gets its own uptime stamp (lab finding: all four read 501.5 s)."""

import importlib.util
import itertools
import pathlib
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("perf", pathlib.Path(__file__).with_name("perf.py"))
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)


class Api:
    def call(self, method, path):
        return 200, {}, None


class ReadyStamps(unittest.TestCase):
    def test_milestones_are_stamped_when_their_own_check_passes(self):
        clock = itertools.count(100, 20)  # every uptime() call is 20 s later (slow kubectl)
        nodes = {"items": [{"status": {"conditions": [{"type": "Ready", "status": "True"}]}}]}
        with mock.patch.object(perf, "uptime", lambda: float(next(clock))), \
             mock.patch.object(perf, "kubectl_json", lambda *a, **k: nodes if "nodes" in a else {"items": []}):
            done = {}
            perf.check_ready(Api(), None, done, ())
        self.assertEqual(set(done), {"k3s_node_ready", "k3s_addons_available", "gateway_healthz"})
        self.assertEqual(len(set(done.values())), 3, done)


if __name__ == "__main__":
    unittest.main()
