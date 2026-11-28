<!-- SPDX-License-Identifier: Apache-2.0 -->
# Private plugin signing keys (E9, issue 180)

`GET /v1/plugin-trust/keys` lists real enrolled public keys and revocations for owners (`apps:read`). `POST /v1/plugin-trust/keys/requests` requests `plugin.key.enroll`; `POST /v1/plugin-trust/keys/{fingerprint}/revoke` requests `plugin.key.revoke`. Narrow personal tokens need the exact action scope as well as owner identity. Plugins cannot manage signing trust.

Enrollment accepts one SPKI public PEM (Ed25519, RSA at least 2048 bits, or NIST P-256/P-384/P-521). Its identifier is `sha256:` plus the SHA-256 hex digest of canonical SPKI DER. Private, multiple and unsupported keys are rejected before candidate storage, action filing or auditing. Action parameters expose the fingerprint and label for review, never private material.

Both mutations file pending sensitive actions. Trust changes only after explicit owner approval; active passkeys require an action-bound assertion even when global passkey approval is optional. The dashboard fetches generated `ApprovalChallenge` options only after the gateway requests step-up, invokes the browser authenticator, and submits its assertion without automatic retry. Cancelling submits no approval.

New trust tables use a separate feature schema. Enrollment is idempotent by owner and request key; changing a proposal conflicts. Re-enrollment of a revoked key requires another approved action. Revocation affects future verification; this slice does not terminate installed workloads. OCI verification must separately consult active trust, signatures, scan freshness, revocation metadata and compatibility before installation. Candidate-key signature validity alone never grants trust.
