---
pr: 1125
branch: claude/p07-journal
---
Adds the whole-system log viewer (P-07). `GET /v1/system/journal?unit=&priority=&boot=&tail=&follow=` lets the owner read the box's systemd journal (kernel, SSH, any unit, not only the registry services), through a new `GET /v1/journal` route on the host service that validates every value against an allow-list before it reaches journalctl. The gateway redacts every line (the app-log filter plus WireGuard, age and NATS keys, SSH fingerprints and MAC addresses), caps a read at 2000 lines and 1 MiB, allows 30 reads a minute and 3 open follow streams per owner, and audits each read. Troubleshoot gets a Logs tab with unit, level, boot and line-count filters and a follow mode, and the CLI gets `onemind logs [--unit] [--priority] [--boot -1] [--tail] [--follow]`, sharing the stream code of `onemind services logs`. Read only, so nothing waits for an approval.
