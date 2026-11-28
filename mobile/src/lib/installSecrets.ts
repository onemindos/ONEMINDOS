// SPDX-License-Identifier: Apache-2.0
// Install secrets on the phone (#528): which keys the owner types, the value checks, and the step that
// turns the typed form into a sealed box. The rules mirror the gateway
// (core/onemind_core/appsecrets/service.py) and the dashboard (ui/src/secrets/logic.ts); the gateway
// stays the authority and refuses an install whose required secrets are missing.
import { OP, type Features, type OneMindApi } from '../api/client';
import { ApiError, type Action, type AppSecrets, type SealedInput, type SecretKeyState, type SecretKind, type SecretValues } from '../api/types';
import { sealValues, type AesGcm } from './seal';

export const VALUE_MIN = 4;
export const VALUE_MAX = 8192;

export const KIND_LABEL: Record<SecretKind, string> = { 'api-key': 'API key', password: 'Password', token: 'Token', url: 'URL' };

export const refOf = (secret: string, key: string) => `${secret}/${key}`;

/** The app an install request is for, or undefined for any other request. */
export function installAppId(a: Pick<Action, 'type' | 'params'>): string | undefined {
  return a.type === 'app.install' && typeof a.params?.app_id === 'string' ? a.params.app_id : undefined;
}

/** The keys the owner types (generated ones are made by the box at install). */
export function ownerKeys(s: AppSecrets): Array<{ secret: string; key: SecretKeyState }> {
  return s.secrets.flatMap((d) => d.keys.filter((k) => k.source === 'owner').map((key) => ({ secret: d.name, key })));
}

/** How many keys the box makes itself, to say so on the form. */
export function generatedCount(s: AppSecrets): number {
  return s.secrets.reduce((n, d) => n + d.keys.filter((k) => k.source === 'generated').length, 0);
}

/** Why a value cannot be stored, or undefined. Never repeats the value. */
export function valueProblem(kind: SecretKind, value: string): string | undefined {
  if (value.length < VALUE_MIN || value.length > VALUE_MAX) return `Use ${VALUE_MIN} to ${VALUE_MAX} characters.`;
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f\x7f]/.test(value)) return 'Remove line breaks and control characters.';
  if (kind !== 'password' && /\s/.test(value)) return 'Remove the spaces; keys and URLs have none.';
  if (kind === 'url' && !/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^/?#\s]+/.test(value))
    return 'Enter a full URL with a scheme and a host, such as https://host:port/path.';
  return undefined;
}

/** Field problems keyed by "<secret>/<key>". Empty when the form can be sealed. */
export function formProblems(s: AppSecrets, values: SecretValues): Record<string, string> {
  const out: Record<string, string> = {};
  for (const { secret, key } of ownerKeys(s)) {
    const v = values[secret]?.[key.key] ?? '';
    if (v) {
      const p = valueProblem(key.kind, v);
      if (p) out[refOf(secret, key.key)] = p;
    } else if (key.required && !key.set) out[refOf(secret, key.key)] = 'Required to install.';
  }
  return out;
}

/** Only what the owner typed, and only for declared owner keys. */
export function compactValues(s: AppSecrets, values: SecretValues): SecretValues {
  const out: SecretValues = {};
  for (const { secret, key } of ownerKeys(s)) {
    const v = values[secret]?.[key.key];
    if (v) (out[secret] ??= {})[key.key] = v;
  }
  return out;
}

/**
 * Before an install is approved: the app's declared secrets when the owner has to type any, else
 * undefined (no form; approve as usual). A hub without the secrets routes, or an app the hub no
 * longer knows, also means no form: the gateway refuses the approval if secrets were needed.
 */
export async function secretsToAsk(api: OneMindApi, features: Features, a: Action): Promise<AppSecrets | undefined> {
  const appId = installAppId(a);
  if (!appId || !api.appSecrets || !features.has(OP.appSecrets) || !features.has(OP.secretsPublicKey)) return undefined;
  try {
    const s = await api.appSecrets(appId);
    return ownerKeys(s).length ? s : undefined;
  } catch (e) {
    if (e instanceof ApiError && e.code === 'not_found') return undefined;
    throw e;
  }
}

/** Seal the typed values to the box's current key, bound to this app. Nothing is sent here. */
export async function sealInstallSecrets(api: OneMindApi, s: AppSecrets, values: SecretValues, aes?: AesGcm): Promise<SealedInput> {
  if (!api.secretsPublicKey) throw new ApiError(404, 'not_found', 'This hub cannot take sealed secrets.');
  const pk = await api.secretsPublicKey();
  // The form was read for one box key; if the hub's key changed since, the hub would refuse the box anyway.
  if (s.key_id && pk.key_id !== s.key_id) throw new Error("the hub's sealing key changed since the form opened; close it and approve again");
  return sealValues(pk, s.app_id, compactValues(s, values), aes);
}
