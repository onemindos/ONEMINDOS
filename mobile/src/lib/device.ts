// SPDX-License-Identifier: Apache-2.0
// This phone as a device of the box (docs/umbrel2/clients.md §4.3–4.4, CLIENT-2; not yet in the contract).
// Adding a device is a request: `POST /v1/devices/requests` files the action `device.add`, and only an
// owner can approve it (on this phone, the dashboard or the CLI). The owner's own first phone may be
// approved at once by the box (`approval: self`). Once active, the device renews its sign-in with a
// DPoP proof (RFC 9449) from a key that never leaves this phone.
//
// Key storage today is `software`: a P-256 key made with a CSPRNG (expo-crypto) and kept in the
// Keychain / Keystore-encrypted secure store. A hardware key (Secure Enclave, StrongBox) needs a
// native module and is a follow-up; the box shows `key_storage` so the owner can see the difference.
import { p256 } from '@noble/curves/nist.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { utf8ToBytes } from '@noble/hashes/utils.js';
import Constants from 'expo-constants';
import * as Crypto from 'expo-crypto';
import { Platform } from 'react-native';
import { OP, type Features, type OneMindApi } from '../api/client';
import { ApiError, type DeviceRequest, type DeviceState, type EcPublicJwk, type LoginResult } from '../api/types';
import { deleteSecret, loadSecret, saveSecret } from '../storage';

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

/** Unpadded base64url (no Buffer or btoa needed). */
export function toB64url(b: Uint8Array): string {
  let out = '';
  for (let i = 0; i < b.length; i += 3) {
    const n = (b[i]! << 16) | ((b[i + 1] ?? 0) << 8) | (b[i + 2] ?? 0);
    out += B64[(n >> 18) & 63]! + B64[(n >> 12) & 63]!;
    if (i + 1 < b.length) out += B64[(n >> 6) & 63]!;
    if (i + 2 < b.length) out += B64[n & 63]!;
  }
  return out;
}

export function fromB64url(s: string): Uint8Array {
  const clean = s.replace(/=+$/, '');
  const out: number[] = [];
  let buf = 0;
  let bits = 0;
  for (const ch of clean) {
    const v = B64.indexOf(ch);
    if (v < 0) throw new Error('not base64url');
    buf = (buf << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out.push((buf >> bits) & 255);
    }
  }
  return Uint8Array.from(out);
}

export interface DeviceKey {
  secret: Uint8Array;
  jwk: EcPublicJwk;
}

export function keyFromSecret(secret: Uint8Array): DeviceKey {
  const pub = p256.getPublicKey(secret, false); // 0x04 ‖ X ‖ Y
  return { secret, jwk: { kty: 'EC', crv: 'P-256', x: toB64url(pub.slice(1, 33)), y: toB64url(pub.slice(33, 65)) } };
}

/** RFC 7638 JWK thumbprint: what the box binds this device's tokens to. */
export function thumbprint(jwk: EcPublicJwk): string {
  return toB64url(sha256(utf8ToBytes(`{"crv":"${jwk.crv}","kty":"${jwk.kty}","x":"${jwk.x}","y":"${jwk.y}"}`)));
}

type Random = (n: number) => Uint8Array;
const cryptoRandom: Random = (n) => Crypto.getRandomBytes(n);

const KEY = 'onemind.devicekey.v1';

/** This phone's device key: loaded from the secure store, or made once. */
export async function loadOrCreateKey(random: Random = cryptoRandom): Promise<DeviceKey> {
  const stored = await loadSecret(KEY);
  if (stored) {
    try {
      return keyFromSecret(fromB64url(stored));
    } catch {
      /* unreadable: make a new one; the box then sees a new device */
    }
  }
  const secret = p256.utils.randomSecretKey(random(p256.lengths.seed ?? 48));
  await saveSecret(KEY, toB64url(secret));
  return keyFromSecret(secret);
}

export async function loadKey(): Promise<DeviceKey | undefined> {
  const stored = await loadSecret(KEY);
  return stored ? keyFromSecret(fromB64url(stored)) : undefined;
}

