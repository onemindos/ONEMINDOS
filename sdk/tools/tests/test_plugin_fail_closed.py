# SPDX-License-Identifier: Apache-2.0
"""The schema-only CI gate cannot admit plugin declarations."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml
from test_app_tools import validate

class _AcceptsEverything:
    """A catalog whose manifest check passes, so only the plugin gate can refuse."""
    def validate(self, doc):
        return []


class PluginFailClosed(unittest.TestCase):
    def test_every_plugin_entry_point_refused_before_render(self):
        checker = validate.AppChecker(_AcceptsEverything(), "kustomize", "kubeconform")
        for field in ("extensions", "plugin", "permissions", "compat"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "onemind.app.yaml").write_text(yaml.safe_dump({"metadata": {"id": root.name}, "spec": {field: {}}}))
                with patch.object(checker, "render", side_effect=AssertionError("must not render")):
                    _, errors = checker.check(root)
                self.assertTrue(any("validator" in e for e in errors))
