---
pr: 1000
branch: claude/d12-market-unblock
---
Market unblock (#147, UMB-P10): pin Copyparty 1.20.27, Home Assistant 2026.11.2 and Audiobookshelf 2.38.0 by digest and commit the CI gate's scans for amd64 and arm64. Copyparty passes vulnerability, malware and smoke checks and moves to community. Home Assistant and Audiobookshelf each still have four fixable critical findings and stay blocked. The CI workflow generates the Go SDK before building the validator and schedules image scans independently of committed-scan validation.
