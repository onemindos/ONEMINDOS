---
pr: 902
branch: claude/fnd-jetstream-followups
---
Hub JetStream follow-ups (#601): the hub's JetStream cap is now a share of the data disk instead of a fixed 4 GiB, and JetStream without a cap is refused everywhere (onemind-firstboot, the gateway, and the hub NATS start check, which reads nats.conf and its includes the way nats-server does, so `jetstream: on`, upper-case keys or a limit outside the block cannot slip past it). Every leaf renders max_memory_store 0 and a leaf config without it is refused. The outbox retention, discard policy, size and age are pinned by tests. The gateway creates the core streams and the asset-state and layer-meta KV buckets from the subject tree, file storage only and within half of the cap, and creates them again after NATS comes back.
