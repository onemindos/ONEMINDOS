# SPDX-License-Identifier: Apache-2.0
"""validate-apps rule 11: system apps live in apps/_system/ and on the signed list (refs #234)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app_tools import SCHEMA, validate  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

LIST = {"notebook": {"id": "notebook", "class": "container", "update": "own", "disable": "allowed"}}
CLAIM = {"class": "container", "update": "own", "disable": "allowed", "keepDataOnDisable": True}


class SystemRuleTests(unittest.TestCase):
    def test_claim_outside_the_system_folder_is_refused(self):
        errs = validate.system_errors(Path("apps/sneaky"), {"system": CLAIM}, LIST)
        self.assertTrue(any("only allowed in apps/_system/" in e for e in errs))

    def test_ordinary_app_passes_and_cannot_use_a_listed_id(self):
        self.assertEqual(validate.system_errors(Path("apps/whoami"), {}, LIST), [])
        self.assertTrue(validate.system_errors(Path("apps/notebook"), {}, LIST))

    def test_system_folder_needs_the_list_and_a_matching_claim(self):
        d = Path("apps/_system/notebook")
        self.assertEqual(validate.system_errors(d, {"system": CLAIM}, LIST), [])
        self.assertTrue(validate.system_errors(Path("apps/_system/other"), {"system": CLAIM}, LIST))
        self.assertTrue(validate.system_errors(d, {}, LIST))
        bad = validate.system_errors(d, {"system": {**CLAIM, "disable": "never"}}, LIST)
        self.assertTrue(any("signed list says 'allowed'" in e for e in bad))

    def test_the_image_list_loads(self):
        lst = validate.load_system_list(validate.SYSTEM_LIST_PATH)
        self.assertEqual({"files", "approvals", "settings", "market"} & set(lst), {"files", "approvals", "settings", "market"})

    def test_schema_accepts_the_claim_and_refuses_junk(self):
        spec = SCHEMA["properties"]["spec"]["properties"]["system"]
        v = Draft202012Validator(spec)
        self.assertEqual(list(v.iter_errors(CLAIM)), [])
        self.assertTrue(list(v.iter_errors({**CLAIM, "keepDataOnDisable": False})))
        self.assertTrue(list(v.iter_errors({**CLAIM, "class": "vm"})))
        self.assertTrue(list(v.iter_errors({"class": "native"})))
        self.assertTrue(list(v.iter_errors({**CLAIM, "extra": 1})))


if __name__ == "__main__":
    unittest.main()
