---
pr: pending
branch: claude/159-agent-kill-switch
status_rows:
  - CORE-SEC-6 | in-review | agent kill switch built; signed audit checkpoints still to do
---
Agent kill switch (CORE-SEC-6, #159): one owner switch, GET and PUT /v1/agents/kill-switch, that makes the gateway refuse every AI agent principal (static agent token, app agent issued at install, identity-issued agent token) with 403 and reason agents_stopped, and refuses approving anything an agent asked for while it is on. Only the owner can turn it on or off, every change is an audited agents.stopped or agents.resumed event, refused agent calls are audited at most once a minute, and the state lives in the database so it survives a restart. Reachable from Settings, Agents in the dashboard (owner sees the button, everyone sees the state) and from `onemind agents status`, `stop` and `resume`.
