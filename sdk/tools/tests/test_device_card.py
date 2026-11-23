# SPDX-License-Identifier: Apache-2.0
"""Device capability card (issue #727): the Python validator against the shared examples and fixtures.

The fixtures (sdk/schema/testdata/device-card/invalid.json) are the same ones the Go validator's
test reads, so the two validators are held to the same rules.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk" / "tools"))
from applib import devicecard  # noqa: E402

EXAMPLES = ROOT / "sdk" / "schema" / "examples" / "device-card"
FIXTURES = json.loads((ROOT / "sdk" / "schema" / "testdata" / "device-card" / "invalid.json").read_text())
NEAR_MISSES = json.loads((ROOT / "sdk" / "schema" / "testdata" / "device-card" / "valid.json").read_text())


def apply(doc, ops):
    doc = copy.deepcopy(doc)
    for op in ops:
        *parents, last = op[1].lstrip("/").split("/")
        node = doc
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node[part]
        key = int(last) if isinstance(node, list) else last
        if op[0] == "del":
            del node[key]
        else:
            node[key] = op[2]
    return doc


class DeviceCard(unittest.TestCase):
    def test_both_examples_validate_in_under_five_seconds(self):
        start = time.monotonic()
        for name in ("temperature-sensor", "relay"):
            self.assertEqual(devicecard.validate((EXAMPLES / f"{name}.json").read_bytes()), [], name)
        self.assertLess(time.monotonic() - start, 5)

    def test_every_fixture_fails_with_its_rule(self):
        seen = set()
        for fx in FIXTURES["fixtures"]:
            base = json.loads((EXAMPLES / f"{fx['base']}.json").read_text())
            problems = devicecard.validate(json.dumps(apply(base, fx["ops"])).encode())
            rules = {p.rule for p in problems}
            self.assertTrue(set(fx["rules"]) <= rules, f"{fx['name']}: got {problems}")
            seen |= set(fx["rules"])
        self.assertEqual(seen, set(devicecard.RULES))   # one fixture per rule, at least

    def test_problems_never_echo_a_value(self):
        base = json.loads((EXAMPLES / "relay.json").read_text())
        card = apply(base, [["set", "/securityDefinitions/basic_sc", {"scheme": "basic", "password": "do-not-print"}]])
        self.assertNotIn("do-not-print", repr(devicecard.validate(json.dumps(card).encode())))

    def test_observe_on_a_writable_affordance_is_refused_by_the_schema_alone(self):
        # A registry that only reads the JSON Schema must not take an actuation as risk read either.
        for fx in FIXTURES["fixtures"]:
            if fx["rules"] == ["observe-read-only"]:
                card = apply(json.loads((EXAMPLES / f"{fx['base']}.json").read_text()), fx["ops"])
                self.assertFalse(devicecard._VALIDATOR.is_valid(card), fx["name"])

    def test_observe_stays_allowed_where_nothing_changes(self):
        base = json.loads((EXAMPLES / "relay.json").read_text())
        safe_action = {"title": "Read the meter", "safe": True, "output": {"type": "number", "unit": "W"},
                       "om:safety": {"class": "observe", "needsHold": False, "askers": ["owner", "automation"]}}
        card = apply(base, [["set", "/actions/meter", safe_action]])
        self.assertEqual(devicecard.validate(json.dumps(card).encode()), [])

    def test_harmless_urls_and_prose_are_not_credentials(self):
        base = json.loads((EXAMPLES / "relay.json").read_text())
        card = apply(base, [
            ["set", "/actions/switch/forms", [{"href": "https://relay.example/switch?on=1&unit=s#state"}]],
            ["set", "/description", "Is it on? It keeps no token or secret: the gateway holds those."],
        ])
        self.assertEqual(devicecard.validate(json.dumps(card).encode()), [])

    def test_near_misses_stay_valid_in_the_validator_and_the_schema(self):
        for fx in NEAR_MISSES["fixtures"]:
            card = apply(json.loads((EXAMPLES / f"{fx['base']}.json").read_text()), fx["ops"])
            self.assertEqual(devicecard.validate(json.dumps(card).encode()), [], fx["name"])
            self.assertTrue(devicecard._VALIDATOR.is_valid(card), fx["name"])

    def test_every_url_fixture_is_refused_whatever_the_field(self):
        # A user part or credential key is refused in any string, not only in a form href.
        base = json.loads((EXAMPLES / "relay.json").read_text())
        for fx in FIXTURES["fixtures"]:
            if fx["rules"] == ["credential-field"] and fx["ops"][0][1] == "/actions/switch/forms":
                card = apply(base, [["set", "/id", fx["ops"][0][2][0]["href"]]])
                rules = {p.rule for p in devicecard.validate(json.dumps(card).encode())}
                self.assertIn("credential-field", rules, fx["name"])

    def test_a_url_inside_prose_is_checked_word_by_word(self):
        # The shared fixtures cover it; spell out the two the review named, with the near miss beside them.
        base = json.loads((EXAMPLES / "relay.json").read_text())
        for text, bad in (("Web UI at https://admin:pw@relay/ for setup", True),
                          ("Open https://relay.example/x?access_token=abc now", True),
                          ("Open https://relay.example/x?unit=s now", False),
                          ("Is it on? It keeps no token or secret.", False)):
            card = apply(base, [["set", "/description", text]])
            rules = {p.rule for p in devicecard.validate(json.dumps(card).encode())}
            self.assertEqual("credential-field" in rules, bad, text)

    def test_class_to_risk_table_matches_the_action_ledger(self):
        # core/onemind_core/actions.py accepts only these risk classes; hold follows approvalcard.hold_required.
        self.assertEqual(devicecard.CLASS_RISK, {
            "observe": ("read", False), "reversible": ("write", False),
            "irreversible": ("destructive", False), "physical": ("actuate", True),
        })
        self.assertTrue(devicecard.hold_required(*devicecard.CLASS_RISK["irreversible"]))
        self.assertFalse(devicecard.hold_required(*devicecard.CLASS_RISK["reversible"]))

    def test_not_json_and_oversize_are_refused(self):
        self.assertEqual(devicecard.validate(b"{")[0].rule, "json")
        self.assertEqual(devicecard.validate(b'{"a": NaN}')[0].rule, "json")
        self.assertEqual(devicecard.validate(b" " * (devicecard.MAX_CARD_BYTES + 1))[0].rule, "size")

    def test_cli_exit_codes(self):
        tool = ROOT / "sdk" / "tools" / "applib" / "devicecard.py"
        ok = subprocess.run([sys.executable, "-I", str(tool)], capture_output=True, text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        bad = ROOT / "sdk" / "schema" / "testdata" / "device-card" / "invalid.json"
        r = subprocess.run([sys.executable, "-I", str(tool), str(bad)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
