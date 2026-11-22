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
from .spec import NAMESPACE, MachineCreateParams, render_clone, render_create, render_snapshot, snapshot_name

Runner = Callable[..., subprocess.CompletedProcess]


class MachineRuntime(Protocol):
    def create(self, p: MachineCreateParams) -> ExecResult: ...

    def set_running(self, name: str, running: bool) -> ExecResult: ...

    def delete(self, name: str) -> ExecResult: ...

    def restart(self, name: str) -> ExecResult: ...

    def force_stop(self, name: str) -> ExecResult: ...

    def snapshot(self, name: str, snap: str) -> tuple[ExecResult, list[str]]:
        """The result and KubeVirt's `status.indications` of the snapshot (how the freeze went)."""
        ...

    def clone(self, source: str, target: str) -> ExecResult: ...


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


    def restart(self, name: str) -> ExecResult:
        return ExecResult("succeeded", f"noop: machine {name} not restarted", [{"would": f"restart VirtualMachineInstance {name}"}])

    def force_stop(self, name: str) -> ExecResult:
        return ExecResult("succeeded", f"noop: machine {name} not forced off",
                          [{"would": f"set VirtualMachine {name} runStrategy Halted and delete its instance with no grace period"}])

    def snapshot(self, name: str, snap: str) -> tuple[ExecResult, list[str]]:
        return ExecResult("succeeded", f"noop: machine {name} not snapshotted",
                          [{"would": f"create VirtualMachineSnapshot {snapshot_name(name, snap)}"}]), ["GuestAgent"]

    def clone(self, source: str, target: str) -> ExecResult:
        return ExecResult("succeeded", f"noop: machine {source} not cloned",
                          [{"would": f"create VirtualMachineClone {source} -> {target}, stopped, with a deny-all NetworkPolicy"}])


class KubectlRuntime:
    name = "kubernetes"

    def __init__(self, kubectl: str = "kubectl", runner: Runner = subprocess.run, timeout_s: float = 300):
        self.kubectl, self.runner, self.timeout_s = kubectl, runner, timeout_s

    def _run(self, steps: list[dict], argv: list[str], stdin: str | None = None, *, keep_stdout: bool = False) -> ExecResult | None:
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
        if keep_stdout:
            step["stdout"] = (cp.stdout or "")[-400:]
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
        bad = (self._run(steps, [k, "delete", "virtualmachinesnapshot", "-l", f"onemind.io/machine={name}", "-n", NAMESPACE,
                                 "--ignore-not-found", "--wait=false"])
               or self._run(steps, [k, "delete", "virtualmachine", name, "-n", NAMESPACE, "--ignore-not-found", "--wait=false"])
               or self._run(steps, [k, "delete", "networkpolicy", f"{name}-deny", "-n", NAMESPACE, "--ignore-not-found"]))
        return bad or ExecResult("succeeded", f"machine {name} deleted", steps)

    def restart(self, name: str) -> ExecResult:
        steps: list[dict] = []
        # The VM keeps runStrategy Always, so deleting its running instance (a graceful shutdown the guest
        # sees as a power-button press) makes KubeVirt start a fresh one. The disk is untouched.
        bad = self._run(steps, [self.kubectl, "delete", "virtualmachineinstance", name, "-n", NAMESPACE, "--wait=false"])
        return bad or ExecResult("succeeded", f"machine {name} restarting", steps)

    def force_stop(self, name: str) -> ExecResult:
        steps: list[dict] = []
        k = self.kubectl
        # Halted first, or KubeVirt would start the instance again the moment it is killed.
        patch = json.dumps({"spec": {"runStrategy": "Halted"}})
        bad = (self._run(steps, [k, "patch", "virtualmachine", name, "-n", NAMESPACE, "--type", "merge", "-p", patch])
               or self._run(steps, [k, "delete", "virtualmachineinstance", name, "-n", NAMESPACE, "--grace-period=0",
                                    "--force", "--ignore-not-found", "--wait=false"]))
        return bad or ExecResult("succeeded", f"machine {name} forced off", steps)

    def snapshot(self, name: str, snap: str) -> tuple[ExecResult, list[str]]:
        steps: list[dict] = []
        k, obj = self.kubectl, f"virtualmachinesnapshot/{snapshot_name(name, snap)}"
        # `create`, not `apply`: an existing object fails with AlreadyExists, so a restore point that was
        # never taken of this machine can never be reported as taken (wait would return at once).
        bad = (self._run(steps, [k, "create", "-f", "-"], render_snapshot(name, snap))
               or self._run(steps, [k, "wait", "--for=jsonpath={.status.readyToUse}=true", obj, "-n", NAMESPACE, "--timeout=240s"]))
        if bad:
            return bad, []
        bad = self._run(steps, [k, "get", obj, "-n", NAMESPACE, "-o", "jsonpath={.status.indications}"], keep_stdout=True)
        if bad:  # the copy exists; only how it was frozen is unknown, so say best effort rather than fail
            return ExecResult("succeeded", f"snapshot {snap} of {name} taken", steps), []
        raw = steps[-1].get("stdout", "")
        try:
            found = json.loads(raw) if raw.strip() else []
        except ValueError:
            found = []
        return ExecResult("succeeded", f"snapshot {snap} of {name} taken", steps), [str(i) for i in found] if isinstance(found, list) else []

    def clone(self, source: str, target: str) -> ExecResult:
        steps: list[dict] = []
        k = self.kubectl
        label = json.dumps({"metadata": {"labels": {"onemind.io/machine": target}},
                            "spec": {"runStrategy": "Halted",
                                     "template": {"metadata": {"labels": {"onemind.io/machine": target}}}}})
        # UNVERIFIED on real KVM (LT-MACH-2): the clone is relabelled and held Halted before anything can
        # start it, so it is never outside its deny-all policy, and it never starts without a start approval.
        bad = (self._run(steps, [k, "apply", "--server-side", "--field-manager=onemind-gateway", "--force-conflicts", "-f", "-"],
                         render_clone(source, target))
               or self._run(steps, [k, "wait", "--for=jsonpath={.status.phase}=Succeeded", f"virtualmachineclone/{target}-clone",
                                    "-n", NAMESPACE, "--timeout=900s"])
               or self._run(steps, [k, "patch", "virtualmachine", target, "-n", NAMESPACE, "--type", "merge", "-p", label]))
        return bad or ExecResult("succeeded", f"machine {source} cloned to {target}, stopped", steps)
