// SPDX-License-Identifier: Apache-2.0
// Time helpers. Every component that shows age takes `now` from its caller, so the
// screen and the tests agree on one clock (the hub's clock in the dashboard).

/** Seconds from `iso` to `now` (ms epoch); NaN when the date is unreadable. */
export function secondsSince(iso: string, now: number): number {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? Number.NaN : Math.max(0, Math.round((now - t) / 1000));
}

/** "just now", "42 s ago", "5 min ago", "3 h ago", "2 d ago"; "unknown" when NaN. */
export function formatAgo(seconds: number): string {
  if (!Number.isFinite(seconds)) return 'unknown';
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86_400)} d ago`;
}

/** "in 23 h", "in 4 min"; "expired" when in the past. */
export function formatIn(iso: string, now: number): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'unknown';
  const s = Math.round((t - now) / 1000);
  if (s <= 0) return 'expired';
  if (s < 60) return `in ${s} s`;
  if (s < 3600) return `in ${Math.floor(s / 60)} min`;
  if (s < 86_400) return `in ${Math.floor(s / 3600)} h`;
  return `in ${Math.floor(s / 86_400)} d`;
}

/** "12 Nov 2026" in UTC, so every viewer sees the date the hub recorded. */
export function formatDay(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'unknown date';
  return new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
}
