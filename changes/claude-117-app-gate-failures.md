---
pr: pending
branch: claude/117-app-gate-failures
---
App gate failures, first slice (Refs #117): Gitea moves to 28.4.0-rootless and Node-RED to 5.0.10, the first upstream releases whose images carry no CRITICAL with a fix in a local Trivy check (no gate run yet, so both go from blocked to community and CI computes the real tier); Mosquitto goes to verified and OpenClaw to community because their committed gate scans no longer justify blocked; a new test keeps every committed tier in line with its committed scan.json. Every other blocked app was re-checked against current upstream pins and stays blocked with its reason in the app README.
