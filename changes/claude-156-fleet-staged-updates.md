---
pr: pending
branch: claude/156-fleet-staged-updates
status_rows:
  - CORE-UPDATE-9 | in-review | gateway release service (fleet view, staged rollout, pause and owner-approved resume); node-side update.apply consumer still open
---
Fleet-staged OS updates in the gateway (Z-20). GET /v1/os/fleet shows the version and update state of every machine and how many run each version. An owner (or an agent, asking) requests os.rollout.start with a version and cumulative stages such as 10, 50, 100 percent; only an owner approves it. The gateway then offers the version stage by stage as a signed onemind.job/v1 update.apply job on onemind.node.<id>.job.update.apply, reads each machine's progress from its heartbeat, pauses when more machines roll back, error or stay silent than allowed, and continues only after an owner approves os.rollout.resume. GET /v1/os/rollouts follows a rollout and the owner may cancel one. A five-machine test rolls out, pauses on an injected rollback and resumes.
