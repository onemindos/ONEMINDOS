---
pr: 902
branch: claude/fnd-jetstream-followups
---
Hub JetStream follow-ups (#601): the hub's JetStream cap is now a share of the data disk instead of a fixed 4 GiB, and JetStream without a cap is refused everywhere (onemind-firstboot, the hub NATS start check, the gateway). Every leaf renders max_memory_store 0 and a leaf config without it is refused. The outbox retention, discard policy, size and age are pinned by tests. The gateway creates the core streams and the asset-state and layer-meta KV buckets from the subject tree, file storage only and within half of the cap, and creates them again after NATS comes back.
