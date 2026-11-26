---
pr: pending
branch: claude/gw-perm-13-auto-notices
---
A request an owner's standing approval accepted now tells the owners (new notice approval.auto): an each rule pushes a notice for every use, a digest rule (the default) puts one in the inbox and adds it to a daily list (approval.auto.digest, once a day after 18:00 UTC, with the number of rules in force and how many have no end date), and a silent read-only rule says nothing. Every such notice carries a Revoke rule action (kind revoke with the rule id) and a link to the rule, never an approve action, and apps still cannot post either kind. An each rule pauses (suspended, reason push_failed or no_push_target, audited as approval.policy.paused) when its notice cannot be pushed, and one passkey tap re-confirms it. Gateway permissions design PR 13, fix 10.
