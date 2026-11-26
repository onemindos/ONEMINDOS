---
pr: pending
branch: claude/perm-ui-5-remember
---
An approval card for an agent's request now offers Approve and remember when the owner has a passkey. The sheet sets how long the rule lasts (30 days preselected, 90, 180 or Forever, which adds a line that it never ends by itself and is reviewed every 90 days), End if unused for 14 days (on), a daily limit, how you are told about uses, and which of the request's details must stay the same. Show the rule asks the gateway to build it: the summary shown is the gateway's own, written from the rule your passkey will sign, and any change to the choices needs the rule shown again. The passkey then approves the request and stores that exact rule. When the gateway refuses (the requester is on Locked or Always ask, the request is physical, tainted, above write or a hard-floor item, or the rule needs a proven key it cannot check yet), the sheet says why in plain words.
