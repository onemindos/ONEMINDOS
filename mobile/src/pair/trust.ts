// SPDX-License-Identifier: Apache-2.0
// How the phone checks and trusts the box certificate (issue 716). The join QR carries the sha256 of the
// box CA (core/onemind_core/ca.py ca_fingerprint: sha256 of the DER certificate). Each candidate address is
// asked for /v1/tls/ca.crt; the answer counts only if its sha256 is the one in the QR AND the address's own
// TLS chain verifies to that CA. Then, on Android, the CA is pinned in the app's HTTPS stack
// (modules/onemind-box-trust): no certificate warning and no CA install in the phone's settings.
import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex } from '@noble/hashes/utils.js';
import { boxTrust, type BoxProbe } from '../../modules/onemind-box-trust';
import type { FetchLike } from '../api/client';
import { toB64url } from '../lib/device';

export type { BoxProbe };

export interface BoxTrust {
  /** `pinned`: the app's own TLS trusts the pinned box CA (Android). `system`: only the OS trust store (iPhone, for now). */
  readonly mode: 'pinned' | 'system';
  probe(url: string): Promise<BoxProbe>;
  pin(caDer: string): void;
  clear(): void;
}

export const caSha256 = (der: Uint8Array): string => bytesToHex(sha256(der));

const PROBE_TIMEOUT_MS = 6_000;

/** Android: the native module fetches the CA without trusting it first, then checks the chain against it. */
function nativeTrust(n: NonNullable<typeof boxTrust>): BoxTrust {
  return { mode: 'pinned', probe: (url) => n.probe(url, PROBE_TIMEOUT_MS), pin: (der) => n.pin(der), clear: () => n.clear() };
}

/**
 * Without the module the OS checks the TLS chain itself (a box with only its own CA fails here and the next
 * address is tried); an answer that gets through still has to match the QR's sha256.
 */
export function systemTrust(fetchFn: FetchLike = (u, i) => fetch(u, i)): BoxTrust {
  return {
    mode: 'system',
    async probe(url) {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), PROBE_TIMEOUT_MS);
      try {
        const res = await fetchFn(`${url}/v1/tls/ca.crt`, { signal: ctl.signal, headers: { Accept: 'application/x-x509-ca-cert' } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const der = new Uint8Array(await res.arrayBuffer());
        return { servedCa: caSha256(der), chainOk: true, caDer: toB64url(der) };
      } finally {
        clearTimeout(timer);
      }
    },
    pin: () => undefined,
    clear: () => undefined,
  };
}

export function defaultTrust(): BoxTrust {
  return boxTrust ? nativeTrust(boxTrust) : systemTrust();
}
