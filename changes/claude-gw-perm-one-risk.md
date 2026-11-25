---
pr: pending
branch: claude/gw-perm-one-risk
---
Gateway permissions PR 1, one effective risk. A standing approval is now judged on each request's actual risk class: the higher of the risk table (with its parameter upgrades) and the class stored on the request when it was filed, so a feature that raises a request to destructive is never auto-approved. A request with no valid risk class is refused. Feature types registered at runtime now feed the one risk table and must agree with it. Removing an app is now a sensitive action, so no standing rule can cover it.
