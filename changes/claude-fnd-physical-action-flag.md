---
pr: pending
branch: claude/fnd-physical-action-flag
---
Physical actions (#723): an action type can be registered with an immutable physical flag, separate from its risk class. A physical action is approved only by an owner with a passkey and hold-to-approve, bound to its plan_sha256 (changed parameters or limits need a new approval), is never covered by a standing approval and never filed by an automation, and is refused while the owner's motion lockout (GET and PUT /v1/physical/lockout, owner only) is on. Every action now carries an approval card: hold is true for an action that cannot be undone (risk destructive) or that moves something physical, and a physical card adds limits with units and a preview slot. node.wake and OS install behave as before.
