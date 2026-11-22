---
pr: pending
branch: claude/phone-approver-key-hub
---
Phone approver keys, gateway side (Refs #702): an owner signed in with a fresh passkey can register a phone's P-256 approver key (named for the phone, key kind hardware-reported or software; hardware-attested is refused until attestation is verified), list it and revoke it (POST, GET and DELETE /v1/auth/approver-keys). Approve-options now also returns device_payload, and POST /v1/actions/{id}/approve accepts device_signature, an ECDSA signature by that key, checked against the action and plan hash, the 120-second expiry and single use, with the phone name and key kind in the audit. Destructive and actuate approvals stay passkey-only behind the new F-2 setting ONEMIND_IDENTITY_APPROVER_KEY_HIGH_RISK (off), physical actions always need a passkey, and the SDK spec is regenerated.
