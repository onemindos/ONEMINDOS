---
pr: 1200
branch: claude/gw-perm-7-principal-id
---
Standing approvals now bind each agent and plugin they name to a permanent principal id (prn_ followed by a ULID) and the person who owns it, instead of the display id alone. Revoking a token, cancelling the agent, disabling its owner, removing or reinstalling its app ends that identity, so its rules stop and a later token or app with the same name never inherits them. An app whose agent id a personal agent token or the tokens file already holds is refused at install (409 agent_id_taken). A rule for an agent nobody holds yet is refused (422 unknown_principal); rules made before the upgrade bind once, at start, to whoever holds the id then. GET /v1/agents/id shows principal_uid and every rule shows what it is bound to. New table principals_registry. Gateway permissions design PR 7, gap 19, D-027.
