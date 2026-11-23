# SPDX-License-Identifier: Apache-2.0
"""Passwords built in (#679): Vaultwarden is a system app, honest about its licence, its scan and its reach.

What these tests hold the repo to:
- apps/_system/vaultwarden/ is the only copy, its id is on the signed list, and its spec.system matches;
- the app page has what it needs: licence AGPL-3.0 and a source link to the upstream repository;
- a gate-failing image is never marked verified (the tier follows the scan, CI sets it);
- no exposure outside the home network or the mesh: no host ports, no NodePort or LoadBalancer
  Service, no Ingress, no host network. Reaching it goes through the gateway's app proxy only;
- no admin token and no OneMind token is planted in the app: the vault password is the person's own.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app_tools import SCHEMA, validate  # noqa: E402
import yaml  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "_system" / "vaultwarden"


def manifest() -> dict:
    return yaml.safe_load((APP / "onemind.app.yaml").read_text(encoding="utf-8"))


def k8s_docs() -> list[dict]:
    out = []
    for f in sorted((APP / "manifests").glob("*.yaml")):
        out.extend(d for d in yaml.safe_load_all(f.read_text(encoding="utf-8")) if isinstance(d, dict))
    return out


class PasswordsBuiltInTests(unittest.TestCase):
    def test_vaultwarden_lives_only_in_the_system_folder(self):
        self.assertTrue((APP / "onemind.app.yaml").is_file())
        self.assertFalse((ROOT / "apps" / "vaultwarden").exists(), "a second copy in apps/ would be a Market app")

    def test_it_is_on_the_signed_list_and_claims_exactly_what_the_list_says(self):
        listed = validate.load_system_list(validate.SYSTEM_LIST_PATH)
        self.assertEqual({k: listed["vaultwarden"][k] for k in ("class", "update", "disable")},
                         {"class": "container", "update": "own", "disable": "allowed"})
        self.assertEqual(listed["vaultwarden"]["name"], "Passwords")
        spec = manifest()["spec"]
        self.assertEqual(spec["system"], {"class": "container", "update": "own", "disable": "allowed",
                                          "keepDataOnDisable": True})
        self.assertEqual(validate.system_errors(APP, spec, listed), [])
        self.assertEqual(list(Draft202012Validator(SCHEMA).iter_errors(manifest())), [])

    def test_app_page_shows_the_licence_and_the_upstream_source(self):
        md = manifest()["metadata"]
        self.assertEqual(md["license"], "AGPL-3.0")
        self.assertEqual(md["source"], "https://github.com/dani-garcia/vaultwarden")
        self.assertEqual(md["links"]["github"], md["source"])
        readme = (APP / "README.md").read_text(encoding="utf-8")
        self.assertIn("ships it unmodified as a separate program", readme)

    def test_a_gate_failing_image_is_never_marked_verified(self):
        scan = yaml.safe_load((APP / "scan.json").read_text(encoding="utf-8"))
        tier = manifest()["metadata"]["tier"]
        if scan["result"] != "pass":
            self.assertNotEqual(tier, "verified")

    def test_nothing_opens_it_beyond_the_home_network_or_the_mesh(self):
        self.assertNotIn("hostPorts", manifest()["spec"])
        docs = k8s_docs()
        self.assertTrue(docs)
        for d in docs:
            self.assertNotIn(d.get("kind"), {"Ingress", "IngressRoute", "Gateway", "HTTPRoute"})
            if d.get("kind") == "Service":
                self.assertIn(d["spec"].get("type", "ClusterIP"), {"ClusterIP"})
            pod = (d.get("spec") or {}).get("template", {}).get("spec") or {}
            self.assertFalse(pod.get("hostNetwork", False))
            for c in pod.get("containers", []):
                self.assertTrue(all("hostPort" not in p for p in c.get("ports", [])))

    def test_no_admin_or_onemind_token_is_planted_in_the_app(self):
        for d in k8s_docs():
            pod = (d.get("spec") or {}).get("template", {}).get("spec") or {}
            for c in pod.get("containers", []):
                names = {e["name"] for e in c.get("env", [])}
                self.assertNotIn("ADMIN_TOKEN", names, "the /admin page stays off")
                self.assertFalse(any("ONEMIND" in n or "TOKEN" in n for n in names), names)
                self.assertNotIn("envFrom", c)
        self.assertNotIn("credentials", manifest()["spec"], "no generated shared login: each person owns their vault")


if __name__ == "__main__":
    unittest.main()
