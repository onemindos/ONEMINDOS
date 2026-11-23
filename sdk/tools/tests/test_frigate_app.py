# SPDX-License-Identifier: Apache-2.0
"""MKT-NVR-01 (#245): the Frigate NVR app's promises, checked on the files in the repo.

validate-apps and app-gate check every app (schema, pins, limits, isolation, scan). This file pins what is
special to a camera recorder so a later edit cannot quietly drop it:
- licence: Frigate core is MIT; Frigate+ (a paid model service) and the hardware-specific images are never used;
- recordings stay on the box: video lives on a box-local volume, is left out of every backup, the only port
  reachable from outside the pod is the signed-in web UI, and the seeded config makes no outbound calls;
- storage budget and retention are set before the first camera is added;
- the accelerator overlay runs the same scanned image, only on the GPU;
- the install sandbox (core/onemind_core/policy.py) accepts it once its reviewed row exists, and refuses
  nothing else.
"""
from __future__ import annotations

import dataclasses
import re
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "apps" / "frigate"
sys.path.insert(0, str(REPO / "core"))
from onemind_core import policy  # noqa: E402
from onemind_core.catalog import Catalog  # noqa: E402

IMAGE = re.compile(r"^ghcr\.io/blakeblackshear/frigate:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")
# Tags upstream publishes for other hardware (-tensorrt, -rocm, -rk, ...) are separate images the scan gate
# does not cover here; Frigate+ is a paid cloud model service.
FORBIDDEN = re.compile(r"tensorrt|rocm|-rk|synaptics|jp6|PLUS_API_KEY|api\.frigate\.video", re.I)
# Exactly what s6-overlay needs as root (proven by running the pinned image with each set; see README).
CAPS = {"CHOWN", "FOWNER", "SETGID", "SETUID"}
POD_SECURITY_RULES = {"S-01", "S-02", "S-03", "S-04", "S-05", "F-07"}


def manifest() -> dict:
    return yaml.safe_load((APP / "onemind.app.yaml").read_text())


def docs(name: str, folder: str = "manifests") -> list[dict]:
    return [d for d in yaml.safe_load_all((APP / folder / name).read_text()) if d]


def rendered() -> list[dict]:
    """The kustomization's resources, in order (kustomize only adds labels here)."""
    k = yaml.safe_load((APP / "manifests" / "kustomization.yaml").read_text())
    return [d for name in k["resources"] for d in docs(name)]


def pod() -> dict:
    (dep,) = [d for d in rendered() if d["kind"] == "Deployment"]
    return dep["spec"]["template"]["spec"]


def seed_config() -> dict:
    (cm,) = [d for d in rendered() if d["kind"] == "ConfigMap"]
    return yaml.safe_load(cm["data"]["config.yml"])


class Licence(unittest.TestCase):
    def test_mit_core_from_upstream(self):
        m = manifest()
        self.assertEqual(m["metadata"]["license"], "MIT")
        self.assertEqual(m["metadata"]["source"], "https://github.com/blakeblackshear/frigate")
        self.assertEqual(m["metadata"]["category"], "home")

    def test_only_the_standard_image_and_no_frigate_plus(self):
        for path in sorted(APP.rglob("*")):
            if path.is_file() and path.suffix in (".yaml", ".yml"):
                with self.subTest(path=path.name):
                    self.assertIsNone(FORBIDDEN.search(path.read_text()))
        p = pod()
        for c in p["containers"] + p.get("initContainers", []):
            self.assertRegex(c["image"], IMAGE)
        self.assertEqual(len({c["image"] for c in p["containers"] + p.get("initContainers", [])}), 1)

    def test_icon_is_not_the_upstream_brand(self):
        # Frigate's logo is a trademark outside the MIT licence (docs/static/img/branding/LICENSE.md upstream).
        self.assertIn("Neutral generated icon", (APP / "icon.svg").read_text())


