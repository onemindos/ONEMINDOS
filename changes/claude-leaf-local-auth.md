---
pr: pending
branch: claude/leaf-local-auth
---
Local sign-in on every joined machine's NATS leaf (G1): the leaf no longer has a passwordless user. onemindd, the owner's `onemind fabric outbox` tool and a sensor's writers each get their own nkey and exact publish and subscribe lists, `leaf.conf` carries only public keys, and `onemind fabric join` makes the seeds (root-only, kept across a re-join) and points onemindd at its own. The image's leaf check now fails a leaf with no nkey users or with a no_auth_user. The dev compose NATS moves to the pinned 2.15.3, and check-pins fails if a dev NATS image differs from the image's version (G7).
