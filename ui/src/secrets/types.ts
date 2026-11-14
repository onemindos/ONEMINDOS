// SPDX-License-Identifier: Apache-2.0
// Shapes of the gateway's secrets and owner-override routes (docs/leap/core/SECRETS.md).
// None of them ever carries a secret value: values leave the browser only inside SealedInput.

export type SecretKind = 'api-key' | 'password' | 'token' | 'url';

/** One declared key and whether the box holds a value for it. */
export interface SecretKeyState {
  key: string;
  kind: SecretKind;
  description: string;
  required: boolean;
  /** owner: typed by the owner; generated: made by the box at install, rotatable. */
  source: 'owner' | 'generated';
  set: boolean;
  version: number | null;
  updated_at: string | null;
}

export interface AppSecretDecl {
  /** The Kubernetes Secret in app-<id>. */
  name: string;
  description: string;
  keys: SecretKeyState[];
}

/** GET /v1/apps/{id}/secrets */
export interface AppSecrets {
  app_id: string;
  secrets: AppSecretDecl[];
  /** "<secret>/<key>" of required keys without a value. */
  missing_required: string[];
  /** Which box key the form is sealed to (shown to the owner). */
  key_id: string;
}

/** GET /v1/secrets/public-key */
export interface SecretsPublicKey {
  alg: 'X25519';
  /** base64url, 32 bytes */
  key: string;
  key_id: string;
  sealed_alg: 'X25519-AES256GCM';
}

/** Contract §12.1 sealed input. */
export interface SealedInput {
  alg: 'X25519-AES256GCM';
  kid?: string;
  epk: string;
  ct: string;
}

/** { <secret name>: { <key>: <value> } } — lives only in the browser until sealed. */
export type SecretValues = Record<string, Record<string, string>>;

/** What the form hands its caller. `generate` and `clear` are "<secret>/<key>" refs (change mode). */
export interface SecretsSubmission {
  values: SecretValues;
  generate: string[];
  clear: string[];
}

/** GET /v1/apps/{id}/owner-override (owner only). */
export interface OwnerOverrideInfo {
  app_id: string;
  /** ONEMIND_ALLOW_OWNER_OVERRIDE=1 on this box (F-7: off by default). */
  enabled: boolean;
  scan_problem: string | null;
  eligible: boolean;
  /** Why this app can never be overridden (malware, no scan record), when that is the case. */
  refusal: string | null;
  /** The text the owner must type: the app id. */
  confirm: string;
  reason_length: [number, number];
  /** passkey once the owner has one (identity feature); none before. */
  step_up: 'passkey' | 'none';
  requester_must_be: 'person';
}

/** The approve body's `override` field. */
export interface OwnerOverrideInput {
  reason: string;
  confirm: string;
}
