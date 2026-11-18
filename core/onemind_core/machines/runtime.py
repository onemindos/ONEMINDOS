# SPDX-License-Identifier: Apache-2.0
"""The part of the gateway that changes the outside world for machines, only after approval.

`NoopRuntime` (the noop executor: Mac demos, tests) records what it would do. `KubectlRuntime` runs
kubectl against the KubeVirt objects of spec.py. The runtime is the small `MachineRuntime`
interface of docs/umbrel2/machines.md §4.1, so a different runtime would not change the contract.

Outcome rules follow executors.py: exit 0 is succeeded, a non-zero exit or a missing kubectl is
failed, a timeout is outcome_unknown (we cannot know what was applied; a person decides next).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Protocol

from ..executors import ExecResult
from .spec import NAMESPACE, MachineCreateParams, render_create

Runner = Callable[..., subprocess.CompletedProcess]


class MachineRuntime(Protocol):
    def create(self, p: MachineCreateParams) -> ExecResult: ...

    def set_running(self, name: str, running: bool) -> ExecResult: ...

    def delete(self, name: str) -> ExecResult: ...


class NoopRuntime:
    name = "noop"

    def create(self, p: MachineCreateParams) -> ExecResult:
        return ExecResult("succeeded", f"noop: machine {p.name} not created", [
            {"would": f"apply namespace {NAMESPACE}, NetworkPolicy {p.name}-deny and VirtualMachine {p.name}",
             "ram_mb": p.ram_mb, "cpus": p.cpus, "disk_gb": p.disk_gb}])

    def set_running(self, name: str, running: bool) -> ExecResult:
        return ExecResult("succeeded", f"noop: machine {name} not changed",
                          [{"would": f"set VirtualMachine {name} runStrategy {'Always' if running else 'Halted'}"}])

    def delete(self, name: str) -> ExecResult:
        return ExecResult("succeeded", f"noop: machine {name} not deleted",
                          [{"would": f"delete VirtualMachine {name} (and its disk) and NetworkPolicy {name}-deny"}])


class KubectlRuntime:
    name = "kubernetes"

    def __init__(self, kubectl: str = "kubectl", runner: Runner = subprocess.run, timeout_s: float = 300):
        self.kubectl, self.runner, self.timeout_s = kubectl, runner, timeout_s

    def _run(self, steps: list[dict], argv: list[str], stdin: str | None = None) -> ExecResult | None:
        """Run one command; the ExecResult to return when it went wrong, None when it succeeded."""
        step = {"argv": argv}
        steps.append(step)
        try:
            cp = self.runner(argv, input=stdin, capture_output=True, text=True, timeout=self.timeout_s, check=False)
        except FileNotFoundError:
            step["error"] = "kubectl not found"
            return ExecResult("failed", f"{self.kubectl} not found on PATH", steps)
        except subprocess.TimeoutExpired:
            step["error"] = f"timeout after {self.timeout_s}s"
            return ExecResult("outcome_unknown", f"kubectl timed out after {self.timeout_s}s", steps)
        step["returncode"] = cp.returncode
        step["stderr"] = (cp.stderr or "")[-400:]
        if cp.returncode != 0:
            return ExecResult("failed", f"kubectl exited {cp.returncode}", steps)
        return None

    def create(self, p: MachineCreateParams) -> ExecResult:
        steps: list[dict] = []
        k = self.kubectl
        bad = self._run(steps, [k, "apply", "--server-side", "--field-manager=onemind-gateway", "--force-conflicts", "-f", "-"],
                        render_create(p))
        return bad or ExecResult("succeeded", f"machine {p.name} created, stopped", steps)

    def set_running(self, name: str, running: bool) -> ExecResult:
        steps: list[dict] = []
        patch = json.dumps({"spec": {"runStrategy": "Always" if running else "Halted"}})
        bad = self._run(steps, [self.kubectl, "patch", "virtualmachine", name, "-n", NAMESPACE, "--type", "merge", "-p", patch])
        return bad or ExecResult("succeeded", f"machine {name} {'started' if running else 'stopped'}", steps)

    def delete(self, name: str) -> ExecResult:
        steps: list[dict] = []
        k = self.kubectl
        # The disk is a DataVolume the VirtualMachine owns: deleting the VM deletes it.
        bad = (self._run(steps, [k, "delete", "virtualmachine", name, "-n", NAMESPACE, "--ignore-not-found", "--wait=false"])
               or self._run(steps, [k, "delete", "networkpolicy", f"{name}-deny", "-n", NAMESPACE, "--ignore-not-found"]))
        return bad or ExecResult("succeeded", f"machine {name} deleted", steps)
