---
pr: pending
branch: claude/fu-1133-inputs-forget
---
Follow-ups from the Opus reviews of stored taint and exposed agents: removing a plugin, or a failed plugin install, now clears what the owner declared about that plugin's outside inputs (as it already did for agent apps), so a plugin installed later under the same id starts fail-closed again. The forget and the owner set now take one writer lock, so a set landing between the cache pop and the row delete can no longer leave the cache and database apart. The forget test now drives a real app.remove through the action queue and checks the row is gone, and the audit test asserts the exact proof method.
