---
pr: 936
branch: claude/phone-my-devices
---
My devices, first slice (Refs #715): GET /v1/me/devices lists the phones, browsers and apps signed in as you, each joining the sessions, passkeys, approver keys (when #702 is in) and push registrations that carry its name, with kind and last seen; mesh and NATS report as absent until per-person credentials exist. DELETE /v1/me/devices/{id} (Lost this device) revokes all of them in one step: a person's own session only (never an API token or agent), a fresh passkey once passkeys are on, never the device in use or the box's last owner passkey, audited as auth.device.removed and idempotent (a second call revokes nothing). The phone shows the list in Settings with Lost this device behind a second tap. The dashboard screen follows in another PR.
