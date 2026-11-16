# SPDX-License-Identifier: Apache-2.0
"""Which boxes may run virtual machines (docs/umbrel2/machines.md §4.7 preflight, #281 scope 2).

Machines are off by default and install only on an x86 hub that has KVM and about 16 GB of RAM.
Anywhere else, enabling them is refused with a reason a person can read: never on a Pi, never on a
board that is itself a VM, never on a small box. Pure functions over a node's heartbeat
(contract section 2); nothing here touches the cluster.

`kvm` is an optional heartbeat field: true when /dev/kvm exists on the node. A node that does not
report it is treated as having no KVM, so a missing field refuses rather than guesses.
"""

from __future__ import annotations

from dataclasses import dataclass

# A 16 GiB box reports MemTotal of roughly 15,300 to 15,900 MiB; an 8 GiB box about 7,800 and a
# 12 GiB box about 11,600 (firmware and the GPU take some). 15,000 sits between the last two and
# the first, so "16 GB" means a real 16 GiB machine. UNVERIFIED on the Beelink: LT-MACH-2 reads it.
MIN_MEMORY_MB = 15_000
# Boards that can host machines: x86 hardware. `vm` and `vm-do` are boxes that are already a VM
# (nested virtualisation is not supported); rpi5 and jetson-orin are the small and ARM boards.
X86_BOARDS = frozenset({"x86_64-efi"})


@dataclass(frozen=True)
class Reason:
    code: str
    message: str

    def to_json(self) -> dict:
        return {"code": self.code, "message": self.message}


def refusals(node: dict) -> list[Reason]:
    """Why this node cannot run machines; empty when it can."""
    out: list[Reason] = []
    board, arch = node.get("board"), node.get("arch")
    if node.get("role") != "hub":
        out.append(Reason("not_a_hub", "Machines run on the hub, and this node is not the hub."))
    if board in ("rpi5", "jetson-orin") or arch == "arm64":
        out.append(Reason("not_x86", "Machines need an x86 PC. A Raspberry Pi or another ARM board is too small and the wrong kind of CPU."))
    elif board in ("vm", "vm-do"):
        out.append(Reason("already_a_vm", "This box is itself a virtual machine, and OneMind does not nest virtual machines."))
    elif board not in X86_BOARDS or arch != "amd64":
        out.append(Reason("not_x86", "Machines need an x86 PC, and this box did not report one."))
    mem = node.get("mem_total_mb")
    if not isinstance(mem, int | float) or isinstance(mem, bool) or mem < MIN_MEMORY_MB:
        have = f"{mem / 1024:.0f} GB" if isinstance(mem, int | float) and not isinstance(mem, bool) else "an unknown amount"
        out.append(Reason("memory_below_16gb", f"Machines need at least 16 GB of memory, and this box has {have}."))
    if node.get("kvm") is not True:
        out.append(Reason("no_kvm", "This box's processor features for virtual machines (KVM) are not available or not switched on in the BIOS."))
    k3s = node.get("k3s")
    if not isinstance(k3s, dict) or not k3s.get("ready"):
        out.append(Reason("cluster_not_ready", "The cluster on this box is not ready yet."))
    return out


def describe(node: dict) -> dict:
    """One node's line in GET /v1/machines/capabilities. Facts the owner already sees in /v1/nodes."""
    why = refusals(node)
    return {
        "node_id": node.get("node_id"), "hostname": node.get("hostname"), "role": node.get("role"),
        "board": node.get("board"), "arch": node.get("arch"), "mem_total_mb": node.get("mem_total_mb"),
        "kvm": node.get("kvm") is True, "status": node.get("status"),
        "eligible": not why, "reasons": [r.to_json() for r in why],
    }
