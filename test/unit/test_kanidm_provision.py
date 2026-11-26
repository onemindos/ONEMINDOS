# SPDX-License-Identifier: Apache-2.0
"""Kanidm provisioning plan (os/identity/kanidm): pin, sign-in name and passkey policy (D-015, D-030)."""
import copy
import importlib.util
import io
import os
import re
import unittest
from contextlib import redirect_stdout

import yaml

try:
    import tomllib  # Python 3.11+ (CI and the dev venv run 3.12)
except ImportError:  # pragma: no cover
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location(
    "kanidm_provision", os.path.join(ROOT, "os", "identity", "kanidm", "kanidm-provision.py"))
kp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kp)
with open(os.path.join(ROOT, "os", "versions.lock.yaml"), encoding="utf-8") as _f:
    LOCK = yaml.safe_load(_f)
PLAN = kp.load()


class ShippedPlan(unittest.TestCase):
    def test_plan_is_valid(self):
        self.assertEqual(kp.validate(PLAN), [])

    def test_version_matches_lock(self):
        k = LOCK["identity"]["kanidm"]
        self.assertEqual(PLAN["kanidm_version"], k["version"])
        self.assertEqual(k["version"], "1.12.1")  # D-030 (3): HIGH DoS fix over 1.12.0
        self.assertEqual(k["tag"], "v" + k["version"])
        self.assertRegex(k["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(k["git_archive_sha256"], r"^[0-9a-f]{64}$")

    def test_canonical_sign_in_name(self):
        # D-030 (1): the passkey RP ID is onemind.local; the origin is that name or a sub-name of it.
        self.assertEqual(PLAN["server"]["domain"], "onemind.local")
        host = re.match(r"https://([^:/]+)", PLAN["server"]["origin"]).group(1)
        self.assertTrue(host == "onemind.local" or host.endswith(".onemind.local"), host)

    def test_new_invitees_are_passkey_only(self):
        # D-030 (2): every invite joins a group whose account policy needs a passkey.
        self.assertEqual(kp.invite_minimum(PLAN), "passkey")
        steps = kp.invite(PLAN, "newkid", "New Kid", "child")
        self.assertIn(["kanidm", "group", "add-members", "onemind_passkey_only", "newkid"], steps)
        self.assertIn(["kanidm", "group", "add-members", "onemind_children", "newkid"], steps)
        self.assertEqual(steps[-1][:5], ["kanidm", "person", "credential", "create-reset-token", "newkid"])
        self.assertEqual(steps[-1][-2:], ["--ttl", "86400"])

    def test_existing_people_keep_totp_fallback(self):
        # D-030 (2): no role group carries a credential policy, so people who are not invited after D-030
        # (not in onemind_passkey_only) keep their TOTP as a fallback.
        self.assertFalse(set(PLAN["role_groups"].values()) & set(PLAN["policy_groups"]))

    def test_plan_enables_policy_before_setting_it(self):
        steps = kp.plan(PLAN)
        enable = steps.index(["kanidm", "group", "account-policy", "enable", "onemind_passkey_only"])
        minimum = steps.index(["kanidm", "group", "account-policy", "credential-type-minimum",
                               "onemind_passkey_only", "passkey"])
        create = steps.index(["kanidm", "group", "create", "onemind_passkey_only"])
        self.assertLess(create, enable)
        self.assertLess(enable, minimum)
        for g in PLAN["role_groups"].values():
            self.assertIn(["kanidm", "group", "create", g], steps)

    @unittest.skipIf(tomllib is None, "tomllib needs Python 3.11+")
    def test_server_toml_is_valid_toml(self):
        t = tomllib.loads(kp.server_toml(PLAN))
        self.assertEqual(t["domain"], "onemind.local")
        self.assertEqual(t["origin"], PLAN["server"]["origin"])
        self.assertEqual(t["version"], "2")

    def test_cli_check(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(kp.main(["check"]), 0)
        self.assertIn("new invitees need passkey", out.getvalue())


class Rejects(unittest.TestCase):
    def broken(self, edit):
        cfg = copy.deepcopy(PLAN)
        edit(cfg)
        return kp.validate(cfg)

    def test_origin_outside_domain(self):
        # The lab's PK-5: an unrelated name cannot use or enrol the passkey.
        errs = self.broken(lambda c: c["server"].update(origin="https://hub.mesh.example:8445"))
        self.assertTrue(any("not 'onemind.local' or a sub-name" in e for e in errs), errs)

    def test_lookalike_suffix_is_not_a_sub_name(self):
        errs = self.broken(lambda c: c["server"].update(origin="https://evilonemind.local:8445"))
        self.assertTrue(any("sub-name" in e for e in errs), errs)

    def test_gateway_port(self):
        errs = self.broken(lambda c: c["server"].update(origin="https://onemind.local:8443", bindaddress="[::]:8443"))
        self.assertTrue(any("held by the gateway" in e for e in errs), errs)

    def test_bind_port_mismatch(self):
        errs = self.broken(lambda c: c["server"].update(bindaddress="[::]:9000"))
        self.assertTrue(any("bindaddress port differs" in e for e in errs), errs)

    def test_unknown_credential_type(self):
        errs = self.broken(lambda c: c["policy_groups"]["onemind_passkey_only"].update(credential_type_minimum="totp"))
        self.assertTrue(any("credential_type_minimum" in e for e in errs), errs)

    def test_invite_group_must_be_a_policy_group(self):
        errs = self.broken(lambda c: c["invite"].update(add_to_groups=["onemind_adults"]))
        self.assertTrue(any("not a policy group" in e for e in errs), errs)

    def test_reset_ttl_bounds(self):
        for ttl in (60, 172800):
            errs = self.broken(lambda c: c["invite"].update(reset_token_ttl_seconds=ttl))
            self.assertTrue(any("reset_token_ttl_seconds" in e for e in errs), (ttl, errs))

    def test_missing_role(self):
        errs = self.broken(lambda c: c["role_groups"].pop("guest"))
        self.assertTrue(any("role_groups" in e for e in errs), errs)

    def test_no_invite_policy_means_any(self):
        cfg = copy.deepcopy(PLAN)
        cfg["invite"]["add_to_groups"] = []
        self.assertEqual(kp.invite_minimum(cfg), "any")

    def test_invite_refuses_bad_role_and_name(self):
        with self.assertRaises(ValueError):
            kp.invite(PLAN, "someone", "Someone", "admin")
        with self.assertRaises(ValueError):
            kp.invite(PLAN, "Bad Name", "Someone", "adult")


if __name__ == "__main__":
    unittest.main()