class RecordingsStayOnTheBox(unittest.TestCase):
    def test_video_is_on_a_box_local_volume(self):
        p = pod()
        (c,) = p["containers"]
        mounts = {v["mountPath"]: v["name"] for v in c["volumeMounts"]}
        volumes = {v["name"]: v for v in p["volumes"]}
        media = volumes[mounts["/media/frigate"]]
        claim = media["persistentVolumeClaim"]["claimName"]
        (pvc,) = [d for d in rendered() if d["kind"] == "PersistentVolumeClaim" and d["metadata"]["name"] == claim]
        self.assertIn(pvc["spec"].get("storageClassName"), (None, "local-path", "onemind-local"))
        self.assertEqual(pvc["spec"]["accessModes"], ["ReadWriteOnce"])
        for v in p["volumes"]:
            self.assertFalse({"nfs", "hostPath", "csi", "iscsi", "cephfs"} & set(v), v["name"])

    def test_video_never_goes_into_a_backup(self):
        exclude = manifest()["spec"]["backup"]["exclude"]
        for folder in ("recordings/", "clips/", "exports/"):
            self.assertIn(folder, exclude)
        self.assertNotIn("content", manifest()["spec"]["backup"])  # no opt-in tier that could copy video out

    def test_only_the_signed_in_ui_is_reachable(self):
        (svc,) = [d for d in rendered() if d["kind"] == "Service"]
        self.assertEqual(svc["spec"]["type"], "ClusterIP")
        self.assertEqual([p["port"] for p in svc["spec"]["ports"]], [8971])
        self.assertEqual(manifest()["spec"]["web"]["port"], 8971)
        (c,) = pod()["containers"]
        # 5000 is upstream's unauthenticated port, 8554/8555 its RTSP and WebRTC restreams: none is declared.
        self.assertEqual([p["containerPort"] for p in c["ports"]], [8971])
        self.assertTrue(all("hostPort" not in p for p in c["ports"]))
        self.assertNotIn("hostNetwork", pod())

    def test_seeded_config_makes_no_outbound_calls(self):
        cfg = seed_config()
        self.assertIs(cfg["telemetry"]["version_check"], False)   # api.github.com on every start
        self.assertIs(cfg["mqtt"]["enabled"], False)
        self.assertIs(cfg["tls"]["enabled"], False)               # the gateway proxy fronts 8971 inside the box
        for key in ("genai", "plus", "notifications", "semantic_search", "face_recognition", "lpr"):
            self.assertNotIn(key, cfg)
        self.assertEqual(cfg["cameras"], {})
        (c,) = pod()["containers"]
        env = {e["name"]: e.get("value") for e in c.get("env", [])}
        self.assertEqual(env.get("HF_HUB_OFFLINE"), "1")
        self.assertEqual(env.get("TRANSFORMERS_OFFLINE"), "1")
        self.assertNotIn("egress", manifest()["spec"])            # no internet hostnames asked for

    def test_seed_never_overwrites_the_owners_config(self):
        (init,) = pod()["initContainers"]
        script = " ".join(init["command"])
        self.assertIn("test -s /config/config.yml ||", script)


class StorageBudgetAndRetention(unittest.TestCase):
    def test_retention_is_set_before_the_first_camera(self):
        rec = seed_config()["record"]
        self.assertIs(rec["enabled"], True)
        self.assertEqual(rec["continuous"]["days"], 0)
        self.assertGreater(rec["motion"]["days"], 0)
        for kind in ("alerts", "detections"):
            self.assertGreater(rec[kind]["retain"]["days"], 0)
        self.assertGreater(seed_config()["snapshots"]["retain"]["default"], 0)

    def test_storage_budget(self):
        sizes = {d["metadata"]["name"]: d["spec"]["resources"]["requests"]["storage"]
                 for d in rendered() if d["kind"] == "PersistentVolumeClaim"}
        self.assertEqual(sizes, {"frigate-config": "2Gi", "frigate-media": "100Gi"})
        volumes = {v["name"]: v for v in pod()["volumes"]}
        self.assertEqual(volumes["cache"]["emptyDir"], {"medium": "Memory", "sizeLimit": "1Gi"})
        self.assertEqual(volumes["shm"]["emptyDir"], {"medium": "Memory", "sizeLimit": "512Mi"})
        (c,) = pod()["containers"]
        self.assertEqual(c["resources"]["limits"]["memory"], "4Gi")
        self.assertGreaterEqual(manifest()["spec"]["requires"]["minMemoryMb"], 4096)


