---
pr: pending
branch: claude/fnd-physical-action-flag
---
Physical actions (#723): an action type can be registered with an immutable physical flag, separate from its risk class. A physical action is approved only by an owner with a passkey and hold-to-approve, bound to its plan_sha256 (changed parameters or limits need a new approval), is never covered by a standing approval and never filed by an automation, and is refused while the owner's motion lockout (GET and PUT /v1/physical/lockout, owner only) is on. Actions now carry an approval card with the hold flag, limits with units and a preview slot. node.wake and OS install behave as before.
