# SPDX-License-Identifier: Apache-2.0
"""The machines extension: KubeVirt and CDI, turned on and off by an owner (MACH-2, #281).

Machines are an optional layer of the image (os/rootfs/layers/machines). The image carries four
pinned release manifests and `extension.json` with their sha256. Nothing is applied until an owner
approves the `machines.enable` action; `machines.disable` takes it all out again.

Safety rules kept here:
- every manifest is re-hashed against extension.json before it is applied (a changed file is refused);
- the operators' container images are named by mutable tag today (digests are UNVERIFIED until LT-MACH-2),
  so install is refused unless the box was started with ONEMIND_MACHINES_ALLOW_TAG_IMAGES=1 (default off);
- software emulation (`useEmulation`, a slow fallback for boxes without KVM) is refused, in the file
  before install and in the live KubeVirt object after it;
- removal must leave no CRD, webhook or API service of KubeVirt or CDI behind, or it reports failed.
`NoopExtension` (the noop executor: Mac demos, tests) records the plan and never touches a cluster.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..executors import ExecResult

Runner = Callable[..., subprocess.CompletedProcess]
FILES = ("kubevirt-operator.yaml", "kubevirt-cr.yaml", "cdi-operator.yaml", "cdi-cr.yaml")
LEFTOVER_KINDS = "crd,validatingwebhookconfigurations,mutatingwebhookconfigurations,apiservices"
LEFTOVER_MARKS = ("kubevirt.io", "cdi.kubevirt.io", "virt-", "cdi-")
EMULATION = "useEmulation"
UNPINNED = ("The machines layer still names its container images by tag, not by digest, so it will not be applied "
            "until the images are pinned (LT-MACH-2).")


@dataclass(frozen=True)
class Layer:
    """What the image carries: a directory with extension.json and the manifests it names."""
    root: Path
    files: dict[str, str]  # file name -> sha256

    @classmethod
    def load(cls, root: Path) -> tuple[Layer | None, str]:
        """(layer, "") when the layer is whole and honest, else (None, the plain reason)."""
        try:
            meta = json.loads((root / "extension.json").read_text())
            files = meta["files"]
        except (OSError, ValueError, KeyError, TypeError):
            return None, "The machines layer is not part of this image."
        if not isinstance(files, dict) or set(files) != set(FILES):
            return None, "The machines layer lists the wrong files."
        for name in FILES:
            try:
                data = (root / name).read_bytes()
            except OSError:
                return None, f"The machines layer is missing {name}."
            if hashlib.sha256(data).hexdigest() != files[name]:
                return None, f"{name} does not match its pinned checksum, so it will not be applied."
            if EMULATION.encode() in data and name.endswith("-cr.yaml"):
                return None, "The machines layer asks for software emulation, which OneMind refuses."
        return cls(root, dict(files)), ""


class ExtensionRuntime(Protocol):
    def available(self) -> tuple[bool, str]: ...

    def install(self) -> ExecResult: ...

    def remove(self) -> ExecResult: ...


class NoopExtension:
    name = "noop"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def install(self) -> ExecResult:
        return ExecResult("succeeded", "noop: machines extension not installed", [
            {"would": "apply KubeVirt and CDI, wait until both are ready, refuse software emulation"}])

    def remove(self) -> ExecResult:
        return ExecResult("succeeded", "noop: machines extension not removed", [
            {"would": "delete CDI and KubeVirt, then check no CRD or webhook is left"}])


class KubectlExtension:
    name = "kubernetes"

    def __init__(self, root: Path, kubectl: str = "kubectl", runner: Runner = subprocess.run, timeout_s: float = 1200,
                 allow_tag_images: bool = False):
        self.root, self.kubectl, self.runner, self.timeout_s = Path(root), kubectl, runner, timeout_s
        self.allow_tag_images = allow_tag_images

    def available(self) -> tuple[bool, str]:
        layer, why = Layer.load(self.root)
        if layer is not None and not self.allow_tag_images:
            return False, UNPINNED
        return layer is not None, why

    def _run(self, steps: list[dict], *argv: str) -> tuple[ExecResult | None, str]:
        """Run kubectl; (the ExecResult to return when it went wrong, stdout) otherwise (None, stdout)."""
        cmd = [self.kubectl, *argv]
        step: dict = {"argv": cmd}
        steps.append(step)
        try:
            cp = self.runner(cmd, capture_output=True, text=True, timeout=self.timeout_s, check=False)
        except FileNotFoundError:
            step["error"] = "kubectl not found"
            return ExecResult("failed", f"{self.kubectl} not found on PATH", steps), ""
        except subprocess.TimeoutExpired:
            step["error"] = f"timeout after {self.timeout_s}s"
            return ExecResult("outcome_unknown", f"kubectl timed out after {self.timeout_s}s", steps), ""
        step["returncode"] = cp.returncode
        step["stderr"] = (cp.stderr or "")[-400:]
        if cp.returncode != 0:
            return ExecResult("failed", f"kubectl exited {cp.returncode}", steps), ""
        return None, cp.stdout or ""

    def install(self) -> ExecResult:
        layer, why = Layer.load(self.root)
        if layer is None:  # the file is re-read here: it may have changed since the owner asked
            return ExecResult("failed", why, [])
        if not self.allow_tag_images:  # privileged images by mutable tag: never without the explicit switch
            return ExecResult("failed", UNPINNED, [])
        steps: list[dict] = []
        f = lambda n: str(layer.root / n)  # noqa: E731
        wait = ("--for=condition=Available", "--timeout=15m")
        for argv in (
            ("apply", "-f", f("kubevirt-operator.yaml")),
            ("-n", "kubevirt", "wait", "deploy/virt-operator", *wait),
            ("apply", "-f", f("kubevirt-cr.yaml")),
            ("apply", "-f", f("cdi-operator.yaml")),
            ("-n", "cdi", "wait", "deploy/cdi-operator", *wait),
            ("apply", "-f", f("cdi-cr.yaml")),
            ("-n", "kubevirt", "wait", "kubevirt/kubevirt", "--for=condition=Available", "--timeout=20m"),
            ("wait", "cdi/cdi", "--for=condition=Available", "--timeout=20m"),
        ):
            bad, _ = self._run(steps, *argv)
            if bad:
                return bad
        bad, out = self._run(steps, "-n", "kubevirt", "get", "kubevirt", "kubevirt", "-o",
                             "jsonpath={.spec.configuration.developerConfiguration.useEmulation}")
        if bad:
            return bad
        if out.strip().lower() == "true":
            return ExecResult("failed", "KubeVirt is set to software emulation, which OneMind refuses: machines stay off.", steps)
        return ExecResult("succeeded", "machines extension installed and ready", steps)

    def remove(self) -> ExecResult:
        layer, why = Layer.load(self.root)
        if layer is None:
            return ExecResult("failed", why, [])
        steps: list[dict] = []
        f = lambda n: str(layer.root / n)  # noqa: E731
        for argv in (
            ("delete", "-f", f("cdi-cr.yaml"), "--ignore-not-found", "--wait", "--timeout=10m"),
            ("delete", "-f", f("cdi-operator.yaml"), "--ignore-not-found", "--wait", "--timeout=10m"),
            ("-n", "kubevirt", "delete", "kubevirt", "kubevirt", "--ignore-not-found", "--wait", "--timeout=10m"),
            ("delete", "-f", f("kubevirt-operator.yaml"), "--ignore-not-found", "--wait", "--timeout=10m"),
        ):
            bad, _ = self._run(steps, *argv)
            if bad:
                return bad
        bad, out = self._run(steps, "get", LEFTOVER_KINDS, "-o", "name")
        if bad:
            return bad
        left = sorted(n for n in out.split() if any(m in n for m in LEFTOVER_MARKS))
        if left:
            steps[-1]["leftovers"] = left
            return ExecResult("failed", "Removal left cluster objects behind: " + ", ".join(left[:8]), steps)
        return ExecResult("succeeded", "machines extension removed, nothing left behind", steps)