class Accelerator(unittest.TestCase):
    def test_gpu_is_optional_and_uses_the_same_scanned_image(self):
        acc = manifest()["spec"]["requires"]["accelerator"]
        self.assertEqual(acc, {"capability": "gpu-compute", "minMemoryMb": 1024, "optional": True,
                               "overlay": "manifests-gpu"})
        self.assertIs(manifest()["spec"]["requires"]["gpu"], False)
        k = yaml.safe_load((APP / "manifests-gpu" / "kustomization.yaml").read_text())
        self.assertEqual(k["resources"], ["../manifests"])
        self.assertNotIn("images", k)
        ops = [op for p in k["patches"] for op in yaml.safe_load(p["patch"])]
        self.assertFalse([op for op in ops if "image" in op["path"]])
        paths = {op["path"] for op in ops}
        self.assertIn("/spec/template/spec/runtimeClassName", paths)
        self.assertIn("/spec/template/spec/containers/0/resources/limits/nvidia.com~1gpu", paths)
        (seed,) = [op["value"] for op in ops if op["path"] == "/data/config.yml"]
        gpu_cfg = yaml.safe_load(seed)
        self.assertEqual(gpu_cfg.pop("ffmpeg"), {"hwaccel_args": "preset-nvidia"})
        self.assertEqual(gpu_cfg, seed_config())  # otherwise the same seed, retention and privacy included


class InstallSandbox(unittest.TestCase):
    """What the gateway does at install: core/onemind_core/policy.py over the app's objects."""

    def setUp(self):
        self.rules = policy.load_rules(REPO / "sdk" / "policy" / "app-objects.yaml")
        self.m = manifest()

    def with_row(self, row: dict | None):
        reviewed = {k: v for k, v in self.rules.reviewed.items() if k != "frigate"}
        if row is not None:
            reviewed["frigate"] = row
        return dataclasses.replace(self.rules, reviewed=reviewed)

    def test_kustomization_tree_passes(self):
        self.assertEqual(policy.check_kustomization(APP / "manifests", APP, self.rules), [])
        self.assertEqual(policy.check_kustomization(APP / "manifests-gpu", APP, self.rules), [])

    def test_passes_with_the_reviewed_row_it_needs(self):
        row = {"level": "baseline", "reviewed": "pending", "reason": "s6-overlay as root",
               "add_capabilities": sorted(CAPS)}
        self.assertEqual(policy.check_objects(rendered(), "frigate", self.m, self.with_row(row)), [])

    def test_without_the_row_only_pod_security_is_refused(self):
        found = policy.check_objects(rendered(), "frigate", self.m, self.with_row(None))
        self.assertTrue(found)
        self.assertEqual({v.rule for v in found} - POD_SECURITY_RULES, set(), [v.rule for v in found])


class Catalogue(unittest.TestCase):
    def test_market_lists_it(self):
        # GET /v1/apps and the dashboard's Market read this catalogue.
        cat = Catalog(REPO / "apps", REPO / "sdk" / "schema" / "onemind.app.schema.json")
        self.assertEqual(cat.validate(manifest()), [])
        entry = cat.load().get("frigate")
        self.assertIsNotNone(entry, cat.errors.get("frigate"))
        self.assertEqual(entry.summary()["id"], "frigate")


if __name__ == "__main__":
    unittest.main()
