---
pr: 1006
branch: claude/blk-machine-id
---
Every machine built from one image now gets its own identity, so a fleet of more than one node can join a hub (#943). The image assembly empties /etc/machine-id and turns /var/lib/dbus/machine-id into the upstream symlink to it, so systemd no longer seeds every machine's transient id from the build container's D-Bus copy. `onemind fabric join` and `onemind device join` now ask to join with ONEMIND_NODE_ID or first boot's own random node_id (the same id onemindd reports), and fall back to the machine-id hash only on a machine that never ran first boot.
