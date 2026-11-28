#!/usr/bin/python3
# SPDX-License-Identifier: Apache-2.0
"""Re-reserve the released platform map volume for the Offline Maps claim."""

import json
import subprocess
from pathlib import Path

NAME = "offline-maps-packs"
CLAIM = {"namespace": "app-offline-maps", "name": NAME}
PATH = "/data/onemind/maps/packs"


def release_patch(volume):
    spec = volume["spec"]
    ref = spec.get("claimRef", {})
    if not (
        volume["metadata"]["name"] == NAME
        and volume.get("status", {}).get("phase") == "Released"
        and spec.get("persistentVolumeReclaimPolicy") == "Retain"
        and spec.get("local") == {"path": PATH}
        and all(ref.get(key) == value for key, value in CLAIM.items())
        and ref.get("uid")
    ):
        return None
    return [
        {"op": "test", "path": "/metadata/resourceVersion", "value": volume["metadata"]["resourceVersion"]},
        {"op": "replace", "path": "/spec/claimRef", "value": CLAIM},
    ]


def main():
    # Image and developer install use different root-only admin kubeconfig paths.
    image = Path("/run/k3s/k3s.yaml")
    config = image if image.is_file() else Path("/etc/rancher/k3s/k3s.yaml")
    command = ["/usr/local/bin/k3s", "kubectl", "--kubeconfig", str(config), "--request-timeout=10s"]
    result = subprocess.run(command + ["get", "pv", NAME, "--ignore-not-found", "-o", "json"],
                            check=True, capture_output=True, text=True, timeout=15)
    if result.stdout.strip():
        patch = release_patch(json.loads(result.stdout))
        if patch:
            subprocess.run(command + ["patch", "pv", NAME, "--type=json", "-p", json.dumps(patch)],
                           check=True, timeout=15)


if __name__ == "__main__":
    main()
