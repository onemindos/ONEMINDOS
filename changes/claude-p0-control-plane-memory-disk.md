---
pr: pending
branch: claude/p0-control-plane-memory-disk
---
The image now protects its control plane from memory and disk pressure. Compressed RAM swap (zram, zstd, half the RAM up to 4 GiB) is configured, k3s, NATS, the gateway and onemindd get OOMScoreAdjust=-900 and a MemoryMin so the kernel OOM killer picks a big app instead, the kubelet reserves 1 GiB of memory for the system and evicts pods before the box runs out, the journal is capped at 500 MB, and /data is mounted noatime. A new pre-registered QEMU test (CRITERIA-MEMORY.md, make memory-test) runs a 6 GiB memory hog on an 8 GiB hub VM and requires every gateway health probe to answer 200; its first run is CI or the lab, not this change.
