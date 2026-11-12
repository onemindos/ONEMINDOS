// SPDX-License-Identifier: Apache-2.0
import type { CatalogApp } from '../api/types';

/** §10.3 / §11.1: the hub installs only apps with a passing scan at most 7 days old. */
export const SCAN_MAX_AGE_MS = 7 * 86_400_000;
/** Same tolerance as the gateway for a scan dated slightly in the future (clock skew). */
const FUTURE_SKEW_MS = 5 * 60_000;

/** "12 Nov 2026" in UTC, so every viewer sees the same date the hub recorded. */
export function formatDay(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'unknown date';
  return new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
}

/**
 * Why Install is not offered for this app, or undefined when it is.
 * `hubNow` is the hub's clock (the gateway decides staleness on its own clock).
 * Mirrors the gateway's approve check, so the UI does not offer what will be refused;
 * the gateway stays the authority and still answers 409 stale_precondition.
 */
export function installBlockReason(app: Pick<CatalogApp, 'scan'>, hubNow: number): string | undefined {
  const scan = app.scan;
  if (!scan) return 'Not scanned yet. Only apps with a passing security scan from the last 7 days can be installed.';
  const t = Date.parse(scan.scanned_at);
  if (Number.isNaN(t) || t - hubNow > FUTURE_SKEW_MS) return 'The scan record has an invalid date, so it cannot be trusted.';
  if (scan.result !== 'pass') return `Failed its last security scan (${formatDay(scan.scanned_at)}).`;
  if (hubNow - t > SCAN_MAX_AGE_MS)
    return `Last scanned ${formatDay(scan.scanned_at)}, more than 7 days ago. Waiting for a new scan.`;
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
