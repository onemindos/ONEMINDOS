---
pr: pending
branch: claude/perf-audit-growth-boot-ready
status_rows:
  - CORE-NET-14 | in-progress | lab findings: audit log rotation and retention, boot-ready probe fix
---
Audit log growth is bounded: the gateway can compress the active audit file into a gzip segment at a size you set (ONEMIND_AUDIT_MAX_BYTES, off by default because the backup unit copies only the active file; a damaged segment is reported by verify as tampering) and can keep only the newest N segments (ONEMIND_AUDIT_KEEP_SEGMENTS), recording the cut in an audit.pruned event inside the hash chain. List, get and verify read across segments, and verify reports history that was deleted without such an event. The boot-ready probe now stamps each milestone when its own check passes, starts early instead of after network-online, and records when systemd activated each boot unit; the gateway kubeconfig poll drops from 10 s to 2 s.
