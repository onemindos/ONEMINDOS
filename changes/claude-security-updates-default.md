---
pr: 1342
branch: claude/security-updates-default
---
REL-02 (#154): security updates stay on by default (the security channel installs by itself inside the maintenance window, with the A/B health-gated rollback), and the owner can now opt out or move the window. The choice is stored under /data (the image's update.conf stays read-only), the updater and the heartbeat read it on every cycle, and each machine reports its policy, window and who set them. Settings > Updates and `onemind update settings show/set` show and request a change through `PUT /v1/os/settings`, which only files an `os.update.settings` action: only an owner files it, it runs through the host service after approval, and turning automatic updates off or moving the window needs the owner's passkey (D-027, D-028).
