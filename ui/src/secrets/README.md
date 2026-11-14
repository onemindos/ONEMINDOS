<!-- SPDX-License-Identifier: Apache-2.0 -->
# App secrets and owner override (`ui/src/secrets/`)

**Serves:** CORE-SECRETS-1 and APP-OVERRIDE-1 ([`docs/leap/core/SECRETS.md`](../../../docs/leap/core/SECRETS.md)), DEPLOYMENTS.md §7 (D-R7), contract §12.1 (sealed input) and §12.18 (`spec.secrets`), founder decision F-7.
**Demo:** `#/secrets/<state>` in `ui/demo` with states `install`, `required`, `change`, `error`, `override`, `override-off`, `override-blocked`, `override-passkey`, `override-agent`, `mark`. Submitting really seals the form to a key made in the tab and shows the body that would be sent.

| File | What |
|---|---|
| `types.ts` | Shapes of `GET /v1/apps/{id}/secrets`, `GET /v1/secrets/public-key`, `GET /v1/apps/{id}/owner-override`, the sealed input and the override input |
| `logic.ts` | Pure rules mirroring the gateway: value checks per kind, required keys, the override's reason and typed confirmation, the approve body |
| `seal.ts` | `sealValues(publicKey, appId, values)`: X25519 + HKDF-SHA256 + AES-256-GCM with WebCrypto, bound to the app id |
| `SecretsForm.tsx` | The form. `mode="install"` sits in the install approval; `mode="change"` on the app page (set, rotate generated keys, clear optional ones) |
| `OwnerOverride.tsx` | `OwnerOverrideDialog` (off, refused, or reason + typed app id + passkey note) and `OwnerOverrideMark` (the red mark) |

## Wiring (dashboard pass)
1. Install approval for an app with secrets: `GET /v1/apps/{id}/secrets` → `<SecretsForm mode="install">` → on submit `GET /v1/secrets/public-key`, `sealValues(...)`, then `POST /v1/actions/{id}/approve` with `approveBody({sealed})`.
2. App page: `<SecretsForm mode="change">` → `POST /v1/apps/{id}/secrets` with `{sealed?, generate, clear}` → the returned `app.configure` action goes through the normal approval card.
3. A 409 on approve whose message says the scan failed: owners `GET /v1/apps/{id}/owner-override` and open `<OwnerOverrideDialog>`; on confirm, approve with `approveBody({override, webauthn})` (the passkey assertion once identity lands). Show `<OwnerOverrideMark>` wherever the action's `result.owner_override.mark` is set.

## Rules the code follows
- No value is ever displayed after it is typed: the hub returns names and set flags only, inputs are masked with a per-field Show toggle, and typed values are dropped from state after submit and on unmount.
- Values leave the browser only inside `sealed`; the caller seals right before sending.
- A refused override is explained (off on this box, malware, an agent's request), never silently hidden.
- If WebCrypto lacks X25519 (old browsers), the dashboard says so and points to the `onemind-secrets` terminal helper; it never falls back to plain text.
