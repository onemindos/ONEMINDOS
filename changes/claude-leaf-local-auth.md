---
pr: 1126
branch: claude/leaf-local-auth
---
Local sign-in on every joined machine's NATS leaf (G1): the leaf no longer has a passwordless user. onemindd, the owner's `onemind fabric outbox` tool and a sensor's writers each get their own nkey and exact publish and subscribe lists, `leaf.conf` carries only public keys, and `onemind fabric join` makes the seeds (root-only, kept across a re-join) and points onemindd at its own. The image's leaf check now fails a leaf with no nkey users or with a no_auth_user. The dev compose NATS moves to the pinned 2.15.3, and check-pins fails if a dev NATS image differs from the image's version (G7).

An edge that joined before this change takes the update that ships it: the new `onemind-leaf-local.service` runs `onemind fabric upgrade-local` at every boot, before the health gate and onemindd, and does nothing unless the leaf has no local programs yet. Then it makes the onemindd and cli seeds, renders `leaf.conf` again, points onemindd at its seed and restarts the leaf and onemindd. Without it the gate's leaf check would fail the trial boot, roll back and put the release on the bad-releases list.

Rollback note: if the trial slot fails for another reason after the upgrade has run, `/data` already holds the signed-in `leaf.conf` and the old slot boots against it. The old onemindd reads `ONEMIND_NATS_NKEY_SEED`, so it signs in and heartbeats still reach the hub, but it does not know `ONEMIND_NATS_INBOX_PREFIX`, so its `_INBOX.>` replies are refused. Durable-outbox JetStream requests and the old `onemind fabric outbox` CLI fail until the next good release (the upgrade is then a no-op). The node stays reachable and is never open.
