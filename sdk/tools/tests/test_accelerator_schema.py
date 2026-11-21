# SPDX-License-Identifier: Apache-2.0
"""S-5: `spec.requires.accelerator` in the app schema, and Ollama's use of it (CPU stays the default)."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "sdk" / "schema" / "onemind.app.schema.json").read_text())
V = Draft202012Validator(SCHEMA)
OLLAMA = yaml.safe_load((ROOT / "apps" / "ollama" / "onemind.app.yaml").read_text())


def errors(requires):
    doc = copy.deepcopy(OLLAMA)
    doc["spec"]["requires"] = requires
    return [e.message for e in V.iter_errors(doc)]


class AcceleratorSchema(unittest.TestCase):
    def test_ollama_validates_and_declares_an_optional_gpu(self):
        self.assertEqual([e.message for e in V.iter_errors(OLLAMA)], [])
        acc = OLLAMA["spec"]["requires"]["accelerator"]
        self.assertEqual((acc["capability"], acc["optional"], acc["overlay"]), ("gpu-compute", True, "manifests-gpu"))
        self.assertIs(OLLAMA["spec"]["requires"]["gpu"], False)     # no hard need: CPU-only boxes still install it
        self.assertTrue((ROOT / "apps" / "ollama" / acc["overlay"] / "kustomization.yaml").is_file())

    def test_a_required_accelerator_needs_gpu_true(self):
        acc = {"capability": "gpu-compute", "minMemoryMb": 8192}
        self.assertEqual(errors({"gpu": True, "minMemoryMb": 4096, "accelerator": acc}), [])
        self.assertTrue(errors({"gpu": False, "minMemoryMb": 4096, "accelerator": acc}))

    def test_an_optional_accelerator_may_leave_gpu_false(self):
        acc = {"capability": "gpu-compute", "optional": True}
        self.assertEqual(errors({"gpu": False, "minMemoryMb": 4096, "accelerator": acc}), [])

    def test_vendor_words_and_bad_values_are_refused(self):
        base = {"gpu": True, "minMemoryMb": 4096}
        for bad in ({"capability": "cuda"}, {"capability": "nvidia"}, {"capability": "gpu-compute", "minMemoryMb": 100},
                    {"capability": "gpu-compute", "vendor": "nvidia"}, {"capability": "gpu-compute", "overlay": "../x"},
                    {"minMemoryMb": 4096}):
            self.assertTrue(errors({**base, "accelerator": bad}), bad)


if __name__ == "__main__":
    unittest.main()
