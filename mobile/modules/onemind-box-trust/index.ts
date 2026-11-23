// SPDX-License-Identifier: Apache-2.0
// JS side of the box-trust module (Android only). It makes the app's own HTTPS (fetch, OkHttp) trust
// the one box CA this phone paired with, by its sha256 from the join QR, and nothing more: the system
// CAs still apply to every other address. On iPhone, in tests and in Expo Go the module is absent and
// `boxTrust` is undefined; src/pair/trust.ts then uses the system's own TLS checks only.
import { requireOptionalNativeModule } from 'expo';

/** What one probe of a candidate address saw. `caDer` is base64url (no padding). */
export interface BoxProbe {
  /** sha256 hex of the CA certificate the address served at /v1/tls/ca.crt. */
  servedCa: string;
  /** The TLS chain the address presented verifies to that CA (and its name matches). */
  chainOk: boolean;
  caDer: string;
}

export interface BoxTrustNative {
  /** Trust this CA (DER, base64url) for the app's HTTPS from now on; replaces any earlier pin. Kept across restarts. */
  pin(caDer: string): void;
  /** Forget the pinned CA. */
  clear(): void;
  /** sha256 hex of the pinned CA, or null. */
  pinned(): string | null;
  /** Fetch `${url}/v1/tls/ca.crt` without trusting it yet, and check the served chain against it. https only. */
  probe(url: string, timeoutMs: number): Promise<BoxProbe>;
}

export const boxTrust: BoxTrustNative | undefined = requireOptionalNativeModule<BoxTrustNative>('OneMindBoxTrust') ?? undefined;
