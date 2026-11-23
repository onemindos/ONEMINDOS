---
pr: pending
branch: claude/ab2-backup-units-wiring
---
Built-in apps' data now reaches the off-site backup on a real box (#616). Before each box run the gateway writes the built-ins' tables-only export (builtin-units.tar) into /data/onemind/gateway/backup-export, and onemind-firstboot adds that folder and the files root (/data/onemind/files) to the backup agent's system unit, also on boxes set up earlier (their other agent.json settings are kept). GET /v1/backups/status shows a built-in as in_snapshot only once a run with a successful system snapshot wrote its export first and every folder it uses is one the agent copies; a failed export fails the built-ins' units of that run.
