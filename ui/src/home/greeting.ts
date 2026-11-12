// SPDX-License-Identifier: Apache-2.0
// Greeting and clock for Home. Time comes from the caller (the hub's clock) and the hub's
// time zone, so every screen and every test agree.

export type DayPart = 'morning' | 'afternoon' | 'evening' | 'night';

/** Hour 0-23 in `timeZone` (IANA name); falls back to UTC for an unknown zone. */
export function hourIn(now: number, timeZone: string): number {
  try {
    const h = new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hourCycle: 'h23', timeZone }).format(now);
    return Number.parseInt(h, 10) % 24;
  } catch {
    return new Date(now).getUTCHours();
  }
}

export function dayPart(hour: number): DayPart {
  if (hour >= 5 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 18) return 'afternoon';
  if (hour >= 18 && hour < 23) return 'evening';
  return 'night';
}

export function greeting(now: number, timeZone: string, name?: string): string {
  const part = dayPart(hourIn(now, timeZone));
  const hello = part === 'night' ? 'Good night' : `Good ${part}`;
  const who = name?.trim();
  return who ? `${hello}, ${who}` : hello;
}

function fmt(now: number, timeZone: string, opts: Intl.DateTimeFormatOptions): string {
  try {
    return new Intl.DateTimeFormat('en-GB', { ...opts, timeZone }).format(now);
  } catch {
    return new Intl.DateTimeFormat('en-GB', { ...opts, timeZone: 'UTC' }).format(now);
  }
}

/** "15:00" */
export const clockText = (now: number, timeZone: string) => fmt(now, timeZone, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
/** "Thursday 12 November" */
export const dateText = (now: number, timeZone: string) => fmt(now, timeZone, { weekday: 'long', day: 'numeric', month: 'long' });

export interface SummaryInput {
  waiting: number;
  staleNodes: number;
  offlineNodes: number;
  unhealthyApps: number;
  hubLive: boolean;
}

/** One calm line: what needs the person first, then what is not fine, else "all running". */
export function summaryLine(s: SummaryInput): string {
  if (!s.hubLive) return 'The hub is not answering. Everything below is its last known state.';
  const parts: string[] = [];
  if (s.waiting) parts.push(`${s.waiting} ${s.waiting === 1 ? 'request needs' : 'requests need'} your decision`);
  if (s.unhealthyApps) parts.push(`${s.unhealthyApps} ${s.unhealthyApps === 1 ? 'app is' : 'apps are'} unhealthy`);
  const nodeBits = [s.staleNodes && `${s.staleNodes} stale`, s.offlineNodes && `${s.offlineNodes} offline`].filter(Boolean);
  if (nodeBits.length) parts.push(`${nodeBits.join(' and ')} ${s.staleNodes + s.offlineNodes === 1 ? 'node' : 'nodes'}`);
  if (!parts.length) return 'Everything is running. Nothing needs you.';
  const [first, ...rest] = parts;
  const head = first!.charAt(0).toUpperCase() + first!.slice(1);
  return rest.length ? `${head}; ${rest.join('; ')}.` : `${head}.`;
}

/** "3 d 4 h", "5 h 12 min", "12 min"; "unknown" when missing. */
export function formatUptime(s: number | undefined | null): string {
  if (s == null || !Number.isFinite(s) || s < 0) return 'unknown';
  const d = Math.floor(s / 86_400);
  const h = Math.floor((s % 86_400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d} d ${h} h`;
  if (h) return `${h} h ${m} min`;
  return `${m} min`;
}
