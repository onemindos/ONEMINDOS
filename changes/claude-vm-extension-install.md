---
pr: pending
branch: claude/vm-extension-install
status_rows:
  - UMB-MACH-2 | in-review | KubeVirt and CDI pinned in an optional image layer; Turn on is an owner-approved action; real-KVM result of LT-MACH-2 still gates a release
---
Machines can now be turned on. The image carries an optional layer with the pinned KubeVirt v1.9.1 and CDI v1.66.1 manifests (sha256 in os/versions.lock.yaml, both licences re-read as Apache-2.0 at those tags). The Turn on button on the Machines page, or an agent asking, files a machines.enable action; only an owner approves it. On approval the gateway re-checks each manifest hash, applies KubeVirt and CDI, waits until both are ready, refuses software emulation, and only then reports machines as on. A machines.disable action removes them and fails if any CRD or webhook is left. Pi, small and no-KVM boxes are still refused with plain reasons, and the noop executor never touches a cluster.
