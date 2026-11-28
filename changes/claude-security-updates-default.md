---
pr: 1342
branch: claude/security-updates-default
---
REL-02 (#154): OS security updates now ask first by default, and installing them automatically is the owner's choice. Z-02 was answered by the founder on 2026-11-28: not automatic by default. The image and the updater default to policy notify on every channel: the box finds security updates and tells the owner, and nothing installs or reboots until the owner approves. The owner can turn on automatic installs inside a chosen maintenance window (A/B install with health-gated rollback), or turn checks off, from Settings > Updates or `onemind update settings show/set`. Both go through `PUT /v1/os/settings`, which only files an `os.update.settings` action: only an owner files it, a standing approval never covers it, approving it always needs the owner's passkey (D-027, D-028), and the host service stores the choice under /data while the image's update.conf stays read-only. Each machine reports its policy, its window and who set them.
