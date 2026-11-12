// SPDX-License-Identifier: Apache-2.0
// Small pieces shared by Home: app glyph, status dot, category icon, freshness helpers.
import type { Tone } from '../tokens/tokens';
import { cx } from '../lib/cx';
import { freshness, NODE_LIMITS, type Freshness } from '../lib/freshness';
import { safeHttpUrl } from '../lib/trust';
import { secondsSince } from '../lib/time';
import type { AppRunState, HomeApp, HomeNode } from './types';
import type { CategoryInfo } from './taxonomy';

export const APP_STATE: Record<AppRunState, { tone: Tone; label: string; pulse?: boolean }> = {
  running: { tone: 'ok', label: 'Running' },
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

export function AppGlyph({ app, size = 56 }: { app: Pick<HomeApp, 'name' | 'icon' | 'hue'>; size?: number }) {
  const src = app.icon ? safeHttpUrl(app.icon) : null;
  return (
    <span className={cx('omh-glyph', `omh-hue-${app.hue ?? 'neutral'}`)} style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }} aria-hidden="true">
      {src ? <img src={src} alt="" width={size} height={size} loading="lazy" /> : app.name.trim().charAt(0).toUpperCase() || '?'}
    </span>
  );
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
