// SPDX-License-Identifier: Apache-2.0
// Pair this phone with a box from its join QR (issue 716, FABRIC §4.3 onemind-join:v2). Steps:
//   1. read the scanned or typed code with the shared parser (sdk joinqr); refuse plain http and a code
//      this phone has already used (replay);
//   2. try the addresses in the code in order: hub, then mdns, then alt; the first that serves the box CA
//      with the QR's sha256, under a chain that verifies to it, is pinned (trust.ts). A different CA on any
//      address stops the whole join: nothing is trusted and nothing is sent;
//   3. finish with passkey sign-in (lib/signin) or the person's enrolment code (POST /v1/auth/enrol, an
//      owner-made one-time code, 24 hours). The QR code is then marked used on this phone.
// No token is pasted and no password leaves the phone except to the pinned box.
import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex, utf8ToBytes } from '@noble/hashes/utils.js';
import { errorFrom, type FetchLike } from '../api/client';
import type { LoginResult } from '../api/types';
import { PROTOCOL_HEADER, PROTOCOL_VERSION } from '../lib/protocol';
import { fromB64url } from '../lib/device';
import { deleteSecret, loadSecret, saveSecret, type LiveConnection } from '../storage';
import { JoinQRError, parseJoinQR, type JoinQR } from './joinqr';
import { caSha256, defaultTrust, type BoxTrust } from './trust';

export type PairErrorKind = 'code' | 'insecure' | 'mismatch' | 'unreachable' | 'expired' | 'replay' | 'rejected';

export class PairError extends Error {
  constructor(
    readonly kind: PairErrorKind,
    message: string,
  ) {
    super(message);
    this.name = 'PairError';
  }
}

/** What the phone keeps about the box it trusts (secure store; the CA itself is public data). */
export interface BoxPin {
  /** sha256 hex of the box CA, from the join QR. */
  ca: string;
  /** The address that answered first. */
  hubUrl: string;
  /** Every address in the code, in the order tried. */
  addresses: string[];
  mode: BoxTrust['mode'];
  pinnedAt: string;
}

const PIN = 'onemind.boxpin.v1';
const SPENT = 'onemind.pair.spent.v1';
const SPENT_MAX = 64;

export async function loadPin(): Promise<BoxPin | undefined> {
  try {
    const p = JSON.parse((await loadSecret(PIN)) ?? 'null') as BoxPin | null;
    return p && typeof p.ca === 'string' && typeof p.hubUrl === 'string' ? p : undefined;
  } catch {
    return undefined;
  }
}

export async function forgetPin(trust: BoxTrust = defaultTrust()): Promise<void> {
  trust.clear();
  await deleteSecret(PIN);
}

const codeHash = (code: string) => bytesToHex(sha256(utf8ToBytes(`onemind-pair:${code.trim()}`)));

