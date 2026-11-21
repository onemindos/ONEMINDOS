---
pr: pending
branch: claude/167-hermes-principal
---
AI agents such as Hermes are now gateway principals with their own limits. The owner can set a daily request budget per agent, cancel an agent in one call (new requests refused, its waiting requests withdrawn, its identity tokens revoked) and resume it, through new owner-only agents routes. Approval is unchanged: an agent files a request and only a person approves it, bound to the exact plan.
