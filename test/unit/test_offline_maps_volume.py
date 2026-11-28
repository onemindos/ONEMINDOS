# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
LAYER = ROOT / "os/rootfs/layers/onemind/usr/lib/onemind"
MANIFEST = LAYER / "manifests/offline-maps-packs-pv.yaml"
APP = ROOT / "apps/offline-maps/manifests"
spec = importlib.util.spec_from_file_location("offline_maps_rebind", LAYER / "offline_maps_rebind.py")
rebind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rebind)


class OfflineMapsVolume(unittest.TestCase):
    def test_platform_and_app_manifests_pin_the_same_read_only_storage(self):
        pv = yaml.safe_load(MANIFEST.read_text())
        claim = next(document for document in yaml.safe_load_all((APP / "pvc.yaml").read_text())
                     if document["metadata"]["name"] == rebind.NAME)
        volume = pv["spec"]
        self.assertEqual(volume["claimRef"], rebind.CLAIM)
        self.assertEqual(volume["persistentVolumeReclaimPolicy"], "Retain")
        self.assertEqual(volume["local"], {"path": rebind.PATH})
        self.assertEqual(volume["capacity"], claim["spec"]["resources"]["requests"])
        self.assertEqual(volume["storageClassName"], "")
        self.assertEqual(claim["spec"]["storageClassName"], "")
        self.assertEqual(claim["spec"]["volumeName"], pv["metadata"]["name"])
        self.assertEqual(volume["nodeAffinity"]["required"]["nodeSelectorTerms"], [
            {"matchExpressions": [{"key": "node-role.kubernetes.io/control-plane", "operator": "In", "values": ["true"]}]}
        ])
        pod = yaml.safe_load((APP / "deployment.yaml").read_text())["spec"]["template"]["spec"]
        self.assertEqual(pod["volumes"], [v for v in pod["volumes"] if "hostPath" not in v])
        self.assertIn({"name": "packs", "persistentVolumeClaim": {"claimName": rebind.NAME, "readOnly": True}}, pod["volumes"])
        viewer, tile_server = pod["containers"]
        self.assertIn({"name": "packs", "mountPath": "/packs", "readOnly": True}, viewer["volumeMounts"])
        self.assertFalse(any(mount["name"] == "packs" for mount in tile_server["volumeMounts"]))

    def test_image_developer_installer_and_smoke_use_the_platform_manifest(self):
        k3s_unit = ROOT / "os/rootfs/layers/base/usr/lib/systemd/system/k3s.service"
        self.assertIn("cp /usr/lib/onemind/manifests/*.yaml", k3s_unit.read_text())
        installer = (ROOT / "deploy/install.sh").read_text()
        self.assertIn('local manifest="$layer/onemind/manifests/offline-maps-packs-pv.yaml"', installer)
        self.assertIn('"$BIN/k3s" kubectl apply -f "$manifest"', installer)
        self.assertIn(str(MANIFEST.relative_to(ROOT)), (ROOT / "sdk/tools/ci/map-packs-volume.sh").read_text())

    def test_reinstall_reserves_the_released_volume_without_a_stale_claim_uid(self):
        volume = yaml.safe_load(MANIFEST.read_text())
        volume["metadata"]["resourceVersion"] = "100"
        volume["spec"]["claimRef"]["uid"] = "old-claim"
        volume["status"] = {"phase": "Released"}
        self.assertEqual(rebind.release_patch(volume), [
            {"op": "test", "path": "/metadata/resourceVersion", "value": "100"},
            {"op": "replace", "path": "/spec/claimRef", "value": rebind.CLAIM},
        ])
        for phase, ns, path in (("Bound", "app-offline-maps", rebind.PATH),
                                ("Released", "app-other", rebind.PATH),
                                ("Released", "app-offline-maps", "/unrelated")):
            changed = copy.deepcopy(volume)
            changed["status"]["phase"] = phase
            changed["spec"]["claimRef"]["namespace"] = ns
            changed["spec"]["local"]["path"] = path
            self.assertIsNone(rebind.release_patch(changed))
