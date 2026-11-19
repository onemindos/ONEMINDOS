---
pr: pending
branch: claude/171-capability-labels
status_rows:
  - CORE-FABRIC-4 | in-review | labels from heartbeats, placement from spec.requires, GET /v1/apps/{id}/placement
---
The Market can now say where an app would run. Each machine's facts from onemindd (arch, board, CPU level, GPU, KVM, memory, role) become capability labels such as onemind.io/gpu=nvidia; a fact a machine does not report gives no label. The new GET /v1/apps/{id}/placement (scope nodes:read, since it names the machines; a child is refused as on /v1/nodes) checks the app's spec.archs and spec.requires (GPU, minimum memory, CPU level, reusing the NMD-09 CPU check) against every machine and answers here, on another machine, nowhere or unknown, with each machine's reasons. Installing or updating an app that no machine can run, such as one that needs a GPU when no machine has one, is refused with reason no_node_fits.
