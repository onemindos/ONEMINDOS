// SPDX-License-Identifier: Apache-2.0
// Small pieces shared by Home: app glyph, status dot, category icon, freshness helpers.
import type { Tone } from '../tokens/tokens';
import { cx } from '../lib/cx';
import { freshness, NODE_LIMITS, type Freshness } from '../lib/freshness';
import { AppIcon } from '../components/AppIcon';
import { secondsSince } from '../lib/time';
import type { AppRunState, HomeApp, HomeNode } from './types';
import type { CategoryInfo } from './taxonomy';

export const APP_STATE: Record<AppRunState, { tone: Tone; label: string; pulse?: boolean }> = {
  running: { tone: 'ok', label: 'Running' },
  installed: { tone: 'info', label: 'Installed' },
  starting: { tone: 'info', label: 'Starting', pulse: true },
  updating: { tone: 'info', label: 'Updating', pulse: true },
  stopped: { tone: 'neutral', label: 'Stopped' },
  unhealthy: { tone: 'bad', label: 'Unhealthy' },
  unknown: { tone: 'neutral', label: 'Unknown' },
};

/** App state as Home may say it: when the hub is not live, it is the last known state. */
export function appState(app: Pick<HomeApp, 'status'>, hubLive: boolean): { tone: Tone; label: string; pulse?: boolean; lastKnown: boolean } {
  const s = APP_STATE[app.status ?? 'unknown'] ?? APP_STATE.unknown;
  return hubLive ? { ...s, lastKnown: false } : { tone: 'neutral', label: `${s.label} (last known)`, lastKnown: true };
}

export function nodeFreshness(n: HomeNode, now: number): Freshness {
  if (n.status === 'online') return 'live';
  if (n.status === 'stale' || n.status === 'offline') return n.status;
  return freshness(secondsSince(n.last_seen, now), NODE_LIMITS);
}

export function StatusDot({ tone, pulse, hollow, className }: { tone: Tone; pulse?: boolean; hollow?: boolean; className?: string }) {
  return <span className={cx('omh-dot', `om-tone-${tone}`, pulse && 'om-pulse', hollow && 'omh-dot-hollow', className)} aria-hidden="true" />;
}

/** Home's app icon is the shared AppIcon (CRITIQUE #20), so an app looks the same here and in the Store. */
export function AppGlyph({ app, size = 56 }: { app: Pick<HomeApp, 'id' | 'name' | 'icon'>; size?: number }) {
  return <AppIcon app={app} size={size} className="omh-glyph" />;
}

export function CategoryIcon({ category, size = 16 }: { category: Pick<CategoryInfo, 'icon'>; size?: number }) {
  return (
    <svg className="om-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={category.icon} />
    </svg>
  );
}

/** Percentage with no false precision: "42 %", "<1 %". */
export function pct(f: number): string {
  if (!Number.isFinite(f)) return 'unknown';
  const p = f * 100;
  return p > 0 && p < 1 ? '<1 %' : `${Math.round(p)} %`;
}

export function gb(mb: number): string {
  return `${(mb / 1024).toFixed(mb >= 10_240 ? 0 : 1)} GB`;
}

/** Temperature tone: amber at 75 °C, red at 85 °C (typical SoC throttle points). */
export function tempTone(c: number): Tone {
  return c >= 85 ? 'bad' : c >= 75 ? 'warn' : 'ok';
}
