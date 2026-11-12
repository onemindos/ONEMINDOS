// SPDX-License-Identifier: Apache-2.0
// Pure rules of the secrets form and the override dialog. They mirror the gateway
// (core/onemind_core/appsecrets/service.py value_problem, override.py), which stays the authority.
import type { AppSecrets, OwnerOverrideInfo, SecretKind, SecretsSubmission, SealedInput, OwnerOverrideInput } from './types';

export const VALUE_MIN = 4;
export const VALUE_MAX = 8192;

export const KIND_LABEL: Record<SecretKind, string> = {
  'api-key': 'API key',
  password: 'Password',
  token: 'Token',
  url: 'URL',
};

export const refOf = (secret: string, key: string) => `${secret}/${key}`;

/** Why a value cannot be stored, or undefined. Never repeats the value. */
export function valueProblem(kind: SecretKind, value: string): string | undefined {
  if (value.length < VALUE_MIN || value.length > VALUE_MAX) return `Use ${VALUE_MIN} to ${VALUE_MAX} characters.`;
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f\x7f]/.test(value)) return 'Remove line breaks and control characters.';
  if (kind !== 'password' && /\s/.test(value)) return 'Remove the spaces; keys and URLs have none.';
  if (kind === 'url') {
    const m = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\/([^/?#\s]+)/.exec(value);
    if (!m) return 'Enter a full URL with a scheme and a host, such as https://host:port/path.';
  }
  return undefined;
}

/** Field problems keyed by "<secret>/<key>", plus `_form` for the whole form. */
export function submissionProblems(secrets: AppSecrets, sub: SecretsSubmission, mode: 'install' | 'change'): Record<string, string> {
  const out: Record<string, string> = {};
  let changes = sub.generate.length + sub.clear.length;
  for (const s of secrets.secrets) {
    for (const k of s.keys) {
      const ref = refOf(s.name, k.key);
      const v = sub.values[s.name]?.[k.key] ?? '';
      if (v) {
        changes += 1;
        const p = valueProblem(k.kind, v);
        if (p) out[ref] = p;
      } else if (mode === 'install' && k.required && k.source === 'owner' && !k.set) {
        out[ref] = 'Required to install.';
      }
    }
  }
  if (mode === 'change' && changes === 0) out._form = 'Enter a new value, or choose Rotate or Clear.';
  return out;
}

/** Drops empty fields so only what the owner typed is sealed. */
export function compactValues(values: SecretsSubmission['values']): SecretsSubmission['values'] {
  const out: SecretsSubmission['values'] = {};
  for (const [name, keys] of Object.entries(values)) {
    for (const [key, v] of Object.entries(keys)) if (v) (out[name] ??= {})[key] = v;
  }
  return out;
}

export function overrideProblems(info: OwnerOverrideInfo, reason: string, confirm: string): { reason?: string; confirm?: string } {
  const [min, max] = info.reason_length;
  const r = reason.split(/\s+/).filter(Boolean).join(' ');
  return {
    reason: r.length < min || r.length > max ? `Write ${min} to ${max} characters.` : undefined,
    confirm: confirm !== info.confirm ? `Type ${info.confirm} exactly.` : undefined,
  };
}

/** Body of POST /v1/actions/{id}/approve. `webauthn` comes from the passkey step (identity). */
export function approveBody(parts: { sealed?: SealedInput; override?: OwnerOverrideInput; webauthn?: unknown }): Record<string, unknown> | undefined {
  const body: Record<string, unknown> = {};
  if (parts.sealed) body.sealed = parts.sealed;
  if (parts.override) body.override = parts.override;
  if (parts.webauthn) body.webauthn = parts.webauthn;
  return Object.keys(body).length ? body : undefined;
}
