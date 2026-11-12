// SPDX-License-Identifier: Apache-2.0
// App trust rules (contract §9.3, §10.3, §11.1, §11.4). The gateway is the authority;
// the UI mirrors its rule so it never offers what the hub would refuse.

export type AppTier = 'verified' | 'community' | 'blocked';
export type CosignState = 'verified' | 'unsigned' | 'failed';

export interface ScanSummary {
  scanned_at: string;
  result: 'pass' | 'fail';
  critical?: number;
  high?: number;
  malware?: number;
  cosign?: CosignState;
}

export const SCAN_MAX_AGE_MS = 7 * 86_400_000;
const FUTURE_SKEW_MS = 5 * 60_000;

/** Why Install is not offered, or undefined when it is. */
export function installBlockReason(scan: ScanSummary | null | undefined, tier: AppTier | null | undefined, now: number): string | undefined {
  if (tier === 'blocked') return 'Blocked by the Market (licence, malware or a failed check). It cannot be installed.';
  if (!scan) return 'Not scanned yet. Only apps with a passing security scan from the last 7 days can be installed.';
  const t = Date.parse(scan.scanned_at);
  if (Number.isNaN(t) || t - now > FUTURE_SKEW_MS) return 'The scan record has an invalid date, so it cannot be trusted.';
  if (scan.result !== 'pass') return 'Failed its last security scan.';
  if (now - t > SCAN_MAX_AGE_MS) return 'The last scan is more than 7 days old. Waiting for a new scan.';
  return undefined;
}

/** Only absolute http(s) links are rendered (never javascript: or data: URLs). */
export function safeHttpUrl(u: string | null | undefined): string | undefined {
  if (!u) return undefined;
  try {
    const url = new URL(u);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : undefined;
  } catch {
    return undefined;
  }
}
