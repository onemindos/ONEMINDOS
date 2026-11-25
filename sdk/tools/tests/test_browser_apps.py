# SPDX-License-Identifier: Apache-2.0
"""Rules for the Market's Browsers row (apps/firefox, apps/chromium), checked on the files in the repo.

These are the things the founder asked us to refuse: the image's own port or terminal exposed, Chrome or Edge
images (licence), mutable tags, root, sudo. validate-apps checks digests and resources for every app; this
file pins the browser-specific promises so a later edit cannot quietly drop one.
"""
import json
import re
import unittest
from pathlib import Path

import yaml

APPS = Path(__file__).resolve().parents[3] / "apps"
BROWSERS = ["firefox", "chromium"]
FORBIDDEN_IDS = {"chrome", "google-chrome", "edge", "microsoft-edge"}
IMAGE = re.compile(r"^ghcr\.io/m1k1o/neko/(firefox|chromium):\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")


def load(app, name):
    return list(yaml.safe_load_all((APPS / app / "manifests" / name).read_text()))


class BrowserApps(unittest.TestCase):
    def test_no_chrome_or_edge_app(self):
        present = {p.name for p in APPS.iterdir() if p.is_dir()}
        self.assertEqual(present & FORBIDDEN_IDS, set())

    def test_manifest_facts(self):
        for app in BROWSERS:
            with self.subTest(app=app):
                m = yaml.safe_load((APPS / app / "onemind.app.yaml").read_text())
                self.assertEqual(m["metadata"]["license"], "Apache-2.0")
                self.assertEqual(m["spec"]["web"]["port"], 8080)
                self.assertGreaterEqual(m["spec"]["requires"]["minMemoryMb"], 1024)
                self.assertEqual(m["spec"]["credentials"]["password"], "generated")
                self.assertNotEqual(m["metadata"]["version"], "latest")

    def test_pod_is_pinned_non_root_and_closed(self):
        for app in BROWSERS:
            with self.subTest(app=app):
                (dep,) = load(app, "deployment.yaml")
                pod = dep["spec"]["template"]["spec"]
                self.assertTrue(pod["securityContext"]["runAsNonRoot"])
                self.assertEqual(pod["securityContext"]["runAsUser"], 1000)
                self.assertFalse(pod["automountServiceAccountToken"])
                self.assertNotIn("hostNetwork", pod)
                (c,) = pod["containers"]
                self.assertRegex(c["image"], IMAGE)
                self.assertFalse(c["securityContext"]["allowPrivilegeEscalation"])
                self.assertEqual(c["securityContext"]["capabilities"]["drop"], ["ALL"])
                self.assertEqual([p["containerPort"] for p in c["ports"]], [8080])
                self.assertTrue(all("hostPort" not in p for p in c["ports"]))
                self.assertEqual(c["resources"]["requests"]["memory"], "1Gi")
                shm = next(v for v in pod["volumes"] if v["name"] == "shm")
                self.assertEqual(shm["emptyDir"], {"medium": "Memory", "sizeLimit": "1Gi"})

    def test_one_profile_per_person_never_a_shared_one(self):
        # #692: the Deployment is a template the gateway copies per person; it never runs a shared profile.
        for app in BROWSERS:
            with self.subTest(app=app):
                m = yaml.safe_load((APPS / app / "onemind.app.yaml").read_text())
                volume = m["spec"]["browser"]["profileVolume"]
                (dep,) = load(app, "deployment.yaml")
                self.assertEqual(dep["spec"]["replicas"], 0)
                (vol,) = [v for v in dep["spec"]["template"]["spec"]["volumes"] if v["name"] == volume]
                (pvc,) = load(app, "pvc.yaml")
                self.assertEqual(vol["persistentVolumeClaim"]["claimName"], pvc["metadata"]["name"])

    def test_service_is_cluster_ip_web_only(self):
        for app in BROWSERS:
            with self.subTest(app=app):
                (svc,) = load(app, "service.yaml")
                self.assertEqual(svc["spec"]["type"], "ClusterIP")
                self.assertEqual([p["port"] for p in svc["spec"]["ports"]], [8080])

    def test_no_terminal_and_no_sudo(self):
        for app in BROWSERS:
            with self.subTest(app=app):
                # parsed values only: comments may say "no sudo"
                text = json.dumps([load(app, f.name) for f in sorted((APPS / app / "manifests").glob("*.yaml"))]).lower()
                text = text.replace("allowprivilegeescalation", "")
                for bad in ("sudo", "ttyd", "xterm", "gotty", "privileged", "nodeport", "loadbalancer", "hostport"):
                    self.assertNotIn(bad, text)
                (cm,) = load(app, "configmap.yaml")
                conf = cm["data"]["supervisord.conf"]
                self.assertNotIn("user=", conf)  # no root, so nothing switches user


if __name__ == "__main__":
    unittest.main()
