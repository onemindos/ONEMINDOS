---
pr: pending
branch: claude/perf-harness-image-layout
---
The hub performance harness now runs unmodified on the shipped image: it detects the image layout (tokens file under the data partition, onemindd in /usr/bin, admin kubeconfig in /run/k3s, no metrics-server wait, the image's Headscale unit, and the hub NATS key for simulated nodes), and has a new plan command that takes devices, events per second, duration and a p95 target, with a capabilities read per device. The update engine also clears a stale bad-releases entry once that same version is running and committed.