/** RFC 9449 DPoP proof: a short JWT signed by the device key, bound to one method and URL. */
export function dpopProof(
  key: DeviceKey,
  o: { htm: string; htu: string; nonce?: string; iat?: number; jti?: string; random?: Random },
): string {
  const header = { typ: 'dpop+jwt', alg: 'ES256', jwk: key.jwk };
  const payload = {
    jti: o.jti ?? toB64url((o.random ?? cryptoRandom)(16)),
    htm: o.htm,
    htu: o.htu,
    iat: o.iat ?? Math.floor(Date.now() / 1000),
    ...(o.nonce ? { nonce: o.nonce } : {}),
  };
  const input = `${toB64url(utf8ToBytes(JSON.stringify(header)))}.${toB64url(utf8ToBytes(JSON.stringify(payload)))}`;
  // ES256 = ECDSA P-256 over SHA-256, signature as raw r ‖ s (64 bytes); deterministic (RFC 6979).
  const sig = p256.sign(utf8ToBytes(input), key.secret, { prehash: true, format: 'compact', extraEntropy: false });
  return `${input}.${toB64url(sig)}`;
}

/** What the phone remembers about its device request on one hub. */
export interface DeviceLink {
  hubUrl: string;
  requestId: string;
  pollCode?: string;
  deviceId?: string;
  actionId?: string | null;
  state: DeviceState;
  /** Device-bound refresh token, given once when the request turns active. */
  refreshToken?: string;
  since: string;
}

const LINK = 'onemind.device.v1';

export async function loadLink(hubUrl: string): Promise<DeviceLink | undefined> {
  try {
    const l = JSON.parse((await loadSecret(LINK)) ?? 'null') as DeviceLink | null;
    return l && l.hubUrl === hubUrl && typeof l.requestId === 'string' ? l : undefined;
  } catch {
    return undefined;
  }
}

async function saveLink(l: DeviceLink) {
  await saveSecret(LINK, JSON.stringify(l)).catch(() => undefined);
}

/** Forget the device record and key (Disconnect). The box keeps its record until the owner revokes it. */
export async function forgetDevice(): Promise<void> {
  await deleteSecret(LINK);
  await deleteSecret(KEY);
}

function merge(prev: Partial<DeviceLink>, r: DeviceRequest, hubUrl: string, now: number): DeviceLink {
  return {
    hubUrl,
    requestId: r.id ?? prev.requestId!,
    pollCode: r.poll_code ?? prev.pollCode,
    deviceId: r.device_id ?? prev.deviceId,
    actionId: r.action_id ?? prev.actionId,
    state: r.state,
    refreshToken: r.one_time?.refresh_token ?? prev.refreshToken,
    since: prev.since ?? new Date(now).toISOString(),
  };
}

export function deviceInfo(name: string) {
  return {
    name: name.trim().slice(0, 64) || (Platform.OS === 'ios' ? 'iPhone' : 'Android phone'),
    kind: 'phone' as const,
    platform: (Platform.OS === 'ios' ? 'ios' : 'android') as 'ios' | 'android',
    app_version: Constants.expoConfig?.version ?? '0.0.0',
    os_version: String(Platform.Version),
  };
}

/** Ask the owner to add this phone. Files `device.add`; the answer may already be `active` (owner's own phone). */
export async function requestDevice(api: OneMindApi, hubUrl: string, name: string, o: { random?: Random; now?: number } = {}): Promise<DeviceLink> {
  const key = await loadOrCreateKey(o.random);
  const r = await api.deviceRequest({ ...deviceInfo(name), jwk: key.jwk });
  const link = merge({}, r, hubUrl, o.now ?? Date.now());
  await saveLink(link);
  return link;
}

/** Check a pending request (the owner may have approved or denied it). */
export async function pollDevice(api: OneMindApi, link: DeviceLink): Promise<DeviceLink> {
  const r = await api.deviceRequestStatus(link.requestId, link.pollCode);
  const next = merge(link, r, link.hubUrl, Date.now());
  await saveLink(next);
  return next;
}

/**
 * Renew this phone's sign-in with its device key (SessionDeps.renewWithDevice). One retry with the
 * server's nonce when it asks for one (RFC 9449 §8, `DPoP-Nonce`).
 */
export async function renewWithDevice(api: OneMindApi, features: Features, hubUrl: string): Promise<LoginResult | undefined> {
  if (!features.has(OP.deviceToken)) return undefined;
  const link = await loadLink(hubUrl);
  const key = await loadKey();
  if (!link || link.state !== 'active' || !link.refreshToken || !key) return undefined;
  const htu = `${hubUrl}/v1/devices/token`;
  let r: LoginResult;
  try {
    r = await api.deviceToken(dpopProof(key, { htm: 'POST', htu }), link.refreshToken);
  } catch (e) {
    if (!(e instanceof ApiError) || !e.dpopNonce) throw e;
    r = await api.deviceToken(dpopProof(key, { htm: 'POST', htu, nonce: e.dpopNonce }), link.refreshToken);
  }
  if (r.refresh_token && r.refresh_token !== link.refreshToken) await saveLink({ ...link, refreshToken: r.refresh_token });
  return r;
}