async function spent(): Promise<string[]> {
  try {
    const v = JSON.parse((await loadSecret(SPENT)) ?? '[]') as unknown;
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

export async function wasUsed(code: string): Promise<boolean> {
  return (await spent()).includes(codeHash(code));
}

/** Remember a one-time code as used, so the same QR or enrolment code is never sent again from this phone. */
export async function markUsed(code: string): Promise<void> {
  const h = codeHash(code);
  const list = (await spent()).filter((x) => x !== h);
  await saveSecret(SPENT, JSON.stringify([...list, h].slice(-SPENT_MAX))).catch(() => undefined);
}

const PLAIN_HTTP = /(?:^|[?&])(?:hub|alt)=http(?::|%3a)/i;

/** Read a scanned or typed join code. Throws PairError. */
export async function readJoin(text: string): Promise<JoinQR> {
  const v = text.trim();
  let q: JoinQR;
  try {
    q = parseJoinQR(v);
  } catch (e) {
    if (e instanceof JoinQRError && (e.reason === 'hub' || e.reason === 'alt') && PLAIN_HTTP.test(v))
      throw new PairError('insecure', 'This code points at a plain http:// address. The phone pairs only over https, so nothing was sent.');
    throw new PairError('code', e instanceof Error ? e.message : String(e));
  }
  if (q.version !== 2) throw new PairError('code', 'This is an older machine join code (v1). On the box, show the code for a phone.');
  if (await wasUsed(q.code)) throw new PairError('replay', 'This code was already used on this phone. On the box, make a new one.');
  return q;
}

/** hub, then mdns (on the hub's port), then alt; no repeats. */
export function addresses(q: JoinQR): string[] {
  const port = /:(\d+)$/.exec(q.hub)?.[1];
  const mdns = q.mdns ? `https://${q.mdns}${port ? `:${port}` : ''}` : '';
  return [...new Set([q.hub, mdns, q.alt].filter(Boolean))];
}

const host = (url: string) => url.replace(/^https:\/\//, '');

/** Find the box at one of the code's addresses, check its CA against the code, and pin it. */
export async function trustBox(q: JoinQR, o: { trust?: BoxTrust; now?: number } = {}): Promise<BoxPin> {
  const trust = o.trust ?? defaultTrust();
  const list = addresses(q);
  const failed: string[] = [];
  for (const url of list) {
    if (!url.startsWith('https://')) throw new PairError('insecure', `${url} is not https; nothing was sent.`);
    let p;
    try {
      p = await trust.probe(url);
    } catch (e) {
      failed.push(`${host(url)} (${e instanceof Error ? e.message : String(e)})`);
      continue;
    }
    let actual = '';
    try {
      actual = caSha256(fromB64url(p.caDer));
    } catch {
      /* unreadable: a mismatch below */
    }
    if (actual !== q.ca || p.servedCa !== q.ca)
      throw new PairError(
        'mismatch',
        `${host(url)} answered with a different box certificate than the code shows, so nothing was trusted or sent. If this is your box, make a new code on it; otherwise someone may be in between.`,
      );
    if (!p.chainOk)
      throw new PairError('mismatch', `${host(url)} did not prove it holds a certificate from this box, so nothing was trusted or sent.`);
    trust.pin(p.caDer);
    const pin: BoxPin = { ca: q.ca, hubUrl: url, addresses: list, mode: trust.mode, pinnedAt: new Date(o.now ?? Date.now()).toISOString() };
    await saveSecret(PIN, JSON.stringify(pin));
    return pin;
  }
  throw new PairError('unreachable', `Could not reach the box at ${failed.join(', ')}. Join the same Wi-Fi as the box, or use its outside address.`);
}

/**
 * Finish with the enrolment code the owner made for this person (People on the dashboard): the box claims
 * the code once and answers with a session that renews itself. Only to an https hub (the pinned box).
 */
export async function enrolWithCode(
  hubUrl: string,
  f: { code: string; username?: string; password: string },
  o: { fetchFn?: FetchLike } = {},
): Promise<LiveConnection> {
  if (!hubUrl.startsWith('https://')) throw new PairError('insecure', 'Enrolment needs the box’s https address; nothing was sent.');
  const code = f.code.trim();
  if (await wasUsed(code)) throw new PairError('replay', 'This enrolment code was already used on this phone. Ask the owner for a new one.');
  const fetchFn = o.fetchFn ?? ((u, i) => fetch(u, i));
  const res = await fetchFn(`${hubUrl}/v1/auth/enrol`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'OneMind-API-Version': '1', [PROTOCOL_HEADER]: String(PROTOCOL_VERSION) },
    body: JSON.stringify({ code, password: f.password, client: 'app', ...(f.username?.trim() ? { username: f.username.trim() } : {}) }),
  });
  let data: unknown;
  try {
    data = await res.json();
  } catch {
    data = undefined;
  }
  if (!res.ok) {
    const e = errorFrom(res.status, data, res.headers.get('Retry-After'));
    if (e.reason === 'code_used') {
      await markUsed(code);
      throw new PairError('replay', 'This enrolment code was already used. Ask the owner for a new one.');
    }
    if (res.status === 401 || e.code === 'expired' || e.reason === 'code_unknown')
      throw new PairError('expired', 'This enrolment code has expired or is not known on this box. Codes last 24 hours; ask the owner for a new one.');
    if (res.status === 409 || res.status === 422) throw new PairError('rejected', e.message);
    throw e;
  }
  const r = data as Partial<LoginResult> | undefined;
  if (!r || typeof r.access_token !== 'string') throw new PairError('rejected', 'The box answered without a session.');
  await markUsed(code);
  // A hub session (like passkey sign-in): short-lived bearer renewed with the refresh token (session.tsx).
  return {
    mode: 'live',
    hubUrl,
    token: r.access_token,
    auth: 'passkey',
    ...(r.expires_at ? { expiresAt: r.expires_at } : {}),
    ...(r.refresh_token ? { refreshToken: r.refresh_token } : {}),
  };
}
