# SPDX-License-Identifier: Apache-2.0
"""Vaultwarden is an ordinary Market app (#679, founder 2026-11-25), not a built-in.

Held by these tests:
- it lives in apps/vaultwarden/ only, with no spec.system block, and is not on the signed system list;
- AGPL-3.0 upstream run as an unmodified container: licence L2, source link, image pinned by tag and digest;
- age_rating and age_reason are set; a gate-failing scan is never marked verified;
- hardening stays: non-root, seccomp, no service account token, nothing opened beyond the home network
  or the mesh, no admin token and no OneMind token planted in the app.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app_tools import SCHEMA, validate  # noqa: E402
import yaml  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "vaultwarden"


def manifest() -> dict:
    return yaml.safe_load((APP / "onemind.app.yaml").read_text(encoding="utf-8"))


def k8s_docs() -> list[dict]:
    out = []
    for f in sorted((APP / "manifests").glob("*.yaml")):
        out.extend(d for d in yaml.safe_load_all(f.read_text(encoding="utf-8")) if isinstance(d, dict))
    return out


def pods() -> list[dict]:
    return [(d.get("spec") or {}).get("template", {}).get("spec") or {} for d in k8s_docs()
            if d.get("kind") == "Deployment"]


class VaultwardenMarketTests(unittest.TestCase):
    def test_it_is_a_market_app_and_not_a_built_in(self):
        self.assertTrue((APP / "onemind.app.yaml").is_file())
        self.assertFalse((ROOT / "apps" / "_system" / "vaultwarden").exists())
        self.assertNotIn("system", manifest()["spec"])
        listed = validate.load_system_list(validate.SYSTEM_LIST_PATH)
        self.assertNotIn("vaultwarden", listed)
        self.assertEqual(list(Draft202012Validator(SCHEMA).iter_errors(manifest())), [])

    def test_licence_class_source_age_and_pinned_image(self):
        md = manifest()["metadata"]
        self.assertEqual((md["license"], md["licenceClass"]), ("AGPL-3.0", "L2"))
        self.assertEqual(md["source"], "https://github.com/dani-garcia/vaultwarden")
        self.assertEqual(md["age_rating"], 18)
        self.assertTrue(md["age_reason"])
        images = [c["image"] for p in pods() for c in p["containers"]]
        self.assertTrue(images)
        for img in images:
            self.assertRegex(img, r":[\w.\-]+@sha256:[0-9a-f]{64}$")
        readme = (APP / "README.md").read_text(encoding="utf-8")
        self.assertIn("ships it unmodified as a separate program", readme)
        self.assertNotRegex(readme, r"built in as \*\*Passwords\*\*")

    def test_a_gate_failing_image_is_never_marked_verified(self):
        scan = yaml.safe_load((APP / "scan.json").read_text(encoding="utf-8")) if (APP / "scan.json").is_file() else {}
        if scan.get("result") != "pass":
            self.assertNotEqual(manifest()["metadata"]["tier"], "verified")

    def test_hardening_and_no_planted_tokens(self):
        self.assertTrue(pods())
        for p in pods():
            self.assertIs(p["automountServiceAccountToken"], False)
            sc = p["securityContext"]
            self.assertTrue(sc["runAsNonRoot"])
            self.assertNotEqual(sc["runAsUser"], 0)
            self.assertEqual(sc["seccompProfile"]["type"], "RuntimeDefault")
            self.assertFalse(p.get("hostNetwork", False))
            for c in p["containers"]:
                self.assertIs(c["securityContext"]["allowPrivilegeEscalation"], False)
                self.assertEqual(c["securityContext"]["capabilities"]["drop"], ["ALL"])
                names = {e["name"] for e in c.get("env", [])}
                self.assertNotIn("ADMIN_TOKEN", names, "the /admin page stays off")
                self.assertFalse(any("ONEMIND" in n or "TOKEN" in n for n in names), names)
                self.assertNotIn("envFrom", c)
                self.assertTrue(all("hostPort" not in x for x in c.get("ports", [])))
        self.assertNotIn("hostPorts", manifest()["spec"])
        self.assertNotIn("credentials", manifest()["spec"])

    def test_nothing_opens_it_beyond_the_home_network_or_the_mesh(self):
        for d in k8s_docs():
            self.assertNotIn(d.get("kind"), {"Ingress", "IngressRoute", "Gateway", "HTTPRoute"})
            if d.get("kind") == "Service":
                self.assertEqual(d["spec"].get("type", "ClusterIP"), "ClusterIP")


if __name__ == "__main__":
    unittest.main()
