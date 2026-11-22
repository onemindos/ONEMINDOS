---
pr: pending
branch: claude/vm-lifecycle-snapshot-clone
---
Machines gain restart, force off, snapshot and clone (#281, MACH-01). Each is a request that waits for an owner, and an agent may only ask. A snapshot of a running machine asks the guest agent to pause the disk first and is shown to the owner as best effort when that fails (QuiesceFailed); a clone needs a stopped source, counts against the memory and core quota, and starts stopped with no network. Deleting a machine now also removes its snapshots and still needs its name typed. The Machines screen gets the buttons and a snapshot list, and the onemind CLI gets restart, force-stop, snapshot, snapshots and clone. Written against KubeVirt snapshot and clone objects and not yet run on real KVM hardware (LT-MACH-2).
