---
pr: 441
branch: claude/429-live-usage
---
UMB-P11 Live usage: a new read-only gateway route, GET /v1/usage (scope monitoring:read, like app metrics), returns CPU, memory, disk and temperature for each machine from the heartbeats, and CPU, memory and volume disk for each installed app from the app runtime (metrics-server plus the kubelet stats summary, read with kubectl get --raw). A machine with an old heartbeat is marked stale with its age, the per-app block says when it was read and turns stale after 30 s or when the runtime stops answering, a figure nobody reported is null rather than 0, and apps hidden from the reader by sharing are left out. The desktop gets a Live usage window opened from a gauge button in the menu bar (also in Launchpad and the Console view), refreshing every 5 s, built on the generated SDK types, and the CLI gets onemind status --usage. SDKs regenerated.
